#!/usr/bin/env python3
"""
調試重試管理器狀態的腳本
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.controllers.retry_manager import retry_manager
from app.utils.config_manager import config

def main():
    print("🔍 重試管理器狀態檢查")
    print("=" * 50)
    
    # 檢查重試配置
    print("\n📋 重試配置:")
    retry_config = retry_manager.retry_config
    print(f"  啟用狀態: {retry_config['enabled']}")
    print(f"  最大重試次數: {retry_config['max_retry_count']}")
    print(f"  重試間隔(分鐘): {retry_config['retry_intervals_minutes']}")
    print(f"  部分失敗時重試: {retry_config['retry_on_partial_failure']}")
    
    # 檢查重試隊列狀態
    print("\n📊 重試隊列狀態:")
    stats = retry_manager.get_retry_stats()
    print(f"  總任務數: {stats['total_retry_tasks']}")
    print(f"  準備重試的任務數: {stats['ready_for_retry']}")
    
    # 檢查具體任務詳情
    if stats['task_details']:
        print("\n📋 任務詳情:")
        for i, task_detail in enumerate(stats['task_details']):
            print(f"  {i+1}. 組件 {task_detail['component_id']}:")
            print(f"     嘗試次數: {task_detail['attempt_count']}")
            print(f"     下次重試時間: {task_detail['next_retry_time']}")
            print(f"     失敗原因: {task_detail['failure_reason']}")
    else:
        print("  ❌ 重試隊列為空")
    
    # 檢查準備重試的任務
    print("\n🔄 準備重試的任務:")
    ready_tasks = retry_manager.get_ready_retry_tasks()
    if ready_tasks:
        for task in ready_tasks:
            print(f"  ✅ {task.component_id} - 第 {task.attempt_count} 次嘗試")
    else:
        print("  ⏸️  沒有準備重試的任務")
    
    # 檢查配置文件中的重試設定
    print("\n⚙️  配置文件重試設定:")
    try:
        config_retry = config.get("auto_move.retry_mechanism", {})
        print(f"  啟用: {config_retry.get('enabled', '未設定')}")
        print(f"  最大重試次數: {config_retry.get('max_retry_count', '未設定')}")
        print(f"  重試間隔: {config_retry.get('retry_intervals_minutes', '未設定')}")
    except Exception as e:
        print(f"  ❌ 讀取配置失敗: {e}")

if __name__ == "__main__":
    main()

