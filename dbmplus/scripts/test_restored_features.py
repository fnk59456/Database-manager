#!/usr/bin/env python3
"""
測試恢復的功能：重試機制、文件檢查優化、智能路徑查找等
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def test_restored_features():
    """測試所有恢復的功能"""
    print("開始測試恢復的功能...")
    
    try:
        # 測試 1: 全局延遲移動管理器
        print("\n1. 測試全局延遲移動管理器...")
        from app.controllers.data_processor import (
            DelayedMoveManager,
            get_global_delayed_move_manager,
            set_global_delayed_move_manager
        )
        print("✓ 導入成功")
        
        # 測試 2: 創建延遲移動管理器實例
        print("\n2. 測試延遲移動管理器實例...")
        delayed_manager = DelayedMoveManager()
        print("✓ 創建實例成功")
        
        # 測試 3: 設置全局實例
        print("\n3. 測試全局實例設置...")
        set_global_delayed_move_manager(delayed_manager)
        retrieved_manager = get_global_delayed_move_manager()
        if retrieved_manager is delayed_manager:
            print("✓ 全局實例設置成功")
        else:
            print("✗ 全局實例設置失敗")
            return False
        
        # 測試 4: 重試機制相關方法
        print("\n4. 測試重試機制方法...")
        test_component_id = "TEST_COMPONENT_001"
        test_lot_id = "TEST_LOT_001"
        test_station = "MT"
        test_source_product = "TestProduct"
        test_target_product = "TargetProduct"
        
        # 測試記錄失敗
        delayed_manager.record_component_failure(
            test_component_id, test_lot_id, test_station,
            test_source_product, test_target_product, "找不到組件"
        )
        print("✓ record_component_failure 方法正常")
        
        # 測試獲取失敗摘要
        summary = delayed_manager.get_failed_components_summary()
        if summary['total_failed'] == 1:
            print("✓ get_failed_components_summary 方法正常")
        else:
            print("✗ get_failed_components_summary 方法異常")
            return False
        
        # 測試 5: 文件檢查優化方法
        print("\n5. 測試文件檢查優化方法...")
        try:
            delayed_manager._debug_component_files(
                test_component_id, test_lot_id, test_station,
                test_source_product, test_target_product, ["org", "roi"]
            )
            print("✓ _debug_component_files 方法正常（靜默版本）")
        except Exception as e:
            print(f"✗ _debug_component_files 方法異常: {e}")
            return False
        
        # 測試 6: 智能路徑查找方法
        print("\n6. 測試智能路徑查找方法...")
        try:
            result = delayed_manager._find_actual_file_path(
                test_component_id, test_lot_id, test_station,
                test_source_product, "org"
            )
            print("✓ _find_actual_file_path 方法正常")
        except Exception as e:
            print(f"✗ _find_actual_file_path 方法異常: {e}")
            return False
        
        # 測試 7: 重試管理器
        print("\n7. 測試重試管理器...")
        from app.controllers.retry_manager import retry_manager
        
        # 測試添加重試任務
        success = retry_manager.add_retry_task(
            test_component_id, test_lot_id, test_station,
            test_source_product, test_target_product, ["org", "roi"],
            "找不到組件"
        )
        if success:
            print("✓ 重試管理器添加任務成功")
        else:
            print("✗ 重試管理器添加任務失敗")
            return False
        
        # 測試獲取重試統計
        stats = retry_manager.get_retry_statistics()
        if stats['total_tasks'] > 0:
            print("✓ 重試管理器統計功能正常")
        else:
            print("✗ 重試管理器統計功能異常")
            return False
        
        print("\n🎉 所有恢復的功能測試通過！")
        return True
        
    except ImportError as e:
        print(f"✗ 導入失敗: {e}")
        return False
    except Exception as e:
        print(f"✗ 測試過程中發生錯誤: {e}")
        return False

if __name__ == "__main__":
    success = test_restored_features()
    sys.exit(0 if success else 1)
