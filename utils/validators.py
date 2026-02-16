"""
Input validators for WUT Feedback Bot.

Validates user inputs, command arguments, and data integrity.
"""

import re
from typing import Optional, Tuple, List


def validate_professor_name(name: str) -> Tuple[bool, Optional[str]]:
    """
    Validate professor name input.
    
    Args:
        name: Professor name to validate
    
    Returns:
        Tuple of (is_valid, error_message)
    """
    if not name:
        return False, "Professor name is required"
    
    if len(name) < 2:
        return False, "Professor name is too short"
    
    if len(name) > 100:
        return False, "Professor name is too long"
    
    # Check for mainly special characters
    alpha_count = sum(1 for c in name if c.isalpha())
    if alpha_count < 2:
        return False, "Professor name must contain letters"
    
    return True, None


def validate_course_code(code: str) -> Tuple[bool, Optional[str]]:
    """
    Validate course code input.
    
    Args:
        code: Course code to validate
    
    Returns:
        Tuple of (is_valid, error_message)
    """
    if not code:
        return False, "Course code is required"
    
    # Remove spaces and convert to uppercase
    code = code.replace(' ', '').upper()
    
    # Expected format: 2-4 letters followed by 3-4 digits
    if not re.match(r'^[A-Z]{2,4}\d{3,4}$', code):
        return False, "Course code should be in format like 'COSC1570' or 'MATH201'"
    
    return True, None


def validate_rating(rating: float) -> Tuple[bool, Optional[str]]:
    """
    Validate rating value.
    
    Args:
        rating: Rating to validate
    
    Returns:
        Tuple of (is_valid, error_message)
    """
    if rating is None:
        return False, "Rating is required"
    
    if not isinstance(rating, (int, float)):
        return False, "Rating must be a number"
    
    if rating < 1 or rating > 5:
        return False, "Rating must be between 1 and 5"
    
    return True, None


def validate_compare_args(args: List[str]) -> Tuple[bool, Optional[str], Optional[Tuple[str, str]]]:
    """
    Validate compare command arguments.
    
    Expected format: "Professor A vs Professor B"
    
    Args:
        args: Command arguments
    
    Returns:
        Tuple of (is_valid, error_message, (prof1, prof2))
    """
    if not args:
        return False, "Please provide two professor names: /compare Prof A vs Prof B", None
    
    full_text = ' '.join(args)
    
    # Look for "vs" or "versus" separator
    separators = [' vs ', ' vs. ', ' versus ', ' и ', ' va ']
    
    for sep in separators:
        if sep in full_text.lower():
            parts = re.split(sep, full_text, flags=re.IGNORECASE)
            if len(parts) == 2:
                prof1 = parts[0].strip()
                prof2 = parts[1].strip()
                
                valid1, err1 = validate_professor_name(prof1)
                valid2, err2 = validate_professor_name(prof2)
                
                if not valid1:
                    return False, f"First professor name: {err1}", None
                if not valid2:
                    return False, f"Second professor name: {err2}", None
                
                return True, None, (prof1, prof2)
    
    return False, "Use format: /compare Professor A vs Professor B", None


def validate_telegram_user_id(user_id: int) -> bool:
    """
    Validate Telegram user ID.
    
    Args:
        user_id: User ID to validate
    
    Returns:
        True if valid
    """
    return isinstance(user_id, int) and user_id > 0


def validate_group_id(group_id: int) -> bool:
    """
    Validate Telegram group ID.
    
    Args:
        group_id: Group ID to validate
    
    Returns:
        True if valid
    """
    # Group IDs are typically negative numbers
    return isinstance(group_id, int) and group_id != 0


def sanitize_input(text: str, max_length: int = 500) -> str:
    """
    Sanitize user input text.
    
    Args:
        text: Text to sanitize
        max_length: Maximum allowed length
    
    Returns:
        Sanitized text
    """
    if not text:
        return ""
    
    # Truncate to max length
    text = text[:max_length]
    
    # Remove control characters
    text = ''.join(c for c in text if c.isprintable() or c in '\n\t')
    
    # Normalize whitespace
    text = ' '.join(text.split())
    
    return text.strip()


def is_valid_semester(semester: str) -> bool:
    """
    Check if semester string is valid.
    
    Valid formats:
    - "Fall 2023"
    - "Spring 2024"
    - "Summer 2023"
    - "2023-2024"
    
    Args:
        semester: Semester string
    
    Returns:
        True if valid format
    """
    if not semester:
        return False
    
    semester = semester.lower()
    
    # Check for season + year
    if re.match(r'^(fall|spring|summer|winter)\s*\d{4}$', semester):
        return True
    
    # Check for year range
    if re.match(r'^\d{4}\s*[-/]\s*\d{4}$', semester):
        return True
    
    return False
