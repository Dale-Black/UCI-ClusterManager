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
from modules.auth import can_connect_to_hpc, check_and_login_with_key, get_last_node_info, check_network_connectivity, HPC_SERVER
from ui.login_dialog import LoginDialog, get_last_node_info as ui_get_last_node_info
from ui.task_manager_widget import TaskManagerWidget
from ui.node_status_widget import NodeStatusWidget
from ui.balance_widget import BalanceWidget
from ui.storage_widget import StorageWidget
from ui.vscode_widget import VSCodeWidget

# 配置日志记录
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

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
            "存储管理",
            "VSCode配置",
            "账户可用计算余额"
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
        self.setup_storage_management_page()
        self.setup_vscode_page()
        self.setup_balance_page()
        
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

    def setup_storage_management_page(self):
        """设置存储管理页面"""
        try:
            logger.info(f"初始化存储管理页面，用户: {self.username}")
            # 创建存储管理组件
            storage_widget = StorageWidget(username=self.username)
            
            # 创建页面容器
            page = QWidget()
            layout = QVBoxLayout(page)
            layout.addWidget(storage_widget)
            
            # 添加到页面堆栈
            self.pages.addWidget(page)
            logger.info("存储管理页面初始化完成")
        except Exception as e:
            logger.error(f"初始化存储管理页面失败: {e}")
            # 创建错误页面
            page = QWidget()
            layout = QVBoxLayout(page)
            
            # 错误消息
            error_label = QLabel(f"加载存储管理组件失败: {str(e)}")
            error_label.setStyleSheet("color: red;")
            layout.addWidget(error_label)
            
            # 重试按钮
            retry_btn = QPushButton("重试")
            retry_btn.clicked.connect(lambda: self.reload_storage_page())
            layout.addWidget(retry_btn)
            
            # 添加到页面堆栈
            self.pages.addWidget(page)
    
    def reload_storage_page(self):
        """重新加载存储管理页面"""
        try:
            # 移除当前页面
            current_index = self.pages.currentIndex()
            current_widget = self.pages.widget(current_index)
            self.pages.removeWidget(current_widget)
            current_widget.deleteLater()
            
            # 创建新页面
            self.setup_storage_management_page()
            
            # 显示新页面
            self.pages.setCurrentIndex(current_index)
            logger.info("存储管理页面重新加载完成")
        except Exception as e:
            logger.error(f"重新加载存储管理页面失败: {e}")
            QMessageBox.critical(self, "错误", f"重新加载存储管理页面失败: {str(e)}")

    def setup_vscode_page(self):
        """设置VSCode配置页面"""
        # 创建VSCode配置组件
        vscode_widget = VSCodeWidget(username=self.username)
        
        # 创建页面容器
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addWidget(vscode_widget)
        
        # 添加到页面堆栈
        self.pages.addWidget(page)

    def setup_balance_page(self):
        """设置账户可用计算余额页面"""
        # 创建计算资源余额组件
        balance_widget = BalanceWidget(username=self.username)
        
        # 创建页面容器
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addWidget(balance_widget)
        
        # 添加到页面堆栈
        self.pages.addWidget(page)

    def display_page(self, index):
        """显示选中的页面"""
        self.pages.setCurrentIndex(index)

    def check_network(self):
        """检查网络连接，确保可以连接到HPC服务器"""
        logging.info("Checking network connection to HPC...")
        network_ok = check_network_connectivity(HPC_SERVER)
        if network_ok:
            logging.info("Network connection to HPC is successful.")
        else:
            logging.error("Failed to connect to HPC server.")
        return network_ok

    def show_login_dialog(self):
        """显示登录对话框"""
        login_dialog = LoginDialog(self)
        if login_dialog.exec_():
            # 登录成功
            self.username = login_dialog.uc_id_input.text()
            self.node_info = ui_get_last_node_info()
            self.init_components()
        else:
            # 登录取消或失败
            logging.info('User cancelled login')
            sys.exit(0)

    def init_components(self):
        """初始化各组件"""
        pass  # 这个方法不需要，已通过其他方式实现

    def show_node_status(self):
        """显示节点状态视图"""
        self.pages.setCurrentIndex(1)  # 节点状态页的索引

    def show_balance(self):
        """显示账户可用计算余额视图"""
        self.pages.setCurrentIndex(4)  # 账户可用计算余额页的索引

    def closeEvent(self, event):
        """关闭窗口事件"""
        reply = QMessageBox.question(self, '确认退出', 
                                     '确定要退出应用程序吗？',
                                     QMessageBox.Yes | QMessageBox.No,
                                     QMessageBox.No)
        
        if reply == QMessageBox.Yes:
            event.accept()
        else:
            event.ignore()

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