#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, 
                           QGroupBox, QComboBox, QGridLayout, QSpinBox, QTextEdit,
                           QLineEdit, QMessageBox, QSplitter, QTabWidget)
from PyQt5.QtCore import Qt, pyqtSlot, QMetaObject, Q_ARG, pyqtSignal, QTimer, QObject
from PyQt5.QtGui import QFont, QIcon

import logging
import time
import threading
from modules.vscode_helper import VSCodeManager
from modules.auth import HPC_SERVER, get_all_existing_users
from modules.balance import BalanceManager
from modules.node_status import NodeStatusManager
import os

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger('VSCodeWidget')

class ThreadSafeHelper(QObject):
    """辅助类用于线程安全地更新UI"""
    update_status = pyqtSignal(str)
    update_job_info_signal = pyqtSignal(dict)
    show_config_signal = pyqtSignal(dict)
    show_error_signal = pyqtSignal(str)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent = parent

class VSCodeWidget(QWidget):
    """VSCode远程配置组件，提供VSCode服务器设置和连接功能"""
    
    def __init__(self, parent=None, username=None):
        super().__init__(parent)
        
        # 用户信息
        self.username = username
        self.vscode_manager = None
        self.balance_manager = None
        self.node_manager = None
        
        # 线程安全辅助对象
        self.thread_helper = ThreadSafeHelper(self)
        self.thread_helper.update_status.connect(self.update_status_safe)
        self.thread_helper.update_job_info_signal.connect(self.update_job_info)
        self.thread_helper.show_config_signal.connect(self.safe_show_config)
        self.thread_helper.show_error_signal.connect(self.show_error)
        
        # 账户信息
        self.accounts = []
        
        # GPU类型信息
        self.gpu_types = []
        
        # 当前作业信息
        self.current_job = None
        
        # 是否已完成初始化
        self.initialization_complete = False
        
        # 初始化UI
        self.init_ui()
        
        # 使用定时器延迟初始化其他管理器，避免启动时阻塞UI
        QTimer.singleShot(500, self.delayed_init_managers)
    
    def delayed_init_managers(self):
        """延迟初始化管理器，避免在UI显示前阻塞"""
        try:
            # 注册QTextCursor元数据类型，用于线程间传递
            try:
                from PyQt5.QtCore import qRegisterMetaType
                qRegisterMetaType('QTextCursor')
            except (ImportError, AttributeError):
                logger.warning("无法注册QTextCursor元数据类型，可能影响多线程操作")
            
            # 初始化管理器
            self.init_managers()
            
            # 设置初始化完成标志
            self.initialization_complete = True
        except Exception as e:
            logger.error(f"延迟初始化管理器失败: {e}")
            self.status_label.setText(f"错误: 初始化失败 - {str(e)}")
    
    def init_managers(self):
        """初始化VSCode管理器和余额管理器"""
        if not self.username:
            self.status_label.setText("错误: 未提供用户名")
            return
        
        # 获取SSH密钥路径
        users = get_all_existing_users()
        key_path = None
        
        for user in users:
            if user['username'] == self.username:
                key_path = user['key_path']
                break
        
        if not key_path:
            self.status_label.setText(f"错误: 未找到用户 {self.username} 的SSH密钥")
            return
        
        try:
            # 在主线程中创建管理器对象
            # 创建VSCode管理器
            self.vscode_manager = VSCodeManager(
                hostname=HPC_SERVER,
                username=self.username,
                key_path=key_path
            )
            
            # 连接信号
            self.vscode_manager.vscode_job_submitted.connect(self.update_job_info)
            self.vscode_manager.vscode_job_status_updated.connect(self.update_job_status)
            self.vscode_manager.vscode_config_ready.connect(self.show_config)
            self.vscode_manager.error_occurred.connect(self.show_error)
            
            # 连接SSH配置信号
            self.vscode_manager.ssh_config_added.connect(self.on_ssh_config_added)
            self.vscode_manager.ssh_config_removed.connect(self.on_ssh_config_removed)
            
            # 创建余额管理器以获取账户信息
            self.balance_manager = BalanceManager(
                hostname=HPC_SERVER,
                username=self.username,
                key_path=key_path
            )
            
            # 创建节点状态管理器以获取GPU类型信息
            self.node_manager = NodeStatusManager(
                hostname=HPC_SERVER,
                username=self.username,
                key_path=key_path
            )
            
            # 更新状态
            self.status_label.setText("管理器初始化完成，准备就绪")
            
            # 使用线程安全的方式初始化连接和数据
            # 在后台线程中获取账户信息
            threading.Thread(target=self._init_background_data, daemon=True).start()
        except Exception as e:
            self.status_label.setText(f"错误: 初始化管理器失败 - {str(e)}")
    
    def _init_background_data(self):
        """在后台线程中初始化数据"""
        try:
            # 使用延迟处理，让UI有时间完全初始化
            time.sleep(1)
            
            # 首先获取账户和GPU类型，这些不容易出问题
            try:
                self.fetch_accounts()
            except Exception as e:
                logger.error(f"获取账户信息失败: {e}")
                self.thread_helper.show_error_signal.emit(f"获取账户信息失败: {str(e)}")
            
            try:
                self.fetch_gpu_types()
            except Exception as e:
                logger.error(f"获取GPU类型失败: {e}")
                self.thread_helper.show_error_signal.emit(f"获取GPU类型失败: {str(e)}")
            
            # 延迟检查运行中的作业，因为这可能是崩溃的来源
            time.sleep(1.5)
            
            # 最后检查是否有正在运行的VSCode作业（这部分可能导致问题）
            try:
                # 使用线程安全的方式检查作业
                self.safe_check_running_jobs()
            except Exception as e:
                logger.error(f"检查运行中的VSCode作业失败: {e}")
                self.thread_helper.show_error_signal.emit(f"检查运行中的VSCode作业失败: {str(e)}")
        except Exception as e:
            logger.error(f"初始化后台数据失败: {e}")
            self.thread_helper.show_error_signal.emit(f"初始化后台数据失败: {str(e)}")
    
    def fetch_accounts(self):
        """获取用户可用的账户列表"""
        try:
            balance_data = self.balance_manager.get_user_balance()
            if balance_data and 'accounts' in balance_data:
                self.accounts = []
                
                # 添加个人账户和实验室账户
                for account in balance_data['accounts']:
                    self.accounts.append({
                        'name': account['name'],
                        'is_personal': account['is_personal'],
                        'available': account['available']
                    })
                
                # 更新账户下拉列表
                self.update_account_combobox()
        except Exception as e:
            logger.error(f"获取账户信息失败: {str(e)}")
            self.show_error(f"获取账户信息失败: {str(e)}")
    
    def update_account_combobox(self):
        """更新账户下拉列表"""
        self.account_combo.clear()
        
        # 添加空选项
        self.account_combo.addItem("请选择扣费账户", None)
        
        for account in self.accounts:
            account_text = f"{account['name']} (可用: {account['available']})"
            if account['is_personal']:
                account_text += " (个人)"
            self.account_combo.addItem(account_text, account['name'])
        
        # 默认不选择账户，确保用户必须主动选择
        self.account_combo.setCurrentIndex(0)
        self.submit_btn.setEnabled(False)
    
    def fetch_gpu_types(self):
        """获取可用的GPU类型"""
        try:
            # 先添加默认选项
            self.gpu_types = [{"name": "不使用GPU", "value": None}]
            
            # 获取GPU分区节点信息 - 使用特定命令查询GPU分区
            if self.node_manager.connect_ssh():
                # 使用sinfo命令获取GPU分区信息
                gpu_cmd = 'sinfo -NO "CPUsState:14,Memory:9,AllocMem:10,Gres:14,GresUsed:22,NodeList:20" -p gpu'
                try:
                    output = self.node_manager.execute_ssh_command(gpu_cmd)
                    logger.info(f"获取GPU分区信息成功")
                    
                    # 解析输出获取GPU类型
                    gpu_types_set = set()
                    lines = output.strip().split('\n')
                    
                    # 跳过标题行
                    if len(lines) > 1:
                        for line in lines[1:]:
                            parts = line.split()
                            if len(parts) >= 4:  # 确保至少有GRES列
                                # GRES列通常是第4列，格式如 gpu:V100:4
                                gres_info = parts[3]
                                # 解析格式 gpu:TYPE:COUNT
                                gres_parts = gres_info.split(':')
                                if len(gres_parts) >= 3 and gres_parts[0] == 'gpu':
                                    gpu_type = gres_parts[1]
                                    gpu_types_set.add(gpu_type)
                
                    # 添加找到的GPU类型
                    for gpu_type in sorted(gpu_types_set):
                        self.gpu_types.append({
                            "name": f"{gpu_type} GPU",
                            "value": gpu_type.lower()
                        })
                    
                    logger.info(f"找到以下GPU类型: {[gpu_type for gpu_type in gpu_types_set]}")
                except Exception as e:
                    logger.error(f"执行GPU查询命令失败: {e}")
                    # 回退到基本选项
                    self.gpu_types.extend([
                        {"name": "V100 GPU", "value": "v100"},
                        {"name": "A30 GPU", "value": "a30"},
                        {"name": "A100 GPU", "value": "a100"}
                    ])
            else:
                logger.error("无法连接到SSH服务器获取GPU信息")
                # 回退到基本选项
                self.gpu_types.extend([
                    {"name": "V100 GPU", "value": "v100"},
                    {"name": "A30 GPU", "value": "a30"},
                    {"name": "A100 GPU", "value": "a100"}
                ])
            
            # 在主线程中更新UI
            QMetaObject.invokeMethod(self, "update_gpu_combobox", Qt.QueuedConnection)
        except Exception as e:
            logger.error(f"获取GPU类型失败: {e}")
            self.show_error(f"获取GPU类型失败: {str(e)}")
            # 添加默认选项
            self.gpu_types = [
                {"name": "不使用GPU", "value": None},
                {"name": "V100 GPU", "value": "v100"},
                {"name": "A30 GPU", "value": "a30"},
                {"name": "A100 GPU", "value": "a100"}
            ]
            # 在主线程中更新UI
            QMetaObject.invokeMethod(self, "update_gpu_combobox", Qt.QueuedConnection)
    
    @pyqtSlot()
    def update_gpu_combobox(self):
        """更新GPU类型下拉列表"""
        self.gpu_combo.clear()
        
        for gpu_type in self.gpu_types:
            self.gpu_combo.addItem(gpu_type["name"], gpu_type["value"])
    
    def safe_check_running_jobs(self):
        """线程安全的检查运行中的作业"""
        try:
            # 获取作业列表可能需要时间，且可能抛出异常
            jobs = self.vscode_manager.get_running_vscode_jobs()
            
            if not jobs:
                logger.info("没有发现正在运行的VSCode作业")
                return
            
            # 找到第一个RUNNING状态的作业
            running_job = next((job for job in jobs if job['status'] == 'RUNNING'), None)
            if not running_job:
                logger.info("没有发现处于RUNNING状态的VSCode作业")
                return
            
            # 获取作业详细信息
            job_id = running_job['job_id']
            logger.info(f"发现正在运行的VSCode作业: {job_id}")
            
            # 使用信号更新状态（线程安全）
            self.thread_helper.update_status.emit(f"发现正在运行的VSCode作业: {job_id}")
            
            # 创建作业信息字典
            job_info = {
                'job_id': job_id,
                'status': 'RUNNING',
                'node': running_job.get('node', '未知'),
                'hostname': running_job.get('node', '未知')
            }
            
            # 设置当前作业信息
            self.current_job = job_info
            
            # 使用信号更新作业信息（线程安全）
            self.thread_helper.update_job_info_signal.emit(job_info)
            
            # 解析配置信息前添加一个短暂的延迟
            time.sleep(0.5)
            
            # 尝试获取配置信息
            try:
                config_info = self.vscode_manager._parse_vscode_config(job_id)
                if config_info:
                    # 更新作业信息
                    job_info['config'] = config_info
                    job_info['hostname'] = config_info.get('hostname')
                    job_info['port'] = config_info.get('port')
                    
                    # 更新self.current_job也为完整信息
                    self.current_job = job_info.copy()
                    
                    # 使用信号显示配置（线程安全）
                    self.thread_helper.show_config_signal.emit(job_info)
            except Exception as e:
                logger.error(f"解析现有作业配置失败: {e}")
                # 即使无法解析配置，也确保UI反映出作业正在运行
                self.thread_helper.update_status.emit(f"检测到正在运行的VSCode作业: {job_id}（无法获取完整配置）")
        except Exception as e:
            logger.error(f"安全检查运行中的作业失败: {e}")
            # 即使检查失败，也不应让程序崩溃
    
    @pyqtSlot(dict)
    def safe_show_config(self, config_info):
        """线程安全的配置信息显示方法，在主线程中调用"""
        try:
            if not config_info or 'config' not in config_info:
                return
            
            config = config_info['config']
            job_id = config_info.get('job_id', 'N/A')
            
            # 构建配置信息文本 - 简化和直接化连接说明
            config_text = "## VSCode连接已就绪 ##\n\n"
            
            # 添加直接的VSCode连接说明
            config_text += "1. SSH配置已自动写入 ~/.ssh/config\n\n"
            
            # 添加VSCode连接说明
            config_text += "2. 在VSCode中连接到远程主机:\n\n"
            config_text += f"   - 打开VSCode\n"
            config_text += f"   - 点击左下角的远程连接图标 (><) 或按 F1 输入 'Remote-SSH: Connect to Host...'\n"
            config_text += f"   - 从列表中选择 \"{config['hostname']}\"\n\n"
            
            # 连接信息
            config_text += f"主机: {config['hostname']}\n"
            config_text += f"用户: {config['user']}\n"
            config_text += f"端口: {config['port']}\n\n"
            
            # 添加作业信息
            config_text += f"作业ID: {job_id}\n"
            
            # 添加关闭说明
            config_text += "\n3. 使用完成后关闭步骤:\n\n"
            config_text += "   - 在VSCode中关闭窗口\n"
            config_text += f"   - 在本应用中点击 \"取消作业\" 按钮\n"
            
            # 更新配置文本
            self.config_text.setText(config_text)
            
            # 切换到配置标签页
            tabs = self.findChild(QTabWidget)
            if tabs:
                tabs.setCurrentWidget(self.config_widget)
            
            # 更新状态标签
            self.status_label.setText(f"VSCode连接已就绪 - 作业 {job_id}")
        except Exception as e:
            logger.error(f"显示配置信息时出错: {e}")
    
    @pyqtSlot(dict)
    def show_config(self, config_info):
        """显示VSCode配置信息 - 确保在主线程中调用"""
        try:
            # 直接调用safe_show_config而不是使用invokeMethod
            self.safe_show_config(config_info)
        except Exception as e:
            logger.error(f"显示配置信息时出错: {e}")
    
    def init_ui(self):
        """初始化UI组件"""
        main_layout = QVBoxLayout(self)
        
        # 添加标题
        title_label = QLabel("VSCode远程配置")
        title_label.setFont(QFont('Arial', 16, QFont.Bold))
        main_layout.addWidget(title_label)
        
        # 创建分割器，将页面分为上下两部分
        splitter = QSplitter(Qt.Vertical)
        
        # 上部分：配置面板
        config_widget = QWidget()
        config_layout = QVBoxLayout(config_widget)
        
        # 创建资源配置组
        resources_group = QGroupBox("资源配置")
        resources_layout = QGridLayout(resources_group)
        
        # CPU数量
        cpu_label = QLabel("CPU数量:")
        self.cpu_spinbox = QSpinBox()
        self.cpu_spinbox.setMinimum(1)
        self.cpu_spinbox.setMaximum(128)
        self.cpu_spinbox.setValue(2)  # 默认值更改为2
        resources_layout.addWidget(cpu_label, 0, 0)
        resources_layout.addWidget(self.cpu_spinbox, 0, 1)
        
        # 内存大小
        memory_label = QLabel("内存大小:")
        self.memory_combo = QComboBox()
        for mem in ["4G", "8G", "16G", "32G", "64G", "128G"]:
            self.memory_combo.addItem(mem)
        self.memory_combo.setCurrentText("4G")  # 默认值更改为4G
        resources_layout.addWidget(memory_label, 1, 0)
        resources_layout.addWidget(self.memory_combo, 1, 1)
        
        # GPU类型
        gpu_label = QLabel("GPU类型:")
        self.gpu_combo = QComboBox()
        self.gpu_combo.addItem("加载中...", None)
        resources_layout.addWidget(gpu_label, 2, 0)
        resources_layout.addWidget(self.gpu_combo, 2, 1)
        
        # 添加资源配置组到配置布局
        config_layout.addWidget(resources_group)
        
        # 创建作业配置组
        job_group = QGroupBox("作业配置")
        job_layout = QGridLayout(job_group)
        
        # 扣费账户
        account_label = QLabel("扣费账户:")
        self.account_combo = QComboBox()
        self.account_combo.addItem("加载中...", "")
        self.account_combo.currentIndexChanged.connect(self.on_account_changed)
        job_layout.addWidget(account_label, 0, 0)
        job_layout.addWidget(self.account_combo, 0, 1)
        
        # 作业时限
        time_label = QLabel("运行时间:")
        self.time_combo = QComboBox()
        for time_limit in ["1:00:00", "2:00:00", "4:00:00", "8:00:00", "12:00:00", "24:00:00", "48:00:00"]:
            self.time_combo.addItem(time_limit)
        self.time_combo.setCurrentText("8:00:00")  # 默认值更改为8小时
        job_layout.addWidget(time_label, 1, 0)
        job_layout.addWidget(self.time_combo, 1, 1)
        
        # 免费选项
        free_option_label = QLabel("使用免费资源:")
        self.free_option_check = QComboBox()
        self.free_option_check.addItem("否", False)
        self.free_option_check.addItem("是 (可能不稳定)", True)
        free_option_hint = QLabel("注意: 使用免费资源仍需选择扣费账户")
        free_option_hint.setStyleSheet("color: #666; font-size: 10px;")
        job_layout.addWidget(free_option_label, 2, 0)
        job_layout.addWidget(self.free_option_check, 2, 1)
        job_layout.addWidget(free_option_hint, 3, 0, 1, 2)
        
        # 添加作业配置组到配置布局
        config_layout.addWidget(job_group)
        
        # 创建控制按钮
        button_layout = QHBoxLayout()
        
        # 提交按钮
        self.submit_btn = QPushButton("提交VSCode作业")
        self.submit_btn.clicked.connect(self.submit_job)
        self.submit_btn.setEnabled(False)  # 默认禁用，直到选择账户
        button_layout.addWidget(self.submit_btn)
        
        # 关闭按钮
        self.cancel_btn = QPushButton("取消作业")
        self.cancel_btn.clicked.connect(self.cancel_job)
        self.cancel_btn.setEnabled(False)  # 初始时禁用
        button_layout.addWidget(self.cancel_btn)
        
        # 添加按钮布局到配置布局
        config_layout.addLayout(button_layout)
        
        # 添加配置部件到分割器
        splitter.addWidget(config_widget)
        
        # 下部分：结果面板
        result_widget = QTabWidget()
        
        # 作业信息标签页
        self.job_info_widget = QWidget()
        job_info_layout = QVBoxLayout(self.job_info_widget)
        
        # 作业状态信息
        self.job_info_text = QTextEdit()
        self.job_info_text.setReadOnly(True)
        self.job_info_text.setPlaceholderText("提交作业后在此显示作业状态信息")
        job_info_layout.addWidget(self.job_info_text)
        
        # 配置标签页
        self.config_widget = QWidget()
        config_info_layout = QVBoxLayout(self.config_widget)
        
        # 配置信息
        self.config_text = QTextEdit()
        self.config_text.setReadOnly(True)
        self.config_text.setPlaceholderText("作业运行后在此显示VSCode远程连接配置")
        config_info_layout.addWidget(self.config_text)
        
        # 添加标签页
        result_widget.addTab(self.job_info_widget, "作业信息")
        result_widget.addTab(self.config_widget, "连接配置")
        
        # 添加结果部件到分割器
        splitter.addWidget(result_widget)
        
        # 设置分割器比例
        splitter.setSizes([300, 500])
        
        # 添加分割器到主布局
        main_layout.addWidget(splitter)
        
        # 底部状态栏
        self.status_label = QLabel("初始化中...")
        main_layout.addWidget(self.status_label)
    
    def on_account_changed(self, index):
        """当账户选择改变时触发"""
        # 检查是否选择了有效账户
        if index > 0 and self.account_combo.currentData():
            self.submit_btn.setEnabled(True)
        else:
            self.submit_btn.setEnabled(False)
    
    @pyqtSlot()
    def submit_job(self):
        """提交VSCode作业"""
        if not self.vscode_manager:
            self.show_error("VSCode管理器未初始化，无法提交作业")
            return
        
        # 首先检查是否有正在运行的VSCode作业
        try:
            running_jobs = self.vscode_manager.get_running_vscode_jobs()
            if running_jobs:
                # 找到RUNNING状态的作业
                running_job = next((job for job in running_jobs if job['status'] == 'RUNNING'), None)
                if running_job:
                    job_id = running_job['job_id']
                    # 询问用户是否取消旧作业
                    confirm = QMessageBox.question(
                        self,
                        "发现运行中的作业",
                        f"发现正在运行的VSCode作业 (ID: {job_id})，是否取消该作业并创建新作业？",
                        QMessageBox.Yes | QMessageBox.No,
                        QMessageBox.No
                    )
                    
                    if confirm == QMessageBox.Yes:
                        # 用户选择取消旧作业
                        self.status_label.setText(f"正在取消旧作业 {job_id}...")
                        success = self.vscode_manager.cancel_job(job_id)
                        if success:
                            # 确保配置信息被清理
                            self.clean_old_ssh_config(job_id)
                            self.status_label.setText(f"旧作业已取消，准备创建新作业")
                        else:
                            self.show_error(f"无法取消旧作业 {job_id}，请手动取消后再试")
                            return
                    else:
                        # 用户选择不取消旧作业
                        self.status_label.setText("保留旧作业，取消创建新作业")
                        return
        except Exception as e:
            logger.warning(f"检查运行中的作业时出错: {e}")
            # 即使检查失败，也继续创建新作业
        
        # 获取资源配置
        cpus = self.cpu_spinbox.value()
        memory = self.memory_combo.currentText()
        gpu_type = self.gpu_combo.currentData()
        account = self.account_combo.currentData()
        time_limit = self.time_combo.currentText()
        use_free = self.free_option_check.currentData()
        
        # 检查是否选择了账户
        if not account:
            self.show_error("请选择扣费账户")
            return
        
        # 更新状态
        self.status_label.setText("正在提交VSCode作业...")
        self.submit_btn.setEnabled(False)
        
        # 提交作业
        try:
            self.vscode_manager.submit_vscode_job(
                cpus=cpus,
                memory=memory,
                gpu_type=gpu_type,
                account=account,
                time_limit=time_limit,
                use_free=use_free  # 传递是否使用免费资源的选项
            )
        except Exception as e:
            self.show_error(f"提交作业失败: {str(e)}")
            self.submit_btn.setEnabled(True)
    
    def clean_old_ssh_config(self, job_id):
        """清理指定作业的SSH配置"""
        try:
            # 检查SSH配置文件
            ssh_config_file = os.path.expanduser("~/.ssh/config")
            if not os.path.exists(ssh_config_file):
                logger.info(f"SSH配置文件不存在: {ssh_config_file}")
                return
            
            # 读取当前配置
            with open(ssh_config_file, 'r') as f:
                content = f.read()
            
            # 查找与指定作业相关的配置块
            import re
            pattern = re.compile(rf'# === BEGIN HPC App VSCode配置 \(JobID: {job_id}\) ===.*?# === END HPC App VSCode配置 \(JobID: {job_id}\) ===', re.DOTALL)
            
            # 检查是否存在相关配置
            match = pattern.search(content)
            if match:
                # 移除相关配置
                new_content = pattern.sub('', content)
                
                # 写回文件
                with open(ssh_config_file, 'w') as f:
                    f.write(new_content)
                
                logger.info(f"已清理作业 {job_id} 的SSH配置")
                # 通知配置已移除
                if hasattr(self.vscode_manager, 'ssh_config_removed'):
                    self.vscode_manager.ssh_config_removed.emit(job_id)
            else:
                logger.info(f"未找到作业 {job_id} 的SSH配置，无需清理")
        except Exception as e:
            logger.error(f"清理SSH配置时出错: {e}")
    
    @pyqtSlot()
    def cancel_job(self):
        """取消当前VSCode作业"""
        if not self.vscode_manager or not self.current_job:
            self.show_error("没有正在运行的作业，无法取消")
            return
        
        job_id = self.current_job.get('job_id')
        if not job_id:
            self.show_error("作业ID不存在，无法取消")
            return
        
        # 更新状态
        self.status_label.setText(f"正在取消作业 {job_id}...")
        
        # 取消作业
        try:
            success = self.vscode_manager.cancel_job(job_id)
            if success:
                # 清理SSH配置
                self.clean_old_ssh_config(job_id)
                
                self.status_label.setText(f"作业 {job_id} 已取消")
                # 更新UI
                self.update_job_status({
                    'job_id': job_id,
                    'status': 'CANCELLED'
                })
                # 清除当前作业信息
                self.current_job = None
                # 启用提交按钮，禁用取消按钮
                self.submit_btn.setEnabled(True)
                self.cancel_btn.setEnabled(False)
                # 清除配置信息
                self.config_text.clear()
                self.config_text.setPlaceholderText("作业运行后在此显示VSCode远程连接配置")
            else:
                self.show_error(f"取消作业 {job_id} 失败")
        except Exception as e:
            self.show_error(f"取消作业失败: {str(e)}")
    
    @pyqtSlot(dict)
    def update_job_info(self, job_info):
        """更新作业信息显示"""
        if not job_info:
            return
        
        # 更新当前作业信息
        self.current_job = job_info
        
        # 更新UI状态
        self.cancel_btn.setEnabled(True)
        self.submit_btn.setEnabled(False)
        
        # 构建作业信息文本
        info_text = f"作业ID: {job_info.get('job_id', 'N/A')}\n"
        info_text += f"状态: {job_info.get('status', 'N/A')}\n"
        
        if 'node' in job_info and job_info['node']:
            info_text += f"节点: {job_info['node']}\n"
        
        info_text += "\n资源配置:\n"
        info_text += f"CPU数量: {job_info.get('cpus', 'N/A')}\n"
        info_text += f"内存大小: {job_info.get('memory', 'N/A')}\n"
        
        if job_info.get('gpu_type'):
            info_text += f"GPU类型: {job_info['gpu_type']}\n"
        else:
            info_text += "GPU类型: 不使用GPU\n"
        
        info_text += f"扣费账户: {job_info.get('account', 'N/A')}\n"
        info_text += f"运行时间限制: {job_info.get('time_limit', 'N/A')}\n"
        
        # 添加是否使用免费资源
        if 'use_free' in job_info:
            info_text += f"使用免费资源: {'是' if job_info['use_free'] else '否'}\n"
        
        # 添加提交时间
        if 'submit_time' in job_info:
            submit_time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(job_info['submit_time']))
            info_text += f"\n提交时间: {submit_time}\n"
        
        # 添加提交命令和脚本路径
        if 'command' in job_info:
            info_text += f"\n提交命令: {job_info['command']}\n"
        
        if 'script_path' in job_info:
            info_text += f"脚本路径: {job_info['script_path']}\n"
        
        # 更新作业信息文本
        self.job_info_text.setText(info_text)
        
        # 更新状态标签
        self.status_label.setText(f"作业 {job_info.get('job_id', 'N/A')} 已提交，状态: {job_info.get('status', 'N/A')}")
    
    @pyqtSlot(dict)
    def update_job_status(self, status_info):
        """更新作业状态信息"""
        if not status_info or not self.current_job:
            return
        
        # 更新当前作业状态
        self.current_job['status'] = status_info.get('status')
        if 'node' in status_info and status_info['node']:
            self.current_job['node'] = status_info['node']
        
        # 更新作业信息显示
        self.update_job_info(self.current_job)
        
        # 如果作业已结束，恢复UI状态
        if status_info.get('status') in ['COMPLETED', 'CANCELLED', 'FAILED', 'TIMEOUT']:
            self.submit_btn.setEnabled(True)
            self.cancel_btn.setEnabled(False)
    
    def show_error(self, error_msg):
        """显示错误信息"""
        self.status_label.setText(f"错误: {error_msg}")
        logger.error(error_msg)
        # 也可以显示对话框
        QMessageBox.critical(self, "错误", error_msg)

    @pyqtSlot(str, str)
    def on_ssh_config_added(self, job_id, hostname):
        """SSH配置被添加到本地文件时的处理函数"""
        logger.info(f"SSH配置已添加 - 作业: {job_id}, 主机: {hostname}")
        self.status_label.setText(f"已添加VSCode连接配置 - 主机: {hostname}")
        
        # 在作业信息中添加提示，使用setText完全替换文本，避免使用append
        job_info_text = self.job_info_text.toPlainText()
        if "SSH配置:" not in job_info_text:
            # 安全地更新文本
            new_text = job_info_text + "\n\nSSH配置: 已写入 ~/.ssh/config"
            self.job_info_text.setText(new_text)

    @pyqtSlot(str)
    def on_ssh_config_removed(self, job_id):
        """SSH配置从本地文件中移除时的处理函数"""
        logger.info(f"SSH配置已移除 - 作业: {job_id}")
        self.status_label.setText(f"已移除VSCode连接配置")

    @pyqtSlot(str)
    def update_status_safe(self, message):
        """安全地更新状态标签（从主线程调用）"""
        try:
            self.status_label.setText(message)
        except Exception as e:
            logger.error(f"更新状态标签失败: {e}")
    
    def remove_vscode_config(self, job_id):
        """移除VSCode配置"""
        try:
            # 执行移除操作
            self.vscode_manager.remove_ssh_config(job_id)
            self.status_label.setText(f"已移除VSCode连接配置")
        except Exception as e:
            logger.error(f"移除VSCode配置失败: {e}")
            self.show_error(f"移除VSCode配置失败: {str(e)}")