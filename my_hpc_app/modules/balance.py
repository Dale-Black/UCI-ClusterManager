#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import re
import logging
import paramiko
import threading
from PyQt5.QtCore import QObject, pyqtSignal

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class BalanceManager(QObject):
    """
    计算资源余额管理器，用于查询用户的资源使用情况和余额
    """
    
    # 信号定义
    balance_updated = pyqtSignal(dict)  # 余额信息更新信号
    error_occurred = pyqtSignal(str)    # 错误信号
    
    def __init__(self, hostname, username, key_path=None, password=None):
        """
        初始化余额管理器
        
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
        
        # 数据缓存
        self.data_cache = {
            'last_refresh': 0,
            'balance_data': None
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
    
    def get_user_balance(self, username=None):
        """
        获取用户的资源余额信息
        
        Args:
            username: 要查询的用户名，默认为当前登录用户
            
        Returns:
            dict: 包含用户余额信息的字典
        """
        username = username or self.username
        
        try:
            # 执行sbank命令获取余额
            cmd = f"sbank balance statement -u {username}"
            output = self.execute_ssh_command(cmd)
            
            # 解析输出
            balance_data = self._parse_balance_output(output, username)
            
            # 发送信号通知UI更新
            self.balance_updated.emit(balance_data)
            
            # 更新缓存
            self.data_cache['balance_data'] = balance_data
            
            return balance_data
        except Exception as e:
            error_msg = f"获取用户余额失败: {str(e)}"
            logger.error(error_msg)
            self.error_occurred.emit(error_msg)
            return None
    
    def _parse_balance_output(self, output, target_username):
        """
        解析sbank命令输出
        
        Args:
            output: sbank命令输出字符串
            target_username: 目标用户名
            
        Returns:
            dict: 解析后的余额数据
        """
        result = {
            'username': target_username,
            'accounts': [],
            'total_available': 0,
            'total_usage': 0
        }
        
        lines = output.strip().split('\n')
        
        # 至少需要有3行（包括两行标题和至少一行数据）
        if len(lines) < 3:
            return result
        
        # 跳过标题行
        current_account = None
        
        for line in lines[2:]:  # 跳过前两行标题
            # 跳过空行
            if not line.strip():
                continue
                
            # 匹配行数据
            parts = re.split(r'\s+\|\s+', line.strip())
            
            if len(parts) != 3:
                continue
            
            # 解析每部分
            user_part = parts[0].strip()
            account_part = parts[1].strip()
            limit_part = parts[2].strip()
            
            # 解析用户部分
            user_parts = re.split(r'\s+', user_part)
            if len(user_parts) < 2:
                continue
                
            username = user_parts[0]
            
            # 检查是否包含星号（标记当前用户）
            is_current = '*' in user_part
            user_usage = int(user_parts[-1].replace(',', ''))
            
            # 解析账户部分
            account_parts = re.split(r'\s+', account_part)
            if len(account_parts) < 2:
                continue
                
            account_name = account_parts[0]
            account_usage = int(account_parts[-1].replace(',', ''))
            
            # 解析限制和可用部分
            limit_parts = re.split(r'\s+', limit_part)
            if len(limit_parts) < 2:
                continue
                
            account_limit = int(limit_parts[0].replace(',', ''))
            available = int(limit_parts[-1].replace(',', ''))
            
            # 如果用户名匹配目标用户，添加到结果
            if username == target_username:
                # 检查是否是相同账户的新条目
                if current_account and current_account['name'] == account_name:
                    # 更新现有账户信息
                    current_account['user_usage'] += user_usage
                else:
                    # 创建新账户条目
                    current_account = {
                        'name': account_name,
                        'user_usage': user_usage,
                        'account_usage': account_usage,
                        'account_limit': account_limit,
                        'available': available,
                        'is_personal': account_name.upper() == target_username.upper()
                    }
                    result['accounts'].append(current_account)
                
                # 累计总使用量
                if is_current:
                    result['total_usage'] += user_usage
                    
                    # 如果是个人账户，添加到总可用量
                    if current_account['is_personal']:
                        result['total_available'] += available
        
        return result
    
    def refresh_balance(self):
        """
        强制刷新余额信息
        
        Returns:
            dict: 更新后的余额信息
        """
        return self.get_user_balance()
    
    def __del__(self):
        """析构函数，确保关闭SSH连接"""
        if hasattr(self, '_ssh_client') and self._ssh_client:
            try:
                self._ssh_client.close()
            except Exception as e:
                logging.error(f"关闭SSH连接失败: {str(e)}") 