import os
import sys
from PySide6.QtWidgets import QApplication, QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem, QPushButton, QSizePolicy
from PySide6.QtCore import Qt
import check  # 引入 check.py，包含處理任務的邏輯

class DatabaseManagerGUI(QWidget):
    def __init__(self):
        super().__init__()
        self.initUI()
        self.selected_product = None
        self.selected_number = None
        self.selected_type = None

    def initUI(self):
        # 主布局
        main_layout = QVBoxLayout()

        # 定義表格標題
        headers = ['Product', 'LOT', 'MT', 'DC2', 'INNER1', 'RDL', 'INNER2', 'CU', 'EMC']

        # 創建主表格
        self.table_widget = QTableWidget(0, len(headers), self)
        self.table_widget.setHorizontalHeaderLabels(headers)

        # 填充表格
        base_dir = r'D:\Database-PC'
        self.populate_table(self.table_widget, base_dir)

        self.table_widget.setMaximumHeight(335)
        self.table_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        self.table_widget.cellClicked.connect(self.table_item_clicked)
        main_layout.addWidget(self.table_widget, stretch=3)

        # 訊息表格，顯示 LOTID、Org、Csv、Basemap 等資訊
        self.info_table = QTableWidget(0, 10)  # 10 列用於顯示訊息，行數根據 LOTID 動態設置
        self.info_table.setHorizontalHeaderLabels(['Product', 'LOT', 'Station', 'LOTID', 'Org', 'Csv', 'Basemap', 'Losemap', 'Bar', 'FPY'])
        self.info_table.verticalHeader().setVisible(False)  # 隱藏行號

        # 設置每一欄的寬度
        self.info_table.setColumnWidth(0, 100)  # Product
        self.info_table.setColumnWidth(1, 100)  # LOT
        self.info_table.setColumnWidth(2, 100)  # Station
        self.info_table.setColumnWidth(3, 135)  # LOTID
        self.info_table.setColumnWidth(4, 80)   # Org
        self.info_table.setColumnWidth(5, 80)   # Csv
        self.info_table.setColumnWidth(6, 80)   # Basemap
        self.info_table.setColumnWidth(7, 80)   # Losemap
        self.info_table.setColumnWidth(8, 80)   # Bar
        self.info_table.setColumnWidth(9, 80)   # FPY
        main_layout.addWidget(self.info_table)

        # 下方的按鈕區域
        bottom_layout = QHBoxLayout()

        # 在按鈕之間添加伸縮空間，讓按鈕平均分布
        bottom_layout.addStretch(1)  # 添加一個伸縮空間

        single_ym_button = QPushButton('Single Y&M', self)
        single_ym_button.setStyleSheet("background-color: tan; color: black;")
        single_ym_button.setFixedSize(120, 40)
        single_ym_button.clicked.connect(self.run_single_ym)
        bottom_layout.addWidget(single_ym_button)

        bottom_layout.addStretch(1)  # 添加一個伸縮空間

        button2 = QPushButton('Schedule Y&M', self)
        button2.setStyleSheet("background-color: tan; color: black;")
        button2.setFixedSize(120, 40)
        bottom_layout.addWidget(button2)

        bottom_layout.addStretch(1)  # 添加一個伸縮空間

        button3 = QPushButton('Trigger Y&M', self)
        button3.setStyleSheet("background-color: tan; color: black;")
        button3.setFixedSize(120, 40)
        bottom_layout.addWidget(button3)

        bottom_layout.addStretch(1)  # 添加一個伸縮空間

        button4 = QPushButton('Log output', self)
        button4.setStyleSheet("background-color: tan; color: black;")
        button4.setFixedSize(120, 40)
        bottom_layout.addWidget(button4)

        bottom_layout.addStretch(1)  # 添加一個伸縮空間

        button5 = QPushButton('Rawdata output', self)
        button5.setStyleSheet("background-color: tan; color: black;")
        button5.setFixedSize(120, 40)
        bottom_layout.addWidget(button5)

        bottom_layout.addStretch(1)  # 添加一個伸縮空間

        main_layout.addLayout(bottom_layout)

        # 設置主布局
        main_layout.addLayout(bottom_layout)
        self.setLayout(main_layout)
        self.setWindowTitle("Database Manager")
        self.setFixedWidth(950)
        self.setMinimumHeight(800)

    def populate_table(self, table_widget, base_dir):
        folder_names = ['MT', 'DC2', 'INNER1', 'RDL', 'INNER2', 'CU', 'EMC']

        # 遍歷 base_dir 資料夾
        for product_folder in os.listdir(base_dir):
            product_path = os.path.join(base_dir, product_folder)
            csv_path = os.path.join(product_path, 'csv')
            if os.path.isdir(csv_path):
                for lot_folder in os.listdir(csv_path):
                    lot_path = os.path.join(csv_path, lot_folder)
                    if os.path.isdir(lot_path):
                        row_data = [product_folder, lot_folder]
                        for folder in folder_names:
                            folder_path = os.path.join(lot_path, folder)
                            if os.path.exists(folder_path):
                                csv_count = len([f for f in os.listdir(folder_path) if f.startswith(f"{lot_folder}") and f.endswith('.csv')])
                                row_data.append(f"{csv_count} PCS")
                            else:
                                row_data.append("0 PCS")
                        row_position = table_widget.rowCount()
                        table_widget.insertRow(row_position)
                        for col, data in enumerate(row_data):
                            item = QTableWidgetItem(data)
                            item.setTextAlignment(Qt.AlignCenter)
                            item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                            table_widget.setItem(row_position, col, item)

    def table_item_clicked(self, row, col):
        # 記錄選中的 product, number 和 type
        self.selected_product = self.table_widget.item(row, 0).text()
        self.selected_number = self.table_widget.item(row, 1).text()
        self.selected_type = self.table_widget.horizontalHeaderItem(col).text()

        # 清空 info_table 並顯示對應 LOTID 的資料
        self.info_table.setRowCount(0)
        self.populate_info_table(self.selected_product, self.selected_number, self.selected_type)

    def populate_info_table(self, product_folder, lot_folder, folder_name):
        # 獲取符合 rule_csv 的檔案
        csv_files = [f for f in os.listdir(os.path.join(f"D:/Database-PC/{product_folder}/csv/{lot_folder}/{folder_name}")) if f.startswith(lot_folder) and f.endswith('.csv')]
        self.info_table.setRowCount(len(csv_files))  # 根據 LOTID 的數量創建對應的行

        for idx, lotid in enumerate(csv_files):
            lotid = os.path.splitext(lotid)[0]  # 去除文件的 .csv 副檔名

            # 設置每一行的值
            self.set_info_table_row(idx, product_folder, lot_folder, folder_name, lotid)

    def set_info_table_row(self, idx, product_folder, lot_folder, folder_name, lotid):
        # 設定表格內容並置中
        self.info_table.setItem(idx, 0, self.create_centered_item(product_folder))
        self.info_table.setItem(idx, 1, self.create_centered_item(lot_folder))
        self.info_table.setItem(idx, 2, self.create_centered_item(folder_name))
        self.info_table.setItem(idx, 3, self.create_centered_item(lotid))

        # Org 判斷
        org_folder = f"D:/Database-PC/{product_folder}/org/{lot_folder}/{folder_name}/{lotid}"
        tif_files = len([f for f in os.listdir(org_folder) if f.endswith('.tif')]) if os.path.exists(org_folder) else 0
        org_status = "OK" if tif_files >= 7 else f"{tif_files} TIF files"
        self.info_table.setItem(idx, 4, self.create_centered_item(org_status))

        # Csv 判斷
        csv_path = f"D:/Database-PC/{product_folder}/csv/{lot_folder}/{folder_name}/{lotid}.csv"
        csv_status = "OK" if os.path.exists(csv_path) else "NONE"
        self.info_table.setItem(idx, 5, self.create_centered_item(csv_status))

        # Basemap 判斷
        basemap_path = f"D:/Database-PC/{product_folder}/map/{lot_folder}/{folder_name}/{lotid}.png"
        basemap_status = "OK" if os.path.exists(basemap_path) else "NONE"
        self.info_table.setItem(idx, 6, self.create_centered_item(basemap_status))

        # Losemap 判斷
        losemap_status = self.get_losemap_status(folder_name, lotid, product_folder, lot_folder)
        self.info_table.setItem(idx, 7, self.create_centered_item(losemap_status))

        # Bar 判斷
        bar_path = f"D:/Database-PC/{product_folder}/bar/{lot_folder}/{folder_name}/{folder_name}.png"
        bar_status = "OK" if os.path.exists(bar_path) else "NONE"
        self.info_table.setItem(idx, 8, self.create_centered_item(bar_status))

        # FPY 判斷
        fpy_path = f"D:/Database-PC/{product_folder}/map/{lot_folder}/FPY/{lotid}.png"
        fpy_status = "OK" if os.path.exists(fpy_path) else "NONE"
        self.info_table.setItem(idx, 9, self.create_centered_item(fpy_status))
        fpy_path = f"D:/Database-PC/{product_folder}/map/{lot_folder}/FPY/{lotid}.png"
        fpy_status = "OK" if os.path.exists(fpy_path) else "NONE"
        self.info_table.setItem(idx, 9, self.create_centered_item(fpy_status))

    def create_centered_item(self, text):
        # 建立一個文字置中的 QTableWidgetItem
        item = QTableWidgetItem(text)
        item.setTextAlignment(Qt.AlignCenter)
        item.setFlags(item.flags() & ~Qt.ItemIsEditable)  # 設為不可編輯
        return item

    def get_losemap_status(self, folder_name, lotid, product_folder, lot_folder):
        # 根據 folder_name 判斷 Losemap 狀態
        if folder_name == "MT":
            return "N/A"
        elif folder_name == "DC2":
            losemap_path = f"D:/Database-PC/{product_folder}/map/{lot_folder}/LOSS1/{lotid}.png"
        elif folder_name == "INNER1":
            losemap_path = f"D:/Database-PC/{product_folder}/map/{lot_folder}/LOSS2/{lotid}.png"
        elif folder_name == "RDL":
            losemap_path = f"D:/Database-PC/{product_folder}/map/{lot_folder}/LOSS3/{lotid}.png"
        elif folder_name == "INNER2":
            losemap_path = f"D:/Database-PC/{product_folder}/map/{lot_folder}/LOSS4/{lotid}.png"
        elif folder_name == "CU":
            losemap_path = f"D:/Database-PC/{product_folder}/map/{lot_folder}/LOSS5/{lotid}.png"
        elif folder_name == "EMC":
            losemap_path = f"D:/Database-PC/{product_folder}/map/{lot_folder}/LOSS6/{lotid}.png"
        return "OK" if os.path.exists(losemap_path) else "NONE"

    def run_single_ym(self):
        # 檢查是否已選擇product, number 和 type
        if not self.selected_product or not self.selected_number or not self.selected_type:
            print("請先選擇表格中的一項")
            return

        # 執行 check.py 中的 process_task 函數，傳遞已選擇的 product, number, type
        print(f"正在處理：{self.selected_product}, {self.selected_number}, {self.selected_type}")
        check.process_task(self.selected_product,self.selected_number, self.selected_type)  # 執行 check 中的邏輯

if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = DatabaseManagerGUI()
    window.show()
    sys.exit(app.exec())

