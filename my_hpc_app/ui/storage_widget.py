#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, 
                           QFrame, QGridLayout, QProgressBar, QGroupBox, QTextEdit)
from PyQt5.QtCore import Qt, pyqtSlot
from PyQt5.QtGui import QFont

import logging
from modules.storage import StorageManager
from modules.auth import HPC_SERVER, get_all_existing_users

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger('StorageWidget')

class StorageWidget(QWidget):
    """存储管理组件，显示用户在HPC上的各种存储空间使用情况"""
    
    def __init__(self, parent=None, username=None):
        super().__init__(parent)
        
        # 用户信息
        self.username = username
        self.storage_manager = None
        
        # 存储数据
        self.storage_data = None
        
        # 初始化UI
        self.init_ui()
        
        # 初始化存储管理器
        self.init_storage_manager()
    
    def init_storage_manager(self):
        """初始化存储管理器"""
        if not self.username:
            self.status_label.setText("错误: 未提供用户名")
            return
        
        # 获取SSH密钥路径
        users = get_all_existing_users()
        key_path = None
        
        for user in users:
            if user['username'] == self.username:
                key_path = user['key_path']
                break
        
        if not key_path:
            self.status_label.setText(f"错误: 未找到用户 {self.username} 的SSH密钥")
            return
        
        try:
            # 创建存储管理器
            self.storage_manager = StorageManager(
                hostname=HPC_SERVER,
                username=self.username,
                key_path=key_path
            )
            
            # 连接信号
            self.storage_manager.storage_updated.connect(self.update_storage_data)
            self.storage_manager.error_occurred.connect(self.show_error)
            
            # 更新状态
            self.status_label.setText("已初始化存储管理器，准备就绪")
            
            # 启动刷新
            self.refresh_storage_info()
        except Exception as e:
            self.status_label.setText(f"错误: 初始化存储管理器失败 - {str(e)}")
    
    def init_ui(self):
        """初始化UI组件"""
        main_layout = QVBoxLayout(self)
        
        # 顶部控制栏
        control_layout = QHBoxLayout()
        
        # 刷新按钮
        self.refresh_btn = QPushButton("刷新存储信息")
        self.refresh_btn.clicked.connect(self.refresh_storage_info)
        control_layout.addWidget(self.refresh_btn)
        
        # 刷新状态指示器
        self.refresh_indicator = QLabel("就绪")
        control_layout.addWidget(self.refresh_indicator)
        
        control_layout.addStretch()
        
        # 添加控制栏到主布局
        main_layout.addLayout(control_layout)
        
        # 创建存储概览分组框
        overview_group = QGroupBox("存储空间概览")
        overview_layout = QVBoxLayout(overview_group)
        
        # 创建各类存储空间的组
        self.create_storage_section("HOME目录", overview_layout)
        self.create_storage_section("个人DFS空间", overview_layout)
        self.create_storage_section("实验室共享DFS", overview_layout)
        self.create_storage_section("个人CRSP空间", overview_layout)
        self.create_storage_section("实验室共享CRSP", overview_layout)
        self.create_storage_section("临时存储(Scratch)", overview_layout)
        
        # 添加到主布局
        main_layout.addWidget(overview_group)
        
        # 底部状态栏
        self.status_label = QLabel("初始化中...")
        main_layout.addWidget(self.status_label)
    
    def create_storage_section(self, title, parent_layout):
        """创建存储区域显示部分"""
        frame = QFrame()
        frame.setFrameShape(QFrame.StyledPanel)
        layout = QGridLayout(frame)
        
        # 标题
        title_label = QLabel(title)
        title_label.setFont(QFont('Arial', 12, QFont.Bold))
        layout.addWidget(title_label, 0, 0, 1, 2)
        
        # 路径标签
        path_label = QLabel("路径:")
        layout.addWidget(path_label, 1, 0)
        
        path_value = QLabel("加载中...")
        path_value.setObjectName(f"{title.lower().replace(' ', '_').replace('(', '').replace(')', '')}_path")
        layout.addWidget(path_value, 1, 1)
        
        # 使用情况标签
        usage_label = QLabel("使用情况:")
        layout.addWidget(usage_label, 2, 0)
        
        # 进度条
        progress = QProgressBar()
        progress.setObjectName(f"{title.lower().replace(' ', '_').replace('(', '').replace(')', '')}_progress")
        progress.setFormat("%v / %m (%p%)")
        layout.addWidget(progress, 2, 1)
        
        # 添加到父布局
        parent_layout.addWidget(frame)
    
    @pyqtSlot()
    def refresh_storage_info(self):
        """刷新存储信息"""
        if not self.storage_manager:
            self.show_error("未设置存储管理器，无法获取数据")
            return
        
        # 更新UI状态
        self.refresh_btn.setEnabled(False)
        self.refresh_indicator.setText("正在刷新...")
        self.status_label.setText("正在获取存储信息...")
        
        # 获取存储信息
        try:
            self.storage_manager.refresh_storage_info()
        except Exception as e:
            self.show_error(f"刷新存储信息时出错: {str(e)}")
            self.refresh_btn.setEnabled(True)
    
    @pyqtSlot(dict)
    def update_storage_data(self, storage_data):
        """更新存储数据"""
        self.storage_data = storage_data
        
        # 更新UI
        try:
            self.update_ui()
        except Exception as e:
            self.show_error(f"更新UI时出错: {str(e)}")
        
        # 恢复UI状态
        self.refresh_btn.setEnabled(True)
        self.refresh_indicator.setText("刷新完成")
        self.status_label.setText("存储信息已更新")
    
    def update_ui(self):
        """更新UI显示"""
        if not self.storage_data:
            return
        
        # 更新HOME信息
        if 'home' in self.storage_data:
            self.update_storage_section_with_data(self.storage_data['home'], "HOME目录")
        
        # 更新个人DFS信息
        if 'personal_dfs' in self.storage_data:
            self.update_storage_section_with_data(self.storage_data['personal_dfs'], "个人DFS空间")
        
        # 更新实验室DFS信息
        if 'lab_dfs' in self.storage_data and self.storage_data['lab_dfs']:
            self.update_storage_section_with_data(self.storage_data['lab_dfs'][0], "实验室共享DFS")
        
        # 更新个人CRSP信息
        if 'personal_crsp' in self.storage_data:
            self.update_storage_section_with_data(self.storage_data['personal_crsp'], "个人CRSP空间")
        
        # 更新实验室CRSP信息
        if 'lab_crsp' in self.storage_data:
            self.update_storage_section_with_data(self.storage_data['lab_crsp'], "实验室共享CRSP")
        
        # 更新Scratch信息
        if 'scratch' in self.storage_data:
            self.update_storage_section_with_data(self.storage_data['scratch'], "临时存储(Scratch)")
    
    def update_storage_section_with_data(self, data, ui_key):
        """使用数据更新存储部分UI"""
        ui_base = ui_key.lower().replace(' ', '_').replace('(', '').replace(')', '')
        
        # 更新路径
        path_label = self.findChild(QLabel, f"{ui_base}_path")
        if path_label:
            path_label.setText(data.get('path', '未知'))
        
        # 更新进度条
        progress = self.findChild(QProgressBar, f"{ui_base}_progress")
        if progress:
            if data.get('exists', False):
                # 尝试转换使用百分比为数字
                try:
                    use_percent = float(data.get('use_percent', 0))
                except:
                    use_percent = 0
                
                # 设置进度条
                progress.setMaximum(100)
                progress.setValue(int(use_percent))
                progress.setFormat(f"{data.get('used', '?')} / {data.get('total', '?')} ({use_percent}%)")
                
                # 设置颜色
                self.set_progress_bar_color(progress, use_percent)
            else:
                progress.setValue(0)
                progress.setFormat(data.get('error', "目录不存在"))
    
    def set_progress_bar_color(self, progress_bar, usage_ratio):
        """根据使用率设置进度条颜色"""
        if usage_ratio > 90:
            progress_bar.setStyleSheet("""
                QProgressBar::chunk { background-color: red; }
                QProgressBar { text-align: center; }
            """)
        elif usage_ratio > 70:
            progress_bar.setStyleSheet("""
                QProgressBar::chunk { background-color: orange; }
                QProgressBar { text-align: center; }
            """)
        else:
            progress_bar.setStyleSheet("""
                QProgressBar::chunk { background-color: green; }
                QProgressBar { text-align: center; }
            """)
    
    def show_error(self, error_msg):
        """显示错误信息"""
        self.refresh_indicator.setText(f"错误")
        self.status_label.setText(f"错误: {error_msg}")
        logger.error(error_msg)
        
        # 启用刷新按钮
        self.refresh_btn.setEnabled(True) 