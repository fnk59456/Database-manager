"""
數據處理控制器模塊，負責執行數據處理和圖像生成任務
"""
import os
import json
import uuid
import pandas as pd
import threading
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any, Callable
import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from PySide6.QtCore import QObject, Signal, QMetaObject, Qt, QTimer
import shutil
from queue import Queue, Empty
from datetime import timedelta

from ..utils import (
    get_logger, config, ensure_directory, 
    load_csv, find_header_row, save_df_to_csv,
    convert_to_binary, flip_data, apply_mask,
    calculate_loss_points, plot_basemap, 
    plot_lossmap, plot_fpy_map, plot_fpy_bar,
    check_csv_alignment, remove_header_and_rename,
    AOI_FILENAME_PATTERN, PROCESSED_FILENAME_PATTERN,
    extract_component_from_filename
)
from ..models import (
    db_manager, ComponentInfo, ProcessingTask
)

logger = get_logger("data_processor")


class ProcessingTask:
    """處理任務，用於追蹤長時間運行的處理操作"""
    
    def __init__(self, task_id: str, task_type: str, product_id: str, lot_id: str, station: str = None, component_id: str = None):
        self.task_id = task_id
        self.task_type = task_type
        self.product_id = product_id
        self.lot_id = lot_id
        self.station = station
        self.component_id = component_id
        self.status = "pending"  # pending, running, completed, failed
        self.message = ""
        self.created_at = datetime.datetime.now()
        self.completed_at = None
    
    def start(self):
        """標記任務為運行中"""
        self.status = "running"
    
    def complete(self, message: str = ""):
        """標記任務為已完成"""
        self.status = "completed"
        self.message = message
        self.completed_at = datetime.datetime.now()
    
    def fail(self, message: str = ""):
        """標記任務為失敗"""
        self.status = "failed"
        self.message = message
        self.completed_at = datetime.datetime.now()
    
    def to_dict(self) -> Dict[str, Any]:
        """轉換為字典"""
        return {
            "task_id": self.task_id,
            "task_type": self.task_type,
            "product_id": self.product_id,
            "lot_id": self.lot_id,
            "station": self.station,
            "component_id": self.component_id,
            "status": self.status,
            "message": self.message,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None
        }


# 任務回調信號器類
class TaskSignaler(QObject):
    """用於在線程間安全傳遞信號的類"""
    task_completed = Signal(str, bool, str)


class DelayedMoveManager(QObject):
    """延遲移動管理器，處理大量檔案的延遲移動"""
    
    def __init__(self):
        super().__init__()
        self.move_queue = Queue()
        self.scheduler = QTimer()
        self.scheduler.setSingleShot(True)  # 設置為單次觸發
        self.scheduler.timeout.connect(self.process_delayed_moves)
        self.is_running = False
        logger.info("延遲移動管理器已初始化")
        
    def add_to_delayed_queue(self, component_id: str, lot_id: str, station: str, 
                            source_product: str, target_product: str):
        """添加到延遲移動隊列"""
        self.move_queue.put({
            'component_id': component_id,
            'lot_id': lot_id,
            'station': station,
            'source_product': source_product,
            'target_product': target_product,
            'timestamp': datetime.datetime.now()
        })
        logger.info(f"已添加到延遲移動隊列: {component_id}")
    
    def start_scheduler(self, interval_hours: int = 24):
        """啟動定時器（根據配置的時間執行）"""
        if self.is_running:
            logger.info("延遲移動調度器已在運行中")
            return
            
        self.is_running = True
        
        # 從配置中讀取時間設定
        schedule_config = config.get("auto_move.delayed.schedule", {})
        scheduled_time = schedule_config.get("time", "02:00")  # 默認凌晨2點
        scheduled_days = schedule_config.get("days", ["monday", "tuesday", "wednesday", "thursday", "friday"])
        
        logger.info(f"延遲移動配置 - 時間: {scheduled_time}, 天數: {scheduled_days}")
        
        # 解析時間
        try:
            hour, minute = map(int, scheduled_time.split(":"))
            logger.info(f"解析時間成功 - 小時: {hour}, 分鐘: {minute}")
        except ValueError:
            logger.error(f"無效的時間格式: {scheduled_time}，使用默認時間 02:00")
            hour, minute = 2, 0
        
        # 計算到下次執行時間的毫秒數
        now = datetime.datetime.now()
        next_run = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        
        # 如果今天的時間已過，設定為明天
        if next_run <= now:
            next_run += timedelta(days=1)
            logger.info(f"今天的時間已過，設定為明天執行")
        
        delay_ms = (next_run - now).total_seconds() * 1000
        logger.info(f"延遲時間: {delay_ms} 毫秒 ({delay_ms/1000/60:.1f} 分鐘)")
        
        self.scheduler.start(delay_ms)
        logger.info(f"延遲移動管理器已啟動，下次執行時間: {next_run} (配置時間: {scheduled_time})")
    
    def stop_scheduler(self):
        """停止定時器"""
        self.is_running = False
        self.scheduler.stop()
        logger.info("延遲移動管理器已停止")
    
    def process_delayed_moves(self):
        """處理延遲移動隊列"""
        logger.info("延遲移動管理器開始處理隊列")
        
        if self.move_queue.empty():
            logger.info("延遲移動隊列為空")
            # 即使隊列為空，也要重新啟動調度器
            self.start_scheduler()
            return
        
        logger.info("開始處理延遲移動隊列")
        
        # 獲取目標產品
        target_product = config.get("auto_move.target_product", "i-Pixel")
        
        # 收集所有需要移動的組件
        components_to_move = []
        queue_size = self.move_queue.qsize()
        logger.info(f"延遲移動隊列中有 {queue_size} 個項目")
        
        while not self.move_queue.empty():
            try:
                item = self.move_queue.get_nowait()
                components_to_move.append((
                    item['component_id'],
                    item['lot_id'],
                    item['station'],
                    item['source_product']
                ))
            except Empty:
                break
        
        logger.info(f"收集到 {len(components_to_move)} 個組件需要移動")
        
        if components_to_move:
            # 獲取延遲移動的檔案類型
            delayed_file_types = config.get("auto_move.delayed.file_types", ["org", "roi"])
            logger.info(f"延遲移動檔案類型: {delayed_file_types}")
            
            # 創建批量移動任務
            task_id = data_processor.create_task(
                "batch_move_files",
                target_product,  # 使用配置的目標產品
                components_to_move[0][1],  # lot_id
                components_to_move[0][2],  # station
                component_id=components_to_move[0][0],  # component_id
                batch_move_params={
                    'components_data': components_to_move,
                    'target_product': target_product,  # 使用配置的目標產品
                    'file_types': delayed_file_types  # 使用配置的檔案類型
                }
            )
            logger.info(f"已創建延遲移動任務: {task_id}")
        else:
            logger.info("沒有組件需要移動")
        
        # 重新啟動定時器
        logger.info("重新啟動延遲移動調度器")
        self.is_running = False  # 重置狀態
        self.start_scheduler()


class DataProcessor:
    """數據處理控制器，提供數據處理與圖像生成功能"""
    
    _instance = None  # 單例實例
    
    def __new__(cls):
        """實現單例模式"""
        if cls._instance is None:
            cls._instance = super(DataProcessor, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        """初始化數據處理控制器"""
        if self._initialized:
            return
            
        self._initialized = True
        self.base_path = Path(config.get("database.base_path", "D:/Database-PC"))
        self.active_tasks = {}  # 追蹤活動任務
        self.task_results = {}  # 保存任務結果
        self.task_callbacks = {}  # 任務完成回調函數
        
        # 讀取處理配置
        self.station_order = config.get("processing.station_order", [])
        self.flip_config = config.get("processing.flip_config", {})
        self.station_recipes = config.get("processing.station_recipe", {})
        self.station_logic = config.get("processing.station_logic", {})
        
        # 創建信號器對象，用於線程安全的回調
        self.signaler = TaskSignaler()
        
        # 注意：延遲移動管理器現在在主視窗中初始化，以確保在正確的線程中運行
    
    def _load_mask_rules(self, station):
        """載入指定站點的遮罩規則"""
        mask_path = Path("config/masks") / f"{station}.json"
        if not mask_path.exists():
            logger.warning(f"找不到站點 {station} 的遮罩規則檔案")
            return []
            
        try:
            with open(mask_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"載入遮罩規則失敗: {e}")
            return []
    
    def process_csv_header(self, file_path, skiprows=20):
        """處理CSV檔案標頭，刪除標頭並重新格式化"""
        return remove_header_and_rename(file_path)
    
    def generate_basemap(self, component: ComponentInfo) -> Tuple[bool, str]:
        """
        生成Basemap圖像

        流程根據原始databasemanager:
        # Step 1: 讀取config參數(configs/formulas、masks、plots、sample_rule.json等等)
        # Step 2: 原始 CSV 偏移確認 (rawdata_check.py)
        # Step 3: 去表頭 + rename(head_remove.py)
        # Step 4: 做 Basemap(basemap_runner.py)
        """
        try:
            if not component.csv_path or not Path(component.csv_path).exists():
                return False, "找不到CSV檔案"
            
            csv_filename = Path(component.csv_path).name
            
            # 如果是原始格式 {device}_{component}_{time}.csv，執行 step1~3
            if AOI_FILENAME_PATTERN.match(csv_filename):
                logger.info(f"檔案 {csv_filename} 是原始格式，執行 step1~3")
                
                # 取得產品ID，用於設定正確的路徑
                product_id = db_manager.get_lot(component.lot_id).product_id
                
                # Step 1: 讀取config參數
                logger.info(f"Step 1: 讀取元件 {component.component_id} 的config參數")
                sample_rules_path = Path("config/sample_rules.json")
                if not sample_rules_path.exists():
                    return False, "找不到sample_rules.json配置檔案"
                with open(sample_rules_path, 'r', encoding='utf-8') as f:
                    sample_rules = json.load(f)
                station = component.station
                rule = sample_rules.get(station, {})
                if not rule:
                    return False, f"在sample_rules中找不到站點 {station} 的配置"
                formula_path = Path(rule.get("formulas", ""))
                mask_path = Path(rule.get("mask", ""))
                plot_path = Path(rule.get("plot", ""))
                if not formula_path.exists():
                    return False, f"找不到formula配置檔案: {formula_path}"
                if not mask_path.exists():
                    logger.warning(f"找不到mask配置檔案: {mask_path}")
                if not plot_path.exists():
                    return False, f"找不到plot配置檔案: {plot_path}"

                # Step 2: 原始 CSV 偏移確認
                logger.info(f"Step 2: 執行 {component.component_id} 的原始CSV偏移確認")
                align_config_path = Path("config/align_key_config.json")
                if not align_config_path.exists():
                    return False, "找不到align_key_config.json配置檔案"
                with open(align_config_path, 'r', encoding='utf-8') as f:
                    align_config = json.load(f)
                recipe = self.station_recipes.get(station, "Sapphire A")
                status, detail = check_csv_alignment(component.csv_path, recipe, align_config)

                if status == "fail":
                    return False, f"CSV檔案偏移錯誤: {detail}"

                # Step 3: 去表頭 + rename，並存儲到csv目錄
                logger.info(f"Step 3: 處理 {component.component_id} 的CSV標頭")
                
                # 獲取原始批次ID，用於構建路徑
                lot_obj = db_manager.get_lot(component.lot_id)
                product_id = lot_obj.product_id
                original_lot_id = lot_obj.original_lot_id
                
                # 設置csv目錄路徑，使用原始批次ID
                csv_dir = config.get_path(
                    "database.structure.csv", 
                    product=product_id, 
                    lot=original_lot_id, 
                    station=component.station
                )
                
                # 確保目錄存在
                ensure_directory(Path(csv_dir))
                
                # 提取component_id用於重命名
                component_id = extract_component_from_filename(Path(component.csv_path).name)
                if not component_id:
                    component_id = component.component_id
                
                # 設置處理後文件的目標路徑
                target_csv_path = os.path.join(csv_dir, f"{component_id}.csv")
                
                # 執行去表頭和重命名，並保存到csv目錄
                success, result = remove_header_and_rename(component.csv_path, output_path=target_csv_path)
                if not success:
                    return False, f"處理CSV標頭失敗: {result}"
                
                # 更新組件路徑，保存原始路徑
                original_csv_path = component.csv_path
                component.original_csv_path = original_csv_path  # 保存原始路徑
                component.csv_path = result  # 更新為處理後的路徑
                db_manager.update_component(component)
                
                # 更新檔名以便後續檢查
                csv_filename = Path(component.csv_path).name
            
            # 確認檔案是否符合處理後格式，如果不符合則報錯
            if not PROCESSED_FILENAME_PATTERN.match(csv_filename):
                return False, f"CSV檔案 {csv_filename} 格式不正確，無法生成Basemap"

            # Step 4: 做 Basemap
            logger.info(f"Step 4: 為 {component.component_id} 生成Basemap")
            
            # 讀取 config 相關內容（如果 step1 未執行）
            if not 'sample_rules' in locals():
                sample_rules_path = Path("config/sample_rules.json")
                if not sample_rules_path.exists():
                    return False, "找不到sample_rules.json配置檔案"
                with open(sample_rules_path, 'r', encoding='utf-8') as f:
                    sample_rules = json.load(f)
                station = component.station
                rule = sample_rules.get(station, {})
                if not rule:
                    return False, f"在sample_rules中找不到站點 {station} 的配置"
                formula_path = Path(rule.get("formulas", ""))
                mask_path = Path(rule.get("mask", ""))
                plot_path = Path(rule.get("plot", ""))
            
            # 讀取 CSV 資料
            df = load_csv(component.csv_path)
            if df is None:
                return False, "讀取處理後的CSV失敗"
            
            # 應用遮罩
            mask_rules = []
            if mask_path.exists():
                try:
                    with open(mask_path, 'r', encoding='utf-8') as f:
                        mask_rules = json.load(f)
                except Exception as e:
                    mask_rules = []
            if mask_rules:
                df = apply_mask(df, mask_rules)
            
            # 執行翻轉
            if self.flip_config.get(component.station, False):
                df = flip_data(df)
            
            # 設置輸出路徑，按照設定格式存儲
            lot_obj = db_manager.get_lot(component.lot_id)
            product_id = lot_obj.product_id
            original_lot_id = lot_obj.original_lot_id
            
            # 使用配置獲取正確的map目錄路徑
            map_dir = config.get_path(
                "database.structure.map",
                product=product_id,
                lot=original_lot_id
            )
            
            # 確保站點子目錄存在
            output_dir = Path(map_dir) / component.station
            ensure_directory(output_dir)
            
            # 設置輸出文件名
            component_name = Path(component.csv_path).stem
            output_path = output_dir / f"{component_name}.png"
            
            # 讀取繪圖配置
            try:
                with open(plot_path, 'r', encoding='utf-8') as f:
                    plot_config = json.load(f)
            except Exception as e:
                return False, f"讀取繪圖配置失敗: {str(e)}"
            
            # 繪製 Basemap
            if plot_basemap(df, str(output_path), plot_config=plot_config):
                component.basemap_path = str(output_path)
                db_manager.update_component(component)
                
                # 新增：自動移動即時檔案（CSV 和 Map）
                self._auto_move_immediate_files(component)
                
                logger.info(f"成功生成Basemap: {output_path}")
                return True, str(output_path)
            else:
                return False, "生成Basemap失敗"
                
        except Exception as e:
            logger.error(f"生成Basemap時發生錯誤: {e}")
            return False, f"生成失敗: {str(e)}"
    
    def generate_lossmap(self, product_id: str, lot_id: str, station: str) -> Tuple[bool, str]:
        """
        生成指定站點的所有元件的Lossmap
        
        Args:
            product_id: 產品ID
            lot_id: 批次ID
            station: 站點名稱
            
        Returns:
            Tuple[bool, str]: (成功狀態, 訊息)
        """
        try:
            # 確認站點可以生成Lossmap
            if station == self.station_order[0]:
                return False, f"{station} 是第一站，無法生成Lossmap"
                
            # 獲取前站索引
            station_idx = self.station_order.index(station)
            prev_station = self.station_order[station_idx - 1]
            
            # 獲取站點所有元件
            components = db_manager.get_components_by_lot_station(lot_id, station)
            success_count = 0
            fail_count = 0
            
            # 獲取原始批次ID，用於構建路徑
            lot_obj = db_manager.get_lot(lot_id)
            original_lot_id = lot_obj.original_lot_id
            
            for component in components:
                # 獲取對應的前站元件
                prev_component = db_manager.get_component(lot_id, prev_station, component.component_id)
                if not prev_component:
                    logger.warning(f"找不到前站({prev_station})對應的元件: {component.component_id}")
                    fail_count += 1
                    continue
                    
                # 檢查CSV是否存在
                if not component.csv_path or not Path(component.csv_path).exists():
                    logger.warning(f"找不到當前站CSV: {component.csv_path}")
                    fail_count += 1
                    continue
                    
                if not prev_component.csv_path or not Path(prev_component.csv_path).exists():
                    logger.warning(f"找不到前站CSV: {prev_component.csv_path}")
                    fail_count += 1
                    continue
                    
                # 讀取當前站與前站CSV
                df_curr = load_csv(component.csv_path)
                df_prev = load_csv(prev_component.csv_path)
                
                if df_curr is None or df_prev is None:
                    logger.warning(f"讀取CSV失敗: {component.component_id}")
                    fail_count += 1
                    continue
                
                # 處理翻轉
                if self.flip_config.get(station, False):
                    df_curr = flip_data(df_curr)
                if self.flip_config.get(prev_station, False):
                    df_prev = flip_data(df_prev)
                
                # 轉換為二進制格式
                df_curr_bin = convert_to_binary(df_curr)
                df_prev_bin = convert_to_binary(df_prev)
                
                # 計算狀態點 (包括良品→良品、良品→缺陷、缺陷→缺陷)
                status_points = calculate_loss_points(df_prev_bin, df_curr_bin)
                
                if status_points.empty:
                    logger.info(f"元件無數據點: {component.component_id}")
                    success_count += 1
                    continue
                
                # 確定輸出路徑
                output_dir = config.get_path(
                    "database.structure.map",
                    product=product_id,
                    lot=original_lot_id
                )
                # 建立LOSS站點子目錄
                output_dir = Path(output_dir) / f"LOSS{station_idx}"
                ensure_directory(output_dir)
                output_path = output_dir / f"{component.component_id}.png"
                
                # 生成圖像
                if plot_lossmap(status_points, str(output_path)):
                    # 更新元件資訊
                    component.lossmap_path = str(output_path)
                    db_manager.update_component(component)
                    success_count += 1
                else:
                    fail_count += 1
            
            total_count = success_count + fail_count
            logger.info(f"Lossmap處理完成: 總計 {total_count}, 成功 {success_count}, 失敗 {fail_count}")
            
            if fail_count == 0:
                return True, f"所有{total_count}個元件Lossmap已生成"
            elif success_count > 0:
                return True, f"部分完成: {success_count}/{total_count}個元件Lossmap已生成"
            else:
                return False, "所有元件Lossmap生成失敗"
                
        except Exception as e:
            logger.error(f"生成Lossmap時發生錯誤: {e}")
            return False, f"生成失敗: {str(e)}"
    
    def generate_fpy(self, product_id: str, lot_id: str, station: str) -> Tuple[bool, str]:
        """
        生成指定站點的FPY圖
        
        Args:
            product_id: 產品ID
            lot_id: 批次ID
            station: 站點名稱
            
        Returns:
            Tuple[bool, str]: (成功狀態, 訊息)
        """
        try:
            # 獲取站點所有元件
            components = db_manager.get_components_by_lot_station(lot_id, station)
            if not components:
                return False, f"找不到站點 {station} 的元件"
            
            # 獲取之前所有站點 - 提前計算站點索引，避免重複計算
            try:
                station_idx = self.station_order.index(station)
                prev_stations = self.station_order[:station_idx] if station_idx > 0 else []
            except ValueError:
                logger.error(f"站點 {station} 不在 station_order 配置中")
                return False, f"站點 {station} 未在系統配置中定義"
            
            # 獲取原始批次ID，用於構建路徑
            lot_obj = db_manager.get_lot(lot_id)
            original_lot_id = lot_obj.original_lot_id
            
            is_first_station = len(prev_stations) == 0
            if is_first_station:
                logger.warning(f"{station} 是第一站，但仍將生成FPY圖")
                
            # 處理每個元件
            success_count = 0
            fail_count = 0
            skipped_count = 0
            fpy_summary = []
            
            # 預先獲取翻轉配置
            current_station_flip = self.flip_config.get(station, False)
            prev_station_flip_config = {ps: self.flip_config.get(ps, False) for ps in prev_stations}
            
            for component in components:
                # 檢查CSV是否存在
                if not component.csv_path or not Path(component.csv_path).exists():
                    logger.warning(f"找不到當前站CSV: {component.csv_path}")
                    fail_count += 1
                    continue
                
                # 檢查CSV檔名是否符合處理後格式
                csv_filename = Path(component.csv_path).name
                if not PROCESSED_FILENAME_PATTERN.match(csv_filename):
                    logger.warning(f"跳過非處理後格式的CSV: {csv_filename}")
                    skipped_count += 1
                    continue
                
                # 讀取當前站CSV
                df_curr = load_csv(component.csv_path)
                if df_curr is None:
                    logger.warning(f"讀取CSV失敗: {component.component_id}")
                    fail_count += 1
                    continue
                
                # 處理翻轉
                if current_station_flip:
                    df_curr = flip_data(df_curr)
                
                # 轉換為二進制格式
                df_curr_bin = convert_to_binary(df_curr)
                df_curr_bin = df_curr_bin.rename(columns={"binary": f"binary_{station}"})
                
                # 準備合併前站資料
                all_dfs = [df_curr_bin]
                
                # 處理前站資料
                for prev_station in prev_stations:
                    prev_component = db_manager.get_component(lot_id, prev_station, component.component_id)
                    if not prev_component or not prev_component.csv_path or not Path(prev_component.csv_path).exists():
                        logger.warning(f"找不到前站({prev_station})對應的元件CSV: {component.component_id}")
                        continue
                    
                    # 檢查前站CSV檔名是否符合處理後格式
                    prev_csv_filename = Path(prev_component.csv_path).name
                    if not PROCESSED_FILENAME_PATTERN.match(prev_csv_filename):
                        logger.warning(f"跳過前站非處理後格式的CSV: {prev_csv_filename}")
                        continue
                    
                    df_prev = load_csv(prev_component.csv_path)
                    if df_prev is None:
                        continue
                    
                    # 處理翻轉
                    if prev_station_flip_config[prev_station]:
                        df_prev = flip_data(df_prev)
                    
                    # 轉換為二進制格式
                    df_prev_bin = convert_to_binary(df_prev)
                    df_prev_bin = df_prev_bin.rename(columns={"binary": f"binary_{prev_station}"})
                    
                    all_dfs.append(df_prev_bin)
                
                # 合併所有站點資料
                if len(all_dfs) == 1:
                    logger.warning(f"元件只有當前站資料: {component.component_id}")
                    # 僅有當前站資料的情況
                    merged_df = all_dfs[0]
                    merged_df["CombinedDefectType"] = merged_df[f"binary_{station}"]
                else:
                    # 合併所有站點資料
                    merged_df = all_dfs[0]
                    for df in all_dfs[1:]:
                        merged_df = pd.merge(merged_df, df, on=["Col", "Row"], how="outer")
                    
                    # 填充缺失值
                    merged_df = merged_df.fillna(0)
                    
                    # 計算綜合缺陷類型 (1代表全部站均為良品)
                    binary_cols = [col for col in merged_df.columns if col.startswith("binary_")]
                    merged_df["CombinedDefectType"] = merged_df[binary_cols].min(axis=1)
                
                # 計算 FPY 數值
                fpy = merged_df["CombinedDefectType"].mean() * 100
                fpy_summary.append({"ID": component.component_id, "FPY": round(fpy, 2)})
                
                # 確定輸出路徑
                output_dir = config.get_path(
                    "database.structure.map",
                    product=product_id,
                    lot=original_lot_id
                )
                # 建立FPY站點子目錄
                output_dir = Path(output_dir) / "FPY"
                ensure_directory(output_dir)
                output_path = output_dir / f"{component.component_id}.png"
                
                # 生成圖像
                if plot_fpy_map(merged_df, str(output_path)):
                    # 更新元件資訊
                    component.fpy_path = str(output_path)
                    db_manager.update_component(component)
                    success_count += 1
                else:
                    fail_count += 1
            
            # 生成匯總FPY長條圖
            if fpy_summary:
                summary_df = pd.DataFrame(fpy_summary)
                
                # 使用配置的路徑保存匯總數據
                output_dir = config.get_path(
                    "database.structure.map",
                    product=product_id,
                    lot=original_lot_id
                )
                fpy_dir = Path(output_dir) / "FPY"
                ensure_directory(fpy_dir)
                
                summary_path = fpy_dir / f"summary_{station}.csv"
                save_df_to_csv(summary_df, str(summary_path))
                
                bar_path = str(summary_path).replace(".csv", ".png")
                plot_fpy_bar(summary_df, bar_path)
            
            total_count = success_count + fail_count
            logger.info(f"FPY處理完成: 總計 {total_count}, 成功 {success_count}, 失敗 {fail_count}")
            
            if fail_count == 0:
                return True, f"所有{total_count}個元件FPY已生成"
            elif success_count > 0:
                return True, f"部分完成: {success_count}/{total_count}個元件FPY已生成"
            else:
                return False, "所有元件FPY生成失敗"
                
        except Exception as e:
            logger.error(f"生成FPY時發生錯誤: {e}")
            return False, f"生成失敗: {str(e)}"
    
    def generate_fpy_parallel(self, product_id: str, lot_id: str, station: str) -> Tuple[bool, str]:
        """
        使用多線程並行生成指定站點的FPY圖
        
        Args:
            product_id: 產品ID
            lot_id: 批次ID
            station: 站點名稱
            
        Returns:
            Tuple[bool, str]: (成功狀態, 訊息)
        """
        try:
            # 獲取站點所有元件
            components = db_manager.get_components_by_lot_station(lot_id, station)
            if not components:
                return False, f"找不到站點 {station} 的元件"
            
            # 獲取之前所有站點 - 提前計算站點索引，避免重複計算
            try:
                station_idx = self.station_order.index(station)
                prev_stations = self.station_order[:station_idx] if station_idx > 0 else []
            except ValueError:
                logger.error(f"站點 {station} 不在 station_order 配置中")
                return False, f"站點 {station} 未在系統配置中定義"
            
            # 獲取原始批次ID，用於構建路徑
            lot_obj = db_manager.get_lot(lot_id)
            original_lot_id = lot_obj.original_lot_id
            
            is_first_station = len(prev_stations) == 0
            if is_first_station:
                logger.warning(f"{station} 是第一站，但仍將生成FPY圖")
            
            # 線程結果跟踪
            thread_results = []
            success_count = 0
            fail_count = 0
            fpy_summary = []
            summary_lock = threading.Lock()  # 用於線程安全地更新共享數據
            
            # 預先獲取翻轉配置
            current_station_flip = self.flip_config.get(station, False)
            prev_station_flip_config = {ps: self.flip_config.get(ps, False) for ps in prev_stations}
            
            # 定義單個元件處理函數
            def process_component(component):
                local_success = False
                local_fpy = None
                
                try:
                    # 檢查CSV是否存在
                    if not component.csv_path or not Path(component.csv_path).exists():
                        logger.warning(f"找不到當前站CSV: {component.csv_path}")
                        return False, None
                    
                    # 檢查CSV檔名是否符合處理後格式
                    csv_filename = Path(component.csv_path).name
                    if not PROCESSED_FILENAME_PATTERN.match(csv_filename):
                        logger.warning(f"跳過非處理後格式的CSV: {csv_filename}")
                        return False, None
                    
                    # 讀取當前站CSV
                    df_curr = load_csv(component.csv_path)
                    if df_curr is None:
                        logger.warning(f"讀取CSV失敗: {component.component_id}")
                        return False, None
                    
                    # 處理翻轉
                    if current_station_flip:
                        df_curr = flip_data(df_curr)
                    
                    # 轉換為二進制格式
                    df_curr_bin = convert_to_binary(df_curr)
                    df_curr_bin = df_curr_bin.rename(columns={"binary": f"binary_{station}"})
                    
                    # 準備合併前站資料
                    all_dfs = [df_curr_bin]
                    
                    # 處理前站資料
                    for prev_station in prev_stations:
                        prev_component = db_manager.get_component(lot_id, prev_station, component.component_id)
                        if not prev_component or not prev_component.csv_path or not Path(prev_component.csv_path).exists():
                            logger.warning(f"找不到前站({prev_station})對應的元件CSV: {component.component_id}")
                            continue
                        
                        # 檢查前站CSV檔名是否符合處理後格式
                        prev_csv_filename = Path(prev_component.csv_path).name
                        if not PROCESSED_FILENAME_PATTERN.match(prev_csv_filename):
                            logger.warning(f"跳過前站非處理後格式的CSV: {prev_csv_filename}")
                            continue
                        
                        df_prev = load_csv(prev_component.csv_path)
                        if df_prev is None:
                            continue
                        
                        # 處理翻轉
                        if prev_station_flip_config[prev_station]:
                            df_prev = flip_data(df_prev)
                        
                        # 轉換為二進制格式
                        df_prev_bin = convert_to_binary(df_prev)
                        df_prev_bin = df_prev_bin.rename(columns={"binary": f"binary_{prev_station}"})
                        
                        all_dfs.append(df_prev_bin)
                    
                    # 合併所有站點資料
                    if len(all_dfs) == 1:
                        # 僅有當前站資料的情況
                        merged_df = all_dfs[0]
                        merged_df["CombinedDefectType"] = merged_df[f"binary_{station}"]
                    else:
                        # 合併所有站點資料
                        merged_df = all_dfs[0]
                        for df in all_dfs[1:]:
                            merged_df = pd.merge(merged_df, df, on=["Col", "Row"], how="outer")
                        
                        # 填充缺失值
                        merged_df = merged_df.fillna(0)
                        
                        # 計算綜合缺陷類型 (1代表全部站均為良品)
                        binary_cols = [col for col in merged_df.columns if col.startswith("binary_")]
                        merged_df["CombinedDefectType"] = merged_df[binary_cols].min(axis=1)
                    
                    # 計算 FPY 數值
                    fpy = merged_df["CombinedDefectType"].mean() * 100
                    
                    # 確定輸出路徑
                    output_dir = config.get_path(
                        "database.structure.map",
                        product=product_id,
                        lot=original_lot_id
                    )
                    # 建立FPY站點子目錄
                    output_dir = Path(output_dir) / "FPY"
                    ensure_directory(output_dir)
                    output_path = output_dir / f"{component.component_id}.png"
                    
                    # 生成圖像 - 確保不涉及UI操作
                    try:
                        if plot_fpy_map(merged_df, str(output_path)):
                            # 將元件更新操作存儲為回傳值，避免在工作線程中直接更新
                            local_success = True
                            local_fpy = {
                                "ID": component.component_id, 
                                "FPY": round(fpy, 2),
                                "path": str(output_path)  # 將路徑傳回，讓主線程統一更新資料庫
                            }
                    except Exception as img_error:
                        logger.error(f"生成FPY圖像失敗 {component.component_id}: {img_error}")
                        return False, None
                    
                    return local_success, local_fpy
                    
                except Exception as e:
                    logger.error(f"處理元件 {component.component_id} FPY時發生錯誤: {e}")
                    return False, None
            
            # 使用線程池並行處理
            max_workers = min(8, len(components))  # 最多8個線程，避免過度並行
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = [executor.submit(process_component, comp) for comp in components]
                
                # 收集需要更新的組件信息
                components_to_update = []
                
                for future in futures:
                    success, fpy_data = future.result()
                    with summary_lock:
                        if success:
                            success_count += 1
                            if fpy_data:
                                fpy_summary.append({"ID": fpy_data["ID"], "FPY": fpy_data["FPY"]})
                                # 保存需要更新的組件路徑信息
                                components_to_update.append((fpy_data["ID"], fpy_data["path"]))
                        else:
                            fail_count += 1
            
            # 在主線程中更新組件信息（避免跨線程數據庫操作）
            for component_id, fpy_path in components_to_update:
                comp = db_manager.get_component(lot_id, station, component_id)
                if comp:
                    comp.fpy_path = fpy_path
                    db_manager.update_component(comp)
            
            # 生成匯總FPY長條圖
            if fpy_summary:
                summary_df = pd.DataFrame(fpy_summary)
                
                # 使用配置的路徑保存匯總數據
                output_dir = config.get_path(
                    "database.structure.map",
                    product=product_id,
                    lot=original_lot_id
                )
                fpy_dir = Path(output_dir) / "FPY"
                ensure_directory(fpy_dir)
                
                summary_path = fpy_dir / f"summary_{station}.csv"
                save_df_to_csv(summary_df, str(summary_path))
                
                bar_path = str(summary_path).replace(".csv", ".png")
                plot_fpy_bar(summary_df, bar_path)
            
            total_count = success_count + fail_count
            logger.info(f"FPY並行處理完成: 總計 {total_count}, 成功 {success_count}, 失敗 {fail_count}")
            
            if fail_count == 0:
                return True, f"所有{total_count}個元件FPY已生成"
            elif success_count > 0:
                return True, f"部分完成: {success_count}/{total_count}個元件FPY已生成"
            else:
                return False, "所有元件FPY生成失敗"
                
        except Exception as e:
            logger.error(f"生成FPY時發生錯誤: {e}")
            return False, f"生成失敗: {str(e)}"
    
    def create_task(self, task_type: str, product_id: str, lot_id: str, station: str = None, 
                   component_id: str = None, callback: Callable = None, **kwargs) -> str:
        """
        創建並啟動一個處理任務
        
        Args:
            task_type: 任務類型，'basemap', 'lossmap', 'fpy', 'move_files'
            product_id: 產品ID
            lot_id: 批次ID
            station: 站點名稱
            component_id: 元件ID
            callback: 任務完成後的回調函數（可選，優先使用信號槽連接）
            **kwargs: 其他任務參數（如move_files的move_params）
            
        Returns:
            str: 任務ID
        """
        task_id = str(uuid.uuid4())
        task = ProcessingTask(
            task_id=task_id,
            task_type=task_type,
            product_id=product_id,
            lot_id=lot_id,
            station=station,
            component_id=component_id
        )
        
        # 如果是移動檔案任務，保存額外的參數
        if task_type == "move_files" and "move_params" in kwargs:
            task.move_params = kwargs["move_params"]
        
        # 如果是批量移動檔案任務，保存額外的參數
        if task_type == "batch_move_files" and "batch_move_params" in kwargs:
            task.batch_move_params = kwargs["batch_move_params"]
        
        self.active_tasks[task_id] = task
        
        # 如果提供了callback，保存它但不再連接信號
        # 主視窗已在初始化時連接了信號槽
        if callback:
            self.task_callbacks[task_id] = callback
        
        # 啟動任務執行緒
        thread = threading.Thread(target=self._run_task, args=(task_id,))
        thread.daemon = True
        thread.start()
        
        return task_id
    
    def _run_task(self, task_id: str):
        """
        在獨立執行緒中執行任務
        
        Args:
            task_id: 任務ID
        """
        if task_id not in self.active_tasks:
            logger.error(f"找不到任務: {task_id}")
            return
            
        task = self.active_tasks[task_id]
        task.start()
        
        logger.info(f"開始執行任務: {task_id} ({task.task_type})")
        
        success = False
        message = ""
        
        try:
            # 性能監控開始
            import time
            start_time = time.time()
            
            self._monitor_performance(
                f"task_{task.task_type}",
                product_id=task.product_id,
                lot_id=task.lot_id,
                station=task.station,
                task_id=task_id,
                status="開始"
            )
            
            if task.task_type == "process_csv":
                # 處理CSV標頭 - 專門的CSV處理任務
                if task.component_id:
                    # 處理單個元件的CSV
                    component = db_manager.get_component(task.lot_id, task.station, task.component_id)
                    if component and component.csv_path:
                        success, result = self.process_csv_header(component.csv_path)
                        if success:
                            # 更新處理後的CSV路徑
                            component.csv_path = result
                            db_manager.update_component(component)
                            message = f"已處理CSV標頭: {result}"
                        else:
                            message = f"處理CSV標頭失敗: {result}"
                    else:
                        success, message = False, f"找不到元件或CSV路徑: {task.component_id}"
                else:
                    # 處理整個站點的所有CSV
                    components = db_manager.get_components_by_lot_station(task.lot_id, task.station)
                    total = len(components)
                    success_count = 0
                    
                    for component in components:
                        if component.csv_path and Path(component.csv_path).exists():
                            result, processed_path = self.process_csv_header(component.csv_path)
                            if result:
                                component.csv_path = processed_path
                                db_manager.update_component(component)
                                success_count += 1
                                
                    success = success_count > 0
                    message = f"已處理 {success_count}/{total} 個元件的CSV標頭"
            
            elif task.task_type == "basemap":
                if task.component_id:
                    # 處理單個元件的 basemap
                    component = db_manager.get_component(task.lot_id, task.station, task.component_id)
                    if component:
                        success, message = self.generate_basemap(component)
                    else:
                        success, message = False, f"找不到元件: {task.component_id}"
                else:
                    # 處理整個站點的 basemap
                    components = db_manager.get_components_by_lot_station(task.lot_id, task.station)
                    total = len(components)
                    success_count = 0
                    
                    for component in components:
                        result, _ = self.generate_basemap(component)
                        if result:
                            success_count += 1
                            
                    success = success_count > 0
                    message = f"已處理 {success_count}/{total} 個元件的 Basemap"
                    
            elif task.task_type == "lossmap":
                success, message = self.generate_lossmap(task.product_id, task.lot_id, task.station)
                
            elif task.task_type == "fpy":
                success, message = self.generate_fpy(task.product_id, task.lot_id, task.station)
                
            elif task.task_type == "fpy_parallel":
                success, message = self.generate_fpy_parallel(task.product_id, task.lot_id, task.station)
                
            elif task.task_type == "move_files":
                # 移動檔案任務
                # 從task的自定義屬性中獲取參數
                if hasattr(task, 'move_params'):
                    params = task.move_params
                    success, message = self.move_files(
                        component_id=task.component_id,
                        lot_id=task.lot_id,
                        station=task.station,
                        source_product=params['source_product'],
                        target_product=params['target_product'],
                        file_types=params['file_types']
                    )
                else:
                    success, message = False, "移動檔案任務缺少必要參數"
                
            elif task.task_type == "batch_move_files":
                # 批量移動檔案任務
                if hasattr(task, 'batch_move_params'):
                    params = task.batch_move_params
                    success, message = self.batch_move_files(
                        components_data=params['components_data'],
                        target_product=params['target_product'],
                        file_types=params['file_types']
                    )
                else:
                    success, message = False, "批量移動檔案任務缺少必要參數"
                
            else:
                success, message = False, f"未知的任務類型: {task.task_type}"
                
            # 性能監控結束
            end_time = time.time()
            elapsed_time = end_time - start_time
            
            self._monitor_performance(
                f"task_{task.task_type}",
                product_id=task.product_id,
                lot_id=task.lot_id,
                station=task.station,
                task_id=task_id,
                status="結束",
                success=success,
                elapsed_time=elapsed_time
            )
            
        except Exception as e:
            logger.error(f"執行任務 {task_id} 時發生錯誤: {e}")
            success, message = False, f"執行失敗: {str(e)}"
            
            # 記錄異常性能數據
            try:
                import time
                end_time = time.time()
                elapsed_time = end_time - start_time
                
                self._monitor_performance(
                    f"task_{task.task_type}",
                    product_id=task.product_id,
                    lot_id=task.lot_id,
                    station=task.station,
                    task_id=task_id,
                    status="錯誤",
                    error=str(e),
                    elapsed_time=elapsed_time
                )
            except:
                pass
            
        # 更新任務狀態
        if success:
            task.complete(message)
        else:
            task.fail(message)
            
        # 保存任務結果
        self.task_results[task_id] = {
            "success": success,
            "message": message,
            "task": task.to_dict()
        }
        
        # 發射任務完成信號 - 使用信號槽機制安全地回調到UI線程
        try:
            self.signaler.task_completed.emit(task_id, success, message)
        except Exception as e:
            logger.error(f"發射任務完成信號時發生錯誤: {e}")
            
            # 如果有直接回調，也嘗試調用它（向後兼容）
            if task_id in self.task_callbacks:
                try:
                    callback = self.task_callbacks[task_id]
                    # 記錄警告，提示應該使用信號槽機制
                    logger.warning(f"使用直接回調函數而非信號槽機制: {task_id}")
                    callback(task_id, success, message)
                except Exception as e2:
                    logger.error(f"執行直接回調時發生錯誤: {e2}")
            
        logger.info(f"任務 {task_id} 已完成: {success} - {message}")
    
    def get_task_status(self, task_id: str) -> Dict[str, Any]:
        """
        獲取任務狀態
        
        Args:
            task_id: 任務ID
            
        Returns:
            Dict: 任務狀態
        """
        if task_id in self.task_results:
            return self.task_results[task_id]
            
        if task_id in self.active_tasks:
            task = self.active_tasks[task_id]
            return {
                "success": None,
                "message": f"任務 {task.status}",
                "task": task.to_dict()
            }
            
        return {
            "success": False,
            "message": f"找不到任務: {task_id}",
            "task": None
        }
    
    def cancel_task(self, task_id: str) -> bool:
        """
        取消正在執行的任務（目前只能標記任務為失敗，無法真正終止）
        
        Args:
            task_id: 任務ID
            
        Returns:
            bool: 是否成功取消
        """
        if task_id in self.active_tasks:
            task = self.active_tasks[task_id]
            if task.status == "running":
                task.fail("任務已取消")
                self.task_results[task_id] = {
                    "success": False,
                    "message": "任務已取消",
                    "task": task.to_dict()
                }
                return True
                
        return False
    
    def clean_completed_tasks(self, max_age_hours: int = 24) -> int:
        """
        清理已完成的舊任務
        
        Args:
            max_age_hours: 任務保留最大小時數
            
        Returns:
            int: 清理的任務數量
        """
        now = datetime.datetime.now()
        max_age = max_age_hours * 3600  # 轉換為秒
        to_delete = []
        
        for task_id, result in self.task_results.items():
            task = result.get("task")
            if not task or not task.get("end_time"):
                continue
                
            end_time = datetime.datetime.fromisoformat(task["end_time"])
            age = (now - end_time).total_seconds()
            
            if age > max_age:
                to_delete.append(task_id)
                
        # 刪除舊任務
        for task_id in to_delete:
            if task_id in self.active_tasks:
                del self.active_tasks[task_id]
            del self.task_results[task_id]
            
        return len(to_delete)

    def validate_fpy_config(self) -> Dict[str, Any]:
        """
        驗證FPY相關配置
        
        Returns:
            Dict: 驗證結果
        """
        issues = []
        warnings = []
        
        # 檢查站點順序配置
        if not self.station_order:
            issues.append("未配置站點順序(station_order)")
        
        # 檢查翻轉配置
        for station in self.station_order:
            if station not in self.flip_config:
                warnings.append(f"站點 {station} 缺少翻轉配置，將使用默認值 False")
        
        # 檢查站點邏輯配置
        for station in self.station_order:
            if station not in self.station_logic:
                warnings.append(f"站點 {station} 缺少邏輯配置")
            else:
                logic = self.station_logic.get(station, {})
                if "run_fpy" not in logic:
                    warnings.append(f"站點 {station} 缺少 run_fpy 配置，將使用默認值 True")
        
        # 檢查計算第一站FPY的合理性
        if self.station_order and self.station_logic:
            first_station = self.station_order[0]
            if first_station in self.station_logic:
                if self.station_logic[first_station].get("run_fpy", False):
                    warnings.append(f"第一站 {first_station} 配置了run_fpy=True，但作為第一站無前序站點比較")
        
        status = len(issues) == 0
        
        if not status:
            logger.error(f"FPY配置驗證失敗: {issues}")
        
        if warnings:
            logger.warning(f"FPY配置警告: {warnings}")
            
        return {
            "status": status,
            "issues": issues,
            "warnings": warnings
        }

    def _monitor_performance(self, func_name, product_id=None, lot_id=None, station=None, **metrics):
        """
        監控並記錄性能數據
        
        Args:
            func_name: 被監控的函數名稱
            product_id: 產品ID (可選)
            lot_id: 批次ID (可選)
            station: 站點名稱 (可選)
            metrics: 其他想要記錄的指標
        """
        try:
            import time
            import psutil
            import platform
            
            process = psutil.Process()
            current_memory = process.memory_info().rss / (1024 * 1024)  # MB
            
            perf_data = {
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                "function": func_name,
                "product_id": product_id,
                "lot_id": lot_id,
                "station": station,
                "memory_usage_mb": current_memory,
                "cpu_percent": psutil.cpu_percent(),
                "thread_count": len(process.threads()),
                "python_version": platform.python_version(),
                **metrics
            }
            
            # 記錄性能數據
            log_dir = Path("logs/performance")
            log_dir.mkdir(parents=True, exist_ok=True)
            
            log_file = log_dir / f"perf_{time.strftime('%Y%m%d')}.csv"
            
            # 檢查文件是否存在，決定是否需要寫入表頭
            file_exists = log_file.exists()
            
            import csv
            with open(log_file, 'a', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=perf_data.keys())
                if not file_exists:
                    writer.writeheader()
                writer.writerow(perf_data)
                
            logger.debug(f"已記錄性能數據: {func_name}, 記憶體使用: {current_memory:.2f}MB")
            
        except Exception as e:
            logger.error(f"記錄性能數據時發生錯誤: {e}")
    
    def _time_function(self, func, *args, **kwargs):
        """
        測量函數執行時間的裝飾器
        
        Args:
            func: 要測量的函數
            args, kwargs: 函數參數
            
        Returns:
            函數的返回值
        """
        import time
        
        func_name = func.__name__
        start_time = time.time()
        
        if 'product_id' in kwargs and 'lot_id' in kwargs and 'station' in kwargs:
            self._monitor_performance(
                func_name, 
                product_id=kwargs['product_id'],
                lot_id=kwargs['lot_id'],
                station=kwargs['station'],
                status="開始"
            )
        
        result = func(*args, **kwargs)
        
        end_time = time.time()
        elapsed_time = end_time - start_time
        
        if 'product_id' in kwargs and 'lot_id' in kwargs and 'station' in kwargs:
            if isinstance(result, tuple) and len(result) >= 1:
                status = "成功" if result[0] else "失敗"
            else:
                status = "完成"
                
            self._monitor_performance(
                func_name, 
                product_id=kwargs['product_id'],
                lot_id=kwargs['lot_id'],
                station=kwargs['station'],
                elapsed_time=elapsed_time,
                status=status
            )
        
        logger.info(f"函數 {func_name} 執行時間: {elapsed_time:.2f}秒")
        return result

    def move_files(self, component_id: str, lot_id: str, station: str, 
                   source_product: str, target_product: str, 
                   file_types: List[str]) -> Tuple[bool, str]:
        """
        移動組件相關檔案從源產品到目標產品
        
        Args:
            component_id: 組件ID
            lot_id: 批次ID
            station: 站點名稱
            source_product: 源產品ID
            target_product: 目標產品ID
            file_types: 要移動的檔案類型列表 ['csv', 'map', 'org', 'roi']
            
        Returns:
            Tuple[bool, str]: (成功狀態, 訊息)
        """
        try:
            # 獲取組件信息
            component = db_manager.get_component(lot_id, station, component_id)
            if not component:
                return False, f"找不到組件: {component_id}"
            
            # 獲取批次信息以取得原始批次ID
            lot_obj = db_manager.get_lot(lot_id)
            if not lot_obj:
                return False, f"找不到批次: {lot_id}"
            
            original_lot_id = lot_obj.original_lot_id
            
            moved_files = []
            failed_files = []
            
            # 處理每種檔案類型
            for file_type in file_types:
                try:
                    if file_type == 'csv':
                        # CSV檔案移動
                        source_path = config.get_path(
                            "database.structure.csv",
                            product=source_product,
                            lot=original_lot_id,
                            station=station
                        )
                        target_path = config.get_path(
                            "database.structure.csv",
                            product=target_product,
                            lot=original_lot_id,
                            station=station
                        )
                        
                        source_file = Path(source_path) / f"{component_id}.csv"
                        target_file = Path(target_path) / f"{component_id}.csv"
                        
                        if source_file.exists():
                            ensure_directory(target_file.parent)
                            shutil.move(str(source_file), str(target_file))
                            moved_files.append(f"CSV: {source_file} -> {target_file}")
                            
                            # 更新組件的CSV路徑
                            component.csv_path = str(target_file)
                        else:
                            failed_files.append(f"CSV檔案不存在: {source_file}")
                    
                    elif file_type == 'map':
                        # Map檔案移動 (可能包含多種類型的map)
                        source_map_base = config.get_path(
                            "database.structure.map",
                            product=source_product,
                            lot=original_lot_id
                        )
                        target_map_base = config.get_path(
                            "database.structure.map",
                            product=target_product,
                            lot=original_lot_id
                        )
                        
                        # 檢查並移動各種類型的map檔案
                        map_types = [
                            (f"{station}/{component_id}.png", "basemap_path"),
                            (f"LOSS{self.station_order.index(station)}/{component_id}.png", "lossmap_path"),
                            (f"FPY/{component_id}.png", "fpy_path")
                        ]
                        
                        for map_subpath, attr_name in map_types:
                            source_map = Path(source_map_base) / map_subpath
                            target_map = Path(target_map_base) / map_subpath
                            
                            if source_map.exists():
                                ensure_directory(target_map.parent)
                                shutil.move(str(source_map), str(target_map))
                                moved_files.append(f"Map: {source_map} -> {target_map}")
                                
                                # 更新組件的map路徑
                                setattr(component, attr_name, str(target_map))
                    
                    elif file_type == 'org':
                        # Org資料夾移動
                        source_org = Path(config.get_path(
                            "database.structure.org",
                            product=source_product,
                            lot=original_lot_id,
                            station=station,
                            component=component_id
                        ))
                        target_org = Path(config.get_path(
                            "database.structure.org",
                            product=target_product,
                            lot=original_lot_id,
                            station=station,
                            component=component_id
                        ))
                        
                        if source_org.exists():
                            ensure_directory(target_org.parent)
                            shutil.move(str(source_org), str(target_org))
                            moved_files.append(f"Org: {source_org} -> {target_org}")
                        else:
                            failed_files.append(f"Org資料夾不存在: {source_org}")
                    
                    elif file_type == 'roi':
                        # ROI資料夾移動
                        source_roi = Path(config.get_path(
                            "database.structure.roi",
                            product=source_product,
                            lot=original_lot_id,
                            station=station,
                            component=component_id
                        ))
                        target_roi = Path(config.get_path(
                            "database.structure.roi",
                            product=target_product,
                            lot=original_lot_id,
                            station=station,
                            component=component_id
                        ))
                        
                        if source_roi.exists():
                            ensure_directory(target_roi.parent)
                            shutil.move(str(source_roi), str(target_roi))
                            moved_files.append(f"ROI: {source_roi} -> {target_roi}")
                        else:
                            failed_files.append(f"ROI資料夾不存在: {source_roi}")
                            
                except Exception as e:
                    failed_files.append(f"{file_type}移動失敗: {str(e)}")
            
            # 更新組件的product_id
            component.product_id = target_product
            db_manager.update_component(component)
            
            # 構建結果訊息
            success_count = len(moved_files)
            fail_count = len(failed_files)
            
            result_parts = []
            if success_count > 0:
                result_parts.append(f"成功移動 {success_count} 個檔案")
            if fail_count > 0:
                result_parts.append(f"失敗 {fail_count} 個檔案")
            
            message = "; ".join(result_parts) if result_parts else "沒有檔案需要移動"
            
            # 記錄詳細信息
            if moved_files:
                logger.info(f"成功移動的檔案: {moved_files}")
            if failed_files:
                logger.warning(f"移動失敗的檔案: {failed_files}")
            
            return success_count > 0 or fail_count == 0, message
            
        except Exception as e:
            logger.error(f"移動檔案時發生錯誤: {e}")
            return False, f"移動失敗: {str(e)}"

    def batch_move_files(self, components_data: List[Tuple[str, str, str, str]], 
                        target_product: str, file_types: List[str]) -> Tuple[bool, str]:
        """
        批量移動多個組件的檔案 - 多線程版本
        
        Args:
            components_data: 組件數據列表 [(component_id, lot_id, station, source_product), ...]
            target_product: 目標產品ID
            file_types: 要移動的檔案類型列表 ['csv', 'map', 'org', 'roi']
            
        Returns:
            Tuple[bool, str]: (成功狀態, 訊息)
        """
        try:
            from concurrent.futures import ThreadPoolExecutor, as_completed
            from ..controllers.online_monitor import online_manager
            import time
            
            total_components = len(components_data)
            success_count = 0
            fail_count = 0
            all_moved_files = []
            all_failed_files = []
            
            logger.info(f"開始批量移動 {total_components} 個組件的檔案 (多線程模式)")
            
            # 創建總體進度日誌
            batch_log = online_manager.create_log(
                product_id=target_product,
                lot_id="BATCH",
                station="BATCH_MOVE",
                component_id=f"BATCH_{total_components}_COMPONENTS"
            )
            batch_log.start_processing(f"批量移動 {total_components} 個組件")
            
            def move_single_component(component_data, index):
                """移動單個組件的檔案"""
                component_id, lot_id, station, source_product = component_data
                
                try:
                    # 為每個組件創建單獨的日誌
                    component_log = online_manager.create_log(
                        product_id=target_product,
                        lot_id=lot_id,
                        station=station,
                        component_id=component_id
                    )
                    component_log.start_processing(f"移動檔案 ({index+1}/{total_components})")
                    
                    # 調用單個檔案移動功能
                    success, message = self.move_files(
                        component_id=component_id,
                        lot_id=lot_id,
                        station=station,
                        source_product=source_product,
                        target_product=target_product,
                        file_types=file_types
                    )
                    
                    if success:
                        component_log.complete(f"移動成功: {message}")
                        online_manager.log_updated.emit(component_log)  # 觸發組件日誌更新
                        return True, f"{component_id}: {message}"
                    else:
                        component_log.fail(f"移動失敗: {message}")
                        online_manager.log_updated.emit(component_log)  # 觸發組件日誌更新
                        return False, f"{component_id}: {message}"
                        
                except Exception as e:
                    error_msg = f"{component_id}: 處理失敗 - {str(e)}"
                    logger.error(f"移動組件 {component_id} 時發生錯誤: {e}")
                    
                    # 更新組件日誌
                    if 'component_log' in locals():
                        component_log.fail(f"移動失敗: {str(e)}")
                        online_manager.log_updated.emit(component_log)  # 觸發組件日誌更新
                    
                    return False, error_msg
            
            # 使用線程池並行處理，限制並發數量避免資源競爭
            max_workers = min(4, total_components)  # 最多4個並發線程
            processed_count = 0
            
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                # 提交所有任務
                future_to_component = {
                    executor.submit(move_single_component, comp_data, idx): (comp_data, idx)
                    for idx, comp_data in enumerate(components_data)
                }
                
                # 處理完成的任務
                for future in as_completed(future_to_component):
                    component_data, index = future_to_component[future]
                    component_id = component_data[0]
                    processed_count += 1
                    
                    try:
                        success, message = future.result()
                        
                        if success:
                            success_count += 1
                            all_moved_files.append(message)
                        else:
                            fail_count += 1
                            all_failed_files.append(message)
                        
                        # 更新批次進度
                        progress_msg = f"處理進度: {processed_count}/{total_components} (成功: {success_count}, 失敗: {fail_count})"
                        batch_log.update_status("processing", progress_msg)
                        online_manager.log_updated.emit(batch_log)  # 手動觸發更新信號
                        logger.info(f"批量移動進度: {progress_msg}")
                        
                    except Exception as e:
                        fail_count += 1
                        error_msg = f"{component_id}: 執行異常 - {str(e)}"
                        all_failed_files.append(error_msg)
                        logger.error(f"處理組件 {component_id} 的Future時發生錯誤: {e}")
                        
                        # 更新批次進度 (即使出錯也要更新)
                        progress_msg = f"處理進度: {processed_count}/{total_components} (成功: {success_count}, 失敗: {fail_count})"
                        batch_log.update_status("processing", progress_msg)
                        online_manager.log_updated.emit(batch_log)  # 手動觸發更新信號
            
            # 構建結果訊息
            result_parts = []
            if success_count > 0:
                result_parts.append(f"成功處理 {success_count} 個組件")
            if fail_count > 0:
                result_parts.append(f"失敗 {fail_count} 個組件")
            
            message = "; ".join(result_parts) if result_parts else "沒有組件需要處理"
            
            # 記錄詳細信息
            if all_moved_files:
                logger.info(f"批量移動成功的組件: {all_moved_files}")
            if all_failed_files:
                logger.warning(f"批量移動失敗的組件: {all_failed_files}")
            
            overall_success = success_count > 0 or fail_count == 0
            
            # 完成批次日誌
            if overall_success:
                batch_log.complete(f"批量移動完成: {message}")
            else:
                batch_log.fail(f"批量移動失敗: {message}")
            
            # 手動觸發最終更新信號
            online_manager.log_updated.emit(batch_log)
            
            return overall_success, message
            
        except Exception as e:
            logger.error(f"批量移動檔案時發生錯誤: {e}")
            
            # 如果批次日誌已創建，更新其狀態
            if 'batch_log' in locals():
                batch_log.fail(f"批量移動異常: {str(e)}")
            
            return False, f"批量移動失敗: {str(e)}"

    def _auto_move_immediate_files(self, component: ComponentInfo):
        """
        自動移動即時生成的檔案（CSV 和 Map）
        
        Args:
            component: 組件資訊
        """
        try:
            # 檢查自動移動是否啟用
            if not config.get("auto_move.enabled", False):
                logger.info("自動移動功能已禁用")
                return
            
            # 獲取目標產品
            target_product = config.get("auto_move.target_product", "i-Pixel")
            
            # 獲取批次信息以取得產品ID
            lot_obj = db_manager.get_lot(component.lot_id)
            if not lot_obj:
                logger.warning(f"找不到批次: {component.lot_id}，無法移動即時檔案")
                return
            
            source_product = lot_obj.product_id
            
            # 如果組件已經在目標產品中，不需要移動
            if source_product == target_product:
                logger.info(f"組件 {component.component_id} 已在目標產品 {target_product} 中")
                return
            
            original_lot_id = lot_obj.original_lot_id
            station = component.station
            component_id = component.component_id
            
            # 獲取即時檔案類型
            immediate_file_types = config.get("auto_move.immediate.file_types", ["csv", "map"])
            
            # 執行移動
            success, message = self.move_files(
                component_id=component_id,
                lot_id=component.lot_id,
                station=station,
                source_product=source_product,
                target_product=target_product,
                file_types=immediate_file_types
            )
            
            if success:
                logger.info(f"自動移動即時檔案成功: {component_id} -> {target_product}")
                
                # 添加到延遲移動隊列（如果啟用）
                if config.get("auto_move.delayed.enabled", False):
                    # 嘗試從主視窗獲取延遲移動管理器
                    try:
                        from PySide6.QtWidgets import QApplication
                        app = QApplication.instance()
                        if app:
                            main_window = app.activeWindow()
                            if hasattr(main_window, 'delayed_move_manager'):
                                main_window.delayed_move_manager.add_to_delayed_queue(
                                    component_id, component.lot_id, station, 
                                    source_product, target_product
                                )
                            else:
                                logger.warning("主視窗中沒有延遲移動管理器")
                        else:
                            logger.warning("無法獲取應用程式實例")
                    except Exception as e:
                        logger.error(f"添加到延遲移動隊列時發生錯誤: {e}")
            else:
                logger.error(f"自動移動即時檔案失敗: {message}")
                
        except Exception as e:
            logger.error(f"自動移動即時檔案時發生錯誤: {e}")

    def _move_file_or_folder(self, source_path: str, target_path: str, attr_name: str):
        """
        移動單個檔案或資料夾
        
        Args:
            source_path: 源路徑
            target_path: 目標路徑
            attr_name: 組件屬性名稱 (e.g., 'basemap_path', 'lossmap_path', 'fpy_path', 'csv_path')
        """
        try:
            # 確保目標目錄存在
            ensure_directory(target_path)
            
            # 檢查源檔案是否存在
            if Path(source_path).exists():
                # 檢查源檔案是否為資料夾
                if Path(source_path).is_dir():
                    shutil.move(str(source_path), str(target_path))
                else:
                    # 檔案移動
                    shutil.move(str(source_path), str(target_path))
            else:
                logger.warning(f"源檔案不存在，無法移動: {source_path}")
                
        except Exception as e:
            logger.error(f"移動檔案或資料夾時發生錯誤 ({attr_name}): {e}")


# 創建全局數據處理器實例
data_processor = DataProcessor() 