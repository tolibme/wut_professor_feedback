
import os
import sys

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from config import Config
except ImportError:
    print("Error: Could not import Config. Ensure you run this from project root.")
    sys.exit(1)

def check_config():
    print("Checking configuration...")
    
    # Check for .env file
    if not os.path.exists(".env"):
        print("❌ .env file not found!")
        return False

    # Check for placeholder values
    placeholders = [
        "your_query_bot_token_here",
        "your_gemini_key",
        "your_hash",
    ]
    
    with open(".env", "r") as f:
        content = f.read()
        for p in placeholders:
            if p in content:
                print(f"❌ Placeholder value found in .env: {p}")
                print("Please update .env with actual values.")
                return False

    try:
        Config.validate()
        print("✅ Configuration format valid.")
    except Exception as e:
        print(f"❌ Configuration validation failed: {e}")
        return False
        
    return True

if __name__ == "__main__":
    if check_config():
        print("Ready to run!")
        sys.exit(0)
    else:
        sys.exit(1)
