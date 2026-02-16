"""
WUT Professor Feedback Bot - Main Entry Point

A dual-mode Telegram system for Webster University in Tashkent:
1. Userbot Collector: Uses your Telegram account to collect feedback from groups
2. Query Bot: Student-facing assistant for professor information

Usage:
    python main.py --mode collector    # Run userbot collector only
    python main.py --mode query        # Run query bot only
    python main.py --mode both         # Run both (default)
    
Collector sub-modes:
    python main.py --mode collector --collector-mode bulk      # One-time import
    python main.py --mode collector --collector-mode monitor   # Real-time monitoring
    python main.py --mode collector --collector-mode hybrid    # Both (default)
"""

import argparse
import asyncio
import signal
import sys
from typing import Optional

from config import Config, ConfigError
from utils.logger import setup_logging, get_logger

# Ensure console can handle UTF-8 output (emoji, box chars, etc.)
if sys.platform.startswith("win"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


# Global for graceful shutdown
shutdown_event: Optional[asyncio.Event] = None


def setup_signal_handlers():
    """Setup signal handlers for graceful shutdown."""
    global shutdown_event
    shutdown_event = asyncio.Event()
    
    def signal_handler(sig, frame):
        print("\nReceived shutdown signal. Shutting down gracefully...")
        if shutdown_event:
            shutdown_event.set()
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)


async def run_collector(collector_mode: str = "hybrid", force_bulk: bool = False):
    """Run the userbot collector."""
    from bots.userbot_collector import get_userbot_collector
    
    logger = get_logger(__name__)
    logger.info(f"Starting Userbot Collector (mode: {collector_mode})...")
    
    collector = get_userbot_collector()
    await collector.run(mode=collector_mode, force_bulk=force_bulk)


async def run_query():
    """Run the query bot."""
    from bots.query_bot import QueryBot
    
    logger = get_logger(__name__)
    logger.info("Starting Query Bot...")
    
    bot = QueryBot()
    await bot.start()


async def run_both(collector_mode: str = "hybrid", force_bulk: bool = False):
    """Run collector and query bot concurrently."""
    logger = get_logger(__name__)
    logger.info("Starting both userbot collector and query bot...")
    
    # Run both
    await asyncio.gather(
        run_collector(collector_mode, force_bulk=force_bulk),
        run_query()
    )


def print_banner():
    """Print application banner."""
    banner = r"""
+--------------------------------------------------------------+
|                                                              |
|   WUT Professor Feedback Bot                                 |
|   Webster University in Tashkent                             |
|                                                              |
|   Collect, Analyze, and Query Professor Feedback             |
|                                                              |
+--------------------------------------------------------------+
"""
    print(banner)


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="WUT Professor Feedback Bot",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py --mode collector    # Run collector only
  python main.py --mode query        # Run query bot only
  python main.py --mode both         # Run both (default)

First-time setup:
  1. Copy .env.example to .env and configure
  2. Run: python scripts/init_db.py
  3. Run: python scripts/bulk_import.py
  4. Run: python main.py
        """
    )
    
    parser.add_argument(
        "--mode",
        choices=["collector", "query", "both"],
        default="both",
        help="Which mode to run (default: both)"
    )
    
    parser.add_argument(
        "--collector-mode",
        choices=["bulk", "monitor", "hybrid"],
        default="hybrid",
        help="Collector sub-mode: bulk import, monitor, or hybrid (default: hybrid)"
    )

    parser.add_argument(
        "--force-bulk-import",
        action="store_true",
        help="Force bulk import even if it was previously completed"
    )
    
    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default=None,
        help="Override log level from config"
    )
    
    args = parser.parse_args()
    
    # Print banner
    print_banner()
    
    # Setup logging
    log_level = args.log_level or Config.LOG_LEVEL
    setup_logging(log_level, Config.LOG_FILE)
    logger = get_logger(__name__)
    
    # Validate configuration
    print(f"Mode: {args.mode.upper()}")
    print(f"Log Level: {log_level}")
    print()
    
    print("Validating configuration...")
    try:
        Config.validate(mode=args.mode)
        Config.ensure_directories()
        print("[OK] Configuration valid")
    except ConfigError as e:
        print("\n[ERROR] Configuration Error:")
        print(str(e))
        print("\nPlease check your .env file.")
        print("Copy .env.example to .env if you haven't already.")
        sys.exit(1)
    
    print()
    
    # Setup signal handlers
    setup_signal_handlers()
    
    # Run the appropriate mode
    try:
        if args.mode == "collector":
            mode_desc = {
                "bulk": "One-time bulk import",
                "monitor": "Real-time monitoring",
                "hybrid": "Bulk import + monitoring"
            }
            print(f"Starting Userbot Collector ({mode_desc[args.collector_mode]})...")
            print("Press Ctrl+C to stop")
            print("-" * 50)
            asyncio.run(run_collector(args.collector_mode, force_bulk=args.force_bulk_import))
        
        elif args.mode == "query":
            print("Starting Query Bot...")
            print("Press Ctrl+C to stop")
            print("-" * 50)
            asyncio.run(run_query())
        
        else:  # both
            print("Starting Userbot Collector + Query Bot...")
            print("Press Ctrl+C to stop")
            print("-" * 50)
            asyncio.run(run_both(args.collector_mode, force_bulk=args.force_bulk_import))
    
    except KeyboardInterrupt:
        print("\nShutdown complete.")
    except Exception as e:
        logger.exception("Fatal error")
        print(f"\n[ERROR] Fatal Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
