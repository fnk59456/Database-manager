import os
import sys
import logging
import logging.handlers
from pathlib import Path

# ---------------------- [可選設定] ----------------------

DEFAULT_LOG_CONFIG = {
    "log_dir": "logs",
    "level": "INFO",
    "log_format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    "max_size": 10 * 1024 * 1024,  # 10 MB
    "backup_count": 5
}

# ---------------------- [工具函數] ----------------------

def get_base_dir() -> Path:
    """取得主程式或執行檔所在目錄"""
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).parent
    return Path(sys.argv[0]).resolve().parent

def resolve_log_dir(config_dir: str) -> Path:
    """依據相對或絕對路徑建立 log 目錄"""
    raw_path = Path(config_dir)
    if raw_path.is_absolute():
        return raw_path
    return get_base_dir() / raw_path

# ---------------------- [Logger 管理器] ----------------------

class LoggerManager:
    """日誌管理器（單例）"""

    _instance = None
    _loggers = {}

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(LoggerManager, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self, config: dict = None):
        if self._initialized:
            return
        self._initialized = True

        cfg = config or DEFAULT_LOG_CONFIG

        self.log_dir = resolve_log_dir(cfg.get("log_dir", "logs"))
        self.log_level = getattr(logging, cfg.get("level", "INFO").upper(), logging.INFO)
        self.log_format = cfg.get("log_format", DEFAULT_LOG_CONFIG["log_format"])
        self.max_size = cfg.get("max_size", DEFAULT_LOG_CONFIG["max_size"])
        self.backup_count = cfg.get("backup_count", DEFAULT_LOG_CONFIG["backup_count"])

        os.makedirs(self.log_dir, exist_ok=True)
        self._configure_root_logger()

    def _configure_root_logger(self):
        root_logger = logging.getLogger()
        root_logger.setLevel(self.log_level)

        # 移除舊的 handler
        for handler in root_logger.handlers[:]:
            root_logger.removeHandler(handler)

        # Console handler
        console_handler = logging.StreamHandler()
        console_handler.setLevel(self.log_level)
        console_handler.setFormatter(logging.Formatter(self.log_format))
        root_logger.addHandler(console_handler)

        # File handler
        file_handler = logging.handlers.RotatingFileHandler(
            self.log_dir / "app.log",
            maxBytes=self.max_size,
            backupCount=self.backup_count,
            encoding="utf-8"
        )
        file_handler.setLevel(self.log_level)
        file_handler.setFormatter(logging.Formatter(self.log_format))
        root_logger.addHandler(file_handler)

    def get_logger(self, name: str):
        """取得指定 logger（可為模組名）"""
        if name in self._loggers:
            return self._loggers[name]

        logger = logging.getLogger(name)
        logger.setLevel(self.log_level)

        # 讓特殊模組寫入獨立檔案
        if name in ["data_processor", "ui_controller"]:
            handler = logging.handlers.RotatingFileHandler(
                self.log_dir / f"{name}.log",
                maxBytes=self.max_size,
                backupCount=self.backup_count,
                encoding="utf-8"
            )
            handler.setFormatter(logging.Formatter(self.log_format))
            logger.addHandler(handler)

        self._loggers[name] = logger
        return logger

# ---------------------- [外部存取接口] ----------------------

logger_manager = LoggerManager()

def get_logger(name: str):
    return logger_manager.get_logger(name)

def setup_logging():
    logger = get_logger("main")
    logger.info("日誌系統初始化成功")
    return logger

