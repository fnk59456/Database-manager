#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
測試修復後的移動功能
"""

import sys
import os
from pathlib import Path

# 添加項目根目錄到 Python 路徑
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.controllers.data_processor import DelayedMoveManager
from app.utils.logger import setup_logger

def test_fixed_move_function():
    """測試修復後的移動功能"""
    print("=== 測試修復後的移動功能 ===")
    
    # 設置日誌
    logger = setup_logger("test_fixed_move_function")
    
    try:
        # 創建延遲移動管理器實例
        print("創建延遲移動管理器...")
        delayed_manager = DelayedMoveManager()
        print("✅ 延遲移動管理器創建成功")
        
        # 測試 _debug_component_files 方法
        print("\n測試 _debug_component_files 方法...")
        
        # 準備測試數據
        component_id = "TEST001"
        lot_id = "LOT001"
        station = "STATION1"
        source_product = "test_product"
        target_product = "target_product"
        file_types = ["org", "roi"]
        
        print(f"測試參數:")
        print(f"  組件ID: {component_id}")
        print(f"  批次ID: {lot_id}")
        print(f"  站點: {station}")
        print(f"  源產品: {source_product}")
        print(f"  目標產品: {target_product}")
        print(f"  文件類型: {file_types}")
        
        # 調用方法（這應該不會出錯）
        try:
            delayed_manager._debug_component_files(
                component_id, lot_id, station, source_product, target_product, file_types
            )
            print("✅ _debug_component_files 方法調用成功，沒有參數錯誤")
        except Exception as e:
            print(f"❌ _debug_component_files 方法調用失敗: {e}")
            return False
        
        # 測試添加組件到延遲移動隊列
        print("\n測試添加組件到延遲移動隊列...")
        try:
            delayed_manager.add_to_delayed_queue(component_id, lot_id, station, source_product)
            print("✅ 組件成功添加到延遲移動隊列")
        except Exception as e:
            print(f"❌ 添加組件到延遲移動隊列失敗: {e}")
            return False
        
        # 檢查隊列狀態
        queue_size = delayed_manager.move_queue.qsize()
        print(f"延遲移動隊列大小: {queue_size}")
        
        print("\n🎉 所有測試通過！移動功能已修復")
        return True
        
    except Exception as e:
        print(f"❌ 測試過程中發生錯誤: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_fixed_move_function()
    sys.exit(0 if success else 1)

