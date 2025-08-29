#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
測試優化後的文件檢查功能
驗證大量文件目錄的檢查性能
"""

import sys
import os
import time
from pathlib import Path

# 添加項目根目錄到 Python 路徑
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.controllers.data_processor import DelayedMoveManager
from app.utils.config_manager import config

def test_optimized_file_check():
    """測試優化後的文件檢查功能"""
    print("🧪 測試優化後的文件檢查功能")
    print("=" * 60)
    
    # 創建延遲移動管理器
    delayed_manager = DelayedMoveManager()
    
    # 測試參數
    component_id = "WLPF80030004"
    lot_id = "WLPF800300"
    station = "RDL"
    source_product = "temp"
    target_product = "i-Pixel"
    file_types = ["org", "roi", "csv", "map"]
    
    print(f"📋 測試參數:")
    print(f"  組件ID: {component_id}")
    print(f"  批次ID: {lot_id}")
    print(f"  站點: {station}")
    print(f"  源產品: {source_product}")
    print(f"  目標產品: {target_product}")
    print(f"  文件類型: {file_types}")
    print()
    
    # 測試文件檢查功能
    print("🔍 開始文件檢查...")
    start_time = time.time()
    
    try:
        delayed_manager._debug_component_files(
            component_id, lot_id, station, 
            source_product, target_product, file_types
        )
    except Exception as e:
        print(f"❌ 文件檢查失敗: {e}")
        return False
    
    end_time = time.time()
    execution_time = end_time - start_time
    
    print(f"\n⏱️  執行時間: {execution_time:.3f} 秒")
    
    if execution_time < 1.0:
        print("✅ 性能測試通過：文件檢查在1秒內完成")
    else:
        print(f"⚠️  性能警告：文件檢查耗時 {execution_time:.3f} 秒")
    
    return True

def test_large_directory_performance():
    """測試大量文件目錄的性能"""
    print("\n" + "=" * 60)
    print("🚀 測試大量文件目錄的性能")
    print("=" * 60)
    
    # 創建測試目錄結構
    test_dir = Path("test_large_directory")
    test_dir.mkdir(exist_ok=True)
    
    # 創建大量測試文件
    print("📁 創建測試目錄結構...")
    for i in range(1000):  # 創建1000個測試文件
        test_file = test_dir / f"test_file_{i:06d}.txt"
        test_file.write_text(f"Test content {i}")
    
    print(f"✅ 已創建 {len(list(test_dir.glob('*')))} 個測試文件")
    
    # 測試目錄讀取性能
    print("\n⏱️  測試目錄讀取性能...")
    
    # 方法1：使用 os.listdir（優化後的方法）
    start_time = time.time()
    try:
        import os
        items = os.listdir(test_dir)
        file_count = len([item for item in items if (test_dir / item).is_file()])
        end_time = time.time()
        print(f"✅ os.listdir 方法:")
        print(f"   文件數量: {file_count}")
        print(f"   耗時: {(end_time - start_time)*1000:.2f} 毫秒")
    except Exception as e:
        print(f"❌ os.listdir 方法失敗: {e}")
    
    # 方法2：使用 Path.iterdir（舊方法）
    start_time = time.time()
    try:
        files = list(test_dir.iterdir())
        file_count = len([f for f in files if f.is_file()])
        end_time = time.time()
        print(f"✅ Path.iterdir 方法:")
        print(f"   文件數量: {file_count}")
        print(f"   耗時: {(end_time - start_time)*1000:.2f} 毫秒")
    except Exception as e:
        print(f"❌ Path.iterdir 方法失敗: {e}")
    
    # 方法3：使用 Path.rglob（最慢的方法）
    start_time = time.time()
    try:
        files = list(test_dir.rglob('*'))
        file_count = len([f for f in files if f.is_file()])
        end_time = time.time()
        print(f"✅ Path.rglob 方法:")
        print(f"   文件數量: {file_count}")
        print(f"   耗時: {(end_time - start_time)*1000:.2f} 毫秒")
    except Exception as e:
        print(f"❌ Path.rglob 方法失敗: {e}")
    
    # 清理測試目錄
    print("\n🧹 清理測試目錄...")
    try:
        import shutil
        shutil.rmtree(test_dir)
        print("✅ 測試目錄已清理")
    except Exception as e:
        print(f"⚠️  清理測試目錄失敗: {e}")

if __name__ == "__main__":
    print("🚀 開始測試優化後的文件檢查功能")
    print()
    
    # 測試基本功能
    if test_optimized_file_check():
        print("\n✅ 基本功能測試通過")
    else:
        print("\n❌ 基本功能測試失敗")
    
    # 測試性能
    test_large_directory_performance()
    
    print("\n🎉 所有測試完成！")

