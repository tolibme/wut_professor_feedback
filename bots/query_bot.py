"""
Query Bot for WUT Feedback Bot.

Student-facing bot that provides:
- Professor search and information
- Professor comparison
- Course-based recommendations
- Natural language queries
- Statistics and rankings
"""

import time
from typing import Optional, List, Dict, Any

from telegram import Update
from telegram.error import BadRequest
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

from config import Config
from services.database_service import get_database_service, DatabaseService
from services.gemini_service import get_gemini_service, GeminiService
from services.embedding_service import get_embedding_service, EmbeddingService
from services.analytics_service import get_analytics_service, AnalyticsService
from rapidfuzz import fuzz

from utils.text_processing import normalize_professor_name
from utils.validators import validate_professor_name, validate_compare_args, sanitize_input
from utils.logger import get_logger

logger = get_logger(__name__)


class QueryBot:
    """
    Student query bot.
    
    Commands:
    - /start - Welcome message
    - /search <professor> - Search for professor info
    - /compare <prof1> vs <prof2> - Compare two professors
    - /course <code> - Find best professors for a course
    - /stats - Show overall statistics
    - /top - Show top rated professors
    - /help - Show help message
    
    Also handles natural language queries.
    """
    
    def __init__(self):
        """Initialize query bot."""
        self.token = Config.TELEGRAM_BOT_TOKEN_QUERY
        
        # Services
        self.db: Optional[DatabaseService] = None
        self.gemini: Optional[GeminiService] = None
        self.embedding: Optional[EmbeddingService] = None
        self.analytics: Optional[AnalyticsService] = None
        
        # Application
        self.app: Optional[Application] = None
        
        logger.info("Query bot initialized")
    
    async def initialize_services(self) -> None:
        """Initialize all required services."""
        logger.info("Initializing services...")
        
        self.db = get_database_service()
        self.gemini = get_gemini_service()
        self.embedding = get_embedding_service()
        self.analytics = get_analytics_service()
        
        logger.info("All services initialized")
    
    def setup_handlers(self, app: Application) -> None:
        """Setup command and message handlers."""
        # Command handlers
        app.add_handler(CommandHandler("start", self.cmd_start))
        app.add_handler(CommandHandler("help", self.cmd_help))
        app.add_handler(CommandHandler("search", self.cmd_search))
        app.add_handler(CommandHandler("compare", self.cmd_compare))
        app.add_handler(CommandHandler("course", self.cmd_course))
        app.add_handler(CommandHandler("stats", self.cmd_stats))
        app.add_handler(CommandHandler("top", self.cmd_top))
        
        # Natural language handler (must be last)
        app.add_handler(MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            self.handle_natural_query
        ))
    
    async def start(self) -> None:
        """
        Start the query bot.
        
        Initializes services and starts polling.
        """
        await self.initialize_services()
        
        # Build application
        self.app = ApplicationBuilder().token(self.token).build()
        self.setup_handlers(self.app)
        
        # Start polling
        logger.info("Starting query bot polling...")
        await self.app.initialize()
        await self.app.start()
        await self.app.updater.start_polling()
        
        # Keep running
        try:
            while True:
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            logger.info("Query bot shutting down...")
            await self.app.updater.stop()
            await self.app.stop()
            await self.app.shutdown()
    
    # ==================== Command Handlers ====================
    
    async def cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /start command - welcome message."""
        welcome_text = (
            "👋 **Welcome to WUT Professor Feedback Bot!**\n\n"
            "I can help you find information about professors at "
            "Webster University in Tashkent.\n\n"
            "**Commands:**\n"
            "🔍 /search `Professor Name` - Get professor info\n"
            "⚖️ /compare `Prof A vs Prof B` - Compare professors\n"
            "📚 /course `COSC 1570` - Best profs for a course\n"
            "📊 /stats - Overall statistics\n"
            "🏆 /top - Top rated professors\n"
            "❓ /help - Show this help\n\n"
            "You can also just type a question like:\n"
            "_\"Is Professor Johnson good at teaching?\"_"
        )
        
        await update.message.reply_text(welcome_text, parse_mode="Markdown")
    
    async def cmd_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /help command."""
        await self.cmd_start(update, context)
    
    async def cmd_search(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """
        Handle /search command - search for professor.
        
        Usage: /search Professor Name
        """
        start_time = time.time()
        
        if not context.args:
            await update.message.reply_text(
                "Please provide a professor name:\n"
                "/search Professor Name"
            )
            return
        
        professor_name = " ".join(context.args)
        
        # Validate input
        is_valid, error = validate_professor_name(professor_name)
        if not is_valid:
            await update.message.reply_text(f"❌ {error}")
            return
        
        # Search for professor
        await update.message.reply_text("🔍 Searching...")
        
        professor = self.db.search_professor_fuzzy(professor_name)
        
        if not professor:
            await update.message.reply_text(
                f"❌ Professor '{professor_name}' not found.\n\n"
                "Try different spelling or use /top to see available professors."
            )
            return
        
        # Get feedbacks
        feedbacks = self.db.get_professor_feedbacks(professor.id, limit=20)
        
        # Prepare professor data dict
        professor_data = {
            "name": professor.name,
            "department": professor.department,
            "courses": professor.courses,
            "overall_rating": professor.overall_rating,
            "total_feedbacks": professor.total_feedbacks,
            "positive_feedbacks": professor.positive_feedbacks,
            "negative_feedbacks": professor.negative_feedbacks,
            "neutral_feedbacks": professor.neutral_feedbacks,
            "avg_teaching_quality": professor.avg_teaching_quality,
            "avg_grading_fairness": professor.avg_grading_fairness,
            "avg_workload": professor.avg_workload,
            "avg_communication": professor.avg_communication,
            "avg_engagement": professor.avg_engagement,
        }
        
        # Prepare feedbacks for AI
        feedback_dicts = [
            {
                "original_message": f.original_message,
                "sentiment": f.sentiment,
                "final_rating": f.final_rating,
            }
            for f in feedbacks
        ]
        
        # Generate AI response
        try:
            response = await self.gemini.generate_query_response(
                user_query=f"Tell me about {professor.name}",
                professor_data=professor_data,
                feedbacks=feedback_dicts,
            )
        except Exception as e:
            logger.error(f"AI response generation failed: {e}")
            response = self._format_basic_professor_info(professor)
        
        # Add statistics
        stats_text = self._format_professor_stats(professor)
        
        # Calculate response time
        response_time = int((time.time() - start_time) * 1000)
        
        # Log query
        self.db.log_user_query(
            query_text=f"/search {professor_name}",
            query_type="search",
            response_text=response[:500],
            telegram_user_id=update.effective_user.id,
            professors_mentioned=[professor.name],
            response_time_ms=response_time,
        )
        
        await self._safe_reply_markdown(update, f"{response}\n\n{stats_text}")
    
    async def cmd_compare(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """
        Handle /compare command - compare two professors.
        
        Usage: /compare Professor A vs Professor B
        """
        if not context.args:
            await update.message.reply_text(
                "Please provide two professor names:\n"
                "/compare Professor A vs Professor B"
            )
            return
        
        # Validate and parse arguments
        is_valid, error, names = validate_compare_args(context.args)
        if not is_valid:
            await update.message.reply_text(f"❌ {error}")
            return
        
        prof1_name, prof2_name = names
        
        await update.message.reply_text("🔍 Comparing professors...")
        
        # Find both professors
        prof1 = self.db.search_professor_fuzzy(prof1_name)
        prof2 = self.db.search_professor_fuzzy(prof2_name)
        
        if not prof1:
            await update.message.reply_text(f"❌ Professor '{prof1_name}' not found.")
            return
        
        if not prof2:
            await update.message.reply_text(f"❌ Professor '{prof2_name}' not found.")
            return
        
        # Get detailed stats for both
        stats1 = self.analytics.get_professor_detailed_stats(prof1.id)
        stats2 = self.analytics.get_professor_detailed_stats(prof2.id)
        
        # Generate comparison
        try:
            response = await self.gemini.generate_comparison_response(
                user_query=f"Compare {prof1.name} and {prof2.name}",
                prof1_data=stats1 or {},
                prof2_data=stats2 or {},
            )
        except Exception as e:
            logger.error(f"Comparison generation failed: {e}")
            response = self._format_basic_comparison(prof1, prof2)
        
        # Log query
        self.db.log_user_query(
            query_text=f"/compare {prof1_name} vs {prof2_name}",
            query_type="compare",
            response_text=response[:500],
            telegram_user_id=update.effective_user.id,
            professors_mentioned=[prof1.name, prof2.name],
        )
        
        await self._safe_reply_markdown(update, response)
    
    async def cmd_course(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """
        Handle /course command - find professors for a course.
        
        Usage: /course COSC 1570
        """
        if not context.args:
            await update.message.reply_text(
                "Please provide a course code:\n"
                "/course COSC 1570"
            )
            return
        
        course_code = " ".join(context.args).upper()
        
        await update.message.reply_text("🔍 Finding professors...")
        
        # Get professors for this course
        professors = self.analytics.get_professors_for_course(course_code)
        
        if not professors:
            await update.message.reply_text(
                f"❌ No professors found for course '{course_code}'.\n\n"
                "This might be because:\n"
                "• The course code is wrong\n"
                "• No feedbacks mention this course yet"
            )
            return
        
        # Format response
        response = f"📚 **Professors for {course_code}:**\n\n"
        
        for i, prof in enumerate(professors[:5], 1):
            rating = prof.get('course_rating', 0)
            stars = "⭐" * int(rating)
            response += (
                f"{i}. **{prof['name']}**\n"
                f"   Rating: {rating:.1f}/5 {stars}\n"
                f"   Course Feedbacks: {prof['course_feedbacks']}\n\n"
            )
        
        if len(professors) > 5:
            response += f"_...and {len(professors) - 5} more_"
        
        # Log query
        self.db.log_user_query(
            query_text=f"/course {course_code}",
            query_type="course",
            telegram_user_id=update.effective_user.id,
            professors_mentioned=[p['name'] for p in professors[:5]],
        )
        
        await self._safe_reply_markdown(update, response)
    
    async def cmd_stats(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /stats command - show overall statistics."""
        stats = self.analytics.get_overall_statistics()
        
        total = stats.get('total_feedbacks', 0)
        pos = stats.get('sentiment_distribution', {}).get('positive', 0)
        neg = stats.get('sentiment_distribution', {}).get('negative', 0)
        
        response = (
            "📊 **WUT Professor Feedback Statistics**\n\n"
            f"👨‍🏫 Professors: {stats.get('total_professors', 0)}\n"
            f"📝 Total Feedbacks: {total}\n"
            f"⭐ Average Rating: {stats.get('average_rating', 0):.1f}/5\n\n"
            f"**Sentiment Distribution:**\n"
            f"✅ Positive: {pos} ({stats.get('positive_percent', 0):.1f}%)\n"
            f"❌ Negative: {neg} ({stats.get('negative_percent', 0):.1f}%)\n\n"
            "_Use /top to see top rated professors_"
        )
        
        await self._safe_reply_markdown(update, response)
    
    async def cmd_top(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /top command - show top rated professors."""
        # Parse optional limit
        limit = 5
        if context.args:
            try:
                limit = min(int(context.args[0]), 10)
            except ValueError:
                pass
        
        top_professors = self.analytics.get_top_professors(limit=limit)
        
        if not top_professors:
            await update.message.reply_text(
                "❌ No professors found with enough feedbacks yet."
            )
            return
        
        response = "🏆 **Top Rated Professors**\n\n"
        
        medals = ["🥇", "🥈", "🥉"]
        for i, prof in enumerate(top_professors):
            medal = medals[i] if i < 3 else f"{i+1}."
            response += (
                f"{medal} **{prof['name']}**\n"
                f"   ⭐ {prof['rating']:.1f}/5 "
                f"({prof['total_feedbacks']} feedbacks)\n"
                f"   👍 {prof['positive_percent']:.0f}% positive\n\n"
            )
        
        await update.message.reply_text(response, parse_mode="Markdown")
    
    # ==================== Natural Language Handler ====================
    
    async def handle_natural_query(
        self, 
        update: Update, 
        context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """
        Handle natural language queries.
        
        Uses Gemini to understand intent and generate appropriate response.
        """
        query = sanitize_input(update.message.text, max_length=500)
        
        if len(query) < 5:
            return
        
        start_time = time.time()
        
        await update.message.reply_text("🤔 Let me think...")
        
        # Analyze intent
        try:
            intent = await self.gemini.analyze_query_intent(query)
        except Exception as e:
            logger.warning(f"Intent analysis failed: {e}")
            intent = {"intent": "unknown", "professor_names": []}
        
        intent_type = intent.get("intent", "unknown")
        professor_names = intent.get("professor_names", [])
        
        # Handle based on intent
        if intent_type == "search_professor" and professor_names:
            # Search for the professor
            prof_name = professor_names[0]
            professor = self.db.search_professor_fuzzy(prof_name)
            if not professor:
                professor = self._find_professor_partial_match(prof_name)
            
            if professor:
                feedbacks = self.db.get_professor_feedbacks(professor.id, limit=15)
                
                professor_data = {
                    "name": professor.name,
                    "department": professor.department,
                    "courses": professor.courses,
                    "overall_rating": professor.overall_rating,
                    "total_feedbacks": professor.total_feedbacks,
                    "positive_feedbacks": professor.positive_feedbacks,
                    "negative_feedbacks": professor.negative_feedbacks,
                    "neutral_feedbacks": professor.neutral_feedbacks,
                    "avg_teaching_quality": professor.avg_teaching_quality,
                    "avg_grading_fairness": professor.avg_grading_fairness,
                    "avg_workload": professor.avg_workload,
                    "avg_communication": professor.avg_communication,
                    "avg_engagement": professor.avg_engagement,
                }
                
                feedback_dicts = [
                    {
                        "original_message": f.original_message,
                        "sentiment": f.sentiment,
                        "final_rating": f.final_rating,
                    }
                    for f in feedbacks
                ]
                
                response = await self.gemini.generate_query_response(
                    user_query=query,
                    professor_data=professor_data,
                    feedbacks=feedback_dicts,
                )
            else:
                response = (
                    f"I couldn't find a professor named '{prof_name}'.\n\n"
                    "Try using /search with the exact name, or /top to see available professors."
                )
        
        elif intent_type == "compare" and len(professor_names) >= 2:
            # Redirect to compare
            await update.message.reply_text(
                f"For comparing professors, please use:\n"
                f"/compare {professor_names[0]} vs {professor_names[1]}"
            )
            return
        
        elif intent_type == "course_recommendation":
            course_code = intent.get("course_code")
            if course_code:
                await update.message.reply_text(
                    f"For course-specific recommendations, use:\n"
                    f"/course {course_code}"
                )
                return
            response = "Please specify a course code, e.g., /course COSC 1570"
        
        elif intent_type == "general_stats":
            # Show stats
            await self.cmd_stats(update, context)
            return
        
        else:
            # Unknown intent - try semantic search
            similar = self.embedding.search_similar_feedbacks(query, n_results=5)
            
            if similar:
                response = (
                    "I found some related feedbacks:\n\n"
                )
                for i, item in enumerate(similar[:3], 1):
                    text = item.get('text', '')[:150]
                    prof_name = item.get('metadata', {}).get('professor_name', 'Unknown')
                    response += f"{i}. About **{prof_name}**: _{text}..._\n\n"
                
                response += "Use /search `Professor Name` for detailed info."
            else:
                response = (
                    "I'm not sure how to help with that.\n\n"
                    "Try:\n"
                    "• /search Professor Name\n"
                    "• /compare Prof A vs Prof B\n"
                    "• /course COSC 1570\n"
                    "• /stats or /top"
                )
        
        # Log query
        response_time = int((time.time() - start_time) * 1000)
        self.db.log_user_query(
            query_text=query,
            query_type="natural",
            response_text=response[:500] if response else None,
            telegram_user_id=update.effective_user.id,
            professors_mentioned=professor_names,
            response_time_ms=response_time,
        )
        
        await update.message.reply_text(response, parse_mode="Markdown")
    
    # ==================== Helper Methods ====================
    
    @staticmethod
    def _format_professor_stats(professor) -> str:
        """Format professor statistics for display."""
        rating = professor.overall_rating or 0
        stars = "⭐" * int(rating)
        
        return (
            f"📊 **Statistics:**\n"
            f"Rating: {rating:.1f}/5 {stars}\n"
            f"Feedbacks: {professor.total_feedbacks}\n"
            f"👍 Positive: {professor.positive_feedbacks} | "
            f"👎 Negative: {professor.negative_feedbacks}"
        )
    
    @staticmethod
    def _format_basic_professor_info(professor) -> str:
        """Format basic professor info without AI."""
        courses = ", ".join(professor.courses or []) or "Not specified"
        
        return (
            f"**{professor.name}**\n\n"
            f"Department: {professor.department or 'Unknown'}\n"
            f"Courses: {courses}\n"
            f"Rating: {professor.overall_rating:.1f}/5\n"
            f"Total Feedbacks: {professor.total_feedbacks}"
        )
    
    @staticmethod
    def _format_basic_comparison(prof1, prof2) -> str:
        """Format basic comparison without AI."""
        return (
            f"**{prof1.name}** vs **{prof2.name}**\n\n"
            f"**{prof1.name}:**\n"
            f"  Rating: {prof1.overall_rating:.1f}/5\n"
            f"  Feedbacks: {prof1.total_feedbacks}\n\n"
            f"**{prof2.name}:**\n"
            f"  Rating: {prof2.overall_rating:.1f}/5\n"
            f"  Feedbacks: {prof2.total_feedbacks}"
        )

    async def _safe_reply_markdown(self, update: Update, text: str) -> None:
        """Send a Markdown reply and fall back to plain text if formatting fails."""
        try:
            await update.message.reply_text(text, parse_mode="Markdown")
        except BadRequest:
            await update.message.reply_text(text)

    def _find_professor_partial_match(self, query: str):
        """Fallback matching for partial or misspelled professor names."""
        query_norm = normalize_professor_name(query)
        if not query_norm:
            return None

        professors = self.db.get_all_professors()
        if not professors:
            return None

        best_professor = None
        best_score = 0
        for prof in professors:
            name_norm = normalize_professor_name(prof.name)
            token_set = fuzz.token_set_ratio(query_norm, name_norm)
            partial = fuzz.partial_ratio(query_norm, name_norm)
            score = max(token_set, partial)

            if score > best_score:
                best_score = score
                best_professor = prof

        # Lower threshold for single-token queries like "javad"
        threshold = 75 if len(query_norm.split()) == 1 else 85
        return best_professor if best_score >= threshold else None


# Import asyncio for the start method
import asyncio
