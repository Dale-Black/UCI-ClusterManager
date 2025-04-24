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
    """任务提交对话框"""
    
    def __init__(self, parent=None, partitions=None):
        super().__init__(parent)
        self.setWindowTitle("提交新任务")
        self.resize(700, 500)
        
        # 分区列表
        self.partitions = partitions or []
        
        # 初始化UI
        self.initUI()
    
    def initUI(self):
        """初始化UI组件"""
        layout = QVBoxLayout(self)
        
        # 作业配置选项卡
        tab_widget = QTabWidget()
        
        # 基本选项卡
        basic_tab = QWidget()
        basic_layout = QFormLayout(basic_tab)
        
        # 作业名称
        self.job_name = QLineEdit()
        self.job_name.setText("my_job")
        basic_layout.addRow("作业名称:", self.job_name)
        
        # 分区选择
        self.partition = QComboBox()
        if self.partitions:
            for p in self.partitions:
                self.partition.addItem(p['name'], p)
        else:
            self.partition.addItem("default")
        basic_layout.addRow("分区:", self.partition)
        
        # 节点数量
        self.nodes = QSpinBox()
        self.nodes.setMinimum(1)
        self.nodes.setMaximum(100)
        self.nodes.setValue(1)
        basic_layout.addRow("节点数:", self.nodes)
        
        # CPU核心数
        self.cpus = QSpinBox()
        self.cpus.setMinimum(1)
        self.cpus.setMaximum(128)
        self.cpus.setValue(1)
        basic_layout.addRow("CPU核心数:", self.cpus)
        
        # 内存需求
        self.memory = QLineEdit()
        self.memory.setText("1G")
        basic_layout.addRow("内存需求:", self.memory)
        
        # 运行时间限制
        self.time_limit = QLineEdit()
        self.time_limit.setText("1:00:00")  # 1小时
        basic_layout.addRow("时间限制:", self.time_limit)
        
        # 输出文件
        self.output_file = QLineEdit()
        self.output_file.setText("slurm-%j.out")
        basic_layout.addRow("输出文件:", self.output_file)
        
        # 添加基本选项卡
        tab_widget.addTab(basic_tab, "基本设置")
        
        # 高级选项卡
        advanced_tab = QWidget()
        advanced_layout = QFormLayout(advanced_tab)
        
        # 电子邮件通知
        self.email = QLineEdit()
        advanced_layout.addRow("邮箱地址:", self.email)
        
        # 通知类型
        self.email_type = QComboBox()
        self.email_type.addItems(["NONE", "BEGIN", "END", "FAIL", "ALL"])
        advanced_layout.addRow("通知类型:", self.email_type)
        
        # GPU需求
        self.gpu = QSpinBox()
        self.gpu.setMinimum(0)
        self.gpu.setMaximum(8)
        self.gpu.setValue(0)
        advanced_layout.addRow("GPU数量:", self.gpu)
        
        # 添加高级选项卡
        tab_widget.addTab(advanced_tab, "高级设置")
        
        # 脚本编辑器选项卡
        script_tab = QWidget()
        script_layout = QVBoxLayout(script_tab)
        
        # 添加说明标签
        info_label = QLabel("在下方编辑作业脚本：")
        script_layout.addWidget(info_label)
        
        # 脚本编辑器
        self.script_editor = QTextEdit()
        self.script_editor.setFont(QFont("Courier New", 10))
        
        # 设置默认脚本模板
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

# 加载模块
module load python/3.9.0

# 打印当前工作目录
echo "当前工作目录: $PWD"
echo "当前节点: $(hostname)"

# 在这里添加您的命令
echo "Hello, Slurm!"
sleep 10
echo "任务完成"
"""
        self.script_editor.setText(default_script)
        script_layout.addWidget(self.script_editor)
        
        # 脚本模板按钮
        template_layout = QHBoxLayout()
        update_template_btn = QPushButton("更新脚本模板")
        update_template_btn.clicked.connect(self.update_script_template)
        template_layout.addWidget(update_template_btn)
        
        # 保存脚本按钮
        save_script_btn = QPushButton("保存脚本到本地")
        save_script_btn.clicked.connect(self.save_script)
        template_layout.addWidget(save_script_btn)
        
        # 导入脚本按钮
        load_script_btn = QPushButton("从本地导入脚本")
        load_script_btn.clicked.connect(self.load_script)
        template_layout.addWidget(load_script_btn)
        
        script_layout.addLayout(template_layout)
        
        # 添加脚本选项卡
        tab_widget.addTab(script_tab, "脚本编辑")
        
        # 添加选项卡组件到主布局
        layout.addWidget(tab_widget)
        
        # 设置"更新脚本模板"为默认选中状态
        tab_widget.setCurrentIndex(2)  # 脚本编辑选项卡
        
        # 添加按钮
        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)
        
        # 初次更新脚本模板
        self.update_script_template()
    
    def update_script_template(self):
        """根据设置更新脚本模板"""
        # 获取设置值
        job_name = self.job_name.text()
        partition = self.partition.currentText()
        nodes = self.nodes.value()
        cpus = self.cpus.value()
        memory = self.memory.text()
        time_limit = self.time_limit.text()
        output_file = self.output_file.text()
        
        # 电子邮件设置
        email_settings = ""
        if self.email.text():
            email_settings = f"#SBATCH --mail-user={self.email.text()}\n#SBATCH --mail-type={self.email_type.currentText()}"
        
        # GPU设置
        gpu_settings = ""
        if self.gpu.value() > 0:
            gpu_settings = f"#SBATCH --gres=gpu:{self.gpu.value()}"
        
        # 获取当前的脚本内容
        current_script = self.script_editor.toPlainText()
        
        # 只替换脚本头部的SBATCH指令
        header_end = current_script.find("# 加载模块")
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
"""
            new_script = header + current_script[header_end:]
            self.script_editor.setText(new_script)
        else:
            # 如果找不到标记，则保留用户的全部内容
            pass
    
    def save_script(self):
        """将脚本保存到本地文件"""
        filename, _ = QFileDialog.getSaveFileName(
            self, "保存脚本", "", "Shell脚本 (*.sh);;所有文件 (*)"
        )
        if filename:
            with open(filename, 'w') as f:
                f.write(self.script_editor.toPlainText())
            QMessageBox.information(self, "成功", f"脚本已保存到 {filename}")
    
    def load_script(self):
        """从本地文件加载脚本"""
        filename, _ = QFileDialog.getOpenFileName(
            self, "加载脚本", "", "Shell脚本 (*.sh);;所有文件 (*)"
        )
        if filename:
            with open(filename, 'r') as f:
                self.script_editor.setText(f.read())
            QMessageBox.information(self, "成功", f"已加载脚本 {filename}")
    
    def get_script_content(self):
        """获取脚本内容"""
        return self.script_editor.toPlainText()


class JobDetailDialog(QDialog):
    """任务详情对话框"""
    
    def __init__(self, parent=None, job=None, job_details=None):
        super().__init__(parent)
        self.setWindowTitle("任务详情")
        self.resize(600, 400)
        
        self.job = job
        self.job_details = job_details
        
        # 初始化UI
        self.initUI()
    
    def initUI(self):
        """初始化UI组件"""
        layout = QVBoxLayout(self)
        
        # 基本信息部分
        if self.job:
            basic_info = QGroupBox("基本信息")
            basic_layout = QFormLayout(basic_info)
            
            basic_layout.addRow("任务ID:", QLabel(self.job.get('id', 'N/A')))
            basic_layout.addRow("任务名称:", QLabel(self.job.get('name', 'N/A')))
            basic_layout.addRow("状态:", QLabel(self.job.get('state', 'N/A')))
            basic_layout.addRow("运行时间:", QLabel(self.job.get('time', 'N/A')))
            basic_layout.addRow("时间限制:", QLabel(self.job.get('time_limit', 'N/A')))
            basic_layout.addRow("节点数:", QLabel(self.job.get('nodes', 'N/A')))
            basic_layout.addRow("CPU数:", QLabel(self.job.get('cpus', 'N/A')))
            
            layout.addWidget(basic_info)
        
        # 详细信息部分
        if self.job_details:
            detail_info = QGroupBox("详细信息")
            detail_layout = QFormLayout(detail_info)
            
            # 添加所有详细信息
            for key, value in self.job_details.items():
                detail_layout.addRow(f"{key}:", QLabel(str(value)))
            
            layout.addWidget(detail_info)
        else:
            layout.addWidget(QLabel("无法获取详细信息"))
        
        # 添加按钮
        button_box = QDialogButtonBox(QDialogButtonBox.Close)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)


class TaskManagerWidget(QWidget):
    """任务管理组件"""
    
    def __init__(self, parent=None, username=None):
        super().__init__(parent)
        
        # 用户信息
        self.username = username
        self.slurm_manager = None
        
        # 获取SSH密钥路径
        self.init_slurm_manager()
        
        # 初始化UI
        self.initUI()
        
        # 定时刷新
        self.refresh_timer = QTimer(self)
        self.refresh_timer.timeout.connect(self.refresh_jobs)
        self.refresh_timer.start(30000)  # 30秒刷新一次
        
        # 加载任务列表
        self.refresh_jobs()
    
    def init_slurm_manager(self):
        """初始化Slurm管理器"""
        if not self.username:
            QMessageBox.warning(self, "警告", "未设置用户名，无法管理任务")
            return
        
        # 获取SSH密钥路径
        users = get_all_existing_users()
        key_path = None
        
        for user in users:
            if user['username'] == self.username:
                key_path = user['key_path']
                break
        
        if not key_path:
            QMessageBox.warning(self, "警告", f"未找到用户 {self.username} 的SSH密钥")
            return
        
        # 创建Slurm管理器
        self.slurm_manager = SlurmManager(
            hostname=HPC_SERVER,
            username=self.username,
            key_path=key_path
        )
        
        # 连接信号
        self.slurm_manager.error_occurred.connect(self.show_error)
        self.slurm_manager.job_submitted.connect(self.on_job_submitted)
        self.slurm_manager.job_canceled.connect(self.on_job_canceled)
    
    def initUI(self):
        """初始化UI组件"""
        main_layout = QVBoxLayout(self)
        
        # 顶部控制栏
        control_layout = QHBoxLayout()
        
        # 刷新按钮
        refresh_btn = QPushButton("刷新任务列表")
        refresh_btn.clicked.connect(self.refresh_jobs)
        control_layout.addWidget(refresh_btn)
        
        # 新建任务按钮
        submit_btn = QPushButton("提交新任务")
        submit_btn.clicked.connect(self.show_job_submission_dialog)
        control_layout.addWidget(submit_btn)
        
        # 自动刷新复选框
        self.auto_refresh = QCheckBox("自动刷新")
        self.auto_refresh.setChecked(True)
        self.auto_refresh.stateChanged.connect(self.toggle_auto_refresh)
        control_layout.addWidget(self.auto_refresh)
        
        # 状态过滤器
        self.status_filter = QComboBox()
        self.status_filter.addItems(["全部", "运行中", "排队中", "已完成", "已取消", "失败"])
        self.status_filter.currentTextChanged.connect(self.apply_filter)
        control_layout.addWidget(QLabel("状态过滤:"))
        control_layout.addWidget(self.status_filter)
        
        control_layout.addStretch()
        
        # 添加控制栏到主布局
        main_layout.addLayout(control_layout)
        
        # 任务表格
        self.jobs_table = QTableWidget()
        self.jobs_table.setColumnCount(8)
        self.jobs_table.setHorizontalHeaderLabels([
            "任务ID", "任务名称", "状态", "运行时间", "时间限制", "节点数", "CPU数", "备注"
        ])
        self.jobs_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.jobs_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.jobs_table.setAlternatingRowColors(True)
        self.jobs_table.horizontalHeader().setStretchLastSection(True)
        self.jobs_table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.jobs_table.customContextMenuRequested.connect(self.show_context_menu)
        self.jobs_table.doubleClicked.connect(self.show_job_details)
        
        # 调整列宽
        self.jobs_table.setColumnWidth(0, 80)   # ID
        self.jobs_table.setColumnWidth(1, 180)  # 名称
        self.jobs_table.setColumnWidth(2, 80)   # 状态
        self.jobs_table.setColumnWidth(3, 80)   # 运行时间
        self.jobs_table.setColumnWidth(4, 80)   # 时间限制
        self.jobs_table.setColumnWidth(5, 60)   # 节点数
        self.jobs_table.setColumnWidth(6, 60)   # CPU数
        
        # 添加表格到主布局
        main_layout.addWidget(self.jobs_table)
        
        # 底部状态栏
        status_layout = QHBoxLayout()
        
        self.status_label = QLabel("就绪")
        status_layout.addWidget(self.status_label)
        
        status_layout.addStretch()
        
        self.job_count_label = QLabel("任务数: 0")
        status_layout.addWidget(self.job_count_label)
        
        # 添加状态栏到主布局
        main_layout.addLayout(status_layout)
    
    @pyqtSlot()
    def refresh_jobs(self):
        """刷新任务列表"""
        if not self.slurm_manager:
            self.status_label.setText("Slurm管理器未初始化")
            return
        
        self.status_label.setText("正在加载任务列表...")
        
        # 获取任务列表
        jobs = self.slurm_manager.get_jobs()
        
        # 清空表格
        self.jobs_table.setRowCount(0)
        
        # 填充表格
        for i, job in enumerate(jobs):
            self.jobs_table.insertRow(i)
            
            # 设置单元格
            self.jobs_table.setItem(i, 0, QTableWidgetItem(job.get('id', 'N/A')))
            self.jobs_table.setItem(i, 1, QTableWidgetItem(job.get('name', 'N/A')))
            
            # 根据状态设置颜色
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
        
        # 更新任务计数
        self.job_count_label.setText(f"任务数: {len(jobs)}")
        
        # 应用过滤器
        self.apply_filter()
        
        # 更新状态
        self.status_label.setText(f"任务列表已更新 ({time.strftime('%H:%M:%S')})")
    
    def apply_filter(self):
        """应用状态过滤器"""
        filter_text = self.status_filter.currentText()
        
        # 映射状态文本到任务状态
        status_map = {
            "全部": None,
            "运行中": "RUNNING",
            "排队中": "PENDING",
            "已完成": "COMPLETED",
            "已取消": "CANCELLED",
            "失败": "FAILED"
        }
        
        filter_status = status_map.get(filter_text)
        
        # 应用过滤器
        for i in range(self.jobs_table.rowCount()):
            state_item = self.jobs_table.item(i, 2)
            if state_item:
                state = state_item.text()
                if filter_status is None or state == filter_status:
                    self.jobs_table.setRowHidden(i, False)
                else:
                    self.jobs_table.setRowHidden(i, True)
    
    def toggle_auto_refresh(self, state):
        """切换自动刷新"""
        if state == Qt.Checked:
            self.refresh_timer.start(30000)
        else:
            self.refresh_timer.stop()
    
    def show_job_submission_dialog(self):
        """显示任务提交对话框"""
        if not self.slurm_manager:
            QMessageBox.warning(self, "警告", "Slurm管理器未初始化")
            return
        
        # 获取分区信息
        partitions = self.slurm_manager.get_partition_info()
        
        # 显示提交对话框
        dialog = JobSubmissionDialog(self, partitions)
        result = dialog.exec_()
        
        if result == QDialog.Accepted:
            # 获取脚本内容
            script_content = dialog.get_script_content()
            
            # 提交任务
            job_id = self.slurm_manager.submit_job(script_content)
            if job_id:
                QMessageBox.information(self, "成功", f"任务已提交，ID: {job_id}")
                # 刷新任务列表
                self.refresh_jobs()
            else:
                QMessageBox.warning(self, "提交失败", "任务提交失败，请检查脚本")
    
    def show_job_details(self):
        """显示任务详情"""
        selected_rows = self.jobs_table.selectionModel().selectedRows()
        if not selected_rows:
            return
        
        # 获取选中行的任务ID
        row = selected_rows[0].row()
        job_id = self.jobs_table.item(row, 0).text()
        
        # 构建任务对象
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
        
        # 获取任务详情
        job_details = self.slurm_manager.get_job_details(job_id)
        
        # 显示详情对话框
        dialog = JobDetailDialog(self, job, job_details)
        dialog.exec_()
    
    def show_context_menu(self, position):
        """显示右键菜单"""
        selected_rows = self.jobs_table.selectionModel().selectedRows()
        if not selected_rows:
            return
        
        # 创建右键菜单
        menu = QMenu(self)
        
        # 添加菜单项
        details_action = menu.addAction("任务详情")
        cancel_action = menu.addAction("取消任务")
        
        # 执行菜单
        action = menu.exec_(self.jobs_table.mapToGlobal(position))
        
        # 处理菜单动作
        if action == details_action:
            self.show_job_details()
        elif action == cancel_action:
            self.cancel_selected_job()
    
    def cancel_selected_job(self):
        """取消选中的任务"""
        selected_rows = self.jobs_table.selectionModel().selectedRows()
        if not selected_rows:
            return
        
        # 获取选中行的任务ID
        row = selected_rows[0].row()
        job_id = self.jobs_table.item(row, 0).text()
        job_name = self.jobs_table.item(row, 1).text()
        
        # 确认取消
        confirm = QMessageBox.question(
            self,
            "确认取消",
            f"确定要取消任务 {job_id} ({job_name}) 吗？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        
        if confirm == QMessageBox.Yes:
            # 取消任务
            success = self.slurm_manager.cancel_job(job_id)
            if success:
                QMessageBox.information(self, "成功", f"任务 {job_id} 已取消")
                # 刷新任务列表
                self.refresh_jobs()
            else:
                QMessageBox.warning(self, "失败", f"取消任务 {job_id} 失败")
    
    @pyqtSlot(str)
    def show_error(self, message):
        """显示错误消息"""
        QMessageBox.warning(self, "错误", message)
    
    @pyqtSlot(str)
    def on_job_submitted(self, job_id):
        """任务提交成功的槽函数"""
        self.status_label.setText(f"任务已提交: {job_id}")
    
    @pyqtSlot(str)
    def on_job_canceled(self, job_id):
        """任务取消成功的槽函数"""
        self.status_label.setText(f"任务已取消: {job_id}") 