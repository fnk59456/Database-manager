#!/usr/bin/env python3
"""
測試修復後的全局延遲移動管理器功能
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def test_global_delayed_move_manager_fixed():
    """測試修復後的全局延遲移動管理器功能"""
    print("開始測試修復後的全局延遲移動管理器...")
    
    try:
        # 測試導入
        from app.controllers.data_processor import (
            DelayedMoveManager,
            get_global_delayed_move_manager,
            set_global_delayed_move_manager
        )
        print("✓ 導入成功")
        
        # 測試初始狀態
        initial_manager = get_global_delayed_move_manager()
        if initial_manager is None:
            print("✓ 初始狀態為 None（正常）")
        else:
            print("⚠ 初始狀態不為 None")
        
        # 創建新的管理器實例
        new_manager = DelayedMoveManager()
        print("✓ 創建新的 DelayedMoveManager 實例成功")
        
        # 設置為全局實例
        set_global_delayed_move_manager(new_manager)
        print("✓ 設置全局實例成功")
        
        # 驗證全局實例
        retrieved_manager = get_global_delayed_move_manager()
        if retrieved_manager is new_manager:
            print("✓ 全局實例設置和獲取成功")
        else:
            print("✗ 全局實例設置失敗")
            return False
        
        # 測試延遲移動隊列功能
        test_component_id = "TEST_COMPONENT_001"
        test_lot_id = "TEST_LOT_001"
        test_station = "MT"
        test_source_product = "TestProduct"
        test_target_product = "TargetProduct"
        
        # 添加到延遲移動隊列
        new_manager.add_to_delayed_queue(
            test_component_id, test_lot_id, test_station,
            test_source_product, test_target_product
        )
        print("✓ 添加到延遲移動隊列成功")
        
        # 檢查隊列狀態
        queue_size = new_manager.move_queue.qsize()
        print(f"✓ 延遲移動隊列大小: {queue_size}")
        
        # 測試從隊列中獲取任務
        try:
            task = new_manager.move_queue.get_nowait()
            print(f"✓ 從隊列獲取任務成功: {task}")
        except Exception as e:
            print(f"✗ 從隊列獲取任務失敗: {e}")
            return False
        
        print("\n🎉 所有測試通過！全局延遲移動管理器功能正常")
        return True
        
    except ImportError as e:
        print(f"✗ 導入失敗: {e}")
        return False
    except Exception as e:
        print(f"✗ 測試過程中發生錯誤: {e}")
        return False

if __name__ == "__main__":
    success = test_global_delayed_move_manager_fixed()
    sys.exit(0 if success else 1)
