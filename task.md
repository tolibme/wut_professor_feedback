# Project Setup Checklist

- [x] Install dependencies
- [ ] Configure environment variables
    - [ ] Update `TELEGRAM_BOT_TOKEN_QUERY` in `.env`
- [ ] Initialize Database
    - [x] Create `wut_feedback` database if not exists
    - [x] Run `python scripts/init_db.py`
- [x] Run the application
    - [x] `python main.py`
- [x] Debugging startup failure
    - [x] Modify `main.py` to expose exceptions
    - [x] Identify and fix the root cause (NumPy 2.0 incompatibility)
    - [x] Fix `huggingface_hub` incompatibility (Upgraded `sentence-transformers`)
- [x] Fix Gemini API Error
    - [x] Upgrade `google-generativeai` library
    - [x] Update model name (`gemini-1.5-flash`)
