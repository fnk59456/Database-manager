import os
from main_pipeline import main_pipeline_v2

def process_task(product, lot, station):
    """
    從 GUI 呼叫，根據選取的 product, lot, station 執行對應的主流程
    """
    print(f"\n🚀 開始處理：{product}/{lot}/{station}")

    # 模擬觸發點路徑：根據 global_config 中定義，手動組出 csv path
    base_path = os.path.join("D:/Database-PC", product)

    # 指定 config 路徑（可調整成固定位置）
    config_path = "configs/global_config.json"

    # 呼叫主流程，限制處理指定 lot/station
    main_pipeline_v2(base_path, config_path, only_lot=lot, only_station=station)
