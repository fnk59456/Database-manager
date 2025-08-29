#!/usr/bin/env python3
"""
重試管理器模塊，負責管理文件移動失敗後的重試任務
"""

import os
import json
import time
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict
from typing import Dict, List, Optional, Any
from pathlib import Path

from ..utils import get_logger, config

logger = get_logger("retry_manager")


@dataclass
class RetryTask:
    """重試任務數據類"""
    component_id: str
    lot_id: str
    station: str
    source_product: str
    target_product: str
    file_types: List[str]
    failure_reason: str
    retry_count: int
    first_failure_time: str
    last_failure_time: str
    next_retry_time: str
    max_retry_count: int = 3
    
    def to_dict(self) -> Dict[str, Any]:
        """轉換為字典"""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'RetryTask':
        """從字典創建實例"""
        return cls(**data)


class RetryManager:
    """重試管理器，負責管理失敗任務的重試邏輯"""
    
    def __init__(self):
        self.retry_tasks: Dict[str, RetryTask] = {}
        self.config_file = Path("data/retry_tasks.json")
        self.logger = get_logger("retry_manager")
        
        # 從配置讀取重試設置
        self.enabled = config.get("auto_move.retry_mechanism.enabled", True)
        self.max_retry_count = config.get("auto_move.retry_mechanism.max_retry_count", 3)
        self.retry_intervals = config.get("auto_move.retry_mechanism.retry_intervals_minutes", [5, 10, 15])
        self.retry_on_partial_failure = config.get("auto_move.retry_mechanism.retry_on_partial_failure", True)
        
        # 載入現有的重試任務
        self.load_retry_tasks()
        
        self.logger.info("重試管理器已初始化")
    
    def add_retry_task(self, component_id: str, lot_id: str, station: str,
                       source_product: str, target_product: str, file_types: List[str],
                       failure_reason: str) -> bool:
        """添加重試任務"""
        if not self.enabled:
            return False
            
        try:
            # 檢查是否已存在重試任務
            if component_id in self.retry_tasks:
                existing_task = self.retry_tasks[component_id]
                existing_task.retry_count += 1
                existing_task.last_failure_time = datetime.now().isoformat()
                existing_task.failure_reason = failure_reason
                
                # 檢查是否超過最大重試次數
                if existing_task.retry_count >= self.max_retry_count:
                    self.logger.warning(f"組件 {component_id} 已超過最大重試次數 {self.max_retry_count}")
                    return False
                
                # 計算下次重試時間
                retry_index = min(existing_task.retry_count - 1, len(self.retry_intervals) - 1)
                retry_interval = self.retry_intervals[retry_index]
                next_retry = datetime.now() + timedelta(minutes=retry_interval)
                existing_task.next_retry_time = next_retry.isoformat()
                
                self.logger.info(f"更新組件 {component_id} 的重試任務，重試次數: {existing_task.retry_count}")
            else:
                # 創建新的重試任務
                first_failure = datetime.now()
                next_retry = first_failure + timedelta(minutes=self.retry_intervals[0])
                
                retry_task = RetryTask(
                    component_id=component_id,
                    lot_id=lot_id,
                    station=station,
                    source_product=source_product,
                    target_product=target_product,
                    file_types=file_types,
                    failure_reason=failure_reason,
                    retry_count=1,
                    first_failure_time=first_failure.isoformat(),
                    last_failure_time=first_failure.isoformat(),
                    next_retry_time=next_retry.isoformat(),
                    max_retry_count=self.max_retry_count
                )
                
                self.retry_tasks[component_id] = retry_task
                self.logger.info(f"創建組件 {component_id} 的重試任務")
            
            # 保存到文件
            self.save_retry_tasks()
            return True
            
        except Exception as e:
            self.logger.error(f"添加重試任務時發生錯誤: {e}")
            return False
    
    def get_retry_tasks(self, include_expired: bool = False) -> List[RetryTask]:
        """獲取重試任務列表"""
        if include_expired:
            return list(self.retry_tasks.values())
        
        # 只返回準備重試的任務
        current_time = datetime.now()
        ready_tasks = []
        
        for task in self.retry_tasks.values():
            try:
                next_retry = datetime.fromisoformat(task.next_retry_time)
                if current_time >= next_retry:
                    ready_tasks.append(task)
            except ValueError:
                self.logger.warning(f"無效的時間格式: {task.next_retry_time}")
                continue
        
        return ready_tasks
    
    def remove_retry_task(self, component_id: str) -> bool:
        """移除重試任務"""
        if component_id in self.retry_tasks:
            del self.retry_tasks[component_id]
            self.save_retry_tasks()
            self.logger.info(f"移除組件 {component_id} 的重試任務")
            return True
        return False
    
    def cleanup_expired_tasks(self) -> int:
        """清理過期的重試任務（24小時後自動清理）"""
        current_time = datetime.now()
        expired_tasks = []
        
        for component_id, task in self.retry_tasks.items():
            try:
                first_failure = datetime.fromisoformat(task.first_failure_time)
                if current_time - first_failure > timedelta(hours=24):
                    expired_tasks.append(component_id)
            except ValueError:
                self.logger.warning(f"無效的時間格式: {task.first_failure_time}")
                expired_tasks.append(component_id)
        
        for component_id in expired_tasks:
            del self.retry_tasks[component_id]
        
        if expired_tasks:
            self.save_retry_tasks()
            self.logger.info(f"清理了 {len(expired_tasks)} 個過期的重試任務")
        
        return len(expired_tasks)
    
    def get_retry_statistics(self) -> Dict[str, Any]:
        """獲取重試統計信息"""
        if not self.retry_tasks:
            return {
                'total_tasks': 0,
                'ready_for_retry': 0,
                'retry_distribution': {},
                'failure_reasons': {}
            }
        
        current_time = datetime.now()
        ready_count = 0
        retry_distribution = {}
        failure_reasons = {}
        
        for task in self.retry_tasks.values():
            # 統計重試次數分布
            retry_count = task.retry_count
            retry_distribution[retry_count] = retry_distribution.get(retry_count, 0) + 1
            
            # 統計失敗原因
            reason = task.failure_reason
            failure_reasons[reason] = failure_reasons.get(reason, 0) + 1
            
            # 檢查是否準備重試
            try:
                next_retry = datetime.fromisoformat(task.next_retry_time)
                if current_time >= next_retry:
                    ready_count += 1
            except ValueError:
                continue
        
        return {
            'total_tasks': len(self.retry_tasks),
            'ready_for_retry': ready_count,
            'retry_distribution': retry_distribution,
            'failure_reasons': failure_reasons
        }
    
    def load_retry_tasks(self):
        """從文件載入重試任務"""
        try:
            if self.config_file.exists():
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                self.retry_tasks = {}
                for component_id, task_data in data.items():
                    try:
                        self.retry_tasks[component_id] = RetryTask.from_dict(task_data)
                    except Exception as e:
                        self.logger.warning(f"載入重試任務 {component_id} 失敗: {e}")
                        continue
                
                self.logger.info(f"載入了 {len(self.retry_tasks)} 個重試任務")
            else:
                self.logger.info("重試任務配置文件不存在，將創建新文件")
                
        except Exception as e:
            self.logger.error(f"載入重試任務失敗: {e}")
    
    def save_retry_tasks(self):
        """保存重試任務到文件"""
        try:
            # 確保目錄存在
            self.config_file.parent.mkdir(parents=True, exist_ok=True)
            
            # 轉換為字典格式
            data = {}
            for component_id, task in self.retry_tasks.items():
                data[component_id] = task.to_dict()
            
            # 保存到文件
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            
            self.logger.debug(f"保存了 {len(self.retry_tasks)} 個重試任務")
            
        except Exception as e:
            self.logger.error(f"保存重試任務失敗: {e}")


# 創建全局重試管理器實例
retry_manager = RetryManager()
