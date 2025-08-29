#!/usr/bin/env python3
"""
調試 dbmplus 實際使用的路徑配置和文件查找邏輯
"""

import sys
import os
from pathlib import Path

# 添加項目根目錄到 Python 路徑
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.utils.config_manager import ConfigManager
from app.models.database_manager import DatabaseManager

def debug_dbmplus_paths():
    """調試 dbmplus 實際使用的路徑配置"""
    print("=" * 80)
    print("dbmplus 路徑配置調試")
    print("=" * 80)
    
    # 初始化配置管理器
    config = ConfigManager()
    
    print(f"配置基礎路徑: {config.get('database.base_path')}")
    print(f"ORG 路徑模板: {config.get('database.structure.org')}")
    print(f"ROI 路徑模板: {config.get('database.structure.roi')}")
    
    # 測試組件
    test_components = [
        {
            "component_id": "WLPF80030004",
            "lot_id": "temp_WLPF800300",  # 這是 dbmplus 中使用的完整 lot_id
            "station": "RDL",
            "source_product": "i-Pixel",
            "target_product": "i-Pixel"
        }
    ]
    
    for comp in test_components:
        print(f"\n組件: {comp['component_id']}")
        print(f"完整批次ID: {comp['lot_id']}")
        
        # 提取原始批次ID（這是我們修復後的邏輯）
        if comp['lot_id'].startswith("temp_"):
            original_lot_id = comp['lot_id'][5:]  # 移除 "temp_" 前綴
        else:
            original_lot_id = comp['lot_id']
        print(f"原始批次ID: {original_lot_id}")
        
        # 檢查實際文件系統中的路徑
        print("\n--- 實際文件系統路徑 ---")
        
        # 檢查 temp 目錄下的路徑
        temp_base = r"E:\Database-PC\temp"
        if os.path.exists(temp_base):
            print(f"Temp 基礎目錄存在: {temp_base}")
            
            # 檢查 org 路徑
            org_temp_path = os.path.join(temp_base, "org", original_lot_id, comp['station'], comp['component_id'])
            print(f"ORG Temp 路徑: {org_temp_path}")
            print(f"ORG Temp 路徑存在: {os.path.exists(org_temp_path)}")
            
            # 檢查 roi 路徑
            roi_temp_path = os.path.join(temp_base, "roi", original_lot_id, comp['station'], comp['component_id'])
            print(f"ROI Temp 路徑: {roi_temp_path}")
            print(f"ROI Temp 路徑存在: {os.path.exists(roi_temp_path)}")
        else:
            print(f"Temp 基礎目錄不存在: {temp_base}")
        
        # 檢查配置路徑
        print("\n--- 配置路徑 ---")
        try:
            org_config_path = config.get_path("database.structure.org", 
                                            base_path=config.get("database.base_path"),
                                            product=comp['source_product'],
                                            lot=comp['lot_id'],
                                            station=comp['station'],
                                            component=comp['component_id'])
            roi_config_path = config.get_path("database.structure.roi", 
                                            base_path=config.get("database.base_path"),
                                            product=comp['source_product'],
                                            lot=comp['lot_id'],
                                            station=comp['station'],
                                            component=comp['component_id'])
            
            print(f"ORG 配置路徑: {org_config_path}")
            print(f"ROI 配置路徑: {roi_config_path}")
            
            if org_config_path:
                print(f"ORG 配置路徑存在: {Path(org_config_path).exists()}")
            if roi_config_path:
                print(f"ROI 配置路徑存在: {Path(roi_config_path).exists()}")
        except Exception as e:
            print(f"配置路徑生成錯誤: {e}")
        
        # 檢查使用原始批次ID的配置路徑
        print("\n--- 使用原始批次ID的配置路徑 ---")
        try:
            org_config_path_original = config.get_path("database.structure.org", 
                                                     base_path=config.get("database.base_path"),
                                                     product=comp['source_product'],
                                                     lot=original_lot_id,
                                                     station=comp['station'],
                                                     component=comp['component_id'])
            roi_config_path_original = config.get_path("database.structure.roi", 
                                                     base_path=config.get("database.base_path"),
                                                     product=comp['source_product'],
                                                     lot=original_lot_id,
                                                     station=comp['station'],
                                                     component=comp['component_id'])
            
            print(f"ORG 配置路徑（原始批次ID）: {org_config_path_original}")
            print(f"ROI 配置路徑（原始批次ID）: {roi_config_path_original}")
            
            if org_config_path_original:
                print(f"ORG 配置路徑（原始批次ID）存在: {Path(org_config_path_original).exists()}")
            if roi_config_path_original:
                print(f"ROI 配置路徑（原始批次ID）存在: {Path(roi_config_path_original).exists()}")
        except Exception as e:
            print(f"配置路徑生成錯誤: {e}")

def debug_database_manager_paths():
    """調試數據庫管理器使用的路徑"""
    print("\n" + "=" * 80)
    print("數據庫管理器路徑調試")
    print("=" * 80)
    
    try:
        # 初始化數據庫管理器
        db_manager = DatabaseManager()
        
        # 檢查基礎路徑
        print(f"數據庫管理器基礎路徑: {db_manager.base_path}")
        
        # 檢查組件路徑
        component_id = "WLPF80030004"
        lot_id = "WLPF800300"  # 使用原始批次ID
        station = "RDL"
        product_id = "i-Pixel"
        
        # 檢查 org 路徑
        org_path = db_manager.base_path / product_id / "org" / lot_id / station / component_id
        print(f"ORG 路徑: {org_path}")
        print(f"ORG 路徑存在: {org_path.exists()}")
        
        # 檢查 roi 路徑
        roi_path = db_manager.base_path / product_id / "roi" / lot_id / station / component_id
        print(f"ROI 路徑: {roi_path}")
        print(f"ROI 路徑存在: {roi_path.exists()}")
        
    except Exception as e:
        print(f"數據庫管理器路徑調試錯誤: {e}")

def main():
    """主函數"""
    print("dbmplus 路徑配置調試工具")
    print("這個工具檢查 dbmplus 實際使用的路徑配置和文件查找邏輯")
    
    # 1. 調試 dbmplus 路徑配置
    debug_dbmplus_paths()
    
    # 2. 調試數據庫管理器路徑
    debug_database_manager_paths()
    
    print("\n" + "=" * 80)
    print("調試完成")
    print("=" * 80)

if __name__ == "__main__":
    main()
