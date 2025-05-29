"""
在線監控模組，處理CSV檔案的即時監控和處理
"""
import os
import time
import hashlib
from pathlib import Path
from datetime import datetime
from queue import Queue, Empty
from threading import Lock
from typing import Dict, List, Optional, Tuple, Any, Set

from PySide6.QtCore import QThread, Signal, QObject, QTimer

from ..utils import (
    get_logger, config, ensure_directory, 
    load_csv, extract_component_from_filename,
    AOI_FILENAME_PATTERN
)
from ..models import db_manager, ComponentInfo
from ..controllers.data_processor import data_processor

logger = get_logger("online_monitor")


class ProcessingLog:
    """處理日誌記錄"""
    def __init__(self, 
                 product_id: str,
                 lot_id: str, 
                 station: str, 
                 component_id: str,
                 file_path: str):
        self.timestamp = datetime.now()
        self.product_id = product_id
        self.lot_id = lot_id  # 內部批次ID
        self.original_lot_id = None  # 顯示用批次ID
        self.station = station
        self.component_id = component_id
        self.file_path = file_path
        self.steps = []  # 處理步驟記錄
        self.status = "pending"  # pending, processing, completed, failed
        self.message = ""
        self.duration = None  # 處理耗時
        
        # 獲取顯示用批次ID
        lot_obj = db_manager.get_lot(lot_id)
        if lot_obj:
            self.original_lot_id = lot_obj.original_lot_id
        else:
            self.original_lot_id = lot_id
    
    def add_step(self, step_name: str, status: str, message: str = ""):
        """添加處理步驟日誌"""
        self.steps.append({
            "timestamp": datetime.now(),
            "step": step_name,
            "status": status,
            "message": message
        })
    
    def start_processing(self):
        """標記為處理中"""
        self.status = "processing"
        self.start_time = datetime.now()
    
    def complete(self, message: str = ""):
        """標記為完成"""
        self.status = "completed"
        self.message = message
        self.end_time = datetime.now()
        self.duration = (self.end_time - self.start_time).total_seconds()
    
    def fail(self, message: str):
        """標記為失敗"""
        self.status = "failed"
        self.message = message
        self.end_time = datetime.now()
        self.duration = (self.end_time - self.start_time).total_seconds()
    
    def to_dict(self) -> Dict[str, Any]:
        """轉換為字典"""
        return {
            "timestamp": self.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
            "product_id": self.product_id,
            "lot_id": self.lot_id,
            "display_lot": self.original_lot_id,
            "station": self.station,
            "component_id": self.component_id,
            "status": self.status,
            "message": self.message,
            "duration": self.duration,
            "steps": self.steps
        }
    
    def get_summary(self) -> Dict[str, Any]:
        """獲取日誌摘要（用於顯示）"""
        return {
            "timestamp": self.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
            "product_id": self.product_id,
            "lot_id": self.original_lot_id,  # 使用顯示用批次ID
            "station": self.station,
            "component_id": self.component_id,
            "status": self.status,
            "message": self.message,
            "duration": f"{self.duration:.2f}s" if self.duration else "-"
        }


class FileWatcher(QThread):
    """檔案監控執行緒，監控目錄中的新CSV檔案"""
    file_found = Signal(str, str, str, str)  # 產品ID, 批次ID, 站點, 檔案路徑
    
    def __init__(self, scan_interval: int = None, rescan_interval: int = None):
        """
        初始化檔案監控器
        
        Args:
            scan_interval: 掃描間隔（秒），如果為None則從設定讀取
            rescan_interval: 重新掃描資料庫間隔（秒），如果為None則從設定讀取
        """
        super().__init__()
        # 從設定檔讀取掃描間隔，如果未設定則使用默認值
        self.scan_interval = scan_interval if scan_interval is not None else config.get("monitoring.scan_interval", 5)
        self.rescan_interval = rescan_interval if rescan_interval is not None else config.get("monitoring.rescan_interval", 30)
        
        logger.info(f"檔案監控已設置：掃描間隔={self.scan_interval}秒，重新掃描間隔={self.rescan_interval}秒")
        
        self.running = False
        self.monitored_dirs = []  # 監控的目錄列表
        self.processed_files = set()  # 已處理檔案集合
        self.base_path = Path(config.get("database.base_path", "D:/Database-PC"))
        self.last_rescan_time = 0  # 上次重新掃描時間
    
    def stop(self):
        """停止監控"""
        self.running = False
    
    def run(self):
        """執行監控"""
        self.running = True
        logger.info("檔案監控已啟動")
        
        # 初始掃描
        self._rescan_database()
        
        # 設置初始的last_rescan_time
        self.last_rescan_time = time.time()
        last_config_check = time.time()  # 上次檢查配置的時間
        config_check_interval = 60  # 每60秒檢查一次配置更新
        
        while self.running:
            try:
                # 檢查是否需要更新配置設置
                current_time = time.time()
                if current_time - last_config_check >= config_check_interval:
                    # 從配置中重新讀取掃描間隔設置
                    new_scan_interval = config.get("monitoring.scan_interval", 5)
                    new_rescan_interval = config.get("monitoring.rescan_interval", 30)
                    
                    # 如果設置已更改，則更新並記錄
                    if new_scan_interval != self.scan_interval or new_rescan_interval != self.rescan_interval:
                        logger.info(f"檢測到掃描設置變更: 掃描間隔 {self.scan_interval}→{new_scan_interval}秒, "
                                   f"重新掃描間隔 {self.rescan_interval}→{new_rescan_interval}秒")
                        self.scan_interval = new_scan_interval
                        self.rescan_interval = new_rescan_interval
                    
                    last_config_check = current_time
                
                # 檢查是否需要重新掃描資料庫
                elapsed_time = current_time - self.last_rescan_time
                
                if elapsed_time >= self.rescan_interval:
                    #logger.info(f"執行定期資料庫重新掃描...（距上次掃描: {elapsed_time:.1f}秒）")
                    self._rescan_database()
                    self.last_rescan_time = time.time()  # 更新為當前時間
                else:
                    # 常規掃描已監控目錄
                    self._scan_all_products()
                
                # 等待指定間隔
                for _ in range(self.scan_interval):
                    if not self.running:
                        break
                    time.sleep(1)
            except Exception as e:
                logger.error(f"檔案監控過程中發生錯誤: {e}")
                time.sleep(5)  # 發生錯誤後等待5秒再重試
    
    def _rescan_database(self):
        """重新掃描資料庫並更新監控目錄"""
        try:
            # 嘗試使用不同方式調用scan_database，處理可能不接受force參數的情況
            try:
                # 首先嘗試使用force參數
                db_manager.scan_database(force=True)
            except TypeError as e:
                # 如果發生TypeError（可能是因為不接受force參數），則不使用參數調用
                logger.warning(f"調用scan_database時發生參數錯誤，嘗試不使用force參數: {e}")
                db_manager.scan_database()
            
            # 掃描所有產品
            self._scan_all_products()
            logger.info("資料庫重新掃描完成")
        except Exception as e:
            logger.error(f"重新掃描資料庫時發生錯誤: {e}")
            
    def _scan_all_products(self):
        """掃描所有產品目錄"""
        # 獲取所有產品
        products = db_manager.get_products()
        
        for product in products:
            product_id = product.product_id
            product_path = self.base_path / product_id
            
            # 檢查processed_csv目錄
            processed_csv_dir = product_path / "processed_csv"
            if not processed_csv_dir.exists():
                continue
            
            # 獲取產品下的所有批次
            lots = db_manager.get_lots_by_product(product_id)
            
            for lot in lots:
                lot_id = lot.lot_id
                original_lot_id = lot.original_lot_id
                
                # 獲取批次下的所有站點
                for station in lot.stations:
                    # 構建監控目錄路徑
                    monitor_dir = processed_csv_dir / original_lot_id / station
                    if not monitor_dir.exists():
                        continue
                    
                    # 掃描目錄中的檔案
                    self._scan_directory(product_id, lot_id, station, monitor_dir)
    
    def _scan_directory(self, product_id: str, lot_id: str, station: str, directory: Path):
        """掃描單個目錄的檔案"""
        try:
            for file_path in directory.glob("*.csv"):
                # 檢查檔案名是否符合AOI原始格式
                if not AOI_FILENAME_PATTERN.match(file_path.name):
                    continue
                
                # 創建檔案唯一標識
                file_id = self._get_file_id(file_path)
                
                # 檢查是否已處理
                if file_id in self.processed_files:
                    continue
                
                # 添加到已處理集合
                self.processed_files.add(file_id)
                
                # 發射發現檔案信號
                self.file_found.emit(product_id, lot_id, station, str(file_path))
                logger.debug(f"發現新檔案: {file_path}")
        except Exception as e:
            logger.error(f"掃描目錄 {directory} 時發生錯誤: {e}")
    
    def _get_file_id(self, file_path: Path) -> str:
        """獲取檔案的唯一標識（路徑+大小+修改時間）"""
        stats = file_path.stat()
        file_id = f"{file_path}_{stats.st_size}_{stats.st_mtime}"
        return hashlib.md5(file_id.encode()).hexdigest()


class OnlineProcessManager(QObject):
    """在線處理管理器，管理檔案的處理佇列和狀態"""
    log_updated = Signal(object)  # 發射日誌更新信號
    processing_status_changed = Signal(str, int, int)  # 狀態, 佇列大小, 已處理數
    
    def __init__(self, max_concurrent_tasks: int = 2):
        """
        初始化在線處理管理器
        
        Args:
            max_concurrent_tasks: 最大並行任務數
        """
        super().__init__()
        self.processing_queue = Queue()  # 處理佇列
        self.processing_logs = []  # 處理日誌列表
        self.file_watcher = FileWatcher()  # 檔案監控器（使用配置中的設置）
        self.max_concurrent_tasks = max_concurrent_tasks
        self.current_tasks = 0
        self.is_running = False
        self.processed_count = 0
        self.failed_count = 0
        
        # 連接檔案發現信號
        self.file_watcher.file_found.connect(self.enqueue_file)
        
        # 創建處理定時器
        self.process_timer = QTimer(self)
        self.process_timer.timeout.connect(self._process_next)
        
        # 創建數據處理器任務完成信號連接
        data_processor.signaler.task_completed.connect(self._on_task_completed)
        
        # 任務映射表 - 追蹤任務ID到日誌物件的映射
        self.task_map = {}
        
        # 創建鎖，保護共享資源
        self.lock = Lock()
    
    def start(self):
        """啟動在線處理"""
        if self.is_running:
            return
        
        self.is_running = True
        self.file_watcher.start()  # 啟動檔案監控
        self.process_timer.start(1000)  # 每秒檢查一次佇列
        self.processing_status_changed.emit("running", 0, self.processed_count)
        logger.info("在線處理已啟動")
    
    def stop(self):
        """停止在線處理"""
        if not self.is_running:
            return
        
        self.is_running = False
        self.file_watcher.stop()  # 停止檔案監控
        self.process_timer.stop()  # 停止處理定時器
        self.processing_status_changed.emit("stopped", self.processing_queue.qsize(), self.processed_count)
        logger.info("在線處理已停止")
    
    def enqueue_file(self, product_id: str, lot_id: str, station: str, file_path: str):
        """將檔案加入處理佇列"""
        if not self.is_running:
            return
        
        # 從檔案名提取組件ID
        component_id = extract_component_from_filename(Path(file_path).name)
        if not component_id:
            logger.warning(f"無法從檔案名提取組件ID: {file_path}")
            return
        
        # 檢查批次是否存在，不存在則創建
        lot = db_manager.get_lot(lot_id)
        if not lot:
            logger.warning(f"找不到批次 {lot_id}，可能需要重新掃描數據庫")
            # 在處理佇列前，不主動創建批次，以避免不必要的數據庫污染
            return
            
        # 檢查組件是否已存在於數據庫中
        existing_component = db_manager.get_component(lot_id, station, component_id)
        if not existing_component:
            # 創建新組件並添加到數據庫
            logger.info(f"創建新組件: {component_id} (批次: {lot_id}, 站點: {station})")
            new_component = ComponentInfo(
                component_id=component_id,
                lot_id=lot_id,
                station=station,
                csv_path=file_path
            )
            if not db_manager.add_component(new_component):
                logger.error(f"添加組件到數據庫失敗: {component_id}")
                return
        else:
            # 更新現有組件的CSV路徑
            if existing_component.csv_path != file_path:
                existing_component.csv_path = file_path
                db_manager.update_component(existing_component)
        
        # 創建處理日誌
        log = ProcessingLog(product_id, lot_id, station, component_id, file_path)
        
        # 將檔案加入佇列
        self.processing_queue.put(log)
        self.processing_logs.append(log)
        
        # 更新狀態
        self.log_updated.emit(log)
        self.processing_status_changed.emit("running", self.processing_queue.qsize(), self.processed_count)
        
        logger.info(f"檔案已加入佇列: {file_path}")
    
    def _process_next(self):
        """處理佇列中的下一個檔案"""
        # 如果不在運行狀態或已達到最大並行任務數，則不處理
        if not self.is_running or self.current_tasks >= self.max_concurrent_tasks:
            return
        
        # 嘗試從佇列獲取日誌
        try:
            log = self.processing_queue.get_nowait()
        except Empty:
            return
        
        # 更新日誌狀態
        log.start_processing()
        log.add_step("開始處理", "info", "檔案已開始處理")
        self.log_updated.emit(log)
        
        # 增加當前任務計數
        with self.lock:
            self.current_tasks += 1
        
        # 獲取組件(應該已經在enqueue_file階段創建)
        component = db_manager.get_component(log.lot_id, log.station, log.component_id)
        if not component:
            # 極少數情況下可能發生：組件在入佇後被刪除
            logger.error(f"無法找到組件: {log.component_id} (批次: {log.lot_id}, 站點: {log.station})")
            log.fail("無法找到組件")
            self.log_updated.emit(log)
            with self.lock:
                self.current_tasks -= 1
                self.failed_count += 1
            return
        
        # 創建處理任務
        task_id = data_processor.create_task(
            "basemap",
            log.product_id,
            log.lot_id,
            log.station,
            log.component_id
        )
        
        # 記錄任務與日誌的映射
        self.task_map[task_id] = log
        
        # 添加步驟日誌
        log.add_step("創建任務", "info", f"已創建處理任務，ID: {task_id}")
        self.log_updated.emit(log)
    
    def _on_task_completed(self, task_id: str, success: bool, message: str):
        """處理任務完成回調"""
        # 檢查是否是我們的任務
        if task_id not in self.task_map:
            return
        
        # 獲取對應的日誌
        log = self.task_map[task_id]
        
        # 移除任務映射
        del self.task_map[task_id]
        
        # 減少當前任務計數
        with self.lock:
            self.current_tasks -= 1
            if success:
                self.processed_count += 1
            else:
                self.failed_count += 1
        
        # 更新日誌狀態
        if success:
            log.complete(f"處理成功: {message}")
            log.add_step("處理完成", "success", message)
        else:
            log.fail(f"處理失敗: {message}")
            log.add_step("處理失敗", "error", message)
        
        # 發送日誌更新信號
        self.log_updated.emit(log)
        
        # 更新處理狀態
        self.processing_status_changed.emit(
            "running" if self.is_running else "stopped",
            self.processing_queue.qsize(),
            self.processed_count
        )
    
    def clear_logs(self):
        """清空日誌"""
        self.processing_logs = []
        self.log_updated.emit(None)  # 發送空日誌通知界面更新
        logger.info("處理日誌已清空")
    
    def get_logs(self) -> List[Dict[str, Any]]:
        """獲取所有日誌摘要"""
        return [log.get_summary() for log in self.processing_logs]


# 創建全局實例
online_manager = OnlineProcessManager() 