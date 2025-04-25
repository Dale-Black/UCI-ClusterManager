#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import re
import logging
import paramiko
import threading
from PyQt5.QtCore import QObject, pyqtSignal
import time
import traceback
import socket

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class StorageManager(QObject):
    """
    存储管理器，用于查询用户在HPC上的各种存储空间使用情况
    """
    
    # 信号定义
    storage_updated = pyqtSignal(dict)  # 存储信息更新信号
    error_occurred = pyqtSignal(str)    # 错误信号
    
    def __init__(self, hostname, username, key_path=None, password=None):
        """
        初始化存储管理器
        
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
        self.lock = threading.Lock()  # 线程锁确保SSH连接安全
        
        # 缓存SSH客户端
        self._ssh_client = None
        
        # 尝试连接
        self.connect_ssh()
    
    def connect_ssh(self):
        """连接到SSH服务器"""
        try:
            if self._ssh_client and self._ssh_client.get_transport() and self._ssh_client.get_transport().is_active():
                logger.debug("SSH连接已存在且活跃")
                return True
            
            # 如果有旧的连接，先关闭
            if self._ssh_client:
                try:
                    self._ssh_client.close()
                except:
                    pass
            
            # 创建新的SSH客户端
            logger.info(f"连接到SSH服务器: {self.hostname}@{self.username}")
            self._ssh_client = paramiko.SSHClient()
            self._ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            
            # 使用密钥或密码连接
            if self.key_path:
                self._ssh_client.connect(
                    hostname=self.hostname,
                    username=self.username,
                    key_filename=self.key_path,
                    timeout=15,
                    look_for_keys=False,
                    allow_agent=False
                )
            elif self.password:
                self._ssh_client.connect(
                    hostname=self.hostname,
                    username=self.username,
                    password=self.password,
                    timeout=15,
                    look_for_keys=False,
                    allow_agent=False
                )
            else:
                error_msg = "必须提供密钥路径或密码"
                logger.error(error_msg)
                self.error_occurred.emit(error_msg)
                return False
            
            logger.info("SSH连接成功")
            return True
        except Exception as e:
            error_msg = f"SSH连接失败: {str(e)}"
            logger.error(error_msg)
            self.error_occurred.emit(error_msg)
            return False
    
    def _close_ssh_client(self):
        """安全关闭SSH客户端连接"""
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
        """
        try:
            # 确保有连接
            if not self._ssh_client or not self._ssh_client.get_transport() or not self._ssh_client.get_transport().is_active():
                if not self.connect_ssh():
                    raise Exception("无法连接到SSH服务器")
            
            # 执行命令
            stdin, stdout, stderr = self._ssh_client.exec_command(command, timeout=30)
            output = stdout.read().decode('utf-8')
            error = stderr.read().decode('utf-8')
            
            # 如果有错误且无输出，则抛出异常
            if error and not output:
                logger.error(f"命令执行出错: {error}")
                raise Exception(f"命令执行出错: {error}")
            
            return output
        except Exception as e:
            logger.error(f"执行命令失败: {str(e)}")
            # 尝试重新连接
            self.connect_ssh()
            raise Exception(f"执行命令失败: {str(e)}")
    
    def get_all_storage_info(self):
        """
        获取所有存储空间的信息
        
        Returns:
            dict: 包含所有存储空间信息的字典
        """
        try:
            logger.info("开始获取存储信息")
            storage_data = {}
            
            # 1. 获取HOME信息
            home_path = self.find_home_directory()
            if home_path:
                storage_data['home'] = self.get_storage_usage(home_path)
            else:
                storage_data['home'] = {
                    'path': f"/data/homez*/{self.username}",
                    'exists': False,
                    'error': "无法找到HOME目录"
                }
            
            # 2. 获取DFS信息
            personal_dfs, lab_dfs_paths = self.check_dfs_locations()
            
            if personal_dfs:
                storage_data['personal_dfs'] = self.get_storage_usage(personal_dfs)
            
            # Lab DFS可能有多个
            storage_data['lab_dfs'] = []
            for lab_path in lab_dfs_paths:
                if lab_path.strip():
                    lab_info = self.get_storage_usage(lab_path)
                    storage_data['lab_dfs'].append(lab_info)
            
            # 3. 获取CRSP信息
            personal_crsp, lab_crsp = self.check_crsp_locations()
            
            if personal_crsp:
                storage_data['personal_crsp'] = self.get_storage_usage(personal_crsp)
            
            if lab_crsp:
                storage_data['lab_crsp'] = self.get_storage_usage(lab_crsp)
            
            # 4. 获取Scratch信息(当前节点的临时存储)
            storage_data['scratch'] = self.get_storage_usage('$TMPDIR')
            
            # 发出信号更新UI
            self.storage_updated.emit(storage_data)
            logger.info("存储信息获取完成")
            
            return storage_data
        except Exception as e:
            logger.error(f"获取存储信息失败: {str(e)}")
            self.error_occurred.emit(f"获取存储信息失败: {str(e)}")
            return {}
    
    def find_home_directory(self):
        """
        查找用户的HOME目录在哪个homezvolX
        
        Returns:
            str: HOME目录的完整路径
        """
        try:
            # 执行命令查找HOME目录
            cmd = "echo $HOME"
            output = self.execute_ssh_command(cmd)
            home_path = output.strip()
            
            # 检查是否是预期的格式
            if "/data/homez" in home_path:
                logger.info(f"找到HOME目录: {home_path}")
                return home_path
            else:
                # 尝试通过pwd命令获取
                cmd = "pwd"
                output = self.execute_ssh_command(cmd)
                home_path = output.strip()
                if "/data/homez" in home_path:
                    return home_path
                else:
                    # 最后尝试直接使用格式化路径
                    home_path = f"/data/homez*/{self.username}"
                    cmd = f"ls -d {home_path} 2>/dev/null"
                    output = self.execute_ssh_command(cmd)
                    if output.strip():
                        return output.strip()
            
            # 如果上述方法都失败，则返回None
            return None
        except Exception as e:
            logger.error(f"查找HOME目录失败: {str(e)}")
            return None
    
    def find_lab_name(self):
        """
        根据用户余额信息查找实验室名称
        
        Returns:
            str: 实验室名称
        """
        try:
            # 执行sbank命令获取余额，从中提取实验室名称
            cmd = f"sbank balance statement -u {self.username}"
            output = self.execute_ssh_command(cmd)
            
            # 查找形如 SYMOLLOI_LAB 的字符串
            lab_pattern = r'[A-Z]+_LAB'
            matches = re.findall(lab_pattern, output)
            
            if matches:
                # 移除_LAB后缀并转为小写
                lab_name = matches[0].replace('_LAB', '').lower()
                logger.info(f"找到实验室名称: {lab_name}")
                return lab_name
            else:
                # 尝试查找其他可能的实验室名称格式
                account_pattern = r'(\w+)\s+\|'
                matches = re.findall(account_pattern, output)
                if len(matches) > 1:  # 第一个匹配通常是用户名
                    potential_lab = matches[1]
                    if potential_lab.upper() != self.username.upper():
                        return potential_lab.lower()
            
            # 如果找不到，返回None
            return None
        except Exception as e:
            logger.error(f"查找实验室名称失败: {str(e)}")
            return None
    
    def check_dfs_locations(self):
        """
        检查DFS个人和实验室空间
        
        Returns:
            tuple: (personal_dfs, lab_dfs)
                - personal_dfs: 个人DFS路径
                - lab_dfs: 实验室DFS路径列表
        """
        try:
            # 个人DFS路径是固定的
            personal_dfs = f"/pub/{self.username}"
            
            # 检查实验室DFS路径
            lab_dfs_paths = []
            
            # 查找可能的dfs目录
            cmd = "ls -d /dfs* 2>/dev/null"
            output = self.execute_ssh_command(cmd)
            dfs_roots = output.strip().split('\n')
            
            # 查找实验室名称，用于在DFS中查找
            lab_name = self.find_lab_name()
            
            if lab_name:
                # 在每个dfs目录中查找实验室目录
                for dfs_root in dfs_roots:
                    if not dfs_root.strip():
                        continue
                    
                    # 尝试不同的可能路径模式
                    patterns = [
                        f"{dfs_root}/{lab_name}*",
                        f"{dfs_root}/*{lab_name}*"
                    ]
                    
                    for pattern in patterns:
                        cmd = f"ls -d {pattern} 2>/dev/null"
                        try:
                            output = self.execute_ssh_command(cmd)
                            if output.strip():
                                lab_dfs_paths.extend(output.strip().split('\n'))
                        except:
                            pass
            
            return personal_dfs, lab_dfs_paths
        except Exception as e:
            logger.error(f"检查DFS位置失败: {str(e)}")
            return None, []
    
    def check_crsp_locations(self):
        """
        检查CRSP个人和实验室共享空间
        
        Returns:
            tuple: (personal_crsp, lab_crsp)
                - personal_crsp: 个人CRSP路径
                - lab_crsp: 实验室共享CRSP路径
        """
        try:
            lab_name = self.find_lab_name()
            
            if not lab_name:
                return None, None
            
            personal_crsp = f"/share/crsp/lab/{lab_name}/{self.username}"
            lab_crsp = f"/share/crsp/lab/{lab_name}/share"
            
            return personal_crsp, lab_crsp
        except Exception as e:
            logger.error(f"检查CRSP位置失败: {str(e)}")
            return None, None
    
    def get_storage_usage(self, path):
        """
        获取指定路径的存储使用情况
        
        Args:
            path: 要检查的路径
            
        Returns:
            dict: 包含总容量、已用空间和可用空间的字典
        """
        try:
            # 检查目录是否存在
            cmd = f"test -d {path} && echo exists || echo notexists"
            output = self.execute_ssh_command(cmd)
            if output.strip() == "notexists":
                return {
                    'path': path,
                    'exists': False,
                    'total': 0,
                    'used': 0,
                    'available': 0,
                    'use_percent': 0
                }
            
            # 使用df命令检查使用情况
            cmd = f"df -h {path} | tail -n 1"
            output = self.execute_ssh_command(cmd)
            
            parts = output.strip().split()
            if len(parts) >= 6:
                # 典型的df输出格式: Filesystem Size Used Avail Use% Mounted on
                filesystem = parts[0]
                total = parts[1]
                used = parts[2]
                available = parts[3]
                use_percent = parts[4].replace('%', '')
                mounted_on = ' '.join(parts[5:])
                
                return {
                    'path': path,
                    'exists': True,
                    'filesystem': filesystem,
                    'total': total,
                    'used': used,
                    'available': available,
                    'use_percent': use_percent,
                    'mounted_on': mounted_on
                }
            else:
                logger.warning(f"无法解析df输出: {output}")
                return {
                    'path': path,
                    'exists': True,
                    'total': 'Unknown',
                    'used': 'Unknown',
                    'available': 'Unknown',
                    'use_percent': 'Unknown'
                }
        except Exception as e:
            logger.error(f"获取存储使用情况失败: {str(e)}")
            return {
                'path': path,
                'exists': False,
                'total': 'Error',
                'used': 'Error',
                'available': 'Error',
                'use_percent': 'Error',
                'error': str(e)
            }
    
    def refresh_storage_info(self):
        """
        强制刷新存储信息
        
        Returns:
            dict: 更新后的存储信息
        """
        logger.info("开始刷新存储信息")
        return self.get_all_storage_info()
    
    def __del__(self):
        """析构函数，确保关闭SSH连接"""
        if hasattr(self, '_ssh_client') and self._ssh_client:
            try:
                self._ssh_client.close()
            except Exception as e:
                logging.error(f"关闭SSH连接失败: {str(e)}") 