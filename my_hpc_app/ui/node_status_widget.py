#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, 
                           QTableWidget, QTableWidgetItem, QTabWidget,
                           QHeaderView, QStyle, QProgressBar, QSplitter, QFrame, QGridLayout)
from PyQt5.QtCore import Qt, QTimer, pyqtSlot, QDateTime, QThread, pyqtSignal
from PyQt5.QtGui import QFont, QColor, QIcon, QBrush
import logging
import time
from modules.node_status import NodeStatusManager
from modules.auth import HPC_SERVER, get_all_existing_users

# 配置日志
logger = logging.getLogger('NodeStatusWidget')

class RefreshWorker(QThread):
    """后台刷新数据的线程"""
    
    # 定义信号
    finished = pyqtSignal()
    error = pyqtSignal(str)
    nodes_data = pyqtSignal(list)
    
    def __init__(self, node_manager):
        """初始化刷新线程"""
        super().__init__()
        self.node_manager = node_manager
        self._stopped = False
    
    def run(self):
        """线程执行函数"""
        try:
            if self._stopped:
                return
                
            # 获取节点数据
            nodes = self.node_manager.get_all_nodes()
            if nodes:
                self.nodes_data.emit(nodes)
            else:
                self.error.emit("未获取到节点数据")
        except Exception as e:
            logger.error(f"刷新数据失败: {str(e)}")
            self.error.emit(f"刷新数据失败: {str(e)}")
        finally:
            self.finished.emit()
    
    def stop(self):
        """停止线程"""
        self._stopped = True
        if self.isRunning():
            self.wait(1000)
            if self.isRunning():
                self.terminate()

class NodeStatusWidget(QWidget):
    """节点状态组件，展示HPC集群节点信息和可用情况"""
    
    def __init__(self, parent=None, username=None):
        super().__init__(parent)
        
        # 用户信息
        self.username = username
        self.node_manager = None
        
        # 最后刷新时间
        self.last_refresh_time = None
        
        # 节点数据
        self.nodes_data = []
        
        # 刷新工作线程
        self.refresh_worker = None
        
        # 初始化节点管理器
        self.init_node_manager()
        
        # 初始化UI
        self.init_ui()
        
        # 定时刷新时间显示
        self.refresh_timer = QTimer(self)
        self.refresh_timer.timeout.connect(self.update_refresh_time)
        self.refresh_timer.start(10000)  # 每10秒更新一次时间显示
        
        # 加载数据
        self.refresh_data()
    
    def init_node_manager(self):
        """初始化节点管理器"""
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
        
        # 创建节点管理器
        self.node_manager = NodeStatusManager(
            hostname=HPC_SERVER,
            username=self.username,
            key_path=key_path
        )
        
        # 连接信号
        self.node_manager.nodes_updated.connect(self.update_nodes_data)
        self.node_manager.error_occurred.connect(self.show_error)
    
    def init_ui(self):
        """初始化UI组件"""
        main_layout = QVBoxLayout(self)
        
        # 顶部控制栏
        control_layout = QHBoxLayout()
        
        # 刷新按钮带图标
        self.refresh_btn = QPushButton("刷新节点信息")
        self.refresh_btn.setIcon(self.style().standardIcon(QStyle.SP_BrowserReload))
        self.refresh_btn.clicked.connect(self.refresh_data)
        control_layout.addWidget(self.refresh_btn)
        
        # 刷新状态指示器
        self.refresh_indicator = QLabel("就绪")
        self.refresh_indicator.setStyleSheet("color: green;")
        control_layout.addWidget(self.refresh_indicator)
        
        control_layout.addStretch()
        
        # 整体统计信息
        self.stats_label = QLabel("节点总数: 0 | CPU使用情况: 0/0 | GPU使用情况: 0/0")
        control_layout.addWidget(self.stats_label)
        
        control_layout.addStretch()
        
        # 刷新时间显示
        self.time_label = QLabel("尚未刷新")
        control_layout.addWidget(self.time_label)
        
        # 添加控制栏到主布局
        main_layout.addLayout(control_layout)
        
        # 创建标签页
        tabs = QTabWidget()
        
        # GPU节点标签页 (先创建GPU节点标签页，放在第一个位置)
        gpu_tab = QWidget()
        gpu_layout = QVBoxLayout(gpu_tab)
        
        self.gpu_nodes_table = QTableWidget()
        self.gpu_nodes_table.setColumnCount(5)
        self.gpu_nodes_table.setHorizontalHeaderLabels([
            "节点名称", "CPU使用/总数", "内存使用", 
            "GPU类型", "GPU使用/总数"
        ])
        self.gpu_nodes_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.gpu_nodes_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.gpu_nodes_table.setSortingEnabled(True)
        
        gpu_layout.addWidget(self.gpu_nodes_table)
        
        # 所有节点标签页
        all_nodes_tab = QWidget()
        all_layout = QVBoxLayout(all_nodes_tab)
        
        self.all_nodes_table = QTableWidget()
        self.all_nodes_table.setColumnCount(5)
        self.all_nodes_table.setHorizontalHeaderLabels([
            "节点名称", "CPU使用/总数", "内存使用", 
            "GPU类型", "GPU使用/总数"
        ])
        self.all_nodes_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.all_nodes_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.all_nodes_table.setSortingEnabled(True)
        
        all_layout.addWidget(self.all_nodes_table)
        
        # 添加标签页，GPU节点优先显示
        tabs.addTab(gpu_tab, "GPU节点")
        tabs.addTab(all_nodes_tab, "所有节点")
        
        # 添加选项卡到主布局
        main_layout.addWidget(tabs)
        
        # 底部状态栏
        status_layout = QHBoxLayout()
        
        self.status_label = QLabel("就绪")
        status_layout.addWidget(self.status_label)
        
        # 添加状态栏到主布局
        main_layout.addLayout(status_layout)
    
    def update_refresh_time(self):
        """更新刷新时间显示"""
        if self.last_refresh_time:
            time_str = self.last_refresh_time.toString("yyyy-MM-dd hh:mm:ss")
            self.time_label.setText(f"最后刷新: {time_str}")
            
            # 计算距离上次刷新的时间
            now = QDateTime.currentDateTime()
            secs = self.last_refresh_time.secsTo(now)
            
            # 根据时间设置颜色
            if secs < 60:  # 1分钟内
                self.time_label.setStyleSheet("color: green;")
            elif secs < 300:  # 5分钟内
                self.time_label.setStyleSheet("color: orange;")
            else:  # 超过5分钟
                self.time_label.setStyleSheet("color: red;")
    
    @pyqtSlot()
    def refresh_data(self):
        """刷新节点数据"""
        if not self.node_manager:
            self.show_error("未设置节点管理器，无法获取数据")
            return
        
        # 更新UI状态
        self.refresh_btn.setEnabled(False)
        self.refresh_indicator.setText("正在刷新...")
        self.refresh_indicator.setStyleSheet("color: orange;")
        
        # 安全停止已有线程
        if self.refresh_worker and self.refresh_worker.isRunning():
            self.refresh_worker.stop()
        
        # 创建新的刷新线程
        self.refresh_worker = RefreshWorker(self.node_manager)
        
        # 连接信号
        self.refresh_worker.finished.connect(self.on_refresh_finished)
        self.refresh_worker.error.connect(self.show_error)
        self.refresh_worker.nodes_data.connect(self.update_nodes_data)
        
        # 启动线程
        self.refresh_worker.start()
        
        # 更新刷新时间
        self.last_refresh_time = QDateTime.currentDateTime()
        self.update_refresh_time()
    
    def on_refresh_finished(self):
        """刷新完成时的回调函数"""
        # 更新UI状态
        self.refresh_btn.setEnabled(True)
        self.refresh_indicator.setText("就绪")
        self.refresh_indicator.setStyleSheet("color: green;")
    
    @pyqtSlot(list)
    def update_nodes_data(self, nodes_data):
        """更新节点数据"""
        if not nodes_data:
            return
        
        self.nodes_data = nodes_data
        
        # 更新统计信息
        self.update_stats()
        
        # 更新所有节点表格
        self.update_all_nodes_table()
        
        # 更新GPU节点表格
        self.update_gpu_nodes_table()
    
    def update_stats(self):
        """更新统计信息"""
        if not self.nodes_data:
            return
        
        # 计算基本统计信息
        total_nodes = len(self.nodes_data)
        
        total_cpus = sum(n['total_cpus'] for n in self.nodes_data)
        used_cpus = sum(n['alloc_cpus'] for n in self.nodes_data)
        
        gpu_nodes = [n for n in self.nodes_data if n['has_gpu']]
        total_gpus = sum(n['gpu_count'] for n in gpu_nodes)
        used_gpus = sum(n['used_gpus'] for n in gpu_nodes)
        
        # 更新标签
        stats_text = f"节点总数: {total_nodes} | CPU使用情况: {used_cpus}/{total_cpus} | "
        stats_text += f"GPU使用情况: {used_gpus}/{total_gpus}"
        self.stats_label.setText(stats_text)
    
    def update_all_nodes_table(self):
        """更新所有节点表格"""
        self.all_nodes_table.setSortingEnabled(False)
        self.all_nodes_table.setRowCount(0)
        
        if not self.nodes_data:
            return
        
        # 为每个节点添加一行
        for row, node in enumerate(self.nodes_data):
            self.all_nodes_table.insertRow(row)
            
            # 节点名称
            name_item = QTableWidgetItem(node['name'])
            # 根据状态设置节点名称的颜色
            self.set_color_by_state(name_item, node['state'])
            self.all_nodes_table.setItem(row, 0, name_item)
            
            # CPU使用/总数
            cpu_text = f"{node['alloc_cpus']}/{node['total_cpus']}"
            cpu_item = QTableWidgetItem(cpu_text)
            self.set_color_by_usage(cpu_item, node['cpu_usage'])
            self.all_nodes_table.setItem(row, 1, cpu_item)
            
            # 内存使用
            mem_text = f"{node['alloc_mem']}/{node['memory']}"
            mem_item = QTableWidgetItem(mem_text)
            self.set_color_by_usage(mem_item, node['memory_usage'])
            self.all_nodes_table.setItem(row, 2, mem_item)
            
            # GPU类型
            gpu_type = node['gpu_type'] if node['has_gpu'] else "N/A"
            self.all_nodes_table.setItem(row, 3, QTableWidgetItem(gpu_type))
            
            # GPU使用/总数
            if node['has_gpu']:
                gpu_text = f"{node['used_gpus']}/{node['gpu_count']}"
                gpu_item = QTableWidgetItem(gpu_text)
                self.set_color_by_usage(gpu_item, node['gpu_usage'])
            else:
                gpu_text = "N/A"
                gpu_item = QTableWidgetItem(gpu_text)
            self.all_nodes_table.setItem(row, 4, gpu_item)
        
        self.all_nodes_table.setSortingEnabled(True)
    
    def update_gpu_nodes_table(self):
        """更新GPU节点表格"""
        self.gpu_nodes_table.setSortingEnabled(False)
        self.gpu_nodes_table.setRowCount(0)
        
        if not self.nodes_data:
            return
        
        # 过滤GPU节点
        gpu_nodes = [n for n in self.nodes_data if n['has_gpu']]
        
        # 为每个GPU节点添加一行
        for row, node in enumerate(gpu_nodes):
            self.gpu_nodes_table.insertRow(row)
            
            # 节点名称
            name_item = QTableWidgetItem(node['name'])
            # 根据状态设置节点名称的颜色
            self.set_color_by_state(name_item, node['state'])
            self.gpu_nodes_table.setItem(row, 0, name_item)
            
            # CPU使用/总数
            cpu_text = f"{node['alloc_cpus']}/{node['total_cpus']}"
            cpu_item = QTableWidgetItem(cpu_text)
            self.set_color_by_usage(cpu_item, node['cpu_usage'])
            self.gpu_nodes_table.setItem(row, 1, cpu_item)
            
            # 内存使用
            mem_text = f"{node['alloc_mem']}/{node['memory']}"
            mem_item = QTableWidgetItem(mem_text)
            self.set_color_by_usage(mem_item, node['memory_usage'])
            self.gpu_nodes_table.setItem(row, 2, mem_item)
            
            # GPU类型
            self.gpu_nodes_table.setItem(row, 3, QTableWidgetItem(node['gpu_type']))
            
            # GPU使用/总数
            gpu_text = f"{node['used_gpus']}/{node['gpu_count']}"
            gpu_item = QTableWidgetItem(gpu_text)
            self.set_color_by_usage(gpu_item, node['gpu_usage'])
            self.gpu_nodes_table.setItem(row, 4, gpu_item)
        
        self.gpu_nodes_table.setSortingEnabled(True)
    
    def set_color_by_usage(self, item, usage):
        """根据使用率设置颜色"""
        if usage > 80:
            item.setForeground(QBrush(QColor(255, 0, 0)))  # 红色
        elif usage > 60:
            item.setForeground(QBrush(QColor(255, 165, 0)))  # 橙色
        else:
            item.setForeground(QBrush(QColor(0, 128, 0)))  # 绿色
    
    def set_color_by_state(self, item, state):
        """根据状态设置颜色"""
        if state == "故障":
            item.setForeground(QBrush(QColor(255, 0, 0)))  # 红色
        elif state == "满载":
            item.setForeground(QBrush(QColor(255, 165, 0)))  # 橙色
        elif state == "部分使用":
            item.setForeground(QBrush(QColor(0, 0, 255)))  # 蓝色
        else:  # 空闲
            item.setForeground(QBrush(QColor(0, 128, 0)))  # 绿色
    
    def show_error(self, error_msg):
        """显示错误信息"""
        self.refresh_indicator.setText(f"错误: {error_msg}")
        self.refresh_indicator.setStyleSheet("color: red;")
        logger.error(error_msg)
        
        # 启用刷新按钮
        self.refresh_btn.setEnabled(True)
    
    def closeEvent(self, event):
        """关闭事件"""
        # 停止所有定时器
        if hasattr(self, 'refresh_timer') and self.refresh_timer:
            self.refresh_timer.stop()
        
        # 停止刷新线程
        if self.refresh_worker and self.refresh_worker.isRunning():
            self.refresh_worker.stop()
        
        super().closeEvent(event) 