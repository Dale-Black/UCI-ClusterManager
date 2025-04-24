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
    生成SSH密钥并上传到远程服务器，使用Paramiko keyboard-interactive来支持DUO双因素认证。

    参数:
        username (str): 用户名
        password (str): 密码
        host (str): 服务器地址
        port (int): SSH端口号
        key_comment (str): SSH密钥的备注
        force (bool): 是否强制覆盖现有密钥
    
    返回:
        bool: 成功返回True, 失败返回False
    """
    home_dir = os.path.expanduser("~")
    ssh_dir = os.path.join(home_dir, ".ssh")
    key_file = os.path.join(ssh_dir, f"{username}_hpc_app_key")
    public_key_file = f"{key_file}.pub"

    # 确保~/.ssh目录存在
    if not os.path.exists(ssh_dir):
        os.makedirs(ssh_dir, mode=0o700)

    # 如果密钥已存在, 检查是否覆盖
    if os.path.exists(key_file) and not force:
        print(f"SSH密钥已存在于 {key_file}")
        print("操作已取消。如果要覆盖, 请使用 force=True")
        return False

    # 生成SSH密钥对
    try:
        if not key_comment:
            key_comment = f"{username}_hpc_app_key"
        cmd = ["ssh-keygen", "-t", "rsa", "-b", "4096", "-f", key_file, "-N", "", "-C", key_comment]
        subprocess.run(cmd, check=True)
        print(f"SSH密钥已生成: {key_file}")
    except subprocess.CalledProcessError as e:
        print(f"生成SSH密钥时出错: {e}")
        return False

    # 读取公钥内容
    with open(public_key_file, "r") as f:
        public_key = f.read().strip()

    # 使用 keyboard-interactive + Duo
    transport = paramiko.Transport((host, port))
    try:
        transport.start_client()

        # 回调函数, 用于处理 "Password:" (系统账户密码) 与 Duo 的提示
        def duo_handler(title, instructions, prompt_list):
            responses = []
            for prompt, is_secret in prompt_list:
                # 第一次通常提示 "Password:"
                if "Password:" in prompt:
                    responses.append(password)
                # 第二次通常提示 "Passcode or option (1-...)" 之类 => 选 "1" 触发 Duo Push
                elif "Passcode" in prompt or "Duo two-factor login" in title:
                    responses.append("1")
                # 无其他提示, 不存在空回车情况, 如果出现未知提示直接返回空串
                else:
                    responses.append('')
            return responses

        transport.auth_interactive(username, duo_handler)

        if not transport.is_authenticated():
            print("认证失败: 请检查用户名、密码或DUO认证情况")
            return False

        # 建立 SSHClient 并绑定已认证的 Transport
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client._transport = transport

    except paramiko.AuthenticationException as e:
        print(f"认证失败: {e}")
        return False
    except paramiko.SSHException as e:
        print(f"SSH连接错误: {e}")
        return False
    except Exception as e:
        print(f"发生错误: {e}")
        return False

    # 上传公钥到服务器 authorized_keys
    try:
        print("正在将公钥写入服务器 authorized_keys...")
        command = (
            f'mkdir -p ~/.ssh && '
            f'echo "{public_key}" >> ~/.ssh/authorized_keys && '
            f'chmod 600 ~/.ssh/authorized_keys && chmod 700 ~/.ssh'
        )
        stdin, stdout, stderr = client.exec_command(command)
        exit_status = stdout.channel.recv_exit_status()
        if exit_status == 0:
            print("SSH密钥已成功上传到服务器")
            return True
        else:
            error = stderr.read().decode()
            print(f"上传SSH密钥时出错: {error}")
            return False
    finally:
        client.close()


def main():
    """
    主函数，处理命令行参数并调用生成上传函数
    """
    parser = argparse.ArgumentParser(description='SSH密钥生成和上传工具')
    parser.add_argument('-u', '--username', required=True, help='用户名')
    parser.add_argument('-p', '--password', required=True, help='密码')
    parser.add_argument('-H', '--host', default='hpc3.rcic.uci.edu', help='服务器地址（默认：hpc3.rcic.uci.edu）')
    parser.add_argument('-P', '--port', type=int, default=22, help='SSH端口（默认：22）')
    parser.add_argument('-c', '--comment', help='SSH密钥备注')
    parser.add_argument('-f', '--force', action='store_true', help='强制覆盖现有密钥')
    
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
        print("操作成功完成！")
    else:
        print("操作未完成，请检查错误信息。")
        exit(1)


def test():
    """
    用于测试的函数, 示例调用:
      1) 强制覆盖现有密钥
      2) 自动触发Duo Push
      3) 上传公钥
    """
    print("使用测试参数运行...")
    result = generate_and_upload_ssh_key(
        username="liangys5",       # 替换成你自己的用户名
        password="GoodLuck2023!",  # 替换成你的真实密码
        host="hpc3.rcic.uci.edu",
        port=22,
        force=True
    )
    if result:
        print("测试成功完成!")
    else:
        print("测试失败, 请检查错误信息。")


if __name__ == "__main__":
    if len(sys.argv) == 1 or (len(sys.argv) > 1 and sys.argv[1] == "--test"):
        # 如果没有参数或第一个参数是 --test，则运行测试函数
        test()
    else:
        # 否则正常运行 main 函数处理命令行参数
        main()
