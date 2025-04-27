import os
import json
import pandas as pd

def load_config(config_path):
    if not os.path.exists(config_path):
        raise FileNotFoundError(f"設定檔不存在: {config_path}")
    with open(config_path, 'r', encoding='utf-8') as f:
        return json.load(f)

def find_header_row(csv_path):
    with open(csv_path, 'r', encoding='utf-8-sig') as f:
        for i, line in enumerate(f):
            if 'Col' in line and 'Row' in line and 'DefectType' in line:
                return i
    return None

def load_csv_correctly(csv_path):
    header_row = find_header_row(csv_path)
    if header_row is None:
        return None, f"無法找到標題行: {csv_path}"
    df = pd.read_csv(csv_path, sep=None, engine='python', encoding='utf-8-sig', skiprows=header_row)
    df.columns = df.columns.str.strip()
    return df, None

def check_csv_against_config(folder_path, selected_recipe, config_data):
    """
    檢查整個資料夾中所有 csv 是否符合配方定義的 (Col, Row, DefectType) 組合
    """
    results = []
    for file in os.listdir(folder_path):
        if file.endswith('.csv'):
            csv_path = os.path.join(folder_path, file)
            df, error = load_csv_correctly(csv_path)
            if error:
                results.append((file, 'error', error))
                continue

            required_columns = {'Col', 'Row', 'DefectType'}
            if not required_columns.issubset(df.columns):
                results.append((file, 'error', '缺少必要欄位'))
                continue

            required_set = set(tuple(item) for item in config_data[selected_recipe])
            csv_set = set(zip(df['Col'], df['Row'], df['DefectType']))
            missing = required_set - csv_set
            if missing:
                results.append((file, 'fail', missing))
            else:
                results.append((file, 'pass', None))

    return results

def check_alignment(csv_path, recipe, config_data):
    """
    包裝函式：針對單一 csv 路徑進行偏移檢查，回傳 (狀態, 詳細內容)
    """
    folder_path = os.path.dirname(csv_path)
    target_name = os.path.basename(csv_path)
    result_list = check_csv_against_config(folder_path, recipe, config_data)

    for fname, status, detail in result_list:
        if fname == target_name:
            return status, detail
    return 'error', '找不到檔案結果'
