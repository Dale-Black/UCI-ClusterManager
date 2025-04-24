#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import logging
import paramiko
import re
import time
import threading
from PyQt5.QtCore import QObject, pyqtSignal

# 配置日志记录
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class NodeStatusManager(QObject):
    """节点状态管理器，用于查询HPC集群节点信息"""
    
    # 信号定义
    partition_info_updated = pyqtSignal(dict)  # 分区信息更新信号
    node_info_updated = pyqtSignal(dict)       # 节点信息更新信号
    error_occurred = pyqtSignal(str)           # 错误信号
    
    def __init__(self, hostname, username, key_path=None, password=None):
        """
        初始化节点状态管理器
        
        Args:
            hostname: HPC主机名
            username: 用户名
            key_path: SSH密钥路径
            password: SSH密码
        """
        super().__init__()
        self.hostname = hostname
        self.username = username
        self.key_path = key_path
        self.password = password
        self.lock = threading.Lock()  # 添加线程锁以确保SSH连接的线程安全
        
        # 缓存SSH客户端
        self._ssh_client = None
        
        # 定义所有需要查询的分区
        self.all_partitions = [
            "free", "free-gpu", "free-gpu32", "gpu", "gpu-hugemem", 
            "gpu32", "highmem", "maxmem", "standard"
        ]
        
        # 分区特性
        self.partition_features = {
            "free": "免费CPU",
            "free-gpu": "免费GPU",
            "free-gpu32": "免费GPU32",
            "gpu": "标准GPU",
            "gpu-hugemem": "大内存GPU",
            "gpu32": "GPU32",
            "highmem": "高内存CPU",
            "maxmem": "最大内存CPU",
            "standard": "标准CPU"
        }
        
        # 数据缓存，避免频繁查询
        self.data_cache = {
            'last_refresh': 0,
            'refresh_interval': 120,  # 刷新间隔（秒）
            'node_data': None
        }
        
        # 尝试连接
        self.connect_ssh()
    
    def connect_ssh(self):
        """连接到SSH服务器"""
        try:
            with self.lock:
                if self._ssh_client and self._ssh_client.get_transport() and self._ssh_client.get_transport().is_active():
                    return True
                
                # 创建新的SSH客户端
                self._ssh_client = paramiko.SSHClient()
                self._ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                
                # 使用密钥或密码连接
                if self.key_path:
                    self._ssh_client.connect(
                        hostname=self.hostname,
                        username=self.username,
                        key_filename=self.key_path,
                        timeout=10
                    )
                elif self.password:
                    self._ssh_client.connect(
                        hostname=self.hostname,
                        username=self.username,
                        password=self.password,
                        timeout=10
                    )
                else:
                    raise ValueError("必须提供密钥路径或密码")
                
                return True
        except Exception as e:
            logger.error(f"SSH连接失败: {e}")
            self.error_occurred.emit(f"SSH连接失败: {str(e)}")
            return False
    
    def _close_ssh_client(self):
        """安全关闭SSH客户端连接"""
        with self.lock:
            if self._ssh_client:
                try:
                    self._ssh_client.close()
                except:
                    pass
                self._ssh_client = None
    
    def _convert_memory_to_gb(self, memory_str):
        """
        将内存字符串转换为GB单位
        
        Args:
            memory_str: 内存字符串，例如 "16384M" 或 "16G" 或 "16777216K"
            
        Returns:
            str: 转换后的内存字符串，带有GB单位
        """
        if not memory_str or memory_str == 'N/A':
            return 'N/A'
            
        # 提取数字和单位
        match = re.match(r'(\d+)([KMGTkmgt]?)', memory_str)
        if not match:
            return memory_str
            
        value = float(match.group(1))  # 使用float避免整数除法问题
        unit = match.group(2).upper() if match.group(2) else ''
        
        # 转换为GB
        if unit == 'K':
            gb_value = value / (1024 * 1024)
        elif unit == 'M':
            gb_value = value / 1024
        elif unit == 'G':
            gb_value = value  # 已经是GB
        elif unit == 'T':
            gb_value = value * 1024
        else:  # 没有单位，假设为MB
            gb_value = value / 1024
        
        # 格式化输出，如果值很小就保留更多小数位
        if gb_value < 0.1:
            return f"{gb_value:.4f}GB"
        elif gb_value < 1:
            return f"{gb_value:.2f}GB"
        else:
            # 对于大于1GB的值，取整数部分就足够了
            return f"{int(gb_value)}GB"
    
    def execute_ssh_command(self, command):
        """
        执行SSH命令并返回结果
        
        Args:
            command: 要执行的命令
            
        Returns:
            str: 命令的输出结果
            
        Raises:
            Exception: 执行命令出错
        """
        with self.lock:
            if not self._ssh_client or not self._ssh_client.get_transport() or not self._ssh_client.get_transport().is_active():
                if not self.connect_ssh():
                    raise Exception("无法连接到SSH服务器")
            
            try:
                logger.debug(f"执行命令: {command}")
                stdin, stdout, stderr = self._ssh_client.exec_command(command, timeout=30)
                output = stdout.read().decode('utf-8')
                error = stderr.read().decode('utf-8')
                
                if error and not output:
                    logger.error(f"命令出错: {error}")
                    raise Exception(f"命令执行出错: {error}")
                
                return output
            except Exception as e:
                logger.error(f"执行命令失败: {e}")
                # 尝试重新连接
                self.connect_ssh()
                raise
    
    def get_all_partitions_info(self):
        """
        获取所有分区的基本信息
        
        Returns:
            dict: 分区信息字典
        """
        cmd = "sinfo -o '%P|%a|%l|%c|%m|%D|%N|%E' -h"
        output = self.execute_ssh_command(cmd)
        
        partition_data = {}
        for line in output.strip().split('\n'):
            if not line.strip():
                continue
            
            parts = line.split('|')
            if len(parts) < 6:
                continue
            
            partition_name = parts[0].strip()
            
            # 保存分区信息
            partition_data[partition_name] = {
                'name': partition_name,
                'available': parts[1].strip(),
                'time_limit': parts[2].strip(),
                'cpus': parts[3].strip(),
                'memory': self._convert_memory_to_gb(parts[4].strip()),
                'nodes': parts[5].strip(),
                'node_names': parts[6].strip() if len(parts) > 6 else "",
                'description': parts[7].strip() if len(parts) > 7 else "",
                'node_list': []  # 将存储该分区的节点列表
            }
            
            # 保存分区名称列表
            if partition_name not in self.all_partitions:
                self.all_partitions.append(partition_name)
        
        # 获取每个分区的节点详情
        for partition_name in partition_data.keys():
            # 根据分区类型选择不同的查询方式
            if "gpu" in partition_name.lower():
                nodes = self.get_gpu_partition_nodes(partition_name)
            else:
                nodes = self.get_cpu_partition_nodes(partition_name)
            
            # 添加到分区信息中
            partition_data[partition_name]['node_list'] = nodes
        
        # 发送更新信号
        self.partition_info_updated.emit(partition_data)
        
        return partition_data
    
    def get_gpu_partition_nodes(self, partition_name):
        """
        获取GPU分区的节点信息
        
        Args:
            partition_name: 分区名称
            
        Returns:
            list: 节点信息列表
        """
        cmd = f'sinfo -NO "NodeList:20,CPUsState:14,Memory:9,AllocMem:10,Gres:14,GresUsed:22,StateComplete:10" -p {partition_name} -h'
        output = self.execute_ssh_command(cmd)
        
        nodes = []
        for line in output.strip().split('\n'):
            if not line.strip():
                continue
            
            parts = line.split()
            if len(parts) < 4:
                continue
            
            node_name = parts[0]
            cpus_info = parts[1]
            memory = parts[2]
            allocated_mem = parts[3]
            
            # 解析CPU状态信息
            cpu_match = re.search(r'(\d+)/(\d+)/(\d+)/(\d+)', cpus_info)
            if cpu_match:
                allocated_cpus = int(cpu_match.group(1))
                idle_cpus = int(cpu_match.group(2))
                total_cpus = allocated_cpus + idle_cpus + int(cpu_match.group(3)) + int(cpu_match.group(4))
            else:
                allocated_cpus = 0
                total_cpus = 0
            
            # 计算CPU使用百分比
            if total_cpus > 0:
                cpu_usage_value = (allocated_cpus / total_cpus) * 100
                cpu_usage = f"{cpu_usage_value:.1f}%"
            else:
                cpu_usage_value = 0
                cpu_usage = "0.0%"
            
            # 解析GPU信息
            gpu_type = "未知"
            gpu_count = 0
            gpu_used = 0
            
            if len(parts) > 4:
                gres_info = parts[4]
                gres_used_info = parts[5] if len(parts) > 5 else ""
                
                # 解析GPU类型和数量
                gpu_match = re.search(r'gpu:([^:]+):(\d+)', gres_info)
                if gpu_match:
                    gpu_type = gpu_match.group(1)
                    gpu_count = int(gpu_match.group(2))
                
                # 解析已使用的GPU数量
                gpu_used_match = re.search(r'gpu:([^:]+):\d+\(IDX:([^)]+)\)', gres_used_info)
                if gpu_used_match:
                    # 计算使用的GPU数量
                    gpu_indices = gpu_used_match.group(2)
                    if gpu_indices:
                        # 计算逗号分隔的数量
                        gpu_used = len(gpu_indices.split(','))
            
            # 计算GPU使用百分比
            if gpu_count > 0:
                gpu_usage_value = (gpu_used / gpu_count) * 100
                gpu_usage = f"{gpu_usage_value:.1f}%"
            else:
                gpu_usage_value = 0
                gpu_usage = "0.0%"
            
            # 节点状态
            node_state = parts[6] if len(parts) > 6 else "未知"
            
            # 创建节点信息
            node_info = {
                'node_name': node_name,
                'total_cpus': total_cpus,
                'allocated_cpus': allocated_cpus,
                'memory': memory,
                'allocated_memory': allocated_mem,
                'gpu_type': gpu_type,
                'gpu_count': gpu_count,
                'gpu_used': gpu_used,
                'state': node_state,
                'partition': partition_name,
                'cpu_usage': cpu_usage,
                'cpu_usage_value': cpu_usage_value,
                'gpu_usage': gpu_usage,
                'gpu_usage_value': gpu_usage_value
            }
            
            nodes.append(node_info)
        
        return nodes
    
    def get_cpu_partition_nodes(self, partition_name):
        """
        获取CPU分区的节点信息
        
        Args:
            partition_name: 分区名称
            
        Returns:
            list: 节点信息列表
        """
        cmd = f'sinfo -NO "NodeList:20,CPUsState:14,Memory:9,AllocMem:10,Features:20,StateComplete:10" -p {partition_name} -h'
        output = self.execute_ssh_command(cmd)
        
        nodes = []
        for line in output.strip().split('\n'):
            if not line.strip():
                continue
            
            parts = line.split()
            if len(parts) < 4:
                continue
            
            node_name = parts[0]
            cpus_info = parts[1]
            memory = parts[2]
            allocated_mem = parts[3]
            
            # 解析CPU状态信息
            cpu_match = re.search(r'(\d+)/(\d+)/(\d+)/(\d+)', cpus_info)
            if cpu_match:
                allocated_cpus = int(cpu_match.group(1))
                idle_cpus = int(cpu_match.group(2))
                total_cpus = allocated_cpus + idle_cpus + int(cpu_match.group(3)) + int(cpu_match.group(4))
            else:
                allocated_cpus = 0
                total_cpus = 0
            
            # 计算CPU使用百分比
            if total_cpus > 0:
                cpu_usage_value = (allocated_cpus / total_cpus) * 100
                cpu_usage = f"{cpu_usage_value:.1f}%"
            else:
                cpu_usage_value = 0
                cpu_usage = "0.0%"
            
            # 特性
            features = parts[4] if len(parts) > 4 else "无"
            
            # 节点状态
            node_state = parts[5] if len(parts) > 5 else "未知"
            
            # 创建节点信息
            node_info = {
                'node_name': node_name,
                'total_cpus': total_cpus,
                'allocated_cpus': allocated_cpus,
                'memory': memory,
                'allocated_memory': allocated_mem,
                'features': features,
                'state': node_state,
                'partition': partition_name,
                'cpu_usage': cpu_usage,
                'cpu_usage_value': cpu_usage_value
            }
            
            nodes.append(node_info)
        
        return nodes
    
    def get_all_nodes_by_partition(self):
        """
        获取所有分区的节点信息
        
        Returns:
            dict: 按分区组织的节点信息字典
        """
        # 获取分区基本信息
        partition_data = self.get_all_partitions_info()
        
        # 为每个分区获取节点信息
        for partition_name in list(partition_data.keys()):
            if "gpu" in partition_name.lower():
                # GPU分区
                partition_data[partition_name]['node_list'] = self.get_gpu_partition_nodes(partition_name)
            else:
                # CPU分区
                partition_data[partition_name]['node_list'] = self.get_cpu_partition_nodes(partition_name)
        
        # 发送更新信号
        self.partition_info_updated.emit(partition_data)
        
        return partition_data
    
    def get_nodes_by_partition(self, partition_name=None):
        """
        按分区获取节点信息
        
        Args:
            partition_name: 可选，特定分区的名称。如果未提供，则返回所有分区的信息
            
        Returns:
            dict: 按分区组织的节点信息字典
        """
        try:
            # 检查缓存
            current_time = time.time()
            if (self.data_cache['node_data'] and 
                current_time - self.data_cache['last_refresh'] < self.data_cache['refresh_interval']):
                # 使用缓存数据
                partitions = self.data_cache['node_data']['partitions']
            else:
                # 刷新数据
                node_data = self.refresh_all_nodes()
                if not node_data:
                    return {}
                partitions = node_data['partitions']
            
            # 如果指定了特定分区，只返回该分区的信息
            if partition_name:
                if partition_name in partitions:
                    return {partition_name: partitions[partition_name]}
                else:
                    logger.warning(f"找不到指定的分区: {partition_name}")
                    return {}
            
            # 否则返回所有分区数据
            return partitions
        except Exception as e:
            logger.error(f"按分区获取节点信息失败: {e}")
            self.error_occurred.emit(f"按分区获取节点信息失败: {str(e)}")
            return {}
    
    def refresh_all_nodes(self):
        """
        刷新所有节点信息，发送信号通知UI更新
        """
        try:
            # 检查是否需要刷新
            current_time = time.time()
            if (self.data_cache['node_data'] and 
                current_time - self.data_cache['last_refresh'] < self.data_cache['refresh_interval']):
                # 使用缓存数据
                self.node_info_updated.emit(self.data_cache['node_data'])
                return
            
            # 获取分区信息
            partition_data = self.get_all_partitions_info()
            
            # 分离GPU和CPU节点
            gpu_nodes = []
            cpu_nodes = []
            
            for partition_name, partition_info in partition_data.items():
                if "gpu" in partition_name.lower():
                    gpu_nodes.extend(partition_info['node_list'])
                else:
                    cpu_nodes.extend(partition_info['node_list'])
            
            # 移除重复节点（一个节点可能属于多个分区）
            unique_gpu_nodes = []
            seen_gpu_nodes = set()
            for node in gpu_nodes:
                if node['node_name'] not in seen_gpu_nodes:
                    seen_gpu_nodes.add(node['node_name'])
                    unique_gpu_nodes.append(node)
            
            unique_cpu_nodes = []
            seen_cpu_nodes = set()
            for node in cpu_nodes:
                if node['node_name'] not in seen_cpu_nodes:
                    seen_cpu_nodes.add(node['node_name'])
                    unique_cpu_nodes.append(node)
            
            # 整合数据
            node_data = {
                'partitions': partition_data,
                'gpu_nodes': unique_gpu_nodes,
                'cpu_nodes': unique_cpu_nodes,
                'refresh_time': current_time
            }
            
            # 更新缓存
            self.data_cache['node_data'] = node_data
            self.data_cache['last_refresh'] = current_time
            
            # 保存到实例变量
            self.partitions_info = partition_data
            self.gpu_nodes = unique_gpu_nodes
            self.cpu_nodes = unique_cpu_nodes
            
            # 发送信号
            self.node_info_updated.emit(node_data)
            
            return node_data
        except Exception as e:
            logger.error(f"刷新节点信息失败: {e}")
            self.error_occurred.emit(f"刷新节点信息失败: {str(e)}")
            return None
    
    def __del__(self):
        """析构函数，确保关闭SSH连接"""
        if hasattr(self, '_ssh_client') and self._ssh_client:
            try:
                self._ssh_client.close()
            except Exception as e:
                logging.error(f"关闭SSH连接失败: {str(e)}") 