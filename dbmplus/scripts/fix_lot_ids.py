#!/usr/bin/env python
"""
修復批次ID腳本

用於修復數據庫快取中的批次ID，確保所有批次都有原始批次ID
"""
import os
import sys
from pathlib import Path

# 添加父目錄到sys.path，以便能夠導入應用程序模塊
sys.path.append(str(Path(__file__).parent.parent.parent))

from dbmplus.app.utils.logger import get_logger
from dbmplus.app.models.database_manager import db_manager

logger = get_logger("fix_lot_ids")

def fix_lot_ids():
    """
    修復現有批次ID，確保所有批次都有原始批次ID
    
    Returns:
        bool: 是否成功修復
    """
    logger.info("開始修復批次ID...")
    
    # 首先檢查是否已加載快取
    if not db_manager.data_cache["lots"]:
        logger.info("快取為空，嘗試加載...")
        db_manager._load_cache()
    
    # 檢查所有批次，確保有original_lot_id
    fixed_count = 0
    for lot_id, lot in db_manager.data_cache["lots"].items():
        # 檢查是否有original_lot_id
        if not hasattr(lot, "original_lot_id") or lot.original_lot_id is None:
            # 設置original_lot_id
            original_id = lot_id
            
            # 如果lot_id格式是product_id_original_id，提取原始ID
            if "_" in lot_id:
                parts = lot_id.split("_")
                if len(parts) >= 2 and parts[0] == lot.product_id:
                    original_id = "_".join(parts[1:])
            
            # 設置原始批次ID
            lot.original_lot_id = original_id
            fixed_count += 1
            logger.info(f"修復批次ID: {lot_id} -> 原始ID: {original_id}")
    
    # 重建批次映射關係
    db_manager.data_cache["lot_keys"] = {}
    for lot_id, lot in db_manager.data_cache["lots"].items():
        lot_key = f"{lot.product_id}_{lot.original_lot_id}"
        db_manager.data_cache["lot_keys"][lot_key] = lot_id
    
    # 保存修複後的快取
    db_manager._save_cache()
    
    logger.info(f"批次ID修復完成，修復了 {fixed_count} 個批次")
    return True

if __name__ == "__main__":
    print("開始修復批次ID...")
    if fix_lot_ids():
        print("批次ID修復成功!")
    else:
        print("批次ID修復失敗，請檢查日誌獲取詳細信息。") 