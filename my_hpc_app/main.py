#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# main.py
# Main program entry point

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

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class MainWindow(QMainWindow):
    def __init__(self, username=None, node_info=None):
        super().__init__()
        self.username = username
        self.node_info = node_info
        self.initUI()

    def initUI(self):
        self.setWindowTitle('HPC Management System')
        self.setGeometry(100, 100, 1200, 800)
        
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
            "Storage Management",
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
        self.setup_storage_management_page()
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
        self.statusBar.showMessage(f'Logged in: {self.username or "Unknown user"}')
        
        # Select first option by default
        self.sidebar.setCurrentRow(0)

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

    def setup_storage_management_page(self):
        """Set up storage management page"""
        try:
            logger.info(f"Initializing storage management page, user: {self.username}")
            # Create storage management component
            storage_widget = StorageWidget(username=self.username)
            
            # Create page container
            page = QWidget()
            layout = QVBoxLayout(page)
            layout.addWidget(storage_widget)
            
            # Add to page stack
            self.pages.addWidget(page)
            logger.info("Storage management page initialization complete")
        except Exception as e:
            logger.error(f"Failed to initialize storage management page: {e}")
            # Create error page
            page = QWidget()
            layout = QVBoxLayout(page)
            
            # Error message
            error_label = QLabel(f"Failed to load storage management component: {str(e)}")
            error_label.setStyleSheet("color: red;")
            layout.addWidget(error_label)
            
            # Retry button
            retry_btn = QPushButton("Retry")
            retry_btn.clicked.connect(lambda: self.reload_storage_page())
            layout.addWidget(retry_btn)
            
            # Add to page stack
            self.pages.addWidget(page)
    
    def reload_storage_page(self):
        """Reload storage management page"""
        try:
            # Remove current page
            current_index = self.pages.currentIndex()
            current_widget = self.pages.widget(current_index)
            self.pages.removeWidget(current_widget)
            current_widget.deleteLater()
            
            # Create new page
            self.setup_storage_management_page()
            
            # Show new page
            self.pages.setCurrentIndex(current_index)
            logger.info("Storage management page reload complete")
        except Exception as e:
            logger.error(f"Failed to reload storage management page: {e}")
            QMessageBox.critical(self, "Error", f"Failed to reload storage management page: {str(e)}")

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
        self.pages.setCurrentIndex(4)  # Account balance page index

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

if __name__ == '__main__':
    app = QApplication(sys.argv)
    
    # First check network connection
    if not can_connect_to_hpc():
        logging.error('Cannot connect to HPC. Please check your network connection.')
        QMessageBox.critical(None, 'Error', 'Unable to connect to HPC server. Please check your network connection.')
        sys.exit(1)
    
    # Show login dialog directly, no auto-login
    login_dialog = LoginDialog()
    if login_dialog.exec_() == QDialog.Accepted:
        # Login successful, get node info and username
        node_info = ui_get_last_node_info()  # Use function from ui module
        if not node_info:
            node_info = get_last_node_info()  # If not in ui module, use from auth module
            
        uc_id = login_dialog.uc_id_input.text()
        
        # Show main window
        window = MainWindow(username=uc_id, node_info=node_info)
        window.show()
        
        # Ensure application continues running
        sys.exit(app.exec_())
    else:
        # User cancelled login
        logging.info('User cancelled login')
        sys.exit(0) 