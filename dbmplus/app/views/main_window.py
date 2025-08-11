"""
主視窗模塊，提供應用程式的主界面
"""
import os
import sys
from pathlib import Path
from typing import Optional, Dict, List, Any
from datetime import datetime
import psutil

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
    QTabWidget, QTableWidget, QTableWidgetItem, QPushButton,
    QLabel, QProgressBar, QMessageBox, QFileDialog, QComboBox,
    QSizePolicy, QHeaderView, QStatusBar, QToolBar, QToolButton,
    QMenu, QDialog, QApplication, QCheckBox, QFrame, QTextEdit
)
from PySide6.QtCore import Qt, QSize, Signal, Slot, QThread, QTimer
from PySide6.QtGui import QIcon, QAction, QPixmap, QFont, QColor

from ..utils import get_logger, config
from ..models import db_manager, ComponentInfo
from ..controllers import data_processor, online_manager
from ..controllers.storage_manager import storage_manager
from .dialogs import MoveFileDialog, BatchMoveFileDialog

logger = get_logger("main_window")


class TaskProgressDialog(QDialog):
    """任務進度對話框，用於顯示長時間任務的進度"""
    
    def __init__(self, title, message, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(400)
        self.setMinimumHeight(150)
        
        # 建立佈局
        layout = QVBoxLayout(self)
        
        # 訊息標籤
        self.message_label = QLabel(message)
        self.message_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.message_label)
        
        # 進度條
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)  # 不確定進度
        layout.addWidget(self.progress_bar)
        
        # 狀態標籤
        self.status_label = QLabel("處理中...")
        self.status_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.status_label)
        
        # 取消按鈕
        self.cancel_button = QPushButton("取消")
        self.cancel_button.clicked.connect(self.reject)
        layout.addWidget(self.cancel_button)
        
        # 任務ID和計時器
        self.task_id = None
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_status)
        self.timer.start(500)  # 每500毫秒更新
    
    def set_task_id(self, task_id):
        """設置要追蹤的任務ID"""
        self.task_id = task_id
    
    def update_status(self):
        """更新任務狀態"""
        if not self.task_id:
            return
            
        status = data_processor.get_task_status(self.task_id)
        task = status.get("task")
        
        if not task:
            return
            
        # 根據任務狀態更新UI
        if task["status"] == "completed":
            self.progress_bar.setRange(0, 100)
            self.progress_bar.setValue(100)
            self.status_label.setText(f"完成: {status.get('message', '')}")
            self.timer.stop()
            self.cancel_button.setText("關閉")
        elif task["status"] == "failed":
            self.progress_bar.setRange(0, 100)
            self.progress_bar.setValue(0)
            self.status_label.setText(f"失敗: {status.get('message', '')}")
            self.timer.stop()
            self.cancel_button.setText("關閉")
        else:
            self.status_label.setText(f"處理中... {task['task_type']}")


class MainWindow(QMainWindow):
    """應用程式主視窗"""
    
    def __init__(self):
        super().__init__()
        self.init_ui()
        
        # 載入資料
        self.load_data()
        
        # 連接數據處理器的信號
        data_processor.signaler.task_completed.connect(self.on_task_completed)
        
        # 初始化延遲移動管理器（在主線程中）
        self.init_delayed_move_manager()
        
        # 初始化存儲管理
        self.init_storage_management()
    
    def init_delayed_move_manager(self):
        """初始化延遲移動管理器"""
        from ..controllers.data_processor import DelayedMoveManager
        
        # 創建延遲移動管理器（在主線程中）
        self.delayed_move_manager = DelayedMoveManager()
        
        # 如果延遲移動啟用，啟動調度器
        if config.get("auto_move.delayed.enabled", False):
            logger.info("主視窗：延遲移動功能已啟用，正在啟動調度器...")
            self.delayed_move_manager.start_scheduler()
        else:
            logger.info("主視窗：延遲移動功能已禁用")
    
    def init_storage_management(self):
        """初始化存儲管理"""
        # 如果存儲管理啟用，啟動監控
        if config.get("storage_management.enabled", False):
            logger.info("主視窗：存儲管理功能已啟用")
            # 注意：存儲管理器的啟動由按鈕控制，不在初始化時啟動
        else:
            logger.info("主視窗：存儲管理功能已禁用")
    
    def init_ui(self):
        """初始化用戶界面"""
        # 設置視窗屬性
        self.setWindowTitle("Database Manager Plus")
        self.setMinimumWidth(config.get("ui.window_size.width", 950))
        self.setMinimumHeight(config.get("ui.window_size.min_height", 800))
        
        # 建立中央小工具
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # 主佈局
        main_layout = QVBoxLayout(central_widget)
        
        # 建立分割器，允許調整各部分大小
        splitter = QSplitter(Qt.Vertical)
        main_layout.addWidget(splitter)
        
        # 上方面板: 主資料表
        top_panel = QWidget()
        top_layout = QVBoxLayout(top_panel)
        
        # 產品資料表
        self.product_table = QTableWidget(0, 9)
        self.product_table.setHorizontalHeaderLabels(['Product', 'LOT', 'MT', 'DC2', 'INNER1', 'RDL', 'INNER2', 'CU', 'EMC'])
        self.product_table.setEditTriggers(QTableWidget.NoEditTriggers)  # 設為不可編輯
        self.product_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.product_table.verticalHeader().setVisible(False)  # 隱藏行號
        self.product_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.product_table.setSelectionMode(QTableWidget.SingleSelection)
        self.product_table.setAlternatingRowColors(True)
        self.product_table.cellClicked.connect(self.on_product_table_cell_clicked)
        
        top_layout.addWidget(self.product_table)
        splitter.addWidget(top_panel)
        
        # 下方面板: 詳細資訊
        bottom_panel = QWidget()
        bottom_layout = QVBoxLayout(bottom_panel)
        
        # 詳細資訊選項卡
        self.detail_tabs = QTabWidget()
        
        # 元件列表選項卡
        self.component_tab = QWidget()
        component_layout = QVBoxLayout(self.component_tab)
        
        # 元件資料表
        self.component_table = QTableWidget(0, 10)
        self.component_table.setHorizontalHeaderLabels(
            ['Product', 'LOT', 'Station', 'Component ID', 'Org', 'CSV', 'Basemap', 'Lossmap', 'FPY', 'Actions']
        )
        self.component_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.component_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.component_table.verticalHeader().setVisible(False)
        self.component_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.component_table.setSelectionMode(QTableWidget.ExtendedSelection)  # 支持多選
        self.component_table.setAlternatingRowColors(True)
        
        # 設置右鍵選單
        self.component_table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.component_table.customContextMenuRequested.connect(self.show_component_context_menu)
        
        # 設置欄寬
        col_widths = config.get("ui.table_column_widths", {})
        for col, name in enumerate(['product', 'lot', 'station', 'lotid', 'org', 'csv', 'basemap', 'lossmap', 'fpy']):
            if name in col_widths:
                self.component_table.setColumnWidth(col, col_widths[name])
        
        component_layout.addWidget(self.component_table)
        
        # 创建日志选项卡
        self.log_tab = QWidget()
        log_layout = QVBoxLayout(self.log_tab)
        
        # 日志表格
        self.log_table = QTableWidget(0, 7)
        self.log_table.setHorizontalHeaderLabels(
            ['時間', '產品', '批次', '站點', '組件', '狀態', '訊息']
        )
        self.log_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.log_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.log_table.verticalHeader().setVisible(False)
        self.log_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.log_table.setAlternatingRowColors(True)
        
        log_layout.addWidget(self.log_table)
        
        # 日志操作按钮
        log_button_panel = QWidget()
        log_button_layout = QHBoxLayout(log_button_panel)
        log_button_layout.setContentsMargins(0, 0, 0, 0)
        
        self.clear_log_btn = QPushButton("清空日誌")
        self.clear_log_btn.setStyleSheet("background-color: lightblue; color: black;")
        self.clear_log_btn.setFixedHeight(30)
        self.clear_log_btn.clicked.connect(self.on_clear_log_clicked)
        log_button_layout.addWidget(self.clear_log_btn)
        
        log_layout.addWidget(log_button_panel)
        
        # 创建Info选项卡
        self.info_tab = QWidget()
        info_layout = QVBoxLayout(self.info_tab)
        
        # 终端风格日志面板
        terminal_log_panel = QWidget()
        terminal_log_layout = QVBoxLayout(terminal_log_panel)
        
        # 终端日志标题
        terminal_log_title = QLabel("終端機日誌")
        terminal_log_title.setStyleSheet("font-size: 14px; font-weight: bold; color: white; padding: 5px;")
        terminal_log_layout.addWidget(terminal_log_title)
        
        # 终端风格日志文本区域
        self.terminal_log_text = QTextEdit()
        self.terminal_log_text.setReadOnly(True)
        self.terminal_log_text.setStyleSheet("background-color: #1e1e1e; color: #ffffff; font-family: 'Consolas', 'Monaco', monospace; font-size: 10px;")
        terminal_log_layout.addWidget(self.terminal_log_text)
        
        # 终端日志操作按钮
        terminal_log_button_panel = QWidget()
        terminal_log_button_layout = QHBoxLayout(terminal_log_button_panel)
        terminal_log_button_layout.setContentsMargins(0, 0, 0, 0)
        
        self.clear_terminal_log_btn = QPushButton("清空終端日誌")
        self.clear_terminal_log_btn.setStyleSheet("background-color: lightcoral; color: black;")
        self.clear_terminal_log_btn.setFixedHeight(30)
        self.clear_terminal_log_btn.clicked.connect(self.on_clear_terminal_log_clicked)
        terminal_log_button_layout.addWidget(self.clear_terminal_log_btn)
        
        self.export_terminal_log_btn = QPushButton("匯出終端日誌")
        self.export_terminal_log_btn.setStyleSheet("background-color: lightblue; color: black;")
        self.export_terminal_log_btn.setFixedHeight(30)
        self.export_terminal_log_btn.clicked.connect(self.on_export_terminal_log_clicked)
        terminal_log_button_layout.addWidget(self.export_terminal_log_btn)
        
        # 添加系統資訊按鈕
        self.add_system_info_btn = QPushButton("添加系統資訊")
        self.add_system_info_btn.setStyleSheet("background-color: lightyellow; color: black;")
        self.add_system_info_btn.setFixedHeight(30)
        self.add_system_info_btn.clicked.connect(self.on_add_system_info_clicked)
        terminal_log_button_layout.addWidget(self.add_system_info_btn)
        
        # 添加日誌更新頻率選擇
        self.log_frequency_label = QLabel("更新頻率:")
        self.log_frequency_label.setStyleSheet("color: white;")
        terminal_log_button_layout.addWidget(self.log_frequency_label)
        
        self.log_frequency_combo = QComboBox()
        self.log_frequency_combo.addItems(["1秒", "5秒", "10秒", "30秒", "1分鐘"])
        self.log_frequency_combo.setCurrentText("10秒")
        self.log_frequency_combo.setFixedHeight(30)
        self.log_frequency_combo.currentTextChanged.connect(self.on_log_frequency_changed)
        terminal_log_button_layout.addWidget(self.log_frequency_combo)
        
        # 添加日誌顯示行數選擇
        self.log_lines_label = QLabel("顯示行數:")
        self.log_lines_label.setStyleSheet("color: white;")
        terminal_log_button_layout.addWidget(self.log_lines_label)
        
        self.log_lines_combo = QComboBox()
        self.log_lines_combo.addItems(["50行", "100行", "200行", "500行"])
        self.log_lines_combo.setCurrentText("100行")
        self.log_lines_combo.setFixedHeight(30)
        self.log_lines_combo.currentTextChanged.connect(self.on_log_lines_changed)
        terminal_log_button_layout.addWidget(self.log_lines_combo)
        
        terminal_log_layout.addWidget(terminal_log_button_panel)
        info_layout.addWidget(terminal_log_panel)
        
        # 初始化日誌檔案監控
        self.setup_log_file_monitor()
        
        # 啟動系統監控定時器
        self.start_system_monitoring()
        
        # 批次處理按鈕面板
        batch_panel = QWidget()
        batch_layout = QHBoxLayout(batch_panel)
        batch_layout.setContentsMargins(0, 0, 0, 0)
        
        # 添加處理按鈕
        self.process_basemap_btn = QPushButton("生成 Basemap")
        self.process_basemap_btn.setStyleSheet("background-color: tan; color: black;")
        self.process_basemap_btn.setFixedHeight(40)
        self.process_basemap_btn.clicked.connect(self.on_process_basemap_clicked)
        batch_layout.addWidget(self.process_basemap_btn)
        
        self.process_lossmap_btn = QPushButton("生成 Lossmap")
        self.process_lossmap_btn.setStyleSheet("background-color: tan; color: black;")
        self.process_lossmap_btn.setFixedHeight(40)
        self.process_lossmap_btn.clicked.connect(self.on_process_lossmap_clicked)
        batch_layout.addWidget(self.process_lossmap_btn)
        
        self.process_fpy_btn = QPushButton("生成 FPY")
        self.process_fpy_btn.setStyleSheet("background-color: tan; color: black;")
        self.process_fpy_btn.setFixedHeight(40)
        self.process_fpy_btn.clicked.connect(self.on_process_fpy_clicked)
        batch_layout.addWidget(self.process_fpy_btn)
        
        # 添加在线处理按钮
        self.online_btn = QPushButton("Online")
        self.online_btn.setStyleSheet("background-color: lightgreen; color: black;")
        self.online_btn.setFixedHeight(40)
        self.online_btn.setCheckable(True)  # 使按钮可切换状态
        self.online_btn.clicked.connect(self.on_online_clicked)
        batch_layout.addWidget(self.online_btn)
        
        # 添加自動移動控制按鈕
        self.auto_move_btn = QPushButton("自動移動")
        self.auto_move_btn.setStyleSheet("background-color: orange; color: black;")
        self.auto_move_btn.setFixedHeight(40)
        self.auto_move_btn.setCheckable(True)  # 使按鈕可切換狀態
        self.auto_move_btn.clicked.connect(self.on_auto_move_clicked)
        batch_layout.addWidget(self.auto_move_btn)
        
        # 添加存儲管理按鈕
        self.storage_btn = QPushButton("存儲管理")
        self.storage_btn.setStyleSheet("background-color: purple; color: white;")
        self.storage_btn.setFixedHeight(40)
        self.storage_btn.setCheckable(True)
        self.storage_btn.clicked.connect(self.on_storage_clicked)
        batch_layout.addWidget(self.storage_btn)
        
        self.refresh_btn = QPushButton("重新掃描資料")
        self.refresh_btn.setStyleSheet("background-color: lightblue; color: black;")
        self.refresh_btn.setFixedHeight(40)
        self.refresh_btn.clicked.connect(self.on_refresh_clicked)
        batch_layout.addWidget(self.refresh_btn)
        
        component_layout.addWidget(batch_panel)
        
        # 添加选项卡
        self.detail_tabs.addTab(self.component_tab, "元件列表")
        self.detail_tabs.addTab(self.log_tab, "LOG")
        self.detail_tabs.addTab(self.info_tab, "Info")
        
        bottom_layout.addWidget(self.detail_tabs)
        splitter.addWidget(bottom_panel)
        
        # 設置分割器初始比例
        splitter.setSizes([int(self.height() * 0.4), int(self.height() * 0.6)])
        
        # 建立狀態欄
        self.statusBar = QStatusBar()
        self.setStatusBar(self.statusBar)
        
        # 狀態標籤
        self.status_label = QLabel("就緒")
        self.statusBar.addWidget(self.status_label, 1)
        
        # 數據統計標籤
        self.stats_label = QLabel("")
        self.statusBar.addPermanentWidget(self.stats_label)
        
        # Online状态标签
        self.online_status_label = QLabel("在線監控: 未啟動")
        self.statusBar.addPermanentWidget(self.online_status_label)
        
        # 添加存儲狀態標籤
        self.storage_status_label = QLabel("存儲狀態: 未監控")
        self.statusBar.addPermanentWidget(self.storage_status_label)
        
        # 儲存當前選中的產品/批次/站點
        self.selected_product = None
        self.selected_lot = None
        self.selected_lot_display = None
        self.selected_station = None
        
        # 连接在线处理管理器的信号
        online_manager.log_updated.connect(self.on_log_updated)
        online_manager.processing_status_changed.connect(self.on_processing_status_changed)
    
    def load_data(self):
        """載入資料庫數據"""
        self.statusBar.showMessage("正在載入資料...")
        
        # 清空表格
        self.product_table.setRowCount(0)
        self.component_table.setRowCount(0)
        
        # 獲取所有產品
        products = db_manager.get_products()
        
        # 填充產品資料表
        for product in products:
            # 獲取產品批次
            lots = db_manager.get_lots_by_product(product.product_id)
            
            for lot in lots:
                # 產品和批次數據 - 使用原始批次ID顯示
                row_data = [product.product_id, lot.get_display_id()]
                
                # 各站點數據
                for station in ['MT', 'DC2', 'INNER1', 'RDL', 'INNER2', 'CU', 'EMC']:
                    if station in lot.stations:
                        # 計算元件數量
                        components = db_manager.get_components_by_lot_station(lot.lot_id, station)
                        row_data.append(f"{len(components)} PCS")
                    else:
                        row_data.append("0 PCS")
                
                # 添加行
                row = self.product_table.rowCount()
                self.product_table.insertRow(row)
                
                # 填充資料
                for col, data in enumerate(row_data):
                    item = QTableWidgetItem(data)
                    item.setTextAlignment(Qt.AlignCenter)
                    self.product_table.setItem(row, col, item)
                    
                    # 存儲實際的批次ID作為項目數據，用於後續查詢
                    if col == 1:  # 批次列
                        item.setData(Qt.UserRole, lot.lot_id)  # 存儲內部批次ID
        
        # 更新統計資訊
        stats = db_manager.get_component_count()
        self.stats_label.setText(f"總計: {stats['total']} 個元件")
        
        self.statusBar.showMessage("資料載入完成", 3000)
    
    def on_product_table_cell_clicked(self, row, col):
        """產品資料表點擊事件處理"""
        # 獲取選中的產品和批次
        self.selected_product = self.product_table.item(row, 0).text()
        
        # 獲取批次 - 從UserRole中獲取內部批次ID，顯示仍使用顯示名稱
        lot_item = self.product_table.item(row, 1)
        self.selected_lot = lot_item.data(Qt.UserRole)  # 內部批次ID
        self.selected_lot_display = lot_item.text()  # 顯示名稱
        
        # 獲取選中的站點
        if col >= 2:
            station_index = col - 2
            self.selected_station = ['MT', 'DC2', 'INNER1', 'RDL', 'INNER2', 'CU', 'EMC'][station_index]
        else:
            self.selected_station = None
        
        # 更新元件表格
        self.update_component_table()
    
    def update_component_table(self):
        """更新元件表格"""
        # 清空表格
        self.component_table.setRowCount(0)
        
        if not self.selected_product or not self.selected_lot:
            return
            
        # 要顯示的站點
        stations = []
        if self.selected_station:
            stations.append(self.selected_station)
        else:
            # 如果沒有選擇站點，則顯示所有站點
            lot = db_manager.get_lot(self.selected_lot)
            if lot:
                stations = lot.stations
        
        # 針對每個站點獲取元件
        for station in stations:
            components = db_manager.get_components_by_lot_station(self.selected_lot, station)
            
            for component in components:
                row = self.component_table.rowCount()
                self.component_table.insertRow(row)
                
                # 產品、批次、站點
                self.component_table.setItem(row, 0, self._create_table_item(self.selected_product))
                self.component_table.setItem(row, 1, self._create_table_item(self.selected_lot_display))
                self.component_table.setItem(row, 2, self._create_table_item(station))
                
                # 元件ID
                self.component_table.setItem(row, 3, self._create_table_item(component.component_id))
                
                # Org 狀態
                org_status = "OK" if component.org_path else "NONE"
                self.component_table.setItem(row, 4, self._create_table_item(org_status))
                
                # CSV 狀態
                csv_status = "OK" if component.csv_path else "NONE"
                self.component_table.setItem(row, 5, self._create_table_item(csv_status))
                
                # Basemap 狀態
                basemap_status = "OK" if component.basemap_path else "NONE"
                self.component_table.setItem(row, 6, self._create_table_item(basemap_status))
                
                # Lossmap 狀態
                if station == "MT":
                    lossmap_status = "N/A"
                else:
                    lossmap_status = "OK" if component.lossmap_path else "NONE"
                self.component_table.setItem(row, 7, self._create_table_item(lossmap_status))
                
                # FPY 狀態
                fpy_status = "OK" if component.fpy_path else "NONE"
                self.component_table.setItem(row, 8, self._create_table_item(fpy_status))
                
                # 操作按鈕
                action_widget = QWidget()
                action_layout = QHBoxLayout(action_widget)
                action_layout.setContentsMargins(0, 0, 0, 0)
                
                view_btn = QPushButton("查看")
                view_btn.clicked.connect(lambda checked=False, c=component: self.on_view_component(c))
                action_layout.addWidget(view_btn)
                
                self.component_table.setCellWidget(row, 9, action_widget)
    
    def _create_table_item(self, text):
        """創建表格項目並設置為居中"""
        item = QTableWidgetItem(text)
        item.setTextAlignment(Qt.AlignCenter)
        return item
    
    def on_view_component(self, component):
        """查看元件"""
        # 顯示元件信息和圖像
        # 這裡只是一個簡單的消息框，實際應用中可以顯示更詳細的對話框
        QMessageBox.information(
            self, 
            "元件信息", 
            f"元件ID: {component.component_id}\n"
            f"批次: {component.lot_id}\n"
            f"站點: {component.station}\n"
            f"CSV: {component.csv_path}\n"
            f"Basemap: {component.basemap_path}\n"
            f"Lossmap: {component.lossmap_path}\n"
            f"FPY: {component.fpy_path}"
        )
    
    def show_component_context_menu(self, position):
        """顯示元件表格的右鍵選單"""
        # 獲取選中的行
        selected_rows = set()
        for item in self.component_table.selectedItems():
            selected_rows.add(item.row())
        
        if not selected_rows:
            return
        
        # 創建右鍵選單
        context_menu = QMenu(self)
        
        if len(selected_rows) == 1:
            # 單選情況 - 原有的單個移動功能
            row = list(selected_rows)[0]
            
            # 獲取該行的組件信息
            product_item = self.component_table.item(row, 0)
            lot_item = self.component_table.item(row, 1)
            station_item = self.component_table.item(row, 2)
            component_id_item = self.component_table.item(row, 3)
            
            if not all([product_item, lot_item, station_item, component_id_item]):
                return
            
            product = product_item.text()
            lot_display = lot_item.text()
            station = station_item.text()
            component_id = component_id_item.text()
            
            # 獲取實際的批次ID
            lot_id = self.selected_lot  # 使用當前選擇的lot_id
            
            # 添加移動檔案選項
            move_action = QAction("移動檔案", self)
            move_action.triggered.connect(
                lambda: self.show_move_file_dialog(component_id, lot_id, station, product)
            )
            context_menu.addAction(move_action)
            
            # 添加分隔線
            context_menu.addSeparator()
            
            # 添加查看詳情選項
            view_action = QAction("查看詳情", self)
            view_action.triggered.connect(
                lambda: self.view_component_details(component_id, lot_id, station)
            )
            context_menu.addAction(view_action)
            
        else:
            # 多選情況 - 批量移動功能
            # 添加批量移動檔案選項
            batch_move_action = QAction(f"批量移動檔案 ({len(selected_rows)} 個項目)", self)
            batch_move_action.triggered.connect(
                lambda: self.show_batch_move_file_dialog(selected_rows)
            )
            context_menu.addAction(batch_move_action)
        
        # 顯示選單
        context_menu.exec(self.component_table.mapToGlobal(position))
    
    def show_move_file_dialog(self, component_id: str, lot_id: str, station: str, source_product: str):
        """顯示移動檔案對話框"""
        try:
            # 創建移動檔案對話框
            dialog = MoveFileDialog(component_id, lot_id, station, source_product, self)
            
            # 連接移動請求信號
            dialog.move_requested.connect(self.handle_move_file_request)
            
            # 顯示對話框
            dialog.exec()
            
        except Exception as e:
            logger.error(f"顯示移動檔案對話框失敗: {e}")
            QMessageBox.critical(self, "錯誤", f"無法顯示移動檔案對話框: {str(e)}")
    
    def handle_move_file_request(self, component_id: str, lot_id: str, station: str, 
                               source_product: str, target_product: str, file_types: list):
        """處理移動檔案請求"""
        try:
            # 創建移動檔案任務
            move_params = {
                'source_product': source_product,
                'target_product': target_product,
                'file_types': file_types
            }
            
            # 創建任務對話框
            file_types_str = ", ".join(file_types)
            dialog = TaskProgressDialog(
                "移動檔案", 
                f"正在移動組件 {component_id} 的檔案...\n"
                f"從 {source_product} 到 {target_product}\n"
                f"檔案類型: {file_types_str}",
                self
            )
            
            # 創建移動檔案任務
            task_id = data_processor.create_task(
                "move_files",
                target_product,  # 使用目標產品作為product_id
                lot_id,
                station,
                component_id=component_id,
                move_params=move_params
            )
            
            dialog.set_task_id(task_id)
            dialog.exec()
            
            # 刷新資料
            self.update_component_table()
            
        except Exception as e:
            logger.error(f"處理移動檔案請求失敗: {e}")
            QMessageBox.critical(self, "錯誤", f"移動檔案失敗: {str(e)}")
    
    def view_component_details(self, component_id: str, lot_id: str, station: str):
        """查看組件詳細信息"""
        try:
            component = db_manager.get_component(lot_id, station, component_id)
            if component:
                self.on_view_component(component)
            else:
                QMessageBox.warning(self, "警告", f"找不到組件: {component_id}")
        except Exception as e:
            logger.error(f"查看組件詳情失敗: {e}")
            QMessageBox.critical(self, "錯誤", f"無法查看組件詳情: {str(e)}")
    
    def show_batch_move_file_dialog(self, selected_rows: set):
        """顯示批量移動檔案對話框"""
        try:
            # 從選中的行收集組件數據
            components_data = []
            for row in selected_rows:
                product_item = self.component_table.item(row, 0)
                lot_item = self.component_table.item(row, 1)
                station_item = self.component_table.item(row, 2)
                component_id_item = self.component_table.item(row, 3)
                
                if all([product_item, lot_item, station_item, component_id_item]):
                    components_data.append((
                        component_id_item.text(),  # component_id
                        self.selected_lot,         # lot_id (使用內部ID)
                        station_item.text(),       # station
                        product_item.text()        # source_product
                    ))
            
            if not components_data:
                QMessageBox.warning(self, "警告", "無法獲取選中的組件信息")
                return
            
            # 創建批量移動檔案對話框
            dialog = BatchMoveFileDialog(components_data, self)
            
            # 連接批量移動請求信號
            dialog.batch_move_requested.connect(self.handle_batch_move_file_request)
            
            # 顯示對話框
            dialog.exec()
            
        except Exception as e:
            logger.error(f"顯示批量移動檔案對話框失敗: {e}")
            QMessageBox.critical(self, "錯誤", f"無法顯示批量移動檔案對話框: {str(e)}")
    
    def handle_batch_move_file_request(self, components_data: list, target_product: str, file_types: list):
        """處理批量移動檔案請求"""
        try:
            # 創建批量移動檔案任務參數
            batch_move_params = {
                'components_data': components_data,
                'target_product': target_product,
                'file_types': file_types
            }
            
            # 使用第一個組件的信息創建任務（批量移動將在後台處理所有組件）
            first_component = components_data[0]
            task_id = data_processor.create_task(
                "batch_move_files",
                target_product,  # 使用目標產品作為product_id
                first_component[1],  # lot_id
                first_component[2],  # station
                component_id=first_component[0],  # component_id
                batch_move_params=batch_move_params
            )
            
            # 顯示開始訊息，但不阻塞界面
            file_types_str = ", ".join(file_types)
            source_products = set(comp[3] for comp in components_data)
            source_products_str = ", ".join(source_products)
            
            self.statusBar.showMessage(
                f"已開始批量移動 {len(components_data)} 個組件的檔案 "
                f"(從 {source_products_str} 到 {target_product})，請查看LOG頁面了解進度",
                5000
            )
            
            # 自動切換到LOG頁面
            self.detail_tabs.setCurrentIndex(1)  # 切換到LOG頁面
            
            logger.info(f"已啟動批量移動任務 {task_id}: {len(components_data)} 個組件")
            
        except Exception as e:
            logger.error(f"處理批量移動檔案請求失敗: {e}")
            QMessageBox.critical(self, "錯誤", f"批量移動檔案失敗: {str(e)}")
    
    def on_process_basemap_clicked(self):
        """生成 Basemap 按鈕點擊事件"""
        if not self.selected_product or not self.selected_lot or not self.selected_station:
            QMessageBox.warning(self, "警告", "請先選擇產品、批次和站點")
            return
        
        # 創建任務對話框
        dialog = TaskProgressDialog(
            "生成 Basemap", 
            f"正在為 {self.selected_product}/{self.selected_lot_display}/{self.selected_station} 生成 Basemap...\n"
            f"流程將遵循原始databasemanager的執行順序：\n"
            f"1. 讀取config參數\n"
            f"2. 原始 CSV 偏移確認\n"
            f"3. 去表頭 + rename\n"
            f"4. 做 Basemap",
            self
        )
        
        # 創建任務並獲取ID
        task_id = data_processor.create_task(
            "basemap", 
            self.selected_product, 
            self.selected_lot, 
            self.selected_station,
            # 不再傳遞回調函數，因為我們使用信號槽連接在MainWindow的init中
            # callback=self.on_task_completed
        )
        
        dialog.set_task_id(task_id)
        dialog.exec()
    
    def on_process_lossmap_clicked(self):
        """生成 Lossmap 按鈕點擊事件"""
        if not self.selected_product or not self.selected_lot or not self.selected_station:
            QMessageBox.warning(self, "警告", "請先選擇產品、批次和站點")
            return
        
        # 第一站不能生成Lossmap
        if self.selected_station == "MT":
            QMessageBox.warning(self, "警告", "第一站不能生成 Lossmap")
            return
        
        # 創建任務對話框
        dialog = TaskProgressDialog(
            "生成 Lossmap", 
            f"正在為 {self.selected_product}/{self.selected_lot_display}/{self.selected_station} 生成 Lossmap...",
            self
        )
        
        # 創建任務並獲取ID
        task_id = data_processor.create_task(
            "lossmap", 
            self.selected_product, 
            self.selected_lot, 
            self.selected_station,
            # callback=self.on_task_completed
        )
        
        dialog.set_task_id(task_id)
        dialog.exec()
    
    def on_process_fpy_clicked(self):
        """生成 FPY 按鈕點擊事件"""
        if not self.selected_product or not self.selected_lot or not self.selected_station:
            QMessageBox.warning(self, "警告", "請先選擇產品、批次和站點")
            return
        
        # 詢問用戶是否使用並行處理
        reply = QMessageBox.question(
            self, 
            "FPY處理模式", 
            "是否使用並行處理模式？\n\n並行模式可提高大量元件的處理速度，但可能需要更多記憶體。",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        
        # 根據用戶選擇決定任務類型
        task_type = "fpy_parallel" if reply == QMessageBox.Yes else "fpy"
        
        # 創建任務對話框
        dialog = TaskProgressDialog(
            "生成 FPY", 
            f"正在為 {self.selected_product}/{self.selected_lot_display}/{self.selected_station} 生成 FPY" +
            (" (並行模式)" if task_type == "fpy_parallel" else "") + "...",
            self
        )
        
        # 創建任務並獲取ID
        task_id = data_processor.create_task(
            task_type, 
            self.selected_product, 
            self.selected_lot, 
            self.selected_station,
            # 不再傳遞回調函數
            # callback=self.on_task_completed
        )
        
        dialog.set_task_id(task_id)
        dialog.exec()
    
    def on_refresh_clicked(self):
        """刷新資料按鈕點擊事件"""
        # 重新掃描資料庫
        db_manager.scan_database()
        
        # 重新載入資料
        self.load_data()
    
    @Slot(str, bool, str)
    def on_task_completed(self, task_id, success, message):
        """任務完成回調 - 使用Qt槽接收信號"""
        # 獲取任務信息
        task_status = data_processor.get_task_status(task_id)
        if task_status and "task" in task_status:
            task = task_status["task"]
            task_type = task.get("task_type", "")
            
            # 如果是批量移動任務，顯示完成訊息
            if task_type == "batch_move_files":
                if success:
                    self.statusBar.showMessage(f"批量移動檔案完成: {message}", 5000)
                else:
                    self.statusBar.showMessage(f"批量移動檔案失敗: {message}", 5000)
        
        # 重新載入元件表格
        self.update_component_table()
    
    def on_online_clicked(self):
        """在線處理按鈕點擊事件"""
        if self.online_btn.isChecked():
            # 启动在线监控
            online_manager.start()
            self.online_btn.setText("Online (運行中)")
            self.online_btn.setStyleSheet("background-color: green; color: white;")
            self.statusBar.showMessage("在線監控已啟動")
        else:
            # 停止在线监控
            online_manager.stop()
            self.online_btn.setText("Online")
            self.online_btn.setStyleSheet("background-color: lightgreen; color: black;")
            self.statusBar.showMessage("在線監控已停止")
    
    def on_auto_move_clicked(self):
        """自動移動控制按鈕點擊事件"""
        if self.auto_move_btn.isChecked():
            online_manager.start_auto_move()
            self.auto_move_btn.setText("自動移動 (運行中)")
            self.auto_move_btn.setStyleSheet("background-color: darkgreen; color: white;")
            self.statusBar.showMessage("自動移動已啟動")
        else:
            online_manager.stop_auto_move()
            self.auto_move_btn.setText("自動移動")
            self.auto_move_btn.setStyleSheet("background-color: orange; color: black;")
            self.statusBar.showMessage("自動移動已停止")
    
    def on_storage_clicked(self):
        """存儲管理按鈕點擊事件"""
        if self.storage_btn.isChecked():
            storage_manager.start_storage_management()
            self.storage_btn.setText("存儲管理 (運行中)")
            self.storage_btn.setStyleSheet("background-color: darkpurple; color: white;")
            self.statusBar.showMessage("存儲管理已啟動")
            
            # 啟動存儲狀態更新定時器
            self.storage_timer = QTimer()
            self.storage_timer.timeout.connect(self.update_storage_status)
            self.storage_timer.start(30000)  # 每30秒更新一次
        else:
            storage_manager.stop_storage_management()
            self.storage_btn.setText("存儲管理")
            self.storage_btn.setStyleSheet("background-color: purple; color: white;")
            self.statusBar.showMessage("存儲管理已停止")
            
            if hasattr(self, 'storage_timer'):
                self.storage_timer.stop()
    
    def update_storage_status(self):
        """更新存儲狀態"""
        try:
            status_info = storage_manager.monitor.get_storage_info()
            self.storage_status_label.setText(f"存儲: {status_info}")
        except Exception as e:
            logger.error(f"更新存儲狀態失敗: {e}")
    
    def on_log_updated(self, log):
        """處理日誌更新"""
        if log is None:
            # 清空日誌表格
            self.log_table.setRowCount(0)
            return
        
        # 獲取日誌摘要
        summary = log.get_summary()
        component_id = summary["component_id"]
        current_status = summary["status"]
        
        # 檢查是否存在相同組件ID的暫態記錄需要更新
        existing_row = -1
        for row in range(self.log_table.rowCount()):
            row_component_id = self.log_table.item(row, 4).text()
            row_status = self.log_table.item(row, 5).text()
            
            # 只有當組件ID相同，且原狀態為暫態(pending或processing)時才考慮更新
            if row_component_id == component_id and (row_status == "pending" or row_status == "processing"):
                existing_row = row
                break
                
        # 如果找到需要更新的行，更新它
        if existing_row >= 0:
            self._update_log_row(existing_row, summary)
        else:
            # 否則添加新行（當是新組件或者是之前沒有暫態記錄時）
            row = self.log_table.rowCount()
            self.log_table.insertRow(row)
            self._update_log_row(row, summary)
        
        # 滾動到最新行
        self.log_table.scrollToBottom()
        
        # 添加到詳細日誌區域
        # self.add_to_detailed_log(summary) # 移除此行
    
    def _update_log_row(self, row, log_summary):
        """更新日誌表格行"""
        # 设置单元格内容
        self.log_table.setItem(row, 0, QTableWidgetItem(log_summary["timestamp"]))
        self.log_table.setItem(row, 1, QTableWidgetItem(log_summary["product_id"]))
        self.log_table.setItem(row, 2, QTableWidgetItem(log_summary["lot_id"]))
        self.log_table.setItem(row, 3, QTableWidgetItem(log_summary["station"]))
        self.log_table.setItem(row, 4, QTableWidgetItem(log_summary["component_id"]))
        
        # 根据状态设置颜色
        status_item = QTableWidgetItem(log_summary["status"])
        if log_summary["status"] == "completed":
            status_item.setBackground(QColor("green"))
            status_item.setForeground(QColor("white"))
        elif log_summary["status"] == "failed":
            status_item.setBackground(QColor("red"))
            status_item.setForeground(QColor("white"))
        elif log_summary["status"] == "processing":
            status_item.setBackground(QColor("blue"))
            status_item.setForeground(QColor("white"))
        self.log_table.setItem(row, 5, status_item)
        
        # 设置消息
        message = f"{log_summary['message']} ({log_summary['duration']})"
        self.log_table.setItem(row, 6, QTableWidgetItem(message))
    
    def add_system_info_to_log(self):
        """添加系統資訊到終端日誌"""
        try:
            import psutil
            from datetime import datetime
            
            # 獲取系統資訊
            cpu_percent = psutil.cpu_percent(interval=1)
            memory_info = psutil.Process(os.getpid()).memory_info()
            memory_mb = memory_info.rss / (1024 * 1024)
            disk_usage = psutil.disk_usage('C:/')
            disk_percent = disk_usage.percent
            disk_free_gb = disk_usage.free / (1024 * 1024 * 1024)
            
            # 獲取應用程式狀態
            online_status = "運行中" if online_manager.is_running else "已停止"
            auto_move_status = "運行中" if hasattr(online_manager, 'is_auto_move_running') and online_manager.is_auto_move_running else "已停止"
            storage_status = "運行中" if storage_manager.is_running else "已停止"
            
            # 格式化系統資訊日誌
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            system_log = f"[{timestamp}] 🔧 系統監控 - CPU: {cpu_percent}% | 記憶體: {memory_mb:.1f}MB | 磁碟: {disk_percent}% ({disk_free_gb:.1f}GB可用) | 在線監控: {online_status} | 自動移動: {auto_move_status} | 存儲管理: {storage_status}"
            
            # 直接添加到終端日誌
            logger.info(system_log)
            
        except Exception as e:
            logger.error(f"添加系統資訊到日誌失敗: {e}")
    
    def _manage_log_size(self):
        """管理日誌大小，避免過度累積"""
        try:
            # 從配置獲取日誌管理設定
            max_lines = config.get("ui.log_max_lines", 1000)
            keep_lines = config.get("ui.log_keep_lines", 500)
            
            # 獲取當前日誌內容
            log_content = self.detailed_log_text.toPlainText()
            lines = log_content.split('\n')
            
            # 如果行數超過限制，保留指定行數
            if len(lines) > max_lines:
                # 保留最後指定行數
                kept_lines = lines[-keep_lines:]
                self.detailed_log_text.setPlainText('\n'.join(kept_lines))
                
                # 添加清理提示
                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                cleanup_notice = f"[{timestamp}] 🧹 日誌已自動清理，保留最新{keep_lines}行記錄\n"
                self.detailed_log_text.append(cleanup_notice)
                
                logger.info(f"詳細日誌已自動清理，保留最新{keep_lines}行")
            
        except Exception as e:
            logger.error(f"管理日誌大小失敗: {e}")
    
    def start_system_monitoring(self):
        """啟動系統監控定時器"""
        try:
            # 從配置獲取監控頻率，預設30秒
            monitor_interval = config.get("ui.system_monitor_interval_seconds", 30)
            
            # 創建系統監控定時器
            self.system_monitor_timer = QTimer()
            self.system_monitor_timer.timeout.connect(self.add_system_info_to_log)
            self.system_monitor_timer.start(monitor_interval * 1000)  # 轉換為毫秒
            
            logger.info(f"系統監控定時器已啟動，每{monitor_interval}秒記錄系統資訊")
            
        except Exception as e:
            logger.error(f"啟動系統監控失敗: {e}")
    
    def stop_system_monitoring(self):
        """停止系統監控定時器"""
        try:
            if hasattr(self, 'system_monitor_timer'):
                self.system_monitor_timer.stop()
                logger.info("系統監控定時器已停止")
        except Exception as e:
            logger.error(f"停止系統監控失敗: {e}")
    
    def on_processing_status_changed(self, status, queue_size, processed_count):
        """處理在線處理狀態變化"""
        if status == "running":
            status_text = f"在線監控: 運行中 | 佇列: {queue_size} | 已處理: {processed_count}"
        else:
            status_text = f"在線監控: 已停止 | 佇列: {queue_size} | 已處理: {processed_count}"
        
        self.online_status_label.setText(status_text)
    
    def on_clear_log_clicked(self):
        """清空日誌按鈕點擊事件"""
        reply = QMessageBox.question(
            self, 
            "確認清空", 
            "確定要清空所有日誌記錄嗎？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            online_manager.clear_logs()
            self.statusBar.showMessage("日誌已清空")
    
    def on_refresh_info_clicked(self):
        """刷新資訊按鈕點擊事件"""
        # 現在這個按鈕用於手動觸發系統資訊記錄
        self.add_system_info_to_log()
        self.statusBar.showMessage("系統資訊已添加到終端日誌")
    
    def on_add_system_info_clicked(self):
        """添加系統資訊按鈕點擊事件"""
        self.add_system_info_to_log()
        self.statusBar.showMessage("系統資訊已添加到終端日誌")
    
    def on_filter_log_clicked(self):
        """日誌過濾按鈕點擊事件"""
        if self.filter_log_btn.isChecked():
            # 啟用日誌過濾
            self.enable_log_filter()
            self.filter_log_btn.setText("日誌過濾 (開啟)")
            self.filter_log_btn.setStyleSheet("background-color: darkgreen; color: white;")
            self.statusBar.showMessage("日誌過濾已開啟，只顯示重要日誌")
        else:
            # 關閉日誌過濾
            self.disable_log_filter()
            self.filter_log_btn.setText("日誌過濾")
            self.filter_log_btn.setStyleSheet("background-color: lightgreen; color: black;")
            self.statusBar.showMessage("日誌過濾已關閉，顯示所有日誌")
    
    def enable_log_filter(self):
        """啟用日誌過濾"""
        try:
            if hasattr(self, 'terminal_log_handler'):
                # 設置過濾器，只顯示重要日誌
                self.terminal_log_handler.setLevel(logging.WARNING)
                logger.info("日誌過濾已啟用，只顯示警告及以上級別的日誌")
        except Exception as e:
            logger.error(f"啟用日誌過濾失敗: {e}")
    
    def disable_log_filter(self):
        """關閉日誌過濾"""
        try:
            if hasattr(self, 'terminal_log_handler'):
                # 恢復顯示所有日誌
                self.terminal_log_handler.setLevel(logging.INFO)
                logger.info("日誌過濾已關閉，顯示所有日誌")
        except Exception as e:
            logger.error(f"關閉日誌過濾失敗: {e}")
    
    def on_emergency_stop_clicked(self):
        """緊急停止按鈕點擊事件"""
        reply = QMessageBox.question(
            self, 
            "確認緊急停止", 
            "確定要緊急停止所有日誌捕獲和輸出嗎？這將會關閉所有日誌輸出，並停止系統監控。",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            self.stop_system_monitoring()
            self.terminal_log_text.clear()
            self.statusBar.showMessage("緊急停止成功，所有日誌已清除。")
            logger.warning("緊急停止：所有日誌捕獲和輸出已關閉。")
        else:
            logger.info("緊急停止已取消。")
    
    def closeEvent(self, event):
        """窗口关闭事件处理"""
        # 停止系統監控定時器
        self.stop_system_monitoring()
        
        # 停止日誌檔案監控定時器
        if hasattr(self, 'log_update_timer'):
            self.log_update_timer.stop()
        
        # 确保在线监控正确停止
        if online_manager.is_running:
            online_manager.stop()
        
        # 接受关闭事件
        event.accept() 

    def setup_terminal_log_capture(self):
        """設置終端日誌捕獲"""
        try:
            import logging
            import sys
            from io import StringIO
            import threading
            import queue
            
            # 創建自定義日誌處理器
            class TerminalLogHandler(logging.Handler):
                def __init__(self, text_widget):
                    super().__init__()
                    self.text_widget = text_widget
                    self.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
                    
                    # 使用線程安全的隊列
                    self.log_queue = queue.Queue()
                    self.buffer_size = 20  # 更小的緩衝區
                    self.last_update = 0
                    self.update_interval = 200  # 200毫秒更新一次
                    self.max_log_lines = 200  # 更嚴格的限制
                    self.keep_log_lines = 100  # 更少的保留行數
                    
                    # 啟動更新線程
                    self.update_thread = threading.Thread(target=self._update_worker, daemon=True)
                    self.update_thread.start()
                    
                def emit(self, record):
                    try:
                        msg = self.format(record)
                        # 根據日誌級別設置顏色
                        color = {
                            'DEBUG': '#888888',
                            'INFO': '#ffffff',
                            'WARNING': '#ffaa00',
                            'ERROR': '#ff4444',
                            'CRITICAL': '#ff0000'
                        }.get(record.levelname, '#ffffff')
                        
                        # 添加到隊列
                        log_entry = f'<span style="color: {color};">{msg}</span>'
                        self.log_queue.put(log_entry)
                        
                        # 限制隊列大小
                        while self.log_queue.qsize() > self.buffer_size:
                            try:
                                self.log_queue.get_nowait()
                            except queue.Empty:
                                break
                        
                    except Exception as e:
                        print(f"日誌處理錯誤: {e}")
                
                def _update_worker(self):
                    """更新工作線程"""
                    import time
                    while True:
                        try:
                            # 收集所有待處理的日誌
                            logs_to_add = []
                            while not self.log_queue.empty() and len(logs_to_add) < 10:
                                try:
                                    log_entry = self.log_queue.get_nowait()
                                    logs_to_add.append(log_entry)
                                except queue.Empty:
                                    break
                            
                            # 如果有日誌要添加
                            if logs_to_add:
                                # 使用QTimer在主線程中更新UI
                                from PySide6.QtCore import QTimer
                                QTimer.singleShot(0, lambda: self._safe_update_ui(logs_to_add))
                            
                            time.sleep(0.1)  # 100毫秒檢查一次
                            
                        except Exception as e:
                            print(f"更新工作線程錯誤: {e}")
                            time.sleep(0.5)
                
                def _safe_update_ui(self, logs_to_add):
                    """安全地更新UI"""
                    try:
                        # 檢查日誌大小並清理
                        self._manage_log_size()
                        
                        # 批量添加日誌
                        for log_entry in logs_to_add:
                            self.text_widget.append(log_entry)
                        
                        # 自動滾動到底部
                        self.text_widget.verticalScrollBar().setValue(
                            self.text_widget.verticalScrollBar().maximum()
                        )
                        
                    except Exception as e:
                        print(f"安全更新UI失敗: {e}")
                
                def _manage_log_size(self):
                    """管理日誌大小"""
                    try:
                        # 獲取當前日誌內容
                        log_content = self.text_widget.toPlainText()
                        lines = log_content.split('\n')
                        
                        # 如果行數超過限制，保留指定行數
                        if len(lines) > self.max_log_lines:
                            # 保留最後指定行數
                            kept_lines = lines[-self.keep_log_lines:]
                            self.text_widget.setPlainText('\n'.join(kept_lines))
                            
                            # 添加清理提示
                            from datetime import datetime
                            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                            cleanup_notice = f"[{timestamp}] 🧹 終端日誌已自動清理，保留最新{self.keep_log_lines}行記錄"
                            self.text_widget.append(cleanup_notice)
                            
                    except Exception as e:
                        print(f"管理終端日誌大小失敗: {e}")
            
            # 創建並設置日誌處理器
            self.terminal_log_handler = TerminalLogHandler(self.terminal_log_text)
            self.terminal_log_handler.setLevel(logging.INFO)
            
            # 添加到根日誌記錄器
            logging.getLogger().addHandler(self.terminal_log_handler)
            
            # 添加啟動訊息
            from datetime import datetime
            startup_msg = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 🚀 終端日誌捕獲已啟動 (優化模式)"
            self.terminal_log_text.append(startup_msg)
            
            logger.info("終端日誌捕獲已設置 (優化模式)")
            
        except Exception as e:
            logger.error(f"設置終端日誌捕獲失敗: {e}")
    
    def setup_log_file_monitor(self):
        """設置日誌檔案監控"""
        try:
            # 採用與 logger.py 相同的路徑解析邏輯
            def get_base_dir() -> Path:
                """取得主程式或執行檔所在目錄"""
                if getattr(sys, 'frozen', False):
                    return Path(sys.executable).parent
                return Path(sys.argv[0]).resolve().parent
            
            def resolve_log_dir(config_dir: str) -> Path:
                """依據相對或絕對路徑建立 log 目錄"""
                raw_path = Path(config_dir)
                if raw_path.is_absolute():
                    return raw_path
                return get_base_dir() / raw_path
            
            # 動態確定日誌目錄路徑
            base_dir = get_base_dir()
            logs_dir = resolve_log_dir("logs")
            
            logger.info(f"基礎目錄: {base_dir}")
            logger.info(f"日誌目錄: {logs_dir}")
            
            # 確保日誌目錄存在
            if not logs_dir.exists():
                logger.warning(f"日誌目錄不存在: {logs_dir}")
                # 嘗試創建日誌目錄
                try:
                    logs_dir.mkdir(parents=True, exist_ok=True)
                    logger.info(f"已創建日誌目錄: {logs_dir}")
                except Exception as e:
                    logger.error(f"創建日誌目錄失敗: {e}")
            
            # 日誌檔案路徑列表（使用絕對路徑）
            self.log_file_paths = [
                logs_dir / "data_processor.log",
                logs_dir / "app.log"
            ]
            
            # 監控設定
            self.log_update_interval = 10  # 預設10秒
            self.log_display_lines = 100   # 預設100行
            self.last_log_size = 0         # 記錄上次檔案大小
            
            # 創建日誌更新定時器
            self.log_update_timer = QTimer()
            self.log_update_timer.timeout.connect(self.update_log_display)
            self.log_update_timer.start(self.log_update_interval * 1000)  # 轉換為毫秒
            
            # 初始化顯示
            self.update_log_display()
            
            logger.info("日誌檔案監控已設置 (支持多個日誌檔案)")
            
        except Exception as e:
            logger.error(f"設置日誌檔案監控失敗: {e}")
    
    def update_log_display(self):
        """更新日誌顯示"""
        try:
            all_log_lines = []
            total_lines = 0
            existing_files = 0
            
            # 讀取所有日誌檔案
            for log_path in self.log_file_paths:
                absolute_path = log_path.absolute()
                if log_path.exists():
                    existing_files += 1
                    try:
                        # 檢查檔案大小
                        file_size = absolute_path.stat().st_size
                        if file_size == 0:
                            logger.debug(f"日誌檔案為空: {absolute_path}")
                            continue
                        
                        with open(log_path, 'r', encoding='utf-8') as f:
                            lines = f.readlines()
                        
                        # 為每行添加檔案標識
                        for line in lines:
                            # 添加檔案標識到行首
                            file_name = log_path.name
                            timestamp = line.split(' - ')[0] if ' - ' in line else ''
                            if timestamp:
                                # 如果行有時間戳，在時間戳後添加檔案標識
                                parts = line.split(' - ', 1)
                                if len(parts) == 2:
                                    timestamp_part = parts[0]
                                    content_part = parts[1]
                                    marked_line = f"{timestamp_part} [{file_name}] - {content_part}"
                                else:
                                    marked_line = f"{line.rstrip()} [{file_name}]"
                            else:
                                marked_line = f"{line.rstrip()} [{file_name}]"
                            
                            all_log_lines.append(marked_line)
                        
                        total_lines += len(lines)
                        logger.debug(f"成功讀取日誌檔案: {absolute_path} ({len(lines)} 行)")
                        
                    except UnicodeDecodeError as e:
                        logger.error(f"日誌檔案編碼錯誤 {absolute_path}: {e}")
                        error_line = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] ERROR - 日誌檔案編碼錯誤: {log_path.name} [{log_path.name}]"
                        all_log_lines.append(error_line)
                    except PermissionError as e:
                        logger.error(f"日誌檔案權限錯誤 {absolute_path}: {e}")
                        error_line = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] ERROR - 日誌檔案權限錯誤: {log_path.name} [{log_path.name}]"
                        all_log_lines.append(error_line)
                    except Exception as e:
                        logger.error(f"讀取日誌檔案 {absolute_path} 失敗: {e}")
                        error_line = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] ERROR - 讀取日誌檔案 {log_path.name} 失敗: {str(e)} [{log_path.name}]"
                        all_log_lines.append(error_line)
                else:
                    # 如果檔案不存在，添加提示
                    missing_line = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] INFO - 日誌檔案不存在: {log_path.name} (路徑: {absolute_path}) [{log_path.name}]"
                    all_log_lines.append(missing_line)
                    logger.debug(f"日誌檔案不存在: {absolute_path}")
            
            # 如果沒有找到任何日誌檔案
            if existing_files == 0:
                # 獲取基礎目錄信息
                def get_base_dir() -> Path:
                    if getattr(sys, 'frozen', False):
                        return Path(sys.executable).parent
                    return Path(sys.argv[0]).resolve().parent
                
                base_dir = get_base_dir()
                current_dir = Path.cwd()
                error_msg = f"未找到任何日誌檔案:\n"
                error_msg += f"基礎目錄: {base_dir}\n"
                error_msg += f"當前工作目錄: {current_dir}\n"
                error_msg += f"嘗試讀取的檔案:\n"
                for log_path in self.log_file_paths:
                    error_msg += f"- {log_path.absolute()}\n"
                error_msg += f"\n請確保應用程式已運行並產生日誌。"
                self.terminal_log_text.setPlainText(error_msg)
                return
            
            # 按時間戳排序所有日誌行
            def extract_timestamp(line):
                try:
                    # 嘗試提取時間戳
                    if '[' in line and ']' in line:
                        # 移除檔案標識後提取時間戳
                        clean_line = line.split(' [')[0]
                        if ' - ' in clean_line:
                            timestamp_str = clean_line.split(' - ')[0]
                            # 嘗試解析時間戳
                            from datetime import datetime
                            return datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S')
                except:
                    pass
                # 如果無法解析，返回最小時間
                from datetime import datetime
                return datetime.min
            
            # 排序日誌行
            all_log_lines.sort(key=extract_timestamp)
            
            # 獲取最新的指定行數
            display_lines = all_log_lines[-self.log_display_lines:] if len(all_log_lines) > self.log_display_lines else all_log_lines
            
            # 格式化日誌內容
            formatted_lines = []
            for line in display_lines:
                # 根據日誌級別添加顏色
                if "ERROR" in line or "CRITICAL" in line:
                    formatted_lines.append(f'<span style="color: #ff4444;">{line.rstrip()}</span>')
                elif "WARNING" in line:
                    formatted_lines.append(f'<span style="color: #ffaa00;">{line.rstrip()}</span>')
                elif "DEBUG" in line:
                    formatted_lines.append(f'<span style="color: #888888;">{line.rstrip()}</span>')
                else:
                    formatted_lines.append(f'<span style="color: #ffffff;">{line.rstrip()}</span>')
            
            # 更新顯示
            self.terminal_log_text.setHtml('<br>'.join(formatted_lines))
            
            # 自動滾動到底部
            self.terminal_log_text.verticalScrollBar().setValue(
                self.terminal_log_text.verticalScrollBar().maximum()
            )
            
            # 更新狀態欄
            self.statusBar.showMessage(f"日誌已更新 - 顯示最新 {len(display_lines)} 行，總共 {total_lines} 行，來自 {existing_files} 個檔案")
            
        except Exception as e:
            logger.error(f"更新日誌顯示失敗: {e}")
            self.terminal_log_text.setPlainText(f"讀取日誌檔案失敗: {str(e)}")
    
    def on_log_frequency_changed(self, frequency_text):
        """日誌更新頻率改變事件"""
        try:
            # 解析頻率設定
            frequency_map = {
                "1秒": 1,
                "5秒": 5,
                "10秒": 10,
                "30秒": 30,
                "1分鐘": 60
            }
            
            new_interval = frequency_map.get(frequency_text, 10)
            self.log_update_interval = new_interval
            
            # 重新啟動定時器
            self.log_update_timer.stop()
            self.log_update_timer.start(new_interval * 1000)
            
            logger.info(f"日誌更新頻率已更改為: {frequency_text}")
            self.statusBar.showMessage(f"日誌更新頻率已更改為: {frequency_text}")
            
        except Exception as e:
            logger.error(f"更改日誌更新頻率失敗: {e}")
    
    def on_log_lines_changed(self, lines_text):
        """日誌顯示行數改變事件"""
        try:
            # 解析行數設定
            lines_map = {
                "50行": 50,
                "100行": 100,
                "200行": 200,
                "500行": 500
            }
            
            new_lines = lines_map.get(lines_text, 100)
            self.log_display_lines = new_lines
            
            # 立即更新顯示
            self.update_log_display()
            
            logger.info(f"日誌顯示行數已更改為: {lines_text}")
            self.statusBar.showMessage(f"日誌顯示行數已更改為: {lines_text}")
            
        except Exception as e:
            logger.error(f"更改日誌顯示行數失敗: {e}")
    
    def on_clear_terminal_log_clicked(self):
        """清空終端日誌按鈕點擊事件"""
        reply = QMessageBox.question(
            self, 
            "確認清空", 
            "確定要清空終端日誌顯示嗎？\n注意：這只會清空顯示，不會刪除實際的日誌檔案。",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            self.terminal_log_text.clear()
            self.statusBar.showMessage("終端日誌顯示已清空")
    
    def on_export_terminal_log_clicked(self):
        """匯出終端日誌按鈕點擊事件"""
        try:
            file_path, _ = QFileDialog.getSaveFileName(
                self, 
                "匯出終端日誌", 
                "terminal_log.txt", 
                "Text Files (*.txt);;All Files (*)"
            )
            
            if file_path:
                # 匯出當前顯示的日誌內容
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(self.terminal_log_text.toPlainText())
                QMessageBox.information(self, "成功", f"終端日誌已匯出到 {file_path}")
        except Exception as e:
            logger.error(f"匯出終端日誌失敗: {e}")
            QMessageBox.critical(self, "錯誤", f"無法匯出終端日誌: {str(e)}")
    
    def on_add_system_info_clicked(self):
        """添加系統資訊按鈕點擊事件"""
        self.add_system_info_to_log()
        self.statusBar.showMessage("系統資訊已添加到日誌檔案")
    
    def closeEvent(self, event):
        """窗口关闭事件处理"""
        # 停止系統監控定時器
        self.stop_system_monitoring()
        
        # 停止日誌檔案監控定時器
        if hasattr(self, 'log_update_timer'):
            self.log_update_timer.stop()
        
        # 确保在线监控正确停止
        if online_manager.is_running:
            online_manager.stop()
        
        # 接受关闭事件
        event.accept() 