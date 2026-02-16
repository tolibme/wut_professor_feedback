"""
Collector Bot for WUT Feedback Bot.

Handles two main modes:
1. Bulk Import Mode - Process historical messages from Telegram group
2. Monitoring Mode - Periodically check for new messages

Uses admin commands for control and status reporting.
"""

import asyncio
from datetime import datetime
from typing import Optional

from telegram import Update, Bot
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
)

from config import Config
from services.database_service import get_database_service, DatabaseService
from services.gemini_service import get_gemini_service, GeminiService
from services.embedding_service import get_embedding_service, EmbeddingService
from services.telegram_history_service import get_telegram_history_service, TelegramHistoryService
from utils.logger import get_logger
from utils.text_processing import clean_feedback_text

logger = get_logger(__name__)


class CollectorBot:
    """
    Feedback collection bot.
    
    Primary Functions:
    1. Bulk import historical messages on first run
    2. Monitor for new messages periodically
    
    Admin Commands:
    - /status - Show current status
    - /import - Trigger bulk import
    - /stats - Show collection statistics
    - /pause - Pause monitoring
    - /resume - Resume monitoring
    """
    
    def __init__(self):
        """Initialize collector bot."""
        self.token = Config.TELEGRAM_BOT_TOKEN_COLLECTOR
        self.group_id = Config.FEEDBACK_GROUP_ID
        self.check_interval = Config.CHECK_INTERVAL_MINUTES * 60  # Convert to seconds
        self.min_confidence = Config.MIN_EXTRACTION_CONFIDENCE
        
        # Services
        self.db: Optional[DatabaseService] = None
        self.gemini: Optional[GeminiService] = None
        self.embedding: Optional[EmbeddingService] = None
        self.telegram_history: Optional[TelegramHistoryService] = None
        
        # State
        self.is_monitoring = False
        self.is_importing = False
        self.monitoring_task: Optional[asyncio.Task] = None
        
        # Application
        self.app: Optional[Application] = None
        
        logger.info("Collector bot initialized")
    
    async def initialize_services(self) -> None:
        """Initialize all required services."""
        logger.info("Initializing services...")
        
        self.db = get_database_service()
        self.db.initialize_database()
        
        self.gemini = get_gemini_service()
        self.embedding = get_embedding_service()
        self.telegram_history = get_telegram_history_service()
        
        # Ensure directories exist
        Config.ensure_directories()
        
        logger.info("All services initialized")
    
    def setup_handlers(self, app: Application) -> None:
        """Setup command handlers."""
        app.add_handler(CommandHandler("start", self.cmd_start))
        app.add_handler(CommandHandler("status", self.cmd_status))
        app.add_handler(CommandHandler("import", self.cmd_import))
        app.add_handler(CommandHandler("stats", self.cmd_stats))
        app.add_handler(CommandHandler("pause", self.cmd_pause))
        app.add_handler(CommandHandler("resume", self.cmd_resume))
        app.add_handler(CommandHandler("help", self.cmd_help))
    
    async def start(self) -> None:
        """
        Main entry point - start the collector bot.
        
        Flow:
        1. Initialize services
        2. Check if bulk import needed
        3. Start monitoring mode
        4. Run bot polling
        """
        await self.initialize_services()
        
        # Build application
        self.app = ApplicationBuilder().token(self.token).build()
        self.setup_handlers(self.app)
        
        # Check if bulk import has been done
        if not self.db.is_bulk_import_completed():
            logger.info("No completed bulk import found. Starting bulk import...")
            await self.run_bulk_import()
        else:
            logger.info("Bulk import already completed. Starting monitoring mode...")
        
        # Start monitoring in background
        self.monitoring_task = asyncio.create_task(self.monitoring_loop())
        
        # Start polling
        logger.info("Starting bot polling...")
        await self.app.initialize()
        await self.app.start()
        await self.app.updater.start_polling()
        
        # Keep running
        try:
            while True:
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            logger.info("Bot shutting down...")
            if self.monitoring_task:
                self.monitoring_task.cancel()
            await self.app.updater.stop()
            await self.app.stop()
            await self.app.shutdown()
    
    # ==================== Bulk Import ====================
    
    async def run_bulk_import(self, notify_user_id: int = None) -> dict:
        """
        Run bulk import of historical messages.
        
        Args:
            notify_user_id: Optional user ID to notify on completion
        
        Returns:
            Import statistics
        """
        if self.is_importing:
            logger.warning("Bulk import already in progress")
            return {"error": "Import already in progress"}
        
        self.is_importing = True
        logger.info(f"Starting bulk import from group {self.group_id}")
        
        # Create import log
        import_log = self.db.create_bulk_import_log()
        
        # Statistics
        stats = {
            "total_messages": 0,
            "processed_messages": 0,
            "feedbacks_created": 0,
            "professors_created": 0,
            "errors": 0,
            "started_at": datetime.utcnow(),
        }
        
        try:
            # Connect to Telegram history service
            await self.telegram_history.connect()
            
            # Fetch messages
            async for message in self.telegram_history.fetch_messages(
                self.group_id,
                limit=Config.BULK_IMPORT_LIMIT,
            ):
                stats["total_messages"] += 1
                
                try:
                    result = await self.process_message(message)
                    stats["processed_messages"] += 1
                    
                    if result.get("feedback_created"):
                        stats["feedbacks_created"] += 1
                    if result.get("professor_created"):
                        stats["professors_created"] += 1
                    
                except Exception as e:
                    stats["errors"] += 1
                    logger.error(f"Error processing message {message['id']}: {e}")
                
                # Update progress every 100 messages
                if stats["total_messages"] % 100 == 0:
                    logger.info(
                        f"Progress: {stats['total_messages']} messages, "
                        f"{stats['feedbacks_created']} feedbacks"
                    )
                    self.db.update_bulk_import_progress(
                        import_log.id,
                        processed_messages=stats["processed_messages"],
                        feedbacks_created=stats["feedbacks_created"],
                        professors_created=stats["professors_created"],
                        errors_count=stats["errors"],
                        last_message_id=message["id"],
                    )
            
            # Complete import
            stats["completed_at"] = datetime.utcnow()
            stats["duration_minutes"] = (
                stats["completed_at"] - stats["started_at"]
            ).total_seconds() / 60
            
            self.db.complete_bulk_import(
                import_log.id,
                status="completed",
                total_messages=stats["total_messages"],
            )
            
            # Persist embeddings
            self.embedding.persist()
            
            logger.info(
                f"Bulk import complete: {stats['feedbacks_created']} feedbacks "
                f"from {stats['total_messages']} messages in "
                f"{stats['duration_minutes']:.1f} minutes"
            )
            
            # Notify admin
            if notify_user_id:
                await self._notify_admin(notify_user_id, self._format_import_summary(stats))
            
        except Exception as e:
            logger.error(f"Bulk import failed: {e}")
            self.db.complete_bulk_import(
                import_log.id,
                status="failed",
                error_message=str(e),
            )
            stats["error"] = str(e)
        
        finally:
            self.is_importing = False
            await self.telegram_history.disconnect()
        
        return stats
    
    # ==================== Monitoring Mode ====================
    
    async def monitoring_loop(self) -> None:
        """
        Periodic monitoring loop for new messages.
        
        Runs every CHECK_INTERVAL_MINUTES to fetch and process new messages.
        """
        logger.info(f"Starting monitoring loop (interval: {Config.CHECK_INTERVAL_MINUTES} min)")
        self.is_monitoring = True
        
        while self.is_monitoring:
            try:
                await self.check_new_messages()
            except Exception as e:
                logger.error(f"Error in monitoring loop: {e}")
            
            # Wait for next check
            await asyncio.sleep(self.check_interval)
    
    async def check_new_messages(self) -> dict:
        """
        Check for and process new messages.
        
        Returns:
            Statistics about processed messages
        """
        if self.is_importing:
            logger.debug("Skipping check - import in progress")
            return {}
        
        # Get last processed message ID
        last_id = self.db.get_last_processed_message_id() or 0
        
        try:
            await self.telegram_history.connect()
            
            # Fetch new messages
            new_messages = await self.telegram_history.fetch_new_messages_since(
                self.group_id,
                last_id,
                limit=500,
            )
            
            if not new_messages:
                logger.debug("No new messages found")
                return {"new_messages": 0}
            
            logger.info(f"Found {len(new_messages)} new messages")
            
            stats = {"new_messages": len(new_messages), "feedbacks": 0}
            
            for message in new_messages:
                try:
                    result = await self.process_message(message)
                    if result.get("feedback_created"):
                        stats["feedbacks"] += 1
                except Exception as e:
                    logger.error(f"Error processing message {message['id']}: {e}")
            
            # Persist embeddings
            if stats["feedbacks"] > 0:
                self.embedding.persist()
            
            logger.info(f"Processed {len(new_messages)} messages, {stats['feedbacks']} feedbacks")
            return stats
            
        finally:
            await self.telegram_history.disconnect()
    
    # ==================== Message Processing ====================
    
    async def process_message(self, message: dict) -> dict:
        """
        Process a single message.
        
        Steps:
        1. Check if already processed
        2. Extract feedback with Gemini
        3. Moderate content
        4. Store if valid feedback
        5. Generate embedding
        6. Mark as processed
        
        Args:
            message: Message dict with id, text, date, user_id
        
        Returns:
            Processing result dict
        """
        result = {
            "message_id": message["id"],
            "is_feedback": False,
            "feedback_created": False,
            "professor_created": False,
        }
        
        # Check if already processed
        if self.db.is_message_processed(message["id"]):
            logger.debug(f"Message {message['id']} already processed")
            return result
        
        # Clean text
        text = clean_feedback_text(message.get("text", ""))
        if not text or len(text) < 20:
            self.db.mark_message_processed(message["id"], is_feedback=False)
            return result
        
        # Extract feedback with Gemini
        try:
            extraction = await self.gemini.extract_feedback(text)
        except Exception as e:
            logger.warning(f"Extraction failed for message {message['id']}: {e}")
            self.db.mark_message_processed(
                message["id"],
                is_feedback=False,
                error=str(e)
            )
            return result
        
        # Check if it's feedback with sufficient confidence
        if not extraction.get("is_feedback") or extraction.get("confidence", 0) < self.min_confidence:
            self.db.mark_message_processed(message["id"], is_feedback=False)
            return result
        
        result["is_feedback"] = True
        
        # Check content appropriateness
        if not extraction.get("is_appropriate", True):
            logger.warning(f"Inappropriate content in message {message['id']}")
            self.db.mark_message_processed(message["id"], is_feedback=False)
            return result
        
        # Get or create professor
        professor_name = extraction.get("professor_name")
        professor_name_normalized = extraction.get("professor_name_normalized")
        name_for_matching = professor_name_normalized or professor_name
        if not name_for_matching:
            self.db.mark_message_processed(message["id"], is_feedback=False)
            return result
        
        professor, was_created = self.db.find_or_create_professor(name_for_matching)
        result["professor_created"] = was_created
        
        # Add course to professor if mentioned
        course_code = extraction.get("course_code")
        if course_code:
            self.db.add_course_to_professor(professor.id, course_code)
        
        # Create feedback
        feedback = self.db.create_feedback(
            professor_id=professor.id,
            original_message=text,
            telegram_message_id=message["id"],
            extracted_data=extraction,
            telegram_user_id=message.get("user_id"),
            message_date=message.get("date"),
        )
        result["feedback_created"] = True
        result["feedback_id"] = feedback.id
        
        # Generate and store embedding
        try:
            self.embedding.store_feedback_embedding(
                feedback_id=feedback.id,
                text=text,
                professor_id=professor.id,
                professor_name=professor.name,
                metadata={
                    "sentiment": extraction.get("sentiment"),
                    "rating": extraction.get("inferred_rating"),
                }
            )
        except Exception as e:
            logger.warning(f"Embedding storage failed: {e}")
        
        # Update professor statistics
        self.db.update_professor_statistics(professor.id)
        
        # Mark message as processed
        self.db.mark_message_processed(
            message["id"],
            is_feedback=True,
            feedback_id=feedback.id
        )
        
        logger.info(f"Created feedback {feedback.id} for professor {professor.name}")
        
        return result
    
    # ==================== Command Handlers ====================
    
    async def cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /start command."""
        if not self._is_admin(update.effective_user.id):
            await update.message.reply_text("This bot is for admin use only.")
            return
        
        await update.message.reply_text(
            "🤖 **WUT Feedback Collector Bot**\n\n"
            "Commands:\n"
            "/status - Show current status\n"
            "/import - Start bulk import\n"
            "/stats - Show statistics\n"
            "/pause - Pause monitoring\n"
            "/resume - Resume monitoring\n"
            "/help - Show this help",
            parse_mode="Markdown"
        )
    
    async def cmd_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /status command."""
        if not self._is_admin(update.effective_user.id):
            return
        
        status = "🔄 Importing..." if self.is_importing else (
            "✅ Monitoring" if self.is_monitoring else "⏸️ Paused"
        )
        
        last_import = self.db.get_latest_bulk_import()
        import_info = ""
        if last_import:
            import_info = (
                f"\nLast Import: {last_import.status}\n"
                f"Feedbacks: {last_import.feedbacks_created}\n"
                f"Completed: {last_import.completed_at or 'N/A'}"
            )
        
        await update.message.reply_text(
            f"**Status:** {status}\n"
            f"**Check Interval:** {Config.CHECK_INTERVAL_MINUTES} min"
            f"{import_info}",
            parse_mode="Markdown"
        )
    
    async def cmd_import(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /import command - trigger bulk import."""
        if not self._is_admin(update.effective_user.id):
            return
        
        if self.is_importing:
            await update.message.reply_text("⚠️ Import already in progress!")
            return
        
        await update.message.reply_text(
            "🚀 Starting bulk import...\n"
            "This may take a while. I'll notify you when complete."
        )
        
        # Run import in background
        asyncio.create_task(
            self.run_bulk_import(notify_user_id=update.effective_user.id)
        )
    
    async def cmd_stats(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /stats command - show statistics."""
        if not self._is_admin(update.effective_user.id):
            return
        
        stats = self.db.get_overall_statistics()
        
        await update.message.reply_text(
            f"📊 **Collection Statistics**\n\n"
            f"Professors: {stats['total_professors']}\n"
            f"Feedbacks: {stats['total_feedbacks']}\n"
            f"Processed Messages: {stats['total_processed_messages']}\n"
            f"User Queries: {stats['total_queries']}\n\n"
            f"Sentiment Distribution:\n"
            f"  ✅ Positive: {stats['positive_feedbacks']}\n"
            f"  ❌ Negative: {stats['negative_feedbacks']}",
            parse_mode="Markdown"
        )
    
    async def cmd_pause(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /pause command - pause monitoring."""
        if not self._is_admin(update.effective_user.id):
            return
        
        if not self.is_monitoring:
            await update.message.reply_text("⏸️ Already paused")
            return
        
        self.is_monitoring = False
        await update.message.reply_text("⏸️ Monitoring paused")
    
    async def cmd_resume(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /resume command - resume monitoring."""
        if not self._is_admin(update.effective_user.id):
            return
        
        if self.is_monitoring:
            await update.message.reply_text("✅ Already monitoring")
            return
        
        self.is_monitoring = True
        self.monitoring_task = asyncio.create_task(self.monitoring_loop())
        await update.message.reply_text("✅ Monitoring resumed")
    
    async def cmd_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /help command."""
        await self.cmd_start(update, context)
    
    # ==================== Helper Methods ====================
    
    def _is_admin(self, user_id: int) -> bool:
        """Check if user is admin."""
        return Config.is_admin(user_id)
    
    async def _notify_admin(self, user_id: int, message: str) -> None:
        """Send notification to admin user."""
        try:
            bot = Bot(token=self.token)
            await bot.send_message(chat_id=user_id, text=message, parse_mode="Markdown")
        except Exception as e:
            logger.error(f"Failed to notify admin: {e}")
    
    @staticmethod
    def _format_import_summary(stats: dict) -> str:
        """Format import statistics for message."""
        duration = stats.get("duration_minutes", 0)
        return (
            "✅ **Bulk Import Complete!**\n\n"
            f"Total Messages: {stats.get('total_messages', 0)}\n"
            f"Feedbacks Created: {stats.get('feedbacks_created', 0)}\n"
            f"Professors Found: {stats.get('professors_created', 0)}\n"
            f"Errors: {stats.get('errors', 0)}\n"
            f"Duration: {duration:.1f} minutes"
        )
