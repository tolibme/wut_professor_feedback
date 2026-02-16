"""
Database initialization script.

Creates all necessary database tables and initial setup.

Usage:
    python scripts/init_db.py [--drop]
"""

import argparse
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import Config
from models.database_models import create_all_tables, drop_all_tables
from utils.logger import setup_logging, get_logger


def main():
    """Initialize the database."""
    parser = argparse.ArgumentParser(description="Initialize WUT Feedback Bot database")
    parser.add_argument(
        "--drop",
        action="store_true",
        help="Drop all existing tables before creating (WARNING: destroys data!)"
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Skip confirmation for destructive operations"
    )
    args = parser.parse_args()
    
    # Setup logging
    setup_logging(Config.LOG_LEVEL)
    logger = get_logger(__name__)
    
    print("=" * 50)
    print("WUT Feedback Bot - Database Initialization")
    print("=" * 50)
    print()
    
    # Validate config
    try:
        # We only need database URL for this script
        if not Config.DATABASE_URL:
            print("ERROR: DATABASE_URL not configured in .env")
            print("Please copy .env.example to .env and configure DATABASE_URL")
            sys.exit(1)
        
        print(f"Database URL: {Config.DATABASE_URL[:50]}...")
        print()
        
    except Exception as e:
        print(f"ERROR: Configuration error: {e}")
        sys.exit(1)
    
    # Handle drop
    if args.drop:
        if not args.force:
            print("WARNING: This will delete all existing data!")
            confirm = input("Type 'DELETE' to confirm: ")
            if confirm != "DELETE":
                print("Aborted.")
                sys.exit(0)
        
        print("Dropping existing tables...")
        try:
            drop_all_tables()
            print("✓ Tables dropped")
        except Exception as e:
            print(f"ERROR: Failed to drop tables: {e}")
            sys.exit(1)
    
    # Create tables
    print("Creating database tables...")
    try:
        create_all_tables()
        print("✓ Tables created successfully")
    except Exception as e:
        print(f"ERROR: Failed to create tables: {e}")
        logger.exception("Database initialization failed")
        sys.exit(1)
    
    print()
    print("=" * 50)
    print("Database initialization complete!")
    print("=" * 50)
    print()
    print("Tables created:")
    print("  - professors")
    print("  - feedbacks")
    print("  - processed_messages")
    print("  - bulk_import_logs")
    print("  - user_queries")
    print()
    print("Next steps:")
    print("  1. Configure .env with your credentials")
    print("  2. Run: python scripts/bulk_import.py")
    print("  3. Or start the bot: python main.py")


if __name__ == "__main__":
    main()
