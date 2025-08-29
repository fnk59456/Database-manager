#!/usr/bin/env python3
"""
測試延遲移動過程中的詳細路徑調試功能
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def test_delayed_move_debug():
    """測試延遲移動過程中的詳細路徑調試功能"""
    print("開始測試延遲移動過程中的詳細路徑調試功能...")
    
    try:
        # 導入必要的模塊
        from app.controllers.data_processor import DataProcessor
        print("✓ 導入成功")
        
        # 創建數據處理器實例
        data_processor = DataProcessor()
        print("✓ 創建數據處理器實例成功")
        
        # 模擬延遲移動的組件數據
        components_data = [
            ("WLPF80030001", "temp_WLPF800300", "RDL", "temp"),
            ("WLPF80030002", "temp_WLPF800300", "RDL", "temp"),
            ("WLPF80030003", "temp_WLPF800300", "RDL", "temp"),
            ("WLPF80030004", "temp_WLPF800300", "RDL", "temp"),
            ("WLPF80030005", "temp_WLPF800300", "RDL", "temp")
        ]
        
        target_product = "i-Pixel"
        file_types = ["org", "roi"]
        
        print(f"\n📋 測試數據:")
        print(f"   組件數量: {len(components_data)}")
        print(f"   目標產品: {target_product}")
        print(f"   文件類型: {file_types}")
        print("   " + "="*60)
        
        # 模擬延遲移動過程中的詳細路徑調試
        print("\n🚀 開始模擬延遲移動過程中的詳細路徑調試...")
        
        for index, (component_id, lot_id, station, source_product) in enumerate(components_data):
            print(f"\n🔍 延遲移動前檢查 - 組件 {component_id} ({index+1}/{len(components_data)})")
            
            # 調用詳細路徑調試方法
            data_processor._debug_component_files(
                component_id=component_id,
                lot_id=lot_id,
                station=station,
                source_product=source_product,
                target_product=target_product,
                file_types=file_types
            )
        
        print("\n🎉 延遲移動詳細路徑調試測試完成！")
        print("\n📝 你應該看到:")
        print("   🔍 延遲移動前檢查 - 每個組件的詳細路徑調試")
        print("   📁 路徑生成邏輯 - 配置模板和參數")
        print("   ✅ 源路徑存在 - 實際文件結構")
        print("   📝 目標路徑 - 將創建的路徑")
        print("   ❌ 源路徑不存在 - 問題診斷")
        print("   📊 移動結果 - 成功/失敗統計")
        
        return True
        
    except ImportError as e:
        print(f"✗ 導入失敗: {e}")
        return False
    except Exception as e:
        print(f"✗ 測試過程中發生錯誤: {e}")
        return False

if __name__ == "__main__":
    success = test_delayed_move_debug()
    sys.exit(0 if success else 1)
