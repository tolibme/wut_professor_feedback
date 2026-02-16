# WUT Professor Feedback Bot

A Telegram userbot + bot system for Webster University in Tashkent (WUT) that collects and analyzes professor feedback, providing an AI-powered student query interface.

## 🎯 Features

### Userbot Collector (Your Telegram Account)
- **No Bot Permissions Needed** - Runs as your personal Telegram account
- **Bulk Import** - Process up to 10,000+ historical messages from any group you're in
- **Real-time Monitoring** - Automatically processes new messages as they arrive
- **Smart Extraction** - Gemini AI extracts structured data from unstructured feedback
- **Multi-language** - Supports English, Russian, and Uzbek
- **Content Moderation** - Filters inappropriate content automatically

### Query Bot
- **Professor Search** - `/search Professor Name` for detailed professor info
- **Compare Professors** - `/compare Prof A vs Prof B` side-by-side comparison
- **Course Recommendations** - `/course COSC 1570` find best professors for a course
- **Natural Language** - Just type questions like "Is Professor Johnson good?"
- **Statistics & Rankings** - `/stats` and `/top` for overall insights

## 📋 Prerequisites

- Python 3.9+
- PostgreSQL database
- **Your Telegram account** (for userbot collector)
- Telegram API credentials (get from [my.telegram.org](https://my.telegram.org/apps))
- Telegram Bot token for Query Bot (get from [@BotFather](https://t.me/BotFather))
- Gemini API key (get from [Google AI Studio](https://makersuite.google.com/app/apikey))

## 🚀 Quick Start

### 1. Clone and Install

```bash
cd wuit_professor_feedback_bot
pip install -r requirements.txt
```

### 2. Configure Environment

```bash
# Copy example configuration
copy .env.example .env

# Edit .env with your credentials
```

Required environment variables:
- `TELEGRAM_BOT_TOKEN_QUERY` - Query bot token (from @BotFather)
- `TELEGRAM_API_ID` - Telegram API ID (from my.telegram.org/apps)
- `TELEGRAM_API_HASH` - Telegram API hash (from my.telegram.org/apps)
- `FEEDBACK_GROUP_ID` - Target feedback group ID
- `GEMINI_API_KEY` - Google Gemini API key
- `GEMINI_MODEL` - Optional model override (auto-selects if omitted)
- `DATABASE_URL` - PostgreSQL connection string

### 3. Initialize Database

```bash
python scripts/init_db.py
```

## 🐳 Docker

### Build and Run

```bash
docker compose up --build
```

This starts:
- `app` running the userbot collector in hybrid mode
- `db` PostgreSQL database

### Run Query Bot Instead

```bash
docker compose run --rm app python main.py --mode query
```

### Notes
- Ensure your `.env` has a valid `DATABASE_URL` that points to the Docker DB:
    `postgresql://postgres:postgres@db:5432/wut_feedback`
- The Telethon session file is mounted from `collector_session.session`.

### 4. First Run - Authenticate Your Account

On first run, you'll need to authenticate your Telegram account:

```bash
python main.py --mode collector --collector-mode bulk
```

You'll be prompted for:
1. Your phone number (with country code, e.g., +998901234567)
2. Verification code sent to your Telegram

After authentication, a session file is created and you won't need to login again.

### 5. Operating Modes

```bash
# Bulk import only (one-time historical messages)
python main.py --mode collector --collector-mode bulk

# Real-time monitoring only (listens for new messages)
python main.py --mode collector --collector-mode monitor

# Hybrid mode: bulk import + monitoring (recommended)
python main.py --mode collector --collector-mode hybrid

# Run query bot only
python main.py --mode query

# Run both collector and query bot
python main.py --mode both
```

## 📁 Project Structure

```
wuit_professor_feedback_bot/
├── main.py                 # Entry point
├── config.py               # Configuration
├── requirements.txt        # Dependencies
├── .env.example           # Environment template
│
├── bots/
│   ├── userbot_collector.py   # Userbot feedback collector
│   └── query_bot.py           # Student query bot
│
├── services/
│   ├── database_service.py        # Database operations
│   ├── gemini_service.py          # AI extraction & responses
│   ├── embedding_service.py       # Vector embeddings
│   ├── telegram_history_service.py # Telethon wrapper
│   └── analytics_service.py       # Statistics
│
├── models/
│   └── database_models.py  # SQLAlchemy models
│
├── prompts/
│   ├── extraction_prompts.py  # Feedback extraction
│   ├── query_prompts.py       # Query responses
│   └── moderation_prompts.py  # Content filtering
│
├── utils/
│   ├── text_processing.py  # Text utilities
│   ├── validators.py       # Input validation
│   └── logger.py           # Logging
│
└── scripts/
    ├── init_db.py          # Database setup
    ├── bulk_import.py      # Historical import
    └── export_data.py      # Data export
```

## 🤖 Bot Commands

### Userbot Collector
No commands - runs automatically. Configured via command-line arguments:
- `--collector-mode bulk` - One-time historical import
- `--collector-mode monitor` - Real-time listening
- `--collector-mode hybrid` - Both (recommended)

### Query Bot (Students)
| Command | Description |
|---------|-------------|
| `/search <name>` | Search professor |
| `/compare <A> vs <B>` | Compare professors |
| `/course <code>` | Best profs for course |
| `/stats` | Overall statistics |
| `/top` | Top rated professors |

## 📊 Database Schema

### Tables
- **professors** - Professor info and aggregate statistics
- **feedbacks** - Individual feedback entries with extracted data
- **processed_messages** - Track processed Telegram messages
- **bulk_import_logs** - Import operation logs
- **user_queries** - Query history for analytics

## 🔧 Configuration

### Environment Variables

```env
# Telegram - Query Bot
TELEGRAM_BOT_TOKEN_QUERY=your_query_token

# Telegram - Userbot Collector
TELEGRAM_API_ID=12345678
TELEGRAM_API_HASH=your_hash
FEEDBACK_GROUP_ID=-1001234567890

# AI
GEMINI_API_KEY=your_gemini_key
GEMINI_MODEL=gemini-1.5-flash

# Database
DATABASE_URL=postgresql://user:pass@localhost:5432/wuit_feedback

# Settings
BULK_IMPORT_LIMIT=10000
CHECK_INTERVAL_MINUTES=30
MIN_EXTRACTION_CONFIDENCE=0.7
ADMIN_USER_IDS=123456789
```

## 📤 Data Export

Export collected data to CSV:

```bash
python scripts/export_data.py --output ./exports
```

This creates:
- `professors.csv` - All professor data
- `feedbacks.csv` - All feedback entries
- `statistics.txt` - Summary statistics

## 🛠️ Development

### Running Tests
```bash
# Validate CLI works
python main.py --help

# Test database connection
python scripts/init_db.py
```

### Logging
Logs are written to `logs/bot.log` (configurable via `LOG_FILE`).

## 📝 License

MIT License

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Submit a pull request

---

Built for Webster University in Tashkent (WUT) 🎓
