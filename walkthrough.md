# Startup Fixes & Status

## Issues Resolved
1.  **ChromaDB Deprecation**: Updated to use `chromadb.PersistentClient`.
2.  **NumPy Compatibility**: Downgraded `numpy` to `<2.0` (1.26.4).
3.  **HuggingFace Hub**: Upgraded `sentence-transformers` to `>=3.0.0`.
4.  **Gemini API Error**: Upgraded `google-generativeai` to `0.8.0+` and switched model to `gemini-1.5-flash` (fixed 404 error).

## Current Status
- ✅ **Application**: Running successfully (Collector + Query Bot).
- ✅ **Dependencies**: All updated in `requirements.txt`.
- ✅ **AI Services**: Gemini 1.5 Flash active.

## How to Run
```bash
python main.py
```
