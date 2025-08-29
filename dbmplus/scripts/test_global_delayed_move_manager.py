#!/usr/bin/env python3
"""
測試全局延遲移動管理器功能
"""
import sys
import os
from pathlib import Path

# 添加項目根目錄到 Python 路徑
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

def test_global_delayed_move_manager():
    """測試全局延遲移動管理器功能"""
    print("🧪 測試全局延遲移動管理器功能")
    print("=" * 60)
    
    try:
        # 導入必要的模塊
        from app.controllers.data_processor import (
            get_global_delayed_move_manager, 
            set_global_delayed_move_manager,
            DelayedMoveManager
        )
        
        print("✅ 成功導入模塊")
        
        # 測試獲取全局實例（應該返回 None，因為還沒有設置）
        print("\n1. 測試初始狀態...")
        initial_manager = get_global_delayed_move_manager()
        if initial_manager is None:
            print("   ✅ 初始狀態正確：全局實例為 None")
        else:
            print("   ❌ 初始狀態錯誤：全局實例不應該存在")
            return False
        
        # 創建一個新的管理器實例
        print("\n2. 創建新的 DelayedMoveManager 實例...")
        new_manager = DelayedMoveManager()
        print("   ✅ 成功創建 DelayedMoveManager 實例")
        
        # 設置為全局實例
        print("\n3. 設置為全局實例...")
        set_global_delayed_move_manager(new_manager)
        print("   ✅ 成功設置全局實例")
        
        # 再次獲取全局實例
        print("\n4. 驗證全局實例...")
        retrieved_manager = get_global_delayed_move_manager()
        if retrieved_manager is new_manager:
            print("   ✅ 全局實例設置成功：返回的是同一個實例")
        else:
            print("   ❌ 全局實例設置失敗：返回的不是同一個實例")
            return False
        
        # 測試添加組件到延遲移動隊列
        print("\n5. 測試添加組件到延遲移動隊列...")
        test_component_id = "TEST_COMPONENT_001"
        test_lot_id = "TEST_LOT_001"
        test_station = "TEST_STATION"
        test_source_product = "TEST_SOURCE"
        test_target_product = "TEST_TARGET"
        
        retrieved_manager.add_to_delayed_queue(
            test_component_id, test_lot_id, test_station,
            test_source_product, test_target_product
        )
        print("   ✅ 成功添加測試組件到延遲移動隊列")
        
        # 檢查隊列大小
        queue_size = retrieved_manager.move_queue.qsize()
        print(f"   📊 延遲移動隊列大小: {queue_size}")
        
        if queue_size == 1:
            print("   ✅ 隊列大小正確")
        else:
            print(f"   ❌ 隊列大小不正確，期望 1，實際 {queue_size}")
            return False
        
        # 測試記錄組件失敗
        print("\n6. 測試記錄組件失敗...")
        test_error_message = "測試錯誤信息"
        retrieved_manager.record_component_failure(test_component_id, test_error_message)
        print("   ✅ 成功記錄組件失敗")
        
        # 檢查失敗記錄
        if test_component_id in retrieved_manager.failed_components:
            failed_info = retrieved_manager.failed_components[test_component_id]
            print(f"   📝 失敗記錄: 次數={failed_info['count']}, 錯誤={failed_info['error']}")
            if failed_info['count'] == 1 and failed_info['error'] == test_error_message:
                print("   ✅ 失敗記錄正確")
            else:
                print("   ❌ 失敗記錄不正確")
                return False
        else:
            print("   ❌ 失敗記錄未找到")
            return False
        
        # 測試獲取失敗組件摘要
        print("\n7. 測試獲取失敗組件摘要...")
        summary = retrieved_manager.get_failed_components_summary()
        print(f"   📊 失敗組件摘要: {summary}")
        
        if summary['total_failed'] == 1:
            print("   ✅ 失敗組件摘要正確")
        else:
            print("   ❌ 失敗組件摘要不正確")
            return False
        
        print("\n" + "=" * 60)
        print("🎉 所有測試通過！全局延遲移動管理器功能正常")
        return True
        
    except Exception as e:
        print(f"\n❌ 測試過程中發生錯誤: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_global_delayed_move_manager()
    sys.exit(0 if success else 1)

