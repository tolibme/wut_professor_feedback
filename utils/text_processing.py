"""
Text processing utilities for WUT Feedback Bot.

Handles name normalization, text cleaning, language detection,
and other text manipulation functions.
"""

import re
import unicodedata
from typing import Optional, List

try:
    from langdetect import detect, LangDetectException
except ImportError:
    detect = None
    LangDetectException = Exception


def normalize_professor_name(name: str) -> str:
    """
    Normalize a professor name for consistent matching.
    
    Transformations:
    - Lowercase
    - Remove extra whitespace
    - Remove titles (Dr., Prof., etc.)
    - Normalize Unicode characters
    - Handle name variations (e.g., "John Smith" == "Smith, John")
    
    Args:
        name: Professor name to normalize
    
    Returns:
        Normalized name string
    """
    if not name:
        return ""
    
    # Normalize Unicode
    name = unicodedata.normalize('NFKD', name)

    # Transliterate Cyrillic to Latin for cross-script matching
    cyrillic_map = {
        'а': 'a', 'б': 'b', 'в': 'v', 'г': 'g', 'д': 'd', 'е': 'e', 'ё': 'e',
        'ж': 'zh', 'з': 'z', 'и': 'i', 'й': 'i', 'к': 'k', 'л': 'l', 'м': 'm',
        'н': 'n', 'о': 'o', 'п': 'p', 'р': 'r', 'с': 's', 'т': 't', 'у': 'u',
        'ф': 'f', 'х': 'h', 'ц': 'ts', 'ч': 'ch', 'ш': 'sh', 'щ': 'shch',
        'ъ': '', 'ы': 'y', 'ь': '', 'э': 'e', 'ю': 'yu', 'я': 'ya',
        'А': 'a', 'Б': 'b', 'В': 'v', 'Г': 'g', 'Д': 'd', 'Е': 'e', 'Ё': 'e',
        'Ж': 'zh', 'З': 'z', 'И': 'i', 'Й': 'i', 'К': 'k', 'Л': 'l', 'М': 'm',
        'Н': 'n', 'О': 'o', 'П': 'p', 'Р': 'r', 'С': 's', 'Т': 't', 'У': 'u',
        'Ф': 'f', 'Х': 'h', 'Ц': 'ts', 'Ч': 'ch', 'Ш': 'sh', 'Щ': 'shch',
        'Ъ': '', 'Ы': 'y', 'Ь': '', 'Э': 'e', 'Ю': 'yu', 'Я': 'ya',
    }
    name = ''.join(cyrillic_map.get(ch, ch) for ch in name)
    
    # Lowercase
    name = name.lower().strip()
    
    # Remove common titles
    titles = [
        r'\bdr\.?\s*',
        r'\bprof\.?\s*',
        r'\bprofessor\s*',
        r'\bmr\.?\s*',
        r'\bmrs\.?\s*',
        r'\bms\.?\s*',
        r'\bphd\.?\s*',
        r'\bph\.d\.?\s*',
    ]
    for title in titles:
        name = re.sub(title, '', name, flags=re.IGNORECASE)
    
    # Remove parenthetical content
    name = re.sub(r'\([^)]*\)', '', name)
    
    # Remove special characters except spaces and hyphens
    name = re.sub(r'[^\w\s\-]', '', name)
    
    # Normalize whitespace
    name = ' '.join(name.split())

    # Map common name variants to a canonical form
    alias_map = {
        "javed": "javad",
    }
    parts = [alias_map.get(part, part) for part in name.split()]
    name = " ".join(parts)
    
    # Handle "Last, First" format - convert to "First Last"
    if ',' in name:
        parts = [p.strip() for p in name.split(',', 1)]
        if len(parts) == 2:
            name = f"{parts[1]} {parts[0]}"
    
    return name.strip()


def clean_feedback_text(text: str) -> str:
    """
    Clean feedback text for processing.
    
    Removes:
    - Multiple newlines
    - Excessive whitespace
    - Control characters
    
    Args:
        text: Raw feedback text
    
    Returns:
        Cleaned text
    """
    if not text:
        return ""
    
    # Normalize Unicode
    text = unicodedata.normalize('NFKC', text)
    
    # Remove control characters except newlines and tabs
    text = ''.join(char for char in text if unicodedata.category(char) != 'Cc' or char in '\n\t')
    
    # Replace multiple newlines with double newline
    text = re.sub(r'\n{3,}', '\n\n', text)
    
    # Replace multiple spaces with single space
    text = re.sub(r' {2,}', ' ', text)
    
    # Strip leading/trailing whitespace from each line
    lines = [line.strip() for line in text.split('\n')]
    text = '\n'.join(lines)
    
    return text.strip()


def detect_language(text: str) -> Optional[str]:
    """
    Detect the language of text.
    
    Args:
        text: Text to analyze
    
    Returns:
        Language code (en, ru, uz, etc.) or None
    """
    if not text or not detect:
        return None
    
    try:
        lang = detect(text)
        # Map some language codes
        lang_map = {
            'ru': 'ru',
            'en': 'en',
            'uz': 'uz',
            'tr': 'uz',  # Turkish is often confused with Uzbek
        }
        return lang_map.get(lang, lang)
    except LangDetectException:
        return None


def extract_course_code(text: str) -> Optional[str]:
    """
    Extract course code from text.
    
    Looks for patterns like:
    - COSC 1570
    - MATH-201
    - CS101
    
    Args:
        text: Text to search
    
    Returns:
        Course code or None
    """
    if not text:
        return None
    
    # Common course code patterns
    patterns = [
        r'\b([A-Z]{2,4})\s*[-]?\s*(\d{3,4})\b',  # COSC 1570, MATH-201
        r'\b([A-Z]{2,4})(\d{3,4})\b',  # CS101
    ]
    
    for pattern in patterns:
        match = re.search(pattern, text.upper())
        if match:
            groups = match.groups()
            if len(groups) == 2:
                return f"{groups[0]} {groups[1]}"
    
    return None


def truncate_text(text: str, max_length: int = 500, suffix: str = "...") -> str:
    """
    Truncate text to maximum length, preserving word boundaries.
    
    Args:
        text: Text to truncate
        max_length: Maximum length
        suffix: Suffix to add if truncated
    
    Returns:
        Truncated text
    """
    if not text or len(text) <= max_length:
        return text
    
    # Find last space before max_length
    truncated = text[:max_length - len(suffix)]
    last_space = truncated.rfind(' ')
    
    if last_space > max_length * 0.7:  # Don't cut too much
        truncated = truncated[:last_space]
    
    return truncated + suffix


def extract_rating_from_text(text: str) -> Optional[float]:
    """
    Extract explicit rating from text.
    
    Looks for patterns like:
    - "Rating: 4/5"
    - "I give 8/10"
    - "4.5 stars"
    - "оценка 4"
    - "баҳо 5"
    
    Args:
        text: Text to search
    
    Returns:
        Rating normalized to 1-5 scale or None
    """
    if not text:
        return None
    
    text_lower = text.lower()
    
    # Pattern: X/5 or X/10
    patterns = [
        (r'(\d+(?:\.\d+)?)\s*/\s*5', 5),   # X/5
        (r'(\d+(?:\.\d+)?)\s*/\s*10', 10), # X/10
        (r'(\d+(?:\.\d+)?)\s*(?:из|out of)\s*5', 5),  # X out of 5
        (r'(\d+(?:\.\d+)?)\s*(?:stars?|звезд)', 5),   # X stars
        (r'(?:rating|оценка|баҳо)[:\s]*(\d+(?:\.\d+)?)', 5),  # rating: X
    ]
    
    for pattern, scale in patterns:
        match = re.search(pattern, text_lower)
        if match:
            try:
                value = float(match.group(1))
                # Normalize to 1-5 scale
                if scale == 10:
                    value = value / 2
                # Clamp to valid range
                value = max(1.0, min(5.0, value))
                return value
            except ValueError:
                continue
    
    return None


def split_into_sentences(text: str) -> List[str]:
    """
    Split text into sentences.
    
    Args:
        text: Text to split
    
    Returns:
        List of sentences
    """
    if not text:
        return []
    
    # Split on sentence-ending punctuation
    sentences = re.split(r'(?<=[.!?])\s+', text)
    
    # Filter empty and very short sentences
    sentences = [s.strip() for s in sentences if len(s.strip()) > 5]
    
    return sentences


def contains_professor_mention(text: str) -> bool:
    """
    Check if text likely mentions a professor.
    
    Args:
        text: Text to check
    
    Returns:
        True if professor mention is likely
    """
    if not text:
        return False
    
    text_lower = text.lower()
    
    # Keywords that suggest professor mention
    keywords = [
        'professor', 'prof', 'teacher', 'instructor', 'lecturer',
        'профессор', 'преподаватель', 'учитель', 'доцент',
        'professor', "o'qituvchi", 'ustoz',
    ]
    
    for keyword in keywords:
        if keyword in text_lower:
            return True
    
    # Check for title patterns
    if re.search(r'\b(dr|prof)\.?\s+[a-z]', text_lower):
        return True
    
    return False
