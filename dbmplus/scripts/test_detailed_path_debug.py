#!/usr/bin/env python3
"""
測試詳細路徑調試功能
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def test_detailed_path_debug():
    """測試詳細路徑調試功能"""
    print("開始測試詳細路徑調試功能...")
    
    try:
        # 導入必要的模塊
        from app.controllers.data_processor import DelayedMoveManager
        from app.controllers.retry_manager import retry_manager
        print("✓ 導入成功")
        
        # 創建延遲移動管理器實例
        delayed_manager = DelayedMoveManager()
        print("✓ 創建延遲移動管理器實例成功")
        
        # 測試詳細路徑調試
        print("\n🔍 測試詳細路徑調試功能...")
        
        # 測試組件1：正常的 temp_ 前綴情況
        print("\n📋 測試案例 1: 正常的 temp_ 前綴情況")
        delayed_manager._debug_component_files(
            "WLPF80030004",           # component_id
            "temp_WLPF800300",        # lot_id (帶 temp_ 前綴)
            "RDL",                    # station
            "temp",                   # source_product
            "i-Pixel",                # target_product
            ["org", "roi"]            # file_types
        )
        
        # 測試組件2：沒有 temp_ 前綴的情況
        print("\n📋 測試案例 2: 沒有 temp_ 前綴的情況")
        delayed_manager._debug_component_files(
            "WLPF80030005",           # component_id
            "WLPF800300",             # lot_id (沒有 temp_ 前綴)
            "MT",                     # station
            "temp",                   # source_product
            "i-Pixel",                # target_product
            ["org", "roi"]            # file_types
        )
        
        # 測試組件3：不同的站點
        print("\n📋 測試案例 3: 不同的站點")
        delayed_manager._debug_component_files(
            "WLPF80030006",           # component_id
            "temp_WLPF800300",        # lot_id
            "DC2",                    # station
            "temp",                   # source_product
            "i-Pixel",                # target_product
            ["org", "roi"]            # file_types
        )
        
        print("\n🎉 詳細路徑調試測試完成！")
        print("\n📝 調試輸出說明:")
        print("   🔍 詳細路徑調試 - 顯示組件基本信息")
        print("   📁 路徑生成 - 顯示配置模板和參數")
        print("   ✅ 路徑存在 - 顯示實際文件結構")
        print("   ❌ 路徑不存在/讀取錯誤 - 顯示問題")
        print("   📊 調試完成 - 總結信息")
        
        return True
        
    except ImportError as e:
        print(f"✗ 導入失敗: {e}")
        return False
    except Exception as e:
        print(f"✗ 測試過程中發生錯誤: {e}")
        return False

if __name__ == "__main__":
    success = test_detailed_path_debug()
    sys.exit(0 if success else 1)
