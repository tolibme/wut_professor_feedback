"""
Database service for WUT Feedback Bot.

Provides all database operations including CRUD, fuzzy search,
statistics calculation, and duplicate tracking.
"""

import asyncio
from contextlib import contextmanager
from datetime import datetime
from typing import Optional, List, Dict, Any, Tuple, Generator

from sqlalchemy import select, update, func, or_, and_
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session
from rapidfuzz import fuzz, process

from models.database_models import (
    Professor,
    Feedback,
    ProcessedMessage,
    TelegramUser,
    BulkImportLog,
    UserQuery,
    get_session_factory,
    create_all_tables,
)
from utils.text_processing import normalize_professor_name
from utils.logger import get_logger

logger = get_logger(__name__)


class DatabaseService:
    """
    Service class for all database operations.
    
    Handles professor management, feedback storage, message tracking,
    and statistics calculation.
    """
    
    def __init__(self, database_url: str = None):
        """Initialize database service."""
        self._session_factory = get_session_factory(database_url)
    
    @contextmanager
    def get_session(self) -> Generator[Session, None, None]:
        """Get a database session with automatic cleanup."""
        session = self._session_factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()
    
    # ==================== Initialization ====================
    
    def initialize_database(self) -> None:
        """Create all tables if they don't exist."""
        create_all_tables()
        logger.info("Database tables initialized")

    # ==================== User Operations ====================

    def upsert_telegram_user(
        self,
        telegram_user_id: int,
        username: str = None,
        display_name: str = None,
        first_name: str = None,
        last_name: str = None,
    ) -> TelegramUser:
        """Insert or update a Telegram user record."""
        with self.get_session() as session:
            user = session.query(TelegramUser).filter(
                TelegramUser.telegram_user_id == telegram_user_id
            ).first()

            if user:
                user.username = username or user.username
                user.display_name = display_name or user.display_name
                user.first_name = first_name or user.first_name
                user.last_name = last_name or user.last_name
            else:
                user = TelegramUser(
                    telegram_user_id=telegram_user_id,
                    username=username,
                    display_name=display_name,
                    first_name=first_name,
                    last_name=last_name,
                )
                session.add(user)

            session.flush()
            session.expunge(user)
            return user
    
    # ==================== Professor Operations ====================
    
    def find_professor_by_name(self, name: str) -> Optional[Professor]:
        """Find a professor by exact name match (case-insensitive)."""
        normalized = normalize_professor_name(name)
        with self.get_session() as session:
            professor = session.query(Professor).filter(
                Professor.name_normalized == normalized
            ).first()
            if professor:
                session.expunge(professor)
            return professor
    
    def search_professor_fuzzy(
        self, 
        name: str, 
        threshold: int = 70
    ) -> Optional[Professor]:
        """
        Find a professor using fuzzy name matching.
        
        Args:
            name: Professor name to search for
            threshold: Minimum match score (0-100)
        
        Returns:
            Best matching professor or None
        """
        with self.get_session() as session:
            professors = session.query(Professor).all()
            if not professors:
                return None
            
            # Create list of (normalized_name, professor) for matching
            choices = [(normalize_professor_name(p.name), p) for p in professors]
            name_normalized = normalize_professor_name(name)
            
            # Find best match
            result = process.extractOne(
                name_normalized,
                [c[0] for c in choices],
                scorer=fuzz.token_sort_ratio
            )
            
            if result and result[1] >= threshold:
                matched_name = result[0]
                for norm_name, professor in choices:
                    if norm_name == matched_name:
                        session.expunge(professor)
                        return professor
            
            return None
    
    def find_or_create_professor(
        self, 
        name: str, 
        department: str = None
    ) -> Tuple[Professor, bool]:
        """
        Find existing professor or create new one.
        
        Uses fuzzy matching to find existing professors with similar names.
        
        Args:
            name: Professor name
            department: Optional department
        
        Returns:
            Tuple of (Professor, was_created)
        """
        # First try exact match
        professor = self.find_professor_by_name(name)
        if professor:
            return professor, False
        
        # Try fuzzy match
        professor = self.search_professor_fuzzy(name, threshold=85)
        if professor:
            return professor, False
        
        # Create new professor
        normalized = normalize_professor_name(name)
        with self.get_session() as session:
            professor = Professor(
                name=name.strip(),
                name_normalized=normalized,
                department=department,
                courses=[],
                overall_rating=0.0,
                total_feedbacks=0,
                positive_feedbacks=0,
                negative_feedbacks=0,
                neutral_feedbacks=0,
            )
            session.add(professor)
            session.flush()
            session.expunge(professor)
            logger.info(f"Created new professor: {professor.name}")
            return professor, True
    
    def get_professor_by_id(self, professor_id: int) -> Optional[Professor]:
        """Get professor by ID."""
        with self.get_session() as session:
            professor = session.query(Professor).filter(
                Professor.id == professor_id
            ).first()
            if professor:
                session.expunge(professor)
            return professor
    
    def get_all_professors(self) -> List[Professor]:
        """Get all professors."""
        with self.get_session() as session:
            professors = session.query(Professor).all()
            for p in professors:
                session.expunge(p)
            return professors
    
    def add_course_to_professor(self, professor_id: int, course_code: str) -> None:
        """Add a course code to professor's course list."""
        with self.get_session() as session:
            professor = session.query(Professor).filter(
                Professor.id == professor_id
            ).first()
            if professor and course_code:
                if course_code not in (professor.courses or []):
                    courses = list(professor.courses or [])
                    courses.append(course_code)
                    professor.courses = courses
    
    def update_professor_statistics(self, professor_id: int) -> None:
        """
        Recalculate and update professor statistics from feedbacks.
        
        Updates: overall_rating, total_feedbacks, sentiment counts,
        and aspect averages.
        """
        with self.get_session() as session:
            professor = session.query(Professor).filter(
                Professor.id == professor_id
            ).first()
            
            if not professor:
                return
            
            # Get all feedbacks for this professor
            feedbacks = session.query(Feedback).filter(
                Feedback.professor_id == professor_id
            ).all()
            
            if not feedbacks:
                return
            
            # Calculate counts
            professor.total_feedbacks = len(feedbacks)
            professor.positive_feedbacks = sum(1 for f in feedbacks if f.sentiment == 'positive')
            professor.negative_feedbacks = sum(1 for f in feedbacks if f.sentiment == 'negative')
            professor.neutral_feedbacks = sum(1 for f in feedbacks if f.sentiment in ('neutral', 'mixed'))
            
            # Calculate average rating
            ratings = [f.final_rating for f in feedbacks if f.final_rating is not None]
            if ratings:
                professor.overall_rating = sum(ratings) / len(ratings)
            
            # Calculate aspect averages
            aspect_sums = {
                'teaching_quality': [],
                'grading_fairness': [],
                'workload': [],
                'communication': [],
                'engagement': [],
                'exams_difficulty': [],
            }
            
            for feedback in feedbacks:
                if feedback.aspects:
                    for aspect_name, values in feedback.aspects.items():
                        if aspect_name in aspect_sums and isinstance(values, dict):
                            score = values.get('score')
                            if score is not None:
                                aspect_sums[aspect_name].append(score)
            
            professor.avg_teaching_quality = self._safe_average(aspect_sums['teaching_quality'])
            professor.avg_grading_fairness = self._safe_average(aspect_sums['grading_fairness'])
            professor.avg_workload = self._safe_average(aspect_sums['workload'])
            professor.avg_communication = self._safe_average(aspect_sums['communication'])
            professor.avg_engagement = self._safe_average(aspect_sums['engagement'])
            professor.avg_exams_difficulty = self._safe_average(aspect_sums['exams_difficulty'])
            
            logger.info(f"Updated statistics for professor {professor.name}: "
                       f"rating={professor.overall_rating:.2f}, feedbacks={professor.total_feedbacks}")
    
    @staticmethod
    def _safe_average(values: List[float]) -> Optional[float]:
        """Calculate average or return None if empty."""
        return sum(values) / len(values) if values else None
    
    # ==================== Feedback Operations ====================
    
    def create_feedback(
        self,
        professor_id: int,
        original_message: str,
        telegram_message_id: int,
        extracted_data: Dict[str, Any],
        telegram_user_id: int = None,
        message_date: datetime = None,
    ) -> Feedback:
        """
        Create a new feedback entry.
        
        Args:
            professor_id: ID of the professor
            original_message: Original message text
            telegram_message_id: Telegram message ID
            extracted_data: Extracted data from Gemini
            telegram_user_id: Optional user ID
            message_date: Optional message timestamp
        
        Returns:
            Created Feedback object
        """
        with self.get_session() as session:
            # Determine final rating
            explicit = extracted_data.get('explicit_rating')
            inferred = extracted_data.get('inferred_rating')
            final_rating = explicit if explicit is not None else inferred

            values = {
                "professor_id": professor_id,
                "original_message": original_message,
                "telegram_message_id": telegram_message_id,
                "telegram_user_id": telegram_user_id,
                "message_date": message_date,
                "course_code": extracted_data.get('course_code'),
                "course_name": extracted_data.get('course_name'),
                "semester": extracted_data.get('semester'),
                "explicit_rating": explicit,
                "inferred_rating": inferred,
                "final_rating": final_rating,
                "sentiment": extracted_data.get('sentiment'),
                "aspects": extracted_data.get('aspects', {}),
                "strengths": extracted_data.get('strengths', []),
                "weaknesses": extracted_data.get('weaknesses', []),
                "extraction_confidence": extracted_data.get('confidence', 0.0),
                "is_appropriate": extracted_data.get('is_appropriate', True),
                "detected_language": extracted_data.get('language'),
            }

            stmt = insert(Feedback).values(**values).on_conflict_do_update(
                index_elements=[Feedback.telegram_message_id],
                set_=values,
            ).returning(Feedback.id)

            result = session.execute(stmt).first()
            feedback_id = result[0] if result else None

            feedback = None
            if feedback_id:
                feedback = session.query(Feedback).filter(
                    Feedback.id == feedback_id
                ).first()
            else:
                feedback = session.query(Feedback).filter(
                    Feedback.telegram_message_id == telegram_message_id
                ).first()

            if feedback:
                session.expunge(feedback)
                logger.info(f"Created feedback {feedback.id} for professor {professor_id}")
                return feedback

            return None
    
    def get_professor_feedbacks(
        self, 
        professor_id: int, 
        limit: int = 20
    ) -> List[Feedback]:
        """Get recent feedbacks for a professor."""
        with self.get_session() as session:
            feedbacks = session.query(Feedback).filter(
                Feedback.professor_id == professor_id
            ).order_by(Feedback.created_at.desc()).limit(limit).all()
            
            for f in feedbacks:
                session.expunge(f)
            return feedbacks
    
    def get_feedbacks_by_course(
        self, 
        course_code: str, 
        limit: int = 50
    ) -> List[Feedback]:
        """Get feedbacks for a specific course."""
        with self.get_session() as session:
            feedbacks = session.query(Feedback).filter(
                Feedback.course_code.ilike(f"%{course_code}%")
            ).order_by(Feedback.created_at.desc()).limit(limit).all()
            
            for f in feedbacks:
                session.expunge(f)
            return feedbacks
    
    # ==================== Processed Message Tracking ====================
    
    def is_message_processed(self, telegram_message_id: int) -> bool:
        """Check if a message has already been processed."""
        with self.get_session() as session:
            exists = session.query(ProcessedMessage).filter(
                ProcessedMessage.telegram_message_id == telegram_message_id
            ).first() is not None
            return exists
    
    def mark_message_processed(
        self,
        telegram_message_id: int,
        is_feedback: bool,
        feedback_id: int = None,
        error: str = None,
    ) -> ProcessedMessage:
        """Mark a message as processed."""
        with self.get_session() as session:
            stmt = insert(ProcessedMessage).values(
                telegram_message_id=telegram_message_id,
                is_feedback=is_feedback,
                feedback_id=feedback_id,
                processing_error=error,
            ).on_conflict_do_update(
                index_elements=[ProcessedMessage.telegram_message_id],
                set_={
                    "is_feedback": is_feedback,
                    "feedback_id": feedback_id,
                    "processing_error": error,
                    "processed_at": func.now(),
                },
            ).returning(ProcessedMessage.id)

            result = session.execute(stmt).first()
            processed_id = result[0] if result else None

            if processed_id:
                processed = session.query(ProcessedMessage).filter(
                    ProcessedMessage.id == processed_id
                ).first()
                if processed:
                    session.expunge(processed)
                    return processed

            # Fallback: fetch by telegram_message_id
            processed = session.query(ProcessedMessage).filter(
                ProcessedMessage.telegram_message_id == telegram_message_id
            ).first()
            if processed:
                session.expunge(processed)
            return processed
    
    def get_last_processed_message_id(self) -> Optional[int]:
        """Get the ID of the most recently processed message."""
        with self.get_session() as session:
            result = session.query(
                func.max(ProcessedMessage.telegram_message_id)
            ).scalar()
            return result
    
    def get_processed_message_count(self) -> int:
        """Get total count of processed messages."""
        with self.get_session() as session:
            return session.query(ProcessedMessage).count()
    
    def get_feedback_count(self) -> int:
        """Get total count of feedbacks."""
        with self.get_session() as session:
            return session.query(Feedback).count()
    
    # ==================== Bulk Import Logging ====================
    
    def create_bulk_import_log(self) -> BulkImportLog:
        """Create a new bulk import log entry."""
        with self.get_session() as session:
            log = BulkImportLog(status='running')
            session.add(log)
            session.flush()
            session.expunge(log)
            logger.info(f"Created bulk import log {log.id}")
            return log
    
    def update_bulk_import_progress(
        self,
        log_id: int,
        processed_messages: int = None,
        feedbacks_created: int = None,
        professors_created: int = None,
        errors_count: int = None,
        last_message_id: int = None,
    ) -> None:
        """Update bulk import progress."""
        with self.get_session() as session:
            log = session.query(BulkImportLog).filter(
                BulkImportLog.id == log_id
            ).first()
            
            if log:
                if processed_messages is not None:
                    log.processed_messages = processed_messages
                if feedbacks_created is not None:
                    log.feedbacks_created = feedbacks_created
                if professors_created is not None:
                    log.professors_created = professors_created
                if errors_count is not None:
                    log.errors_count = errors_count
                if last_message_id is not None:
                    log.last_processed_message_id = last_message_id
    
    def complete_bulk_import(
        self,
        log_id: int,
        status: str = 'completed',
        total_messages: int = None,
        error_message: str = None,
    ) -> None:
        """Mark bulk import as completed or failed."""
        with self.get_session() as session:
            log = session.query(BulkImportLog).filter(
                BulkImportLog.id == log_id
            ).first()
            
            if log:
                log.status = status
                log.completed_at = datetime.utcnow()
                if total_messages is not None:
                    log.total_messages = total_messages
                if error_message:
                    log.error_message = error_message
                
                logger.info(f"Bulk import {log_id} {status}: "
                           f"{log.feedbacks_created} feedbacks created")
    
    def get_latest_bulk_import(self) -> Optional[BulkImportLog]:
        """Get the most recent bulk import log."""
        with self.get_session() as session:
            log = session.query(BulkImportLog).order_by(
                BulkImportLog.started_at.desc()
            ).first()
            if log:
                session.expunge(log)
            return log
    
    def is_bulk_import_completed(self) -> bool:
        """Check if any bulk import has been completed successfully."""
        with self.get_session() as session:
            exists = session.query(BulkImportLog).filter(
                BulkImportLog.status == 'completed'
            ).first() is not None
            return exists
    
    # ==================== User Query Logging ====================
    
    def log_user_query(
        self,
        query_text: str,
        query_type: str,
        response_text: str = None,
        telegram_user_id: int = None,
        professors_mentioned: List[str] = None,
        response_time_ms: int = None,
    ) -> UserQuery:
        """Log a user query for analytics."""
        with self.get_session() as session:
            query = UserQuery(
                telegram_user_id=telegram_user_id,
                query_text=query_text,
                query_type=query_type,
                response_text=response_text,
                professors_mentioned=professors_mentioned or [],
                response_time_ms=response_time_ms,
            )
            session.add(query)
            session.flush()
            session.expunge(query)
            return query
    
    # ==================== Statistics ====================
    
    def get_top_rated_professors(self, limit: int = 10) -> List[Professor]:
        """Get top rated professors with minimum feedback count."""
        with self.get_session() as session:
            professors = session.query(Professor).filter(
                Professor.total_feedbacks >= 3  # Minimum feedbacks
            ).order_by(Professor.overall_rating.desc()).limit(limit).all()
            
            for p in professors:
                session.expunge(p)
            return professors
    
    def get_professors_by_course(self, course_code: str) -> List[Professor]:
        """Get professors who teach a specific course."""
        with self.get_session() as session:
            professors = session.query(Professor).filter(
                Professor.courses.contains([course_code])
            ).all()
            
            for p in professors:
                session.expunge(p)
            return professors
    
    def get_overall_statistics(self) -> Dict[str, Any]:
        """Get overall system statistics."""
        with self.get_session() as session:
            return {
                'total_professors': session.query(Professor).count(),
                'total_feedbacks': session.query(Feedback).count(),
                'total_processed_messages': session.query(ProcessedMessage).count(),
                'total_queries': session.query(UserQuery).count(),
                'positive_feedbacks': session.query(Feedback).filter(
                    Feedback.sentiment == 'positive'
                ).count(),
                'negative_feedbacks': session.query(Feedback).filter(
                    Feedback.sentiment == 'negative'
                ).count(),
            }


# Singleton instance
_db_service: Optional[DatabaseService] = None


def get_database_service(database_url: str = None) -> DatabaseService:
    """Get or create database service singleton."""
    global _db_service
    if _db_service is None:
        _db_service = DatabaseService(database_url)
    return _db_service
