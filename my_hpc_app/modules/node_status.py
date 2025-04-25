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
    nodes_updated = pyqtSignal(list)       # 节点信息更新信号
    error_occurred = pyqtSignal(str)       # 错误信号
    
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
        
        # 数据缓存，避免频繁查询
        self.data_cache = {
            'last_refresh': 0,
            'refresh_interval': 60,  # 刷新间隔（秒）
            'nodes_data': []
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
    
    def get_all_nodes(self):
        """
        获取所有节点的信息
        
        Returns:
            list: 节点信息列表
        """
        current_time = time.time()
        # 检查缓存是否有效
        if (self.data_cache['nodes_data'] and 
            current_time - self.data_cache['last_refresh'] < self.data_cache['refresh_interval']):
            return self.data_cache['nodes_data']
        
        # 使用sinfo命令获取节点信息
        cmd = 'sinfo -N -O "NodeList:20,CPUsState:14,Memory:9,AllocMem:10,Gres:14,GresUsed:22"'
        try:
            output = self.execute_ssh_command(cmd)
            nodes_data = self._parse_nodes_info(output)
            
            # 更新缓存
            self.data_cache['nodes_data'] = nodes_data
            self.data_cache['last_refresh'] = current_time
            
            # 发出信号
            self.nodes_updated.emit(nodes_data)
            
            return nodes_data
        except Exception as e:
            self.error_occurred.emit(f"获取节点信息失败: {str(e)}")
            return []
    
    def _parse_nodes_info(self, output):
        """
        解析节点信息输出
        
        Args:
            output: sinfo命令的输出
            
        Returns:
            list: 解析后的节点信息列表
        """
        lines = output.strip().split('\n')
        if len(lines) < 2:  # 至少应该有标题行和一行数据
            return []
        
        # 跳过标题行
        data_lines = lines[1:]
        nodes_dict = {}  # 使用字典来去重
        
        for line in data_lines:
            # 按空格分割，但保留括号内的内容
            parts = re.findall(r'([^\s]+(?:\([^)]*\)[^\s]*)?|\S+)', line.strip())
            if len(parts) < 6:
                continue
            
            # 解析数据
            node_name = parts[0]
            cpus_state = parts[1]
            memory = parts[2]
            alloc_mem = parts[3]
            gres = parts[4]
            gres_used = parts[5]
            
            # 解析CPU状态 (分配/空闲/脱机/总计)
            cpu_match = re.match(r'(\d+)/(\d+)/(\d+)/(\d+)', cpus_state)
            if cpu_match:
                alloc_cpus = int(cpu_match.group(1))
                idle_cpus = int(cpu_match.group(2))
                other_cpus = int(cpu_match.group(3))
                total_cpus = int(cpu_match.group(4))
            else:
                alloc_cpus = idle_cpus = other_cpus = total_cpus = 0
            
            # 解析GPU信息
            gpu_type = ""
            gpu_count = 0
            used_gpus = 0
            
            if gres != "(null)":
                gpu_match = re.search(r'gpu:([^:]+):(\d+)', gres)
                if gpu_match:
                    gpu_type = gpu_match.group(1)
                    gpu_count = int(gpu_match.group(2))
            
            if gres_used != "(null)":
                # GPU使用信息格式: gpu:TYPE:COUNT(IDX:indices)
                gpu_used_match = re.search(r'gpu:[^:]+:\d+\(IDX:([^)]*)\)', gres_used)
                if gpu_used_match:
                    indices = gpu_used_match.group(1)
                    if indices == "N/A":
                        used_gpus = 0
                    else:
                        # 计算使用的GPU数量（逗号分隔的索引）
                        used_gpus = len(indices.split('-')) if '-' in indices else len(indices.split(','))
            
            # 转换内存数据为GB格式
            memory_gb = self._convert_to_gb(memory)
            alloc_mem_gb = self._convert_to_gb(alloc_mem)
            
            # 节点使用率计算
            cpu_usage = (alloc_cpus / total_cpus * 100) if total_cpus > 0 else 0
            memory_usage = (float(alloc_mem) / float(memory) * 100) if float(memory) > 0 else 0
            gpu_usage = (used_gpus / gpu_count * 100) if gpu_count > 0 else 0
            
            # 节点状态判断
            if other_cpus > 0:
                state = "故障"
            elif alloc_cpus == total_cpus:
                state = "满载"
            elif alloc_cpus > 0:
                state = "部分使用"
            else:
                state = "空闲"
            
            # 创建节点数据
            node = {
                'name': node_name,
                'alloc_cpus': alloc_cpus,
                'idle_cpus': idle_cpus,
                'other_cpus': other_cpus,
                'total_cpus': total_cpus,
                'memory': memory_gb,
                'alloc_mem': alloc_mem_gb,
                'has_gpu': gres != "(null)",
                'gpu_type': gpu_type,
                'gpu_count': gpu_count,
                'used_gpus': used_gpus,
                'cpu_usage': cpu_usage,
                'memory_usage': memory_usage,
                'gpu_usage': gpu_usage,
                'state': state
            }
            
            # 使用节点名称作为键，合并重复节点时保留更多资源的记录
            if node_name in nodes_dict:
                existing_node = nodes_dict[node_name]
                # 如果新节点有GPU而现有节点没有，则替换
                if node['has_gpu'] and not existing_node['has_gpu']:
                    nodes_dict[node_name] = node
                # 如果两者相同或新节点没有GPU，保留现有节点信息
            else:
                nodes_dict[node_name] = node
        
        # 返回去重后的节点列表
        return list(nodes_dict.values())
    
    def _convert_to_gb(self, mem_str):
        """将内存字符串转换为GB格式
        
        Args:
            mem_str: 内存字符串，如 "192000" 表示 192000MB
            
        Returns:
            str: 格式化的GB字符串，如 "187.5GB"
        """
        try:
            # 将字符串转换为整数
            mem_mb = int(mem_str)
            # 转换为GB
            mem_gb = mem_mb / 1024.0
            # 格式化为字符串
            if mem_gb >= 100:
                # 大内存显示为整数
                return f"{int(mem_gb)}GB"
            elif mem_gb >= 10:
                # 中等内存显示为一位小数
                return f"{mem_gb:.1f}GB"
            else:
                # 小内存显示为两位小数
                return f"{mem_gb:.2f}GB"
        except (ValueError, TypeError):
            return mem_str
    
    def refresh_nodes(self):
        """
        强制刷新节点数据
        """
        # 清除缓存时间戳，强制刷新
        self.data_cache['last_refresh'] = 0
        return self.get_all_nodes()
    
    def get_nodes_by_type(self):
        """
        按类型分组获取节点
        
        Returns:
            dict: 按类型分组的节点字典
        """
        nodes = self.get_all_nodes()
        
        # 按类型分组
        grouped = {
            'cpu_nodes': [],
            'gpu_nodes': []
        }
        
        for node in nodes:
            if node['has_gpu']:
                grouped['gpu_nodes'].append(node)
            else:
                grouped['cpu_nodes'].append(node)
        
        return grouped
    
    def get_nodes_stats(self):
        """
        获取节点统计信息
        
        Returns:
            dict: 节点统计信息
        """
        nodes = self.get_all_nodes()
        
        total_nodes = len(nodes)
        used_nodes = sum(1 for n in nodes if n['alloc_cpus'] > 0)
        
        total_cpus = sum(n['total_cpus'] for n in nodes)
        used_cpus = sum(n['alloc_cpus'] for n in nodes)
        
        total_gpus = sum(n['gpu_count'] for n in nodes if n['has_gpu'])
        used_gpus = sum(n['used_gpus'] for n in nodes if n['has_gpu'])
        
        # 计算利用率
        node_usage = (used_nodes / total_nodes * 100) if total_nodes > 0 else 0
        cpu_usage = (used_cpus / total_cpus * 100) if total_cpus > 0 else 0
        gpu_usage = (used_gpus / total_gpus * 100) if total_gpus > 0 else 0
        
        return {
            'total_nodes': total_nodes,
            'used_nodes': used_nodes,
            'total_cpus': total_cpus,
            'used_cpus': used_cpus,
            'total_gpus': total_gpus,
            'used_gpus': used_gpus,
            'node_usage': node_usage,
            'cpu_usage': cpu_usage,
            'gpu_usage': gpu_usage
        }
    
    def __del__(self):
        """析构函数，确保关闭SSH连接"""
        if hasattr(self, '_ssh_client') and self._ssh_client:
            try:
                self._ssh_client.close()
            except Exception as e:
                logging.error(f"关闭SSH连接失败: {str(e)}") 