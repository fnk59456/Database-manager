#!/usr/bin/env python3
"""
測試 dbmplus 中的智能文件查找邏輯
"""

import sys
import os
from pathlib import Path

# 添加項目根目錄到 Python 路徑
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.utils.config_manager import ConfigManager
from app.controllers.data_processor import DelayedMoveManager

def test_smart_file_finding():
    """測試智能文件查找邏輯"""
    print("測試 dbmplus 中的智能文件查找邏輯")
    print("=" * 80)
    
    # 初始化配置管理器
    config = ConfigManager()
    
    # 測試組件
    test_component = {
        "component_id": "WLPF80030004",
        "lot_id": "temp_WLPF800300",
        "station": "RDL",
        "source_product": "temp",
        "target_product": "i-Pixel"
    }
    
    print(f"測試組件: {test_component}")
    
    # 提取原始批次ID
    if test_component['lot_id'].startswith("temp_"):
        original_lot_id = test_component['lot_id'][5:]  # 移除 "temp_" 前綴
    else:
        original_lot_id = test_component['lot_id']
    
    print(f"原始批次ID: {original_lot_id}")
    
    # 測試 org 文件查找
    print(f"\n--- 測試 ORG 文件查找 ---")
    
    # 1. 首先檢查配置的源產品目錄
    config_source_path = Path(config.get_path(
        f"database.structure.org",
        base_path=config.get("database.base_path"),
        product=test_component['source_product'],
        lot=original_lot_id,
        station=test_component['station'],
        component=test_component['component_id']
    ))
    
    print(f"配置源路徑: {config_source_path}")
    print(f"配置源路徑存在: {config_source_path.exists() if config_source_path else False}")
    
    if config_source_path and config_source_path.exists():
        print(f"✅ 使用配置源路徑: {config_source_path}")
        source_path = config_source_path
        actual_product = test_component['source_product']
    else:
        print("❌ 配置源路徑不存在，開始智能搜索...")
        
        # 2. 搜索所有產品目錄
        base_path = Path(config.get("database.base_path", "D:/Database-PC"))
        print(f"搜索基礎路徑: {base_path}")
        
        source_path = None
        actual_product = None
        
        for product_dir in base_path.iterdir():
            if product_dir.is_dir():
                search_path = product_dir / "org" / original_lot_id / test_component['station'] / test_component['component_id']
                print(f"搜索路徑: {search_path} (存在: {search_path.exists()})")
                if search_path.exists():
                    source_path = search_path
                    actual_product = product_dir.name
                    print(f"✅ 找到文件路徑: {source_path}")
                    break
        
        if not source_path:
            print(f"❌ 在所有產品目錄中都未找到 org 文件: {test_component['component_id']}")
        else:
            print(f"✅ 智能搜索成功: {source_path}")
    
    # 測試 ROI 文件查找
    print(f"\n--- 測試 ROI 文件查找 ---")
    
    # 1. 首先檢查配置的源產品目錄
    config_source_path_roi = Path(config.get_path(
        f"database.structure.roi",
        base_path=config.get("database.base_path"),
        product=test_component['source_product'],
        lot=original_lot_id,
        station=test_component['station'],
        component=test_component['component_id']
    ))
    
    print(f"配置源路徑: {config_source_path_roi}")
    print(f"配置源路徑存在: {config_source_path_roi.exists() if config_source_path_roi else False}")
    
    if config_source_path_roi and config_source_path_roi.exists():
        print(f"✅ 使用配置源路徑: {config_source_path_roi}")
        source_path_roi = config_source_path_roi
        actual_product_roi = test_component['source_product']
    else:
        print("❌ 配置源路徑不存在，開始智能搜索...")
        
        # 2. 搜索所有產品目錄
        source_path_roi = None
        actual_product_roi = None
        
        for product_dir in base_path.iterdir():
            if product_dir.is_dir():
                search_path = product_dir / "roi" / original_lot_id / test_component['station'] / test_component['component_id']
                print(f"搜索路徑: {search_path} (存在: {search_path.exists()})")
                if search_path.exists():
                    source_path_roi = search_path
                    actual_product_roi = product_dir.name
                    print(f"✅ 找到文件路徑: {source_path_roi}")
                    break
        
        if not source_path_roi:
            print(f"❌ 在所有產品目錄中都未找到 roi 文件: {test_component['component_id']}")
        else:
            print(f"✅ 智能搜索成功: {source_path_roi}")
    
    # 總結
    print(f"\n--- 查找結果總結 ---")
    if source_path:
        print(f"ORG 文件: ✅ 找到於 {source_path}")
    else:
        print(f"ORG 文件: ❌ 未找到")
    
    if source_path_roi:
        print(f"ROI 文件: ✅ 找到於 {source_path_roi}")
    else:
        print(f"ROI 文件: ❌ 未找到")

def main():
    """主函數"""
    test_smart_file_finding()
    
    print("\n" + "=" * 80)
    print("測試完成")
    print("=" * 80)

if __name__ == "__main__":
    main()



