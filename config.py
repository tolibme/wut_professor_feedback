"""
Configuration management for WUT Feedback Bot.
Loads settings from environment variables with validation.
"""

import os
from pathlib import Path
from typing import List, Optional
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


class ConfigError(Exception):
    """Configuration validation error."""
    pass


class Config:
    """Application configuration loaded from environment variables."""
    
    # ----- Telegram Bot Tokens -----
    # Collector bot token is optional (userbot mode doesn't need it)
    TELEGRAM_BOT_TOKEN_COLLECTOR: str = os.getenv("TELEGRAM_BOT_TOKEN_COLLECTOR", "")
    TELEGRAM_BOT_TOKEN_QUERY: str = os.getenv("TELEGRAM_BOT_TOKEN_QUERY", "")
    
    # ----- Telegram API Credentials -----
    TELEGRAM_API_ID: int = int(os.getenv("TELEGRAM_API_ID", "0"))
    TELEGRAM_API_HASH: str = os.getenv("TELEGRAM_API_HASH", "")
    
    # ----- Feedback Group -----
    FEEDBACK_GROUP_ID: int = int(os.getenv("FEEDBACK_GROUP_ID", "0"))
    
    # ----- Gemini AI -----
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
    GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "")
    
    # ----- Database -----
    DATABASE_URL: str = os.getenv("DATABASE_URL", "postgresql://localhost:5432/wuit_feedback")
    
    # ----- ChromaDB -----
    CHROMA_PERSIST_DIR: str = os.getenv("CHROMA_PERSIST_DIR", "./chroma_data")
    
    # ----- Bot Settings -----
    BULK_IMPORT_LIMIT: int = int(os.getenv("BULK_IMPORT_LIMIT", "10000"))
    BULK_IMPORT_BATCH_SIZE: int = int(os.getenv("BULK_IMPORT_BATCH_SIZE", "100"))
    CHECK_INTERVAL_MINUTES: int = int(os.getenv("CHECK_INTERVAL_MINUTES", "30"))
    MONITOR_BATCH_SIZE: int = int(os.getenv("MONITOR_BATCH_SIZE", "50"))
    MONITOR_BATCH_INTERVAL_SECONDS: int = int(os.getenv("MONITOR_BATCH_INTERVAL_SECONDS", "30"))
    MIN_EXTRACTION_CONFIDENCE: float = float(os.getenv("MIN_EXTRACTION_CONFIDENCE", "0.7"))
    
    # ----- Admin Settings -----
    ADMIN_USER_IDS: List[int] = []
    
    # ----- Logging -----
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    LOG_FILE: str = os.getenv("LOG_FILE", "logs/bot.log")
    
    # ----- Paths -----
    BASE_DIR: Path = Path(__file__).parent.absolute()
    
    @classmethod
    def _parse_admin_ids(cls) -> List[int]:
        """Parse comma-separated admin user IDs."""
        admin_ids_str = os.getenv("ADMIN_USER_IDS", "")
        if not admin_ids_str:
            return []
        try:
            return [int(uid.strip()) for uid in admin_ids_str.split(",") if uid.strip()]
        except ValueError:
            return []
    
    @classmethod
    def load(cls) -> None:
        """Load and parse configuration."""
        cls.ADMIN_USER_IDS = cls._parse_admin_ids()
    
    @classmethod
    def validate(cls, mode: str = "both") -> None:
        """
        Validate configuration based on the mode.
        
        Args:
            mode: 'collector', 'query', or 'both'
        
        Raises:
            ConfigError: If required configuration is missing
        """
        cls.load()
        errors = []
        
        # Common validations
        if not cls.GEMINI_API_KEY:
            errors.append("GEMINI_API_KEY is required")
        
        if not cls.DATABASE_URL:
            errors.append("DATABASE_URL is required")
        
        # Collector-specific validations (userbot mode)
        if mode in ("collector", "userbot", "both"):
            if not cls.TELEGRAM_API_ID or cls.TELEGRAM_API_ID == 0:
                errors.append("TELEGRAM_API_ID is required for collector mode")
            
            if not cls.TELEGRAM_API_HASH:
                errors.append("TELEGRAM_API_HASH is required for collector mode")
            
            if not cls.FEEDBACK_GROUP_ID or cls.FEEDBACK_GROUP_ID == 0:
                errors.append("FEEDBACK_GROUP_ID is required for collector mode")
        
        # Query-specific validations
        if mode in ("query", "both"):
            if not cls.TELEGRAM_BOT_TOKEN_QUERY:
                errors.append("TELEGRAM_BOT_TOKEN_QUERY is required for query mode")
        
        if errors:
            raise ConfigError("Configuration errors:\n" + "\n".join(f"  - {e}" for e in errors))
    
    @classmethod
    def is_admin(cls, user_id: int) -> bool:
        """Check if a user ID is an admin."""
        return user_id in cls.ADMIN_USER_IDS
    
    @classmethod
    def get_session_path(cls) -> Path:
        """Get the path for Telethon session file."""
        return cls.BASE_DIR / "collector_session"
    
    @classmethod
    def ensure_directories(cls) -> None:
        """Ensure required directories exist."""
        # Logs directory
        log_dir = Path(cls.LOG_FILE).parent
        log_dir.mkdir(parents=True, exist_ok=True)
        
        # ChromaDB directory
        chroma_dir = Path(cls.CHROMA_PERSIST_DIR)
        chroma_dir.mkdir(parents=True, exist_ok=True)
