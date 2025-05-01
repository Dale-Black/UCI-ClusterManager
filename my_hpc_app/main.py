#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# main.py
# Main program entry point

import sys
import logging
import os
import time
from PyQt5.QtWidgets import (QApplication, QMainWindow, QAction, QLabel, QVBoxLayout, QWidget, 
                           QTextEdit, QMessageBox, QDialog, QHBoxLayout, QListWidget, QStackedWidget,
                           QPushButton, QGridLayout, QGroupBox, QFrame, QSplitter, QProgressDialog)
from PyQt5.QtCore import QTranslator, Qt, QSize, QTimer
from PyQt5.QtGui import QIcon, QFont, QMovie
from modules.auth import can_connect_to_hpc, check_and_login_with_key, get_last_node_info, check_network_connectivity, HPC_SERVER
from ui.login_dialog import LoginDialog, get_last_node_info as ui_get_last_node_info
from ui.task_manager_widget import TaskManagerWidget
from ui.node_status_widget import NodeStatusWidget
from ui.balance_widget import BalanceWidget
from ui.vscode_widget import VSCodeWidget
from ui.update_dialog import check_for_updates_with_ui
from modules.updater import get_current_version

# Configure logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class MainWindow(QMainWindow):
    def __init__(self, username=None, node_info=None):
        super().__init__()
        self.username = username
        self.node_info = node_info
        self.initUI()

    def initUI(self):
        self.setWindowTitle(f'UCI-ClusterManager - v{get_current_version()}')
        self.setGeometry(100, 100, 1200, 800)
        
        # Set application icon
        self.setAppIcon()
        
        # Create central widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # Create main layout
        main_layout = QHBoxLayout(central_widget)
        
        # Create left sidebar
        self.sidebar = QListWidget()
        self.sidebar.setMinimumWidth(200)
        self.sidebar.setMaximumWidth(300)
        self.sidebar.setFont(QFont('Arial', 12))
        
        # Add sidebar items
        sidebar_items = [
            "Job Management",
            "Node Status",
            "VSCode Configuration",
            "Account Balance"
        ]
        
        for item in sidebar_items:
            self.sidebar.addItem(item)
        
        # Connect sidebar item click event
        self.sidebar.currentRowChanged.connect(self.display_page)
        
        # Create stacked widget for different pages
        self.pages = QStackedWidget()
        
        # Add function pages
        self.setup_task_management_page()
        self.setup_node_status_page()
        self.setup_vscode_page()
        self.setup_balance_page()
        
        # Create splitter to adjust sidebar width
        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(self.sidebar)
        splitter.addWidget(self.pages)
        splitter.setSizes([200, 1000])
        
        # Add splitter to main layout
        main_layout.addWidget(splitter)
        
        # Create status bar
        self.statusBar = self.statusBar()
        self.statusBar.showMessage(f'Logged in as: {self.username or "Unknown User"}')
        
        # Create menu bar
        self.create_menu_bar()
        
        # Select first option by default
        self.sidebar.setCurrentRow(0)
        
        # Schedule update check after startup
        QTimer.singleShot(3000, self.check_for_updates)
    
    def create_menu_bar(self):
        """Create the application menu bar"""
        menubar = self.menuBar()
        
        # File menu
        file_menu = menubar.addMenu('File')
        
        # Exit action
        exit_action = QAction('Exit', self)
        exit_action.setShortcut('Ctrl+Q')
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)
        
        # Help menu
        help_menu = menubar.addMenu('Help')
        
        # Check for updates action
        update_action = QAction('Check for Updates', self)
        update_action.triggered.connect(lambda: check_for_updates_with_ui(self, silent=False))
        help_menu.addAction(update_action)
        
        # About action
        about_action = QAction('About', self)
        about_action.triggered.connect(self.show_about_dialog)
        help_menu.addAction(about_action)
    
    def show_about_dialog(self):
        """Show about dialog"""
        QMessageBox.about(
            self, 
            "About UCI-ClusterManager",
            f"<h3>UCI-ClusterManager</h3>"
            f"<p>Version: {get_current_version()}</p>"
            f"<p>A comprehensive tool for managing UCI HPC cluster resources.</p>"
            f"<p>© 2024 Song Liangyu and contributors</p>"
            f"<p>Licensed under MIT License</p>"
        )
    
    def check_for_updates(self):
        """Check for updates silently"""
        check_for_updates_with_ui(self, silent=True)
    
    def setAppIcon(self):
        """Set application icon"""
        icon_paths = [
            "my_hpc_app/resources/icon.png",          # Universal PNG format
            "my_hpc_app/resources/icon.icns",         # macOS format
            "my_hpc_app/resources/icon.ico",          # Windows format
            "resources/icon.png",                     # Packaged path
            "icon.png"                               # Fallback path
        ]
        
        for icon_path in icon_paths:
            if os.path.exists(icon_path):
                self.setWindowIcon(QIcon(icon_path))
                logger.info(f"Using icon: {icon_path}")
                break

    def setup_task_management_page(self):
        """Set up task management page"""
        # Create task manager component
        task_manager = TaskManagerWidget(username=self.username)
        self.pages.addWidget(task_manager)

    def setup_node_status_page(self):
        """Set up node status page"""
        # Create node status component
        node_status = NodeStatusWidget(username=self.username)
        self.pages.addWidget(node_status)

    def setup_vscode_page(self):
        """Set up VSCode configuration page"""
        # Create VSCode configuration component
        vscode_widget = VSCodeWidget(username=self.username)
        
        # Create page container
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addWidget(vscode_widget)
        
        # Add to page stack
        self.pages.addWidget(page)

    def setup_balance_page(self):
        """Set up account balance page"""
        # Create balance component
        balance_widget = BalanceWidget(username=self.username)
        
        # Create page container
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addWidget(balance_widget)
        
        # Add to page stack
        self.pages.addWidget(page)

    def display_page(self, index):
        """Display selected page"""
        self.pages.setCurrentIndex(index)

    def check_network(self):
        """Check network connection to ensure HPC server is accessible"""
        logging.info("Checking network connection to HPC...")
        network_ok = check_network_connectivity(HPC_SERVER)
        if network_ok:
            logging.info("Network connection to HPC is successful.")
        else:
            logging.error("Failed to connect to HPC server.")
        return network_ok

    def show_login_dialog(self):
        """Show login dialog"""
        login_dialog = LoginDialog(self)
        if login_dialog.exec_():
            # Login successful
            self.username = login_dialog.uc_id_input.text()
            self.node_info = ui_get_last_node_info()
            self.init_components()
        else:
            # Login cancelled or failed
            logging.info('User cancelled login')
            sys.exit(0)

    def init_components(self):
        """Initialize components"""
        pass  # This method is not needed, implemented through other means

    def show_node_status(self):
        """Show node status view"""
        self.pages.setCurrentIndex(1)  # Node status page index

    def show_balance(self):
        """Show account balance view"""
        self.pages.setCurrentIndex(3)  # Account balance page index (updated index)

    def closeEvent(self, event):
        """Close window event"""
        reply = QMessageBox.question(self, 'Confirm Exit', 
                                     'Are you sure you want to exit the application?',
                                     QMessageBox.Yes | QMessageBox.No,
                                     QMessageBox.No)
        
        if reply == QMessageBox.Yes:
            event.accept()
        else:
            event.ignore()

def main():
    """
    Application main entry point
    """
    app = QApplication(sys.argv)
    
    # Set application icon
    icon_paths = [
        "my_hpc_app/resources/icon.png",
        "resources/icon.png",
        "icon.png"
    ]
    
    for icon_path in icon_paths:
        if os.path.exists(icon_path):
            app.setWindowIcon(QIcon(icon_path))
            break
    
    # 禁用自动登录，总是显示登录对话框
    username = None
    node_info = None
    
    # 显示登录对话框
    login_dialog = LoginDialog()
    if login_dialog.exec_() != QDialog.Accepted:
        return 0
    
    username = login_dialog.uc_id_input.text()
    node_info = get_last_node_info()
    
    # 创建并显示加载提示（使用旋转指示器）
    loading_dialog = QDialog()
    loading_dialog.setWindowTitle("Loading")
    loading_dialog.setWindowModality(Qt.WindowModal)
    loading_dialog.setFixedSize(300, 140)
    loading_layout = QVBoxLayout(loading_dialog)
    
    # 创建旋转指示器
    spinner_label = QLabel("⟳")  # 使用Unicode旋转字符
    spinner_label.setStyleSheet("font-size: 32pt; color: #3498db;")
    spinner_label.setAlignment(Qt.AlignCenter)
    loading_layout.addWidget(spinner_label)
    
    # 创建旋转动画
    rotation_timer = QTimer()
    rotation_angle = 0
    
    def rotate_text():
        nonlocal rotation_angle
        rotation_angle = (rotation_angle + 10) % 360
        spinner_label.setStyleSheet(f"font-size: 32pt; color: #3498db; transform: rotate({rotation_angle}deg);")
    
    rotation_timer.timeout.connect(rotate_text)
    rotation_timer.start(50)  # 旋转速度
    
    # 添加标签
    loading_text = QLabel("Loading UCI-ClusterManager...")
    loading_text.setAlignment(Qt.AlignCenter)
    loading_layout.addWidget(loading_text)
    
    # 显示加载对话框
    loading_dialog.show()
    
    # 初始化主窗口
    main_window = MainWindow(username=username, node_info=node_info)
    
    # 延迟显示主窗口
    def show_main_window():
        loading_dialog.close()
        rotation_timer.stop()
        main_window.show()
    
    # 延迟1.5秒显示主窗口
    QTimer.singleShot(1500, show_main_window)
    
    return app.exec_()

if __name__ == '__main__':
    sys.exit(main()) 