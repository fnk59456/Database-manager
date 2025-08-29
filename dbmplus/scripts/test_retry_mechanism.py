#!/usr/bin/env python3
"""
測試重試機制腳本
驗證 "找不到組件" 錯誤是否會被正確添加到重試隊列
"""

import sys
import os
from pathlib import Path

# 添加項目根目錄到 Python 路徑
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.controllers.retry_manager import retry_manager, RetryTask
from app.utils.config_manager import config

def test_retry_mechanism():
    """測試重試機制"""
    print("🔄 測試重試機制")
    print("=" * 50)
    
    # 1. 檢查重試配置
    print("\n1. 重試配置檢查:")
    retry_config = config.get("auto_move.retry_mechanism", {})
    print(f"   啟用狀態: {retry_config.get('enabled', '未設置')}")
    print(f"   最大重試次數: {retry_config.get('max_retry_count', '未設置')}")
    print(f"   重試間隔: {retry_config.get('retry_intervals_minutes', '未設置')}")
    print(f"   部分失敗重試: {retry_config.get('retry_on_partial_failure', '未設置')}")
    
    # 2. 測試重試管理器狀態
    print("\n2. 重試管理器狀態:")
    print(f"   重試機制啟用: {retry_manager.is_retry_enabled()}")
    print(f"   部分失敗重試: {retry_manager.should_retry_on_partial_failure()}")
    
    # 3. 測試添加 "找不到組件" 錯誤到重試隊列
    print("\n3. 測試添加 '找不到組件' 錯誤:")
    
    # 模擬一個 "找不到組件" 錯誤
    component_id = "TEST_COMPONENT_001"
    lot_id = "TEST_LOT_001"
    station = "TEST_STATION"
    source_product = "source_product"
    target_product = "target_product"
    file_types = ["org", "roi"]
    failure_reason = "找不到組件: TEST_COMPONENT_001"
    failed_files = ["org_file1", "roi_file1"]
    successful_files = []
    
    # 添加到重試隊列
    retry_added = retry_manager.add_retry_task(
        component_id=component_id,
        lot_id=lot_id,
        station=station,
        source_product=source_product,
        target_product=target_product,
        file_types=file_types,
        failure_reason=failure_reason,
        failed_files=failed_files,
        successful_files=successful_files
    )
    
    print(f"   添加結果: {'成功' if retry_added else '失敗'}")
    
    # 4. 檢查重試隊列狀態
    print("\n4. 重試隊列狀態:")
    stats = retry_manager.get_retry_stats()
    print(f"   總重試任務數: {stats['total_retry_tasks']}")
    print(f"   準備重試的任務數: {stats['ready_for_retry']}")
    
    # 5. 檢查任務詳情
    if stats['task_details']:
        print("\n5. 任務詳情:")
        for task in stats['task_details']:
            print(f"   組件: {task['component_id']}")
            print(f"   嘗試次數: {task['attempt_count']}")
            print(f"   下次重試時間: {task['next_retry_time']}")
            print(f"   失敗原因: {task['failure_reason']}")
            print("   ---")
    
    # 6. 測試獲取準備重試的任務
    print("\n6. 準備重試的任務:")
    ready_tasks = retry_manager.get_ready_retry_tasks()
    print(f"   準備重試的任務數: {len(ready_tasks)}")
    
    for task in ready_tasks:
        print(f"   組件: {task.component_id}")
        print(f"   失敗原因: {task.failure_reason}")
        print(f"   下次重試時間: {task.next_retry_time}")
    
    # 7. 清理測試數據
    print("\n7. 清理測試數據:")
    retry_manager.clear_all_tasks()
    print("   已清除所有重試任務")
    
    # 8. 最終狀態檢查
    final_stats = retry_manager.get_retry_stats()
    print(f"   清理後總任務數: {final_stats['total_retry_tasks']}")
    
    print("\n✅ 重試機制測試完成")

if __name__ == "__main__":
    try:
        test_retry_mechanism()
    except Exception as e:
        print(f"❌ 測試過程中發生錯誤: {e}")
        import traceback
        traceback.print_exc()
