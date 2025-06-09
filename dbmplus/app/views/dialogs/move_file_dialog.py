"""
移動檔案對話框模塊
"""
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
    QComboBox, QCheckBox, QPushButton, QGroupBox,
    QMessageBox, QFrame, QTableWidget, QTableWidgetItem,
    QHeaderView
)
from PySide6.QtCore import Qt, Signal
from ...models import db_manager
from ...utils import get_logger

logger = get_logger("move_file_dialog")


class MoveFileDialog(QDialog):
    """移動檔案對話框"""
    
    # 定義信號
    move_requested = Signal(str, str, str, str, str, list)  # component_id, lot_id, station, source_product, target_product, file_types
    
    def __init__(self, component_id: str, lot_id: str, station: str, source_product: str, parent=None):
        super().__init__(parent)
        self.component_id = component_id
        self.lot_id = lot_id
        self.station = station
        self.source_product = source_product
        
        self.setWindowTitle("移動檔案")
        self.setModal(True)
        self.resize(400, 300)
        
        self.setup_ui()
        self.load_products()
        
    def setup_ui(self):
        """設置UI"""
        layout = QVBoxLayout(self)
        
        # 基本信息顯示
        info_group = QGroupBox("移動信息")
        info_layout = QVBoxLayout(info_group)
        
        info_layout.addWidget(QLabel(f"組件ID: {self.component_id}"))
        info_layout.addWidget(QLabel(f"批次ID: {self.lot_id}"))
        info_layout.addWidget(QLabel(f"站點: {self.station}"))
        info_layout.addWidget(QLabel(f"源產品: {self.source_product}"))
        
        # 添加分隔線
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setFrameShadow(QFrame.Sunken)
        info_layout.addWidget(line)
        
        layout.addWidget(info_group)
        
        # 目標產品選擇
        target_group = QGroupBox("目標產品")
        target_layout = QVBoxLayout(target_group)
        
        target_layout.addWidget(QLabel("選擇目標產品:"))
        self.target_product_combo = QComboBox()
        target_layout.addWidget(self.target_product_combo)
        
        layout.addWidget(target_group)
        
        # 檔案類型選擇
        file_type_group = QGroupBox("要移動的檔案類型")
        file_type_layout = QVBoxLayout(file_type_group)
        
        self.csv_checkbox = QCheckBox("CSV 檔案")
        self.csv_checkbox.setChecked(True)
        file_type_layout.addWidget(self.csv_checkbox)
        
        self.map_checkbox = QCheckBox("Map 圖像檔案 (Basemap, Lossmap, FPY)")
        self.map_checkbox.setChecked(True)
        file_type_layout.addWidget(self.map_checkbox)
        
        self.org_checkbox = QCheckBox("Org 資料夾")
        self.org_checkbox.setChecked(True)
        file_type_layout.addWidget(self.org_checkbox)
        
        self.roi_checkbox = QCheckBox("ROI 資料夾")
        self.roi_checkbox.setChecked(True)
        file_type_layout.addWidget(self.roi_checkbox)
        
        layout.addWidget(file_type_group)
        
        # 按鈕
        button_layout = QHBoxLayout()
        
        self.select_all_btn = QPushButton("全選")
        self.select_all_btn.clicked.connect(self.select_all)
        button_layout.addWidget(self.select_all_btn)
        
        self.deselect_all_btn = QPushButton("全不選")
        self.deselect_all_btn.clicked.connect(self.deselect_all)
        button_layout.addWidget(self.deselect_all_btn)
        
        button_layout.addStretch()
        
        self.cancel_btn = QPushButton("取消")
        self.cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(self.cancel_btn)
        
        self.move_btn = QPushButton("開始移動")
        self.move_btn.clicked.connect(self.start_move)
        button_layout.addWidget(self.move_btn)
        
        layout.addLayout(button_layout)
        
    def load_products(self):
        """載入可用的產品列表"""
        try:
            products = db_manager.get_products()
            
            for product in products:
                # 排除當前源產品
                if product.product_id != self.source_product:
                    self.target_product_combo.addItem(product.product_id)
                    
            if self.target_product_combo.count() == 0:
                self.target_product_combo.addItem("沒有可用的目標產品")
                self.move_btn.setEnabled(False)
                
        except Exception as e:
            logger.error(f"載入產品列表失敗: {e}")
            QMessageBox.warning(self, "錯誤", f"載入產品列表失敗: {str(e)}")
            self.move_btn.setEnabled(False)
    
    def select_all(self):
        """全選檔案類型"""
        self.csv_checkbox.setChecked(True)
        self.map_checkbox.setChecked(True)
        self.org_checkbox.setChecked(True)
        self.roi_checkbox.setChecked(True)
    
    def deselect_all(self):
        """全不選檔案類型"""
        self.csv_checkbox.setChecked(False)
        self.map_checkbox.setChecked(False)
        self.org_checkbox.setChecked(False)
        self.roi_checkbox.setChecked(False)
    
    def get_selected_file_types(self):
        """獲取選中的檔案類型"""
        file_types = []
        
        if self.csv_checkbox.isChecked():
            file_types.append("csv")
        if self.map_checkbox.isChecked():
            file_types.append("map")
        if self.org_checkbox.isChecked():
            file_types.append("org")
        if self.roi_checkbox.isChecked():
            file_types.append("roi")
            
        return file_types
    
    def start_move(self):
        """開始移動檔案"""
        # 檢查是否選擇了目標產品
        target_product = self.target_product_combo.currentText()
        if not target_product or target_product == "沒有可用的目標產品":
            QMessageBox.warning(self, "錯誤", "請選擇有效的目標產品")
            return
        
        # 檢查是否選擇了檔案類型
        file_types = self.get_selected_file_types()
        if not file_types:
            QMessageBox.warning(self, "錯誤", "請至少選擇一種檔案類型")
            return
        
        # 確認對話框
        file_types_str = ", ".join(file_types)
        msg = f"確定要將組件 {self.component_id} 的以下檔案從 {self.source_product} 移動到 {target_product} 嗎？\n\n"
        msg += f"檔案類型: {file_types_str}\n\n"
        msg += "注意：此操作不可撤銷！"
        
        reply = QMessageBox.question(
            self, "確認移動", msg,
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            # 發射移動請求信號
            self.move_requested.emit(
                self.component_id,
                self.lot_id,
                self.station,
                self.source_product,
                target_product,
                file_types
            )
            self.accept()


class BatchMoveFileDialog(QDialog):
    """批量移動檔案對話框"""
    
    # 定義信號 - components_data: list of tuples (component_id, lot_id, station, source_product)
    batch_move_requested = Signal(list, str, list)  # components_data, target_product, file_types
    
    def __init__(self, components_data: list, parent=None):
        super().__init__(parent)
        self.components_data = components_data  # [(component_id, lot_id, station, source_product), ...]
        
        self.setWindowTitle("批量移動檔案")
        self.setModal(True)
        self.resize(600, 500)
        
        self.setup_ui()
        self.load_products()
        self.populate_components_table()
        
    def setup_ui(self):
        """設置UI"""
        layout = QVBoxLayout(self)
        
        # 信息顯示
        info_group = QGroupBox(f"批量移動信息 (共 {len(self.components_data)} 個組件)")
        info_layout = QVBoxLayout(info_group)
        
        # 組件列表表格
        self.components_table = QTableWidget(0, 4)
        self.components_table.setHorizontalHeaderLabels(['組件ID', '批次ID', '站點', '源產品'])
        self.components_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.components_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.components_table.verticalHeader().setVisible(False)
        self.components_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.components_table.setMaximumHeight(200)
        
        info_layout.addWidget(self.components_table)
        layout.addWidget(info_group)
        
        # 目標產品選擇
        target_group = QGroupBox("目標產品")
        target_layout = QVBoxLayout(target_group)
        
        target_layout.addWidget(QLabel("選擇目標產品:"))
        self.target_product_combo = QComboBox()
        target_layout.addWidget(self.target_product_combo)
        
        layout.addWidget(target_group)
        
        # 檔案類型選擇
        file_type_group = QGroupBox("要移動的檔案類型")
        file_type_layout = QVBoxLayout(file_type_group)
        
        self.csv_checkbox = QCheckBox("CSV 檔案")
        self.csv_checkbox.setChecked(True)
        file_type_layout.addWidget(self.csv_checkbox)
        
        self.map_checkbox = QCheckBox("Map 圖像檔案 (Basemap, Lossmap, FPY)")
        self.map_checkbox.setChecked(True)
        file_type_layout.addWidget(self.map_checkbox)
        
        self.org_checkbox = QCheckBox("Org 資料夾")
        self.org_checkbox.setChecked(True)
        file_type_layout.addWidget(self.org_checkbox)
        
        self.roi_checkbox = QCheckBox("ROI 資料夾")
        self.roi_checkbox.setChecked(True)
        file_type_layout.addWidget(self.roi_checkbox)
        
        layout.addWidget(file_type_group)
        
        # 按鈕
        button_layout = QHBoxLayout()
        
        self.select_all_btn = QPushButton("全選")
        self.select_all_btn.clicked.connect(self.select_all)
        button_layout.addWidget(self.select_all_btn)
        
        self.deselect_all_btn = QPushButton("全不選")
        self.deselect_all_btn.clicked.connect(self.deselect_all)
        button_layout.addWidget(self.deselect_all_btn)
        
        button_layout.addStretch()
        
        self.cancel_btn = QPushButton("取消")
        self.cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(self.cancel_btn)
        
        self.move_btn = QPushButton("開始批量移動")
        self.move_btn.clicked.connect(self.start_batch_move)
        button_layout.addWidget(self.move_btn)
        
        layout.addLayout(button_layout)
    
    def populate_components_table(self):
        """填充組件列表表格"""
        self.components_table.setRowCount(len(self.components_data))
        
        for row, (component_id, lot_id, station, source_product) in enumerate(self.components_data):
            self.components_table.setItem(row, 0, QTableWidgetItem(component_id))
            self.components_table.setItem(row, 1, QTableWidgetItem(lot_id))
            self.components_table.setItem(row, 2, QTableWidgetItem(station))
            self.components_table.setItem(row, 3, QTableWidgetItem(source_product))
    
    def load_products(self):
        """載入可用的產品列表"""
        try:
            products = db_manager.get_products()
            
            # 獲取所有源產品
            source_products = set(comp[3] for comp in self.components_data)
            
            for product in products:
                # 排除所有源產品
                if product.product_id not in source_products:
                    self.target_product_combo.addItem(product.product_id)
                    
            if self.target_product_combo.count() == 0:
                self.target_product_combo.addItem("沒有可用的目標產品")
                self.move_btn.setEnabled(False)
                
        except Exception as e:
            logger.error(f"載入產品列表失敗: {e}")
            QMessageBox.warning(self, "錯誤", f"載入產品列表失敗: {str(e)}")
            self.move_btn.setEnabled(False)
    
    def select_all(self):
        """全選檔案類型"""
        self.csv_checkbox.setChecked(True)
        self.map_checkbox.setChecked(True)
        self.org_checkbox.setChecked(True)
        self.roi_checkbox.setChecked(True)
    
    def deselect_all(self):
        """全不選檔案類型"""
        self.csv_checkbox.setChecked(False)
        self.map_checkbox.setChecked(False)
        self.org_checkbox.setChecked(False)
        self.roi_checkbox.setChecked(False)
    
    def get_selected_file_types(self):
        """獲取選中的檔案類型"""
        file_types = []
        
        if self.csv_checkbox.isChecked():
            file_types.append("csv")
        if self.map_checkbox.isChecked():
            file_types.append("map")
        if self.org_checkbox.isChecked():
            file_types.append("org")
        if self.roi_checkbox.isChecked():
            file_types.append("roi")
            
        return file_types
    
    def start_batch_move(self):
        """開始批量移動檔案"""
        # 檢查是否選擇了目標產品
        target_product = self.target_product_combo.currentText()
        if not target_product or target_product == "沒有可用的目標產品":
            QMessageBox.warning(self, "錯誤", "請選擇有效的目標產品")
            return
        
        # 檢查是否選擇了檔案類型
        file_types = self.get_selected_file_types()
        if not file_types:
            QMessageBox.warning(self, "錯誤", "請至少選擇一種檔案類型")
            return
        
        # 確認對話框
        file_types_str = ", ".join(file_types)
        source_products = set(comp[3] for comp in self.components_data)
        source_products_str = ", ".join(source_products)
        
        msg = f"確定要將以下 {len(self.components_data)} 個組件的檔案移動到 {target_product} 嗎？\n\n"
        msg += f"源產品: {source_products_str}\n"
        msg += f"檔案類型: {file_types_str}\n\n"
        msg += "注意：此操作不可撤銷！"
        
        reply = QMessageBox.question(
            self, "確認批量移動", msg,
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            # 發射批量移動請求信號
            self.batch_move_requested.emit(
                self.components_data,
                target_product,
                file_types
            )
            self.accept() 