# HPC管理系统

这是一个用于高性能计算（HPC）集群的管理系统，基于PyQt5开发的桌面应用程序。该系统提供了以下主要功能：

1. SSH密钥管理和自动登录
2. Slurm任务管理（提交、监控、取消任务）
3. 集群节点状态监控
4. 用户账户管理
5. 存储空间管理

## 安装方法

### 依赖环境

- Python 3.7+
- PyQt5
- paramiko
- pexpect

### 步骤

1. 克隆本仓库：
   ```
   git clone <repository-url>
   ```

2. 安装依赖：
   ```
   pip install -r requirements.txt
   ```

3. 运行应用程序：
   ```
   cd my_hpc_app
   python main.py
   ```

## 使用指南

### 登录

首次使用时，需要输入UCI ID和密码。系统会自动生成SSH密钥并上传到HPC服务器。登录成功后，下次可以直接使用密钥登录，无需再输入密码。

### 任务管理

1. **查看任务列表**：登录后默认显示任务管理界面，列出所有当前任务
2. **提交新任务**：点击"提交新任务"按钮，填写任务配置并编辑脚本
3. **任务详情**：双击任务或右键选择"任务详情"查看详细信息
4. **取消任务**：右键点击任务，选择"取消任务"

### 任务脚本编写

系统提供了Slurm脚本模板，包含常用参数配置，可以根据需要修改：

```bash
#!/bin/bash
#SBATCH --job-name=my_job
#SBATCH --partition=default
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --mem=1G
#SBATCH --time=1:00:00
#SBATCH --output=slurm-%j.out

# 加载模块
module load python/3.9.0

# 打印当前工作目录
echo "当前工作目录: $PWD"
echo "当前节点: $(hostname)"

# 在这里添加您的命令
echo "Hello, Slurm!"
sleep 10
echo "任务完成"
```

## 常见问题

1. **登录失败**：确保网络连接正常，并确认UCI ID和密码正确
2. **任务提交失败**：检查脚本内容是否有语法错误，以及是否有权限访问指定的分区

## 许可证

[MIT License](LICENSE) 