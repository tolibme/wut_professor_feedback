"""
Prompts for content moderation.

Contains templates for checking feedback appropriateness
and filtering harmful content.
"""


MODERATION_PROMPT = """Analyze this message for appropriate content in a university feedback context.

MESSAGE:
\"\"\"{message_text}\"\"\"

Check for:
1. Personal attacks or insults (beyond fair criticism)
2. Discriminatory content (racism, sexism, etc.)
3. Threats or harassment
4. Explicit/inappropriate content
5. Doxxing or private information
6. Spam or promotional content

Return JSON only:
{{
    "is_appropriate": true/false,
    "violations": ["list of violations found"] or [],
    "severity": "none" | "low" | "medium" | "high",
    "reason": "brief explanation if inappropriate"
}}

Note: Strong criticism of teaching or grading is acceptable. Personal attacks or discrimination is not."""


CONTENT_FILTER_PROMPT = """Quick check: Is this message appropriate for a university feedback platform?

Message: \"\"\"{message_text}\"\"\"

Return: {{"pass": true/false, "reason": "string or null"}}

Allow: Criticism of teaching, grading, course difficulty
Block: Personal attacks, discrimination, threats, explicit content"""


SENSITIVITY_CHECK_PROMPT = """Check if this feedback contains sensitive information that should be anonymized.

FEEDBACK:
\"\"\"{message_text}\"\"\"

Check for:
1. Student names (other than the author)
2. Personal contact information
3. Specific grade information that could identify someone
4. Private circumstances

Return JSON:
{{
    "has_sensitive_info": true/false,
    "sensitive_items": ["list of items to anonymize"],
    "suggested_redactions": ["suggested replacements"]
}}"""
