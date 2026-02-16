"""
SQLAlchemy database models for WUT Feedback Bot.

Tables:
- Professor: Professor information and aggregate statistics
- Feedback: Individual feedback entries with extracted data
- ProcessedMessage: Track which Telegram messages have been processed
- BulkImportLog: Track bulk import operations
- UserQuery: Log of user queries for analytics
"""

from datetime import datetime
from typing import Optional, List, Dict, Any

from sqlalchemy import (
    create_engine,
    Column,
    Integer,
    BigInteger,
    String,
    Text,
    Float,
    Boolean,
    DateTime,
    ForeignKey,
    JSON,
    ARRAY,
    Index,
    UniqueConstraint,
)
from sqlalchemy.orm import declarative_base, relationship, sessionmaker
from sqlalchemy.sql import func

Base = declarative_base()


class Professor(Base):
    """
    Professor entity with aggregate statistics.
    
    Stores professor information and calculated metrics from all feedbacks.
    """
    __tablename__ = 'professors'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False, unique=True, index=True)
    name_normalized = Column(String(255), nullable=False, index=True)  # Lowercase, standardized
    department = Column(String(255), nullable=True)
    courses = Column(ARRAY(String), default=list)  # List of course codes
    
    # Aggregate statistics (updated when feedbacks change)
    overall_rating = Column(Float, default=0.0)
    total_feedbacks = Column(Integer, default=0)
    positive_feedbacks = Column(Integer, default=0)
    negative_feedbacks = Column(Integer, default=0)
    neutral_feedbacks = Column(Integer, default=0)
    
    # Aspect averages
    avg_teaching_quality = Column(Float, nullable=True)
    avg_grading_fairness = Column(Float, nullable=True)
    avg_workload = Column(Float, nullable=True)
    avg_communication = Column(Float, nullable=True)
    avg_engagement = Column(Float, nullable=True)
    avg_exams_difficulty = Column(Float, nullable=True)
    
    # Timestamps
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    
    # Relationships
    feedbacks = relationship("Feedback", back_populates="professor", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<Professor(id={self.id}, name='{self.name}', rating={self.overall_rating:.1f})>"


class Feedback(Base):
    """
    Individual feedback entry.
    
    Stores original message and all extracted/analyzed data.
    """
    __tablename__ = 'feedbacks'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    professor_id = Column(Integer, ForeignKey('professors.id'), nullable=False, index=True)
    
    # Original data
    original_message = Column(Text, nullable=False)
    telegram_message_id = Column(BigInteger, nullable=False, unique=True, index=True)
    telegram_user_id = Column(BigInteger, nullable=True)
    message_date = Column(DateTime, nullable=True)
    
    # Extracted course info
    course_code = Column(String(50), nullable=True, index=True)
    course_name = Column(String(255), nullable=True)
    semester = Column(String(50), nullable=True)
    
    # Ratings and sentiment
    explicit_rating = Column(Float, nullable=True)  # Rating explicitly mentioned
    inferred_rating = Column(Float, nullable=True)  # Rating inferred from content
    final_rating = Column(Float, nullable=True)  # Used rating (explicit or inferred)
    sentiment = Column(String(20), nullable=True)  # positive, negative, neutral, mixed
    
    # Detailed aspects (JSON structure)
    # Structure: {"aspect_name": {"score": 1-5, "comment": "..."}}
    aspects = Column(JSON, default=dict)
    
    # Extracted points
    strengths = Column(JSON, default=list)  # List of strength points
    weaknesses = Column(JSON, default=list)  # List of weakness points
    
    # Extraction metadata
    extraction_confidence = Column(Float, default=0.0)
    is_appropriate = Column(Boolean, default=True)
    detected_language = Column(String(10), nullable=True)  # en, ru, uz
    
    # Timestamps
    created_at = Column(DateTime, default=func.now())
    
    # Relationships
    professor = relationship("Professor", back_populates="feedbacks")
    
    # Indexes
    __table_args__ = (
        Index('idx_feedback_sentiment', 'sentiment'),
        Index('idx_feedback_created', 'created_at'),
    )
    
    def __repr__(self):
        return f"<Feedback(id={self.id}, professor_id={self.professor_id}, rating={self.final_rating})>"


class ProcessedMessage(Base):
    """
    Track processed Telegram messages.
    
    Used to avoid duplicate processing and to track which messages
    were identified as feedback vs. non-feedback.
    """
    __tablename__ = 'processed_messages'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    telegram_message_id = Column(BigInteger, nullable=False, unique=True, index=True)
    
    # Processing results
    is_feedback = Column(Boolean, default=False)
    feedback_id = Column(Integer, ForeignKey('feedbacks.id'), nullable=True)
    
    # Processing metadata
    processed_at = Column(DateTime, default=func.now())
    processing_error = Column(Text, nullable=True)
    
    def __repr__(self):
        return f"<ProcessedMessage(telegram_id={self.telegram_message_id}, is_feedback={self.is_feedback})>"


class TelegramUser(Base):
    """
    Store Telegram user info observed in messages.
    """
    __tablename__ = 'telegram_users'

    id = Column(Integer, primary_key=True, autoincrement=True)
    telegram_user_id = Column(BigInteger, nullable=False, unique=True, index=True)
    username = Column(String(255), nullable=True)
    display_name = Column(String(255), nullable=True)
    first_name = Column(String(255), nullable=True)
    last_name = Column(String(255), nullable=True)

    created_at = Column(DateTime, default=func.now())
    last_seen_at = Column(DateTime, default=func.now(), onupdate=func.now())

    def __repr__(self):
        return f"<TelegramUser(telegram_user_id={self.telegram_user_id}, username={self.username})>"


class BulkImportLog(Base):
    """
    Log bulk import operations.
    
    Tracks progress and results of bulk message imports.
    """
    __tablename__ = 'bulk_import_logs'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # Timing
    started_at = Column(DateTime, default=func.now())
    completed_at = Column(DateTime, nullable=True)
    
    # Statistics
    total_messages = Column(Integer, default=0)
    processed_messages = Column(Integer, default=0)
    feedbacks_created = Column(Integer, default=0)
    professors_created = Column(Integer, default=0)
    errors_count = Column(Integer, default=0)
    
    # Status: 'running', 'completed', 'failed', 'cancelled'
    status = Column(String(20), default='running')
    error_message = Column(Text, nullable=True)
    
    # Progress tracking
    last_processed_message_id = Column(BigInteger, nullable=True)
    
    def __repr__(self):
        return f"<BulkImportLog(id={self.id}, status='{self.status}', feedbacks={self.feedbacks_created})>"
    
    @property
    def duration_minutes(self) -> Optional[float]:
        """Calculate duration in minutes."""
        if self.completed_at and self.started_at:
            delta = self.completed_at - self.started_at
            return delta.total_seconds() / 60
        return None


class UserQuery(Base):
    """
    Log user queries for analytics.
    
    Tracks what students are searching for and the responses given.
    """
    __tablename__ = 'user_queries'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # User info
    telegram_user_id = Column(BigInteger, nullable=True)
    
    # Query details
    query_text = Column(Text, nullable=False)
    query_type = Column(String(50), nullable=True)  # search, compare, course, natural
    
    # Response
    response_text = Column(Text, nullable=True)
    professors_mentioned = Column(ARRAY(String), default=list)
    
    # Metadata
    response_time_ms = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=func.now())
    
    def __repr__(self):
        return f"<UserQuery(id={self.id}, query='{self.query_text[:50]}...')>"


# Database engine and session factory
_engine = None
_SessionLocal = None


def get_engine(database_url: str = None):
    """Get or create database engine."""
    global _engine
    if _engine is None:
        if database_url is None:
            from config import Config
            database_url = Config.DATABASE_URL
        _engine = create_engine(database_url, pool_pre_ping=True)
    return _engine


def get_session_factory(database_url: str = None):
    """Get or create session factory."""
    global _SessionLocal
    if _SessionLocal is None:
        engine = get_engine(database_url)
        _SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    return _SessionLocal


def create_all_tables(database_url: str = None):
    """Create all database tables."""
    engine = get_engine(database_url)
    Base.metadata.create_all(bind=engine)


def drop_all_tables(database_url: str = None):
    """Drop all database tables (use with caution!)."""
    engine = get_engine(database_url)
    Base.metadata.drop_all(bind=engine)
