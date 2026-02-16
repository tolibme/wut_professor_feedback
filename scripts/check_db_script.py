
import os
import sys
import psycopg2
from urllib.parse import urlparse

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from config import Config
except ImportError:
    # Fallback if config not importable yet
    from dotenv import load_dotenv
    load_dotenv()
    class Config:
        DATABASE_URL = os.getenv("DATABASE_URL")

def check_db():
    print("Checking database connection...")
    
    db_url = Config.DATABASE_URL
    if not db_url:
        print("❌ DATABASE_URL not found in environment.")
        return False
        
    try:
        # Parse URL to get connection details
        result = urlparse(db_url)
        username = result.username
        password = result.password
        database = result.path[1:]
        hostname = result.hostname
        port = result.port
        
        print(f"Connecting to {database} at {hostname}:{port} as {username}...")
        
        conn = psycopg2.connect(
            dbname=database,
            user=username,
            password=password,
            host=hostname,
            port=port
        )
        conn.close()
        print("✅ Database connection successful!")
        return True
    except psycopg2.OperationalError as e:
        print(f"❌ Connection failed: {e}")
        return False
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

if __name__ == "__main__":
    if check_db():
        sys.exit(0)
    else:
        sys.exit(1)
