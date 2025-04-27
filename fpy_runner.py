import os
import json
import pandas as pd
from utils import convert_to_binary, flip_csv, plot_fpy_map, plot_fpy_bar


def run_fpy(station, product, lot, config):
    # 讀取各站路徑
    station_order = config.get("station_order", [])
    flip_config = config.get("flip", {})
    rules_path = config.get("defect_rules", "configs/defect_rules.json")
    path_pattern = config.get("path_pattern", {})

    rules = json.load(open(rules_path, encoding="utf-8"))
    current_stage_index = station_order.index(station)
    if current_stage_index == 0:
        # 第一站不處理 FPY
        return

    # 尋找當前與上一站的資料夾
    prev_station = station_order[current_stage_index - 1]

    step_a = path_pattern["csv"].format(product=product, lot=lot, station=prev_station)
    step_b = path_pattern["csv"].format(product=product, lot=lot, station=station)
    output_dir = os.path.join(path_pattern["map"].format(product=product, lot=lot), "FPY")
    os.makedirs(output_dir, exist_ok=True)

    # 檢查檔案對應關係（componentID.csv 檔）
    files_a = [f for f in os.listdir(step_a) if f.endswith(".csv")]
    files_b = [f for f in os.listdir(step_b) if f.endswith(".csv")]
    common_files = set(files_a) & set(files_b)

    if not common_files:
        print(f"⚠️ 無對應檔案可比對 FPY：{step_a} ↔ {step_b}")
        return

    fpy_summary = []

    for file in sorted(common_files):
        path_a = os.path.join(step_a, file)
        path_b = os.path.join(step_b, file)

        try:
            df_a = pd.read_csv(path_a)
            df_b = pd.read_csv(path_b)
        except Exception as e:
            print(f"❌ 讀取 CSV 失敗: {file} → {e}")
            continue

        if flip_config.get(prev_station, False):
            df_a = flip_csv(df_a)
        if flip_config.get(station, False):
            df_b = flip_csv(df_b)

        try:
            df_a = convert_to_binary(df_a, rules)
            df_b = convert_to_binary(df_b, rules)
        except Exception as e:
            print(f"❌ binary 轉換失敗: {file} → {e}")
            continue

        merged = pd.merge(df_a, df_b, on=["Col", "Row"], suffixes=("_prev", "_curr"))
        merged["CombinedDefectType"] = merged[["binary_prev", "binary_curr"]].max(axis=1)

        fpy = merged["CombinedDefectType"].mean() * 100
        fpy_summary.append({"ID": file.replace(".csv", ""), "FPY": round(fpy, 2)})

        output_map_path = os.path.join(output_dir, file.replace(".csv", ".png"))
        plot_fpy_map(merged, output_map_path)
        print(f"✅ FPY MAP: {file}（使用站點: {prev_station} → {station}）")

    # 匯出良率報告
    if fpy_summary:
        summary_df = pd.DataFrame(fpy_summary)
        summary_path = os.path.join(output_dir, f"summary_{station}.csv")
        summary_df.to_csv(summary_path, index=False)
        plot_fpy_bar(summary_df, summary_path.replace(".csv", ".png"))
        print(f"📄 FPY 整體報告儲存：{summary_path}")
