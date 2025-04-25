#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import re
import logging
import paramiko
import threading
import time
import os
from PyQt5.QtCore import QObject, pyqtSignal, QThread, Qt

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class VSCodeManager(QObject):
    """
    VSCode服务器管理器，负责提交和管理VSCode服务器作业
    """
    
    # 信号定义
    vscode_job_submitted = pyqtSignal(dict)  # 作业提交成功信号
    vscode_job_status_updated = pyqtSignal(dict)  # 作业状态更新信号
    vscode_config_ready = pyqtSignal(dict)  # 配置信息准备就绪信号
    error_occurred = pyqtSignal(str)  # 错误信号
    ssh_config_added = pyqtSignal(str, str)  # SSH配置添加信号（job_id, hostname）
    ssh_config_removed = pyqtSignal(str)  # SSH配置移除信号（job_id）
    
    def __init__(self, hostname, username, key_path=None, password=None):
        """
        初始化VSCode管理器
        
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
        
        # 当前运行的VSCode作业信息
        self.current_job = None
        
        # 跟踪已写入配置的作业ID
        self.config_written_jobs = set()
        
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
    
    def submit_vscode_job(self, cpus=2, memory="4G", gpu_type=None, account=None, time_limit="8:00:00", use_free=False):
        """
        提交VSCode作业到HPC
        
        Args:
            cpus: CPU核心数
            memory: 内存大小
            gpu_type: GPU类型，如v100、a30等，None表示不使用GPU
            account: 计费账户
            time_limit: 时间限制，格式为HH:MM:SS
            use_free: 是否使用免费资源
        
        Returns:
            bool: 是否成功提交
        """
        if not account:
            raise ValueError("必须指定计费账户")
        
        # 连接到SSH
        if not self.connect_ssh():
            raise Exception("无法连接到SSH服务器")
        
        try:
            # 构建sbatch命令
            cmd = "sbatch"
            
            # 添加资源请求参数
            cmd += f" --cpus-per-task={cpus}"
            cmd += f" --mem={memory}"
            cmd += f" --time={time_limit}"
            cmd += f" --account={account}"
            
            # 添加GPU资源请求（如果需要）
            if gpu_type:
                cmd += f" --gres=gpu:1"
                cmd += f" --constraint={gpu_type}"
            
            # 添加免费分区选项（如果需要）
            if use_free:
                cmd += f" -p free"
            
            # 添加VSCode脚本路径
            cmd += " /opt/rcic/scripts/vscode-sshd.sh"
            
            # 提交作业
            logger.info(f"提交作业命令: {cmd}")
            output = self.execute_ssh_command(cmd)
            logger.info(f"提交作业输出: {output}")
            
            # 解析作业ID
            job_id = None
            if output:
                match = re.search(r'Submitted batch job (\d+)', output)
                if match:
                    job_id = match.group(1)
            
            if not job_id:
                raise Exception(f"提交作业失败，无法获取作业ID，输出: {output}")
            
            # 记录作业信息
            job_info = {
                'job_id': job_id,
                'status': 'PENDING',
                'cpus': cpus,
                'memory': memory,
                'gpu_type': gpu_type,
                'account': account,
                'time_limit': time_limit,
                'submit_time': time.time(),
                'use_free': use_free,  # 记录是否使用免费资源
                'command': cmd,  # 记录提交命令
                'script_path': "/opt/rcic/scripts/vscode-sshd.sh"  # 使用系统脚本路径
            }
            
            # 发出信号
            self.vscode_job_submitted.emit(job_info)
            
            # 启动轮询线程
            self._start_poll_job_status(job_id)
            
            return True
        
        except Exception as e:
            logger.error(f"提交VSCode作业失败: {e}")
            raise
    
    def wait_for_job_and_get_config(self, job_id):
        """
        等待作业运行并获取配置信息
        
        Args:
            job_id: 作业ID
        """
        # 启动一个线程来监视作业状态
        threading.Thread(target=self._monitor_job_status, args=(job_id,), daemon=True).start()
    
    def _monitor_job_status(self, job_id):
        """
        监视作业状态并在作业运行时获取配置信息
        
        Args:
            job_id: 作业ID
        """
        try:
            # 最多等待60分钟
            max_wait_time = 60 * 60
            start_time = time.time()
            
            while time.time() - start_time < max_wait_time:
                # 检查作业状态
                cmd = f"squeue -j {job_id} -h -o '%T %N'"
                try:
                    output = self.execute_ssh_command(cmd)
                    output = output.strip()
                    
                    if not output:
                        # 作业可能已结束
                        logger.warning(f"作业 {job_id} 可能已结束，无法获取状态")
                        self.current_job['status'] = 'COMPLETED'
                        self.vscode_job_status_updated.emit(self.current_job)
                        return
                    
                    # 解析状态和节点
                    parts = output.split()
                    if len(parts) >= 1:
                        status = parts[0]
                        node = parts[1] if len(parts) > 1 else "未分配"
                        
                        # 更新作业信息
                        self.current_job['status'] = status
                        self.current_job['node'] = node
                        
                        # 发送状态更新信号
                        self.vscode_job_status_updated.emit(self.current_job)
                        
                        # 如果作业在运行中，获取配置信息
                        if status == 'RUNNING':
                            # 获取作业输出文件以解析配置信息
                            config_info = self._parse_vscode_config(job_id)
                            if config_info:
                                self.current_job['config'] = config_info
                                self.current_job['hostname'] = config_info.get('hostname')
                                self.current_job['port'] = config_info.get('port')
                                # 发送配置就绪信号
                                self.vscode_config_ready.emit(self.current_job)
                                return
                except Exception as e:
                    logger.error(f"获取作业状态时出错: {str(e)}")
                
                # 间隔10秒检查一次
                time.sleep(10)
            
            # 超时
            logger.warning(f"等待作业 {job_id} 运行超时")
            self.error_occurred.emit(f"等待作业 {job_id} 运行超时，请检查作业状态")
        except Exception as e:
            logger.error(f"监视作业状态时出错: {str(e)}")
            self.error_occurred.emit(f"监视作业状态时出错: {str(e)}")
    
    def _parse_vscode_config(self, job_id):
        """
        解析VSCode配置信息
        
        Args:
            job_id: 作业ID
            
        Returns:
            dict: 配置信息字典
        """
        try:
            # 获取作业输出文件
            cmd = f"cat vscode-sshd-{job_id}.out 2>/dev/null || echo '未找到配置文件'"
            output = self.execute_ssh_command(cmd)
            
            logger.info(f"VSCode配置文件内容:\n{output}")
            
            # 如果找不到配置文件
            if "未找到配置文件" in output:
                # 查询作业信息
                job_info = self.get_job_status(job_id)
                node = job_info.get('node') if job_info else None
                
                if node:
                    # 如果有节点，构造基本配置
                    config = {
                        'hostname': node,
                        'port': '22',  # 使用默认SSH端口
                        'user': self.username,
                        'ssh_config': f"""Host {node}
  HostName {node}
  ProxyJump {self.username}@{self.hostname}
  User {self.username}
  UserKnownHostsFile /dev/null
  StrictHostKeyChecking no"""
                    }
                    logger.info(f"使用节点信息构造配置: {config}")
                    return config
                else:
                    logger.warning(f"无法获取作业 {job_id} 的节点信息")
                    return None
            
            # 解析主机名和端口
            hostname_match = re.search(r'HostName\s+(\S+)', output)
            port_match = re.search(r'Port\s+(\d+)', output)
            
            hostname = None
            port = None
            
            if hostname_match:
                hostname = hostname_match.group(1)
            else:
                # 尝试从node行找到主机名
                node_match = re.search(r'节点:\s+(\S+)', output)
                if node_match:
                    hostname = node_match.group(1)
            
            if port_match:
                port = port_match.group(1)
            else:
                # 默认端口
                port = "22"
            
            if not hostname:
                logger.warning(f"无法从输出中解析主机名: {output}")
                return None
            
            # 构建配置信息
            config = {
                'hostname': hostname,
                'port': port,
                'user': self.username,
                'ssh_config': f"""Host {hostname}
  HostName {hostname}
  Port {port}
  ProxyJump {self.username}@{self.hostname}
  User {self.username}
  UserKnownHostsFile /dev/null
  StrictHostKeyChecking no"""
            }
            
            logger.info(f"解析的VSCode配置信息: {config}")
            return config
        except Exception as e:
            logger.error(f"解析VSCode配置信息时出错: {str(e)}")
            return None
    
    def get_job_status(self, job_id):
        """
        获取作业状态
        
        Args:
            job_id: 作业ID
        
        Returns:
            dict: 作业状态信息
        """
        if not job_id:
            return None
        
        try:
            # 连接SSH
            if not self.connect_ssh():
                raise Exception("无法连接到SSH服务器")
            
            # 执行squeue命令查询作业
            cmd = f"squeue -j {job_id} -o '%j|%i|%T|%N|%C|%m|%l' -h"
            output = self.execute_ssh_command(cmd)
            
            # 如果没有输出，说明作业可能已结束
            if not output or not output.strip():
                # 查询sacct获取已结束作业的信息
                sacct_cmd = f"sacct -j {job_id} -o JobName,JobID,State,NodeList,NCPUS,ReqMem,Timelimit -n -P"
                sacct_output = self.execute_ssh_command(sacct_cmd)
                
                # 解析sacct输出
                if sacct_output and sacct_output.strip():
                    lines = sacct_output.strip().split('\n')
                    for line in lines:
                        if '.batch' not in line and '.extern' not in line:  # 排除批处理和外部步骤
                            parts = line.split('|')
                            if len(parts) >= 3:
                                state = parts[2]
                                node = parts[3] if len(parts) > 3 else ""
                                
                                # 返回作业状态
                                return {
                                    'job_id': job_id,
                                    'status': state,
                                    'node': node
                                }
                
                # 如果sacct也没有信息，则假定作业已取消
                return {
                    'job_id': job_id,
                    'status': 'CANCELLED',
                    'node': None
                }
            
            # 解析squeue输出
            # 格式：JobName|JobId|State|NodeList|NumCPUs|Memory|TimeLimit
            parts = output.strip().split('|')
            if len(parts) >= 3:
                job_name = parts[0]
                status = parts[2]
                node = parts[3] if len(parts) > 3 and parts[3] != '(None)' else None
                cpus = int(parts[4]) if len(parts) > 4 and parts[4].isdigit() else 0
                
                # 获取并解析内存
                memory = parts[5] if len(parts) > 5 else "0"
                
                # 获取时间限制
                time_limit = parts[6] if len(parts) > 6 else ""
                
                # 返回作业状态
                return {
                    'job_id': job_id,
                    'status': status,
                    'node': node,
                    'cpus': cpus,
                    'memory': memory,
                    'time_limit': time_limit
                }
            
            return None
        except Exception as e:
            logger.error(f"获取作业状态失败: {e}")
            return None
    
    def cancel_job(self, job_id=None):
        """
        取消作业
        
        Args:
            job_id: 作业ID，如果为None则使用当前作业ID
            
        Returns:
            bool: 取消是否成功
        """
        if not job_id and self.current_job:
            job_id = self.current_job['job_id']
        
        if not job_id:
            logger.warning("未指定作业ID，无法取消作业")
            return False
        
        try:
            cmd = f"scancel {job_id}"
            self.execute_ssh_command(cmd)
            
            # 始终尝试从本地SSH配置中移除对应条目，不依赖内部跟踪状态
            self._remove_ssh_config_from_local(job_id)
            
            # 如果在跟踪集合中，也移除
            if job_id in self.config_written_jobs:
                self.config_written_jobs.remove(job_id)
            
            # 更新当前作业状态
            if self.current_job and self.current_job['job_id'] == job_id:
                self.current_job['status'] = 'CANCELLED'
                self.vscode_job_status_updated.emit(self.current_job)
            
            logger.info(f"已取消作业 {job_id}")
            return True
        except Exception as e:
            error_msg = f"取消作业 {job_id} 失败: {str(e)}"
            logger.error(error_msg)
            self.error_occurred.emit(error_msg)
            return False
    
    def get_running_vscode_jobs(self):
        """
        获取用户正在运行的VSCode作业
        
        Returns:
            list: 作业信息列表
        """
        try:
            cmd = f"squeue -u {self.username} -h -o '%j %i %T %N' | grep vscode-sshd"
            output = self.execute_ssh_command(cmd)
            
            jobs = []
            for line in output.strip().split('\n'):
                if not line.strip():
                    continue
                
                parts = line.split()
                if len(parts) >= 4:
                    job_name = parts[0]
                    job_id = parts[1]
                    status = parts[2]
                    node = parts[3]
                    
                    jobs.append({
                        'job_id': job_id,
                        'job_name': job_name,
                        'status': status,
                        'node': node
                    })
            
            return jobs
        except Exception as e:
            logger.error(f"获取VSCode作业时出错: {str(e)}")
            return []
    
    def __del__(self):
        """析构函数，确保关闭SSH连接"""
        if hasattr(self, '_ssh_client') and self._ssh_client:
            try:
                self._ssh_client.close()
            except Exception as e:
                logging.error(f"关闭SSH连接失败: {str(e)}")
    
    def _start_poll_job_status(self, job_id):
        """
        启动一个线程来轮询作业状态
        
        Args:
            job_id: 作业ID
        """
        def poll_job():
            """轮询作业状态的线程函数"""
            try:
                # 初始化轮询次数
                poll_count = 0
                
                # 持续轮询，直到作业完成或超时
                while True:
                    # 获取作业状态
                    job_status = self.get_job_status(job_id)
                    
                    if not job_status or job_status.get('status') in ['COMPLETED', 'FAILED', 'CANCELLED', 'TIMEOUT']:
                        # 作业已结束
                        logger.info(f"作业 {job_id} 已结束，状态: {job_status.get('status') if job_status else 'UNKNOWN'}")
                        break
                    elif job_status.get('status') == 'RUNNING':
                        # 作业运行中，尝试获取配置
                        if poll_count % 2 == 0:  # 每隔几次检查配置
                            config = self._parse_vscode_config(job_id)
                            if config:
                                # 更新作业信息
                                job_status['config'] = config
                                
                                # 将配置信息写入本地SSH配置（如果尚未写入）
                                hostname = config.get('hostname')
                                if hostname and job_id not in self.config_written_jobs:
                                    # 使用信号将操作转移到主线程
                                    self._add_ssh_config_to_local(job_id, config)
                                    # 发出信号通知配置已添加
                                    self.ssh_config_added.emit(job_id, hostname)
                                    # 标记已写入配置
                                    self.config_written_jobs.add(job_id)
                                    logger.info(f"作业 {job_id} 的SSH配置已写入（首次）")
                                
                                # 发出配置就绪信号
                                self.vscode_config_ready.emit(job_status)
                    
                    # 发出状态更新信号
                    self.vscode_job_status_updated.emit(job_status)
                    
                    # 增加轮询次数
                    poll_count += 1
                    
                    # 延时
                    time.sleep(5)  # 5秒轮询一次
                    
                    # 如果轮询超过一定次数，则退出
                    if poll_count > 180:  # 15分钟后退出
                        logger.warning(f"轮询作业 {job_id} 状态超时")
                        break
            except Exception as e:
                logger.error(f"轮询作业状态失败: {e}")
        
        # 启动线程
        threading.Thread(target=poll_job, daemon=True).start()

    def _add_ssh_config_to_local(self, job_id, config):
        """
        将SSH配置添加到本地~/.ssh/config文件
        
        Args:
            job_id: 作业ID
            config: 配置信息
        """
        try:
            # 确保本地~/.ssh目录存在
            ssh_dir = os.path.expanduser("~/.ssh")
            if not os.path.exists(ssh_dir):
                os.makedirs(ssh_dir, mode=0o700)
            
            # 配置文件路径
            config_file = os.path.join(ssh_dir, "config")
            
            # 读取现有配置
            existing_config = ""
            if os.path.exists(config_file):
                with open(config_file, 'r') as f:
                    existing_config = f.read()
            
            # 要添加的配置（带有标记注释以便后续移除）
            hostname = config.get('hostname')
            
            # 找到对应的SSH密钥文件路径
            identity_file = self.key_path
            if not identity_file:
                # 如果没有指定密钥路径，尝试从用户信息中获取
                from modules.auth import get_all_existing_users
                users = get_all_existing_users()
                for user in users:
                    if user['username'] == self.username:
                        identity_file = user['key_path']
                        break
            
            # 如果仍然没有找到密钥路径，使用默认路径
            if not identity_file:
                identity_file = os.path.expanduser(f"~/.ssh/{self.username}_hpc_app_key")
            
            # 构造跳板主机名称（唯一标识符）
            jump_host = f"hpc_login_{job_id}"
            
            new_config = f"""
# === BEGIN HPC App VSCode配置 (JobID: {job_id}) ===

Host {jump_host}
    HostName {self.hostname}
    User {self.username}
    IdentityFile {identity_file}


Host {hostname}
    HostName {hostname}
    User {self.username}
    Port {config.get('port')}
    IdentityFile {identity_file}
    ProxyJump {jump_host}
    UserKnownHostsFile /dev/null
    StrictHostKeyChecking no
# === END HPC App VSCode配置 (JobID: {job_id}) ===
"""
            
            # 检查是否已存在相同主机的配置
            pattern = re.compile(r'# === BEGIN HPC App VSCode配置 \(JobID: .*?\) ===.*?# === END HPC App VSCode配置 \(JobID: .*?\) ===', re.DOTALL)
            
            # 如果已经存在由HPC App添加的配置，先移除它
            existing_config = pattern.sub('', existing_config)
            
            # 将新配置添加到文件末尾
            with open(config_file, 'w') as f:
                if existing_config.strip():
                    f.write(existing_config.rstrip() + "\n")
                f.write(new_config)
            
            # 设置正确的权限
            os.chmod(config_file, 0o600)
            
            logger.info(f"已将作业 {job_id} 的SSH配置添加到 {config_file}")
            
        except Exception as e:
            logger.error(f"添加SSH配置到本地文件失败: {e}")
            self.error_occurred.emit(f"添加SSH配置失败: {str(e)}")

    def _remove_ssh_config_from_local(self, job_id):
        """
        从本地~/.ssh/config文件中移除指定作业的SSH配置
        
        Args:
            job_id: 作业ID
        """
        try:
            # 配置文件路径
            config_file = os.path.expanduser("~/.ssh/config")
            
            # 检查配置文件是否存在
            if not os.path.exists(config_file):
                logger.warning(f"SSH配置文件不存在: {config_file}")
                return
            
            # 读取现有配置
            with open(config_file, 'r') as f:
                existing_config = f.read()
            
            # 使用正则表达式匹配并移除指定作业的配置
            pattern = re.compile(rf'# === BEGIN HPC App VSCode配置 \(JobID: {job_id}\) ===.*?# === END HPC App VSCode配置 \(JobID: {job_id}\) ===', re.DOTALL)
            
            # 检查是否存在匹配的配置
            match = pattern.search(existing_config)
            if match:
                # 替换匹配的部分为空字符串
                new_config = pattern.sub('', existing_config)
                
                # 写回文件
                with open(config_file, 'w') as f:
                    f.write(new_config)
                logger.info(f"已从 {config_file} 中移除作业 {job_id} 的SSH配置")
                
                # 发出信号通知配置已移除
                self.ssh_config_removed.emit(job_id)
            else:
                logger.info(f"未在 {config_file} 中找到作业 {job_id} 的SSH配置，无需移除")
        except Exception as e:
            logger.error(f"从本地文件移除SSH配置失败: {e}")
            self.error_occurred.emit(f"移除SSH配置失败: {str(e)}") 