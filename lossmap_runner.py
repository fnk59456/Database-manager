import os
import json
import pandas as pd
from utils import convert_to_binary, flip_csv, plot_loss_map

def load_json(path):
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)

def calculate_loss_coords(prev_df, curr_df):
    """
    找出從上一站良品變成下一站缺陷的位置（Good → Bad）
    """
    merged = pd.merge(prev_df, curr_df, on=['Col', 'Row'], suffixes=('_prev', '_curr'))
    loss_df = merged[(merged['binary_prev'] == 1) & (merged['binary_curr'] == 0)]
    return loss_df[['Col', 'Row']]

def run_lossmap(station, product, lot, config):
    # 從 global config 中讀取 rules path 路徑，再讀檔案
    rules_path = config.get("defect_rules", "configs/defect_rules.json")
    print(rules_path)
    with open(rules_path, encoding="utf-8") as f:
        rules = json.load(f)

    # 讀取是否 flip 與站點順序
    flip_config = config.get("flip", {})
    station_order = config.get("station_order", [])

    # 確認當前站點不是第一站，才能進行 LossMap 比對
    if station not in station_order or station_order.index(station) == 0:
        print(f"⚠️ 跳過 LossMap：{station} 為第一站")
        return

    prev_station = station_order[station_order.index(station) - 1]

    # 解析路徑
    current_path = config["path_pattern"]["csv"].format(product=product, lot=lot, station=station)
    prev_path = config["path_pattern"]["csv"].format(product=product, lot=lot, station=prev_station)
    output_dir = os.path.join(
        config["path_pattern"]["map"].format(product=product, lot=lot),
        f"LOSS{station_order.index(station)}"
    )
    os.makedirs(output_dir, exist_ok=True)

    # 處理每個 component 的對應檔案
    for file in os.listdir(current_path):
        if not file.endswith(".csv"):
            continue
        comp_path = os.path.join(current_path, file)
        prev_file = os.path.join(prev_path, file)

        if not os.path.exists(prev_file):
            print(f"❗ 無對應前一站檔案：{file}，跳過")
            continue

        try:
            df_now = pd.read_csv(comp_path)
            df_prev = pd.read_csv(prev_file)
        except Exception as e:
            print(f"❌ 讀取 CSV 失敗：{file} → {e}")
            continue

        # Flip 處理（前一站可能有 Flip）
        if flip_config.get(prev_station, False):
            df_prev = flip_csv(df_prev)

        # 轉換為 binary
        df_now_bin = convert_to_binary(df_now, rules)
        df_prev_bin = convert_to_binary(df_prev, rules)

        # 對齊欄位名
        df_now_bin = df_now_bin.rename(columns={"binary": "now"})
        df_prev_bin = df_prev_bin.rename(columns={"binary": "prev"})

        merged = pd.merge(df_now_bin, df_prev_bin, on=["Col", "Row"], how="inner")
        merged["loss"] = (merged["prev"] == 1) & (merged["now"] == 0)

        df_loss = merged[merged["loss"]][["Col", "Row"]]
        if df_loss.empty:
            print(f"✅ 無 Loss：{file}")
            continue

        output_path = os.path.join(output_dir, file.replace(".csv", ".png"))
        plot_loss_map(df_loss, output_path)
        print(f"✅ LossMap saved: {output_path}")

if __name__ == "__main__":
    # 測試用 dummy
    config_path = "configs/global_config.json"
    config = load_json(config_path)
    run_lossmap("DC2", "PVT", "WLPF400100", config)
