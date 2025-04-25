#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import logging
import subprocess
import paramiko
import os
import re
import json
import time
from PyQt5.QtCore import QObject, pyqtSignal

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class SlurmManager(QObject):
    """Slurm job manager for interacting with SLURM"""
    
    # Signal definitions
    job_list_updated = pyqtSignal(list)  # Job list update signal
    job_submitted = pyqtSignal(str)  # Job submission signal
    job_canceled = pyqtSignal(str)  # Job cancellation signal
    error_occurred = pyqtSignal(str)  # Error signal
    
    def __init__(self, hostname, username, key_path):
        """
        Initialize Slurm job manager
        
        Args:
            hostname: HPC hostname
            username: Username
            key_path: SSH key path
        """
        super().__init__()
        self.hostname = hostname
        self.username = username
        self.key_path = key_path
        
    def _get_ssh_client(self):
        """
        Get SSH client connection
        
        Returns:
            paramiko.SSHClient: SSH client
        """
        try:
            client = paramiko.SSHClient()
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            client.connect(
                hostname=self.hostname,
                username=self.username,
                key_filename=self.key_path,
                look_for_keys=False
            )
            return client
        except Exception as e:
            logging.error(f"SSH connection failed: {e}")
            self.error_occurred.emit(f"SSH connection failed: {str(e)}")
            return None
    
    def get_jobs(self):
        """
        Get all jobs for current user
        
        Returns:
            list: List of jobs
        """
        try:
            client = self._get_ssh_client()
            if not client:
                return []
                
            try:
                # Use squeue command to get job information
                cmd = f"squeue -u {self.username} -o '%A|%j|%T|%M|%L|%D|%C|%R' -h"
                stdin, stdout, stderr = client.exec_command(cmd)
                
                # Parse output
                jobs = []
                for line in stdout:
                    line = line.strip()
                    if not line:
                        continue
                        
                    parts = line.split('|')
                    if len(parts) == 8:
                        job = {
                            'id': parts[0],
                            'name': parts[1],
                            'state': parts[2],
                            'time': parts[3],
                            'time_limit': parts[4],
                            'nodes': parts[5],
                            'cpus': parts[6],
                            'reason': parts[7]
                        }
                        jobs.append(job)
                
                # Send job list update signal
                self.job_list_updated.emit(jobs)
                return jobs
            finally:
                client.close()
        except Exception as e:
            logging.error(f"Failed to get job list: {e}")
            self.error_occurred.emit(f"Failed to get job list: {str(e)}")
            return []
    
    def get_job_details(self, job_id):
        """
        Get job details
        
        Args:
            job_id: Job ID
            
        Returns:
            dict: Job details
        """
        try:
            client = self._get_ssh_client()
            if not client:
                return {}
                
            try:
                # Use scontrol command to get job details
                cmd = f"scontrol show job {job_id}"
                stdin, stdout, stderr = client.exec_command(cmd)
                
                # Read output
                output = stdout.read().decode()
                
                # Parse output
                details = {}
                for line in output.split('\n'):
                    line = line.strip()
                    if not line:
                        continue
                        
                    for item in line.split():
                        if '=' in item:
                            key, value = item.split('=', 1)
                            details[key] = value
                
                return details
            finally:
                client.close()
        except Exception as e:
            logging.error(f"Failed to get job details: {e}")
            self.error_occurred.emit(f"Failed to get job details: {str(e)}")
            return {}
    
    def submit_job(self, script_content, remote_filename=None):
        """
        Submit job
        
        Args:
            script_content: Script content
            remote_filename: Remote filename, auto-generated if None
            
        Returns:
            str: Job ID, None if failed
        """
        try:
            client = self._get_ssh_client()
            if not client:
                return None
                
            try:
                # Auto-generate remote filename if not provided
                if not remote_filename:
                    timestamp = int(time.time())
                    remote_filename = f"job_script_{timestamp}.sh"
                
                # Create SFTP session
                sftp = client.open_sftp()
                
                # Upload script
                remote_path = f"/tmp/{remote_filename}"
                with sftp.file(remote_path, 'w') as f:
                    f.write(script_content)
                
                # Set executable permission
                sftp.chmod(remote_path, 0o755)
                
                # Submit job
                cmd = f"sbatch {remote_path}"
                stdin, stdout, stderr = client.exec_command(cmd)
                
                # Read output
                output = stdout.read().decode().strip()
                
                # Parse job ID
                match = re.search(r'Submitted batch job (\d+)', output)
                if match:
                    job_id = match.group(1)
                    self.job_submitted.emit(job_id)
                    return job_id
                else:
                    error = stderr.read().decode().strip()
                    logging.error(f"Failed to submit job: {error}")
                    self.error_occurred.emit(f"Failed to submit job: {error}")
                    return None
            finally:
                client.close()
        except Exception as e:
            logging.error(f"Failed to submit job: {e}")
            self.error_occurred.emit(f"Failed to submit job: {str(e)}")
            return None
    
    def cancel_job(self, job_id):
        """
        Cancel job
        
        Args:
            job_id: Job ID
            
        Returns:
            bool: Whether successful
        """
        try:
            client = self._get_ssh_client()
            if not client:
                return False
                
            try:
                # Use scancel command to cancel job
                cmd = f"scancel {job_id}"
                stdin, stdout, stderr = client.exec_command(cmd)
                
                # Check for errors
                error = stderr.read().decode().strip()
                if error:
                    logging.error(f"Failed to cancel job: {error}")
                    self.error_occurred.emit(f"Failed to cancel job: {error}")
                    return False
                
                self.job_canceled.emit(job_id)
                return True
            finally:
                client.close()
        except Exception as e:
            logging.error(f"Failed to cancel job: {e}")
            self.error_occurred.emit(f"Failed to cancel job: {str(e)}")
            return False
    
    def get_cluster_info(self):
        """
        Get cluster node information
        
        Returns:
            dict: Cluster information
        """
        try:
            client = self._get_ssh_client()
            if not client:
                return {}
                
            try:
                # Use sinfo command to get cluster node information
                cmd = "sinfo -o '%N|%C|%t|%O|%T|%P' -h"
                stdin, stdout, stderr = client.exec_command(cmd)
                
                # Parse output
                nodes = []
                for line in stdout:
                    line = line.strip()
                    if not line:
                        continue
                        
                    parts = line.split('|')
                    if len(parts) == 6:
                        node = {
                            'name': parts[0],
                            'cpus': parts[1],
                            'state': parts[2],
                            'features': parts[3],
                            'reason': parts[4],
                            'partition': parts[5]
                        }
                        nodes.append(node)
                
                return nodes
            finally:
                client.close()
        except Exception as e:
            logging.error(f"Failed to get cluster information: {e}")
            self.error_occurred.emit(f"Failed to get cluster information: {str(e)}")
            return []
    
    def get_partition_info(self):
        """
        Get partition information
        
        Returns:
            list: List of partition information
        """
        try:
            client = self._get_ssh_client()
            if not client:
                return []
                
            try:
                # Use sinfo command to get partition information
                cmd = "sinfo -s -o '%P|%a|%l|%D|%T|%N' -h"
                stdin, stdout, stderr = client.exec_command(cmd)
                
                # Parse output
                partitions = []
                for line in stdout:
                    line = line.strip()
                    if not line:
                        continue
                        
                    parts = line.split('|')
                    if len(parts) == 6:
                        partition = {
                            'name': parts[0],
                            'avail': parts[1],
                            'time_limit': parts[2],
                            'nodes': parts[3],
                            'state': parts[4],
                            'node_names': parts[5]
                        }
                        partitions.append(partition)
                
                return partitions
            finally:
                client.close()
        except Exception as e:
            logging.error(f"Failed to get partition information: {e}")
            self.error_occurred.emit(f"Failed to get partition information: {str(e)}")
            return [] 