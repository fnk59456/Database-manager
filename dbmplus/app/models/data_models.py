"""
數據模型模塊，定義應用程式中的各種數據結構和實體
"""
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Union, Any
from pathlib import Path
from datetime import datetime


@dataclass
class ProductInfo:
    """產品信息類"""
    product_id: str
    lots: List[str] = field(default_factory=list)
    description: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.now)
    modified_at: datetime = field(default_factory=datetime.now)

    def add_lot(self, lot_id: str) -> None:
        """添加批次到產品"""
        if lot_id not in self.lots:
            self.lots.append(lot_id)
            self.modified_at = datetime.now()

    def remove_lot(self, lot_id: str) -> bool:
        """從產品中移除批次"""
        if lot_id in self.lots:
            self.lots.remove(lot_id)
            self.modified_at = datetime.now()
            return True
        return False

    def to_dict(self) -> Dict[str, Any]:
        """轉換為字典格式"""
        return {
            "product_id": self.product_id,
            "lots": self.lots,
            "description": self.description,
            "created_at": self.created_at.isoformat(),
            "modified_at": self.modified_at.isoformat()
        }


@dataclass
class LotInfo:
    """批次信息類"""
    lot_id: str
    product_id: str
    original_lot_id: Optional[str] = None  # 原始批次ID，用於顯示
    stations: List[str] = field(default_factory=list)
    description: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.now)
    modified_at: datetime = field(default_factory=datetime.now)

    def __post_init__(self):
        """初始化後處理，確保original_lot_id有值"""
        if self.original_lot_id is None:
            self.original_lot_id = self.lot_id
            
            # 如果lot_id格式是product_id_original_id，提取原始ID
            if "_" in self.lot_id:
                parts = self.lot_id.split("_")
                if len(parts) >= 2 and parts[0] == self.product_id:
                    self.original_lot_id = "_".join(parts[1:])

    def add_station(self, station: str) -> None:
        """添加站點到批次"""
        if station not in self.stations:
            self.stations.append(station)
            self.modified_at = datetime.now()

    def remove_station(self, station: str) -> bool:
        """從批次中移除站點"""
        if station in self.stations:
            self.stations.remove(station)
            self.modified_at = datetime.now()
            return True
        return False

    def to_dict(self) -> Dict[str, Any]:
        """轉換為字典格式"""
        return {
            "lot_id": self.lot_id,
            "product_id": self.product_id,
            "original_lot_id": self.original_lot_id,
            "stations": self.stations,
            "description": self.description,
            "created_at": self.created_at.isoformat(),
            "modified_at": self.modified_at.isoformat()
        }
        
    def get_display_id(self) -> str:
        """獲取用於顯示的批次ID"""
        return self.original_lot_id


@dataclass
class ComponentInfo:
    """元件信息類"""
    component_id: str
    lot_id: str
    station: str
    original_filename: Optional[str] = None
    processed_filename: Optional[str] = None
    org_path: Optional[str] = None
    roi_path: Optional[str] = None
    csv_path: Optional[str] = None
    original_csv_path: Optional[str] = None  # 存儲processed_csv目錄中的原始CSV文件路徑
    basemap_path: Optional[str] = None
    lossmap_path: Optional[str] = None
    fpy_path: Optional[str] = None
    defect_stats: Dict[str, int] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)
    modified_at: datetime = field(default_factory=datetime.now)

    def update_paths(self, **kwargs) -> None:
        """更新檔案路徑"""
        for key, value in kwargs.items():
            if hasattr(self, key) and key.endswith('_path'):
                setattr(self, key, value)
        self.modified_at = datetime.now()

    def update_defect_stats(self, stats: Dict[str, int]) -> None:
        """更新缺陷統計"""
        self.defect_stats = stats
        self.modified_at = datetime.now()

    def to_dict(self) -> Dict[str, Any]:
        """轉換為字典格式"""
        return {
            "component_id": self.component_id,
            "lot_id": self.lot_id,
            "station": self.station,
            "original_filename": self.original_filename,
            "processed_filename": self.processed_filename,
            "org_path": self.org_path,
            "roi_path": self.roi_path,
            "csv_path": self.csv_path,
            "original_csv_path": self.original_csv_path,
            "basemap_path": self.basemap_path,
            "lossmap_path": self.lossmap_path,
            "fpy_path": self.fpy_path,
            "defect_stats": self.defect_stats,
            "created_at": self.created_at.isoformat(),
            "modified_at": self.modified_at.isoformat()
        }


@dataclass
class ProcessingTask:
    """處理任務類，用於追蹤處理作業"""
    task_id: str
    task_type: str  # 'basemap', 'lossmap', 'fpy'
    product_id: str
    lot_id: str
    station: Optional[str] = None
    component_id: Optional[str] = None
    status: str = "pending"  # pending, running, completed, failed
    message: Optional[str] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    created_at: datetime = field(default_factory=datetime.now)

    def start(self) -> None:
        """開始任務"""
        self.status = "running"
        self.start_time = datetime.now()

    def complete(self, message: Optional[str] = None) -> None:
        """完成任務"""
        self.status = "completed"
        self.end_time = datetime.now()
        if message:
            self.message = message

    def fail(self, message: str) -> None:
        """任務失敗"""
        self.status = "failed"
        self.end_time = datetime.now()
        self.message = message

    def get_duration(self) -> Optional[float]:
        """獲取任務持續時間（秒）"""
        if self.start_time and self.end_time:
            return (self.end_time - self.start_time).total_seconds()
        return None

    def to_dict(self) -> Dict[str, Any]:
        """轉換為字典格式"""
        return {
            "task_id": self.task_id,
            "task_type": self.task_type,
            "product_id": self.product_id,
            "lot_id": self.lot_id,
            "station": self.station,
            "component_id": self.component_id,
            "status": self.status,
            "message": self.message,
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "created_at": self.created_at.isoformat(),
            "duration": self.get_duration()
        } 