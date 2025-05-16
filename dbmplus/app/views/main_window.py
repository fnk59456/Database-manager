"""
主視窗模塊，提供應用程式的主界面
"""
import os
import sys
from pathlib import Path
from typing import Optional, Dict, List, Any

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
    QTabWidget, QTableWidget, QTableWidgetItem, QPushButton,
    QLabel, QProgressBar, QMessageBox, QFileDialog, QComboBox,
    QSizePolicy, QHeaderView, QStatusBar, QToolBar, QToolButton,
    QMenu, QDialog, QApplication
)
from PySide6.QtCore import Qt, QSize, Signal, Slot, QThread, QTimer
from PySide6.QtGui import QIcon, QAction, QPixmap, QFont, QColor

from ..utils import get_logger, config
from ..models import db_manager, ComponentInfo
from ..controllers import data_processor

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
        self.component_table.setAlternatingRowColors(True)
        
        # 設置欄寬
        col_widths = config.get("ui.table_column_widths", {})
        for col, name in enumerate(['product', 'lot', 'station', 'lotid', 'org', 'csv', 'basemap', 'lossmap', 'fpy']):
            if name in col_widths:
                self.component_table.setColumnWidth(col, col_widths[name])
        
        component_layout.addWidget(self.component_table)
        
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
        
        self.refresh_btn = QPushButton("重新掃描資料")
        self.refresh_btn.setStyleSheet("background-color: lightblue; color: black;")
        self.refresh_btn.setFixedHeight(40)
        self.refresh_btn.clicked.connect(self.on_refresh_clicked)
        batch_layout.addWidget(self.refresh_btn)
        
        component_layout.addWidget(batch_panel)
        
        # 添加選項卡
        self.detail_tabs.addTab(self.component_tab, "元件列表")
        
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
        
        # 儲存當前選中的產品/批次/站點
        self.selected_product = None
        self.selected_lot = None
        self.selected_station = None
    
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
                # 產品和批次數據
                row_data = [product.product_id, lot.lot_id]
                
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
        
        # 更新統計資訊
        stats = db_manager.get_component_count()
        self.stats_label.setText(f"總計: {stats['total']} 個元件")
        
        self.statusBar.showMessage("資料載入完成", 3000)
    
    def on_product_table_cell_clicked(self, row, col):
        """產品資料表點擊事件處理"""
        # 獲取選中的產品和批次
        self.selected_product = self.product_table.item(row, 0).text()
        self.selected_lot = self.product_table.item(row, 1).text()
        
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
                self.component_table.setItem(row, 1, self._create_table_item(self.selected_lot))
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
    
    def on_process_basemap_clicked(self):
        """生成 Basemap 按鈕點擊事件"""
        if not self.selected_product or not self.selected_lot or not self.selected_station:
            QMessageBox.warning(self, "警告", "請先選擇產品、批次和站點")
            return
        
        # 創建任務對話框
        dialog = TaskProgressDialog(
            "生成 Basemap", 
            f"正在為 {self.selected_product}/{self.selected_lot}/{self.selected_station} 生成 Basemap...\n"
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
            f"正在為 {self.selected_product}/{self.selected_lot}/{self.selected_station} 生成 Lossmap...",
            self
        )
        
        # 創建任務並獲取ID
        task_id = data_processor.create_task(
            "lossmap", 
            self.selected_product, 
            self.selected_lot, 
            self.selected_station,
            # 不再傳遞回調函數
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
            f"正在為 {self.selected_product}/{self.selected_lot}/{self.selected_station} 生成 FPY" +
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
        # 重新載入元件表格
        self.update_component_table() 