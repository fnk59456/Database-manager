import pandas as pd
import matplotlib.pyplot as plt
import os
import json
import re

def convert_to_binary(df: pd.DataFrame, rules: dict) -> pd.DataFrame:
    """
    將 DefectType 欄位依照 rules 轉為 binary (1=good, 0=bad)
    rules: {'good': [...], 'bad': [...]} 可自由配置
    """
    df = df.copy()
    if 'DefectType' not in df.columns:
        raise ValueError("DataFrame 缺少 DefectType 欄位")

    df['binary'] = df['DefectType'].apply(lambda x: 1 if x in rules['good'] else 0)
    return df[['Col', 'Row', 'binary']]

def flip_csv(df: pd.DataFrame, axis='horizontal') -> pd.DataFrame:
    """
    對 DataFrame 進行左右或上下鏡像（flip）
    """
    df = df.copy()
    if axis == 'horizontal':
        df['Col'] = df['Col'].max() - df['Col']
    elif axis == 'vertical':
        df['Row'] = df['Row'].max() - df['Row']
    return df

def plot_loss_map(df: pd.DataFrame, save_path: str):
    """
    繪製 LOSS MAP（灰底 + 紅點）
    """
    plt.figure(figsize=(20, 20))
    plt.scatter(df['Col'], df['Row'], c='red', s=5, label='Loss')
    plt.gca().invert_yaxis()
    plt.xlabel('Col')
    plt.ylabel('Row')
    plt.title('Loss Map')
    plt.legend()
    plt.grid(True)
    os.makedirs(os.path.dirname(save_path), exist_ok=True)
    plt.savefig(save_path)
    plt.close()

def plot_fpy_map(df: pd.DataFrame, save_path: str):
    """
    繪製 FPY 散點圖（0 = 有 defect，1 = 無 defect）
    """
    colors = df['CombinedDefectType'].map({0: 'red', 1: 'black'})
    plt.figure(figsize=(20, 20))
    plt.scatter(df['Col'], df['Row'], c=colors, s=5)
    plt.gca().invert_yaxis()
    plt.xlabel('Col')
    plt.ylabel('Row')
    plt.title('FPY Defect Map')
    os.makedirs(os.path.dirname(save_path), exist_ok=True)
    plt.savefig(save_path)
    plt.close()

def plot_fpy_bar(summary: pd.DataFrame, save_path: str):
    """
    繪製良率長條圖（FPY%）
    summary 必須包含 'ID' 與 'FPY' 欄位
    """
    plt.figure(figsize=(10, 5))
    plt.bar(summary['ID'], summary['FPY'], color='skyblue')
    plt.ylim(0, 100)
    plt.xticks(rotation=45)
    plt.ylabel('FPY (%)')
    plt.title('First Pass Yield')
    plt.tight_layout()
    os.makedirs(os.path.dirname(save_path), exist_ok=True)
    plt.savefig(save_path)
    plt.close()

def load_config(path):
    """讀取 JSON 設定檔"""
    if not os.path.exists(path):
        raise FileNotFoundError(f"設定檔不存在: {path}")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

# AOI 原始輸出格式: device_component_timestamp.csv（不接受 _PC 後綴）
AOI_FILENAME_PATTERN = re.compile(r"^[^_]+_[^_]+_\d+\.csv$")

# 處理後格式: 僅剩 component.csv
PROCESSED_FILENAME_PATTERN = re.compile(r"^[^_]+\.csv$")
