"""
數據處理工具模塊，提供數據處理、轉換和分析功能
"""
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from pathlib import Path
from .logger import get_logger
from .config_manager import config

logger = get_logger("data_utils")


def convert_to_binary(df, rules=None):
    """
    將 DefectType 欄位依照 rules 轉為 binary (1=good, 0=bad)
    
    Args:
        df: 包含 DefectType 欄位的 DataFrame
        rules: 缺陷規則，格式為 {'good': [...], 'bad': [...]}
               如果未提供，則從配置中讀取
    
    Returns:
        DataFrame: 含有 'Col', 'Row', 'binary' 欄位的 DataFrame
    """
    if rules is None:
        rules = {
            'good': config.get('defect_rules.good', []),
            'bad': config.get('defect_rules.bad', [])
        }

    if 'DefectType' not in df.columns:
        logger.error("DataFrame 缺少 DefectType 欄位")
        raise ValueError("DataFrame 缺少 DefectType 欄位")
    
    df_copy = df.copy()
    df_copy['binary'] = df_copy['DefectType'].apply(lambda x: 1 if x in rules['good'] else 0)
    return df_copy[['Col', 'Row', 'binary']]


def flip_data(df, axis='horizontal'):
    """
    對 DataFrame 進行左右或上下鏡像（flip）
    
    Args:
        df: 包含 Col 和 Row 欄位的 DataFrame
        axis: 鏡像軸，'horizontal'=左右翻轉，'vertical'=上下翻轉
    
    Returns:
        DataFrame: 翻轉後的 DataFrame
    """
    df_copy = df.copy()
    
    if axis == 'horizontal':
        df_copy['Col'] = df_copy['Col'].max() - df_copy['Col']
    elif axis == 'vertical':
        df_copy['Row'] = df_copy['Row'].max() - df_copy['Row']
    else:
        logger.warning(f"無效的翻轉軸: {axis}，支援的選項為 'horizontal' 或 'vertical'")
    
    return df_copy


def apply_mask(df, mask_rules):
    """
    根據遮罩規則過濾數據
    
    Args:
        df: 包含 Col 和 Row 欄位的 DataFrame
        mask_rules: 遮罩規則列表，每個規則格式為:
                    {'start_row': int, 'end_row': int, 'start_col': int, 'end_col': int}
    
    Returns:
        DataFrame: 過濾後的 DataFrame
    """
    if df is None or df.empty:
        return df
    
    if 'Row' not in df.columns or 'Col' not in df.columns:
        logger.warning("DataFrame 缺少 Row 或 Col 欄位，無法應用遮罩")
        return df
    
    df_copy = df.copy()
    
    for rule in mask_rules:
        try:
            start_row = int(rule["start_row"])
            end_row = int(rule["end_row"])
            start_col = int(rule["start_col"])
            end_col = int(rule["end_col"])
            
            mask = ~((df_copy['Row'] >= start_row) & (df_copy['Row'] <= end_row) &
                     (df_copy['Col'] >= start_col) & (df_copy['Col'] <= end_col))
            
            df_copy = df_copy[mask]
        except (KeyError, TypeError) as e:
            logger.error(f"處理遮罩規則時出錯: {e}")
    
    return df_copy


def calculate_loss_points(prev_df, curr_df):
    """
    找出從上一站良品變成下一站缺陷的位置（Good → Bad）
    
    Args:
        prev_df: 前一站點的 DataFrame，需包含 'Col', 'Row', 'binary' 欄位
        curr_df: 當前站點的 DataFrame，需包含 'Col', 'Row', 'binary' 欄位
    
    Returns:
        DataFrame: 包含 'Col', 'Row' 的損失點 DataFrame
    """
    # 確保輸入的 DataFrame 包含必要欄位
    for df, name in [(prev_df, 'prev_df'), (curr_df, 'curr_df')]:
        if not all(col in df.columns for col in ['Col', 'Row', 'binary']):
            logger.error(f"{name} 缺少必要欄位")
            raise ValueError(f"{name} 缺少必要欄位: 'Col', 'Row', 'binary'")
    
    # 合併兩個 DataFrame 以查找損失點
    merged = pd.merge(prev_df, curr_df, on=['Col', 'Row'], suffixes=('_prev', '_curr'))
    
    # 找出從良品變為缺陷的點
    loss_points = merged[(merged['binary_prev'] == 1) & (merged['binary_curr'] == 0)]
    
    return loss_points[['Col', 'Row']]


def plot_basemap(df, output_path, title=None, plot_config=None):
    """
    生成基本缺陷分佈圖
    
    Args:
        df: 包含 'Col', 'Row', 'DefectType' 欄位的 DataFrame
        output_path: 圖像保存路徑
        title: 圖像標題，默認為檔名
        plot_config: 繪圖配置，如顏色、大小等
    
    Returns:
        bool: 是否成功生成圖像
    """
    try:
        if df is None or df.empty:
            logger.warning("無法生成圖像: DataFrame 為空")
            return False
        
        if 'Col' not in df.columns or 'Row' not in df.columns or 'DefectType' not in df.columns:
            logger.error("DataFrame 缺少必要欄位: 'Col', 'Row', 'DefectType'")
            return False
        
        # 設置默認繪圖配置
        if plot_config is None:
            plot_config = {
                'map_size': (20, 20),
                'point_size': 100 / 15,  # 原始大小除以 15
                'title_fontsize': 20,
                'invert_y_axis': True,
                'invert_x_axis': False,
                'colors': {
                    'ok': 'black',
                    'dirty': 'red',
                    'miss': 'blue',
                    'hurt': 'orange',
                    'default': 'green'
                }
            }
        
        # 根據缺陷類型設置顏色
        df_sorted = df.sort_values(by=['Col', 'Row'])
        color_map = plot_config.get('colors', {})
        
        # 創建和配置圖形
        fig, ax = plt.subplots(figsize=plot_config.get('map_size', (20, 20)))
        fig.subplots_adjust(left=0.07, right=0.93, bottom=0.07, top=0.93)
        
        # 繪製散點圖，根據 DefectType 進行顏色編碼
        defect_types = df_sorted['DefectType'].unique()
        
        for defect_type in defect_types:
            # 獲取顏色，若未定義則使用默認顏色
            color = None
            for key, value in color_map.items():
                if str(defect_type).lower().startswith(key.lower()):
                    color = value
                    break
            if color is None:
                color = color_map.get('default', 'green')
            
            subset = df_sorted[df_sorted['DefectType'] == defect_type]
            ax.scatter(
                subset['Col'], subset['Row'], 
                c=color, label=defect_type, 
                s=plot_config.get('point_size', 6.67), 
                alpha=0.6, edgecolors='w'
            )
        
        # 設置軸和標題
        ax.set_xlabel('Col Coordinate')
        ax.set_ylabel('Row Coordinate')
        
        if title is None:
            title = Path(output_path).stem
        
        ax.set_title(f'Map of Defects - {title}', fontsize=plot_config.get('title_fontsize', 20))
        ax.legend(title='Defect Type', loc='center left', bbox_to_anchor=(1, 0.5))
        
        # 軸反轉
        if plot_config.get('invert_y_axis', True):
            ax.invert_yaxis()
        if plot_config.get('invert_x_axis', False):
            ax.invert_xaxis()
        
        # 保存圖像
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        plt.savefig(output_path, bbox_inches='tight')
        plt.close()
        
        logger.info(f"成功生成基本地圖: {output_path}")
        return True
    
    except Exception as e:
        logger.error(f"生成基本地圖時出錯: {e}")
        return False


def plot_lossmap(df, output_path, title=None):
    """
    繪製損失點地圖（LOSS MAP），紅點表示損失點
    
    Args:
        df: 包含 'Col' 和 'Row' 欄位的損失點 DataFrame
        output_path: 圖像保存路徑
        title: 圖像標題，默認為檔名
    
    Returns:
        bool: 是否成功生成圖像
    """
    try:
        if df is None or df.empty:
            logger.warning("無法生成損失地圖: DataFrame 為空")
            return False
        
        # 配置參數
        map_size = (20, 20)
        point_size = 100 / 15
        title_fontsize = 20
        
        # 創建和配置圖形
        fig, ax = plt.subplots(figsize=map_size)
        fig.subplots_adjust(left=0.07, right=0.93, bottom=0.07, top=0.93)
        
        # 繪製紅點表示損失點
        ax.scatter(df['Col'], df['Row'], c='red', s=point_size, label='Loss', alpha=0.6)
        
        # 配置軸和標題
        ax.invert_yaxis()
        ax.set_xlabel('Col Coordinate', fontsize=12)
        ax.set_ylabel('Row Coordinate', fontsize=12)
        
        if title is None:
            title = Path(output_path).stem
        
        ax.set_title(f'Loss Map - {title}', fontsize=title_fontsize)
        ax.legend(title='Defect Type', loc='center left', bbox_to_anchor=(1, 0.5))
        ax.grid(True)
        
        # 保存圖像
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        plt.savefig(output_path, bbox_inches='tight')
        plt.close()
        
        logger.info(f"成功生成損失地圖: {output_path}")
        return True
    
    except Exception as e:
        logger.error(f"生成損失地圖時出錯: {e}")
        return False


def plot_fpy_map(df, output_path, title=None):
    """
    繪製 FPY 地圖，展示良品率分佈
    
    Args:
        df: 包含 'Col', 'Row', 'CombinedDefectType' 欄位的 DataFrame
        output_path: 圖像保存路徑
        title: 圖像標題，默認為檔名
    
    Returns:
        bool: 是否成功生成圖像
    """
    try:
        if df is None or df.empty:
            logger.warning("無法生成FPY地圖: DataFrame 為空")
            return False
        
        # 配置參數
        map_size = (20, 20)
        point_size = 100 / 15
        title_fontsize = 20
        
        # 創建新的圖形 - 確保線程安全
        plt.ioff()  # 關閉交互模式
        fig = plt.figure(figsize=map_size)
        ax = fig.add_subplot(111)
        fig.subplots_adjust(left=0.07, right=0.93, bottom=0.07, top=0.93)
        
        # 根據 CombinedDefectType 設置顏色 (0=缺陷, 1=良品)
        colors = df['CombinedDefectType'].map({0: 'red', 1: 'black'})
        
        # 繪製散點圖
        ax.scatter(df['Col'], df['Row'], c=colors, s=point_size, alpha=0.6)
        
        # 配置軸和標題
        ax.invert_yaxis()
        ax.set_xlabel('Col Coordinate', fontsize=12)
        ax.set_ylabel('Row Coordinate', fontsize=12)
        
        if title is None:
            title = Path(output_path).stem
        
        ax.set_title(f'FPY Defect Map - {title}', fontsize=title_fontsize)
        
        # 添加圖例
        from matplotlib.lines import Line2D
        legend_elements = [
            Line2D([0], [0], marker='o', color='w', label='No Defect (1)',
                   markerfacecolor='black', markersize=8),
            Line2D([0], [0], marker='o', color='w', label='Defect (0)',
                   markerfacecolor='red', markersize=8),
        ]
        ax.legend(handles=legend_elements, title='FPY Class', loc='center left', bbox_to_anchor=(1, 0.5))
        
        # 保存圖像
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(output_path, bbox_inches='tight')
        plt.close(fig)
        
        logger.info(f"成功生成FPY地圖: {output_path}")
        return True
    
    except Exception as e:
        logger.error(f"生成FPY地圖時出錯: {e}")
        # 確保關閉任何開啟的圖形
        try:
            plt.close()
        except:
            pass
        return False


def plot_fpy_bar(summary_df, output_path):
    """
    繪製良率長條圖
    
    Args:
        summary_df: 包含 'ID' 和 'FPY' 欄位的 DataFrame
        output_path: 圖像保存路徑
    
    Returns:
        bool: 是否成功生成圖像
    """
    try:
        if summary_df is None or summary_df.empty:
            logger.warning("無法生成FPY長條圖: DataFrame 為空")
            return False
        
        if 'ID' not in summary_df.columns or 'FPY' not in summary_df.columns:
            logger.error("DataFrame 缺少必要欄位: 'ID', 'FPY'")
            return False
        
        # 創建和配置圖形 - 確保線程安全
        plt.ioff()  # 關閉交互模式
        fig = plt.figure(figsize=(10, 5))
        ax = fig.add_subplot(111)
        ax.bar(summary_df['ID'], summary_df['FPY'], color='skyblue')
        ax.set_ylim(0, 100)
        plt.setp(ax.get_xticklabels(), rotation=45)
        ax.set_ylabel('FPY (%)')
        ax.set_title('First Pass Yield')
        fig.tight_layout()
        
        # 保存圖像
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(output_path)
        plt.close(fig)
        
        logger.info(f"成功生成FPY長條圖: {output_path}")
        return True
    
    except Exception as e:
        logger.error(f"生成FPY長條圖時出錯: {e}")
        # 確保關閉任何開啟的圖形
        try:
            plt.close()
        except:
            pass
        return False 