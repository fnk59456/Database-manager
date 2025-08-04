"""
存儲監控模組
"""
import os
import psutil
import json
from pathlib import Path
from typing import Dict, Optional, List
from datetime import datetime, timedelta
from . import get_logger

logger = get_logger("storage_monitor")

class StorageMonitor:
    """存儲監控器"""
    
    def __init__(self):
        self.local_path = "D:/Database-PC"
        self.archive_path = "E:/Database-PC"
        self.archive_reports = []
    
    def get_disk_usage(self, path: str) -> Optional[Dict]:
        """獲取指定路徑的硬碟使用情況"""
        try:
            usage = psutil.disk_usage(path)
            return {
                'total_gb': usage.total / (1024**3),
                'used_gb': usage.used / (1024**3),
                'free_gb': usage.free / (1024**3),
                'percent': usage.percent,
                'path': path
            }
        except Exception as e:
            logger.error(f"獲取硬碟使用情況失敗 {path}: {e}")
            return None
    
    def check_storage_status(self) -> Dict:
        """檢查存儲狀態"""
        local_usage = self.get_disk_usage(self.local_path)
        archive_usage = self.get_disk_usage(self.archive_path)
        
        status = {
            'local': local_usage,
            'archive': archive_usage,
            'needs_action': False,
            'action_type': None
        }
        
        if local_usage:
            # 從配置文件獲取閾值
            from ..utils import config
            warning_threshold = config.get("storage_management.local_storage.warning_threshold_percent", 70)
            critical_threshold = config.get("storage_management.local_storage.critical_threshold_percent", 85)
            
            if local_usage['percent'] >= critical_threshold:
                status['needs_action'] = True
                status['action_type'] = 'critical'
            elif local_usage['percent'] >= warning_threshold:
                status['needs_action'] = True
                status['action_type'] = 'warning'
        
        return status
    
    def get_storage_info(self) -> str:
        """獲取存儲信息字符串"""
        status = self.check_storage_status()
        info = []
        
        if status['local']:
            local = status['local']
            info.append(f"本地存儲: {local['percent']:.1f}% ({local['used_gb']:.1f}GB/{local['total_gb']:.1f}GB)")
        
        if status['archive']:
            archive = status['archive']
            info.append(f"歸檔存儲: {archive['percent']:.1f}% ({archive['used_gb']:.1f}GB/{archive['total_gb']:.1f}GB)")
        
        if status['needs_action']:
            info.append(f"⚠️ 需要{status['action_type']}級別操作")
        
        return " | ".join(info)
    
    def add_archive_report(self, report: Dict):
        """添加歸檔報告"""
        report['timestamp'] = datetime.now().isoformat()
        self.archive_reports.append(report)
        
        # 限制報告數量，保留最近100個
        if len(self.archive_reports) > 100:
            self.archive_reports = self.archive_reports[-100:]
        
        # 保存到文件
        self._save_archive_reports()
    
    def get_archive_reports(self, days: int = 7) -> List[Dict]:
        """獲取指定天數內的歸檔報告"""
        cutoff_date = datetime.now() - timedelta(days=days)
        recent_reports = []
        
        for report in self.archive_reports:
            report_time = datetime.fromisoformat(report['timestamp'])
            if report_time >= cutoff_date:
                recent_reports.append(report)
        
        return recent_reports
    
    def get_archive_statistics(self, days: int = 30) -> Dict:
        """獲取歸檔統計信息"""
        reports = self.get_archive_reports(days)
        
        total_files = 0
        total_size_gb = 0
        file_types = {}
        success_count = 0
        failed_count = 0
        
        for report in reports:
            if report.get('success', False):
                success_count += 1
                total_files += report.get('files_moved', 0)
                total_size_gb += report.get('size_moved_gb', 0)
                
                # 統計文件類型
                for file_type, count in report.get('file_types', {}).items():
                    file_types[file_type] = file_types.get(file_type, 0) + count
            else:
                failed_count += 1
        
        return {
            'period_days': days,
            'total_reports': len(reports),
            'success_count': success_count,
            'failed_count': failed_count,
            'total_files_moved': total_files,
            'total_size_moved_gb': round(total_size_gb, 2),
            'file_types': file_types,
            'success_rate': round(success_count / len(reports) * 100, 1) if reports else 0
        }
    
    def _save_archive_reports(self):
        """保存歸檔報告到文件"""
        try:
            from ..utils import config
            log_file = config.get("storage_management.scheduled_archive.reporting.log_file", "logs/archive_reports.log")
            
            # 確保日誌目錄存在
            log_dir = os.path.dirname(log_file)
            if log_dir and not os.path.exists(log_dir):
                os.makedirs(log_dir, exist_ok=True)
            
            # 保存報告
            with open(log_file, 'w', encoding='utf-8') as f:
                json.dump(self.archive_reports, f, ensure_ascii=False, indent=2)
                
        except Exception as e:
            logger.error(f"保存歸檔報告失敗: {e}")
    
    def load_archive_reports(self):
        """從文件加載歸檔報告"""
        try:
            from ..utils import config
            log_file = config.get("storage_management.scheduled_archive.reporting.log_file", "logs/archive_reports.log")
            
            if os.path.exists(log_file):
                with open(log_file, 'r', encoding='utf-8') as f:
                    self.archive_reports = json.load(f)
                    
        except Exception as e:
            logger.error(f"加載歸檔報告失敗: {e}")
            self.archive_reports = [] 