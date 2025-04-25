import os
import subprocess
import time
import logging
import pexpect
import paramiko
from PyQt5.QtWidgets import QMessageBox
from modules.ssh_key_uploader import generate_and_upload_ssh_key

# 配置日志记录
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# 常量定义
HPC_SERVER = 'hpc3.rcic.uci.edu'
KEY_PASSPHRASE = "create_key_for_hpc_app"  # 固定密码
APP_MARKER = "_hpc_app_key"  # 应用标记

def get_all_existing_users():
    """
    获取所有已存在SSH密钥的用户列表
    
    Returns:
        list: 用户列表，每个项目是一个字典，包含username和key_path
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
    
    # 按最后使用时间排序
    users.sort(key=lambda x: x['last_used'], reverse=True)
    return users

def delete_user_key(username):
    """
    删除用户的SSH密钥
    
    Args:
        username (str): 用户名
        
    Returns:
        bool: 删除是否成功
    """
    try:
        ssh_dir = os.path.expanduser('~/.ssh')
        key_path = os.path.join(ssh_dir, f"{username}{APP_MARKER}")
        pub_key_path = f"{key_path}.pub"
        
        if os.path.exists(key_path):
            os.remove(key_path)
            logging.info(f"已删除密钥: {key_path}")
        
        if os.path.exists(pub_key_path):
            os.remove(pub_key_path)
            logging.info(f"已删除公钥: {pub_key_path}")
            
        return True
    except Exception as e:
        logging.error(f"删除密钥时出错: {e}")
        return False

def check_network_connectivity(host):
    """
    检查是否可以连接到指定主机
    
    Args:
        host (str): 要连接的主机地址
        
    Returns:
        bool: 如果连接成功返回True，否则返回False
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
    检查是否可以连接到HPC服务器
    
    Returns:
        bool: 如果连接成功返回True，否则返回False
    """
    return check_network_connectivity(HPC_SERVER)

def login_with_password(uc_id, password, duo_code=None):
    """
    使用密码登录HPC，并自动处理DUO多因素验证
    
    Args:
        uc_id (str): 用户ID
        password (str): 用户密码
        duo_code (str, optional): DUO验证码，必须提供
        
    Returns:
        tuple: (success, node_info)
            - success (bool): 登录是否成功
            - node_info (str): 如果登录成功，返回节点信息；否则为None
    """
    try:
        # 验证码必须提供
        if not duo_code:
            logging.error('DUO verification code is required')
            return False, None
        
        # 使用导入的generate_and_upload_ssh_key来登录并上传密钥
        result = generate_and_upload_ssh_key(
            username=uc_id,
            password=password,
            host=HPC_SERVER,
            force=True
        )
        
        if result:
            # 获取节点信息
            node_info = get_node_info_via_key(uc_id)
            return True, node_info
        else:
            return False, None
            
    except Exception as e:
        logging.error(f'Error during login with password: {e}')
        return False, None

def get_node_info(child):
    """
    获取HPC节点信息
    
    Args:
        child: pexpect子进程对象
        
    Returns:
        str: 节点信息
    """
    try:
        # 发送hostname命令
        child.sendline('hostname')
        child.expect([r'\[.*@.*\]\$', pexpect.EOF, pexpect.TIMEOUT], timeout=5)
        output = child.before.decode()
        
        # 发送节点信息命令
        child.sendline('sinfo -N | grep $(hostname)')
        child.expect([r'\[.*@.*\]\$', pexpect.EOF, pexpect.TIMEOUT], timeout=5)
        node_info = child.before.decode()
        
        return f"Hostname: {output.strip()}\nNode Info: {node_info.strip()}"
    except Exception as e:
        logging.error(f'Error getting node info: {e}')
        return "Failed to get node information"

def get_node_info_via_key(uc_id):
    """
    使用SSH密钥获取节点信息
    
    Args:
        uc_id (str): 用户ID
        
    Returns:
        str: 节点信息
    """
    try:
        # 获取密钥路径
        ssh_dir = os.path.expanduser('~/.ssh')
        key_path = os.path.join(ssh_dir, f"{uc_id}{APP_MARKER}")
        
        if not os.path.exists(key_path):
            logging.error(f"SSH密钥不存在: {key_path}")
            return None
            
        # 使用SSH密钥登录并获取节点信息
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        
        try:
            client.connect(
                hostname=HPC_SERVER,
                username=uc_id,
                key_filename=key_path,
                look_for_keys=False
            )
            
            # 获取hostname
            stdin, stdout, stderr = client.exec_command('hostname')
            hostname = stdout.read().decode().strip()
            
            # 获取节点信息
            stdin, stdout, stderr = client.exec_command('sinfo -N | grep $(hostname)')
            node_info = stdout.read().decode().strip()
            
            return f"Hostname: {hostname}\nNode Info: {node_info}"
        finally:
            client.close()
    except Exception as e:
        logging.error(f"获取节点信息时出错: {e}")
        return None

def find_existing_key(uc_id):
    """
    查找与用户名和应用标记匹配的密钥
    
    Args:
        uc_id (str): 用户ID
        
    Returns:
        tuple: (key_path, key_exists)
            - key_path (str): 密钥路径，如果不存在则为None
            - key_exists (bool): 密钥是否存在
    """
    try:
        ssh_dir = os.path.expanduser('~/.ssh')
        if not os.path.exists(ssh_dir):
            return None, False
            
        # 查找私钥
        private_key = f"{uc_id}{APP_MARKER}"
        key_path = os.path.join(ssh_dir, private_key)
        
        if os.path.exists(key_path):
            # 检查公钥注释是否匹配
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

def check_and_login_with_key(specific_username=None):
    """
    检查并处理SSH密钥。如果找不到密钥就返回false以便主程序提示用户需要登录
    
    Args:
        specific_username (str, optional): 指定的用户名，如果提供则只检查该用户的密钥
    
    Returns:
        tuple: (success, uc_id, message)
            - success (bool): 是否成功
            - uc_id (str): 用户ID，如果失败则为None
            - message (str): 状态消息
    """
    try:
        # 检查是否存在.ssh目录
        ssh_dir = os.path.expanduser('~/.ssh')
        if not os.path.exists(ssh_dir):
            logging.info('No .ssh directory found')
            return False, None, 'No existing SSH key found. Please login to create one.'
        
        # 查找已有的密钥
        uc_id = None
        key_path = None
        
        if specific_username:
            # 如果指定了用户名，只检查该用户的密钥
            key_path = os.path.join(ssh_dir, f"{specific_username}{APP_MARKER}")
            if os.path.exists(key_path) and os.path.exists(f"{key_path}.pub"):
                uc_id = specific_username
                logging.info(f'Found key for specified user: {specific_username}')
        else:
            # 否则，查找所有可能的密钥
            for file in os.listdir(ssh_dir):
                if file.endswith(APP_MARKER) and not file.endswith('.pub'):
                    uc_id = file.replace(APP_MARKER, '')
                    key_path = os.path.join(ssh_dir, file)
                    
                    # 确保文件是readable的
                    if not os.access(key_path, os.R_OK):
                        logging.error(f'Found key {key_path} but it is not readable')
                        continue
                        
                    # 确保对应的公钥存在
                    pub_key_path = f"{key_path}.pub"
                    if not os.path.exists(pub_key_path):
                        logging.error(f'Found private key {key_path} but public key is missing')
                        continue
                    
                    # 发现一个可能的密钥，尝试使用它
                    break
        
        if not uc_id or not key_path or not os.path.exists(key_path):
            logging.info('No existing key found')
            return False, None, 'No existing SSH key found. Please login to create one.'
        
        # 测试密钥登录
        try:
            client = paramiko.SSHClient()
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            
            logging.info(f'Testing login with key: {key_path}')
            
            client.connect(
                hostname=HPC_SERVER,
                username=uc_id,
                key_filename=key_path,
                look_for_keys=False
            )
            
            # 获取节点信息
            stdin, stdout, stderr = client.exec_command('hostname')
            hostname = stdout.read().decode().strip()
            
            # 更新全局节点信息
            global LAST_NODE_INFO
            LAST_NODE_INFO = f"Hostname: {hostname}\nLogin method: Key-based"
            
            logging.info(f'Login successful using existing key for user: {uc_id}')
            client.close()
            return True, uc_id, 'Login successful using existing key'
        except Exception as e:
            logging.error(f'Error testing key login: {e}')
            
            # 删除无效的密钥
            try:
                if os.path.exists(key_path):
                    os.remove(key_path)
                    logging.info(f'Deleted invalid key: {key_path}')
                pub_key_path = f"{key_path}.pub"
                if os.path.exists(pub_key_path):
                    os.remove(pub_key_path)
                    logging.info(f'Deleted invalid public key: {pub_key_path}')
            except Exception as e:
                logging.error(f'Error deleting invalid key: {e}')
                
            return False, None, 'Existing key login failed. Please login again to create a new key.'
            
    except Exception as e:
        logging.error(f'Error in check_and_login_with_key: {e}')
        return False, None, f'Error checking SSH key: {str(e)}'

# 为了向后兼容，保留原有函数名
def verify_credentials(uc_id, password, duo_code):
    """
    使用密码和DUO验证码验证用户凭据（为向后兼容而保留）
    
    Args:
        uc_id (str): 用户ID
        password (str): 用户密码
        duo_code (str): DUO验证码
        
    Returns:
        bool: 验证是否成功
    """
    logging.info("Using verify_credentials function (backward compatibility)")
    # 调用新的generate_and_upload_ssh_key函数
    result = generate_and_upload_ssh_key(
        username=uc_id,
        password=password,
        host=HPC_SERVER,
        force=True
    )
    
    if result:
        # 获取并保存节点信息
        node_info = get_node_info_via_key(uc_id)
        global LAST_NODE_INFO
        LAST_NODE_INFO = node_info
        return True
    else:
        return False

# 全局变量存储最后一次成功登录的节点信息
LAST_NODE_INFO = None

# 获取最后一次登录的节点信息
def get_last_node_info():
    """
    获取最后一次成功登录的节点信息
    
    Returns:
        str: 节点信息，如果没有则返回None
    """
    return LAST_NODE_INFO

# 测试函数，用于测试模块功能
def test():
    """
    用于测试的函数, 示例调用:
      1) 强制覆盖现有密钥
      2) 自动触发Duo Push
      3) 上传公钥
    """
    print("使用测试参数运行...")
    # 请在这里填入您的测试用户名和密码，或从命令行获取
    username = input("请输入用户名: ")
    password = input("请输入密码: ")
    
    result = generate_and_upload_ssh_key(
        username=username,
        password=password,
        host=HPC_SERVER,
        port=22,
        force=True
    )
    if result:
        print("测试成功完成!")
    else:
        print("测试失败, 请检查错误信息。")

if __name__ == '__main__':
    # 运行测试
    test() 