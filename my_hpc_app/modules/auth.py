import os
import subprocess
import time
import logging
import pexpect
import paramiko
from PyQt5.QtWidgets import QMessageBox
from modules.ssh_key_uploader import generate_and_upload_ssh_key

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Constant definitions
HPC_SERVER = 'hpc3.rcic.uci.edu'
KEY_PASSPHRASE = "create_key_for_hpc_app"  # Fixed passphrase
APP_MARKER = "_hpc_app_key"  # Application marker

def get_all_existing_users():
    """
    Get a list of all users with existing SSH keys
    
    Returns:
        list: List of users, each item is a dictionary containing username and key_path
    """
    users = []
    ssh_dir = os.path.expanduser('~/.ssh')
    
    if not os.path.exists(ssh_dir):
        return users
    
    for file in os.listdir(ssh_dir):
        if file.endswith(APP_MARKER) and not file.endswith('.pub'):
            username = file.replace(APP_MARKER, '')
            key_path = os.path.join(ssh_dir, file)
            
            if os.access(key_path, os.R_OK) and os.path.exists(f"{key_path}.pub"):
                users.append({
                    'username': username,
                    'key_path': key_path,
                    'last_used': os.path.getmtime(key_path)
                })
    
    # Sort by last used time
    users.sort(key=lambda x: x['last_used'], reverse=True)
    return users

def delete_user_key(username):
    """
    Delete a user's SSH key
    
    Args:
        username (str): Username
        
    Returns:
        bool: Whether the deletion was successful
    """
    try:
        ssh_dir = os.path.expanduser('~/.ssh')
        key_path = os.path.join(ssh_dir, f"{username}{APP_MARKER}")
        pub_key_path = f"{key_path}.pub"
        
        if os.path.exists(key_path):
            os.remove(key_path)
            logging.info(f"Deleted key: {key_path}")
        
        if os.path.exists(pub_key_path):
            os.remove(pub_key_path)
            logging.info(f"Deleted public key: {pub_key_path}")
            
        return True
    except Exception as e:
        logging.error(f"Error deleting key: {e}")
        return False

def check_network_connectivity(host):
    """
    Check if the specified host can be connected to
    
    Args:
        host (str): Host address to connect to
        
    Returns:
        bool: True if connection is successful, otherwise False
    """
    try:
        logging.info(f'Checking network connection to {host}...')
        response = subprocess.run(['ping', '-c', '1', '-W', '1', host], capture_output=True)
        if response.returncode == 0:
            logging.info(f'Network connection to {host} is successful.')
            return True
        else:
            logging.error(f'Network connection to {host} failed.')
            return False
    except Exception as e:
        logging.error(f'Error checking network connection: {e}')
        return False

def can_connect_to_hpc():
    """
    Check if the HPC server can be connected to
    
    Returns:
        bool: True if connection is successful, otherwise False
    """
    return check_network_connectivity(HPC_SERVER)

def login_with_password(uc_id, password, duo_code=None):
    """
    Log in to HPC using a password and automatically handle DUO multi-factor authentication
    
    Args:
        uc_id (str): User ID
        password (str): User password
        duo_code (str, optional): DUO verification code, must be provided
        
    Returns:
        tuple: (success, node_info)
            - success (bool): Whether the login was successful
            - node_info (str): Node information if login is successful; otherwise None
    """
    try:
        # Verification code must be provided
        if not duo_code:
            logging.error('DUO verification code is required')
            return False, None
        
        # Use the imported generate_and_upload_ssh_key to log in and upload the key
        result = generate_and_upload_ssh_key(
            username=uc_id,
            password=password,
            host=HPC_SERVER,
            force=True
        )
        
        if result:
            # Get node information
            node_info = get_node_info_via_key(uc_id)
            return True, node_info
        else:
            return False, None
            
    except Exception as e:
        logging.error(f'Error during login with password: {e}')
        return False, None

def get_node_info(child):
    """
    Get HPC node information
    
    Args:
        child: pexpect child process object
        
    Returns:
        str: Node information
    """
    try:
        # Send hostname command
        child.sendline('hostname')
        child.expect([r'\[.*@.*\]\$', pexpect.EOF, pexpect.TIMEOUT], timeout=5)
        output = child.before.decode()
        
        # Send node information command
        child.sendline('sinfo -N | grep $(hostname)')
        child.expect([r'\[.*@.*\]\$', pexpect.EOF, pexpect.TIMEOUT], timeout=5)
        node_info = child.before.decode()
        
        return f"Hostname: {output.strip()}\nNode Info: {node_info.strip()}"
    except Exception as e:
        logging.error(f'Error getting node info: {e}')
        return "Failed to get node information"

def get_node_info_via_key(uc_id):
    """
    Get node information using SSH key
    
    Args:
        uc_id (str): User ID
        
    Returns:
        str: Node information
    """
    try:
        # Get key path
        ssh_dir = os.path.expanduser('~/.ssh')
        key_path = os.path.join(ssh_dir, f"{uc_id}{APP_MARKER}")
        
        if not os.path.exists(key_path):
            logging.error(f"[AuthModule] SSH key does not exist: {key_path}")
            return None
            
        # Log in using SSH key and get node information
        logging.info(f"[AuthModule] Establishing SSH connection to {HPC_SERVER} for node information")
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        
        try:
            client.connect(
                hostname=HPC_SERVER,
                username=uc_id,
                key_filename=key_path,
                look_for_keys=False
            )
            
            logging.debug(f"[AuthModule] SSH connection established, requesting hostname")
            # Get hostname
            stdin, stdout, stderr = client.exec_command('hostname')
            hostname = stdout.read().decode().strip()
            
            logging.debug(f"[AuthModule] Requesting node information")
            # Get node information
            stdin, stdout, stderr = client.exec_command('sinfo -N | grep $(hostname)')
            node_info = stdout.read().decode().strip()
            
            logging.info(f"[AuthModule] SSH connection completed, hostname: {hostname}")
            return f"Hostname: {hostname}\nNode Info: {node_info}"
        finally:
            logging.debug(f"[AuthModule] Closing SSH connection to {HPC_SERVER}")
            client.close()
    except Exception as e:
        logging.error(f"[AuthModule] Error getting node information via SSH: {e}")
        return None

def find_existing_key(uc_id):
    """
    Find a key matching the username and application marker
    
    Args:
        uc_id (str): User ID
        
    Returns:
        tuple: (key_path, key_exists)
            - key_path (str): Key path, None if it does not exist
            - key_exists (bool): Whether the key exists
    """
    try:
        ssh_dir = os.path.expanduser('~/.ssh')
        if not os.path.exists(ssh_dir):
            return None, False
            
        # Find private key
        private_key = f"{uc_id}{APP_MARKER}"
        key_path = os.path.join(ssh_dir, private_key)
        
        if os.path.exists(key_path):
            # Check if public key comment matches
            pub_key_path = f"{key_path}.pub"
            if os.path.exists(pub_key_path):
                with open(pub_key_path, 'r') as f:
                    pub_key_content = f.read().strip()
                    if f"{uc_id}{APP_MARKER}" in pub_key_content:
                        logging.info(f'Found existing key for user {uc_id}')
                        return key_path, True
        
        return None, False
    except Exception as e:
        logging.error(f'Error finding existing key: {e}')
        return None, False

def get_node_info_from_key(uc_id):
    """
    Get node information using SSH key
    
    Args:
        uc_id: UC ID
        
    Returns:
        dict: Dictionary containing node information
    """
    try:
        # Check if the SSH key exists
        ssh_dir = os.path.expanduser('~/.ssh')
        key_path = os.path.join(ssh_dir, f"{uc_id}{APP_MARKER}")
        
        if not os.path.exists(key_path):
            logging.error(f"[AuthModule] SSH key does not exist: {key_path}")
            return None
        
        # Log in using SSH key and get node information
        logging.info(f"[AuthModule] Establishing SSH connection to {HPC_SERVER} to get node information")
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.connect(hostname=HPC_SERVER, username=uc_id, key_filename=key_path)
        
        # Get node information
        logging.debug(f"[AuthModule] Requesting node information via SSH")
        stdin, stdout, stderr = client.exec_command('sinfo -o "%n" -p free | grep -v NODELIST')
        nodes = [node.strip() for node in stdout if node.strip()]
        
        logging.info(f"[AuthModule] SSH connection to {HPC_SERVER} completed, retrieved {len(nodes)} nodes")
        client.close()
        
        if not nodes:
            logging.warning("[AuthModule] No nodes found in free partition")
            return None
        
        # Return the first node
        return {
            'node': nodes[0],
            'username': uc_id
        }
    except Exception as e:
        logging.error(f"[AuthModule] Error getting node information: {e}")
        return None

def check_and_login_with_key(specific_username=None):
    """
    Check and handle SSH key. If no key is found, return false so the main program prompts the user to log in
    
    Args:
        specific_username: Specific username to check
        
    Returns:
        tuple: (key_exists, username, error_message)
    """
    try:
        logging.info(f"[AuthModule] Checking SSH key for {'specified user' if specific_username else 'any user'}")
        
        # Check if .ssh directory exists
        ssh_dir = os.path.expanduser('~/.ssh')
        if not os.path.exists(ssh_dir):
            logging.info('[AuthModule] No .ssh directory found')
            return False, None, 'No existing SSH key found. Please login to create one.'
        
        # First check the specific username if provided
        if specific_username:
            logging.info(f"[AuthModule] Checking for SSH key for specific user: {specific_username}")
            # Check if the SSH key for the specific username exists
            key_path = os.path.join(ssh_dir, f"{specific_username}{APP_MARKER}")
            if os.path.exists(key_path):
                logging.info(f"[AuthModule] Found SSH key for {specific_username}")
                return True, specific_username, None
        
        # If no specific username or no key for the specific username, check all keys
        logging.info(f"[AuthModule] Checking all SSH keys in {ssh_dir}")
        for file in os.listdir(ssh_dir):
            if file.endswith(APP_MARKER):
                # Extract username from key name
                key_path = os.path.join(ssh_dir, file)
                username = file.replace(APP_MARKER, '')
                
                logging.info(f"[AuthModule] Testing SSH key for {username}")
                # Try to connect with this key
                try:
                    logging.info(f"[AuthModule] Establishing SSH connection to {HPC_SERVER} to verify key for {username}")
                    client = paramiko.SSHClient()
                    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                    client.connect(hostname=HPC_SERVER, username=username, key_filename=key_path, timeout=5)
                    
                    # Test if the connection works
                    stdin, stdout, stderr = client.exec_command('hostname')
                    hostname = stdout.read().decode().strip()
                    
                    client.close()
                    logging.info(f"[AuthModule] Successfully verified SSH key for {username}")
                    
                    # Return the username if the key works
                    return True, username, None
                except Exception as e:
                    logging.warning(f"[AuthModule] SSH key for {username} exists but connection failed: {e}")
                    continue
        
        # If no valid keys found
        logging.info("[AuthModule] No valid SSH keys found")
        return False, None, 'No existing SSH key found. Please login to create one.'
        
    except Exception as e:
        logging.error(f"[AuthModule] Error checking SSH key: {e}")
        return False, None, f'Error checking SSH key: {str(e)}'

# For backward compatibility, retain the original function name
def verify_credentials(uc_id, password, duo_code):
    """
    Verify user credentials using password and DUO code (retained for backward compatibility)
    
    Args:
        uc_id (str): User ID
        password (str): User password
        duo_code (str): DUO verification code
        
    Returns:
        bool: Whether the verification was successful
    """
    logging.info("Using verify_credentials function (backward compatibility)")
    # Call the new generate_and_upload_ssh_key function
    result = generate_and_upload_ssh_key(
        username=uc_id,
        password=password,
        host=HPC_SERVER,
        force=True
    )
    
    if result:
        # Get and save node information
        node_info = get_node_info_via_key(uc_id)
        global LAST_NODE_INFO
        LAST_NODE_INFO = node_info
        return True
    else:
        return False

# Global variable to store the last successful login node information
LAST_NODE_INFO = None

# Get the last login node information
def get_last_node_info():
    """
    Get the last successful login node information
    
    Returns:
        str: Node information, None if not available
    """
    return LAST_NODE_INFO

# Test function to test module functionality
def test():
    """
    Test function, example usage:
      1) Force overwrite existing key
      2) Auto-trigger Duo Push
      3) Upload public key
    """
    print("Running with test parameters...")
    # Please enter your test username and password here, or get them from the command line
    username = input("Enter username: ")
    password = input("Enter password: ")
    
    result = generate_and_upload_ssh_key(
        username=username,
        password=password,
        host=HPC_SERVER,
        port=22,
        force=True
    )
    if result:
        print("Test completed successfully!")
    else:
        print("Test failed, please check error messages.")

if __name__ == '__main__':
    # Run test
    test() 