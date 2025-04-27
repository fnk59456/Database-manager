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
            "components": {}
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
                    lot = LotInfo(
                        lot_id=lot_data["lot_id"],
                        product_id=lot_data["product_id"],
                        stations=lot_data.get("stations", []),
                        description=lot_data.get("description"),
                        created_at=datetime.fromisoformat(lot_data.get("created_at", datetime.now().isoformat())),
                        modified_at=datetime.fromisoformat(lot_data.get("modified_at", datetime.now().isoformat()))
                    )
                    self.data_cache["lots"][lot.lot_id] = lot
                
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
                        basemap_path=comp_data.get("basemap_path"),
                        lossmap_path=comp_data.get("lossmap_path"),
                        fpy_path=comp_data.get("fpy_path"),
                        defect_stats=comp_data.get("defect_stats", {}),
                        created_at=datetime.fromisoformat(comp_data.get("created_at", datetime.now().isoformat())),
                        modified_at=datetime.fromisoformat(comp_data.get("modified_at", datetime.now().isoformat()))
                    )
                    key = f"{component.lot_id}_{component.station}_{component.component_id}"
                    self.data_cache["components"][key] = component
                
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
                "components": [component.to_dict() for component in self.data_cache["components"].values()]
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
            "components": {}
        }
        
        # 掃描產品目錄
        for product_dir in list_directories(self.base_path):
            product_id = product_dir
            product_path = self.base_path / product_dir
            
            # 檢查 csv 目錄是否存在
            csv_dir = product_path / "csv"
            if not csv_dir.exists():
                continue
                
            # 創建產品對象
            product = ProductInfo(product_id=product_id)
            self.data_cache["products"][product_id] = product
            
            # 掃描批次目錄
            for lot_dir in list_directories(csv_dir):
                lot_id = lot_dir
                lot_path = csv_dir / lot_dir
                
                # 創建批次對象
                lot = LotInfo(lot_id=lot_id, product_id=product_id)
                self.data_cache["lots"][lot_id] = lot
                product.add_lot(lot_id)
                
                # 掃描站點目錄
                for station_dir in list_directories(lot_path):
                    station = station_dir
                    station_path = lot_path / station_dir
                    
                    # 添加站點到批次
                    lot.add_station(station)
                    
                    # 掃描元件檔案
                    for file in list_files(station_path, pattern=r".*\.csv$"):
                        component_id = Path(file).stem
                        
                        # 創建元件對象
                        component = ComponentInfo(
                            component_id=component_id,
                            lot_id=lot_id,
                            station=station,
                            processed_filename=file,
                            csv_path=str(station_path / file)
                        )
                        
                        # 檢查其他相關檔案
                        self._check_component_files(component, product_id)
                        
                        # 儲存元件
                        key = f"{component.lot_id}_{component.station}_{component.component_id}"
                        self.data_cache["components"][key] = component
        
        logger.info(f"資料庫掃描完成: {len(self.data_cache['products'])} 產品, "
                   f"{len(self.data_cache['lots'])} 批次, "
                   f"{len(self.data_cache['components'])} 元件")
        
        # 保存快取
        self._save_cache()
    
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
        return self.data_cache["lots"].get(lot_id)
    
    def get_stations_by_lot(self, lot_id: str) -> List[str]:
        """獲取指定批次的所有站點"""
        lot = self.data_cache["lots"].get(lot_id)
        return lot.stations if lot else []
    
    def get_components_by_lot_station(self, lot_id: str, station: str) -> List[ComponentInfo]:
        """獲取指定批次和站點的所有元件"""
        components = []
        for key, component in self.data_cache["components"].items():
            if component.lot_id == lot_id and component.station == station:
                components.append(component)
        return components
    
    def get_component(self, lot_id: str, station: str, component_id: str) -> Optional[ComponentInfo]:
        """獲取指定元件信息"""
        key = f"{lot_id}_{station}_{component_id}"
        return self.data_cache["components"].get(key)
    
    def update_component(self, component: ComponentInfo) -> bool:
        """更新元件信息"""
        key = f"{component.lot_id}_{component.station}_{component.component_id}"
        if key in self.data_cache["components"]:
            self.data_cache["components"][key] = component
            self._save_cache()
            return True
        return False
    
    def add_component(self, component: ComponentInfo) -> bool:
        """添加新元件"""
        key = f"{component.lot_id}_{component.station}_{component.component_id}"
        if key not in self.data_cache["components"]:
            # 確保產品和批次存在
            if component.lot_id not in self.data_cache["lots"]:
                # 從元件獲取產品ID
                product_path = Path(component.csv_path).parent.parent.parent.parent
                product_id = product_path.name
                
                # 創建產品和批次
                if product_id not in self.data_cache["products"]:
                    self.data_cache["products"][product_id] = ProductInfo(product_id=product_id)
                
                lot = LotInfo(lot_id=component.lot_id, product_id=product_id)
                self.data_cache["lots"][component.lot_id] = lot
                self.data_cache["products"][product_id].add_lot(component.lot_id)
            
            # 添加站點到批次
            lot = self.data_cache["lots"][component.lot_id]
            if component.station not in lot.stations:
                lot.add_station(component.station)
            
            # 添加元件
            self.data_cache["components"][key] = component
            self._save_cache()
            return True
        return False
    
    def remove_component(self, lot_id: str, station: str, component_id: str) -> bool:
        """移除元件"""
        key = f"{lot_id}_{station}_{component_id}"
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