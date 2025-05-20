"""
數據庫管理模塊，提供對資料庫的訪問和操作
"""
import os
import json
import uuid
from pathlib import Path
from typing import List, Dict, Optional, Any, Tuple
from datetime import datetime

from ..utils.logger import get_logger
from ..utils.config_manager import config
from ..utils.file_utils import list_directories, list_files, ensure_directory
from .data_models import ProductInfo, LotInfo, ComponentInfo

logger = get_logger("database_manager")


class DatabaseManager:
    """數據庫管理器，處理檔案系統上的數據存取"""
    
    _instance = None  # 單例實例
    
    def __new__(cls):
        """實現單例模式"""
        if cls._instance is None:
            cls._instance = super(DatabaseManager, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        """初始化數據庫管理器"""
        if self._initialized:
            return
            
        self._initialized = True
        self.base_path = Path(config.get("database.base_path", "D:/Database-PC"))
        self.data_cache = {
            "products": {},
            "lots": {},
            "components": {},
            "lot_keys": {}  # 添加批次鍵映射字典
        }
        self.cache_file = Path(__file__).parent.parent.parent / "data" / "db_cache.json"
        
        # 確保資料庫目錄存在
        if not self.base_path.exists():
            logger.warning(f"資料庫基礎目錄不存在: {self.base_path}，將自動創建")
            ensure_directory(self.base_path)
        
        # 建立資料目錄
        ensure_directory(self.cache_file.parent)
        
        # 嘗試載入快取檔案
        self._load_cache()
    
    def _load_cache(self):
        """載入快取檔案"""
        if self.cache_file.exists():
            try:
                with open(self.cache_file, 'r', encoding='utf-8') as f:
                    cache_data = json.load(f)
                    
                # 恢復產品信息
                for product_data in cache_data.get("products", []):
                    product = ProductInfo(
                        product_id=product_data["product_id"],
                        lots=product_data.get("lots", []),
                        description=product_data.get("description"),
                        created_at=datetime.fromisoformat(product_data.get("created_at", datetime.now().isoformat())),
                        modified_at=datetime.fromisoformat(product_data.get("modified_at", datetime.now().isoformat()))
                    )
                    self.data_cache["products"][product.product_id] = product
                
                # 恢復批次信息
                for lot_data in cache_data.get("lots", []):
                    # 獲取原始批次ID，如果不存在則使用lot_id
                    original_lot_id = lot_data.get("original_lot_id", lot_data["lot_id"])
                    
                    lot = LotInfo(
                        lot_id=lot_data["lot_id"],
                        product_id=lot_data["product_id"],
                        original_lot_id=original_lot_id,
                        stations=lot_data.get("stations", []),
                        description=lot_data.get("description"),
                        created_at=datetime.fromisoformat(lot_data.get("created_at", datetime.now().isoformat())),
                        modified_at=datetime.fromisoformat(lot_data.get("modified_at", datetime.now().isoformat()))
                    )
                    self.data_cache["lots"][lot.lot_id] = lot
                    
                    # 建立批次映射關係，確保能夠通過 product_id + original_lot_id 找到唯一批次ID
                    lot_key = f"{lot.product_id}_{original_lot_id}"
                    self.data_cache["lot_keys"][lot_key] = lot.lot_id
                
                # 恢復元件信息
                for comp_data in cache_data.get("components", []):
                    component = ComponentInfo(
                        component_id=comp_data["component_id"],
                        lot_id=comp_data["lot_id"],
                        station=comp_data["station"],
                        original_filename=comp_data.get("original_filename"),
                        processed_filename=comp_data.get("processed_filename"),
                        org_path=comp_data.get("org_path"),
                        csv_path=comp_data.get("csv_path"),
                        original_csv_path=comp_data.get("original_csv_path"),
                        basemap_path=comp_data.get("basemap_path"),
                        lossmap_path=comp_data.get("lossmap_path"),
                        fpy_path=comp_data.get("fpy_path"),
                        defect_stats=comp_data.get("defect_stats", {}),
                        created_at=datetime.fromisoformat(comp_data.get("created_at", datetime.now().isoformat())),
                        modified_at=datetime.fromisoformat(comp_data.get("modified_at", datetime.now().isoformat()))
                    )
                    
                    # 獲取批次信息
                    lot = self.data_cache["lots"].get(component.lot_id)
                    if lot:
                        # 使用批次的產品ID建立組件鍵
                        key = f"{lot.product_id}_{component.lot_id}_{component.station}_{component.component_id}"
                        self.data_cache["components"][key] = component
                    else:
                        # 如果找不到批次，記錄警告並嘗試用舊格式保存（向後兼容）
                        logger.warning(f"載入快取時找不到批次 {component.lot_id}，組件: {component.component_id}")
                        key = f"{component.lot_id}_{component.station}_{component.component_id}"
                        self.data_cache["components"][key] = component
                
                # 恢復lot_keys映射（如果存在）
                if "lot_keys" in cache_data:
                    self.data_cache["lot_keys"] = cache_data["lot_keys"]
                
                logger.info(f"已載入資料庫快取: {len(self.data_cache['products'])} 產品, "
                           f"{len(self.data_cache['lots'])} 批次, "
                           f"{len(self.data_cache['components'])} 元件")
            except Exception as e:
                logger.error(f"載入快取檔案失敗: {e}")
                # 如果讀取失敗，則重新掃描
                self.scan_database()
        else:
            # 快取不存在，執行掃描
            logger.info("快取檔案不存在，將掃描資料庫")
            self.scan_database()
    
    def _save_cache(self):
        """保存快取到檔案"""
        try:
            cache_data = {
                "products": [product.to_dict() for product in self.data_cache["products"].values()],
                "lots": [lot.to_dict() for lot in self.data_cache["lots"].values()],
                "components": [component.to_dict() for component in self.data_cache["components"].values()],
                "lot_keys": self.data_cache["lot_keys"]  # 保存批次映射關係
            }
            
            with open(self.cache_file, 'w', encoding='utf-8') as f:
                json.dump(cache_data, f, indent=2, ensure_ascii=False)
                
            logger.info(f"已保存資料庫快取: {self.cache_file}")
        except Exception as e:
            logger.error(f"保存快取檔案失敗: {e}")
    
    def scan_database(self):
        """掃描檔案系統，建立產品和批次資訊"""
        logger.info("開始掃描資料庫...")
        
        # 清空現有資料
        self.data_cache = {
            "products": {},
            "lots": {},
            "components": {},
            "lot_keys": {}  # 添加批次鍵映射字典
        }
        
        # 掃描產品目錄
        for product_dir in list_directories(self.base_path):
            product_id = product_dir
            product_path = self.base_path / product_dir
            
            # 檢查 csv 目錄是否存在
            csv_dir = product_path / "csv"
            processed_csv_dir = product_path / "processed_csv"
            
            # 創建產品對象 - 只要csv或processed_csv目錄存在即可
            if not (csv_dir.exists() or processed_csv_dir.exists()):
                continue
                
            product = ProductInfo(product_id=product_id)
            self.data_cache["products"][product_id] = product
            
            # 先掃描標準csv目錄中的批次
            if csv_dir.exists():
                self._scan_directory_structure(csv_dir, product, product_id, is_processed=False)
            
            # 再掃描processed_csv目錄中的批次
            if processed_csv_dir.exists():
                self._scan_directory_structure(processed_csv_dir, product, product_id, is_processed=True)
        
        logger.info(f"資料庫掃描完成: {len(self.data_cache['products'])} 產品, "
                   f"{len(self.data_cache['lots'])} 批次, "
                   f"{len(self.data_cache['components'])} 元件")
        
        # 保存快取
        self._save_cache()
    
    def _scan_directory_structure(self, root_dir, product, product_id, is_processed=False):
        """掃描指定目錄結構下的批次和站點
        
        Args:
            root_dir: 目錄路徑 (csv或processed_csv)
            product: 產品對象
            product_id: 產品ID
            is_processed: 是否為已處理的CSV目錄
        """
        for lot_dir in list_directories(root_dir):
            lot_id = lot_dir
            lot_path = root_dir / lot_dir
            
            # 獲取或創建批次對象 - 此處根據產品ID和批次ID組合創建批次
            lot_key = f"{product_id}_{lot_id}"
            if lot_key in self.data_cache.get("lot_keys", {}):
                lot = self.data_cache["lots"][self.data_cache["lot_keys"][lot_key]]
            else:
                # 對於同名但不同產品的批次，創建唯一批次ID
                unique_lot_id = lot_id
                if lot_id in self.data_cache["lots"]:
                    existing_lot = self.data_cache["lots"][lot_id]
                    if existing_lot.product_id != product_id:
                        # 如果已存在相同批次ID但產品不同，創建唯一批次ID
                        unique_lot_id = f"{product_id}_{lot_id}"
                        logger.info(f"發現同名批次，創建唯一批次ID: {unique_lot_id} (原始批次: {lot_id})")
                
                # 創建批次對象，保存原始批次ID
                lot = LotInfo(
                    lot_id=unique_lot_id, 
                    product_id=product_id,
                    original_lot_id=lot_id  # 設置原始批次ID，用於UI顯示
                )
                self.data_cache["lots"][unique_lot_id] = lot
                
                # 保存映射關係以便後續查找
                if "lot_keys" not in self.data_cache:
                    self.data_cache["lot_keys"] = {}
                self.data_cache["lot_keys"][lot_key] = unique_lot_id
                
                product.add_lot(unique_lot_id)
            
            # 掃描站點目錄
            for station_dir in list_directories(lot_path):
                station = station_dir
                station_path = lot_path / station_dir
                
                # 添加站點到批次
                lot.add_station(station)
                
                # 掃描元件檔案
                for file in list_files(station_path, pattern=r".*\.csv$"):
                    component_id = Path(file).stem
                    file_path = station_path / file
                    
                    # 檢查是否為有效文件
                    if not file_path.exists() or file_path.stat().st_size == 0:
                        logger.warning(f"跳過無效文件: {file_path}")
                        continue
                    
                    # 為避免不同產品中的相同組件衝突，創建產品相關的組件鍵
                    component_key = f"{product_id}_{lot.lot_id}_{station}_{component_id}"
                    
                    # 檢查組件是否已存在
                    if component_key in self.data_cache["components"]:
                        component = self.data_cache["components"][component_key]
                        
                        # 處理路徑更新邏輯
                        if is_processed:
                            # 如果processed_csv目錄，記錄原始路徑
                            # 只有原始路徑字段為空，或者標準csv路徑不存在時才更新
                            if not component.original_csv_path or not Path(component.csv_path).exists():
                                component.original_csv_path = str(file_path)
                                
                                # 如果標準csv路徑不存在，暫時使用原始路徑
                                if not component.csv_path or not Path(component.csv_path).exists():
                                    component.csv_path = str(file_path)
                                    logger.info(f"更新組件臨時CSV路徑: {component.csv_path}")
                        else:
                            # 如果是標準csv目錄，優先使用標準路徑
                            component.csv_path = str(file_path)
                            logger.info(f"更新組件處理後CSV路徑: {component.csv_path}")
                    else:
                        # 創建新元件對象
                        component = ComponentInfo(
                            component_id=component_id,
                            lot_id=lot.lot_id,  # 使用可能重命名後的批次ID
                            station=station,
                            processed_filename=file
                        )
                        
                        # 根據目錄類型設置路徑
                        if is_processed:
                            component.original_csv_path = str(file_path)
                            component.csv_path = str(file_path)  # 暫時設為原始路徑
                        else:
                            component.csv_path = str(file_path)
                    
                    # 檢查其他相關檔案
                    self._check_component_files(component, product_id)
                    
                    # 儲存元件
                    self.data_cache["components"][component_key] = component
    
    def _check_component_files(self, component: ComponentInfo, product_id: str):
        """檢查元件的相關檔案並更新路徑"""
        lot_id = component.lot_id
        station = component.station
        component_id = component.component_id
        
        # 檢查 org 檔案
        org_path = self.base_path / product_id / "org" / lot_id / station / component_id
        if org_path.exists() and org_path.is_dir():
            component.org_path = str(org_path)
        
        # 檢查 basemap 檔案
        basemap_path = self.base_path / product_id / "map" / lot_id / station / f"{component_id}.png"
        if basemap_path.exists():
            component.basemap_path = str(basemap_path)
        
        # 檢查 lossmap 檔案
        if station != "MT":  # MT 沒有 lossmap
            # 根據站點決定 lossmap 的路徑
            station_order = config.get("processing.station_order", [])
            # 安全檢查：確保站點在站點列表中
            if station in station_order:
                station_index = station_order.index(station)
                if station_index > 0:
                    lossmap_path = self.base_path / product_id / "map" / lot_id / f"LOSS{station_index}" / f"{component_id}.png"
                    if lossmap_path.exists():
                        component.lossmap_path = str(lossmap_path)
        
        # 檢查 fpy 檔案
        fpy_path = self.base_path / product_id / "map" / lot_id / "FPY" / f"{component_id}.png"
        if fpy_path.exists():
            component.fpy_path = str(fpy_path)
    
    def get_products(self) -> List[ProductInfo]:
        """獲取所有產品信息"""
        return list(self.data_cache["products"].values())
    
    def get_product(self, product_id: str) -> Optional[ProductInfo]:
        """獲取指定產品信息"""
        return self.data_cache["products"].get(product_id)
    
    def get_lots_by_product(self, product_id: str) -> List[LotInfo]:
        """獲取指定產品的所有批次"""
        return [
            self.data_cache["lots"][lot_id]
            for lot_id in self.data_cache["products"].get(product_id, ProductInfo(product_id="")).lots
            if lot_id in self.data_cache["lots"]
        ]
    
    def get_lot(self, lot_id: str) -> Optional[LotInfo]:
        """獲取指定批次信息"""
        # 直接通過批次ID查找
        lot = self.data_cache["lots"].get(lot_id)
        if lot:
            return lot
            
        # 嘗試通過產品_批次格式查找
        for key, unique_id in self.data_cache.get("lot_keys", {}).items():
            if unique_id == lot_id:
                return self.data_cache["lots"].get(unique_id)
                
        # 嘗試通過原始批次名稱查找
        for unique_id, lot_obj in self.data_cache["lots"].items():
            if unique_id.endswith(f"_{lot_id}") or unique_id == lot_id:
                return lot_obj
                
        return None
    
    def get_stations_by_lot(self, lot_id: str) -> List[str]:
        """獲取指定批次的所有站點"""
        lot = self.data_cache["lots"].get(lot_id)
        return lot.stations if lot else []
    
    def get_components_by_lot_station(self, lot_id: str, station: str) -> List[ComponentInfo]:
        """獲取指定批次和站點的所有元件"""
        components = []
        # 檢查是否是重命名後的批次ID
        lot = self.data_cache["lots"].get(lot_id)
        
        # 如果找不到直接的批次ID，嘗試通過原始ID查找
        if not lot:
            for lot_obj in self.data_cache["lots"].values():
                if lot_obj.original_lot_id == lot_id:
                    lot = lot_obj
                    break
        
        if not lot:
            logger.warning(f"找不到批次: {lot_id}")
            return []
            
        product_id = lot.product_id
        internal_lot_id = lot.lot_id  # 使用內部批次ID查找組件
        
        # 使用產品ID前綴匹配組件鍵
        prefix = f"{product_id}_{internal_lot_id}_{station}_"
        
        for key, component in self.data_cache["components"].items():
            if key.startswith(prefix):
                components.append(component)
        
        return components
    
    def get_component(self, lot_id: str, station: str, component_id: str) -> Optional[ComponentInfo]:
        """獲取指定元件信息"""
        # 檢查是否是重命名後的批次ID
        lot = self.data_cache["lots"].get(lot_id)
        
        # 如果找不到直接的批次ID，嘗試通過原始ID查找
        if not lot:
            for lot_obj in self.data_cache["lots"].values():
                if lot_obj.original_lot_id == lot_id:
                    lot = lot_obj
                    break
                    
        if not lot:
            logger.warning(f"找不到批次: {lot_id}")
            return None
            
        product_id = lot.product_id
        internal_lot_id = lot.lot_id  # 使用內部批次ID查找組件
        
        # 使用產品ID建立完整的組件鍵
        key = f"{product_id}_{internal_lot_id}_{station}_{component_id}"
        return self.data_cache["components"].get(key)
    
    def update_component(self, component: ComponentInfo) -> bool:
        """更新元件信息"""
        # 獲取批次對象，確定產品ID
        lot = self.get_lot(component.lot_id)
        if not lot:
            # 如果找不到直接的批次ID，嘗試通過原始ID查找
            for lot_obj in self.data_cache["lots"].values():
                if lot_obj.original_lot_id == component.lot_id:
                    lot = lot_obj
                    # 更新組件批次ID為內部ID
                    component.lot_id = lot.lot_id
                    break
                    
            if not lot:
                logger.warning(f"更新組件時找不到批次: {component.lot_id}")
                return False
            
        product_id = lot.product_id
        
        # 使用產品ID建立完整的組件鍵
        key = f"{product_id}_{component.lot_id}_{component.station}_{component.component_id}"
        
        if key in self.data_cache["components"]:
            self.data_cache["components"][key] = component
            self._save_cache()
            return True
            
        logger.warning(f"找不到需要更新的組件: {key}")
        return False
    
    def add_component(self, component: ComponentInfo) -> bool:
        """添加新元件"""
        # 獲取批次對象，確定產品ID
        lot = self.get_lot(component.lot_id)
        if not lot:
            # 嘗試從CSV路徑推導產品ID
            try:
                # 從元件獲取產品ID
                product_path = Path(component.csv_path).parent.parent.parent.parent
                product_id = product_path.name
                
                # 創建產品和批次
                if product_id not in self.data_cache["products"]:
                    self.data_cache["products"][product_id] = ProductInfo(product_id=product_id)
                
                # 檢查是否存在同名批次
                original_lot_id = component.lot_id  # 保存原始批次ID
                lot_key = f"{product_id}_{original_lot_id}"
                if lot_key in self.data_cache.get("lot_keys", {}):
                    unique_lot_id = self.data_cache["lot_keys"][lot_key]
                    lot = self.data_cache["lots"][unique_lot_id]
                else:
                    # 確認批次ID唯一性
                    unique_lot_id = component.lot_id
                    if component.lot_id in self.data_cache["lots"]:
                        existing_lot = self.data_cache["lots"][component.lot_id]
                        if existing_lot.product_id != product_id:
                            unique_lot_id = f"{product_id}_{component.lot_id}"
                            
                    # 創建批次
                    lot = LotInfo(
                        lot_id=unique_lot_id, 
                        product_id=product_id,
                        original_lot_id=original_lot_id  # 設置原始批次ID
                    )
                    self.data_cache["lots"][unique_lot_id] = lot
                    
                    # 保存批次映射
                    if "lot_keys" not in self.data_cache:
                        self.data_cache["lot_keys"] = {}
                    self.data_cache["lot_keys"][lot_key] = unique_lot_id
                    
                    # 添加批次到產品
                    self.data_cache["products"][product_id].add_lot(unique_lot_id)
                    
                # 更新組件批次ID以匹配唯一批次ID
                component.lot_id = lot.lot_id
            except Exception as e:
                logger.error(f"從組件CSV路徑推導產品ID失敗: {e}")
                return False
        
        # 使用產品ID建立完整的組件鍵
        product_id = lot.product_id
        key = f"{product_id}_{component.lot_id}_{component.station}_{component.component_id}"
        
        # 添加站點到批次
        lot.add_station(component.station)
        
        # 添加元件
        if key not in self.data_cache["components"]:
            self.data_cache["components"][key] = component
            self._save_cache()
            return True
        return False
    
    def remove_component(self, lot_id: str, station: str, component_id: str) -> bool:
        """移除元件"""
        # 獲取批次對象，確定產品ID
        lot = self.data_cache["lots"].get(lot_id)
        
        # 如果找不到直接的批次ID，嘗試通過原始ID查找
        if not lot:
            for lot_obj in self.data_cache["lots"].values():
                if lot_obj.original_lot_id == lot_id:
                    lot = lot_obj
                    lot_id = lot.lot_id  # 使用內部批次ID
                    break
                    
        if not lot:
            logger.warning(f"移除組件時找不到批次: {lot_id}")
            return False
            
        product_id = lot.product_id
        
        # 使用產品ID建立完整的組件鍵
        key = f"{product_id}_{lot_id}_{station}_{component_id}"
        
        if key in self.data_cache["components"]:
            del self.data_cache["components"][key]
            self._save_cache()
            return True
        return False

    def get_component_count(self) -> Dict[str, int]:
        """獲取各種元件的數量統計"""
        stats = {
            "total": len(self.data_cache["components"]),
            "by_station": {},
            "by_product": {}
        }
        
        for component in self.data_cache["components"].values():
            # 按站點統計
            if component.station not in stats["by_station"]:
                stats["by_station"][component.station] = 0
            stats["by_station"][component.station] += 1
            
            # 按產品統計
            lot = self.data_cache["lots"].get(component.lot_id)
            if lot and lot.product_id:
                if lot.product_id not in stats["by_product"]:
                    stats["by_product"][lot.product_id] = 0
                stats["by_product"][lot.product_id] += 1
        
        return stats

    def get_lots_display(self) -> List[Dict[str, Any]]:
        """
        獲取用於顯示的批次列表，使用原始批次ID
        
        Returns:
            List[Dict]: 包含顯示信息的批次列表
        """
        result = []
        for lot in self.data_cache["lots"].values():
            # 創建用於顯示的批次信息，使用原始批次ID
            display_info = {
                "lot_id": lot.original_lot_id,  # 使用原始批次ID
                "product_id": lot.product_id,
                "stations": lot.stations,
                "internal_id": lot.lot_id  # 保存內部ID以便查找
            }
            result.append(display_info)
        return result
        
    def get_lot_display_info(self, lot_id: str) -> Dict[str, Any]:
        """
        獲取指定批次的顯示信息
        
        Args:
            lot_id: 批次ID（可能是內部ID或原始ID）
            
        Returns:
            Dict: 批次顯示信息
        """
        # 首先查找批次對象
        lot = self.get_lot(lot_id)
        if not lot:
            # 嘗試通過原始ID查找
            for lot_obj in self.data_cache["lots"].values():
                if lot_obj.original_lot_id == lot_id:
                    lot = lot_obj
                    break
                    
        if not lot:
            return {"error": f"找不到批次: {lot_id}"}
            
        # 返回顯示信息
        return {
            "lot_id": lot.original_lot_id,  # 顯示原始ID
            "product_id": lot.product_id,
            "stations": lot.stations,
            "internal_id": lot.lot_id,
            "description": lot.description
        }

    def validate_station_order(self) -> Tuple[bool, Dict[str, Any]]:
        """
        驗證配置的站點順序與實際資料庫結構是否匹配
        
        Returns:
            Tuple[bool, Dict]: (是否匹配, 詳細信息)
        """
        station_order = config.get("processing.station_order", [])
        if not station_order:
            return False, {"status": False, "message": "未找到站點順序配置"}
            
        # 收集資料庫中所有批次的站點
        all_stations = set()
        for lot in self.data_cache["lots"].values():
            all_stations.update(lot.stations)
            
        # 檢查資料庫中是否存在未配置的站點
        unconfigured_stations = all_stations - set(station_order)
        
        # 檢查配置中是否存在資料庫中沒有的站點
        missing_stations = set(station_order) - all_stations
        
        result = {
            "status": len(unconfigured_stations) == 0,
            "station_order": station_order,
            "all_stations_in_db": list(all_stations),
            "unconfigured_stations": list(unconfigured_stations),
            "missing_stations": list(missing_stations)
        }
        
        if result["status"]:
            logger.info("站點順序驗證通過")
        else:
            logger.warning(f"站點順序驗證失敗: 未配置的站點: {unconfigured_stations}, 缺失的站點: {missing_stations}")
            
        return result["status"], result


# 創建全局數據庫管理器實例
db_manager = DatabaseManager() 