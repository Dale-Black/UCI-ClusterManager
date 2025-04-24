#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import logging
import subprocess
import paramiko
import os
import re
import json
import time
from PyQt5.QtCore import QObject, pyqtSignal

# 配置日志记录
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class SlurmManager(QObject):
    """Slurm任务管理器，用于与SLURM交互"""
    
    # 信号定义
    job_list_updated = pyqtSignal(list)  # 作业列表更新信号
    job_submitted = pyqtSignal(str)  # 作业提交信号
    job_canceled = pyqtSignal(str)  # 作业取消信号
    error_occurred = pyqtSignal(str)  # 错误信号
    
    def __init__(self, hostname, username, key_path):
        """
        初始化Slurm任务管理器
        
        Args:
            hostname: HPC主机名
            username: 用户名
            key_path: SSH密钥路径
        """
        super().__init__()
        self.hostname = hostname
        self.username = username
        self.key_path = key_path
        
    def _get_ssh_client(self):
        """
        获取SSH客户端连接
        
        Returns:
            paramiko.SSHClient: SSH客户端
        """
        try:
            client = paramiko.SSHClient()
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            client.connect(
                hostname=self.hostname,
                username=self.username,
                key_filename=self.key_path,
                look_for_keys=False
            )
            return client
        except Exception as e:
            logging.error(f"SSH连接失败: {e}")
            self.error_occurred.emit(f"SSH连接失败: {str(e)}")
            return None
    
    def get_jobs(self):
        """
        获取当前用户的所有作业
        
        Returns:
            list: 作业列表
        """
        try:
            client = self._get_ssh_client()
            if not client:
                return []
                
            try:
                # 使用squeue命令获取作业信息
                cmd = f"squeue -u {self.username} -o '%A|%j|%T|%M|%L|%D|%C|%R' -h"
                stdin, stdout, stderr = client.exec_command(cmd)
                
                # 解析输出
                jobs = []
                for line in stdout:
                    line = line.strip()
                    if not line:
                        continue
                        
                    parts = line.split('|')
                    if len(parts) == 8:
                        job = {
                            'id': parts[0],
                            'name': parts[1],
                            'state': parts[2],
                            'time': parts[3],
                            'time_limit': parts[4],
                            'nodes': parts[5],
                            'cpus': parts[6],
                            'reason': parts[7]
                        }
                        jobs.append(job)
                
                # 发送作业列表更新信号
                self.job_list_updated.emit(jobs)
                return jobs
            finally:
                client.close()
        except Exception as e:
            logging.error(f"获取作业列表失败: {e}")
            self.error_occurred.emit(f"获取作业列表失败: {str(e)}")
            return []
    
    def get_job_details(self, job_id):
        """
        获取作业详情
        
        Args:
            job_id: 作业ID
            
        Returns:
            dict: 作业详情
        """
        try:
            client = self._get_ssh_client()
            if not client:
                return {}
                
            try:
                # 使用scontrol命令获取作业详情
                cmd = f"scontrol show job {job_id}"
                stdin, stdout, stderr = client.exec_command(cmd)
                
                # 读取输出
                output = stdout.read().decode()
                
                # 解析输出
                details = {}
                for line in output.split('\n'):
                    line = line.strip()
                    if not line:
                        continue
                        
                    for item in line.split():
                        if '=' in item:
                            key, value = item.split('=', 1)
                            details[key] = value
                
                return details
            finally:
                client.close()
        except Exception as e:
            logging.error(f"获取作业详情失败: {e}")
            self.error_occurred.emit(f"获取作业详情失败: {str(e)}")
            return {}
    
    def submit_job(self, script_content, remote_filename=None):
        """
        提交作业
        
        Args:
            script_content: 脚本内容
            remote_filename: 远程文件名，如果为None则自动生成
            
        Returns:
            str: 作业ID，如果失败则返回None
        """
        try:
            client = self._get_ssh_client()
            if not client:
                return None
                
            try:
                # 如果没有提供远程文件名，则自动生成
                if not remote_filename:
                    timestamp = int(time.time())
                    remote_filename = f"job_script_{timestamp}.sh"
                
                # 创建SFTP会话
                sftp = client.open_sftp()
                
                # 上传脚本
                remote_path = f"/tmp/{remote_filename}"
                with sftp.file(remote_path, 'w') as f:
                    f.write(script_content)
                
                # 设置可执行权限
                sftp.chmod(remote_path, 0o755)
                
                # 提交作业
                cmd = f"sbatch {remote_path}"
                stdin, stdout, stderr = client.exec_command(cmd)
                
                # 读取输出
                output = stdout.read().decode().strip()
                
                # 解析作业ID
                match = re.search(r'Submitted batch job (\d+)', output)
                if match:
                    job_id = match.group(1)
                    self.job_submitted.emit(job_id)
                    return job_id
                else:
                    error = stderr.read().decode().strip()
                    logging.error(f"提交作业失败: {error}")
                    self.error_occurred.emit(f"提交作业失败: {error}")
                    return None
            finally:
                client.close()
        except Exception as e:
            logging.error(f"提交作业失败: {e}")
            self.error_occurred.emit(f"提交作业失败: {str(e)}")
            return None
    
    def cancel_job(self, job_id):
        """
        取消作业
        
        Args:
            job_id: 作业ID
            
        Returns:
            bool: 是否成功
        """
        try:
            client = self._get_ssh_client()
            if not client:
                return False
                
            try:
                # 使用scancel命令取消作业
                cmd = f"scancel {job_id}"
                stdin, stdout, stderr = client.exec_command(cmd)
                
                # 检查错误
                error = stderr.read().decode().strip()
                if error:
                    logging.error(f"取消作业失败: {error}")
                    self.error_occurred.emit(f"取消作业失败: {error}")
                    return False
                
                self.job_canceled.emit(job_id)
                return True
            finally:
                client.close()
        except Exception as e:
            logging.error(f"取消作业失败: {e}")
            self.error_occurred.emit(f"取消作业失败: {str(e)}")
            return False
    
    def get_cluster_info(self):
        """
        获取集群节点信息
        
        Returns:
            dict: 集群信息
        """
        try:
            client = self._get_ssh_client()
            if not client:
                return {}
                
            try:
                # 使用sinfo命令获取集群节点信息
                cmd = "sinfo -o '%N|%C|%t|%O|%T|%P' -h"
                stdin, stdout, stderr = client.exec_command(cmd)
                
                # 解析输出
                nodes = []
                for line in stdout:
                    line = line.strip()
                    if not line:
                        continue
                        
                    parts = line.split('|')
                    if len(parts) == 6:
                        node = {
                            'name': parts[0],
                            'cpus': parts[1],
                            'state': parts[2],
                            'features': parts[3],
                            'reason': parts[4],
                            'partition': parts[5]
                        }
                        nodes.append(node)
                
                return nodes
            finally:
                client.close()
        except Exception as e:
            logging.error(f"获取集群信息失败: {e}")
            self.error_occurred.emit(f"获取集群信息失败: {str(e)}")
            return []
    
    def get_partition_info(self):
        """
        获取分区信息
        
        Returns:
            list: 分区信息列表
        """
        try:
            client = self._get_ssh_client()
            if not client:
                return []
                
            try:
                # 使用sinfo命令获取分区信息
                cmd = "sinfo -s -o '%P|%a|%l|%D|%T|%N' -h"
                stdin, stdout, stderr = client.exec_command(cmd)
                
                # 解析输出
                partitions = []
                for line in stdout:
                    line = line.strip()
                    if not line:
                        continue
                        
                    parts = line.split('|')
                    if len(parts) == 6:
                        partition = {
                            'name': parts[0],
                            'avail': parts[1],
                            'time_limit': parts[2],
                            'nodes': parts[3],
                            'state': parts[4],
                            'node_names': parts[5]
                        }
                        partitions.append(partition)
                
                return partitions
            finally:
                client.close()
        except Exception as e:
            logging.error(f"获取分区信息失败: {e}")
            self.error_occurred.emit(f"获取分区信息失败: {str(e)}")
            return [] 