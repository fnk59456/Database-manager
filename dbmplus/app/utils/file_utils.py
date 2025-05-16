"""
文件處理工具模塊，提供檔案相關操作和輔助功能
"""
import os
import re
import shutil
import pandas as pd
from pathlib import Path
from datetime import datetime
from .logger import get_logger
from typing import Optional

logger = get_logger("file_utils")

# 檔名正規表達式：{device}_{component}_{time}.csv
AOI_FILENAME_PATTERN = re.compile(r'^[A-Z0-9]+_([A-Z0-9]+)_\d{12}\.csv$')

# 處理後格式: 僅剩 component.csv
PROCESSED_FILENAME_PATTERN = re.compile(r'^[A-Z0-9]+\.csv$')


def ensure_directory(directory_path):
    """
    確保目錄存在，不存在則創建
    
    Args:
        directory_path: 目錄路徑
    
    Returns:
        Path: 目錄路徑物件
    """
    path = Path(directory_path)
    path.mkdir(parents=True, exist_ok=True)
    return path


def list_files(directory, pattern=None):
    """
    列出目錄中符合模式的檔案
    
    Args:
        directory: 目錄路徑
        pattern: 正則表達式模式，默認為None表示列出所有檔案
    
    Returns:
        list: 符合條件的檔案列表
    """
    directory = Path(directory)
    if not directory.exists():
        logger.warning(f"目錄不存在: {directory}")
        return []
        
    if pattern:
        return [f for f in os.listdir(directory) if re.match(pattern, f)]
    return [f for f in os.listdir(directory) if Path(directory / f).is_file()]


def list_directories(directory):
    """
    列出目錄中的所有子目錄
    
    Args:
        directory: 目錄路徑
    
    Returns:
        list: 子目錄列表
    """
    directory = Path(directory)
    if not directory.exists():
        logger.warning(f"目錄不存在: {directory}")
        return []
        
    return [f for f in os.listdir(directory) if Path(directory / f).is_dir()]


def load_csv(file_path: str, skiprows: int = 0) -> Optional[pd.DataFrame]:
    """
    讀取CSV檔案為DataFrame，可選擇跳過開頭的行數
    
    Args:
        file_path: CSV檔案路徑
        skiprows: 要跳過的行數（預設為 0）
        
    Returns:
        Optional[DataFrame]: 讀取的DataFrame或None（如果讀取失敗）
    """
    try:
        return pd.read_csv(file_path, skiprows=skiprows)
    except pd.errors.ParserError:
        logger.warning(f"標準讀取CSV失敗: {file_path}, 嘗試替代方法...")

        try:
            with open(file_path, 'r') as f:
                first_line = f.readline().strip()

            if '\t' in first_line:
                sep = '\t'
            elif ',' in first_line:
                sep = ','
            elif ';' in first_line:
                sep = ';'
            else:
                sep = None

            if sep:
                df = pd.read_csv(file_path, sep=sep, skiprows=skiprows, on_bad_lines='skip')
                logger.info(f"使用分隔符 '{sep}' 成功讀取CSV: {file_path}")
                return df

            df = pd.read_csv(file_path, skiprows=skiprows, engine='python', on_bad_lines='skip')
            logger.info(f"使用Python引擎成功讀取CSV: {file_path}")
            return df

        except Exception as inner_e:
            logger.error(f"載入CSV檔案失敗: {file_path}, 錯誤: {str(inner_e)}")
            return None
    except Exception as e:
        logger.error(f"載入CSV檔案失敗: {file_path}, 錯誤: {str(e)}")
        return None



def find_header_row(csv_path, header_columns=None):
    """
    尋找CSV檔案中的標題行
    
    Args:
        csv_path: CSV檔案路徑
        header_columns: 標題行應包含的列名列表，默認為['Col', 'Row', 'DefectType']
    
    Returns:
        int: 標題行的索引，若找不到則返回None
    """
    if header_columns is None:
        header_columns = ['Col', 'Row', 'DefectType']
        
    try:
        with open(csv_path, 'r', encoding='utf-8-sig') as f:
            for i, line in enumerate(f):
                if all(col in line for col in header_columns):
                    return i
        return None
    except Exception as e:
        logger.error(f"查找標題行失敗: {csv_path}, 錯誤: {e}")
        return None


def save_df_to_csv(df, file_path, index=False, encoding='utf-8-sig'):
    """
    安全保存DataFrame到CSV檔案
    
    Args:
        df: 要保存的DataFrame
        file_path: 保存路徑
        index: 是否包含索引
        encoding: 檔案編碼
    
    Returns:
        bool: 是否成功保存
    """
    try:
        ensure_directory(Path(file_path).parent)
        df.to_csv(file_path, index=index, encoding=encoding)
        logger.info(f"成功保存CSV檔案: {file_path}")
        return True
    except Exception as e:
        logger.error(f"保存CSV檔案失敗: {file_path}, 錯誤: {e}")
        return False


def backup_file(file_path, backup_dir=None):
    """
    備份檔案
    
    Args:
        file_path: 要備份的檔案路徑
        backup_dir: 備份目錄，若未指定則使用原檔案目錄下的backup資料夾
    
    Returns:
        str: 備份檔案的路徑
    """
    file_path = Path(file_path)
    if not file_path.exists():
        logger.warning(f"要備份的檔案不存在: {file_path}")
        return None

    # 設定備份目錄
    if backup_dir is None:
        backup_dir = file_path.parent / "backup"
    
    backup_dir = Path(backup_dir)
    ensure_directory(backup_dir)
    
    # 生成備份檔名，添加時間戳
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_filename = f"{file_path.stem}_{timestamp}{file_path.suffix}"
    backup_path = backup_dir / backup_filename
    
    try:
        shutil.copy2(file_path, backup_path)
        logger.info(f"已備份檔案: {file_path} -> {backup_path}")
        return str(backup_path)
    except Exception as e:
        logger.error(f"備份檔案失敗: {file_path}, 錯誤: {e}")
        return None


def extract_component_from_filename(filename):
    """
    從AOI原始檔名提取component ID
    
    Args:
        filename: AOI檔案名，格式為 {device}_{component}_{timestamp}.csv
    
    Returns:
        str: 提取的component ID，若未匹配則返回None
    """
    match = AOI_FILENAME_PATTERN.match(filename)
    if match:
        return match.group(1)
    return None


def remove_header_and_rename(file_path, output_path=None, header_line_auto_detect=True, header_line=0):
    """
    移除CSV檔案的表頭並重命名（類似 header_reomve.py)
    
    Args:
        file_path: 原始CSV檔案路徑
        output_path: 輸出CSV檔案路徑，如果為None則根據原檔名推導
        header_line_auto_detect: 是否自動偵測標頭行
        header_line: 固定標頭行位置（若不自動偵測）
    
    Returns:
        Tuple[bool, str]: (成功狀態, 輸出檔案路徑或錯誤訊息)
    """
    try:
        file_path = Path(file_path)
        
        # 找到標頭行
        if header_line_auto_detect:
            header_row = find_header_row(file_path)
            if header_row is None:
                logger.warning(f"無法在檔案中找到標頭行: {file_path}")
                return False, "無法找到標頭行"
        else:
            header_row = header_line
            
        # 讀取CSV，跳過標頭前的行
        df = load_csv(file_path, skiprows=header_row)
        if df is None:
            return False, "讀取CSV失敗"
            
        # 如果未指定輸出路徑，使用component ID作為新檔名
        if output_path is None:
            component_id = extract_component_from_filename(file_path.name)
            if not component_id:
                component_id = file_path.stem  # 使用原始檔名（不含副檔名）
            output_path = file_path.parent / f"{component_id}.csv"
        
        # 保存處理後的檔案
        if save_df_to_csv(df, output_path):
            logger.info(f"成功處理表頭並重命名: {file_path} -> {output_path}")
            return True, str(output_path)
        else:
            return False, "儲存處理後的CSV失敗"
            
    except Exception as e:
        logger.error(f"移除表頭並重命名時發生錯誤: {e}")
        return False, f"處理失敗: {str(e)}" 