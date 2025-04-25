#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import re
import logging
import paramiko
import threading
from PyQt5.QtCore import QObject, pyqtSignal
import time
import traceback
import socket

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class StorageManager(QObject):
    """
    Storage manager for querying various storage space usage on HPC
    """
    
    # Signal definitions
    storage_updated = pyqtSignal(dict)  # Storage information update signal
    error_occurred = pyqtSignal(str)    # Error signal
    
    def __init__(self, hostname, username, key_path=None, password=None):
        """
        Initialize storage manager
        
        Args:
            hostname: HPC hostname
            username: Username
            key_path: SSH key path
            password: SSH password
        """
        super().__init__()
        self.hostname = hostname
        self.username = username
        self.key_path = key_path
        self.password = password
        self.lock = threading.Lock()  # Thread lock to ensure SSH connection safety
        
        # Cache SSH client
        self._ssh_client = None
        
        # Attempt to connect
        self.connect_ssh()
    
    def connect_ssh(self):
        """Connect to SSH server"""
        try:
            if self._ssh_client and self._ssh_client.get_transport() and self._ssh_client.get_transport().is_active():
                logger.debug("SSH connection already exists and is active")
                return True
            
            # If there is an old connection, close it first
            if self._ssh_client:
                try:
                    self._ssh_client.close()
                except:
                    pass
            
            # Create a new SSH client
            logger.info(f"Connecting to SSH server: {self.hostname}@{self.username}")
            self._ssh_client = paramiko.SSHClient()
            self._ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            
            # Connect using key or password
            if self.key_path:
                self._ssh_client.connect(
                    hostname=self.hostname,
                    username=self.username,
                    key_filename=self.key_path,
                    timeout=15,
                    look_for_keys=False,
                    allow_agent=False
                )
            elif self.password:
                self._ssh_client.connect(
                    hostname=self.hostname,
                    username=self.username,
                    password=self.password,
                    timeout=15,
                    look_for_keys=False,
                    allow_agent=False
                )
            else:
                error_msg = "Key path or password must be provided"
                logger.error(error_msg)
                self.error_occurred.emit(error_msg)
                return False
            
            logger.info("SSH connection successful")
            return True
        except Exception as e:
            error_msg = f"SSH connection failed: {str(e)}"
            logger.error(error_msg)
            self.error_occurred.emit(error_msg)
            return False
    
    def _close_ssh_client(self):
        """Safely close SSH client connection"""
        if self._ssh_client:
            try:
                self._ssh_client.close()
            except:
                pass
            self._ssh_client = None
    
    def execute_ssh_command(self, command):
        """
        Execute SSH command and return result
        
        Args:
            command: Command to execute
            
        Returns:
            str: Output of the command
        """
        try:
            # Ensure there is a connection
            if not self._ssh_client or not self._ssh_client.get_transport() or not self._ssh_client.get_transport().is_active():
                if not self.connect_ssh():
                    raise Exception("Unable to connect to SSH server")
            
            # Execute command
            stdin, stdout, stderr = self._ssh_client.exec_command(command, timeout=30)
            output = stdout.read().decode('utf-8')
            error = stderr.read().decode('utf-8')
            
            # If there is an error and no output, raise an exception
            if error and not output:
                logger.error(f"Command execution error: {error}")
                raise Exception(f"Command execution error: {error}")
            
            return output
        except Exception as e:
            logger.error(f"Command execution failed: {str(e)}")
            # Attempt to reconnect
            self.connect_ssh()
            raise Exception(f"Command execution failed: {str(e)}")
    
    def get_all_storage_info(self):
        """
        Get information of all storage spaces
        
        Returns:
            dict: Dictionary containing all storage space information
        """
        try:
            logger.info("Starting to get storage information")
            storage_data = {}
            
            # 1. Get HOME information
            home_path = self.find_home_directory()
            if home_path:
                storage_data['home'] = self.get_storage_usage(home_path)
            else:
                storage_data['home'] = {
                    'path': f"/data/homez*/{self.username}",
                    'exists': False,
                    'error': "Unable to find HOME directory"
                }
            
            # 2. Get DFS information
            personal_dfs, lab_dfs_paths = self.check_dfs_locations()
            
            if personal_dfs:
                storage_data['personal_dfs'] = self.get_storage_usage(personal_dfs)
            
            # Lab DFS may have multiple
            storage_data['lab_dfs'] = []
            for lab_path in lab_dfs_paths:
                if lab_path.strip():
                    lab_info = self.get_storage_usage(lab_path)
                    storage_data['lab_dfs'].append(lab_info)
            
            # 3. Get CRSP information
            personal_crsp, lab_crsp = self.check_crsp_locations()
            
            if personal_crsp:
                storage_data['personal_crsp'] = self.get_storage_usage(personal_crsp)
            
            if lab_crsp:
                storage_data['lab_crsp'] = self.get_storage_usage(lab_crsp)
            
            # 4. Get Scratch information (temporary storage of the current node)
            storage_data['scratch'] = self.get_storage_usage('$TMPDIR')
            
            # Emit signal to update UI
            self.storage_updated.emit(storage_data)
            logger.info("Storage information retrieval complete")
            
            return storage_data
        except Exception as e:
            logger.error(f"Failed to get storage information: {str(e)}")
            self.error_occurred.emit(f"Failed to get storage information: {str(e)}")
            return {}
    
    def find_home_directory(self):
        """
        Find the user's HOME directory in which homezvolX
        
        Returns:
            str: Full path of the HOME directory
        """
        try:
            # Execute command to find HOME directory
            cmd = "echo $HOME"
            output = self.execute_ssh_command(cmd)
            home_path = output.strip()
            
            # Check if it is in the expected format
            if "/data/homez" in home_path:
                logger.info(f"Found HOME directory: {home_path}")
                return home_path
            else:
                # Attempt to get via pwd command
                cmd = "pwd"
                output = self.execute_ssh_command(cmd)
                home_path = output.strip()
                if "/data/homez" in home_path:
                    return home_path
                else:
                    # Finally attempt to use formatted path directly
                    home_path = f"/data/homez*/{self.username}"
                    cmd = f"ls -d {home_path} 2>/dev/null"
                    output = self.execute_ssh_command(cmd)
                    if output.strip():
                        return output.strip()
            
            # If all methods above fail, return None
            return None
        except Exception as e:
            logger.error(f"Failed to find HOME directory: {str(e)}")
            return None
    
    def find_lab_name(self):
        """
        Find the lab name based on user balance information
        
        Returns:
            str: Lab name
        """
        try:
            # Execute sbank command to get balance and extract lab name
            cmd = f"sbank balance statement -u {self.username}"
            output = self.execute_ssh_command(cmd)
            
            # Find strings like SYMOLLOI_LAB
            lab_pattern = r'[A-Z]+_LAB'
            matches = re.findall(lab_pattern, output)
            
            if matches:
                # Remove _LAB suffix and convert to lowercase
                lab_name = matches[0].replace('_LAB', '').lower()
                logger.info(f"Found lab name: {lab_name}")
                return lab_name
            else:
                # Attempt to find other possible lab name formats
                account_pattern = r'(\w+)\s+\|'
                matches = re.findall(account_pattern, output)
                if len(matches) > 1:  # The first match is usually the username
                    potential_lab = matches[1]
                    if potential_lab.upper() != self.username.upper():
                        return potential_lab.lower()
            
            # If not found, return None
            return None
        except Exception as e:
            logger.error(f"Failed to find lab name: {str(e)}")
            return None
    
    def check_dfs_locations(self):
        """
        Check DFS personal and lab spaces
        
        Returns:
            tuple: (personal_dfs, lab_dfs)
                - personal_dfs: Personal DFS path
                - lab_dfs: List of lab DFS paths
        """
        try:
            # Personal DFS path is fixed
            personal_dfs = f"/pub/{self.username}"
            
            # Check lab DFS paths
            lab_dfs_paths = []
            
            # Find possible dfs directories
            cmd = "ls -d /dfs* 2>/dev/null"
            output = self.execute_ssh_command(cmd)
            dfs_roots = output.strip().split('\n')
            
            # Find lab name for searching in DFS
            lab_name = self.find_lab_name()
            
            if lab_name:
                # Search for lab directory in each dfs directory
                for dfs_root in dfs_roots:
                    if not dfs_root.strip():
                        continue
                    
                    # Attempt different possible path patterns
                    patterns = [
                        f"{dfs_root}/{lab_name}*",
                        f"{dfs_root}/*{lab_name}*"
                    ]
                    
                    for pattern in patterns:
                        cmd = f"ls -d {pattern} 2>/dev/null"
                        try:
                            output = self.execute_ssh_command(cmd)
                            if output.strip():
                                lab_dfs_paths.extend(output.strip().split('\n'))
                        except:
                            pass
            
            return personal_dfs, lab_dfs_paths
        except Exception as e:
            logger.error(f"Failed to check DFS locations: {str(e)}")
            return None, []
    
    def check_crsp_locations(self):
        """
        Check CRSP personal and lab shared spaces
        
        Returns:
            tuple: (personal_crsp, lab_crsp)
                - personal_crsp: Personal CRSP path
                - lab_crsp: Lab shared CRSP path
        """
        try:
            lab_name = self.find_lab_name()
            
            if not lab_name:
                return None, None
            
            personal_crsp = f"/share/crsp/lab/{lab_name}/{self.username}"
            lab_crsp = f"/share/crsp/lab/{lab_name}/share"
            
            return personal_crsp, lab_crsp
        except Exception as e:
            logger.error(f"Failed to check CRSP locations: {str(e)}")
            return None, None
    
    def get_storage_usage(self, path):
        """
        Get storage usage of the specified path
        
        Args:
            path: Path to check
            
        Returns:
            dict: Dictionary containing total capacity, used space, and available space
        """
        try:
            # Check if directory exists
            cmd = f"test -d {path} && echo exists || echo notexists"
            output = self.execute_ssh_command(cmd)
            if output.strip() == "notexists":
                return {
                    'path': path,
                    'exists': False,
                    'total': 0,
                    'used': 0,
                    'available': 0,
                    'use_percent': 0
                }
            
            # Use df command to check usage
            cmd = f"df -h {path} | tail -n 1"
            output = self.execute_ssh_command(cmd)
            
            parts = output.strip().split()
            if len(parts) >= 6:
                # Typical df output format: Filesystem Size Used Avail Use% Mounted on
                filesystem = parts[0]
                total = parts[1]
                used = parts[2]
                available = parts[3]
                use_percent = parts[4].replace('%', '')
                mounted_on = ' '.join(parts[5:])
                
                return {
                    'path': path,
                    'exists': True,
                    'filesystem': filesystem,
                    'total': total,
                    'used': used,
                    'available': available,
                    'use_percent': use_percent,
                    'mounted_on': mounted_on
                }
            else:
                logger.warning(f"Unable to parse df output: {output}")
                return {
                    'path': path,
                    'exists': True,
                    'total': 'Unknown',
                    'used': 'Unknown',
                    'available': 'Unknown',
                    'use_percent': 'Unknown'
                }
        except Exception as e:
            logger.error(f"Failed to get storage usage: {str(e)}")
            return {
                'path': path,
                'exists': False,
                'total': 'Error',
                'used': 'Error',
                'available': 'Error',
                'use_percent': 'Error',
                'error': str(e)
            }
    
    def refresh_storage_info(self):
        """
        Force refresh storage information
        
        Returns:
            dict: Updated storage information
        """
        logger.info("Starting to refresh storage information")
        return self.get_all_storage_info()
    
    def __del__(self):
        """Destructor to ensure SSH connection is closed"""
        if hasattr(self, '_ssh_client') and self._ssh_client:
            try:
                self._ssh_client.close()
            except Exception as e:
                logging.error(f"Failed to close SSH connection: {str(e)}") 