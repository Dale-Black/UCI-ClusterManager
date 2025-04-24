#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, 
                           QTableWidget, QTableWidgetItem, QTabWidget, 
                           QHeaderView, QStyle, QTextEdit, QComboBox, QTreeWidget,
                           QTreeWidgetItem, QProgressBar, QFrame, QSplitter, QGridLayout, QGroupBox, QSizePolicy)
from PyQt5.QtCore import Qt, QTimer, pyqtSlot, QDateTime, QThread, pyqtSignal
from PyQt5.QtGui import QFont, QColor, QIcon, QBrush
import logging
import time
import os
from modules.node_status import NodeStatusManager
from modules.auth import HPC_SERVER, get_all_existing_users

# 配置日志
logger = logging.getLogger('NodeStatusWidget')

class RefreshWorker(QThread):
    """后台刷新数据的线程"""
    
    # 定义信号
    finished = pyqtSignal()
    refresh_error = pyqtSignal(str)
    node_data_updated = pyqtSignal(dict)
    partition_data_updated = pyqtSignal(dict)
    
    def __init__(self, node_manager):
        """初始化刷新线程"""
        super().__init__()
        self.node_manager = node_manager
        self.refresh_type = "all"  # "all" 或 "partition"
        self.partition_name = None
        self._is_running = True
    
    def set_refresh_type(self, refresh_type, partition_name=None):
        """设置刷新类型和分区名称"""
        self.refresh_type = refresh_type
        self.partition_name = partition_name
    
    def run(self):
        """线程执行函数"""
        try:
            if not self._is_running:
                return
                
            if self.refresh_type == "all":
                # 全量刷新所有数据
                result = self.node_manager.refresh_all_nodes()
                if result:
                    self.node_data_updated.emit(result)
                else:
                    self.refresh_error.emit("无法获取节点信息")
            
            elif self.refresh_type == "partition":
                # 刷新分区数据
                result = self.node_manager.get_nodes_by_partition(self.partition_name)
                if result:
                    self.partition_data_updated.emit(result)
                else:
                    err_msg = f"无法获取分区{self.partition_name or ''}信息"
                    self.refresh_error.emit(err_msg)
        except Exception as e:
            logger.error(f"刷新数据失败: {str(e)}")
            self.refresh_error.emit(f"刷新数据失败: {str(e)}")
        finally:
            self.finished.emit()
    
    def stop(self):
        """安全停止线程"""
        self._is_running = False
        if self.isRunning():
            self.wait(1000)  # 等待最多1秒
            if self.isRunning():
                self.terminate()  # 如果仍在运行，强制终止

class NodeStatusWidget(QWidget):
    """节点状态组件，展示HPC集群节点信息和可用情况"""
    
    def __init__(self, parent=None, username=None):
        super().__init__(parent)
        
        # 用户信息
        self.username = username
        self.node_manager = None
        
        # 最后刷新时间
        self.last_refresh_time = None
        
        # 数据存储
        self.node_data = {
            'partitions': {},
            'refresh_time': None,
            'gpu_nodes': [],
            'cpu_nodes': []
        }
        
        # 刷新工作线程
        self.refresh_worker = None
        
        # 初始化节点管理器
        self.init_node_manager()
        
        # 初始化UI
        self.init_ui()
        
        # 定时刷新
        self.refresh_timer = QTimer(self)
        self.refresh_timer.timeout.connect(self.update_refresh_time)
        self.refresh_timer.start(10000)  # 每10秒更新一次时间显示
        
        # 定时完全刷新
        self.full_refresh_timer = QTimer(self)
        self.full_refresh_timer.timeout.connect(self.refresh_all)
        self.full_refresh_timer.start(120000)  # 每2分钟自动刷新一次
        
        # 加载数据
        self.refresh_all()
    
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
        self.node_manager.node_info_updated.connect(self.update_node_data)
        self.node_manager.error_occurred.connect(self.show_error)
    
    def init_ui(self):
        """初始化UI组件"""
        main_layout = QVBoxLayout(self)
        
        # 顶部控制栏
        control_layout = QHBoxLayout()
        
        # 刷新按钮带图标
        self.refresh_btn = QPushButton("刷新节点信息")
        self.refresh_btn.setIcon(self.style().standardIcon(QStyle.SP_BrowserReload))
        self.refresh_btn.clicked.connect(self.refresh_all)
        control_layout.addWidget(self.refresh_btn)
        
        # 刷新状态指示器
        self.refresh_indicator = QLabel("就绪")
        self.refresh_indicator.setStyleSheet("color: green;")
        control_layout.addWidget(self.refresh_indicator)
        
        # 分区选择下拉框
        self.partition_selector = QComboBox()
        self.partition_selector.addItem("所有分区")
        if self.node_manager:
            for partition in self.node_manager.all_partitions:
                self.partition_selector.addItem(partition)
        self.partition_selector.currentIndexChanged.connect(self.change_partition)
        control_layout.addWidget(QLabel("分区:"))
        control_layout.addWidget(self.partition_selector)
        
        control_layout.addStretch()
        
        # 刷新时间显示
        self.time_label = QLabel("尚未刷新")
        control_layout.addWidget(self.time_label)
        
        # 添加控制栏到主布局
        main_layout.addLayout(control_layout)
        
        # 创建分割器，在顶部放置节点类型树，在底部放置详细信息
        splitter = QSplitter(Qt.Vertical)
        
        # 创建节点概览
        node_overview_group = QGroupBox("节点配置")
        node_overview_layout = QVBoxLayout()
        
        # 使用树状结构显示节点配置
        self.node_tree = QTreeWidget()
        self.node_tree.setHeaderLabels(["配置", "总节点数", "已用节点", "CPU使用率", "GPU使用率"])
        self.node_tree.setColumnWidth(0, 200)
        self.node_tree.itemClicked.connect(self.on_node_tree_clicked)
        
        node_overview_layout.addWidget(self.node_tree)
        node_overview_group.setLayout(node_overview_layout)
        
        # 创建标签页，显示分区信息、特征组和GPU信息
        detail_tabs = QTabWidget()
        
        # 分区信息标签页
        partition_tab = QWidget()
        partition_layout = QVBoxLayout()
        
        self.partition_table = QTableWidget()
        self.partition_table.setColumnCount(7)
        self.partition_table.setHorizontalHeaderLabels(["分区名称", "可用性", "时间限制", "CPU数量", "内存", "节点数", "描述"])
        self.partition_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        
        partition_layout.addWidget(self.partition_table)
        partition_tab.setLayout(partition_layout)
        
        # 特征组标签页
        feature_tab = QWidget()
        feature_layout = QVBoxLayout()
        
        self.feature_table = QTableWidget()
        self.feature_table.setColumnCount(3)
        self.feature_table.setHorizontalHeaderLabels(["特征名称", "节点数", "节点列表"])
        self.feature_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        
        feature_layout.addWidget(self.feature_table)
        feature_tab.setLayout(feature_layout)
        
        # GPU信息标签页
        gpu_tab = QWidget()
        gpu_layout = QVBoxLayout()
        
        self.gpu_table = QTableWidget()
        self.gpu_table.setColumnCount(5)
        self.gpu_table.setHorizontalHeaderLabels(["节点名称", "GPU型号", "GPU数量", "使用率", "状态"])
        self.gpu_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        
        gpu_layout.addWidget(self.gpu_table)
        gpu_tab.setLayout(gpu_layout)
        
        # 利用率信息标签页
        utilization_tab = QWidget()
        utilization_layout = QGridLayout()
        
        # CPU利用率显示
        cpu_group = QGroupBox("CPU利用率")
        cpu_layout = QVBoxLayout()
        
        self.cpu_allocated_bar = QProgressBar()
        self.cpu_allocated_bar.setFormat("已分配: %v/%m")
        
        self.cpu_idle_bar = QProgressBar()
        self.cpu_idle_bar.setFormat("空闲: %v/%m")
        self.cpu_idle_bar.setStyleSheet("QProgressBar::chunk { background-color: green; }")
        
        cpu_layout.addWidget(QLabel("已分配CPU:"))
        cpu_layout.addWidget(self.cpu_allocated_bar)
        cpu_layout.addWidget(QLabel("空闲CPU:"))
        cpu_layout.addWidget(self.cpu_idle_bar)
        cpu_group.setLayout(cpu_layout)
        
        # GPU利用率显示
        gpu_group = QGroupBox("GPU利用率")
        gpu_layout = QVBoxLayout()
        
        self.gpu_allocated_bar = QProgressBar()
        self.gpu_allocated_bar.setFormat("已分配: %v/%m")
        
        self.gpu_idle_bar = QProgressBar()
        self.gpu_idle_bar.setFormat("空闲: %v/%m")
        self.gpu_idle_bar.setStyleSheet("QProgressBar::chunk { background-color: green; }")
        
        gpu_layout.addWidget(QLabel("已分配GPU:"))
        gpu_layout.addWidget(self.gpu_allocated_bar)
        gpu_layout.addWidget(QLabel("空闲GPU:"))
        gpu_layout.addWidget(self.gpu_idle_bar)
        gpu_group.setLayout(gpu_layout)
        
        # 节点利用率显示
        node_group = QGroupBox("节点利用率")
        node_layout = QVBoxLayout()
        
        self.node_allocated_bar = QProgressBar()
        self.node_allocated_bar.setFormat("已分配: %v/%m")
        
        self.node_idle_bar = QProgressBar()
        self.node_idle_bar.setFormat("空闲: %v/%m")
        self.node_idle_bar.setStyleSheet("QProgressBar::chunk { background-color: green; }")
        
        node_layout.addWidget(QLabel("已分配节点:"))
        node_layout.addWidget(self.node_allocated_bar)
        node_layout.addWidget(QLabel("空闲节点:"))
        node_layout.addWidget(self.node_idle_bar)
        node_group.setLayout(node_layout)
        
        utilization_layout.addWidget(cpu_group, 0, 0)
        utilization_layout.addWidget(gpu_group, 0, 1)
        utilization_layout.addWidget(node_group, 1, 0, 1, 2)
        
        utilization_tab.setLayout(utilization_layout)
        
        # 添加标签页
        detail_tabs.addTab(partition_tab, "分区信息")
        detail_tabs.addTab(feature_tab, "特征组")
        detail_tabs.addTab(gpu_tab, "GPU信息")
        detail_tabs.addTab(utilization_tab, "集群利用率")
        
        # 添加组件到分割器
        splitter.addWidget(node_overview_group)
        splitter.addWidget(detail_tabs)
        
        # 设置默认分割比例
        splitter.setSizes([200, 500])
        
        # 添加分割器到主布局
        main_layout.addWidget(splitter)
        
        # 设置大小
        self.setMinimumSize(800, 600)
        
        # 底部状态栏
        status_layout = QHBoxLayout()
        
        self.status_label = QLabel("就绪")
        status_layout.addWidget(self.status_label)
        
        status_layout.addStretch()
        
        self.node_count_label = QLabel("节点数: 0")
        status_layout.addWidget(self.node_count_label)
        
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
    
    def change_partition(self, index):
        """更改选中的分区"""
        # 防止递归调用
        if hasattr(self, '_updating_partition') and self._updating_partition:
            return
        
        self._updating_partition = True
        try:
            if index == 0:
                # 所有分区
                self.update_all_ui()
            else:
                # 特定分区
                partition_name = self.partition_selector.currentText()
                self.update_for_partition(partition_name)
        finally:
            self._updating_partition = False
    
    @pyqtSlot()
    def refresh_all(self):
        """刷新所有节点和分区信息"""
        if not self.node_manager:
            self.show_error("未设置节点管理器，无法获取数据")
            return
        
        # 更新UI状态
        self.refresh_btn.setEnabled(False)
        self.refresh_indicator.setText("正在刷新...")
        self.refresh_indicator.setStyleSheet("color: orange;")
        
        # 安全停止现有线程
        self._stop_refresh_worker()
        
        # 创建新的工作线程
        self.refresh_worker = RefreshWorker(self.node_manager)
        self.refresh_worker.set_refresh_type("all")
        
        # 连接信号
        self.refresh_worker.finished.connect(self.on_refresh_finished)
        self.refresh_worker.refresh_error.connect(self.show_error)
        self.refresh_worker.node_data_updated.connect(self.update_node_data)
        
        # 启动线程
        self.refresh_worker.start()
        
        # 更新刷新时间
        self.last_refresh_time = QDateTime.currentDateTime()
        self.update_refresh_time()

    def _stop_refresh_worker(self):
        """安全停止刷新线程"""
        if self.refresh_worker and self.refresh_worker.isRunning():
            try:
                self.refresh_worker.stop()
                self.refresh_worker.wait(1000)  # 等待最多1秒
            except Exception as e:
                logger.warning(f"停止线程时出错: {str(e)}")
    
    def refresh_partition_data(self, partition_name=None):
        """刷新特定分区的数据"""
        if not self.node_manager:
            self.show_error("未设置节点管理器，无法获取数据")
            return
        
        # 安全停止现有线程
        self._stop_refresh_worker()
        
        # 创建新的工作线程
        self.refresh_worker = RefreshWorker(self.node_manager)
        self.refresh_worker.set_refresh_type("partition", partition_name)
        
        # 连接信号
        self.refresh_worker.finished.connect(self.on_refresh_finished)
        self.refresh_worker.refresh_error.connect(self.show_error)
        self.refresh_worker.partition_data_updated.connect(self.update_partition_data)
        
        # 启动线程
        self.refresh_worker.start()
    
    def on_refresh_finished(self):
        """刷新完成时的回调函数"""
        # 更新UI状态
        self.refresh_btn.setEnabled(True)
        self.refresh_indicator.setText("就绪")
        self.refresh_indicator.setStyleSheet("color: green;")
        
        # 更新刷新时间
        self.last_refresh_time = QDateTime.currentDateTime()
        self.update_refresh_time()
    
    @pyqtSlot(dict)
    def update_node_data(self, node_data):
        """更新节点数据"""
        if not node_data:
            return
        
        self.node_data = node_data
        self.update_all_ui()
    
    @pyqtSlot(dict)
    def update_partition_data(self, partition_data):
        """更新分区数据"""
        if not partition_data:
            return
        
        # 更新存储的分区数据
        self.node_data['partitions'].update(partition_data)
        
        # 更新相关UI
        self.update_partition_table(self.node_data['partitions'])
        self.update_node_tree(self.node_data)
    
    def update_all_ui(self):
        """更新所有UI组件"""
        # 更新节点树
        self.update_node_tree(self.node_data)
        
        # 更新分区表
        if 'partitions' in self.node_data:
            self.update_partition_table(self.node_data['partitions'])
        
        # 更新特征组表
        if 'feature_groups' in self.node_data:
            self.update_feature_table(self.node_data['feature_groups'])
        
        # 更新GPU表
        if 'gpu_nodes' in self.node_data:
            self.update_gpu_table(self.node_data['gpu_nodes'])
        
        # 更新利用率
        if 'utilization' in self.node_data:
            self.update_utilization(self.node_data['utilization'])
        
        # 更新分区选择器
        if 'partitions' in self.node_data:
            self.update_partition_selector(self.node_data['partitions'])
        
        # 更新刷新时间
        self.update_refresh_time()
    
    def update_node_tree(self, node_data):
        """更新节点树显示"""
        self.node_tree.clear()
        
        if not node_data:
            return
        
        # 处理GPU节点
        self._add_gpu_nodes_to_tree(node_data)
        
        # 处理CPU节点
        self._add_cpu_nodes_to_tree(node_data)
    
    def _add_gpu_nodes_to_tree(self, node_data):
        """添加GPU节点到树视图"""
        if 'gpu_nodes' not in node_data or not node_data['gpu_nodes']:
            return
            
        gpu_root = QTreeWidgetItem(self.node_tree, ["GPU节点"])
        gpu_root.setExpanded(True)
        
        # 按GPU型号分组
        gpu_models = {}
        for node in node_data['gpu_nodes']:
            model = node.get('gpu_model', '未知')
            if model not in gpu_models:
                gpu_models[model] = []
            gpu_models[model].append(node)
        
        # 添加各GPU型号分组
        for model, nodes in gpu_models.items():
            total_nodes = len(nodes)
            used_nodes = sum(1 for n in nodes if n.get('status') == 'allocated')
            
            # 计算使用率
            total_cpus = sum(int(n.get('cpus', 0)) for n in nodes)
            used_cpus = sum(int(n.get('used_cpus', 0)) for n in nodes)
            cpu_usage = 0 if total_cpus == 0 else (used_cpus / total_cpus) * 100
            
            total_gpus = sum(int(n.get('gpus', 0)) for n in nodes)
            used_gpus = sum(int(n.get('used_gpus', 0)) for n in nodes)
            gpu_usage = 0 if total_gpus == 0 else (used_gpus / total_gpus) * 100
            
            # 创建型号条目
            model_item = QTreeWidgetItem(gpu_root, [
                f"{model} ({nodes[0].get('cpus', '?')}核/{nodes[0].get('memory', '?')}GB)",
                str(total_nodes),
                f"{used_nodes}/{total_nodes}",
                f"{cpu_usage:.1f}%",
                f"{gpu_usage:.1f}%"
            ])
            
            # 设置颜色
            self._set_usage_color(model_item, 4, gpu_usage)
            self._set_usage_color(model_item, 3, cpu_usage)
            
            # 添加节点
            for node in nodes:
                self._add_node_to_tree(model_item, node, True)
    
    def _add_cpu_nodes_to_tree(self, node_data):
        """添加CPU节点到树视图"""
        if 'cpu_nodes' not in node_data or not node_data['cpu_nodes']:
            return
            
        cpu_root = QTreeWidgetItem(self.node_tree, ["CPU节点"])
        cpu_root.setExpanded(True)
        
        # 按CPU配置分组
        cpu_configs = {}
        for node in node_data['cpu_nodes']:
            config = f"{node.get('cpus', '?')}核/{node.get('memory', '?')}GB"
            if config not in cpu_configs:
                cpu_configs[config] = []
            cpu_configs[config].append(node)
        
        # 添加各CPU配置分组
        for config, nodes in cpu_configs.items():
            total_nodes = len(nodes)
            used_nodes = sum(1 for n in nodes if n.get('status') == 'allocated')
            
            # 计算使用率
            total_cpus = sum(int(n.get('cpus', 0)) for n in nodes)
            used_cpus = sum(int(n.get('used_cpus', 0)) for n in nodes)
            cpu_usage = 0 if total_cpus == 0 else (used_cpus / total_cpus) * 100
            
            # 创建配置条目
            config_item = QTreeWidgetItem(cpu_root, [
                config,
                str(total_nodes),
                f"{used_nodes}/{total_nodes}",
                f"{cpu_usage:.1f}%",
                "N/A"
            ])
            
            # 设置颜色
            self._set_usage_color(config_item, 3, cpu_usage)
            
            # 添加节点
            for node in nodes:
                self._add_node_to_tree(config_item, node, False)
    
    def _add_node_to_tree(self, parent_item, node, is_gpu):
        """添加单个节点到树结构"""
        node_item = QTreeWidgetItem(parent_item, [
            node.get('name', '未知'),
            "1",
            "已分配" if node.get('status') == 'allocated' else "空闲",
            f"{node.get('used_cpus', 0)}/{node.get('cpus', 0)}",
            f"{node.get('used_gpus', 0)}/{node.get('gpus', 0)}" if is_gpu else "N/A"
        ])
        
        # 设置节点状态颜色
        if node.get('status') == 'allocated':
            node_item.setForeground(2, QBrush(QColor(255, 0, 0)))
        else:
            node_item.setForeground(2, QBrush(QColor(0, 128, 0)))
    
    def _set_usage_color(self, item, column, usage_value):
        """根据使用率设置颜色"""
        if usage_value > 80:
            item.setForeground(column, QBrush(QColor(255, 0, 0)))  # 红色
        elif usage_value > 60:
            item.setForeground(column, QBrush(QColor(255, 165, 0)))  # 橙色
        else:
            item.setForeground(column, QBrush(QColor(0, 128, 0)))  # 绿色
    
    def update_partition_table(self, partitions):
        """更新分区表显示"""
        self.partition_table.setRowCount(0)
        
        if not partitions:
            return
        
        # 填充分区表
        row = 0
        for name, info in partitions.items():
            self.partition_table.insertRow(row)
            
            # 分区名称
            self.partition_table.setItem(row, 0, QTableWidgetItem(name))
            
            # 可用性
            status_item = QTableWidgetItem(info.get('state', '未知'))
            if info.get('state') == 'up':
                status_item.setForeground(QBrush(QColor(0, 128, 0)))
            else:
                status_item.setForeground(QBrush(QColor(255, 0, 0)))
            self.partition_table.setItem(row, 1, status_item)
            
            # 时间限制
            self.partition_table.setItem(row, 2, QTableWidgetItem(info.get('time_limit', '未知')))
            
            # CPU数量
            self.partition_table.setItem(row, 3, QTableWidgetItem(info.get('cpus', '未知')))
            
            # 内存
            self.partition_table.setItem(row, 4, QTableWidgetItem(info.get('memory', '未知')))
            
            # 节点数
            nodes = info.get('nodes', [])
            node_count = QTableWidgetItem(str(len(nodes)))
            self.partition_table.setItem(row, 5, node_count)
            
            # 描述
            self.partition_table.setItem(row, 6, QTableWidgetItem(info.get('description', '')))
            
            row += 1
    
    def update_feature_table(self, feature_groups):
        """更新特征组表显示"""
        self.feature_table.setRowCount(0)
        
        if not feature_groups:
            return
        
        # 填充特征组表
        row = 0
        for feature, nodes in feature_groups.items():
            self.feature_table.insertRow(row)
            
            # 特征名称
            self.feature_table.setItem(row, 0, QTableWidgetItem(feature))
            
            # 节点数
            self.feature_table.setItem(row, 1, QTableWidgetItem(str(len(nodes))))
            
            # 节点列表
            node_names = ", ".join(nodes)
            self.feature_table.setItem(row, 2, QTableWidgetItem(node_names))
            
            row += 1
    
    def update_gpu_table(self, gpu_nodes):
        """更新GPU表显示"""
        self.gpu_table.setRowCount(0)
        
        if not gpu_nodes:
            return
        
        # 填充GPU表
        for row, node in enumerate(gpu_nodes):
            self.gpu_table.insertRow(row)
            
            # 节点名称
            self.gpu_table.setItem(row, 0, QTableWidgetItem(node.get('name', '未知')))
            
            # GPU型号
            self.gpu_table.setItem(row, 1, QTableWidgetItem(node.get('gpu_model', '未知')))
            
            # GPU数量
            self.gpu_table.setItem(row, 2, QTableWidgetItem(str(node.get('gpus', 0))))
            
            # 使用率
            total_gpus = int(node.get('gpus', 0))
            used_gpus = int(node.get('used_gpus', 0))
            usage = 0 if total_gpus == 0 else (used_gpus / total_gpus) * 100
            usage_item = QTableWidgetItem(f"{usage:.1f}% ({used_gpus}/{total_gpus})")
            
            # 设置颜色
            self._set_item_color_by_usage(usage_item, usage)
            self.gpu_table.setItem(row, 3, usage_item)
            
            # 状态
            status_item = QTableWidgetItem("已分配" if node.get('status') == 'allocated' else "空闲")
            status_item.setForeground(QBrush(
                QColor(255, 0, 0) if node.get('status') == 'allocated' else QColor(0, 128, 0)
            ))
            self.gpu_table.setItem(row, 4, status_item)
    
    def _set_item_color_by_usage(self, item, usage):
        """根据使用率设置表格项颜色"""
        if usage > 80:
            item.setForeground(QBrush(QColor(255, 0, 0)))  # 红色
        elif usage > 60:
            item.setForeground(QBrush(QColor(255, 165, 0)))  # 橙色
        else:
            item.setForeground(QBrush(QColor(0, 128, 0)))  # 绿色
    
    def update_utilization(self, utilization):
        """更新利用率显示"""
        if not utilization:
            return
        
        # 更新CPU利用率
        total_cpus = utilization.get('total_cpus', 0)
        used_cpus = utilization.get('allocated_cpus', 0)
        idle_cpus = total_cpus - used_cpus
        
        self.cpu_allocated_bar.setMaximum(total_cpus)
        self.cpu_allocated_bar.setValue(used_cpus)
        self.cpu_idle_bar.setMaximum(total_cpus)
        self.cpu_idle_bar.setValue(idle_cpus)
        
        # 更新GPU利用率
        total_gpus = utilization.get('total_gpus', 0)
        used_gpus = utilization.get('allocated_gpus', 0)
        idle_gpus = total_gpus - used_gpus
        
        self.gpu_allocated_bar.setMaximum(total_gpus)
        self.gpu_allocated_bar.setValue(used_gpus)
        self.gpu_idle_bar.setMaximum(total_gpus)
        self.gpu_idle_bar.setValue(idle_gpus)
        
        # 更新节点利用率
        total_nodes = utilization.get('total_nodes', 0)
        used_nodes = utilization.get('allocated_nodes', 0)
        idle_nodes = total_nodes - used_nodes
        
        self.node_allocated_bar.setMaximum(total_nodes)
        self.node_allocated_bar.setValue(used_nodes)
        self.node_idle_bar.setMaximum(total_nodes)
        self.node_idle_bar.setValue(idle_nodes)
    
    def update_partition_selector(self, partitions):
        """更新分区选择器"""
        # 记住当前选择的分区
        current_partition = self.partition_selector.currentText()
        
        # 清空选择器
        self.partition_selector.clear()
        self.partition_selector.addItem("所有分区")
        
        # 添加分区
        if partitions:
            for name in sorted(partitions.keys()):
                self.partition_selector.addItem(name)
        
        # 恢复之前的选择
        index = self.partition_selector.findText(current_partition)
        if index >= 0:
            self.partition_selector.setCurrentIndex(index)
    
    def update_for_partition(self, partition_name):
        """更新特定分区的信息"""
        if 'partitions' not in self.node_data or partition_name not in self.node_data['partitions']:
            return
        
        # 获取分区信息
        partition_info = self.node_data['partitions'][partition_name]
        
        # 高亮显示分区概览中的指定分区
        self.highlight_partition_in_overview(partition_name)
        
        # 根据分区类型更新不同的表格
        if "gpu" in partition_name.lower():
            # GPU分区
            self.update_gpu_table(partition_info['node_list'])
        else:
            # CPU分区
            cpu_nodes = partition_info.get('node_list', [])
            # 只在CPU节点列表有效时更新表格
            if hasattr(self, 'cpu_table') and cpu_nodes:
                self.update_cpu_table(cpu_nodes)
        
        # 更新节点计数
        self.node_count_label.setText(f"{partition_name} 节点数: {len(partition_info.get('node_list', []))}")
    
    def highlight_partition_in_overview(self, partition_name):
        """在分区概览中高亮显示指定分区"""
        for row in range(self.partition_table.rowCount()):
            if self.partition_table.item(row, 0).text() == partition_name:
                # 高亮显示整行
                for col in range(self.partition_table.columnCount()):
                    item = self.partition_table.item(row, col)
                    if item:
                        item.setBackground(QColor(220, 230, 255))  # 浅蓝色背景
            else:
                # 恢复其他行的背景
                for col in range(self.partition_table.columnCount()):
                    item = self.partition_table.item(row, col)
                    if item:
                        item.setBackground(QColor(255, 255, 255))  # 白色背景
    
    def update_cpu_table(self, cpu_nodes):
        """更新CPU节点表格"""
        # 清空表格
        self.cpu_table.setRowCount(0)
        
        if not cpu_nodes:
            self.cpu_summary_label.setText("未找到CPU节点")
            return
        
        # 更新CPU信息标签
        self.cpu_summary_label.setText(f"CPU节点总数: {len(cpu_nodes)}")
        
        # 按节点名称对节点进行排序
        sorted_nodes = sorted(cpu_nodes, key=lambda n: n['node_name'])
        
        # 填充表格
        for i, node in enumerate(sorted_nodes):
            self.cpu_table.insertRow(i)
            
            # 节点名称
            self.cpu_table.setItem(i, 0, QTableWidgetItem(node['node_name']))
            
            # CPU使用/总数
            cpu_usage = f"{node['allocated_cpus']}/{node['total_cpus']}"
            self.cpu_table.setItem(i, 1, QTableWidgetItem(cpu_usage))
            
            # CPU利用率
            cpu_util_item = QTableWidgetItem(node.get('cpu_usage', 'N/A'))
            try:
                util = float(node.get('cpu_usage_value', 0))
                if util > 80:
                    cpu_util_item.setForeground(QColor('red'))
                elif util > 40:
                    cpu_util_item.setForeground(QColor('orange'))
                else:
                    cpu_util_item.setForeground(QColor('green'))
            except:
                pass
            self.cpu_table.setItem(i, 2, cpu_util_item)
            
            # 内存
            self.cpu_table.setItem(i, 3, QTableWidgetItem(node['memory']))
            
            # 已分配内存
            self.cpu_table.setItem(i, 4, QTableWidgetItem(node['allocated_memory']))
            
            # 特性
            self.cpu_table.setItem(i, 5, QTableWidgetItem(node.get('features', 'N/A')))
            
            # 状态
            state_item = QTableWidgetItem(node.get('state', 'N/A'))
            state = node.get('state', '').lower()
            if 'idle' in state:
                state_item.setForeground(QColor('green'))
            elif 'alloc' in state or 'mix' in state:
                state_item.setForeground(QColor('blue'))
            elif 'down' in state or 'drain' in state:
                state_item.setForeground(QColor('red'))
            self.cpu_table.setItem(i, 6, state_item)
            
            # 分区
            partition_item = QTableWidgetItem(node['partition'])
            if "free" in node['partition'].lower():
                partition_item.setForeground(QColor('green'))
            self.cpu_table.setItem(i, 7, partition_item)
    
    def on_node_tree_clicked(self, item):
        """节点树点击事件处理"""
        # 获取所选项的类型和值
        parent = item.parent()
        
        # 如果是配置项
        if parent and parent.text(0) in ["GPU节点", "CPU节点"]:
            # 是配置组，可以添加特定处理...
            pass
        
        # 如果是节点项
        elif parent and parent.parent() and parent.parent().text(0) in ["GPU节点", "CPU节点"]:
            # 是具体节点，显示节点详细信息
            node_name = item.text(0)
            # 可以添加显示节点详情的代码...
            pass
    
    def show_error(self, error_msg):
        """显示错误信息"""
        self.refresh_indicator.setText(f"错误: {error_msg}")
        self.refresh_indicator.setStyleSheet("color: red;")
        logger.error(error_msg)
        
        # 启用刷新按钮，让用户可以重试
        self.refresh_btn.setEnabled(True)
    
    def closeEvent(self, event):
        """关闭事件"""
        # 停止所有定时器
        if hasattr(self, 'refresh_timer') and self.refresh_timer:
            self.refresh_timer.stop()
        
        if hasattr(self, 'full_refresh_timer') and self.full_refresh_timer:
            self.full_refresh_timer.stop()
        
        # 安全停止刷新线程
        self._stop_refresh_worker()
        
        super().closeEvent(event) 