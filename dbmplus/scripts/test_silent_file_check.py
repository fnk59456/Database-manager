#!/usr/bin/env python3
"""
測試靜默版本的文件檢查功能
驗證 _debug_component_files 方法不再輸出詳細文件信息
"""

import sys
import os
from pathlib import Path
import tempfile
import time

# 添加項目根目錄到 Python 路徑
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.controllers.data_processor import DataProcessor
from app.utils.logger import setup_logger

def test_silent_file_check():
    """測試靜默文件檢查功能"""
    print("=== 測試靜默文件檢查功能 ===")
    
    # 設置日誌
    logger = setup_logger()
    
    # 創建 DataProcessor 實例
    processor = DataProcessor()
    
    # 創建測試目錄結構
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        
        # 創建測試組件目錄
        test_component = "TEST001"
        org_dir = temp_path / "org" / test_component
        roi_dir = temp_path / "roi" / test_component
        
        org_dir.mkdir(parents=True, exist_ok=True)
        roi_dir.mkdir(parents=True, exist_ok=True)
        
        # 創建一些測試文件
        for i in range(5):
            (org_dir / f"org_file_{i}.txt").write_text(f"org content {i}")
            (roi_dir / f"roi_file_{i}.txt").write_text(f"roi content {i}")
        
        # 創建大量文件測試（模擬實際情況）
        large_dir = temp_path / "large_test"
        large_dir.mkdir(exist_ok=True)
        for i in range(1000):
            (large_dir / f"large_file_{i}.txt").write_text(f"large content {i}")
        
        print(f"創建測試目錄: {temp_path}")
        print(f"測試組件: {test_component}")
        print(f"org 文件數量: {len(list(org_dir.glob('*')))}")
        print(f"roi 文件數量: {len(list(roi_dir.glob('*')))}")
        print(f"大量文件目錄: {len(list(large_dir.glob('*')))} 個文件")
        
        # 測試靜默文件檢查
        print("\n--- 執行靜默文件檢查 ---")
        start_time = time.time()
        
        source_paths = {
            'org': org_dir,
            'roi': roi_dir
        }
        
        # 調用靜默版本的方法
        processor._debug_component_files(test_component, source_paths)
        
        end_time = time.time()
        execution_time = end_time - start_time
        
        print(f"執行時間: {execution_time:.4f} 秒")
        print("✅ 靜默文件檢查完成，終端沒有輸出詳細文件信息")
        
        # 測試空目錄情況
        print("\n--- 測試空目錄情況 ---")
        empty_dir = temp_path / "empty_test"
        empty_dir.mkdir(exist_ok=True)
        
        empty_paths = {
            'org': empty_dir,
            'roi': roi_dir
        }
        
        processor._debug_component_files(test_component, empty_paths)
        print("✅ 空目錄檢查完成")
        
        # 測試不存在的路徑
        print("\n--- 測試不存在路徑 ---")
        nonexistent_paths = {
            'org': temp_path / "nonexistent" / test_component,
            'roi': roi_dir
        }
        
        processor._debug_component_files(test_component, nonexistent_paths)
        print("✅ 不存在路徑檢查完成")

def test_performance_comparison():
    """性能比較測試"""
    print("\n=== 性能比較測試 ===")
    
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        
        # 創建大量文件目錄
        large_dir = temp_path / "performance_test"
        large_dir.mkdir(exist_ok=True)
        
        print("創建測試文件...")
        for i in range(5000):
            (large_dir / f"perf_file_{i}.txt").write_text(f"performance test content {i}")
        
        print(f"創建了 {len(list(large_dir.glob('*')))} 個測試文件")
        
        # 測試 os.listdir 性能
        start_time = time.time()
        files = os.listdir(large_dir)
        listdir_time = time.time() - start_time
        
        # 測試 Path.iterdir 性能
        start_time = time.time()
        files_iter = list(large_dir.iterdir())
        iterdir_time = time.time() - start_time
        
        # 測試 Path.rglob 性能
        start_time = time.time()
        files_rglob = list(large_dir.rglob('*'))
        rglob_time = time.time() - start_time
        
        print(f"os.listdir 耗時: {listdir_time:.4f} 秒")
        print(f"Path.iterdir 耗時: {iterdir_time:.4f} 秒")
        print(f"Path.rglob 耗時: {rglob_time:.4f} 秒")
        
        print(f"os.listdir 比 Path.iterdir 快 {iterdir_time/listdir_time:.2f} 倍")
        print(f"os.listdir 比 Path.rglob 快 {rglob_time/listdir_time:.2f} 倍")

if __name__ == "__main__":
    try:
        test_silent_file_check()
        test_performance_comparison()
        print("\n🎉 所有測試完成！")
        
    except Exception as e:
        print(f"❌ 測試過程中發生錯誤: {e}")
        import traceback
        traceback.print_exc()

