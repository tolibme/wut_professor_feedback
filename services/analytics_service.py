"""
Analytics service for WUT Feedback Bot.

Provides statistics, rankings, and analytical insights
from collected professor feedback data.
"""

from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Tuple

from sqlalchemy import func, desc, and_

from models.database_models import (
    Professor,
    Feedback,
    ProcessedMessage,
    UserQuery,
    get_session_factory,
)
from utils.logger import get_logger

logger = get_logger(__name__)


class AnalyticsService:
    """
    Service for generating analytics and statistics.
    
    Provides:
    - Professor rankings
    - Sentiment analysis
    - Trend detection
    - Usage statistics
    """
    
    def __init__(self, database_url: str = None):
        """Initialize analytics service."""
        self._session_factory = get_session_factory(database_url)
    
    def get_session(self):
        """Get database session."""
        return self._session_factory()
    
    # ==================== Professor Analytics ====================
    
    def get_top_professors(
        self,
        limit: int = 10,
        min_feedbacks: int = 3,
        department: str = None,
    ) -> List[Dict[str, Any]]:
        """
        Get top rated professors.
        
        Args:
            limit: Number of professors to return
            min_feedbacks: Minimum feedback count required
            department: Optional department filter
        
        Returns:
            List of professor data with rankings
        """
        session = self.get_session()
        try:
            query = session.query(Professor).filter(
                Professor.total_feedbacks >= min_feedbacks
            )
            
            if department:
                query = query.filter(Professor.department == department)
            
            professors = query.order_by(
                Professor.overall_rating.desc()
            ).limit(limit).all()
            
            return [
                {
                    "rank": i + 1,
                    "name": p.name,
                    "department": p.department,
                    "rating": round(p.overall_rating, 2),
                    "total_feedbacks": p.total_feedbacks,
                    "positive_percent": self._calc_percent(
                        p.positive_feedbacks, p.total_feedbacks
                    ),
                }
                for i, p in enumerate(professors)
            ]
        finally:
            session.close()
    
    def get_bottom_professors(
        self,
        limit: int = 10,
        min_feedbacks: int = 3,
    ) -> List[Dict[str, Any]]:
        """Get lowest rated professors."""
        session = self.get_session()
        try:
            professors = session.query(Professor).filter(
                Professor.total_feedbacks >= min_feedbacks
            ).order_by(
                Professor.overall_rating.asc()
            ).limit(limit).all()
            
            return [
                {
                    "rank": i + 1,
                    "name": p.name,
                    "department": p.department,
                    "rating": round(p.overall_rating, 2),
                    "total_feedbacks": p.total_feedbacks,
                    "negative_percent": self._calc_percent(
                        p.negative_feedbacks, p.total_feedbacks
                    ),
                }
                for i, p in enumerate(professors)
            ]
        finally:
            session.close()
    
    def get_professor_detailed_stats(
        self,
        professor_id: int,
    ) -> Optional[Dict[str, Any]]:
        """
        Get detailed statistics for a professor.
        
        Args:
            professor_id: Professor ID
        
        Returns:
            Detailed statistics dictionary
        """
        session = self.get_session()
        try:
            professor = session.query(Professor).filter(
                Professor.id == professor_id
            ).first()
            
            if not professor:
                return None
            
            # Get recent feedbacks for trend analysis
            recent_feedbacks = session.query(Feedback).filter(
                Feedback.professor_id == professor_id
            ).order_by(Feedback.created_at.desc()).limit(50).all()
            
            # Calculate sentiment distribution
            sentiment_dist = {
                "positive": professor.positive_feedbacks,
                "negative": professor.negative_feedbacks,
                "neutral": professor.neutral_feedbacks,
            }
            
            # Get common strengths and weaknesses
            all_strengths = []
            all_weaknesses = []
            for fb in recent_feedbacks:
                if fb.strengths:
                    all_strengths.extend(fb.strengths)
                if fb.weaknesses:
                    all_weaknesses.extend(fb.weaknesses)
            
            top_strengths = self._get_top_items(all_strengths, 5)
            top_weaknesses = self._get_top_items(all_weaknesses, 5)
            
            return {
                "professor_id": professor.id,
                "name": professor.name,
                "department": professor.department,
                "courses": professor.courses or [],
                "overall_rating": round(professor.overall_rating, 2),
                "total_feedbacks": professor.total_feedbacks,
                "sentiment_distribution": sentiment_dist,
                "aspects": {
                    "teaching_quality": professor.avg_teaching_quality,
                    "grading_fairness": professor.avg_grading_fairness,
                    "workload": professor.avg_workload,
                    "communication": professor.avg_communication,
                    "engagement": professor.avg_engagement,
                    "exams_difficulty": professor.avg_exams_difficulty,
                },
                "top_strengths": top_strengths,
                "top_weaknesses": top_weaknesses,
            }
        finally:
            session.close()
    
    # ==================== Course Analytics ====================
    
    def get_professors_for_course(
        self,
        course_code: str,
    ) -> List[Dict[str, Any]]:
        """
        Get professors who teach a specific course with ratings.
        
        Args:
            course_code: Course code to search
        
        Returns:
            List of professors with course-specific stats
        """
        session = self.get_session()
        try:
            # Find professors with this course
            professors = session.query(Professor).filter(
                Professor.courses.contains([course_code.upper()])
            ).all()
            
            results = []
            for prof in professors:
                # Get course-specific feedbacks
                course_feedbacks = session.query(Feedback).filter(
                    and_(
                        Feedback.professor_id == prof.id,
                        Feedback.course_code.ilike(f"%{course_code}%")
                    )
                ).all()
                
                if course_feedbacks:
                    ratings = [f.final_rating for f in course_feedbacks if f.final_rating]
                    avg_rating = sum(ratings) / len(ratings) if ratings else 0
                else:
                    avg_rating = prof.overall_rating
                
                results.append({
                    "professor_id": prof.id,
                    "name": prof.name,
                    "department": prof.department,
                    "course_rating": round(avg_rating, 2),
                    "course_feedbacks": len(course_feedbacks),
                    "overall_rating": round(prof.overall_rating, 2),
                    "total_feedbacks": prof.total_feedbacks,
                })
            
            # Sort by course rating
            results.sort(key=lambda x: x['course_rating'], reverse=True)
            
            return results
        finally:
            session.close()
    
    # ==================== Overall Statistics ====================
    
    def get_overall_statistics(self) -> Dict[str, Any]:
        """
        Get overall system statistics.
        
        Returns:
            Dictionary with system-wide stats
        """
        session = self.get_session()
        try:
            total_professors = session.query(Professor).count()
            total_feedbacks = session.query(Feedback).count()
            total_processed = session.query(ProcessedMessage).count()
            total_queries = session.query(UserQuery).count()
            
            # Sentiment counts
            positive = session.query(Feedback).filter(
                Feedback.sentiment == 'positive'
            ).count()
            negative = session.query(Feedback).filter(
                Feedback.sentiment == 'negative'
            ).count()
            neutral = session.query(Feedback).filter(
                Feedback.sentiment.in_(['neutral', 'mixed'])
            ).count()
            
            # Average rating
            avg_rating = session.query(
                func.avg(Professor.overall_rating)
            ).filter(
                Professor.total_feedbacks > 0
            ).scalar() or 0
            
            # Department distribution
            dept_counts = session.query(
                Professor.department,
                func.count(Professor.id)
            ).group_by(Professor.department).all()
            
            return {
                "total_professors": total_professors,
                "total_feedbacks": total_feedbacks,
                "total_processed_messages": total_processed,
                "total_queries": total_queries,
                "average_rating": round(avg_rating, 2),
                "sentiment_distribution": {
                    "positive": positive,
                    "negative": negative,
                    "neutral": neutral,
                },
                "positive_percent": self._calc_percent(positive, total_feedbacks),
                "negative_percent": self._calc_percent(negative, total_feedbacks),
                "departments": {
                    dept: count for dept, count in dept_counts if dept
                },
            }
        finally:
            session.close()
    
    def get_recent_activity(
        self,
        days: int = 7,
    ) -> Dict[str, Any]:
        """
        Get recent activity statistics.
        
        Args:
            days: Number of days to look back
        
        Returns:
            Activity statistics
        """
        session = self.get_session()
        try:
            since = datetime.utcnow() - timedelta(days=days)
            
            new_feedbacks = session.query(Feedback).filter(
                Feedback.created_at >= since
            ).count()
            
            new_queries = session.query(UserQuery).filter(
                UserQuery.created_at >= since
            ).count()
            
            # Daily breakdown
            daily_feedbacks = session.query(
                func.date(Feedback.created_at),
                func.count(Feedback.id)
            ).filter(
                Feedback.created_at >= since
            ).group_by(
                func.date(Feedback.created_at)
            ).all()
            
            return {
                "period_days": days,
                "new_feedbacks": new_feedbacks,
                "new_queries": new_queries,
                "daily_feedbacks": {
                    str(date): count for date, count in daily_feedbacks
                },
            }
        finally:
            session.close()
    
    # ==================== Query Analytics ====================
    
    def get_popular_queries(
        self,
        limit: int = 10,
        days: int = 30,
    ) -> List[Dict[str, Any]]:
        """
        Get most popular query patterns.
        
        Args:
            limit: Number of results
            days: Days to look back
        
        Returns:
            List of popular query patterns
        """
        session = self.get_session()
        try:
            since = datetime.utcnow() - timedelta(days=days)
            
            # Group by query type
            type_counts = session.query(
                UserQuery.query_type,
                func.count(UserQuery.id)
            ).filter(
                UserQuery.created_at >= since
            ).group_by(
                UserQuery.query_type
            ).order_by(
                func.count(UserQuery.id).desc()
            ).limit(limit).all()
            
            return [
                {"query_type": qtype, "count": count}
                for qtype, count in type_counts
            ]
        finally:
            session.close()
    
    def get_most_searched_professors(
        self,
        limit: int = 10,
        days: int = 30,
    ) -> List[Dict[str, Any]]:
        """
        Get most frequently searched professors.
        
        Args:
            limit: Number of results
            days: Days to look back
        
        Returns:
            List of popular professors by search count
        """
        session = self.get_session()
        try:
            # This requires parsing professors_mentioned from queries
            # For simplicity, we'll count based on feedbacks accessed
            
            recent_queries = session.query(UserQuery).filter(
                UserQuery.created_at >= datetime.utcnow() - timedelta(days=days)
            ).all()
            
            professor_counts = {}
            for query in recent_queries:
                if query.professors_mentioned:
                    for prof in query.professors_mentioned:
                        professor_counts[prof] = professor_counts.get(prof, 0) + 1
            
            # Sort by count
            sorted_profs = sorted(
                professor_counts.items(),
                key=lambda x: x[1],
                reverse=True
            )[:limit]
            
            return [
                {"professor_name": name, "search_count": count}
                for name, count in sorted_profs
            ]
        finally:
            session.close()
    
    # ==================== Helper Methods ====================
    
    @staticmethod
    def _calc_percent(part: int, total: int) -> float:
        """Calculate percentage."""
        if not total:
            return 0.0
        return round((part / total) * 100, 1)
    
    @staticmethod
    def _get_top_items(items: List[str], limit: int = 5) -> List[str]:
        """Get most common items from a list."""
        if not items:
            return []
        
        counts = {}
        for item in items:
            item_lower = item.lower().strip()
            counts[item_lower] = counts.get(item_lower, 0) + 1
        
        sorted_items = sorted(counts.items(), key=lambda x: x[1], reverse=True)
        return [item for item, _ in sorted_items[:limit]]


# Singleton instance
_analytics_service: Optional[AnalyticsService] = None


def get_analytics_service(database_url: str = None) -> AnalyticsService:
    """Get or create analytics service singleton."""
    global _analytics_service
    if _analytics_service is None:
        _analytics_service = AnalyticsService(database_url)
    return _analytics_service
