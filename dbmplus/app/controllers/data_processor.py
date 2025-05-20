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
from concurrent.futures import ThreadPoolExecutor
from PySide6.QtCore import QObject, Signal, QMetaObject, Qt

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
                
                # 計算損失點
                loss_points = calculate_loss_points(df_prev_bin, df_curr_bin)
                
                if loss_points.empty:
                    logger.info(f"元件無損失點: {component.component_id}")
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
                if plot_lossmap(loss_points, str(output_path)):
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
                   component_id: str = None, callback: Callable = None) -> str:
        """
        創建並啟動一個處理任務
        
        Args:
            task_type: 任務類型，'basemap', 'lossmap', 'fpy'
            product_id: 產品ID
            lot_id: 批次ID
            station: 站點名稱
            component_id: 元件ID
            callback: 任務完成後的回調函數（可選，優先使用信號槽連接）
            
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


# 創建全局數據處理器實例
data_processor = DataProcessor() 