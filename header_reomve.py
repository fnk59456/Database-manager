import os
import pandas as pd
import re

# 檔名正規表達式：{device}_{component}_{time}.csv，排除 _PCx
FILENAME_PATTERN = re.compile(r'^[A-Z0-9]+_[A-Z0-9]+_\d{12}\.csv$')


def remove_header_and_rename(folder_path, skip_lines=20, rename=True):
    """
    保留原始檔案，另存為處理過的 {component_id}.csv。
    僅處理符合命名規則的原始 AOI 檔案。
    """
    for filename in os.listdir(folder_path):
        if not filename.endswith('.csv') or not FILENAME_PATTERN.match(filename):
            print(f"⚠️ 不合法檔名格式，略過：{filename}")
            continue

        file_path = os.path.join(folder_path, filename)

        try:
            df = pd.read_csv(file_path, skiprows=skip_lines)
        except Exception as e:
            print(f"[error] 無法處理 {filename}: {e}")
            continue

        if rename:
            match = re.match(r'(.+)_([A-Z0-9]+)_(\d{12})\.csv', filename)
            if match:
                new_name = f"{match.group(2)}.csv"
                new_path = os.path.join(folder_path, new_name)

                df.to_csv(new_path, index=False)
                print(f"✅ 已輸出處理後檔案：{new_name}")
