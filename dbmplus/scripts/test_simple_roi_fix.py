#!/usr/bin/env python3
"""
簡單的 ROI 路徑修復測試腳本
只測試 ComponentInfo 類的修改，不依賴數據庫管理器
"""

import sys
from pathlib import Path

# 添加項目根目錄到 Python 路徑
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.models.data_models import ComponentInfo

def test_simple_roi_fix():
    """簡單測試 ROI 路徑修復"""
    print("🧪 簡單測試 ROI 路徑修復")
    print("=" * 50)
    
    # 1. 測試 ComponentInfo 類是否包含 roi_path 屬性
    print("\n1. 檢查 ComponentInfo 類屬性...")
    component = ComponentInfo(
        component_id="TEST001",
        lot_id="TEST_LOT",
        station="MT"
    )
    
    if hasattr(component, 'roi_path'):
        print("   ✅ ComponentInfo 類現在包含 roi_path 屬性")
        print(f"   📁 roi_path 初始值: {component.roi_path}")
    else:
        print("   ❌ ComponentInfo 類仍然缺少 roi_path 屬性")
        return False
    
    # 2. 測試 roi_path 可以設置和獲取
    print("\n2. 測試 roi_path 設置和獲取...")
    test_roi_path = "/test/path/to/roi"
    component.roi_path = test_roi_path
    
    if component.roi_path == test_roi_path:
        print("   ✅ roi_path 可以正確設置和獲取")
    else:
        print(f"   ❌ roi_path 設置失敗: 期望 {test_roi_path}, 實際 {component.roi_path}")
        return False
    
    # 3. 測試 to_dict 方法包含 roi_path
    print("\n3. 測試 to_dict 方法...")
    component_dict = component.to_dict()
    
    if 'roi_path' in component_dict:
        print("   ✅ to_dict 方法包含 roi_path 字段")
        print(f"   📋 roi_path 值: {component_dict['roi_path']}")
    else:
        print("   ❌ to_dict 方法缺少 roi_path 字段")
        print(f"   📋 實際字段: {list(component_dict.keys())}")
        return False
    
    # 4. 測試 update_paths 方法
    print("\n4. 測試 update_paths 方法...")
    new_roi_path = "/new/path/to/roi"
    component.update_paths(roi_path=new_roi_path)
    
    if component.roi_path == new_roi_path:
        print("   ✅ update_paths 方法可以更新 roi_path")
    else:
        print(f"   ❌ update_paths 方法更新 roi_path 失敗: 期望 {new_roi_path}, 實際 {component.roi_path}")
        return False
    
    # 5. 檢查所有路徑屬性
    print("\n5. 檢查所有路徑屬性...")
    path_attributes = [
        'org_path', 'roi_path', 'csv_path', 'original_csv_path',
        'basemap_path', 'lossmap_path', 'fpy_path'
    ]
    
    missing_attributes = []
    for attr in path_attributes:
        if not hasattr(component, attr):
            missing_attributes.append(attr)
    
    if not missing_attributes:
        print("   ✅ 所有路徑屬性都存在")
        for attr in path_attributes:
            value = getattr(component, attr)
            print(f"      📁 {attr}: {value}")
    else:
        print(f"   ❌ 缺少路徑屬性: {missing_attributes}")
        return False
    
    print("\n" + "=" * 50)
    print("🎉 簡單 ROI 路徑修復測試完成！")
    print("\n📋 修復摘要:")
    print("   • 在 ComponentInfo 類中添加了 roi_path 屬性")
    print("   • 更新了 to_dict 方法以包含 roi_path")
    print("   • 在 _check_component_files 中添加了 ROI 文件檢查")
    print("   • 這應該解決 '找不到組件' 錯誤，因為現在組件緩存會包含完整的文件路徑信息")
    
    return True

if __name__ == "__main__":
    try:
        success = test_simple_roi_fix()
        if success:
            print("\n✅ 所有測試通過！ROI 路徑修復成功。")
            sys.exit(0)
        else:
            print("\n❌ 測試失敗！請檢查修復。")
            sys.exit(1)
    except Exception as e:
        print(f"\n💥 測試執行時發生錯誤: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

