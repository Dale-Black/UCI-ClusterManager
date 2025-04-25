#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, 
                           QFrame, QGridLayout, QProgressBar, QGroupBox, QTextEdit)
from PyQt5.QtCore import Qt, pyqtSlot
from PyQt5.QtGui import QFont

import logging
from modules.storage import StorageManager
from modules.auth import HPC_SERVER, get_all_existing_users

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger('StorageWidget')

class StorageWidget(QWidget):
    """Storage management component, displays various storage space usage for users on HPC"""
    
    def __init__(self, parent=None, username=None):
        super().__init__(parent)
        
        # User information
        self.username = username
        self.storage_manager = None
        
        # Storage data
        self.storage_data = None
        
        # Initialize UI
        self.init_ui()
        
        # Initialize storage manager
        self.init_storage_manager()
    
    def init_storage_manager(self):
        """Initialize storage manager"""
        if not self.username:
            self.status_label.setText("Error: Username not provided")
            return
        
        # Get SSH key path
        users = get_all_existing_users()
        key_path = None
        
        for user in users:
            if user['username'] == self.username:
                key_path = user['key_path']
                break
        
        if not key_path:
            self.status_label.setText(f"Error: SSH key for user {self.username} not found")
            return
        
        try:
            # Create storage manager
            self.storage_manager = StorageManager(
                hostname=HPC_SERVER,
                username=self.username,
                key_path=key_path
            )
            
            # Connect signals
            self.storage_manager.storage_updated.connect(self.update_storage_data)
            self.storage_manager.error_occurred.connect(self.show_error)
            
            # Update status
            self.status_label.setText("Storage manager initialized, ready")
            
            # Start refresh
            self.refresh_storage_info()
        except Exception as e:
            self.status_label.setText(f"Error: Failed to initialize storage manager - {str(e)}")
    
    def init_ui(self):
        """Initialize UI components"""
        main_layout = QVBoxLayout(self)
        
        # Top control bar
        control_layout = QHBoxLayout()
        
        # Refresh button
        self.refresh_btn = QPushButton("Refresh Storage Info")
        self.refresh_btn.clicked.connect(self.refresh_storage_info)
        control_layout.addWidget(self.refresh_btn)
        
        # Refresh status indicator
        self.refresh_indicator = QLabel("Ready")
        control_layout.addWidget(self.refresh_indicator)
        
        control_layout.addStretch()
        
        # Add control bar to main layout
        main_layout.addLayout(control_layout)
        
        # Create storage overview group box
        overview_group = QGroupBox("Storage Overview")
        overview_layout = QVBoxLayout(overview_group)
        
        # Create groups for various storage spaces
        self.create_storage_section("HOME Directory", overview_layout)
        self.create_storage_section("Personal DFS Space", overview_layout)
        self.create_storage_section("Lab Shared DFS", overview_layout)
        self.create_storage_section("Personal CRSP Space", overview_layout)
        self.create_storage_section("Lab Shared CRSP", overview_layout)
        self.create_storage_section("Temporary Storage (Scratch)", overview_layout)
        
        # Add to main layout
        main_layout.addWidget(overview_group)
        
        # Bottom status bar
        self.status_label = QLabel("Initializing...")
        main_layout.addWidget(self.status_label)
    
    def create_storage_section(self, title, parent_layout):
        """Create storage section display part"""
        frame = QFrame()
        frame.setFrameShape(QFrame.StyledPanel)
        layout = QGridLayout(frame)
        
        # Title
        title_label = QLabel(title)
        title_label.setFont(QFont('Arial', 12, QFont.Bold))
        layout.addWidget(title_label, 0, 0, 1, 2)
        
        # Path label
        path_label = QLabel("Path:")
        layout.addWidget(path_label, 1, 0)
        
        path_value = QLabel("Loading...")
        path_value.setObjectName(f"{title.lower().replace(' ', '_').replace('(', '').replace(')', '')}_path")
        layout.addWidget(path_value, 1, 1)
        
        # Usage label
        usage_label = QLabel("Usage:")
        layout.addWidget(usage_label, 2, 0)
        
        # Progress bar
        progress = QProgressBar()
        progress.setObjectName(f"{title.lower().replace(' ', '_').replace('(', '').replace(')', '')}_progress")
        progress.setFormat("%v / %m (%p%)")
        layout.addWidget(progress, 2, 1)
        
        # Add to parent layout
        parent_layout.addWidget(frame)
    
    @pyqtSlot()
    def refresh_storage_info(self):
        """Refresh storage information"""
        if not self.storage_manager:
            self.show_error("Storage manager not set, unable to retrieve data")
            return
        
        # Update UI status
        self.refresh_btn.setEnabled(False)
        self.refresh_indicator.setText("Refreshing...")
        self.status_label.setText("Retrieving storage information...")
        
        # Get storage information
        try:
            self.storage_manager.refresh_storage_info()
        except Exception as e:
            self.show_error(f"Error refreshing storage information: {str(e)}")
            self.refresh_btn.setEnabled(True)
    
    @pyqtSlot(dict)
    def update_storage_data(self, storage_data):
        """Update storage data"""
        self.storage_data = storage_data
        
        # Update UI
        try:
            self.update_ui()
        except Exception as e:
            self.show_error(f"Error updating UI: {str(e)}")
        
        # Restore UI status
        self.refresh_btn.setEnabled(True)
        self.refresh_indicator.setText("Refresh complete")
        self.status_label.setText("Storage information updated")
    
    def update_ui(self):
        """Update UI display"""
        if not self.storage_data:
            return
        
        # Update HOME information
        if 'home' in self.storage_data:
            self.update_storage_section_with_data(self.storage_data['home'], "HOME Directory")
        
        # Update personal DFS information
        if 'personal_dfs' in self.storage_data:
            self.update_storage_section_with_data(self.storage_data['personal_dfs'], "Personal DFS Space")
        
        # Update lab DFS information
        if 'lab_dfs' in self.storage_data and self.storage_data['lab_dfs']:
            self.update_storage_section_with_data(self.storage_data['lab_dfs'][0], "Lab Shared DFS")
        
        # Update personal CRSP information
        if 'personal_crsp' in self.storage_data:
            self.update_storage_section_with_data(self.storage_data['personal_crsp'], "Personal CRSP Space")
        
        # Update lab CRSP information
        if 'lab_crsp' in self.storage_data:
            self.update_storage_section_with_data(self.storage_data['lab_crsp'], "Lab Shared CRSP")
        
        # Update Scratch information
        if 'scratch' in self.storage_data:
            self.update_storage_section_with_data(self.storage_data['scratch'], "Temporary Storage (Scratch)")
    
    def update_storage_section_with_data(self, data, ui_key):
        """Update storage section UI with data"""
        ui_base = ui_key.lower().replace(' ', '_').replace('(', '').replace(')', '')
        
        # Update path
        path_label = self.findChild(QLabel, f"{ui_base}_path")
        if path_label:
            path_label.setText(data.get('path', 'Unknown'))
        
        # Update progress bar
        progress = self.findChild(QProgressBar, f"{ui_base}_progress")
        if progress:
            if data.get('exists', False):
                # Try converting usage percentage to number
                try:
                    use_percent = float(data.get('use_percent', 0))
                except:
                    use_percent = 0
                
                # Set progress bar
                progress.setMaximum(100)
                progress.setValue(int(use_percent))
                progress.setFormat(f"{data.get('used', '?')} / {data.get('total', '?')} ({use_percent}%)")
                
                # Set color
                self.set_progress_bar_color(progress, use_percent)
            else:
                progress.setValue(0)
                progress.setFormat(data.get('error', "Directory does not exist"))
    
    def set_progress_bar_color(self, progress_bar, usage_ratio):
        """Set progress bar color based on usage rate"""
        if usage_ratio > 90:
            progress_bar.setStyleSheet("""
                QProgressBar::chunk { background-color: red; }
                QProgressBar { text-align: center; }
            """)
        elif usage_ratio > 70:
            progress_bar.setStyleSheet("""
                QProgressBar::chunk { background-color: orange; }
                QProgressBar { text-align: center; }
            """)
        else:
            progress_bar.setStyleSheet("""
                QProgressBar::chunk { background-color: green; }
                QProgressBar { text-align: center; }
            """)
    
    def show_error(self, error_msg):
        """Display error message"""
        self.refresh_indicator.setText(f"Error")
        self.status_label.setText(f"Error: {error_msg}")
        logger.error(error_msg)
        
        # Enable refresh button
        self.refresh_btn.setEnabled(True) 