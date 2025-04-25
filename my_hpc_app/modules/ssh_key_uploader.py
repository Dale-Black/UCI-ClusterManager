#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import paramiko
import subprocess
import time
import argparse
import sys


def generate_and_upload_ssh_key(username, password, host='hpc3.rcic.uci.edu', port=22, key_comment=None, force=False):
    """
    Generate SSH key and upload to remote server, using Paramiko keyboard-interactive to support DUO two-factor authentication.

    Args:
        username (str): Username
        password (str): Password
        host (str): Server address
        port (int): SSH port
        key_comment (str): SSH key comment
        force (bool): Whether to force overwrite existing key
    
    Returns:
        bool: True if successful, False if failed
    """
    home_dir = os.path.expanduser("~")
    ssh_dir = os.path.join(home_dir, ".ssh")
    key_file = os.path.join(ssh_dir, f"{username}_hpc_app_key")
    public_key_file = f"{key_file}.pub"

    # Ensure ~/.ssh directory exists
    if not os.path.exists(ssh_dir):
        os.makedirs(ssh_dir, mode=0o700)

    # If key exists, check whether to overwrite
    if os.path.exists(key_file) and not force:
        print(f"SSH key already exists at {key_file}")
        print("Operation cancelled. Use force=True to overwrite")
        return False

    # Generate SSH key pair
    try:
        if not key_comment:
            key_comment = f"{username}_hpc_app_key"
        cmd = ["ssh-keygen", "-t", "rsa", "-b", "4096", "-f", key_file, "-N", "", "-C", key_comment]
        subprocess.run(cmd, check=True)
        print(f"SSH key generated: {key_file}")
    except subprocess.CalledProcessError as e:
        print(f"Error generating SSH key: {e}")
        return False

    # Read public key content
    with open(public_key_file, "r") as f:
        public_key = f.read().strip()

    # Use keyboard-interactive + Duo
    transport = paramiko.Transport((host, port))
    try:
        transport.start_client()

        # Callback function to handle "Password:" (system account password) and Duo prompts
        def duo_handler(title, instructions, prompt_list):
            responses = []
            for prompt, is_secret in prompt_list:
                # First prompt usually asks for "Password:"
                if "Password:" in prompt:
                    responses.append(password)
                # Second prompt usually asks for "Passcode or option (1-...)" => select "1" to trigger Duo Push
                elif "Passcode" in prompt or "Duo two-factor login" in title:
                    responses.append("1")
                # No other prompts, no empty return case, return empty string for unknown prompts
                else:
                    responses.append('')
            return responses

        transport.auth_interactive(username, duo_handler)

        if not transport.is_authenticated():
            print("Authentication failed: Please check username, password, or DUO authentication status")
            return False

        # Create SSHClient and bind to authenticated Transport
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client._transport = transport

    except paramiko.AuthenticationException as e:
        print(f"Authentication failed: {e}")
        return False
    except paramiko.SSHException as e:
        print(f"SSH connection error: {e}")
        return False
    except Exception as e:
        print(f"An error occurred: {e}")
        return False

    # Upload public key to server's authorized_keys
    try:
        print("Writing public key to server's authorized_keys...")
        command = (
            f'mkdir -p ~/.ssh && '
            f'echo "{public_key}" >> ~/.ssh/authorized_keys && '
            f'chmod 600 ~/.ssh/authorized_keys && chmod 700 ~/.ssh'
        )
        stdin, stdout, stderr = client.exec_command(command)
        exit_status = stdout.channel.recv_exit_status()
        if exit_status == 0:
            print("SSH key successfully uploaded to server")
            return True
        else:
            error = stderr.read().decode()
            print(f"Error uploading SSH key: {error}")
            return False
    finally:
        client.close()


def main():
    """
    Main function to handle command line arguments and call generate/upload function
    """
    parser = argparse.ArgumentParser(description='SSH Key Generation and Upload Tool')
    parser.add_argument('-u', '--username', required=True, help='Username')
    parser.add_argument('-p', '--password', required=True, help='Password')
    parser.add_argument('-H', '--host', default='hpc3.rcic.uci.edu', help='Server address (default: hpc3.rcic.uci.edu)')
    parser.add_argument('-P', '--port', type=int, default=22, help='SSH port (default: 22)')
    parser.add_argument('-c', '--comment', help='SSH key comment')
    parser.add_argument('-f', '--force', action='store_true', help='Force overwrite existing key')
    
    args = parser.parse_args()
    
    result = generate_and_upload_ssh_key(
        username=args.username,
        password=args.password,
        host=args.host,
        port=args.port,
        key_comment=args.comment,
        force=args.force
    )
    
    if result:
        print("Operation completed successfully!")
    else:
        print("Operation incomplete, please check error messages.")
        exit(1)


def test():
    """
    Test function, example usage:
      1) Force overwrite existing key
      2) Auto-trigger Duo Push
      3) Upload public key
    """
    print("Running with test parameters...")
    result = generate_and_upload_ssh_key(
        username="liangys5",       # Replace with your own username
        password="GoodLuck2023!",  # Replace with your real password
        host="hpc3.rcic.uci.edu",
        port=22,
        force=True
    )
    if result:
        print("Test completed successfully!")
    else:
        print("Test failed, please check error messages.")


if __name__ == "__main__":
    if len(sys.argv) == 1 or (len(sys.argv) > 1 and sys.argv[1] == "--test"):
        # If no arguments or first argument is --test, run test function
        test()
    else:
        # Otherwise run main function to handle command line arguments
        main()
