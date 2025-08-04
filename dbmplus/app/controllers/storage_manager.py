"""
存儲管理器
"""
import os
import shutil
import threading
from pathlib import Path
from typing import List, Tuple, Optional, Dict
from datetime import datetime, timedelta
from queue import Queue

from ..utils import get_logger, config
from ..models import db_manager
from ..utils.storage_monitor import StorageMonitor

logger = get_logger("storage_manager")

class StorageMoveManager:
    """存儲移動管理器"""
    
    def __init__(self):
        self.monitor = StorageMonitor()
        self.move_queue = Queue()
        self.active_moves = {}
        self.max_concurrent = config.get("storage_management.move_rules.max_concurrent_moves", 3)
        self.is_running = False
        
        # 定期歸檔相關
        self.scheduled_archive_enabled = config.get("storage_management.scheduled_archive.enabled", False)
        self.archive_scheduler = None
        self.last_scheduled_run = None
        
        # 加載歷史報告
        self.monitor.load_archive_reports()
        
    def safe_move_file(self, source: str, target: str) -> Tuple[bool, str]:
        """安全的跨硬碟檔案移動"""
        try:
            # 檢查源檔案
            if not os.path.exists(source):
                return False, "源檔案不存在"
            
            # 確保目標目錄存在
            target_dir = os.path.dirname(target)
            os.makedirs(target_dir, exist_ok=True)
            
            # 檢查目標硬碟空間
            target_usage = self.monitor.get_disk_usage(target_dir)
            if target_usage and target_usage['free_gb'] < (os.path.getsize(source) / (1024**3)):
                return False, "目標硬碟空間不足"
            
            # 先複製再刪除（更安全）
            logger.info(f"開始移動檔案: {source} -> {target}")
            shutil.copy2(source, target)
            
            # 驗證複製成功
            if os.path.exists(target) and os.path.getsize(source) == os.path.getsize(target):
                os.remove(source)  # 刪除源檔案
                logger.info(f"檔案移動成功: {source}")
                return True, "移動成功"
            else:
                # 複製失敗，清理目標檔案
                if os.path.exists(target):
                    os.remove(target)
                return False, "檔案複製驗證失敗"
                
        except Exception as e:
            logger.error(f"移動檔案失敗 {source}: {e}")
            return False, f"移動失敗: {str(e)}"
    
    def get_archive_path(self, component_id: str, lot_id: str, station: str, product: str, file_type: str = "org", filename: str = None) -> str:
        """生成歸檔路徑"""
        archive_base = config.get("storage_management.archive_storage.path", "E:/Database-PC")
        archive_structure = config.get("storage_management.archive_storage.structure", "{product}/org/{lot}/{station}/{component}")
        
        # 根據文件類型調整路徑結構
        if file_type == "roi":
            archive_structure = archive_structure.replace("/org/", "/roi/")
        elif file_type == "csv":
            archive_structure = archive_structure.replace("/org/", "/csv/")
        
        # 解析路徑模板
        path = archive_structure.format(
            product=product,
            lot=lot_id,
            station=station,
            component=component_id
        )
        
        # 構建完整路徑
        full_path = os.path.join(archive_base, path)
        
        # 如果提供了檔案名，則添加到路徑中
        if filename:
            full_path = os.path.join(full_path, filename)
        
        return full_path
    
    def find_old_files_by_type(self, file_type: str, min_age_days: int = 7) -> List[Tuple]:
        """查找指定類型的舊檔案 - 直接掃描文件系統"""
        old_files = []
        min_age = timedelta(days=min_age_days)
        cutoff_date = datetime.now() - min_age
        
        # 直接掃描文件系統而不是依賴數據庫
        base_path = Path(config.get("database.base_path", "D:/Database-PC"))
        
        if not base_path.exists():
            logger.warning(f"基礎路徑不存在: {base_path}")
            return old_files
        
        # 根據文件類型決定掃描目錄
        if file_type == "org":
            scan_dir = "org"
        elif file_type == "roi":
            scan_dir = "roi"
        elif file_type == "csv":
            scan_dir = "csv"
        else:
            logger.warning(f"不支持的文件類型: {file_type}")
            return old_files
        
        # 獲取檔案格式配置
        file_formats = config.get("storage_management.file_formats", {})
        file_format_config = file_formats.get(file_type, {})
        extensions = file_format_config.get("extensions", [".tif", ".tiff"])
        
        logger.debug(f"掃描 {file_type} 檔案，使用副檔名: {extensions}")
        
        try:
            # 掃描所有產品目錄
            for product_dir in base_path.iterdir():
                if not product_dir.is_dir():
                    continue
                    
                product_id = product_dir.name
                target_dir = product_dir / scan_dir
                
                if not target_dir.exists():
                    continue
                
                # 掃描批次目錄
                for lot_dir in target_dir.iterdir():
                    if not lot_dir.is_dir():
                        continue
                        
                    lot_id = lot_dir.name
                    
                    # 掃描站點目錄
                    for station_dir in lot_dir.iterdir():
                        if not station_dir.is_dir():
                            continue
                            
                        station = station_dir.name
                        
                        # 掃描組件目錄
                        for comp_dir in station_dir.iterdir():
                            if not comp_dir.is_dir():
                                continue
                                
                            component_id = comp_dir.name
                            
                            # 查找檔案 - 使用配置的副檔名
                            files = []
                            for ext in extensions:
                                files.extend(comp_dir.glob(f"*{ext}"))
                            
                            if files:
                                # 檢查檔案年齡
                                oldest_file = min(files, key=lambda f: f.stat().st_mtime)
                                oldest_time = datetime.fromtimestamp(oldest_file.stat().st_mtime)
                                
                                if oldest_time < cutoff_date:
                                    # 將該組件的所有檔案加入移動清單
                                    for file_path in files:
                                        old_files.append((
                                            str(file_path),
                                            component_id,
                                            lot_id,
                                            station,
                                            product_id,
                                            file_type
                                        ))
                                    
                                    logger.debug(f"找到舊檔案組件: {product_id}/{lot_id}/{station}/{component_id}, "
                                               f"檔案數量: {len(files)}, 最舊檔案: {oldest_time.strftime('%Y-%m-%d')}")
        
        except Exception as e:
            logger.error(f"掃描文件系統時發生錯誤: {e}")
        
        logger.info(f"掃描完成，找到 {len(old_files)} 個符合條件的檔案")
        return old_files
    
    def find_old_org_files(self, min_age_days: int = 7) -> List[Tuple]:
        """查找需要移動的舊org檔案（向後兼容）"""
        return self.find_old_files_by_type("org", min_age_days)
    
    def start_storage_management(self):
        """啟動存儲管理"""
        if self.is_running:
            return
        
        self.is_running = True
        logger.info("存儲管理器已啟動")
        
        # 啟動監控線程
        monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        monitor_thread.start()
        
        # 啟動定期歸檔
        if self.scheduled_archive_enabled:
            self._start_scheduled_archive()
    
    def stop_storage_management(self):
        """停止存儲管理"""
        self.is_running = False
        logger.info("存儲管理器已停止")
        
        # 停止定期歸檔線程
        if self.archive_scheduler and self.archive_scheduler.is_alive():
            # 等待線程自然結束（最多等待5秒）
            self.archive_scheduler.join(timeout=5)
            if self.archive_scheduler.is_alive():
                logger.warning("定期歸檔線程未能正常停止")
            else:
                logger.info("定期歸檔線程已停止")
    
    def _start_scheduled_archive(self):
        """啟動定期歸檔排程器"""
        try:
            import schedule
            import time
            
            # 獲取排程配置
            schedule_config = config.get("storage_management.scheduled_archive.schedule", {})
            scheduled_time = schedule_config.get("time", "02:00")
            scheduled_days = schedule_config.get("days", ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"])
            
            # 清空現有排程
            schedule.clear()
            
            # 設置排程
            for day in scheduled_days:
                if day.lower() in ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]:
                    getattr(schedule.every(), day.lower()).at(scheduled_time).do(self._run_scheduled_archive)
            
            logger.info(f"定期歸檔排程已設置: {scheduled_time} on {scheduled_days}")
            
            # 啟動排程器線程
            def run_scheduler():
                # 獲取排程器檢查間隔
                scheduler_interval = config.get("storage_management.monitoring.scheduler_check_interval_seconds", 60)
                error_retry_interval = config.get("storage_management.monitoring.error_retry_interval_seconds", 60)
                
                logger.info(f"定期歸檔排程器啟動，檢查間隔: {scheduler_interval}秒")
                
                while self.is_running:
                    try:
                        schedule.run_pending()
                        time.sleep(scheduler_interval)  # 使用配置的檢查間隔
                    except Exception as e:
                        logger.error(f"排程器錯誤: {e}")
                        time.sleep(error_retry_interval)  # 錯誤時使用配置的重試間隔
            
            self.archive_scheduler = threading.Thread(target=run_scheduler, daemon=True)
            self.archive_scheduler.start()
            
        except ImportError:
            logger.error("需要安裝schedule庫來支持定期歸檔功能: pip install schedule")
        except Exception as e:
            logger.error(f"啟動定期歸檔失敗: {e}")
    
    def _run_scheduled_archive(self):
        """執行定期歸檔"""
        if self.last_scheduled_run and (datetime.now() - self.last_scheduled_run).seconds < 3600:
            logger.info("跳過重複的定期歸檔執行")
            return
        
        self.last_scheduled_run = datetime.now()
        logger.info("開始執行定期歸檔")
        
        # 獲取歸檔規則
        archive_rules = config.get("storage_management.scheduled_archive.archive_rules", {})
        
        total_moved = 0
        total_size_gb = 0
        file_types_moved = {}
        errors = []
        
        for file_type, rule in archive_rules.items():
            if not rule.get("enabled", False):
                continue
            
            try:
                moved_count, moved_size_gb, errors_list = self._archive_files_by_type(
                    file_type, 
                    rule.get("min_age_days", 7),
                    rule.get("batch_size", 10)
                )
                
                total_moved += moved_count
                total_size_gb += moved_size_gb
                file_types_moved[file_type] = moved_count
                errors.extend(errors_list)
                
                logger.info(f"{file_type} 文件歸檔完成: 移動 {moved_count} 個文件，大小 {moved_size_gb:.2f}GB")
                
            except Exception as e:
                error_msg = f"{file_type} 歸檔失敗: {e}"
                logger.error(error_msg)
                errors.append(error_msg)
        
        # 生成報告
        report = {
            'type': 'scheduled_archive',
            'success': len(errors) == 0,
            'files_moved': total_moved,
            'size_moved_gb': round(total_size_gb, 2),
            'file_types': file_types_moved,
            'errors': errors,
            'timestamp': datetime.now().isoformat()
        }
        
        # 保存報告
        self.monitor.add_archive_report(report)
        
        logger.info(f"定期歸檔完成: 總共移動 {total_moved} 個文件，大小 {total_size_gb:.2f}GB")
    
    def _archive_files_by_type(self, file_type: str, min_age_days: int, batch_size: int) -> Tuple[int, float, List[str]]:
        """按類型歸檔文件 - batch_size 現在表示組件數量，不是文件數量"""
        old_files = self.find_old_files_by_type(file_type, min_age_days)
        
        # 按文件修改時間排序，最舊的優先
        old_files.sort(key=lambda x: os.path.getmtime(x[0]))
        
        # 按組件分組，確保同一個組件的所有文件一起處理
        component_groups = {}
        for source_path, component_id, lot_id, station, product, file_type in old_files:
            component_key = f"{component_id}_{lot_id}_{station}_{product}"
            if component_key not in component_groups:
                component_groups[component_key] = {
                    'component_id': component_id,
                    'lot_id': lot_id,
                    'station': station,
                    'product': product,
                    'files': []
                }
            component_groups[component_key]['files'].append((source_path, file_type))
        
        # 按組件的最舊文件時間排序
        sorted_components = sorted(
            component_groups.values(),
            key=lambda x: min(os.path.getmtime(f[0]) for f in x['files'])
        )
        
        moved_count = 0
        moved_size_gb = 0
        errors = []
        
        # 限制處理的組件數量
        for component_info in sorted_components[:batch_size]:
            component_id = component_info['component_id']
            lot_id = component_info['lot_id']
            station = component_info['station']
            product = component_info['product']
            files = component_info['files']
            
            try:
                # 移動該組件的所有文件
                component_moved_count = 0
                component_moved_size = 0
                component_errors = []
                
                for source_path, file_type in files:
                    # 獲取檔案名
                    filename = os.path.basename(source_path)
                    target_path = self.get_archive_path(component_id, lot_id, station, product, file_type, filename=filename)
                    
                    success, message = self.safe_move_file(source_path, target_path)
                    if success:
                        component_moved_count += 1
                        component_moved_size += os.path.getsize(target_path) / (1024**3)
                        logger.info(f"定期歸檔成功: {component_id} ({file_type}) - {filename}")
                    else:
                        component_errors.append(f"{file_type}: {message}")
                
                # 如果該組件的所有文件都移動成功，計入統計
                if component_errors:
                    errors.extend([f"{component_id}: {error}" for error in component_errors])
                else:
                    moved_count += component_moved_count
                    moved_size_gb += component_moved_size
                    logger.info(f"組件 {component_id} 歸檔完成: 移動 {component_moved_count} 個文件，大小 {component_moved_size:.2f}GB")
                    
            except Exception as e:
                error_msg = f"組件 {component_id} 歸檔失敗: {e}"
                errors.append(error_msg)
                logger.error(error_msg)
        
        return moved_count, moved_size_gb, errors
    
    def _monitor_loop(self):
        """監控循環"""
        # 獲取掃描頻率配置
        scan_interval = config.get("storage_management.monitoring.scan_interval_seconds", 300)  # 預設5分鐘
        error_retry_interval = config.get("storage_management.monitoring.error_retry_interval_seconds", 60)  # 預設1分鐘
        
        logger.info(f"存儲監控啟動，掃描間隔: {scan_interval}秒，錯誤重試間隔: {error_retry_interval}秒")
        
        while self.is_running:
            try:
                # 檢查存儲狀態
                status = self.monitor.check_storage_status()
                
                if status['needs_action']:
                    logger.info(f"檢測到存儲問題: {status['action_type']}")
                    self._handle_storage_action(status)
                
                # 使用配置的掃描間隔
                import time
                time.sleep(scan_interval)
                
            except Exception as e:
                logger.error(f"存儲監控循環錯誤: {e}")
                import time
                time.sleep(error_retry_interval)  # 錯誤時使用配置的重試間隔
    
    def _handle_storage_action(self, status: Dict):
        """處理存儲操作"""
        if status['action_type'] == 'critical':
            # 緊急模式：立即移動最舊的檔案
            self._emergency_move()
        elif status['action_type'] == 'warning':
            # 警告模式：移動較舊的檔案
            self._warning_move()
    
    def _emergency_move(self):
        """緊急移動：移動最舊的org檔案（按組件完整移動）"""
        logger.info("執行緊急移動操作")
        old_files = self.find_old_org_files(min_age_days=1)  # 1天以上
        
        logger.info(f"找到 {len(old_files)} 個檔案需要移動")
        
        # 按組件分組
        component_groups = {}
        for file_tuple in old_files:
            # 修復：正確解包6個值
            source_path, component_id, lot_id, station, product, file_type = file_tuple
            
            logger.debug(f"處理檔案: {component_id} - {os.path.basename(source_path)}")
            logger.debug(f"  路徑: {source_path}")
            logger.debug(f"  組件: {component_id}, 批次: {lot_id}, 站點: {station}, 產品: {product}")
            
            component_key = f"{component_id}_{lot_id}_{station}_{product}"
            if component_key not in component_groups:
                component_groups[component_key] = {
                    'component_id': component_id,
                    'lot_id': lot_id,
                    'station': station,
                    'product': product,
                    'files': []
                }
            component_groups[component_key]['files'].append(source_path)
        
        logger.info(f"分組後有 {len(component_groups)} 個組件")
        
        # 按組件的最舊文件時間排序
        sorted_components = sorted(
            component_groups.values(),
            key=lambda x: min(os.path.getmtime(f) for f in x['files'])
        )
        
        # 移動前10個最舊的組件（每個組件的所有文件）
        moved_count = 0
        for i, component_info in enumerate(sorted_components[:10]):
            component_id = component_info['component_id']
            lot_id = component_info['lot_id']
            station = component_info['station']
            product = component_info['product']
            files = component_info['files']
            
            logger.info(f"處理組件 {i+1}: {component_id} ({product}/{lot_id}/{station})")
            logger.info(f"  檔案數量: {len(files)}")
            
            component_moved = 0
            for source_path in files:
                # 獲取檔案名
                filename = os.path.basename(source_path)
                target_path = self.get_archive_path(component_id, lot_id, station, product, filename=filename)
                
                logger.info(f"  移動檔案: {filename}")
                logger.info(f"    源路徑: {source_path}")
                logger.info(f"    目標路徑: {target_path}")
                
                success, message = self.safe_move_file(source_path, target_path)
                if success:
                    component_moved += 1
                    logger.info(f"    結果: ✅ 成功")
                else:
                    logger.error(f"    結果: ❌ 失敗 - {message}")
            
            if component_moved > 0:
                moved_count += component_moved
                logger.info(f"組件 {component_id} 緊急移動完成: {component_moved} 個文件")
        
        logger.info(f"緊急移動完成，成功移動 {moved_count} 個檔案")
    
    def _warning_move(self):
        """警告移動：移動較舊的org檔案（按組件完整移動）"""
        logger.info("執行警告移動操作")
        old_files = self.find_old_org_files(min_age_days=7)  # 7天以上
        
        logger.info(f"找到 {len(old_files)} 個檔案需要移動")
        
        # 按組件分組
        component_groups = {}
        for file_tuple in old_files:
            # 修復：正確解包6個值
            source_path, component_id, lot_id, station, product, file_type = file_tuple
            
            logger.debug(f"處理檔案: {component_id} - {os.path.basename(source_path)}")
            logger.debug(f"  路徑: {source_path}")
            logger.debug(f"  組件: {component_id}, 批次: {lot_id}, 站點: {station}, 產品: {product}")
            
            component_key = f"{component_id}_{lot_id}_{station}_{product}"
            if component_key not in component_groups:
                component_groups[component_key] = {
                    'component_id': component_id,
                    'lot_id': lot_id,
                    'station': station,
                    'product': product,
                    'files': []
                }
            component_groups[component_key]['files'].append(source_path)
        
        logger.info(f"分組後有 {len(component_groups)} 個組件")
        
        # 按組件的最舊文件時間排序
        sorted_components = sorted(
            component_groups.values(),
            key=lambda x: min(os.path.getmtime(f) for f in x['files'])
        )
        
        # 移動前5個最舊的組件（每個組件的所有文件）
        moved_count = 0
        for i, component_info in enumerate(sorted_components[:5]):
            component_id = component_info['component_id']
            lot_id = component_info['lot_id']
            station = component_info['station']
            product = component_info['product']
            files = component_info['files']
            
            logger.info(f"處理組件 {i+1}: {component_id} ({product}/{lot_id}/{station})")
            logger.info(f"  檔案數量: {len(files)}")
            
            component_moved = 0
            for source_path in files:
                # 獲取檔案名
                filename = os.path.basename(source_path)
                target_path = self.get_archive_path(component_id, lot_id, station, product, filename=filename)
                
                logger.info(f"  移動檔案: {filename}")
                logger.info(f"    源路徑: {source_path}")
                logger.info(f"    目標路徑: {target_path}")
                
                success, message = self.safe_move_file(source_path, target_path)
                if success:
                    component_moved += 1
                    logger.info(f"    結果: ✅ 成功")
                else:
                    logger.error(f"    結果: ❌ 失敗 - {message}")
            
            if component_moved > 0:
                moved_count += component_moved
                logger.info(f"組件 {component_id} 警告移動完成: {component_moved} 個文件")
        
        logger.info(f"警告移動完成，成功移動 {moved_count} 個檔案")
    
    def get_archive_statistics(self, days: int = 30) -> Dict:
        """獲取歸檔統計信息"""
        return self.monitor.get_archive_statistics(days)
    
    def get_recent_archive_reports(self, days: int = 7) -> List[Dict]:
        """獲取最近的歸檔報告"""
        return self.monitor.get_archive_reports(days)

# 創建全局存儲管理器實例
storage_manager = StorageMoveManager() 