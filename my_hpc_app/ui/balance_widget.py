#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, 
                           QTableWidget, QTableWidgetItem, QHeaderView, QStyle, 
                           QFrame, QSplitter, QGridLayout, QProgressBar)
from PyQt5.QtCore import Qt, pyqtSlot
from PyQt5.QtGui import QFont, QColor, QBrush

import logging
from modules.balance import BalanceManager
from modules.auth import HPC_SERVER, get_all_existing_users

# 配置日志
logger = logging.getLogger('BalanceWidget')

class BalanceWidget(QWidget):
    """账户可用计算余额组件，显示用户的计算资源使用情况和余额"""
    
    def __init__(self, parent=None, username=None):
        super().__init__(parent)
        
        # 用户信息
        self.username = username
        self.balance_manager = None
        
        # 账户数据
        self.balance_data = None
        
        # 初始化余额管理器
        self.init_balance_manager()
        
        # 初始化UI
        self.init_ui()
        
        # 加载数据
        if self.balance_manager:
            self.refresh_balance()
    
    def init_balance_manager(self):
        """初始化余额管理器"""
        if not self.username:
            return
        
        # 获取SSH密钥路径
        users = get_all_existing_users()
        key_path = None
        
        for user in users:
            if user['username'] == self.username:
                key_path = user['key_path']
                break
        
        if not key_path:
            return
        
        # 创建余额管理器
        self.balance_manager = BalanceManager(
            hostname=HPC_SERVER,
            username=self.username,
            key_path=key_path
        )
        
        # 连接信号
        self.balance_manager.balance_updated.connect(self.update_balance_data)
        self.balance_manager.error_occurred.connect(self.show_error)
    
    def init_ui(self):
        """初始化UI组件"""
        main_layout = QVBoxLayout(self)
        
        # 顶部控制栏
        control_layout = QHBoxLayout()
        
        # 刷新按钮带图标
        self.refresh_btn = QPushButton("刷新余额信息")
        self.refresh_btn.setIcon(self.style().standardIcon(QStyle.SP_BrowserReload))
        self.refresh_btn.clicked.connect(self.refresh_balance)
        control_layout.addWidget(self.refresh_btn)
        
        # 刷新状态指示器
        self.refresh_indicator = QLabel("就绪")
        self.refresh_indicator.setStyleSheet("color: green;")
        control_layout.addWidget(self.refresh_indicator)
        
        control_layout.addStretch()
        
        # 添加控制栏到主布局
        main_layout.addLayout(control_layout)
        
        # 总览面板
        overview_frame = QFrame()
        overview_frame.setFrameShape(QFrame.StyledPanel)
        overview_layout = QGridLayout(overview_frame)
        
        # 用户名标签
        username_layout = QHBoxLayout()
        username_label = QLabel("用户名:")
        username_label.setFont(QFont('Arial', 12, QFont.Bold))
        username_layout.addWidget(username_label)
        
        self.username_value = QLabel(self.username or "未登录")
        self.username_value.setFont(QFont('Arial', 12))
        username_layout.addWidget(self.username_value)
        username_layout.addStretch()
        
        # 总可用资源进度条
        resource_layout = QVBoxLayout()
        resource_label = QLabel("总计算资源:")
        resource_label.setFont(QFont('Arial', 12, QFont.Bold))
        resource_layout.addWidget(resource_label)
        
        self.resource_progress = QProgressBar()
        self.resource_progress.setTextVisible(True)
        self.resource_progress.setFormat("已使用: %v SUs / 总额度: %m SUs (%p%)")
        resource_layout.addWidget(self.resource_progress)
        
        # 添加到网格布局
        overview_layout.addLayout(username_layout, 0, 0)
        overview_layout.addLayout(resource_layout, 1, 0)
        
        # 账户表格
        self.accounts_table = QTableWidget()
        self.accounts_table.setColumnCount(5)
        self.accounts_table.setHorizontalHeaderLabels([
            "账户名称", "个人使用量", "账户总使用量", "账户限额", "可用量"
        ])
        self.accounts_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.accounts_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.accounts_table.setSortingEnabled(True)
        
        # 创建分割器，在顶部放置概览，在底部放置详细信息
        splitter = QSplitter(Qt.Vertical)
        splitter.addWidget(overview_frame)
        splitter.addWidget(self.accounts_table)
        
        # 设置默认分割比例
        splitter.setSizes([100, 500])
        
        # 添加分割器到主布局
        main_layout.addWidget(splitter)
        
        # 底部状态栏
        status_layout = QHBoxLayout()
        
        self.status_label = QLabel("就绪")
        status_layout.addWidget(self.status_label)
        
        # 添加状态栏到主布局
        main_layout.addLayout(status_layout)
    
    @pyqtSlot()
    def refresh_balance(self):
        """刷新余额信息"""
        if not self.balance_manager:
            self.show_error("未设置余额管理器，无法获取数据")
            return
        
        # 更新UI状态
        self.refresh_btn.setEnabled(False)
        self.refresh_indicator.setText("正在刷新...")
        self.refresh_indicator.setStyleSheet("color: orange;")
        
        # 获取余额信息
        self.balance_manager.refresh_balance()
    
    @pyqtSlot(dict)
    def update_balance_data(self, balance_data):
        """更新余额数据"""
        self.balance_data = balance_data
        
        # 更新UI
        self.update_ui()
        
        # 恢复UI状态
        self.refresh_btn.setEnabled(True)
        self.refresh_indicator.setText("就绪")
        self.refresh_indicator.setStyleSheet("color: green;")
    
    def update_ui(self):
        """更新UI显示"""
        if not self.balance_data:
            return
        
        # 更新用户名
        self.username_value.setText(self.balance_data['username'])
        
        # 更新总资源进度条
        total_usage = self.balance_data['total_usage']
        total_available = self.balance_data['total_available']
        total_limit = total_usage + total_available
        
        self.resource_progress.setMaximum(total_limit if total_limit > 0 else 100)
        self.resource_progress.setValue(total_usage)
        
        # 设置进度条颜色
        usage_ratio = (total_usage / total_limit * 100) if total_limit > 0 else 0
        self.set_progress_bar_color(usage_ratio)
        
        # 更新账户表格
        self.update_accounts_table()
    
    def update_accounts_table(self):
        """更新账户表格"""
        # 禁用排序以防重新加载时的混乱
        self.accounts_table.setSortingEnabled(False)
        self.accounts_table.setRowCount(0)
        
        if not self.balance_data or not self.balance_data['accounts']:
            return
        
        # 按账户类型排序：个人账户在前，共享账户在后
        sorted_accounts = sorted(
            self.balance_data['accounts'], 
            key=lambda x: (0 if x['is_personal'] else 1, x['name'])
        )
        
        # 为每个账户添加一行
        for row, account in enumerate(sorted_accounts):
            self.accounts_table.insertRow(row)
            
            # 账户名称
            name_item = QTableWidgetItem(account['name'])
            # 个人账户标记为粗体
            if account['is_personal']:
                font = name_item.font()
                font.setBold(True)
                name_item.setFont(font)
                name_item.setForeground(QBrush(QColor(0, 0, 255)))  # 个人账户蓝色
            self.accounts_table.setItem(row, 0, name_item)
            
            # 个人使用量
            user_usage_item = QTableWidgetItem(f"{account['user_usage']:,}")
            self.accounts_table.setItem(row, 1, user_usage_item)
            
            # 账户总使用量
            account_usage_item = QTableWidgetItem(f"{account['account_usage']:,}")
            self.accounts_table.setItem(row, 2, account_usage_item)
            
            # 账户限额
            account_limit_item = QTableWidgetItem(f"{account['account_limit']:,}")
            self.accounts_table.setItem(row, 3, account_limit_item)
            
            # 可用量
            available_item = QTableWidgetItem(f"{account['available']:,}")
            # 根据可用量设置颜色
            usage_ratio = (account['account_usage'] / account['account_limit'] * 100) if account['account_limit'] > 0 else 0
            self.set_item_color_by_usage(available_item, usage_ratio)
            self.accounts_table.setItem(row, 4, available_item)
        
        # 恢复排序
        self.accounts_table.setSortingEnabled(True)
    
    def set_progress_bar_color(self, usage_ratio):
        """根据使用率设置进度条颜色"""
        if usage_ratio > 90:
            self.resource_progress.setStyleSheet("""
                QProgressBar::chunk { background-color: red; }
                QProgressBar { text-align: center; }
            """)
        elif usage_ratio > 70:
            self.resource_progress.setStyleSheet("""
                QProgressBar::chunk { background-color: orange; }
                QProgressBar { text-align: center; }
            """)
        else:
            self.resource_progress.setStyleSheet("""
                QProgressBar::chunk { background-color: green; }
                QProgressBar { text-align: center; }
            """)
    
    def set_item_color_by_usage(self, item, usage_ratio):
        """根据使用率设置表格项颜色"""
        if usage_ratio > 90:
            item.setForeground(QBrush(QColor(255, 0, 0)))  # 红色
        elif usage_ratio > 70:
            item.setForeground(QBrush(QColor(255, 165, 0)))  # 橙色
        else:
            item.setForeground(QBrush(QColor(0, 128, 0)))  # 绿色
    
    def show_error(self, error_msg):
        """显示错误信息"""
        self.refresh_indicator.setText(f"错误: {error_msg}")
        self.refresh_indicator.setStyleSheet("color: red;")
        logger.error(error_msg)
        
        # 启用刷新按钮
        self.refresh_btn.setEnabled(True) 