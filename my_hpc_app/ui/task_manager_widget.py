#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, 
                           QTableWidget, QTableWidgetItem, QTabWidget, QTextEdit, 
                           QFormLayout, QLineEdit, QComboBox, QSpinBox, 
                           QGroupBox, QSplitter, QMessageBox, QMenu, QDialog, 
                           QDialogButtonBox, QFileDialog, QCheckBox, QFrame)
from PyQt5.QtCore import Qt, QTimer, pyqtSlot
from PyQt5.QtGui import QFont, QColor
import logging
import os
import time
from modules.slurm import SlurmManager
from modules.auth import HPC_SERVER, get_all_existing_users

class JobSubmissionDialog(QDialog):
    """Job Submission Dialog"""
    
    def __init__(self, parent=None, partitions=None, accounts=None, username=None):
        super().__init__(parent)
        self.setWindowTitle("Submit New Job")
        self.resize(700, 500)
        
        # Partition list
        self.partitions = partitions or []
        
        # Account list
        self.accounts = accounts or []
        
        # Username
        self.username = username
        
        # GPU type list
        self.gpu_types = []
        
        # Initialize NodeStatusManager for getting GPU info
        self.node_manager = None
        if username:
            self.init_node_manager(username)
        
        # Initialize UI
        self.initUI()
        
        # Initialize GPU types
        if self.node_manager:
            self.fetch_gpu_types()
    
    def init_node_manager(self, username):
        """Initialize node status manager"""
        # Get SSH key path
        users = get_all_existing_users()
        key_path = None
        
        for user in users:
            if user['username'] == username:
                key_path = user['key_path']
                break
        
        if not key_path:
            logging.warning(f"SSH key for user {username} not found")
            return
        
        # Initialize node manager
        try:
            from modules.node_status import NodeStatusManager
            self.node_manager = NodeStatusManager(
                hostname=HPC_SERVER,
                username=username,
                key_path=key_path
            )
        except Exception as e:
            logging.error(f"Failed to initialize node manager: {e}")
    
    def fetch_gpu_types(self):
        """Get available GPU types"""
        try:
            # Add default option (no GPU) and generic GPU option
            self.gpu_types = [
                {"name": "No GPU", "value": None},
                {"name": "Any GPU (recommended)", "value": ""}
            ]
            
            # Get GPU types from node manager
            if self.node_manager and self.node_manager.connect_ssh():
                try:
                    # Use sinfo command to get GPU types
                    gpu_cmd = 'sinfo -o "%60N %10c %10m  %30f %10G" -e'
                    output = self.node_manager.execute_ssh_command(gpu_cmd)
                    
                    # Parse output to get GPU types
                    gpu_types_set = set()
                    lines = output.strip().split('\n')
                    
                    # Look for GPU types in output
                    if len(lines) > 1:
                        for line in lines[1:]:
                            if "gpu:" in line:
                                parts = line.split("gpu:")[1].split(":")
                                if len(parts) > 0 and parts[0] and parts[0] not in ["N/A", ""]:
                                    gpu_types_set.add(parts[0])
                    
                    # Add found GPU types
                    for gpu_type in sorted(gpu_types_set):
                        self.gpu_types.append({
                            "name": f"{gpu_type} GPU (specific)",
                            "value": gpu_type
                        })
                except Exception as e:
                    logging.error(f"Failed to get GPU types: {e}")
                    # Add fallback options
                    self.gpu_types.extend([
                        {"name": "V100 GPU (specific)", "value": "V100"},
                        {"name": "A30 GPU (specific)", "value": "A30"},
                        {"name": "A100 GPU (specific)", "value": "A100"}
                    ])
            else:
                # Add fallback options
                self.gpu_types.extend([
                    {"name": "V100 GPU (specific)", "value": "V100"},
                    {"name": "A30 GPU (specific)", "value": "A30"},
                    {"name": "A100 GPU (specific)", "value": "A100"}
                ])
            
            # Update GPU combobox
            self.update_gpu_combobox()
        except Exception as e:
            logging.error(f"Failed to fetch GPU types: {e}")
    
    def update_gpu_combobox(self):
        """Update GPU type combo box"""
        if hasattr(self, 'gpu_combo'):
            self.gpu_combo.clear()
            
            for gpu_type in self.gpu_types:
                self.gpu_combo.addItem(gpu_type["name"], gpu_type["value"])
    
    def on_account_changed(self, index):
        """Triggered when account selection changes"""
        # Check if a valid account is selected
        if index > 0 and self.account_combo.currentData():
            account = self.account_combo.currentData()
            
            # Check if account name contains GPU keyword
            is_gpu_account = account and "gpu" in account.lower()
            
            # If it's a GPU account
            if is_gpu_account:
                # Find "Any GPU" option index
                any_gpu_index = -1
                for i in range(self.gpu_combo.count()):
                    if self.gpu_combo.itemData(i) == "":  # Empty string means any GPU
                        any_gpu_index = i
                        break
                
                # If found, select it as recommended option
                if any_gpu_index >= 0:
                    self.gpu_combo.setCurrentIndex(any_gpu_index)
                
                # Set status message with recommendation
                self.statusLabel.setText("GPU account detected - GPU resources recommended")
            else:
                # Non-GPU account
                # Default to "No GPU" option
                no_gpu_index = -1
                for i in range(self.gpu_combo.count()):
                    if self.gpu_combo.itemData(i) is None:  # None means no GPU
                        no_gpu_index = i
                        break
                
                # If found, select it
                if no_gpu_index >= 0:
                    self.gpu_combo.setCurrentIndex(no_gpu_index)
                
                # Clear status message
                self.statusLabel.setText("Ready")
    
    def on_gpu_changed(self, index):
        """Triggered when GPU selection changes"""
        if index >= 0:
            gpu_type = self.gpu_combo.currentData()
            
            # Check if account name contains GPU keyword
            is_gpu_account = self.account_combo.currentData() and "gpu" in self.account_combo.currentData().lower()
            is_requesting_gpu = gpu_type is not None  # None means no GPU
            
            # If it's a GPU account but not selecting GPU, show warning
            if is_gpu_account and not is_requesting_gpu:
                self.statusLabel.setText("Warning: GPU account should use GPU resources")
            # If selecting GPU but not a GPU account
            elif is_requesting_gpu and not is_gpu_account:
                self.statusLabel.setText("Warning: GPU resources require GPU account")
            else:
                self.statusLabel.setText("Ready")
    
    def initUI(self):
        """Initialize UI components"""
        layout = QVBoxLayout(self)
        
        # Job configuration tabs
        tab_widget = QTabWidget()
        
        # Combined settings tab
        settings_tab = QWidget()
        settings_layout = QFormLayout(settings_tab)
        
        # Job name
        self.job_name = QLineEdit()
        self.job_name.setText("my_job")
        settings_layout.addRow("Job Name:", self.job_name)
        
        # Partition selection
        self.partition = QComboBox()
        if self.partitions:
            for p in self.partitions:
                self.partition.addItem(p['name'], p)
        else:
            self.partition.addItem("default")
        settings_layout.addRow("Partition:", self.partition)
        
        # Account selection
        self.account_combo = QComboBox()
        # Add empty option
        self.account_combo.addItem("Please select an account", None)
        # Add account options
        if self.accounts:
            for account in self.accounts:
                account_text = f"{account['name']} (Available: {account['available']})"
                if account.get('is_personal', False):
                    account_text += " (Personal)"
                self.account_combo.addItem(account_text, account['name'])
        # Connect account change signal
        self.account_combo.currentIndexChanged.connect(self.on_account_changed)
        settings_layout.addRow("Account:", self.account_combo)
        
        # Number of nodes
        self.nodes = QSpinBox()
        self.nodes.setMinimum(1)
        self.nodes.setMaximum(100)
        self.nodes.setValue(1)
        settings_layout.addRow("Nodes:", self.nodes)
        
        # Number of CPU cores
        self.cpus = QSpinBox()
        self.cpus.setMinimum(1)
        self.cpus.setMaximum(128)
        self.cpus.setValue(1)
        settings_layout.addRow("CPU Cores:", self.cpus)
        
        # Memory requirement
        self.memory = QLineEdit()
        self.memory.setText("1G")
        settings_layout.addRow("Memory Requirement:", self.memory)
        
        # GPU type selection
        self.gpu_combo = QComboBox()
        self.gpu_combo.addItem("Loading GPU types...", None)
        self.gpu_combo.currentIndexChanged.connect(self.on_gpu_changed)
        settings_layout.addRow("GPU Type:", self.gpu_combo)
        
        # Add a separator
        separator = QFrame()
        separator.setFrameShape(QFrame.HLine)
        separator.setFrameShadow(QFrame.Sunken)
        settings_layout.addRow(separator)
        
        # Runtime limit
        self.time_limit = QLineEdit()
        self.time_limit.setText("1:00:00")  # 1 hour
        settings_layout.addRow("Time Limit:", self.time_limit)
        
        # Output file
        self.output_file = QLineEdit()
        self.output_file.setText("slurm-%j.out")
        settings_layout.addRow("Output File:", self.output_file)
        
        # Email notification - moved from advanced tab
        self.email = QLineEdit()
        settings_layout.addRow("Email Address:", self.email)
        
        # Notification type - moved from advanced tab
        self.email_type = QComboBox()
        self.email_type.addItems(["NONE", "BEGIN", "END", "FAIL", "ALL"])
        settings_layout.addRow("Notification Type:", self.email_type)
        
        # Add settings tab
        tab_widget.addTab(settings_tab, "Job Settings")
        
        # Script editor tab
        script_tab = QWidget()
        script_layout = QVBoxLayout(script_tab)
        
        # Add info label
        info_label = QLabel("Edit job script below:")
        script_layout.addWidget(info_label)
        
        # Script editor
        self.script_editor = QTextEdit()
        self.script_editor.setFont(QFont("Courier New", 10))
        
        # Set default script template
        default_script = """#!/bin/bash
#SBATCH --job-name={job_name}
#SBATCH --partition={partition}
#SBATCH --nodes={nodes}
#SBATCH --ntasks-per-node={cpus}
#SBATCH --mem={memory}
#SBATCH --time={time_limit}
#SBATCH --output={output_file}
{email_settings}
{gpu_settings}
{account_settings}

# Load modules
module load python/3.9.0

# Print current working directory
echo "Current working directory: $PWD"
echo "Current node: $(hostname)"

# Add your commands here
echo "Hello, Slurm!"
sleep 10
echo "Job complete"
"""
        self.script_editor.setText(default_script)
        script_layout.addWidget(self.script_editor)
        
        # Script template buttons
        template_layout = QHBoxLayout()
        update_template_btn = QPushButton("Update Script Template")
        update_template_btn.clicked.connect(self.update_script_template)
        template_layout.addWidget(update_template_btn)
        
        # Save script button
        save_script_btn = QPushButton("Save Script Locally")
        save_script_btn.clicked.connect(self.save_script)
        template_layout.addWidget(save_script_btn)
        
        # Load script button
        load_script_btn = QPushButton("Load Script from Local")
        load_script_btn.clicked.connect(self.load_script)
        template_layout.addWidget(load_script_btn)
        
        script_layout.addLayout(template_layout)
        
        # Add script tab
        tab_widget.addTab(script_tab, "Script Editor")
        
        # Add tab widget to main layout
        layout.addWidget(tab_widget)
        
        # Set "Job Settings" as default selected
        tab_widget.setCurrentIndex(0)
        
        # Add buttons
        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)
        
        # Add status label
        self.statusLabel = QLabel("Ready")
        layout.addWidget(self.statusLabel)
        
        # Initial update of script template
        self.update_script_template()
    
    def update_script_template(self):
        """Update script template based on settings"""
        # Get setting values
        job_name = self.job_name.text()
        partition = self.partition.currentText()
        nodes = self.nodes.value()
        cpus = self.cpus.value()
        memory = self.memory.text()
        time_limit = self.time_limit.text()
        output_file = self.output_file.text()
        account = self.account_combo.currentData()
        gpu_type = self.gpu_combo.currentData()
        
        # Email settings
        email_settings = ""
        if self.email.text():
            email_settings = f"#SBATCH --mail-user={self.email.text()}\n#SBATCH --mail-type={self.email_type.currentText()}"
        
        # GPU settings
        gpu_settings = ""
        if gpu_type is not None:  # None means no GPU
            if gpu_type == "":  # Empty string means any GPU
                gpu_settings = f"#SBATCH --gres=gpu:1"
            else:  # Specific GPU type
                gpu_settings = f"#SBATCH --gres=gpu:{gpu_type}:1"
        
        # Account settings
        account_settings = ""
        if account:
            account_settings = f"#SBATCH --account={account}"
        
        # Get current script content
        current_script = self.script_editor.toPlainText()
        
        # Only replace SBATCH directives in script header
        header_end = current_script.find("# Load modules")
        if header_end > 0:
            header = f"""#!/bin/bash
#SBATCH --job-name={job_name}
#SBATCH --partition={partition}
#SBATCH --nodes={nodes}
#SBATCH --ntasks-per-node={cpus}
#SBATCH --mem={memory}
#SBATCH --time={time_limit}
#SBATCH --output={output_file}
{email_settings}
{gpu_settings}
{account_settings}
"""
            new_script = header + current_script[header_end:]
            self.script_editor.setText(new_script)
        else:
            # If marker not found, retain user's entire content
            pass
    
    def save_script(self):
        """Save script to local file"""
        filename, _ = QFileDialog.getSaveFileName(
            self, "Save Script", "", "Shell Script (*.sh);;All Files (*)"
        )
        if filename:
            with open(filename, 'w') as f:
                f.write(self.script_editor.toPlainText())
            QMessageBox.information(self, "Success", f"Script saved to {filename}")
    
    def load_script(self):
        """Load script from local file"""
        filename, _ = QFileDialog.getOpenFileName(
            self, "Load Script", "", "Shell Script (*.sh);;All Files (*)"
        )
        if filename:
            with open(filename, 'r') as f:
                self.script_editor.setText(f.read())
            QMessageBox.information(self, "Success", f"Script loaded from {filename}")
    
    def get_script_content(self):
        """Get script content"""
        return self.script_editor.toPlainText()
    
    def accept(self):
        """Validate before accepting dialog"""
        # Validate if account is selected
        if self.account_combo.currentData() is None:
            QMessageBox.warning(self, "Validation Failed", "Please select an account")
            return
            
        # Get GPU and account information for validation
        gpu_type = self.gpu_combo.currentData()
        account = self.account_combo.currentData()
        
        # Validate GPU and account constraints
        is_gpu_account = account and "gpu" in account.lower()
        is_requesting_gpu = gpu_type is not None  # None means no GPU
        
        # Using GPU but not a GPU account
        if is_requesting_gpu and not is_gpu_account:
            QMessageBox.warning(self, "Validation Failed", "Using GPU resources requires an account with GPU keyword")
            return
        
        # Using GPU account but not selecting GPU
        if is_gpu_account and not is_requesting_gpu:
            QMessageBox.warning(self, "Validation Failed", "Using GPU account requires selecting GPU resources")
            return
        
        # Call parent method to accept dialog
        super().accept()


class JobDetailDialog(QDialog):
    """Job Detail Dialog"""
    
    def __init__(self, parent=None, job=None, job_details=None):
        super().__init__(parent)
        self.setWindowTitle("Job Details")
        self.resize(600, 400)
        
        self.job = job
        self.job_details = job_details
        
        # Initialize UI
        self.initUI()
    
    def initUI(self):
        """Initialize UI components"""
        layout = QVBoxLayout(self)
        
        # Basic information section
        if self.job:
            basic_info = QGroupBox("Basic Information")
            basic_layout = QFormLayout(basic_info)
            
            basic_layout.addRow("Job ID:", QLabel(self.job.get('id', 'N/A')))
            basic_layout.addRow("Job Name:", QLabel(self.job.get('name', 'N/A')))
            basic_layout.addRow("State:", QLabel(self.job.get('state', 'N/A')))
            basic_layout.addRow("Run Time:", QLabel(self.job.get('time', 'N/A')))
            basic_layout.addRow("Time Limit:", QLabel(self.job.get('time_limit', 'N/A')))
            basic_layout.addRow("Nodes:", QLabel(self.job.get('nodes', 'N/A')))
            basic_layout.addRow("CPUs:", QLabel(self.job.get('cpus', 'N/A')))
            
            layout.addWidget(basic_info)
        
        # Detailed information section
        if self.job_details:
            detail_info = QGroupBox("Detailed Information")
            detail_layout = QFormLayout(detail_info)
            
            # Add all detailed information
            for key, value in self.job_details.items():
                detail_layout.addRow(f"{key}:", QLabel(str(value)))
            
            layout.addWidget(detail_info)
        else:
            layout.addWidget(QLabel("Unable to retrieve detailed information"))
        
        # Add buttons
        button_box = QDialogButtonBox(QDialogButtonBox.Close)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)


class TaskManagerWidget(QWidget):
    """Task Management Component"""
    
    def __init__(self, parent=None, username=None):
        super().__init__(parent)
        
        # User information
        self.username = username
        self.slurm_manager = None
        self.balance_manager = None
        
        # Get SSH key path
        self.init_slurm_manager()
        
        # Initialize UI
        self.initUI()
        
        # Timed refresh
        self.refresh_timer = QTimer(self)
        self.refresh_timer.timeout.connect(self.refresh_jobs)
        self.refresh_timer.start(120000)  # Refresh every 2 minutes (120 seconds)
        
        # Last update time
        self.last_update_time = time.time()
        
        # 添加定时器检查更新时间
        self.update_check_timer = QTimer(self)
        self.update_check_timer.timeout.connect(self.check_update_time)
        self.update_check_timer.start(1000)  # 每秒检查一次
        
        # Load job list
        self.refresh_jobs()
    
    def init_slurm_manager(self):
        """Initialize Slurm manager"""
        if not self.username:
            QMessageBox.warning(self, "Warning", "Username not set, unable to manage tasks")
            return
        
        # Get SSH key path
        users = get_all_existing_users()
        key_path = None
        
        for user in users:
            if user['username'] == self.username:
                key_path = user['key_path']
                break
        
        if not key_path:
            QMessageBox.warning(self, "Warning", f"SSH key for user {self.username} not found")
            return
        
        # Create Slurm manager
        self.slurm_manager = SlurmManager(
            hostname=HPC_SERVER,
            username=self.username,
            key_path=key_path
        )
        
        # Connect signals
        self.slurm_manager.error_occurred.connect(self.show_error)
        self.slurm_manager.job_submitted.connect(self.on_job_submitted)
        self.slurm_manager.job_canceled.connect(self.on_job_canceled)
        
        # Create balance manager
        from modules.balance import BalanceManager
        self.balance_manager = BalanceManager(
            hostname=HPC_SERVER,
            username=self.username,
            key_path=key_path
        )
    
    def initUI(self):
        """Initialize UI components"""
        main_layout = QVBoxLayout(self)
        
        # Top control bar
        control_layout = QHBoxLayout()
        
        # New job button
        submit_btn = QPushButton("Submit New Job")
        submit_btn.clicked.connect(self.show_job_submission_dialog)
        control_layout.addWidget(submit_btn)
        
        # Auto-refresh checkbox
        self.auto_refresh = QCheckBox("Auto Refresh")
        self.auto_refresh.setChecked(True)
        self.auto_refresh.stateChanged.connect(self.toggle_auto_refresh)
        control_layout.addWidget(self.auto_refresh)
        
        # Status filter
        self.status_filter = QComboBox()
        self.status_filter.addItems(["All", "Running", "Pending", "Completed", "Cancelled", "Failed"])
        self.status_filter.currentTextChanged.connect(self.apply_filter)
        control_layout.addWidget(QLabel("Status Filter:"))
        control_layout.addWidget(self.status_filter)
        
        control_layout.addStretch()
        
        # Add control bar to main layout
        main_layout.addLayout(control_layout)
        
        # Job table
        self.jobs_table = QTableWidget()
        self.jobs_table.setColumnCount(8)
        self.jobs_table.setHorizontalHeaderLabels([
            "Job ID", "Job Name", "State", "Run Time", "Time Limit", "Nodes", "CPUs", "Remarks"
        ])
        self.jobs_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.jobs_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.jobs_table.setAlternatingRowColors(True)
        self.jobs_table.horizontalHeader().setStretchLastSection(True)
        self.jobs_table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.jobs_table.customContextMenuRequested.connect(self.show_context_menu)
        self.jobs_table.doubleClicked.connect(self.show_job_details)
        
        # Adjust column width
        self.jobs_table.setColumnWidth(0, 80)   # ID
        self.jobs_table.setColumnWidth(1, 180)  # Name
        self.jobs_table.setColumnWidth(2, 80)   # State
        self.jobs_table.setColumnWidth(3, 80)   # Run Time
        self.jobs_table.setColumnWidth(4, 80)   # Time Limit
        self.jobs_table.setColumnWidth(5, 60)   # Nodes
        self.jobs_table.setColumnWidth(6, 60)   # CPUs
        
        # Add table to main layout
        main_layout.addWidget(self.jobs_table)
        
        # Bottom status bar
        status_layout = QHBoxLayout()
        
        self.status_label = QLabel("Ready")
        status_layout.addWidget(self.status_label)
        
        # 添加刷新按钮到底部状态栏
        refresh_btn = QPushButton("Refresh Job List")
        refresh_btn.clicked.connect(self.refresh_jobs)
        status_layout.addWidget(refresh_btn)
        
        status_layout.addStretch()
        
        self.job_count_label = QLabel("Number of Jobs: 0")
        status_layout.addWidget(self.job_count_label)
        
        # Add status bar to main layout
        main_layout.addLayout(status_layout)
    
    @pyqtSlot()
    def refresh_jobs(self):
        """Refresh job list"""
        if not self.slurm_manager:
            self.status_label.setText("Slurm manager not initialized")
            return
        
        # 记录当前时间作为最后更新时间
        self.last_update_time = time.time()
        
        # 重置状态标签样式
        self.status_label.setStyleSheet("")
        self.status_label.setText("Loading job list...")
        
        # Get job list
        jobs = self.slurm_manager.get_jobs()
        
        # Clear table
        self.jobs_table.setRowCount(0)
        
        # Populate table
        for i, job in enumerate(jobs):
            self.jobs_table.insertRow(i)
            
            # Set cell
            self.jobs_table.setItem(i, 0, QTableWidgetItem(job.get('id', 'N/A')))
            self.jobs_table.setItem(i, 1, QTableWidgetItem(job.get('name', 'N/A')))
            
            # Set color based on state
            state_item = QTableWidgetItem(job.get('state', 'N/A'))
            state = job.get('state', '').lower()
            if state == 'running':
                state_item.setForeground(QColor('green'))
            elif state == 'pending':
                state_item.setForeground(QColor('blue'))
            elif state in ['failed', 'timeout', 'cancelled']:
                state_item.setForeground(QColor('red'))
            elif state == 'completed':
                state_item.setForeground(QColor('darkgreen'))
            
            self.jobs_table.setItem(i, 2, state_item)
            self.jobs_table.setItem(i, 3, QTableWidgetItem(job.get('time', 'N/A')))
            self.jobs_table.setItem(i, 4, QTableWidgetItem(job.get('time_limit', 'N/A')))
            self.jobs_table.setItem(i, 5, QTableWidgetItem(job.get('nodes', 'N/A')))
            self.jobs_table.setItem(i, 6, QTableWidgetItem(job.get('cpus', 'N/A')))
            self.jobs_table.setItem(i, 7, QTableWidgetItem(job.get('reason', 'N/A')))
        
        # Update job count
        self.job_count_label.setText(f"Number of Jobs: {len(jobs)}")
        
        # Apply filter
        self.apply_filter()
        
        # Update status
        self.status_label.setText(f"Job list updated ({time.strftime('%H:%M:%S')})")
        
        # 设置定时器，检查上次更新时间
        self.check_update_time()
    
    def apply_filter(self):
        """Apply status filter"""
        filter_text = self.status_filter.currentText()
        
        # Map status text to job status
        status_map = {
            "All": None,
            "Running": "RUNNING",
            "Pending": "PENDING",
            "Completed": "COMPLETED",
            "Cancelled": "CANCELLED",
            "Failed": "FAILED"
        }
        
        filter_status = status_map.get(filter_text)
        
        # Apply filter
        for i in range(self.jobs_table.rowCount()):
            state_item = self.jobs_table.item(i, 2)
            if state_item:
                state = state_item.text()
                if filter_status is None or state == filter_status:
                    self.jobs_table.setRowHidden(i, False)
                else:
                    self.jobs_table.setRowHidden(i, True)
    
    def toggle_auto_refresh(self, state):
        """Toggle auto-refresh"""
        if state == Qt.Checked:
            self.refresh_timer.start(120000)
        else:
            self.refresh_timer.stop()
    
    def show_job_submission_dialog(self):
        """Show job submission dialog"""
        if not self.slurm_manager:
            QMessageBox.warning(self, "Warning", "Slurm manager not initialized")
            return
        
        # Get partition information
        partitions = self.slurm_manager.get_partition_info()
        
        # Get account information
        accounts = []
        if self.balance_manager:
            try:
                # Get account information
                balance_data = self.balance_manager.get_user_balance()
                if balance_data and 'accounts' in balance_data:
                    for account in balance_data['accounts']:
                        accounts.append({
                            'name': account['name'],
                            'is_personal': account.get('is_personal', False),
                            'available': account.get('available', 0)
                        })
            except Exception as e:
                logging.error(f"Failed to get account information: {e}")
                self.show_error(f"Failed to get account information: {str(e)}")
        
        # Show submission dialog
        dialog = JobSubmissionDialog(self, partitions, accounts, self.username)
        result = dialog.exec_()
        
        if result == QDialog.Accepted:
            # Get script content
            script_content = dialog.get_script_content()
            
            # Check if account is selected
            if dialog.account_combo.currentData() is None:
                QMessageBox.warning(self, "Submission Failed", "Please select an account")
                return
            
            # Submit job
            job_id = self.slurm_manager.submit_job(script_content)
            if job_id:
                QMessageBox.information(self, "Success", f"Job submitted, ID: {job_id}")
                # Refresh job list
                self.refresh_jobs()
            else:
                QMessageBox.warning(self, "Submission Failed", "Job submission failed, please check the script")
    
    def show_job_details(self):
        """Show job details"""
        selected_rows = self.jobs_table.selectionModel().selectedRows()
        if not selected_rows:
            return
        
        # Get job ID of selected row
        row = selected_rows[0].row()
        job_id = self.jobs_table.item(row, 0).text()
        
        # Construct job object
        job = {
            'id': self.jobs_table.item(row, 0).text(),
            'name': self.jobs_table.item(row, 1).text(),
            'state': self.jobs_table.item(row, 2).text(),
            'time': self.jobs_table.item(row, 3).text(),
            'time_limit': self.jobs_table.item(row, 4).text(),
            'nodes': self.jobs_table.item(row, 5).text(),
            'cpus': self.jobs_table.item(row, 6).text(),
            'reason': self.jobs_table.item(row, 7).text()
        }
        
        # Get job details
        job_details = self.slurm_manager.get_job_details(job_id)
        
        # Show detail dialog
        dialog = JobDetailDialog(self, job, job_details)
        dialog.exec_()
    
    def show_context_menu(self, position):
        """Show context menu"""
        selected_rows = self.jobs_table.selectionModel().selectedRows()
        if not selected_rows:
            return
        
        # Create context menu
        menu = QMenu(self)
        
        # Add menu items
        details_action = menu.addAction("Job Details")
        cancel_action = menu.addAction("Cancel Job")
        
        # Execute menu
        action = menu.exec_(self.jobs_table.mapToGlobal(position))
        
        # Handle menu actions
        if action == details_action:
            self.show_job_details()
        elif action == cancel_action:
            self.cancel_selected_job()
    
    def cancel_selected_job(self):
        """Cancel selected job"""
        selected_rows = self.jobs_table.selectionModel().selectedRows()
        if not selected_rows:
            return
        
        # Get job ID of selected row
        row = selected_rows[0].row()
        job_id = self.jobs_table.item(row, 0).text()
        job_name = self.jobs_table.item(row, 1).text()
        
        # Confirm cancellation
        confirm = QMessageBox.question(
            self,
            "Confirm Cancellation",
            f"Are you sure you want to cancel job {job_id} ({job_name})?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        
        if confirm == QMessageBox.Yes:
            # Cancel job
            success = self.slurm_manager.cancel_job(job_id)
            if success:
                QMessageBox.information(self, "Success", f"Job {job_id} cancelled")
                # Refresh job list
                self.refresh_jobs()
            else:
                QMessageBox.warning(self, "Failed", f"Failed to cancel job {job_id}")
    
    @pyqtSlot(str)
    def show_error(self, message):
        """Show error message"""
        QMessageBox.warning(self, "Error", message)
    
    @pyqtSlot(str)
    def on_job_submitted(self, job_id):
        """Slot function for successful job submission"""
        self.status_label.setText(f"Job submitted: {job_id}")
    
    @pyqtSlot(str)
    def on_job_canceled(self, job_id):
        """Slot function for successful job cancellation"""
        self.status_label.setText(f"Job cancelled: {job_id}")

    def check_update_time(self):
        """Check if the last update time has exceeded 10 seconds"""
        current_time = time.time()
        elapsed_time = current_time - self.last_update_time
        if elapsed_time > 10:
            self.status_label.setStyleSheet("QLabel { color: #FFA500; font-weight: bold; }")
        else:
            self.status_label.setStyleSheet("") 