"""
配置管理模塊，負責讀取、處理和提供應用程式配置
"""
import os
import json
import logging
from pathlib import Path


class ConfigManager:
    """配置管理器，提供獲取配置的各種方法和實用功能"""
    
    _instance = None  # 單例實例
    
    def __new__(cls):
        """實現單例模式"""
        if cls._instance is None:
            cls._instance = super(ConfigManager, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        """初始化配置管理器，只在第一次實例化時執行"""
        if self._initialized:
            return
        
        self._initialized = True
        self.logger = logging.getLogger("config_manager")
        self.config = {}
        self.config_file = Path(__file__).parent.parent.parent / "config" / "settings.json"
        self.load_config()

    def load_config(self):
        """載入配置文件"""
        try:
            if not self.config_file.exists():
                self.logger.error(f"配置文件不存在: {self.config_file}")
                raise FileNotFoundError(f"配置文件不存在: {self.config_file}")
                
            with open(self.config_file, 'r', encoding='utf-8') as f:
                self.config = json.load(f)
                
            self.logger.info(f"成功載入配置文件: {self.config_file}")
        except Exception as e:
            self.logger.error(f"載入配置文件失敗: {e}")
            raise

    def save_config(self):
        """保存配置到文件"""
        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, indent=4, ensure_ascii=False)
            self.logger.info(f"配置已保存到: {self.config_file}")
        except Exception as e:
            self.logger.error(f"保存配置失敗: {e}")
            raise

    def get(self, key, default=None):
        """獲取配置值，支援使用點號分隔的鍵路徑"""
        if '.' not in key:
            return self.config.get(key, default)
        
        # 處理多層級配置(如 "database.base_path")
        parts = key.split('.')
        value = self.config
        for part in parts:
            if isinstance(value, dict) and part in value:
                value = value[part]
            else:
                return default
        return value

    def get_path(self, path_key, **format_args):
        """獲取格式化的路徑配置並替換變數
        
        Args:
            path_key: 路徑配置鍵，例如 "database.structure.csv"
            **format_args: 用於格式化路徑的參數
        
        Returns:
            格式化後的完整路徑
        """
        # 獲取原始路徑模板
        path_template = self.get(path_key)
        if not path_template:
            self.logger.error(f"找不到路徑配置: {path_key}")
            return None
            
        # 添加基礎路徑到格式化參數
        if "base_path" not in format_args:
            format_args["base_path"] = self.get("database.base_path")
            
        # 格式化路徑
        try:
            formatted_path = path_template.format(**format_args)
            return formatted_path
        except KeyError as e:
            self.logger.error(f"格式化路徑失敗，缺少參數: {e}")
            return None

    def update(self, key, value):
        """更新配置的特定部分"""
        if '.' not in key:
            self.config[key] = value
            return
            
        # 處理多層級配置更新
        parts = key.split('.')
        config_section = self.config
        
        # 導航到最後一層
        for part in parts[:-1]:
            if part not in config_section:
                config_section[part] = {}
            config_section = config_section[part]
                
        # 設置值
        config_section[parts[-1]] = value
        self.logger.info(f"已更新配置: {key}")


# 提供便捷的配置訪問方式
config = ConfigManager()


def load_config():
    """
    重新載入全局配置
    
    此函數供外部模塊調用，確保配置已被重新載入
    """
    global config
    if not config._initialized:
        config = ConfigManager()
    else:
        config.load_config()
    
    return config 