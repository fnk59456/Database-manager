#!/usr/bin/env python
"""
測試CSV處理流程腳本

測試從processed_csv讀取原始數據，處理後保存到csv目錄的流程
"""
import os
import sys
import argparse
from pathlib import Path

# 添加父目錄到sys.path，以便能夠導入應用程序模塊
sys.path.append(str(Path(__file__).parent.parent.parent))

from dbmplus.app.utils.logger import get_logger
from dbmplus.app.utils.config_manager import config
from dbmplus.app.controllers.data_processor import data_processor
from dbmplus.app.models.database_manager import db_manager
from dbmplus.app.models.data_models import ComponentInfo

logger = get_logger("test_csv_flow")

def test_csv_processing_flow(product_id, lot_id, station, component_id=None):
    """
    測試CSV處理流程
    
    Args:
        product_id: 產品ID
        lot_id: 批次ID
        station: 站點
        component_id: 可選的組件ID，若不提供則處理該站點所有組件
    
    Returns:
        bool: 處理是否成功
    """
    logger.info(f"開始測試CSV處理流程: 產品={product_id}, 批次={lot_id}, 站點={station}, 組件={component_id or '所有'}")
    
    # 1. 檢查processed_csv目錄是否存在
    base_path = Path(config.get("database.base_path", "D:/Database-PC"))
    processed_csv_dir = base_path / product_id / "processed_csv" / lot_id / station
    
    if not processed_csv_dir.exists():
        logger.error(f"processed_csv目錄不存在: {processed_csv_dir}")
        return False
    
    # 2. 重新掃描數據庫
    db_manager.scan_database()
    
    # 3. 如果指定了組件ID，則只處理該組件
    if component_id:
        component = db_manager.get_component(lot_id, station, component_id)
        if not component:
            logger.error(f"找不到組件: {component_id}")
            return False
        
        # 確保組件可以找到原始CSV文件
        potential_file = processed_csv_dir / f"{component_id}.csv"
        if potential_file.exists():
            component.original_csv_path = str(potential_file)
            
            # 如果標準csv路徑不存在，暫時使用原始路徑
            if not component.csv_path or not Path(component.csv_path).exists():
                component.csv_path = str(potential_file)
                
            db_manager.update_component(component)
            logger.info(f"已更新組件原始CSV路徑: {potential_file}")
        else:
            logger.error(f"在processed_csv目錄下找不到對應的CSV文件: {component_id}.csv")
            return False
        
        # 處理單個組件
        success, message = data_processor.generate_basemap(component)
        logger.info(f"處理結果: 成功={success}, 訊息={message}")
        return success
    
    # 4. 處理所有組件
    components = db_manager.get_components_by_lot_station(lot_id, station)
    if not components:
        logger.error(f"找不到任何組件: 批次={lot_id}, 站點={station}")
        return False
    
    success_count = 0
    total_count = len(components)
    
    for component in components:
        # 確保組件可以找到原始CSV文件
        potential_file = processed_csv_dir / f"{component.component_id}.csv"
        if potential_file.exists():
            component.original_csv_path = str(potential_file)
            
            # 如果標準csv路徑不存在，暫時使用原始路徑
            if not component.csv_path or not Path(component.csv_path).exists():
                component.csv_path = str(potential_file)
                
            db_manager.update_component(component)
            logger.info(f"已更新組件原始CSV路徑: {potential_file}")
        else:
            logger.warning(f"在processed_csv目錄下找不到對應的CSV文件: {component.component_id}.csv")
            continue
        
        success, message = data_processor.generate_basemap(component)
        if success:
            success_count += 1
        logger.info(f"處理組件 {component.component_id}: 成功={success}, 訊息={message}")
    
    logger.info(f"處理完成: 總計={total_count}, 成功={success_count}, 失敗={total_count-success_count}")
    return success_count > 0

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="測試CSV處理流程")
    parser.add_argument("product_id", help="產品ID")
    parser.add_argument("lot_id", help="批次ID")
    parser.add_argument("station", help="站點")
    parser.add_argument("--component", "-c", help="可選的組件ID")
    
    args = parser.parse_args()
    
    if test_csv_processing_flow(args.product_id, args.lot_id, args.station, args.component):
        print("測試成功!")
    else:
        print("測試失敗，請檢查日誌獲取詳細信息。") 