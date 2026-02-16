"""
Standalone bulk import script.

Imports historical messages from Telegram group using userbot collector.
Run this before starting monitoring mode for the first time.

Usage:
    python scripts/bulk_import.py [--limit 10000]
"""

import argparse
import asyncio
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import Config, ConfigError
from bots.userbot_collector import get_userbot_collector
from utils.logger import setup_logging, get_logger


async def main():
    """Main entry point for bulk import."""
    parser = argparse.ArgumentParser(
        description="Bulk import historical Telegram messages",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help=f"Maximum messages to process (default: {Config.BULK_IMPORT_LIMIT})"
    )
    
    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default="INFO",
        help="Logging level"
    )
    
    args = parser.parse_args()
    
    # Setup logging
    setup_logging(args.log_level, Config.LOG_FILE)
    logger = get_logger(__name__)
    
    print("=" * 60)
    print("WUT Feedback Bot - Bulk Import (Userbot Mode)")
    print("=" * 60)
    print()
    
    # Validate configuration
    try:
        Config.validate(mode="collector")
        Config.ensure_directories()
    except ConfigError as e:
        print(f"Configuration Error:\n{e}")
        sys.exit(1)
    
    print(f"Group ID: {Config.FEEDBACK_GROUP_ID}")
    print(f"Limit: {args.limit or Config.BULK_IMPORT_LIMIT}")
    print()
    
    # Get userbot collector
    collector = get_userbot_collector()
    
    try:
        # Initialize and connect
        await collector.initialize_services()
        await collector.connect()
        
        # Run bulk import
        stats = await collector.run_bulk_import(limit=args.limit)
        
        # Print summary
        print()
        print("=" * 60)
        print("IMPORT COMPLETE")
        print("=" * 60)
        print()
        print(f"Total Messages:     {stats.get('total_messages', 0)}")
        print(f"Feedbacks Created:  {stats.get('feedbacks_created', 0)}")
        print(f"Professors Created: {stats.get('professors_created', 0)}")
        print(f"Errors:             {stats.get('errors', 0)}")
        
        if stats.get('duration_minutes'):
            print(f"Duration:           {stats['duration_minutes']:.1f} minutes")
        
        print()
        
        if stats.get('error'):
            print(f"❌ Import failed: {stats['error']}")
            sys.exit(1)
        else:
            print("✅ Import successful!")
            print()
            print("Next steps:")
            print("  - Start monitoring: python main.py --mode collector --collector-mode monitor")
            print("  - Start query bot:  python main.py --mode query")
    
    except KeyboardInterrupt:
        print("\n\nImport interrupted by user.")
        sys.exit(0)
    
    except Exception as e:
        logger.exception("Bulk import failed")
        print(f"\n❌ ERROR: {e}")
        sys.exit(1)
    
    finally:
        await collector.disconnect()


if __name__ == "__main__":
    asyncio.run(main())