"""
Userbot Collector for WUT Feedback Bot.

Uses Telegram user account (via Telethon) to:
1. Monitor group messages in real-time
2. Process feedback automatically
3. Support bulk import of historical messages

No bot token needed - runs as your personal Telegram account.
"""

import asyncio
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List

from telethon import TelegramClient, events
from telethon.tl.types import Message

from config import Config
from services.database_service import get_database_service, DatabaseService
from services.gemini_service import get_gemini_service, GeminiService
from services.embedding_service import get_embedding_service, EmbeddingService
from utils.logger import get_logger
from utils.text_processing import clean_feedback_text

logger = get_logger(__name__)


class UserbotCollector:
    """
    Userbot-based feedback collector.
    
    Runs as your Telegram user account to:
    - Monitor groups for new messages in real-time
    - Process historical messages (bulk import)
    - Auto-extract and store feedback
    
    Modes:
    - monitor: Real-time message monitoring
    - bulk: One-time historical import
    - hybrid: Bulk import then monitor
    """
    
    def __init__(self):
        """Initialize userbot collector."""
        self.api_id = Config.TELEGRAM_API_ID
        self.api_hash = Config.TELEGRAM_API_HASH
        self.group_id = Config.FEEDBACK_GROUP_ID
        self.min_confidence = Config.MIN_EXTRACTION_CONFIDENCE
        
        # Services
        self.db: Optional[DatabaseService] = None
        self.gemini: Optional[GeminiService] = None
        self.embedding: Optional[EmbeddingService] = None
        
        # Telethon client
        self.client: Optional[TelegramClient] = None
        
        # State
        self.is_monitoring = False
        self.stats = {
            "messages_processed": 0,
            "feedbacks_created": 0,
            "professors_created": 0,
            "session_start": None,
        }
        
        logger.info("Userbot collector initialized")
    
    async def initialize_services(self) -> None:
        """Initialize all required services."""
        logger.info("Initializing services...")
        
        self.db = get_database_service()
        self.db.initialize_database()
        
        self.gemini = get_gemini_service()
        self.embedding = get_embedding_service()
        
        # Ensure directories exist
        Config.ensure_directories()
        
        logger.info("All services initialized")
    
    async def connect(self) -> None:
        """Connect to Telegram as user account."""
        if self.client:
            return
        
        logger.info("Connecting to Telegram...")
        
        self.client = TelegramClient(
            str(Config.get_session_path()),
            self.api_id,
            self.api_hash,
        )
        
        await self.client.start()
        
        # Get user info
        me = await self.client.get_me()
        logger.info(f"✓ Connected as {me.first_name} {me.last_name or ''} (@{me.username or me.id})")
        
        # Verify group access
        try:
            group = await self.client.get_entity(self.group_id)
            group_title = getattr(group, 'title', 'Unknown')
            logger.info(f"✓ Monitoring group: {group_title}")
        except Exception as e:
            logger.error(f"❌ Cannot access group {self.group_id}: {e}")
            raise
    
    async def disconnect(self) -> None:
        """Disconnect from Telegram."""
        if self.client:
            await self.client.disconnect()
            logger.info("Disconnected from Telegram")
    
    # ==================== Message Processing ====================
    
    async def process_message(self, message: Message) -> Dict[str, Any]:
        """
        Process a single message for feedback extraction.
        
        Args:
            message: Telethon Message object
        
        Returns:
            Processing results
        """
        result = {
            "message_id": message.id,
            "processed": False,
            "is_feedback": False,
            "feedback_created": False,
            "professor_created": False,
            "error": None,
        }
        
        # Skip if no text
        if not message.text or len(message.text.strip()) < 10:
            return result
        
        # Check if already processed
        if self.db.is_message_processed(message.id):
            logger.debug(f"Message {message.id} already processed, skipping")
            return result
        
        try:
            # Clean text
            text = clean_feedback_text(message.text)

            # Capture user info if available
            await self._capture_user(message)
            
            # Extract feedback using Gemini
            extraction = await self.gemini.extract_feedback(text)
            result = await self._process_extraction_result(message, extraction)
        
        except Exception as e:
            logger.error(f"Error processing message {message.id}: {e}")
            result["error"] = str(e)
        
        return result

    async def _capture_user(self, message: Message) -> None:
        """Capture Telegram user data from a message."""
        try:
            sender = await message.get_sender()
            if not sender:
                return

            telegram_user_id = getattr(sender, "id", None)
            if not telegram_user_id:
                return

            first_name = getattr(sender, "first_name", None)
            last_name = getattr(sender, "last_name", None)
            username = getattr(sender, "username", None)
            display_name = " ".join([part for part in [first_name, last_name] if part]) or None

            self.db.upsert_telegram_user(
                telegram_user_id=telegram_user_id,
                username=username,
                display_name=display_name,
                first_name=first_name,
                last_name=last_name,
            )
        except Exception as e:
            logger.debug(f"Failed to capture user info for message {message.id}: {e}")
    
    # ==================== Bulk Import ====================
    
    async def run_bulk_import(self, limit: int = None) -> Dict[str, Any]:
        """
        Import historical messages from the group.
        
        Args:
            limit: Maximum messages to process (None = use config)
        
        Returns:
            Import statistics
        """
        limit = limit or Config.BULK_IMPORT_LIMIT
        
        logger.info(f"Starting bulk import (limit: {limit})")
        
        stats = {
            "total_messages": 0,
            "processed": 0,
            "feedbacks_created": 0,
            "professors_created": 0,
            "errors": 0,
            "started_at": datetime.utcnow(),
        }
        
        # Create import log
        import_log = self.db.create_bulk_import_log()
        
        try:
            batch_size = max(1, Config.BULK_IMPORT_BATCH_SIZE)
            batch_messages = []

            # Fetch messages from newest to oldest
            async for message in self.client.iter_messages(
                self.group_id,
                limit=limit,
            ):
                stats["total_messages"] += 1
                batch_messages.append(message)

                if len(batch_messages) >= batch_size:
                    await self._process_message_batch(batch_messages, stats, import_log)
                    batch_messages = []

            # Process any remainder
            if batch_messages:
                await self._process_message_batch(batch_messages, stats, import_log)
            
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
                f"✅ Bulk import complete: {stats['feedbacks_created']} feedbacks "
                f"from {stats['total_messages']} messages in "
                f"{stats['duration_minutes']:.1f} minutes"
            )
        
        except Exception as e:
            logger.error(f"Bulk import failed: {e}")
            self.db.complete_bulk_import(
                import_log.id,
                status="failed",
                error_message=str(e),
            )
            stats["error"] = str(e)
        
        return stats

    async def _process_message_batch(
        self,
        messages: List[Message],
        stats: Dict[str, Any],
        import_log,
    ) -> None:
        """Process a batch of messages with a single Gemini call."""
        payload = []
        message_map = {}

        for message in messages:
            if not message.text or len(message.text.strip()) < 10:
                continue
            if self.db.is_message_processed(message.id):
                continue
            payload.append({"id": message.id, "text": clean_feedback_text(message.text)})
            message_map[message.id] = message

        if not payload:
            return

        # Quick-check batch to reduce JSON size
        quick_results = await self.gemini.quick_check_feedback_batch(payload)
        if not quick_results:
            # Fallback: split batch or process individually
            if len(messages) == 1:
                result = await self.process_message(messages[0])
                if result.get("processed"):
                    stats["processed"] += 1
                if result.get("feedback_created"):
                    stats["feedbacks_created"] += 1
                if result.get("professor_created"):
                    stats["professors_created"] += 1
                if result.get("error"):
                    stats["errors"] += 1
                return

            mid = len(messages) // 2
            await self._process_message_batch(messages[:mid], stats, import_log)
            await self._process_message_batch(messages[mid:], stats, import_log)
            return

        quick_map = {item.get("id"): item for item in quick_results if item.get("id") is not None}

        for message_id, message in message_map.items():
            quick = quick_map.get(message_id)
            if not quick:
                # Fallback to per-message extraction for missing results
                result = await self.process_message(message)
                if result.get("processed"):
                    stats["processed"] += 1
                if result.get("feedback_created"):
                    stats["feedbacks_created"] += 1
                if result.get("professor_created"):
                    stats["professors_created"] += 1
                if result.get("error"):
                    stats["errors"] += 1
                continue

            if not quick.get("is_feedback"):
                await self._capture_user(message)
                self.db.mark_message_processed(message_id, is_feedback=False)
                stats["processed"] += 1
                continue

            try:
                # Full extraction only for likely feedback
                extraction = await self.gemini.extract_feedback(clean_feedback_text(message.text))
                result = await self._process_extraction_result(message, extraction)
                if result.get("processed"):
                    stats["processed"] += 1
                if result.get("feedback_created"):
                    stats["feedbacks_created"] += 1
                if result.get("professor_created"):
                    stats["professors_created"] += 1
                if result.get("error"):
                    stats["errors"] += 1
            except Exception as e:
                stats["errors"] += 1
                logger.error(f"Error processing message {message_id}: {e}")

            # Progress update every 100 messages
            if stats.get("total_messages") and stats["total_messages"] % 100 == 0:
                logger.info(
                    f"Progress: {stats['total_messages']} messages, "
                    f"{stats['feedbacks_created']} feedbacks created"
                )
                if import_log:
                    self.db.update_bulk_import_progress(
                        import_log.id,
                        processed_messages=stats["processed"],
                        feedbacks_created=stats["feedbacks_created"],
                        professors_created=stats["professors_created"],
                        errors_count=stats["errors"],
                        last_message_id=message_id,
                    )

    async def _process_extraction_result(
        self,
        message: Message,
        extraction: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Process a single extraction result for a message."""
        result = {
            "message_id": message.id,
            "processed": False,
            "is_feedback": False,
            "feedback_created": False,
            "professor_created": False,
            "error": None,
        }

        # Mark as processed
        self.db.mark_message_processed(
            message.id,
            is_feedback=extraction.get("is_feedback", False),
        )
        result["processed"] = True
        result["is_feedback"] = extraction.get("is_feedback", False)

        if not extraction.get("is_feedback"):
            return result
        if not extraction.get("is_appropriate", True):
            return result

        confidence = extraction.get("confidence", 0.0)
        if confidence < self.min_confidence:
            return result

        professor_name = extraction.get("professor_name")
        professor_name_normalized = extraction.get("professor_name_normalized")
        name_for_matching = professor_name_normalized or professor_name
        if not name_for_matching:
            return result

        professor, prof_created = self.db.find_or_create_professor(
            name=name_for_matching,
            department=extraction.get("department"),
        )
        result["professor_created"] = prof_created

        feedback = self.db.create_feedback(
            professor_id=professor.id,
            telegram_message_id=message.id,
            telegram_user_id=message.from_id.user_id if message.from_id else None,
            message_date=message.date,
            original_message=clean_feedback_text(message.text),
            extracted_data=extraction,
        )

        result["feedback_created"] = True
        result["feedback_id"] = feedback.id

        self.db.update_professor_statistics(professor.id)

        embedding_text = f"{professor.name} - {clean_feedback_text(message.text)}"
        metadata = {
            "course_code": extraction.get("course_code"),
            "sentiment": extraction.get("sentiment"),
            "rating": extraction.get("final_rating"),
        }
        metadata = {key: value for key, value in metadata.items() if value is not None}
        self.embedding.store_feedback_embedding(
            feedback_id=feedback.id,
            text=embedding_text,
            professor_id=professor.id,
            professor_name=professor.name,
            metadata=metadata,
        )

        return result
    
    # ==================== Real-time Monitoring ====================
    
    async def start_monitoring(self) -> None:
        """
        Start real-time message monitoring.
        
        Listens to new messages in the group and processes them automatically.
        """
        logger.info("Starting real-time monitoring...")
        
        self.is_monitoring = True
        self.stats["session_start"] = datetime.utcnow()

        batch_size = max(1, Config.MONITOR_BATCH_SIZE)
        batch_interval = max(5, Config.MONITOR_BATCH_INTERVAL_SECONDS)
        buffer = []
        buffer_lock = asyncio.Lock()

        async def flush_buffer() -> None:
            async with buffer_lock:
                if not buffer:
                    return
                batch = list(buffer)
                buffer.clear()

            try:
                await self._process_message_batch(batch, {
                    "total_messages": 0,
                    "processed": 0,
                    "feedbacks_created": 0,
                    "professors_created": 0,
                    "errors": 0,
                }, None)
            except Exception as e:
                logger.error(f"Error processing monitor batch: {e}")

        async def flush_loop() -> None:
            while self.is_monitoring:
                await asyncio.sleep(batch_interval)
                await flush_buffer()

        flush_task = asyncio.create_task(flush_loop())
        
        # Register event handler for new messages
        @self.client.on(events.NewMessage(chats=[self.group_id]))
        async def handler(event):
            if not self.is_monitoring:
                return
            
            logger.info(f"New message detected: {event.message.id}")
            
            try:
                async with buffer_lock:
                    buffer.append(event.message)
                    if len(buffer) >= batch_size:
                        asyncio.create_task(flush_buffer())
            
            except Exception as e:
                logger.error(f"Error in message handler: {e}")
        
        logger.info("✓ Monitoring active - listening for new messages...")
        logger.info("Press Ctrl+C to stop")
        
        # Keep running
        try:
            await self.client.run_until_disconnected()
        finally:
            self.is_monitoring = False
            await flush_buffer()
            flush_task.cancel()
    
    def stop_monitoring(self) -> None:
        """Stop real-time monitoring."""
        self.is_monitoring = False
        logger.info("Monitoring stopped")
    
    # ==================== Main Modes ====================
    
    async def run(self, mode: str = "hybrid", force_bulk: bool = False) -> None:
        """
        Run the userbot collector.
        
        Args:
            mode: Operating mode
                - 'bulk': One-time bulk import only
                - 'monitor': Real-time monitoring only
                - 'hybrid': Bulk import then monitor (default)
            force_bulk: Run bulk import even if it was previously completed
        """
        await self.initialize_services()
        await self.connect()
        
        try:
            if mode == "bulk":
                await self.run_bulk_import()
            
            elif mode == "monitor":
                if force_bulk or not self.db.is_bulk_import_completed():
                    if force_bulk:
                        logger.info("Force bulk import enabled, running bulk import...")
                    else:
                        logger.info("No previous bulk import found, running bulk import...")
                    await self.run_bulk_import()
                else:
                    logger.info("Bulk import already completed, skipping...")

                await self.start_monitoring()
            
            elif mode == "hybrid":
                # Check if bulk import already done
                if force_bulk or not self.db.is_bulk_import_completed():
                    if force_bulk:
                        logger.info("Force bulk import enabled, running bulk import...")
                    else:
                        logger.info("No previous bulk import found, running bulk import...")
                    await self.run_bulk_import()
                else:
                    logger.info("Bulk import already completed, skipping...")
                
                # Start monitoring
                await self.start_monitoring()
            
            else:
                raise ValueError(f"Invalid mode: {mode}")
        
        except KeyboardInterrupt:
            logger.info("\nShutdown requested by user")
        
        except Exception as e:
            logger.error(f"Error in main loop: {e}")
            raise
        
        finally:
            await self.disconnect()
    
    def print_stats(self) -> None:
        """Print current statistics."""
        print("\n" + "=" * 60)
        print("USERBOT COLLECTOR STATISTICS")
        print("=" * 60)
        print(f"Messages processed:    {self.stats['messages_processed']}")
        print(f"Feedbacks created:     {self.stats['feedbacks_created']}")
        print(f"Professors created:    {self.stats['professors_created']}")
        
        if self.stats["session_start"]:
            uptime = datetime.utcnow() - self.stats["session_start"]
            print(f"Session uptime:        {uptime}")
        
        print("=" * 60)


# Singleton instance
_userbot_collector: Optional[UserbotCollector] = None


def get_userbot_collector() -> UserbotCollector:
    """Get or create userbot collector instance."""
    global _userbot_collector
    if _userbot_collector is None:
        _userbot_collector = UserbotCollector()
    return _userbot_collector
