"""
测试在线监控功能的脚本
"""
import os
import sys
import time
import shutil
import random
from pathlib import Path
from datetime import datetime

# 添加项目根目录到路径
script_dir = Path(__file__).parent.parent
if str(script_dir) not in sys.path:
    sys.path.insert(0, str(script_dir))

from app.utils import config, ensure_directory
from app.models import db_manager
from app.models.data_models import ProductInfo, LotInfo


def create_test_csv(processed_csv_dir, product_id, lot_id, station, count=5, interval=2):
    """
    创建测试CSV文件
    
    Args:
        processed_csv_dir: processed_csv目录
        product_id: 产品ID
        lot_id: 批次ID
        station: 站点
        count: 创建文件数量
        interval: 文件创建间隔(秒)
    """
    # 确保目录存在
    target_dir = processed_csv_dir / lot_id / station
    ensure_directory(target_dir)
    
    print(f"将在 {target_dir} 创建 {count} 个测试文件")
    
    for i in range(count):
        # 生成文件名
        now = datetime.now()
        timestamp = now.strftime("%Y%m%d%H%M")
        device = "M3X60"
        component_id = f"WLPF{400100+i:05d}"
        filename = f"{device}_{component_id}_{timestamp}.csv"
        
        # 生成测试CSV内容
        content = """Col,Row,DefectType
1,1,ok
1,2,ok
2,1,ok
2,2,ok
"""
        # 写入文件
        file_path = target_dir / filename
        with open(file_path, 'w') as f:
            f.write(content)
        
        print(f"[{i+1}/{count}] 已创建: {file_path}")
        
        # 等待指定间隔
        if i < count - 1:
            time.sleep(interval)

def ensure_product_and_lot(product_id, lot_id, station):
    """确保产品和批次在数据库中存在"""
    # 检查产品是否存在
    product = db_manager.get_product(product_id)
    if not product:
        # 创建新产品
        print(f"创建新产品: {product_id}")
        product = ProductInfo(product_id=product_id)
        # 假设产品已经存在于文件系统，这里只需更新数据库缓存
    
    # 检查批次是否存在
    lot = None
    for existing_lot in db_manager.get_lots_by_product(product_id):
        if existing_lot.original_lot_id == lot_id:
            lot = existing_lot
            break
    
    if not lot:
        # 创建新批次并关联到产品
        print(f"创建新批次: {lot_id} (产品: {product_id})")
        # 构建内部批次ID
        internal_lot_id = f"{product_id}_{lot_id}"
        lot = LotInfo(
            lot_id=internal_lot_id, 
            product_id=product_id,
            original_lot_id=lot_id
        )
        
        # 确保批次目录存在于文件系统
        base_path = Path(config.get("database.base_path", "D:/Database-PC"))
        csv_dir = base_path / product_id / "csv" / lot_id / station
        processed_csv_dir = base_path / product_id / "processed_csv" / lot_id / station
        ensure_directory(csv_dir)
        ensure_directory(processed_csv_dir)
    
    # 确保站点已添加到批次
    if station not in lot.stations:
        print(f"为批次 {lot_id} 添加站点: {station}")
        lot.add_station(station)
    
    # 扫描数据库以确保更改生效
    print("扫描数据库以更新缓存...")
    db_manager.scan_database()
    print("数据库扫描完成")

def main():
    """主函数"""
    # 获取数据库路径
    base_path = Path(config.get("database.base_path", "D:/Database-PC"))
    
    # 选择一个产品 (示例: PVT)
    product_id = "PVT"
    product_dir = base_path / product_id
    
    # 检查产品目录是否存在
    if not product_dir.exists():
        print(f"产品目录不存在: {product_dir}")
        sys.exit(1)
    
    # processed_csv目录
    processed_csv_dir = product_dir / "processed_csv"
    ensure_directory(processed_csv_dir)
    
    # 创建测试批次和站点
    lot_id = f"TEST{datetime.now().strftime('%Y%m%d%H%M')}"
    station = "MT"
    
    # 确保产品和批次在数据库中存在
    ensure_product_and_lot(product_id, lot_id, station)
    
    # 创建测试文件
    create_test_csv(processed_csv_dir, product_id, lot_id, station, count=10, interval=3)
    
    print("测试完成")

if __name__ == "__main__":
    main() 