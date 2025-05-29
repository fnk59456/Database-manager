"""
數據處理工具模塊，提供數據處理、轉換和分析功能
"""
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from pathlib import Path
import json
import csv
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
    計算並分類從上一站到當前站的點位狀態變化
    
    Args:
        prev_df: 前一站點的 DataFrame，需包含 'Col', 'Row', 'binary' 欄位
        curr_df: 當前站點的 DataFrame，需包含 'Col', 'Row', 'binary' 欄位
    
    Returns:
        DataFrame: 包含 'Col', 'Row', 'status' 的 DataFrame，其中status為:
                 'good_to_good': 良品→良品
                 'good_to_bad': 良品→缺陷(損失點)
                 'bad_to_bad': 缺陷→缺陷
    """
    # 確保輸入的 DataFrame 包含必要欄位
    for df, name in [(prev_df, 'prev_df'), (curr_df, 'curr_df')]:
        if not all(col in df.columns for col in ['Col', 'Row', 'binary']):
            logger.error(f"{name} 缺少必要欄位")
            raise ValueError(f"{name} 缺少必要欄位: 'Col', 'Row', 'binary'")
    
    # 合併兩個 DataFrame 以查找所有重疊點
    merged = pd.merge(prev_df, curr_df, on=['Col', 'Row'], suffixes=('_prev', '_curr'))
    
    # 分類三種狀態
    merged['status'] = 'unknown'  # 初始狀態
    
    # 良品→良品 (Good → Good)
    good_to_good = merged[(merged['binary_prev'] == 1) & (merged['binary_curr'] == 1)]
    good_to_good['status'] = 'good_to_good'
    
    # 良品→缺陷 (Good → Bad，即損失點)
    good_to_bad = merged[(merged['binary_prev'] == 1) & (merged['binary_curr'] == 0)]
    good_to_bad['status'] = 'good_to_bad'
    
    # 缺陷→缺陷 (Bad → Bad)
    bad_to_bad = merged[(merged['binary_prev'] == 0) & (merged['binary_curr'] == 0)]
    bad_to_bad['status'] = 'bad_to_bad'
    
    # 合併所有狀態
    result = pd.concat([good_to_good, good_to_bad, bad_to_bad])
    
    # 只返回需要的列
    return result[['Col', 'Row', 'status']]


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
        
        # 從databasemanager格式配置中提取所需參數
        if 'map_configurations' in plot_config:
            # 處理databasemanager格式的配置
            map_configs = plot_config.get('map_configurations', {})
            # 獲取第一個站點的配置或使用默認MT
            station_config = None
            for station_key in map_configs:
                station_config = map_configs[station_key]
                break
            
            if not station_config:
                station_config = map_configs.get('MT', {})
            
            if station_config:
                color_map = station_config.get('colors', {})
                plot_config['colors'] = color_map
        
        # 處理其他databasemanager格式參數
        if 'map_size' in plot_config:
            # 如果是元組格式，直接使用
            if isinstance(plot_config['map_size'], list):
                plot_config['map_size'] = tuple(plot_config['map_size'])
        else:
            plot_config['map_size'] = (20, 20)
            
        # 處理點大小
        if 'original_size' in plot_config:
            plot_config['point_size'] = plot_config['original_size'] / 15
        
        # 軸反轉配置
        if 'invert_x_axis' in plot_config:
            plot_config['invert_x_axis'] = plot_config['invert_x_axis']
            
        # 標題字號
        if 'title_fontsize' in plot_config:
            plot_config['title_fontsize'] = plot_config['title_fontsize']
        
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
        ax.invert_yaxis()  # Y軸始終反轉
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
    繪製損失點地圖（LOSS MAP），樣式與FPY map保持一致
    
    顯示三種狀態:
    - 良品→良品 (good_to_good): 黑色點
    - 良品→缺陷 (good_to_bad): 紅色點(損失點)
    - 缺陷→缺陷 (bad_to_bad): 紅色點
    
    Args:
        df: 包含 'Col', 'Row', 'status' 欄位的 DataFrame
        output_path: 圖像保存路徑
        title: 圖像標題，默認為檔名
    
    Returns:
        bool: 是否成功生成圖像
    """
    try:
        if df is None or df.empty:
            logger.warning("無法生成損失地圖: DataFrame 為空")
            return False
        
        # 檢查是否有status欄位
        has_status = 'status' in df.columns
        
        # 配置參數
        map_size = (20, 20)
        point_size = 100 / 50
        title_fontsize = 20
        
        # 創建新的圖形 - 確保線程安全
        plt.ioff()  # 關閉交互模式
        fig = plt.figure(figsize=map_size)
        ax = fig.add_subplot(111)
        fig.subplots_adjust(left=0.07, right=0.93, bottom=0.07, top=0.93)
        
        # 設置黑色背景
        ax.set_facecolor('black')
        
        if has_status:
            # 根據status分類點
            status_colors = {
                'good_to_good': 'lightgray',  # 良品→良品: 黑色
                'good_to_bad': 'red',     # 良品→缺陷: 紅色(損失點)
                'bad_to_bad': 'black'       # 缺陷→缺陷: 紅色
            }
            
            # 為每種狀態繪製散點
            for status, color in status_colors.items():
                points = df[df['status'] == status]
                if not points.empty:
                    ax.scatter(points['Col'], points['Row'], c=color, s=point_size, 
                              label=status, alpha=0.6)
            
            # 添加自定義圖例
            from matplotlib.lines import Line2D
            legend_elements = [
                Line2D([0], [0], marker='o', color='w', label='Good → Good',
                      markerfacecolor='lightgray', markersize=8),
                Line2D([0], [0], marker='o', color='w', label='Good → Bad',
                      markerfacecolor='red', markersize=8),
                Line2D([0], [0], marker='o', color='w', label='Bad → Bad',
                      markerfacecolor='black', markersize=8)
            ]
            ax.legend(handles=legend_elements, title='Defect Status', loc='center left', 
                     bbox_to_anchor=(1, 0.5))
        else:
            # 向後兼容，處理舊版本返回的DataFrame
            ax.scatter(df['Col'], df['Row'], c='red', s=point_size, label='Loss', alpha=0.6)
            
            # 簡單圖例
            from matplotlib.lines import Line2D
            legend_elements = [
                Line2D([0], [0], marker='o', color='w', label='Loss Point',
                      markerfacecolor='red', markersize=8)
            ]
            ax.legend(handles=legend_elements, title='Defect Type', loc='center left', 
                     bbox_to_anchor=(1, 0.5))
        
        # 配置軸和標題
        ax.invert_yaxis()
        ax.set_xlabel('Col Coordinate', fontsize=12)
        ax.set_ylabel('Row Coordinate', fontsize=12)
        
        if title is None:
            title = Path(output_path).stem
        
        ax.set_title(f'Loss Map - {title}', fontsize=title_fontsize)
        
        # 保存圖像
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(output_path, bbox_inches='tight')
        plt.close(fig)
        
        logger.info(f"成功生成損失地圖: {output_path}")
        return True
    
    except Exception as e:
        logger.error(f"生成損失地圖時出錯: {e}")
        # 確保關閉任何開啟的圖形
        try:
            plt.close()
        except:
            pass
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


def check_csv_alignment(csv_path, recipe, align_config):
    """
    檢查CSV檔案是否符合對齊要求 (類似 rawdata_check.py)
    
    Args:
        csv_path: CSV檔案路徑
        recipe: 對齊配方名稱，例如 'Sapphire A'
        align_config: 對齊配置字典
        
    Returns:
        Tuple[str, str]: ('success'|'fail'|'error', 詳細訊息)
    """
    try:
        # 獲取配方的對齊關鍵字配置
        alignment_points = align_config.get(recipe, [])
        if not alignment_points:
            logger.warning(f"找不到配方 {recipe} 的對齊關鍵字")
            return "error", f"找不到配方 {recipe} 的對齊關鍵字"
            
        # 讀取CSV並解析，查找包含標頭行的CSV
        header_row = find_header_row(csv_path)
        if header_row is None:
            return "error", "找不到CSV標頭行"
            
        # 使用pandas讀取CSV
        import pandas as pd
        try:
            df = pd.read_csv(csv_path, skiprows=header_row)
        except Exception as e:
            logger.error(f"讀取CSV失敗: {e}")
            return "error", f"讀取CSV失敗: {e}"
            
        # 確保必要的列存在
        required_cols = ['Col', 'Row', 'DefectType']
        if not all(col in df.columns for col in required_cols):
            missing_cols = [col for col in required_cols if col not in df.columns]
            return "error", f"CSV缺少必要列: {', '.join(missing_cols)}"
            
        # 檢查對齊點是否存在
        found_points = 0
        total_points = len(alignment_points)
        
        for point in alignment_points:
            if isinstance(point, list) and len(point) >= 3:
                col_val, row_val, defect_type = point[0], point[1], point[2]
                
                # 查找匹配的行
                matches = df[(df['Col'] == col_val) & (df['Row'] == row_val) & (df['DefectType'] == defect_type)]
                
                if not matches.empty:
                    found_points += 1
                    logger.info(f"找到對齊點: Col={col_val}, Row={row_val}, DefectType={defect_type}")
                else:
                    logger.warning(f"找不到對齊點: Col={col_val}, Row={row_val}, DefectType={defect_type}")
        
        # 判斷是否有足夠的對齊點匹配
        if found_points > 0:
            percentage = (found_points / total_points) * 100
            # 修改判斷標準：只要有1個點匹配即可
            return "success", f"對齊正確，找到 {found_points}/{total_points} 個對齊點"
        else:
            return "fail", f"找不到任何對齊點，需要至少1個匹配"
        
    except Exception as e:
        logger.error(f"檢查CSV對齊時發生錯誤: {e}")
        return "error", f"檢查失敗: {str(e)}"


def find_header_row(file_path, max_lines=30):
    """
    智能查找CSV檔案中的標頭行
    
    Args:
        file_path: CSV檔案路徑
        max_lines: 最大檢查行數
        
    Returns:
        int: 標頭行號，如果找不到則返回None
    """
    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            lines = []
            for i in range(max_lines):
                line = f.readline()
                if not line:
                    break
                lines.append(line.strip())
        
        # 尋找包含 "Row", "Col", "DefectType" 的行
        for i, line in enumerate(lines):
            if all(field in line for field in ["Row", "Col", "DefectType"]):
                logger.info(f"在第 {i} 行找到標頭")
                return i
                
        # 第二種啟發式: 尋找包含大量逗號的行
        comma_counts = [line.count(',') for line in lines]
        if comma_counts:
            max_commas = max(comma_counts)
            if max_commas > 3:  # 假設至少需要有4列
                header_idx = comma_counts.index(max_commas)
                logger.info(f"根據逗號數量，在第 {header_idx} 行找到可能的標頭")
                return header_idx
                
        logger.warning(f"在檔案 {file_path} 中找不到標頭行")
        return None
        
    except Exception as e:
        logger.error(f"查找標頭行時發生錯誤: {e}")
        return None 