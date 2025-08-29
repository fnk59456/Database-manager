#!/usr/bin/env python3
"""
測試實際的批量移動功能，驗證修復後的組件查找邏輯
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def test_actual_move():
    """測試實際的批量移動功能"""
    print("開始測試實際的批量移動功能...")
    
    try:
        # 導入必要的模塊
        from app.controllers.data_processor import DataProcessor
        print("✓ 導入成功")
        
        # 創建數據處理器實例
        data_processor = DataProcessor()
        print("✓ 創建數據處理器實例成功")
        
        # 測試數據：只測試 WLPF80030004 組件
        test_components = [
            ("WLPF80030004", "temp_WLPF800300", "RDL", "temp")
        ]
        
        print(f"\n🔍 測試組件: {test_components[0][0]}")
        print(f"   批次ID: {test_components[0][1]}")
        print(f"   站點: {test_components[0][2]}")
        print(f"   源產品: {test_components[0][3]}")
        print("   " + "="*60)
        
        # 執行批量移動
        print("\n🚀 開始執行批量移動...")
        success, message = data_processor.batch_move_files(
            components_data=test_components,
            target_product="i-Pixel",
            file_types=["org", "roi"]
        )
        
        print(f"\n📊 移動結果:")
        print(f"   成功狀態: {success}")
        print(f"   結果訊息: {message}")
        
        if success:
            print("   ✅ 批量移動成功！")
        else:
            print("   ❌ 批量移動失敗")
            print("   這表示組件查找邏輯仍有問題")
        
        return success
        
    except ImportError as e:
        print(f"✗ 導入失敗: {e}")
        return False
    except Exception as e:
        print(f"✗ 測試過程中發生錯誤: {e}")
        return False

if __name__ == "__main__":
    success = test_actual_move()
    sys.exit(0 if success else 1)
