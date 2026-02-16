# Setup & Run Guide

## Status
- ✅ **Dependencies**: Installed & Fixed (NumPy <2.0, Sentence-Transformers >=3.0.0, Google-GenerativeAI >=0.8.0).
- ✅ **Database**: Connected (`wut_feedback` on localhost).
- ✅ **AI Model**: Configured to use `gemini-1.5-flash`.
- ⚠️ **Configuration**: Check `.env` for valid API keys.

## Recent Fixes
- **NumPy Compatibility**: Downgraded to 1.26.4.
- **HuggingFace Hub**: Upgraded `sentence-transformers`.
- **Gemini API**: Upgraded library and switched to `gemini-1.5-flash`.
- **ChromaDB**: Updated for compatibility.

## Next Steps

### 1. Configure API Tokens
Open `.env` and replace the placeholders:
```ini
TELEGRAM_BOT_TOKEN_QUERY=your_real_token
TELEGRAM_API_ID=your_id
TELEGRAM_API_HASH=your_hash
GEMINI_API_KEY=your_gemini_key
```

### 2. Run the Bot
To run both the Collector and Query Bot:
```bash
python main.py
```
