"""
日誌管理模塊，提供統一的日誌記錄功能
"""
import os
import logging
import logging.handlers
from pathlib import Path
from .config_manager import config


class LoggerManager:
    """日誌管理器，提供統一的日誌設置和獲取方法"""
    
    _instance = None  # 單例實例
    _loggers = {}  # 已創建的日誌器緩存
    
    def __new__(cls):
        """實現單例模式"""
        if cls._instance is None:
            cls._instance = super(LoggerManager, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        """初始化日誌管理器"""
        if self._initialized:
            return
        
        self._initialized = True
        self.log_dir = Path(config.get("logging.log_dir", "logs"))
        self.log_level = getattr(logging, config.get("logging.level", "INFO"))
        self.log_format = config.get("logging.log_format", 
                                   "%(asctime)s - %(name)s - %(levelname)s - %(message)s")
        self.max_size = config.get("logging.max_size", 10485760)  # 10MB
        self.backup_count = config.get("logging.backup_count", 10)
        
        # 確保日誌目錄存在
        os.makedirs(self.log_dir, exist_ok=True)
        
        # 配置根日誌器
        self._configure_root_logger()
    
    def _configure_root_logger(self):
        """配置根日誌器"""
        # 創建根日誌器
        root_logger = logging.getLogger()
        root_logger.setLevel(self.log_level)
        
        # 清除現有處理器
        for handler in root_logger.handlers[:]:
            root_logger.removeHandler(handler)
        
        # 創建並添加控制台處理器
        console_handler = logging.StreamHandler()
        console_handler.setLevel(self.log_level)
        console_formatter = logging.Formatter(self.log_format)
        console_handler.setFormatter(console_formatter)
        root_logger.addHandler(console_handler)
        
        # 創建並添加文件處理器
        log_file = self.log_dir / "app.log"
        file_handler = logging.handlers.RotatingFileHandler(
            log_file, maxBytes=self.max_size, backupCount=self.backup_count,
            encoding='utf-8'
        )
        file_handler.setLevel(self.log_level)
        file_formatter = logging.Formatter(self.log_format)
        file_handler.setFormatter(file_formatter)
        root_logger.addHandler(file_handler)
    
    def get_logger(self, name):
        """獲取指定名稱的日誌器
        
        Args:
            name: 日誌器名稱
            
        Returns:
            配置好的日誌器實例
        """
        if name in self._loggers:
            return self._loggers[name]
        
        logger = logging.getLogger(name)
        
        # 為特定模塊創建專用日誌文件
        if name in ["data_processor", "ui_controller"]:
            log_file = self.log_dir / f"{name}.log"
            handler = logging.handlers.RotatingFileHandler(
                log_file, maxBytes=self.max_size, backupCount=self.backup_count,
                encoding='utf-8'
            )
            handler.setLevel(self.log_level)
            formatter = logging.Formatter(self.log_format)
            handler.setFormatter(formatter)
            logger.addHandler(handler)
        
        self._loggers[name] = logger
        return logger


# 創建全局日誌管理器實例
logger_manager = LoggerManager()


def get_logger(name):
    """獲取日誌器的便捷方法"""
    return logger_manager.get_logger(name)


def setup_logging():
    """
    設置應用程序日誌系統
    
    此函數應在應用程序啟動時調用，確保日誌系統正確初始化
    """
    # 確保日誌管理器已初始化
    global logger_manager
    if not logger_manager._initialized:
        logger_manager = LoggerManager()
    
    # 獲取主日誌器並記錄啟動信息
    logger = get_logger("main")
    logger.info("日誌系統已初始化")
    
    return logger 