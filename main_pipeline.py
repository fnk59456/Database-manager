import os
from utils import load_config, AOI_FILENAME_PATTERN, PROCESSED_FILENAME_PATTERN
from rawdata_check import check_alignment
from header_reomve import remove_header_and_rename
from basemap_runner import run_basemap
from lossmap_runner import run_lossmap
from fpy_runner import run_fpy

def resolve_paths(config, product, lot, station):
    paths = {}
    for key, pattern in config['path_pattern'].items():
        try:
            paths[key] = pattern.format(product=product, lot=lot, station=station, component="{component}")
        except KeyError:
            paths[key] = pattern.format(product=product, lot=lot, station=station)
    return paths

def get_recipe_for_station(station, config):
    return config.get("station_recipe", {}).get(station, "Sapphire A")

def main_pipeline_v2(base_path, global_config_path, only_lot=None, only_station=None):
    config = load_config(global_config_path)
    align_config = load_config("configs/align_key_config.json")

    csv_root = os.path.join(base_path, "csv")
    product = os.path.basename(base_path)

    for lot in os.listdir(csv_root):
        if only_lot and lot != only_lot:
            continue

        lot_path = os.path.join(csv_root, lot)
        if not os.path.isdir(lot_path):
            continue

        for station in os.listdir(lot_path):
            if only_station and station != only_station:
                continue

            station_path = os.path.join(lot_path, station)
            if not os.path.isdir(station_path):
                continue

            print(f"\n🚀 處理 {product}/{lot}/{station}...")
            recipe = get_recipe_for_station(station, config)
            logic = config.get("station_logic", {}).get(station, {})
            paths = resolve_paths(config, product, lot, station)

            # Step 1: 原始 CSV 偏移確認 + 去表頭 + rename
            aoi_csvs = [f for f in os.listdir(station_path) if AOI_FILENAME_PATTERN.match(f)]
            for file in aoi_csvs:
                csv_path = os.path.join(station_path, file)
                status, detail = check_alignment(csv_path, recipe, align_config)
                if status == "fail":
                    print(f"❌ 偏移錯誤: {file} → {detail}")
                    continue
                elif status == "error":
                    print(f"⚠️ 偏移檢查失敗: {file} → {detail}")
                    continue

            if aoi_csvs:
                remove_header_and_rename(station_path)

            # Step 2a: 對每個 component 個別做 Basemap
            processed_csvs = [f for f in os.listdir(station_path) if PROCESSED_FILENAME_PATTERN.match(f)]
            for file in processed_csvs:
                processed_csv_path = os.path.join(station_path, file)
                run_basemap(processed_csv_path, station, product, lot, config)

            # Step 2b: 整站統一跑 Lossmap（一次就好）
            if logic.get("run_lossmap", False):
                run_lossmap(station, product, lot, config)

            # Step 2c: 整站統一跑 FPY（一次就好）
            if logic.get("run_fpy", False):
                run_fpy(station, product, lot, config)

if __name__ == "__main__":
    sample_folder = "D:/Database-PC/PVT"
    config_path = "configs/global_config.json"
    main_pipeline_v2(sample_folder, config_path, only_lot="WLPF400100", only_station="DC2")
