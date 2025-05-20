#!/usr/bin/env python
"""
創建processed_csv目錄結構腳本

用於在base_path下，為每個產品創建與csv目錄結構相同的processed_csv目錄結構
"""
import os
import sys
import shutil
from pathlib import Path

# 添加父目錄到sys.path，以便能夠導入應用程序模塊
sys.path.append(str(Path(__file__).parent.parent.parent))

from dbmplus.app.utils.logger import get_logger
from dbmplus.app.utils.config_manager import config
from dbmplus.app.utils.file_utils import ensure_directory

logger = get_logger("create_processed_csv_dirs")

def create_processed_csv_structure():
    """
    創建與csv相同的processed_csv目錄結構
    """
    base_path = Path(config.get("database.base_path", "D:/Database-PC"))
    if not base_path.exists():
        logger.error(f"基礎路徑不存在: {base_path}")
        return False
    
    logger.info(f"開始在基礎路徑 {base_path} 下創建processed_csv目錄結構")
    
    # 統計信息
    products_scanned = 0
    lots_scanned = 0
    stations_scanned = 0
    directories_created = 0
    
    # 掃描所有產品目錄
    for product_dir in os.listdir(base_path):
        product_path = base_path / product_dir
        if not product_path.is_dir():
            continue
        
        products_scanned += 1
        csv_dir = product_path / "csv"
        if not csv_dir.exists() or not csv_dir.is_dir():
            logger.warning(f"產品 {product_dir} 沒有csv目錄")
            continue
        
        # 創建processed_csv基礎目錄
        processed_csv_dir = product_path / "processed_csv"
        ensure_directory(processed_csv_dir)
        directories_created += 1
        
        # 掃描所有批次目錄
        for lot_dir in os.listdir(csv_dir):
            lot_path = csv_dir / lot_dir
            if not lot_path.is_dir():
                continue
            
            lots_scanned += 1
            processed_lot_dir = processed_csv_dir / lot_dir
            ensure_directory(processed_lot_dir)
            directories_created += 1
            
            # 掃描所有站點目錄
            for station_dir in os.listdir(lot_path):
                station_path = lot_path / station_dir
                if not station_path.is_dir():
                    continue
                
                stations_scanned += 1
                processed_station_dir = processed_lot_dir / station_dir
                ensure_directory(processed_station_dir)
                directories_created += 1
    
    logger.info(f"目錄結構創建完成。掃描: {products_scanned}個產品, {lots_scanned}個批次, {stations_scanned}個站點")
    logger.info(f"總共創建了{directories_created}個目錄")
    return True

if __name__ == "__main__":
    if create_processed_csv_structure():
        print("processed_csv目錄結構創建成功!")
    else:
        print("processed_csv目錄結構創建失敗，請檢查日誌獲取詳細信息。") 