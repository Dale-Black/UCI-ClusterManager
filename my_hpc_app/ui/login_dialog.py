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

# Global variable to store the last successful login node information
LAST_NODE_INFO = None

def get_last_node_info():
    """Get the last successful login node information"""
    return LAST_NODE_INFO

class LoginDialog(QDialog):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('Login')
        self.setGeometry(100, 100, 500, 400)
        self.selected_user = None
        
        # Get the list of existing users
        self.users = get_all_existing_users()
        
        # Initialize UI
        self.initUI()
        
        # Automatically select the first user (if any)
        if self.users and self.user_list.count() > 0:
            self.user_list.setCurrentRow(0)
            self.on_user_selected(self.user_list.item(0))
        
        # Save login information
        self.login_success = False
        self.ssh_key_created = False

    def initUI(self):
        """Initialize UI components"""
        main_layout = QVBoxLayout()
        
        # Add user selection section
        user_selection_group = QGroupBox("Select Existing User")
        user_layout = QGridLayout()
        
        # User list
        self.user_list = QListWidget()
        self.user_list.setMinimumHeight(150)
        self.populate_user_list()
        self.user_list.itemClicked.connect(self.on_user_selected)
        user_layout.addWidget(self.user_list, 0, 0, 1, 2)
        
        # Delete and login with key buttons
        button_layout = QHBoxLayout()
        
        delete_button = QPushButton("Delete User")
        delete_button.clicked.connect(self.delete_selected_user)
        button_layout.addWidget(delete_button)
        
        # Login with key button
        self.key_login_button = QPushButton("Login with Key")
        self.key_login_button.clicked.connect(self.login_with_key)
        self.key_login_button.setEnabled(self.selected_user is not None)
        button_layout.addWidget(self.key_login_button)
        
        user_layout.addLayout(button_layout, 1, 0, 1, 2)
        
        user_selection_group.setLayout(user_layout)
        main_layout.addWidget(user_selection_group)
        
        # Add new user login section
        login_group = QGroupBox("New User Login")
        login_layout = QFormLayout()
        
        # Username input
        self.uc_id_input = QLineEdit()
        login_layout.addRow("UC ID:", self.uc_id_input)
        
        # Password input
        self.password_input = QLineEdit()
        self.password_input.setEchoMode(QLineEdit.Password)
        login_layout.addRow("Password:", self.password_input)
        
        login_group.setLayout(login_layout)
        main_layout.addWidget(login_group)
        
        # Add login button
        button_layout2 = QHBoxLayout()
        new_user_button = QPushButton("Create New User and Login")
        new_user_button.clicked.connect(self.handle_new_user_login)
        new_user_button.setMinimumHeight(40)
        button_layout2.addWidget(new_user_button)
        
        main_layout.addLayout(button_layout2)
        
        # Status information
        self.status_label = QLabel("")
        self.status_label.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(self.status_label)
        
        self.setLayout(main_layout)
    
    def populate_user_list(self):
        """Populate user list"""
        self.user_list.clear()
        if not self.users:
            self.user_list.addItem("No saved users found")
            return
        
        for user in self.users:
            username = user['username']
            item = QListWidgetItem(username)
            item.setData(Qt.UserRole, user)
            self.user_list.addItem(item)
    
    def on_user_selected(self, item):
        """Handler function when a user list item is selected"""
        user_data = item.data(Qt.UserRole)
        if not user_data:
            return
        
        self.selected_user = user_data
        self.uc_id_input.setText(user_data['username'])
        self.status_label.setText(f"Selected user: {user_data['username']}")
        self.key_login_button.setEnabled(True)
    
    def delete_selected_user(self):
        """Delete the selected user"""
        if not self.selected_user:
            QMessageBox.warning(self, "Warning", "Please select a user first")
            return
        
        confirm = QMessageBox.question(
            self, 
            "Confirm Deletion", 
            f"Are you sure you want to delete the key for user {self.selected_user['username']}?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        
        if confirm == QMessageBox.Yes:
            success = delete_user_key(self.selected_user['username'])
            if success:
                # Update user list
                self.users = get_all_existing_users()
                self.populate_user_list()
                self.selected_user = None
                self.uc_id_input.clear()
                self.status_label.setText("User deleted")
                self.key_login_button.setEnabled(False)
            else:
                QMessageBox.critical(self, "Error", "Error deleting user")
    
    def login_with_key(self):
        """Login with the selected user's key"""
        if not self.selected_user:
            QMessageBox.warning(self, "Warning", "Please select a user first")
            return
        
        try:
            self.status_label.setText(f"Logging in with key for {self.selected_user['username']}...")
            QApplication.processEvents()
            
            # Attempt to login with key
            success, username, message = check_and_login_with_key(self.selected_user['username'])
            
            if success:
                # Get node information
                node_info = get_node_info_via_key(username)
                
                # Update global node information
                global LAST_NODE_INFO
                LAST_NODE_INFO = node_info
                
                # Login successful
                logging.info(f"User {username} logged in successfully with key")
                self.login_success = True
                QMessageBox.information(self, "Success", f"Logged in successfully with key!\n\n{message}")
                self.accept()
            else:
                logging.error(f"Key login failed: {message}")
                self.status_label.setText("Key login failed")
                QMessageBox.warning(self, "Login Failed", f"Key login failed: {message}")
        except Exception as e:
            logging.error(f"Error during key login: {e}")
            self.status_label.setText("Login error")
            QMessageBox.critical(self, "Error", f"Error during login: {str(e)}")
    
    def handle_new_user_login(self):
        """Handle new user login"""
        uc_id = self.uc_id_input.text()
        password = self.password_input.text()
        
        if not uc_id or not password:
            QMessageBox.warning(self, "Warning", "Please enter username and password")
            return
        
        try:
            # Show logging in message
            self.status_label.setText("Creating new user and logging in, please wait...")
            QApplication.processEvents()
            
            # Use generate_and_upload_ssh_key function to create new user and login
            result = generate_and_upload_ssh_key(
                username=uc_id,
                password=password,
                host=HPC_SERVER,
                force=True
            )
            
            if result:
                # Login successful, get node information
                node_info = get_node_info_via_key(uc_id)
            
                # Update global node information
                global LAST_NODE_INFO
                LAST_NODE_INFO = node_info
                
                # Update user list
                self.users = get_all_existing_users()
                
                # Login successful
                logging.info(f"New user created and logged in successfully: {uc_id}")
                self.login_success = True
                self.ssh_key_created = True
                
                # Create progress dialog, waiting for key to take effect
                progress = QProgressDialog("SSH key created, waiting to take effect...", "Cancel", 0, 100, self)
                progress.setWindowTitle("Key Effect")
                progress.setMinimumDuration(0)
                progress.setAutoClose(True)
                progress.setValue(0)
                progress.show()
                
                # Set progress bar update
                self.wait_timer = QTimer(self)
                self.wait_step = 0
                
                def update_progress():
                    self.wait_step += 5
                    progress.setValue(self.wait_step)
                    
                    if self.wait_step >= 100:
                        self.wait_timer.stop()
                        progress.close()
                        # Show success message
                        message = f"Login successful!\n\nSSH key created and effective.\nNext login will automatically use the key.\n\nNode information:\n{node_info if node_info else 'No node information'}"
                        QMessageBox.information(self, "Success", message)
                        self.accept()
                
                self.wait_timer.timeout.connect(update_progress)
                self.wait_timer.start(1000)  # Update every second, total 20 seconds
            else:
                # Login failed
                logging.error("Login failed")
                self.status_label.setText("Login failed, please check your credentials")
                QMessageBox.warning(self, "Login Failed", "Login failed, please check your credentials and try again.")
        except Exception as e:
            logging.error(f"Error during login: {e}")
            self.status_label.setText("Login error")
            QMessageBox.critical(self, "Error", f"Error during login: {str(e)}") 