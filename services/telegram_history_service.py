"""
Telegram history service for WUT Feedback Bot.

Uses Telethon to fetch historical messages from Telegram groups
for bulk import and incremental updates.
"""

import asyncio
from datetime import datetime
from typing import List, Dict, Any, Optional, AsyncIterator

from telethon import TelegramClient
from telethon.tl.types import Message, PeerChannel

from config import Config
from utils.logger import get_logger

logger = get_logger(__name__)


class TelegramHistoryServiceError(Exception):
    """Custom exception for Telegram history service errors."""
    pass


class TelegramHistoryService:
    """
    Service for fetching Telegram message history.
    
    Uses Telethon client to:
    - Bulk import historical messages
    - Fetch new messages for incremental updates
    - Handle rate limiting and pagination
    """
    
    def __init__(
        self,
        api_id: int = None,
        api_hash: str = None,
        session_name: str = "collector_session",
    ):
        """
        Initialize Telegram history service.
        
        Args:
            api_id: Telegram API ID
            api_hash: Telegram API hash
            session_name: Name for session file
        """
        self.api_id = api_id or Config.TELEGRAM_API_ID
        self.api_hash = api_hash or Config.TELEGRAM_API_HASH
        self.session_name = session_name
        
        if not self.api_id or not self.api_hash:
            raise TelegramHistoryServiceError(
                "Telegram API credentials are required"
            )
        
        self.client: Optional[TelegramClient] = None
        self._connected = False
    
    async def connect(self) -> None:
        """
        Connect to Telegram.
        
        Creates Telethon client and authenticates.
        First run will prompt for phone number and code.
        """
        if self._connected:
            return
        
        self.client = TelegramClient(
            self.session_name,
            self.api_id,
            self.api_hash,
        )
        
        await self.client.start()
        self._connected = True
        
        me = await self.client.get_me()
        logger.info(f"Connected to Telegram as {me.first_name} ({me.id})")
    
    async def disconnect(self) -> None:
        """Disconnect from Telegram."""
        if self.client and self._connected:
            await self.client.disconnect()
            self._connected = False
            logger.info("Disconnected from Telegram")
    
    async def __aenter__(self):
        """Async context manager entry."""
        await self.connect()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.disconnect()
    
    async def get_group_info(self, group_id: int) -> Dict[str, Any]:
        """
        Get information about a Telegram group.
        
        Args:
            group_id: Telegram group/channel ID
        
        Returns:
            Dictionary with group info
        """
        await self.connect()
        
        try:
            entity = await self.client.get_entity(group_id)
            return {
                "id": entity.id,
                "title": getattr(entity, 'title', 'Unknown'),
                "username": getattr(entity, 'username', None),
                "participants_count": getattr(entity, 'participants_count', None),
            }
        except Exception as e:
            logger.error(f"Error getting group info: {e}")
            raise TelegramHistoryServiceError(f"Failed to get group info: {e}")
    
    async def fetch_messages(
        self,
        group_id: int,
        limit: int = 10000,
        min_id: int = 0,
        max_id: int = 0,
    ) -> AsyncIterator[Dict[str, Any]]:
        """
        Fetch messages from a Telegram group.
        
        Yields messages one at a time for memory efficiency.
        
        Args:
            group_id: Telegram group/channel ID
            limit: Maximum messages to fetch
            min_id: Minimum message ID (for incremental updates)
            max_id: Maximum message ID (for pagination)
        
        Yields:
            Dictionary with message data
        """
        await self.connect()
        
        processed = 0
        
        try:
            async for message in self.client.iter_messages(
                group_id,
                limit=limit,
                min_id=min_id,
                offset_id=max_id,
            ):
                if not isinstance(message, Message):
                    continue
                
                # Skip empty messages
                if not message.text:
                    continue
                
                # Extract message data
                yield {
                    "id": message.id,
                    "text": message.text,
                    "date": message.date,
                    "user_id": message.from_id.user_id if message.from_id else None,
                    "reply_to": message.reply_to_msg_id if message.reply_to else None,
                }
                
                processed += 1
                
                # Log progress every 500 messages
                if processed % 500 == 0:
                    logger.info(f"Fetched {processed} messages...")
        
        except Exception as e:
            logger.error(f"Error fetching messages: {e}")
            raise TelegramHistoryServiceError(f"Failed to fetch messages: {e}")
        
        logger.info(f"Total messages fetched: {processed}")
    
    async def fetch_messages_batch(
        self,
        group_id: int,
        limit: int = 10000,
        min_id: int = 0,
        batch_size: int = 100,
    ) -> List[List[Dict[str, Any]]]:
        """
        Fetch messages in batches for efficient processing.
        
        Args:
            group_id: Telegram group/channel ID
            limit: Maximum messages to fetch
            min_id: Minimum message ID
            batch_size: Messages per batch
        
        Returns:
            List of message batches
        """
        batches = []
        current_batch = []
        
        async for message in self.fetch_messages(group_id, limit, min_id):
            current_batch.append(message)
            
            if len(current_batch) >= batch_size:
                batches.append(current_batch)
                current_batch = []
        
        # Don't forget the last batch
        if current_batch:
            batches.append(current_batch)
        
        return batches
    
    async def bulk_import_history(
        self,
        group_id: int,
        limit: int = 10000,
        callback=None,
    ) -> Dict[str, Any]:
        """
        Bulk import historical messages from a group.
        
        This is the main method for initial data population.
        
        Args:
            group_id: Telegram group/channel ID
            limit: Maximum messages to import
            callback: Optional async callback for progress updates
                     Signature: async def callback(processed: int, total: int)
        
        Returns:
            Dictionary with import statistics
        """
        await self.connect()
        
        start_time = datetime.utcnow()
        messages = []
        
        logger.info(f"Starting bulk import from group {group_id}, limit={limit}")
        
        # Fetch all messages
        async for message in self.fetch_messages(group_id, limit):
            messages.append(message)
            
            # Call progress callback
            if callback and len(messages) % 100 == 0:
                await callback(len(messages), limit)
        
        end_time = datetime.utcnow()
        duration = (end_time - start_time).total_seconds()
        
        result = {
            "total_messages": len(messages),
            "messages": messages,
            "started_at": start_time,
            "completed_at": end_time,
            "duration_seconds": duration,
            "group_id": group_id,
        }
        
        logger.info(
            f"Bulk import complete: {len(messages)} messages in {duration:.1f}s"
        )
        
        return result
    
    async def fetch_new_messages_since(
        self,
        group_id: int,
        last_message_id: int,
        limit: int = 1000,
    ) -> List[Dict[str, Any]]:
        """
        Fetch new messages since a specific message ID.
        
        Used for incremental updates during monitoring.
        
        Args:
            group_id: Telegram group/channel ID
            last_message_id: ID of the last processed message
            limit: Maximum new messages to fetch
        
        Returns:
            List of new messages (oldest first)
        """
        await self.connect()
        
        messages = []
        
        async for message in self.fetch_messages(
            group_id,
            limit=limit,
            min_id=last_message_id,
        ):
            messages.append(message)
        
        # Return in chronological order (oldest first)
        messages.reverse()
        
        logger.info(f"Found {len(messages)} new messages since ID {last_message_id}")
        
        return messages
    
    async def get_message_count(self, group_id: int) -> int:
        """
        Get approximate total message count in a group.
        
        Args:
            group_id: Telegram group/channel ID
        
        Returns:
            Approximate message count
        """
        await self.connect()
        
        try:
            # Get the latest message to estimate count
            async for message in self.client.iter_messages(group_id, limit=1):
                return message.id
        except Exception as e:
            logger.warning(f"Error getting message count: {e}")
        
        return 0


# Singleton instance
_telegram_history_service: Optional[TelegramHistoryService] = None


def get_telegram_history_service(
    api_id: int = None,
    api_hash: str = None,
) -> TelegramHistoryService:
    """Get or create Telegram history service singleton."""
    global _telegram_history_service
    if _telegram_history_service is None:
        _telegram_history_service = TelegramHistoryService(api_id, api_hash)
    return _telegram_history_service
