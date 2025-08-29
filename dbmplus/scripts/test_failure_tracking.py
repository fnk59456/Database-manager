#!/usr/bin/env python3
"""
測試失敗記錄機制的腳本
"""
import sys
import os
from pathlib import Path

# 添加項目根目錄到Python路徑
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.controllers.data_processor import DelayedMoveManager
import datetime

def test_failure_tracking():
    """測試失敗記錄機制"""
    print("🧪 測試失敗記錄機制")
    print("=" * 50)
    
    # 創建延遲移動管理器
    manager = DelayedMoveManager()
    
    # 測試1: 記錄組件失敗
    print("\n1. 測試記錄組件失敗")
    manager.record_component_failure("TEST001", "文件不存在")
    manager.record_component_failure("TEST002", "權限不足")
    manager.record_component_failure("TEST001", "路徑錯誤")  # 重複失敗
    
    print(f"失敗組件數量: {len(manager.failed_components)}")
    
    # 測試2: 獲取失敗摘要
    print("\n2. 測試獲取失敗摘要")
    summary = manager.get_failed_components_summary()
    print(f"總失敗數: {summary['total']}")
    print(f"組件詳情:")
    for comp_id, info in summary['components'].items():
        print(f"  {comp_id}: 失敗{info['failure_count']}次, 錯誤: {info['error']}")
    
    # 測試3: 測試重試限制
    print("\n3. 測試重試限制")
    print("嘗試添加已失敗的組件到隊列:")
    
    # 模擬多次失敗
    for i in range(5):
        manager.record_component_failure("TEST001", f"第{i+1}次失敗")
    
    # 嘗試添加到延遲移動隊列
    manager.add_to_delayed_queue("TEST001", "LOT001", "STATION1", "PRODUCT1", "TARGET1")
    
    # 測試4: 獲取失敗統計
    print("\n4. 測試失敗統計")
    stats = manager.get_failure_statistics()
    print(f"總失敗組件: {stats['total_failed']}")
    print(f"最大失敗次數: {stats['max_failure_count']}")
    print(f"按失敗次數分組:")
    for count, components in stats['components_by_failure_count'].items():
        print(f"  失敗{count}次: {components}")
    
    # 測試5: 重置失敗記錄
    print("\n5. 測試重置失敗記錄")
    reset_count = manager.reset_failure_record("TEST001")
    print(f"重置了 {reset_count} 個組件的失敗記錄")
    
    # 再次嘗試添加到隊列
    manager.add_to_delayed_queue("TEST001", "LOT001", "STATION1", "PRODUCT1", "TARGET1")
    print("重置後，組件已成功添加到隊列")
    
    # 測試6: 清理過期記錄
    print("\n6. 測試清理過期記錄")
    # 手動設置一個過期的失敗記錄
    manager.failed_components["EXPIRED001"] = {
        'count': 1,
        'last_failure': datetime.datetime.now() - datetime.timedelta(hours=25),  # 25小時前
        'error': "過期錯誤"
    }
    
    print(f"清理前失敗組件數: {len(manager.failed_components)}")
    cleaned_count = manager.cleanup_expired_failures()
    print(f"清理了 {cleaned_count} 個過期記錄")
    print(f"清理後失敗組件數: {len(manager.failed_components)}")
    
    print("\n✅ 所有測試完成!")

if __name__ == "__main__":
    test_failure_tracking()

