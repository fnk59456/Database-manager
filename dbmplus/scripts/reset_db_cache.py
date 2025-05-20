#!/usr/bin/env python
"""
重置資料庫快取腳本

用於清除資料庫快取，並重新掃描資料庫結構
"""
import os
import sys
import shutil
from pathlib import Path

# 添加父目錄到sys.path，以便能夠導入應用程序模塊
sys.path.append(str(Path(__file__).parent.parent.parent))

from dbmplus.app.utils.logger import get_logger
from dbmplus.app.models.database_manager import db_manager

logger = get_logger("reset_db_cache")

def reset_database_cache():
    """
    重置資料庫快取，並重新掃描資料庫
    """
    # 獲取快取文件路徑
    cache_file = db_manager.cache_file
    
    logger.info(f"準備重置快取文件: {cache_file}")
    
    # 備份快取文件（如果存在）
    if cache_file.exists():
        backup_path = cache_file.parent / f"{cache_file.stem}_backup{cache_file.suffix}"
        try:
            shutil.copy2(cache_file, backup_path)
            logger.info(f"已備份原始快取文件到: {backup_path}")
        except Exception as e:
            logger.warning(f"備份快取文件失敗: {e}")
        
        # 刪除原始快取文件
        try:
            cache_file.unlink()
            logger.info(f"已刪除快取文件: {cache_file}")
        except Exception as e:
            logger.error(f"刪除快取文件失敗: {e}")
            return False
    
    # 清空數據庫管理器的內存快取
    db_manager.data_cache = {
        "products": {},
        "lots": {},
        "components": {},
        "lot_keys": {}
    }
    
    # 重新掃描資料庫
    logger.info("開始重新掃描資料庫...")
    db_manager.scan_database()
    
    # 輸出掃描結果
    product_count = len(db_manager.data_cache["products"])
    lot_count = len(db_manager.data_cache["lots"])
    component_count = len(db_manager.data_cache["components"])
    
    logger.info(f"資料庫掃描完成，已載入: {product_count} 產品, {lot_count} 批次, {component_count} 元件")
    return True

if __name__ == "__main__":
    print("開始重置資料庫快取...")
    if reset_database_cache():
        print("資料庫快取已成功重置並重新掃描！")
    else:
        print("重置資料庫快取失敗，請檢查日誌獲取詳細信息。") 