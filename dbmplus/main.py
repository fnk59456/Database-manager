"""
Database Manager Plus 主程序
"""
import sys
import os
from pathlib import Path

# 設置 matplotlib 後端，避免線程問題
import matplotlib
matplotlib.use('Agg')  # 使用非互動式後端

from app.utils.logger import get_logger, setup_logging
from app.utils.config_manager import load_config
from app.models.database_manager import db_manager
from app.controllers.data_processor import DataProcessor
from app.views.main_window import MainWindow

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt
import qdarkstyle


# 設置工作目錄為腳本所在目錄
script_dir = Path(__file__).parent
os.chdir(script_dir)

# 初始化日誌
setup_logging()
logger = get_logger("main")

# 初始化數據處理器
data_processor = DataProcessor()

def validate_configs():
    """驗證應用配置"""
    # 驗證站點順序配置
    station_order_valid, station_order_info = db_manager.validate_station_order()
    if not station_order_valid:
        logger.warning(f"站點順序配置驗證失敗: {station_order_info}")
        
    # 驗證翻轉配置
    from app.utils.config_manager import config
    station_order = config.get("processing.station_order", [])
    flip_config = config.get("processing.flip_config", {})
    
    # 檢查是否所有站點都有翻轉配置
    missing_flip_config = [s for s in station_order if s not in flip_config]
    if missing_flip_config:
        logger.warning(f"以下站點缺少翻轉配置: {missing_flip_config}")
    
    # 檢查站點邏輯配置
    station_logic = config.get("processing.station_logic", {})
    missing_logic_config = [s for s in station_order if s not in station_logic]
    if missing_logic_config:
        logger.warning(f"以下站點缺少邏輯配置: {missing_logic_config}")
        
    # 驗證FPY相關配置
    fpy_config_result = data_processor.validate_fpy_config()
    if not fpy_config_result["status"]:
        logger.warning("FPY配置驗證發現問題，可能影響程序正常運行")

def main():
    """應用程序入口點"""
    # 載入配置文件
    load_config()
    
    # 驗證配置
    validate_configs()
    
    # 建立 Qt 應用
    app = QApplication(sys.argv)
    
    # 設置暗色主題
    app.setStyleSheet(qdarkstyle.load_stylesheet(qt_api='pyside6'))
    logger.info("已載入深色主題樣式")
    
    # 建立主視窗
    window = MainWindow()
    window.show()
    
    # 啟動應用程序事件循環
    logger.info(f"啟動 Database Manager Plus v1.0.0")
    sys.exit(app.exec())


if __name__ == "__main__":
    main() 