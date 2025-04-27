"""
Database Manager Plus 應用程式包
"""
import os
import sys
from pathlib import Path

# 添加應用目錄到路徑，確保可以正確 import
app_path = Path(__file__).parent.parent
if str(app_path) not in sys.path:
    sys.path.insert(0, str(app_path))

# 創建必要的文件夾結構
def ensure_app_directories():
    """確保應用所需的目錄結構存在"""
    dirs = [
        app_path / "data",
        app_path / "logs",
        app_path / "resources"
    ]
    for dir_path in dirs:
        os.makedirs(dir_path, exist_ok=True)

# 確保在應用載入時即建立所需的資料夾
ensure_app_directories()

__version__ = "1.0.0" 