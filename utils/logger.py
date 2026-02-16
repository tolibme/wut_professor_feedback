"""
Logging configuration for WUT Feedback Bot.

Provides structured logging with file and console output.
"""

import logging
import sys
from pathlib import Path
from typing import Optional

# Default format
LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# Logger cache
_loggers = {}
_initialized = False


def setup_logging(
    log_level: str = "INFO",
    log_file: Optional[str] = None,
) -> None:
    """
    Setup logging configuration.
    
    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_file: Optional file path for log output
    """
    global _initialized
    
    if _initialized:
        return
    
    # Get numeric level
    numeric_level = getattr(logging, log_level.upper(), logging.INFO)
    
    # Create root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(numeric_level)
    
    # Clear existing handlers
    root_logger.handlers.clear()
    
    # Create formatter
    formatter = logging.Formatter(LOG_FORMAT, DATE_FORMAT)
    
    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(numeric_level)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)
    
    # File handler
    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        
        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_handler.setLevel(numeric_level)
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)
    
    # Reduce noise from third-party libraries
    logging.getLogger('httpx').setLevel(logging.WARNING)
    logging.getLogger('httpcore').setLevel(logging.WARNING)
    logging.getLogger('telethon').setLevel(logging.WARNING)
    logging.getLogger('chromadb').setLevel(logging.WARNING)
    logging.getLogger('sentence_transformers').setLevel(logging.WARNING)
    
    _initialized = True


def get_logger(name: str) -> logging.Logger:
    """
    Get a logger by name.
    
    Initializes logging if not already done.
    
    Args:
        name: Logger name (usually __name__)
    
    Returns:
        Logger instance
    """
    global _loggers
    
    if not _initialized:
        # Default initialization
        try:
            from config import Config
            setup_logging(Config.LOG_LEVEL, Config.LOG_FILE)
        except Exception:
            setup_logging()
    
    if name not in _loggers:
        _loggers[name] = logging.getLogger(name)
    
    return _loggers[name]


class LogContext:
    """Context manager for adding context to log messages."""
    
    def __init__(self, logger: logging.Logger, **context):
        """
        Initialize log context.
        
        Args:
            logger: Logger to use
            **context: Context key-value pairs
        """
        self.logger = logger
        self.context = context
        self._old_factory = None
    
    def __enter__(self):
        """Enter context - add extra context to logs."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Exit context."""
        pass
    
    def info(self, message: str):
        """Log info with context."""
        self.logger.info(f"{message} | {self._format_context()}")
    
    def debug(self, message: str):
        """Log debug with context."""
        self.logger.debug(f"{message} | {self._format_context()}")
    
    def warning(self, message: str):
        """Log warning with context."""
        self.logger.warning(f"{message} | {self._format_context()}")
    
    def error(self, message: str):
        """Log error with context."""
        self.logger.error(f"{message} | {self._format_context()}")
    
    def _format_context(self) -> str:
        """Format context as string."""
        return " ".join(f"{k}={v}" for k, v in self.context.items())
