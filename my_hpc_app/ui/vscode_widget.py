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

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger('VSCodeWidget')

class ThreadSafeHelper(QObject):
    """Helper class for thread-safe UI updates"""
    update_status = pyqtSignal(str)
    update_job_info_signal = pyqtSignal(dict)
    show_config_signal = pyqtSignal(dict)
    show_error_signal = pyqtSignal(str)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent = parent

class VSCodeWidget(QWidget):
    """VSCode remote configuration component, provides VSCode server setup and connection functionality"""
    
    def __init__(self, parent=None, username=None):
        super().__init__(parent)
        
        # User information
        self.username = username
        self.vscode_manager = None
        self.balance_manager = None
        self.node_manager = None
        
        # Thread-safe helper object
        self.thread_helper = ThreadSafeHelper(self)
        self.thread_helper.update_status.connect(self.update_status_safe)
        self.thread_helper.update_job_info_signal.connect(self.update_job_info)
        self.thread_helper.show_config_signal.connect(self.safe_show_config)
        self.thread_helper.show_error_signal.connect(self.show_error)
        
        # Account information
        self.accounts = []
        
        # GPU type information
        self.gpu_types = []
        
        # Current job information
        self.current_job = None
        
        # Initialization complete flag
        self.initialization_complete = False
        
        # Initialize UI
        self.init_ui()
        
        # Use timer to delay initialization of other managers to avoid blocking UI at startup
        QTimer.singleShot(500, self.delayed_init_managers)
    
    def delayed_init_managers(self):
        """Delay initialization of managers to avoid blocking before UI is displayed"""
        try:
            # Register QTextCursor meta type for inter-thread communication
            try:
                from PyQt5.QtCore import qRegisterMetaType
                qRegisterMetaType('QTextCursor')
            except (ImportError, AttributeError):
                logger.warning("Unable to register QTextCursor meta type, may affect multithreading")
            
            # Initialize managers
            self.init_managers()
            
            # Set initialization complete flag
            self.initialization_complete = True
        except Exception as e:
            logger.error(f"Failed to delay initialize managers: {e}")
            self.status_label.setText(f"Error: Initialization failed - {str(e)}")
    
    def init_managers(self):
        """Initialize VSCode manager and balance manager"""
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
            # Create manager objects in the main thread
            # Create VSCode manager
            self.vscode_manager = VSCodeManager(
                hostname=HPC_SERVER,
                username=self.username,
                key_path=key_path
            )
            
            # Connect signals
            self.vscode_manager.vscode_job_submitted.connect(self.update_job_info)
            self.vscode_manager.vscode_job_status_updated.connect(self.update_job_status)
            self.vscode_manager.vscode_config_ready.connect(self.show_config)
            self.vscode_manager.error_occurred.connect(self.show_error)
            
            # Connect SSH config signals
            self.vscode_manager.ssh_config_added.connect(self.on_ssh_config_added)
            self.vscode_manager.ssh_config_removed.connect(self.on_ssh_config_removed)
            
            # Create balance manager to get account information
            self.balance_manager = BalanceManager(
                hostname=HPC_SERVER,
                username=self.username,
                key_path=key_path
            )
            
            # Create node status manager to get GPU type information
            self.node_manager = NodeStatusManager(
                hostname=HPC_SERVER,
                username=self.username,
                key_path=key_path
            )
            
            # Update status
            self.status_label.setText("Managers initialized, ready")
            
            # Initialize connections and data in a thread-safe manner
            # Get account information in a background thread
            threading.Thread(target=self._init_background_data, daemon=True).start()
        except Exception as e:
            self.status_label.setText(f"Error: Failed to initialize managers - {str(e)}")
    
    def _init_background_data(self):
        """Initialize data in a background thread"""
        try:
            # Use delay to give UI time to fully initialize
            time.sleep(1)
            
            # First get accounts and GPU types, which are less likely to fail
            try:
                self.fetch_accounts()
            except Exception as e:
                logger.error(f"Failed to get account information: {e}")
                self.thread_helper.show_error_signal.emit(f"Failed to get account information: {str(e)}")
            
            try:
                self.fetch_gpu_types()
            except Exception as e:
                logger.error(f"Failed to get GPU types: {e}")
                self.thread_helper.show_error_signal.emit(f"Failed to get GPU types: {str(e)}")
            
            # Delay checking running jobs, as this may be a source of crashes
            time.sleep(1.5)
            
            # Finally check for running VSCode jobs (this part may cause issues)
            try:
                # Check jobs in a thread-safe manner
                self.safe_check_running_jobs()
            except Exception as e:
                logger.error(f"Failed to check running VSCode jobs: {e}")
                self.thread_helper.show_error_signal.emit(f"Failed to check running VSCode jobs: {str(e)}")
        except Exception as e:
            logger.error(f"Failed to initialize background data: {e}")
            self.thread_helper.show_error_signal.emit(f"Failed to initialize background data: {str(e)}")
    
    def fetch_accounts(self):
        """Get list of available accounts for the user"""
        try:
            balance_data = self.balance_manager.get_user_balance()
            if balance_data and 'accounts' in balance_data:
                self.accounts = []
                
                # Add personal and lab accounts
                for account in balance_data['accounts']:
                    self.accounts.append({
                        'name': account['name'],
                        'is_personal': account['is_personal'],
                        'available': account['available']
                    })
                
                # Update account combo box
                self.update_account_combobox()
        except Exception as e:
            logger.error(f"Failed to get account information: {str(e)}")
            self.show_error(f"Failed to get account information: {str(e)}")
    
    def update_account_combobox(self):
        """Update account combo box"""
        self.account_combo.clear()
        
        # Add empty option
        self.account_combo.addItem("Please select an account", None)
        
        for account in self.accounts:
            account_text = f"{account['name']} (Available: {account['available']})"
            if account['is_personal']:
                account_text += " (Personal)"
            self.account_combo.addItem(account_text, account['name'])
        
        # Default to no account selected, ensure user must actively select
        self.account_combo.setCurrentIndex(0)
        self.submit_btn.setEnabled(False)
    
    def fetch_gpu_types(self):
        """Get available GPU types"""
        try:
            # Add default option (no GPU) and generic GPU option
            self.gpu_types = [
                {"name": "No GPU", "value": None},
                {"name": "Any GPU (recommended)", "value": ""}
            ]
            
            # Get GPU partition node information - use specific command to query GPU partition
            if self.node_manager.connect_ssh():
                # Use sinfo command to get GPU partition information
                gpu_cmd = 'sinfo -o "%60N %10c %10m  %30f %10G" -e'
                try:
                    output = self.node_manager.execute_ssh_command(gpu_cmd)
                    logger.info(f"Successfully got GPU partition information")
                    
                    # Parse output to get GPU types
                    gpu_types_set = set()
                    lines = output.strip().split('\n')
                    
                    # Skip header line
                    if len(lines) > 1:
                        for line in lines[1:]:
                            # 查找 gpu: 后面的类型，例如 gpu:V100:1(IDX:0)
                            if "gpu:" in line:
                                gpu_info = line.split("gpu:")[1].split(":")[0]
                                if gpu_info and gpu_info not in ["N/A", ""]:
                                    gpu_types_set.add(gpu_info)
                
                    # Add found GPU types
                    for gpu_type in sorted(gpu_types_set):
                        self.gpu_types.append({
                            "name": f"{gpu_type} GPU (specific)",
                            "value": gpu_type
                        })
                    
                    logger.info(f"Found the following GPU types: {[gpu_type for gpu_type in gpu_types_set]}")
                except Exception as e:
                    logger.error(f"Failed to execute GPU query command: {e}")
                    # Fallback to basic options
                    self.gpu_types.extend([
                        {"name": "V100 GPU (specific)", "value": "V100"},
                        {"name": "A30 GPU (specific)", "value": "A30"},
                        {"name": "A100 GPU (specific)", "value": "A100"}
                    ])
            else:
                logger.error("Unable to connect to SSH server to get GPU information")
                # Fallback to basic options
                self.gpu_types.extend([
                    {"name": "V100 GPU (specific)", "value": "V100"},
                    {"name": "A30 GPU (specific)", "value": "A30"},
                    {"name": "A100 GPU (specific)", "value": "A100"}
                ])
            
            # Update UI in the main thread
            QMetaObject.invokeMethod(self, "update_gpu_combobox", Qt.QueuedConnection)
        except Exception as e:
            logger.error(f"Failed to get GPU types: {e}")
            self.show_error(f"Failed to get GPU types: {str(e)}")
            # Add default options
            self.gpu_types = [
                {"name": "No GPU", "value": None},
                {"name": "Any GPU (recommended)", "value": ""},
                {"name": "V100 GPU (specific)", "value": "V100"},
                {"name": "A30 GPU (specific)", "value": "A30"},
                {"name": "A100 GPU (specific)", "value": "A100"}
            ]
            # Update UI in the main thread
            QMetaObject.invokeMethod(self, "update_gpu_combobox", Qt.QueuedConnection)
    
    @pyqtSlot()
    def update_gpu_combobox(self):
        """Update GPU type combo box"""
        self.gpu_combo.clear()
        
        for gpu_type in self.gpu_types:
            self.gpu_combo.addItem(gpu_type["name"], gpu_type["value"])
        
        # Connect GPU selection change signal
        self.gpu_combo.currentIndexChanged.connect(self.on_gpu_changed)
    
    def safe_check_running_jobs(self):
        """Thread-safe check of running jobs"""
        try:
            # Getting job list may take time and may throw exceptions
            jobs = self.vscode_manager.get_running_vscode_jobs()
            
            if not jobs:
                logger.info("No running VSCode jobs found")
                return
            
            # Find the first RUNNING status job
            running_job = next((job for job in jobs if job['status'] == 'RUNNING'), None)
            if not running_job:
                logger.info("No VSCode jobs in RUNNING status found")
                return
            
            # Get job details
            job_id = running_job['job_id']
            logger.info(f"Found running VSCode job: {job_id}")
            
            # Update status using signal (thread-safe)
            self.thread_helper.update_status.emit(f"Found running VSCode job: {job_id}")
            
            # Create job info dictionary
            job_info = {
                'job_id': job_id,
                'status': 'RUNNING',
                'node': running_job.get('node', 'Unknown'),
                'hostname': running_job.get('node', 'Unknown')
            }
            
            # Set current job information
            self.current_job = job_info
            
            # Update job information using signal (thread-safe)
            self.thread_helper.update_job_info_signal.emit(job_info)
            
            # Add a short delay before parsing configuration information
            time.sleep(0.5)
            
            # Try to get configuration information
            try:
                config_info = self.vscode_manager._parse_vscode_config(job_id)
                if config_info:
                    # Update job information
                    job_info['config'] = config_info
                    job_info['hostname'] = config_info.get('hostname')
                    job_info['port'] = config_info.get('port')
                    
                    # Update self.current_job to complete information
                    self.current_job = job_info.copy()
                    
                    # Show configuration using signal (thread-safe)
                    self.thread_helper.show_config_signal.emit(job_info)
            except Exception as e:
                logger.error(f"Failed to parse existing job configuration: {e}")
                # Even if unable to parse configuration, ensure UI reflects job is running
                self.thread_helper.update_status.emit(f"Detected running VSCode job: {job_id} (unable to get full configuration)")
        except Exception as e:
            logger.error(f"Failed to safely check running jobs: {e}")
            # Even if check fails, should not crash the program
    
    @pyqtSlot(dict)
    def safe_show_config(self, config_info):
        """Thread-safe method to display configuration information, called in the main thread"""
        try:
            if not config_info or 'config' not in config_info:
                return
            
            config = config_info['config']
            job_id = config_info.get('job_id', 'N/A')
            
            # Build configuration information text - simplify and direct connection instructions
            config_text = "## VSCode connection ready ##\n\n"
            
            # Add direct VSCode connection instructions
            config_text += "1. SSH configuration has been automatically written to ~/.ssh/config\n\n"
            
            # Add VSCode connection instructions
            config_text += "2. Connect to remote host in VSCode:\n\n"
            config_text += f"   - Open VSCode\n"
            config_text += f"   - Click the remote connection icon (><) in the lower left corner or press F1 and enter 'Remote-SSH: Connect to Host...'\n"
            config_text += f"   - Select \"{config['hostname']}\" from the list\n\n"
            
            # Connection information
            config_text += f"Host: {config['hostname']}\n"
            config_text += f"User: {config['user']}\n"
            config_text += f"Port: {config['port']}\n\n"
            
            # Add job information
            config_text += f"Job ID: {job_id}\n"
            
            # Add closing instructions
            config_text += "\n3. Close steps after use:\n\n"
            config_text += "   - Close the window in VSCode\n"
            config_text += f"   - Click the \"Cancel Job\" button in this application\n"
            
            # Update configuration text
            self.config_text.setText(config_text)
            
            # Switch to configuration tab
            tabs = self.findChild(QTabWidget)
            if tabs:
                tabs.setCurrentWidget(self.config_widget)
            
            # Update status label
            self.status_label.setText(f"VSCode connection ready - Job {job_id}")
        except Exception as e:
            logger.error(f"Error displaying configuration information: {e}")
    
    @pyqtSlot(dict)
    def show_config(self, config_info):
        """Display VSCode configuration information - ensure called in the main thread"""
        try:
            # Directly call safe_show_config instead of using invokeMethod
            self.safe_show_config(config_info)
        except Exception as e:
            logger.error(f"Error displaying configuration information: {e}")
    
    def init_ui(self):
        """Initialize UI components"""
        main_layout = QVBoxLayout(self)
        
        # Add title
        title_label = QLabel("VSCode Remote Configuration")
        title_label.setFont(QFont('Arial', 16, QFont.Bold))
        main_layout.addWidget(title_label)
        
        # Create splitter to divide page into upper and lower parts
        splitter = QSplitter(Qt.Vertical)
        
        # Upper part: configuration panel
        config_widget = QWidget()
        config_layout = QVBoxLayout(config_widget)
        
        # Create resource configuration group
        resources_group = QGroupBox("Resource Configuration")
        resources_layout = QGridLayout(resources_group)
        
        # Number of CPUs
        cpu_label = QLabel("Number of CPUs:")
        self.cpu_spinbox = QSpinBox()
        self.cpu_spinbox.setMinimum(1)
        self.cpu_spinbox.setMaximum(128)
        self.cpu_spinbox.setValue(2)  # Default value changed to 2
        resources_layout.addWidget(cpu_label, 0, 0)
        resources_layout.addWidget(self.cpu_spinbox, 0, 1)
        
        # Memory size
        memory_label = QLabel("Memory Size:")
        self.memory_combo = QComboBox()
        for mem in ["4G", "8G", "16G", "32G", "64G", "128G"]:
            self.memory_combo.addItem(mem)
        self.memory_combo.setCurrentText("4G")  # Default value changed to 4G
        resources_layout.addWidget(memory_label, 1, 0)
        resources_layout.addWidget(self.memory_combo, 1, 1)
        
        # GPU type
        gpu_label = QLabel("GPU Type:")
        self.gpu_combo = QComboBox()
        self.gpu_combo.addItem("Loading...", None)
        resources_layout.addWidget(gpu_label, 2, 0)
        resources_layout.addWidget(self.gpu_combo, 2, 1)
        
        # Add resource configuration group to configuration layout
        config_layout.addWidget(resources_group)
        
        # Create job configuration group
        job_group = QGroupBox("Job Configuration")
        job_layout = QGridLayout(job_group)
        
        # Account
        account_label = QLabel("Account:")
        self.account_combo = QComboBox()
        self.account_combo.addItem("Loading...", "")
        self.account_combo.currentIndexChanged.connect(self.on_account_changed)
        job_layout.addWidget(account_label, 0, 0)
        job_layout.addWidget(self.account_combo, 0, 1)
        
        # Job time limit
        time_label = QLabel("Run Time:")
        self.time_combo = QComboBox()
        for time_limit in ["1:00:00", "2:00:00", "4:00:00", "8:00:00", "12:00:00", "24:00:00", "48:00:00"]:
            self.time_combo.addItem(time_limit)
        self.time_combo.setCurrentText("8:00:00")  # Default value changed to 8 hours
        job_layout.addWidget(time_label, 1, 0)
        job_layout.addWidget(self.time_combo, 1, 1)
        
        # Free option
        free_option_label = QLabel("Use Free Resources:")
        self.free_option_check = QComboBox()
        self.free_option_check.addItem("No", False)
        self.free_option_check.addItem("Yes (may be unstable)", True)
        free_option_hint = QLabel("Note: Using free resources still requires selecting an account")
        free_option_hint.setStyleSheet("color: #666; font-size: 10px;")
        job_layout.addWidget(free_option_label, 2, 0)
        job_layout.addWidget(self.free_option_check, 2, 1)
        job_layout.addWidget(free_option_hint, 3, 0, 1, 2)
        
        # Add job configuration group to configuration layout
        config_layout.addWidget(job_group)
        
        # Create control buttons
        button_layout = QHBoxLayout()
        
        # Submit button
        self.submit_btn = QPushButton("Submit VSCode Job")
        self.submit_btn.clicked.connect(self.submit_job)
        self.submit_btn.setEnabled(False)  # Default disabled until account is selected
        button_layout.addWidget(self.submit_btn)
        
        # Cancel button
        self.cancel_btn = QPushButton("Cancel Job")
        self.cancel_btn.clicked.connect(self.cancel_job)
        self.cancel_btn.setEnabled(False)  # Initially disabled
        button_layout.addWidget(self.cancel_btn)
        
        # Add button layout to configuration layout
        config_layout.addLayout(button_layout)
        
        # Add configuration widget to splitter
        splitter.addWidget(config_widget)
        
        # Lower part: result panel
        result_widget = QTabWidget()
        
        # Job information tab
        self.job_info_widget = QWidget()
        job_info_layout = QVBoxLayout(self.job_info_widget)
        
        # Job status information
        self.job_info_text = QTextEdit()
        self.job_info_text.setReadOnly(True)
        self.job_info_text.setPlaceholderText("Job status information will be displayed here after submission")
        job_info_layout.addWidget(self.job_info_text)
        
        # Configuration tab
        self.config_widget = QWidget()
        config_info_layout = QVBoxLayout(self.config_widget)
        
        # Configuration information
        self.config_text = QTextEdit()
        self.config_text.setReadOnly(True)
        self.config_text.setPlaceholderText("VSCode remote connection configuration will be displayed here after job runs")
        config_info_layout.addWidget(self.config_text)
        
        # Add tabs
        result_widget.addTab(self.job_info_widget, "Job Information")
        result_widget.addTab(self.config_widget, "Connection Configuration")
        
        # Add result widget to splitter
        splitter.addWidget(result_widget)
        
        # Set splitter ratio
        splitter.setSizes([300, 500])
        
        # Add splitter to main layout
        main_layout.addWidget(splitter)
        
        # Bottom status bar
        self.status_label = QLabel("Initializing...")
        main_layout.addWidget(self.status_label)
    
    def on_account_changed(self, index):
        """Triggered when account selection changes"""
        # Check if a valid account is selected
        if index > 0 and self.account_combo.currentData():
            account = self.account_combo.currentData()
            self.submit_btn.setEnabled(True)
            
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
                self.status_label.setText("GPU account detected - GPU resources recommended")
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
                self.status_label.setText("Ready")
        else:
            self.submit_btn.setEnabled(False)
    
    @pyqtSlot()
    def submit_job(self):
        """Submit VSCode job"""
        if not self.vscode_manager:
            self.show_error("VSCode manager not initialized, unable to submit job")
            return
        
        # First check if there are any running VSCode jobs
        try:
            running_jobs = self.vscode_manager.get_running_vscode_jobs()
            if running_jobs:
                # Find RUNNING status job
                running_job = next((job for job in running_jobs if job['status'] == 'RUNNING'), None)
                if running_job:
                    job_id = running_job['job_id']
                    # Ask user if they want to cancel the old job
                    confirm = QMessageBox.question(
                        self,
                        "Running Job Found",
                        f"Found running VSCode job (ID: {job_id}), do you want to cancel it and create a new job?",
                        QMessageBox.Yes | QMessageBox.No,
                        QMessageBox.No
                    )
                    
                    if confirm == QMessageBox.Yes:
                        # User chooses to cancel old job
                        self.status_label.setText(f"Cancelling old job {job_id}...")
                        success = self.vscode_manager.cancel_job(job_id)
                        if success:
                            # Ensure configuration information is cleared
                            self.clean_old_ssh_config(job_id)
                            self.status_label.setText(f"Old job cancelled, preparing to create new job")
                        else:
                            self.show_error(f"Unable to cancel old job {job_id}, please cancel manually and try again")
                            return
                    else:
                        # User chooses not to cancel old job
                        self.status_label.setText("Keeping old job, cancelling new job creation")
                        return
        except Exception as e:
            logger.warning(f"Error checking running jobs: {e}")
            # Even if check fails, continue creating new job
        
        # Get resource configuration
        cpus = self.cpu_spinbox.value()
        memory = self.memory_combo.currentText()
        gpu_type = self.gpu_combo.currentData()
        account = self.account_combo.currentData()
        time_limit = self.time_combo.currentText()
        use_free = self.free_option_check.currentData()
        
        # Check if account is selected
        if not account:
            self.show_error("Please select an account")
            return
        
        # Validate GPU and account constraints
        is_gpu_account = account and "gpu" in account.lower()
        is_requesting_gpu = gpu_type is not None  # None means no GPU
        
        # Using GPU but not a GPU account
        if is_requesting_gpu and not is_gpu_account:
            self.show_error("Using GPU resources requires an account with GPU keyword")
            return
        
        # Using GPU account but not selecting GPU
        if is_gpu_account and not is_requesting_gpu:
            self.show_error("Using GPU account requires selecting GPU resources")
            return
        
        # Update status
        self.status_label.setText("Submitting VSCode job...")
        self.submit_btn.setEnabled(False)
        
        # Submit job
        try:
            self.vscode_manager.submit_vscode_job(
                cpus=cpus,
                memory=memory,
                gpu_type=gpu_type,
                account=account,
                time_limit=time_limit,
                use_free=use_free  # Pass option to use free resources
            )
        except Exception as e:
            self.show_error(f"Failed to submit job: {str(e)}")
            self.submit_btn.setEnabled(True)
    
    def clean_old_ssh_config(self, job_id):
        """Clean SSH configuration for specified job"""
        try:
            # Check SSH config file
            ssh_config_file = os.path.expanduser("~/.ssh/config")
            if not os.path.exists(ssh_config_file):
                logger.info(f"SSH config file does not exist: {ssh_config_file}")
                return
            
            # Read current configuration
            with open(ssh_config_file, 'r') as f:
                content = f.read()
            
            # Find configuration block related to specified job
            import re
            pattern = re.compile(rf'# === BEGIN HPC App VSCode Config \(JobID: {job_id}\) ===.*?# === END HPC App VSCode Config \(JobID: {job_id}\) ===', re.DOTALL)
            
            # Check if related configuration exists
            match = pattern.search(content)
            if match:
                # Remove related configuration
                new_content = pattern.sub('', content)
                
                # Write back to file
                with open(ssh_config_file, 'w') as f:
                    f.write(new_content)
                
                logger.info(f"Cleaned SSH configuration for job {job_id}")
                # Notify configuration removed
                if hasattr(self.vscode_manager, 'ssh_config_removed'):
                    self.vscode_manager.ssh_config_removed.emit(job_id)
            else:
                logger.info(f"No SSH configuration found for job {job_id}, no need to clean")
        except Exception as e:
            logger.error(f"Error cleaning SSH configuration: {e}")
    
    @pyqtSlot()
    def cancel_job(self):
        """Cancel current VSCode job"""
        if not self.vscode_manager or not self.current_job:
            self.show_error("No running job, unable to cancel")
            return
        
        job_id = self.current_job.get('job_id')
        if not job_id:
            self.show_error("Job ID does not exist, unable to cancel")
            return
        
        # Update status
        self.status_label.setText(f"Cancelling job {job_id}...")
        
        # Cancel job
        try:
            success = self.vscode_manager.cancel_job(job_id)
            if success:
                # Clean SSH configuration
                self.clean_old_ssh_config(job_id)
                
                self.status_label.setText(f"Job {job_id} cancelled")
                # Update UI
                self.update_job_status({
                    'job_id': job_id,
                    'status': 'CANCELLED'
                })
                # Clear current job information
                self.current_job = None
                # Enable submit button, disable cancel button
                self.submit_btn.setEnabled(True)
                self.cancel_btn.setEnabled(False)
                # Clear configuration information
                self.config_text.clear()
                self.config_text.setPlaceholderText("VSCode remote connection configuration will be displayed here after job runs")
            else:
                self.show_error(f"Failed to cancel job {job_id}")
        except Exception as e:
            self.show_error(f"Failed to cancel job: {str(e)}")
    
    @pyqtSlot(dict)
    def update_job_info(self, job_info):
        """Update job information display"""
        if not job_info:
            return
        
        # Update current job information
        self.current_job = job_info
        
        # Update UI status
        self.cancel_btn.setEnabled(True)
        self.submit_btn.setEnabled(False)
        
        # Build job information text
        info_text = f"Job ID: {job_info.get('job_id', 'N/A')}\n"
        info_text += f"Status: {job_info.get('status', 'N/A')}\n"
        
        if 'node' in job_info and job_info['node']:
            info_text += f"Node: {job_info['node']}\n"
        
        info_text += "\nResource Configuration:\n"
        info_text += f"Number of CPUs: {job_info.get('cpus', 'N/A')}\n"
        info_text += f"Memory Size: {job_info.get('memory', 'N/A')}\n"
        
        if job_info.get('gpu_type'):
            info_text += f"GPU Type: {job_info['gpu_type']}\n"
        else:
            info_text += "GPU Type: No GPU\n"
        
        info_text += f"Account: {job_info.get('account', 'N/A')}\n"
        info_text += f"Run Time Limit: {job_info.get('time_limit', 'N/A')}\n"
        
        # Add whether free resources are used
        if 'use_free' in job_info:
            info_text += f"Use Free Resources: {'Yes' if job_info['use_free'] else 'No'}\n"
        
        # Add submission time
        if 'submit_time' in job_info:
            submit_time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(job_info['submit_time']))
            info_text += f"\nSubmission Time: {submit_time}\n"
        
        # Add submission command and script path
        if 'command' in job_info:
            info_text += f"\nSubmission Command: {job_info['command']}\n"
        
        if 'script_path' in job_info:
            info_text += f"Script Path: {job_info['script_path']}\n"
        
        # Update job information text
        self.job_info_text.setText(info_text)
        
        # Update status label
        self.status_label.setText(f"Job {job_info.get('job_id', 'N/A')} submitted, status: {job_info.get('status', 'N/A')}")
    
    @pyqtSlot(dict)
    def update_job_status(self, status_info):
        """Update job status information"""
        if not status_info or not self.current_job:
            return
        
        # Update current job status
        self.current_job['status'] = status_info.get('status')
        if 'node' in status_info and status_info['node']:
            self.current_job['node'] = status_info['node']
        
        # Update job information display
        self.update_job_info(self.current_job)
        
        # If job has ended, restore UI status
        if status_info.get('status') in ['COMPLETED', 'CANCELLED', 'FAILED', 'TIMEOUT']:
            self.submit_btn.setEnabled(True)
            self.cancel_btn.setEnabled(False)
    
    def show_error(self, error_msg):
        """Display error message"""
        self.status_label.setText(f"Error: {error_msg}")
        logger.error(error_msg)
        # Can also display dialog
        QMessageBox.critical(self, "Error", error_msg)

    @pyqtSlot(str, str)
    def on_ssh_config_added(self, job_id, hostname):
        """Handler function when SSH configuration is added to local file"""
        logger.info(f"SSH configuration added - Job: {job_id}, Host: {hostname}")
        self.status_label.setText(f"VSCode connection configuration added - Host: {hostname}")
        
        # Add hint in job information, use setText to completely replace text, avoid using append
        job_info_text = self.job_info_text.toPlainText()
        if "SSH Configuration:" not in job_info_text:
            # Safely update text
            new_text = job_info_text + "\n\nSSH Configuration: Written to ~/.ssh/config"
            self.job_info_text.setText(new_text)

    @pyqtSlot(str)
    def on_ssh_config_removed(self, job_id):
        """Handler function when SSH configuration is removed from local file"""
        logger.info(f"SSH configuration removed - Job: {job_id}")
        self.status_label.setText(f"VSCode connection configuration removed")

    @pyqtSlot(str)
    def update_status_safe(self, message):
        """Safely update status label (called from main thread)"""
        try:
            self.status_label.setText(message)
        except Exception as e:
            logger.error(f"Failed to update status label: {e}")
    
    def remove_vscode_config(self, job_id):
        """Remove VSCode configuration"""
        try:
            # Perform removal operation
            self.vscode_manager.remove_ssh_config(job_id)
            self.status_label.setText(f"VSCode connection configuration removed")
        except Exception as e:
            logger.error(f"Failed to remove VSCode configuration: {e}")
            self.show_error(f"Failed to remove VSCode configuration: {str(e)}")

    @pyqtSlot(int)
    def on_gpu_changed(self, index):
        """Triggered when GPU selection changes"""
        # Check if a valid GPU is selected
        if index >= 0:
            gpu_type = self.gpu_combo.currentData()
            
            # Check if account name contains GPU keyword
            is_gpu_account = self.account_combo.currentData() and "gpu" in self.account_combo.currentData().lower()
            is_requesting_gpu = gpu_type is not None  # None means no GPU
            
            # If it's a GPU account but not selecting GPU, show warning
            if is_gpu_account and not is_requesting_gpu:
                self.status_label.setText("Warning: GPU account should use GPU resources")
            # If selecting GPU but not a GPU account
            elif is_requesting_gpu and not is_gpu_account:
                self.status_label.setText("Warning: GPU resources require GPU account")
            else:
                self.status_label.setText("Ready")