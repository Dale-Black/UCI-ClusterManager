#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# main.py
# 主程序入口

import sys
import logging
import os
from PyQt5.QtWidgets import (QApplication, QMainWindow, QAction, QLabel, QVBoxLayout, QWidget, 
                           QTextEdit, QMessageBox, QDialog, QHBoxLayout, QListWidget, QStackedWidget,
                           QPushButton, QGridLayout, QGroupBox, QFrame, QSplitter, QProgressDialog)
from PyQt5.QtCore import QTranslator, Qt, QSize, QTimer
from PyQt5.QtGui import QIcon, QFont
from modules.auth import can_connect_to_hpc, check_and_login_with_key, get_last_node_info
from ui.login_dialog import LoginDialog, get_last_node_info as ui_get_last_node_info
from ui.task_manager_widget import TaskManagerWidget
from ui.node_status_widget import NodeStatusWidget

# 配置日志记录
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class MainWindow(QMainWindow):
    def __init__(self, username=None, node_info=None):
        super().__init__()
        self.username = username
        self.node_info = node_info
        self.initUI()

    def initUI(self):
        self.setWindowTitle('HPC管理系统')
        self.setGeometry(100, 100, 1200, 800)
        
        # 创建中央部件
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # 创建主布局
        main_layout = QHBoxLayout(central_widget)
        
        # 创建左侧侧栏
        self.sidebar = QListWidget()
        self.sidebar.setMinimumWidth(200)
        self.sidebar.setMaximumWidth(300)
        self.sidebar.setFont(QFont('Arial', 12))
        
        # 添加侧栏项目
        sidebar_items = [
            "任务管理",
            "节点可用状态",
            "用户账户状态",
            "存储管理",
            "软件环境"
        ]
        
        for item in sidebar_items:
            self.sidebar.addItem(item)
        
        # 连接侧栏项目点击事件
        self.sidebar.currentRowChanged.connect(self.display_page)
        
        # 创建堆叠部件，用于显示不同页面
        self.pages = QStackedWidget()
        
        # 添加各个功能页面
        self.setup_task_management_page()
        self.setup_node_status_page()
        self.setup_user_account_page()
        self.setup_storage_management_page()
        self.setup_software_environment_page()
        
        # 创建分割器，允许调整侧栏宽度
        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(self.sidebar)
        splitter.addWidget(self.pages)
        splitter.setSizes([200, 1000])
        
        # 添加分割器到主布局
        main_layout.addWidget(splitter)
        
        # 创建状态栏
        self.statusBar = self.statusBar()
        self.statusBar.showMessage(f'已登录: {self.username or "未知用户"}')
        
        # 默认选择第一个选项
        self.sidebar.setCurrentRow(0)

    def setup_task_management_page(self):
        """设置任务管理页面"""
        # 创建任务管理组件
        task_manager = TaskManagerWidget(username=self.username)
        self.pages.addWidget(task_manager)

    def setup_node_status_page(self):
        """设置节点可用状态页面"""
        # 创建节点状态组件
        node_status = NodeStatusWidget(username=self.username)
        self.pages.addWidget(node_status)

    def setup_user_account_page(self):
        """设置用户账户状态页面"""
        page = QWidget()
        layout = QVBoxLayout(page)
        
        # 标题
        title = QLabel("用户账户状态")
        title.setFont(QFont('Arial', 16, QFont.Bold))
        layout.addWidget(title)
        
        # 占位符内容
        placeholder = QLabel("此处将显示用户账户状态")
        placeholder.setAlignment(Qt.AlignCenter)
        layout.addWidget(placeholder)
        
        # 添加到堆叠部件
        self.pages.addWidget(page)

    def setup_storage_management_page(self):
        """设置存储管理页面"""
        page = QWidget()
        layout = QVBoxLayout(page)
        
        # 标题
        title = QLabel("存储管理")
        title.setFont(QFont('Arial', 16, QFont.Bold))
        layout.addWidget(title)
        
        # 占位符内容
        placeholder = QLabel("此处将显示存储管理功能")
        placeholder.setAlignment(Qt.AlignCenter)
        layout.addWidget(placeholder)
        
        # 添加到堆叠部件
        self.pages.addWidget(page)

    def setup_software_environment_page(self):
        """设置软件环境页面"""
        page = QWidget()
        layout = QVBoxLayout(page)
        
        # 标题
        title = QLabel("软件环境")
        title.setFont(QFont('Arial', 16, QFont.Bold))
        layout.addWidget(title)
        
        # 占位符内容
        placeholder = QLabel("此处将显示软件环境管理功能")
        placeholder.setAlignment(Qt.AlignCenter)
        layout.addWidget(placeholder)
        
        # 添加到堆叠部件
        self.pages.addWidget(page)

    def display_page(self, index):
        """显示选中的页面"""
        self.pages.setCurrentIndex(index)

if __name__ == '__main__':
    app = QApplication(sys.argv)
    
    # 首先检查网络连接
    if not can_connect_to_hpc():
        logging.error('Cannot connect to HPC. Please check your network connection.')
        QMessageBox.critical(None, '错误', '无法连接到HPC服务器。请检查网络连接。')
        sys.exit(1)
    
    # 直接显示登录对话框，不自动登录
    login_dialog = LoginDialog()
    if login_dialog.exec_() == QDialog.Accepted:
        # 登录成功，获取节点信息和用户名
        node_info = ui_get_last_node_info()  # 使用ui模块中的函数
        if not node_info:
            node_info = get_last_node_info()  # 如果ui模块中没有，则使用auth模块中的
            
        uc_id = login_dialog.uc_id_input.text()
        
        # 显示主窗口
        window = MainWindow(username=uc_id, node_info=node_info)
        window.show()
        
        # 确保应用程序继续运行
        sys.exit(app.exec_())
    else:
        # 用户取消登录
        logging.info('User cancelled login')
        sys.exit(0) 