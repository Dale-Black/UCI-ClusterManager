from PyQt5.QtWidgets import (QDialog, QLineEdit, QPushButton, QFormLayout, QMessageBox, 
                            QInputDialog, QProgressDialog, QApplication, QVBoxLayout, QHBoxLayout, 
                            QListWidget, QLabel, QFrame, QGroupBox, QGridLayout, QComboBox, 
                            QListWidgetItem)
import logging
import os
import subprocess
import time
import pexpect
from PyQt5.QtCore import QTimer, Qt
from PyQt5.QtGui import QIcon, QFont
from modules.auth import HPC_SERVER, APP_MARKER, get_all_existing_users, delete_user_key
from modules.auth import check_and_login_with_key, get_node_info_via_key
from modules.ssh_key_uploader import generate_and_upload_ssh_key

# 全局变量存储最后一次成功登录的节点信息
LAST_NODE_INFO = None

def get_last_node_info():
    """获取最后一次成功登录的节点信息"""
    return LAST_NODE_INFO

class LoginDialog(QDialog):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('登录')
        self.setGeometry(100, 100, 500, 400)
        self.selected_user = None
        
        # 获取已存在的用户列表
        self.users = get_all_existing_users()
        
        # 初始化UI
        self.initUI()
        
        # 自动选择第一个用户（如果有）
        if self.users and self.user_list.count() > 0:
            self.user_list.setCurrentRow(0)
            self.on_user_selected(self.user_list.item(0))
        
        # 保存登录信息
        self.login_success = False
        self.ssh_key_created = False

    def initUI(self):
        """初始化UI组件"""
        main_layout = QVBoxLayout()
        
        # 添加用户选择部分
        user_selection_group = QGroupBox("选择已有用户")
        user_layout = QGridLayout()
        
        # 用户列表
        self.user_list = QListWidget()
        self.user_list.setMinimumHeight(150)
        self.populate_user_list()
        self.user_list.itemClicked.connect(self.on_user_selected)
        user_layout.addWidget(self.user_list, 0, 0, 1, 2)
        
        # 删除和使用密钥登录按钮
        button_layout = QHBoxLayout()
        
        delete_button = QPushButton("删除用户")
        delete_button.clicked.connect(self.delete_selected_user)
        button_layout.addWidget(delete_button)
        
        # 使用密钥登录按钮
        self.key_login_button = QPushButton("使用密钥登录")
        self.key_login_button.clicked.connect(self.login_with_key)
        self.key_login_button.setEnabled(self.selected_user is not None)
        button_layout.addWidget(self.key_login_button)
        
        user_layout.addLayout(button_layout, 1, 0, 1, 2)
        
        user_selection_group.setLayout(user_layout)
        main_layout.addWidget(user_selection_group)
        
        # 添加新用户登录部分
        login_group = QGroupBox("新建用户登录")
        login_layout = QFormLayout()
        
        # 用户名输入
        self.uc_id_input = QLineEdit()
        login_layout.addRow("UC ID:", self.uc_id_input)
        
        # 密码输入
        self.password_input = QLineEdit()
        self.password_input.setEchoMode(QLineEdit.Password)
        login_layout.addRow("密码:", self.password_input)
        
        login_group.setLayout(login_layout)
        main_layout.addWidget(login_group)
        
        # 添加登录按钮
        button_layout2 = QHBoxLayout()
        new_user_button = QPushButton("新建用户并登录")
        new_user_button.clicked.connect(self.handle_new_user_login)
        new_user_button.setMinimumHeight(40)
        button_layout2.addWidget(new_user_button)
        
        main_layout.addLayout(button_layout2)
        
        # 状态信息
        self.status_label = QLabel("")
        self.status_label.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(self.status_label)
        
        self.setLayout(main_layout)
    
    def populate_user_list(self):
        """填充用户列表"""
        self.user_list.clear()
        if not self.users:
            self.user_list.addItem("没有找到已保存的用户")
            return
        
        for user in self.users:
            username = user['username']
            item = QListWidgetItem(username)
            item.setData(Qt.UserRole, user)
            self.user_list.addItem(item)
    
    def on_user_selected(self, item):
        """用户列表项被选中时的处理函数"""
        user_data = item.data(Qt.UserRole)
        if not user_data:
            return
        
        self.selected_user = user_data
        self.uc_id_input.setText(user_data['username'])
        self.status_label.setText(f"已选择用户: {user_data['username']}")
        self.key_login_button.setEnabled(True)
    
    def delete_selected_user(self):
        """删除选中的用户"""
        if not self.selected_user:
            QMessageBox.warning(self, "警告", "请先选择一个用户")
            return
        
        confirm = QMessageBox.question(
            self, 
            "确认删除", 
            f"确定要删除用户 {self.selected_user['username']} 的密钥吗？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        
        if confirm == QMessageBox.Yes:
            success = delete_user_key(self.selected_user['username'])
            if success:
                # 更新用户列表
                self.users = get_all_existing_users()
                self.populate_user_list()
                self.selected_user = None
                self.uc_id_input.clear()
                self.status_label.setText("用户已删除")
                self.key_login_button.setEnabled(False)
            else:
                QMessageBox.critical(self, "错误", "删除用户时出错")
    
    def login_with_key(self):
        """使用选中用户的密钥登录"""
        if not self.selected_user:
            QMessageBox.warning(self, "警告", "请先选择一个用户")
            return
        
        try:
            self.status_label.setText(f"正在使用密钥登录 {self.selected_user['username']}...")
            QApplication.processEvents()
            
            # 尝试使用密钥登录
            success, username, message = check_and_login_with_key(self.selected_user['username'])
            
            if success:
                # 获取节点信息
                node_info = get_node_info_via_key(username)
                
                # 更新全局节点信息
                global LAST_NODE_INFO
                LAST_NODE_INFO = node_info
                
                # 登录成功
                logging.info(f"用户 {username} 使用密钥登录成功")
                self.login_success = True
                QMessageBox.information(self, "成功", f"使用密钥登录成功!\n\n{message}")
                self.accept()
            else:
                logging.error(f"密钥登录失败: {message}")
                self.status_label.setText("密钥登录失败")
                QMessageBox.warning(self, "登录失败", f"密钥登录失败: {message}")
        except Exception as e:
            logging.error(f"密钥登录过程中出错: {e}")
            self.status_label.setText("登录出错")
            QMessageBox.critical(self, "错误", f"登录过程中出现错误: {str(e)}")
    
    def handle_new_user_login(self):
        """处理新建用户登录"""
        uc_id = self.uc_id_input.text()
        password = self.password_input.text()
        
        if not uc_id or not password:
            QMessageBox.warning(self, "警告", "请输入用户名和密码")
            return
        
        try:
            # 显示登录中的提示
            self.status_label.setText("正在创建新用户并登录，请稍候...")
            QApplication.processEvents()
            
            # 使用generate_and_upload_ssh_key函数创建新用户并登录
            result = generate_and_upload_ssh_key(
                username=uc_id,
                password=password,
                host=HPC_SERVER,
                force=True
            )
            
            if result:
                # 登录成功，获取节点信息
                node_info = get_node_info_via_key(uc_id)
                
                # 更新全局节点信息
                global LAST_NODE_INFO
                LAST_NODE_INFO = node_info
                
                # 更新用户列表
                self.users = get_all_existing_users()
                
                # 登录成功
                logging.info(f"新用户创建并登录成功: {uc_id}")
                self.login_success = True
                self.ssh_key_created = True
                
                # 创建等待对话框，等待密钥生效
                progress = QProgressDialog("SSH密钥已创建，等待生效中...", "取消", 0, 100, self)
                progress.setWindowTitle("密钥生效")
                progress.setMinimumDuration(0)
                progress.setAutoClose(True)
                progress.setValue(0)
                progress.show()
                
                # 设置进度条更新
                self.wait_timer = QTimer(self)
                self.wait_step = 0
                
                def update_progress():
                    self.wait_step += 5
                    progress.setValue(self.wait_step)
                    
                    if self.wait_step >= 100:
                        self.wait_timer.stop()
                        progress.close()
                        # 显示成功消息
                        message = f"登录成功!\n\nSSH密钥已创建并生效。\n下次登录将自动使用密钥。\n\n节点信息:\n{node_info if node_info else '无节点信息'}"
                        QMessageBox.information(self, "成功", message)
                        self.accept()
                
                self.wait_timer.timeout.connect(update_progress)
                self.wait_timer.start(1000)  # 每秒更新一次，总共20秒
            else:
                # 登录失败
                logging.error("登录失败")
                self.status_label.setText("登录失败，请检查您的凭据")
                QMessageBox.warning(self, "登录失败", "登录失败，请检查您的凭据并重试。")
        except Exception as e:
            logging.error(f"登录过程中出错: {e}")
            self.status_label.setText("登录出错")
            QMessageBox.critical(self, "错误", f"登录过程中出现错误: {str(e)}") 