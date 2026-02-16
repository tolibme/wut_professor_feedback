"""
Prompts for extracting feedback data from unstructured text.

Contains templates for Gemini AI to extract structured professor
feedback information from student messages.
"""


FEEDBACK_EXTRACTION_PROMPT = """You are an AI assistant that extracts structured data from student feedback about university professors. Analyze the following message and extract information.

IMPORTANT INSTRUCTIONS:
1. Extract professor name exactly as mentioned (preserve original spelling)
2. Also provide a normalized professor name in Latin script, fixing common misspellings
3. Identify course code if mentioned (format: DEPT XXXX, e.g., "COSC 1570")
4. Determine sentiment from context and explicit statements
5. Rate teaching aspects on a 1-5 scale based on the feedback content
6. If information is not mentioned, set it to null
7. Be conservative with ratings - only rate aspects that are explicitly or clearly implicitly mentioned
8. Handle Russian, Uzbek, and English text

Return ONLY valid JSON with this exact structure. Do NOT wrap in code fences or extra text:
```json
{{
    "is_feedback": true/false,
    "professor_name": "string or null",
    "professor_name_normalized": "string or null",
    "course_code": "string or null",
    "course_name": "string or null",
    "semester": "string or null",
    "explicit_rating": number 1-5 or null,
    "inferred_rating": number 1-5 or null,
    "sentiment": "positive" | "negative" | "neutral" | "mixed" | null,
    "aspects": {{
        "teaching_quality": {{"score": 1-5, "comment": "brief note"}},
        "grading_fairness": {{"score": 1-5, "comment": "brief note"}},
        "workload": {{"score": 1-5, "comment": "brief note"}},
        "communication": {{"score": 1-5, "comment": "brief note"}},
        "engagement": {{"score": 1-5, "comment": "brief note"}},
        "exams_difficulty": {{"score": 1-5, "comment": "brief note"}}
    }},
    "strengths": ["point 1", "point 2"],
    "weaknesses": ["point 1", "point 2"],
    "confidence": 0.0-1.0,
    "language": "en" | "ru" | "uz",
    "is_appropriate": true/false
}}
```

SCORING GUIDELINES:
- 5: Excellent, highly praised
- 4: Good, positive feedback
- 3: Average, neutral or mixed
- 2: Below average, some criticism
- 1: Poor, strong criticism

For aspects not mentioned in the feedback, omit them from the "aspects" object entirely.

Set "is_feedback" to false if the message is:
- Just a question without feedback
- Off-topic discussion
- Not related to a professor or course

Set "is_appropriate" to false if the message contains:
- Personal attacks
- Discriminatory content
- Threats or harassment
- Explicit content

STUDENT MESSAGE:
\"\"\"
{message_text}
\"\"\"

Remember: Return ONLY the JSON, no explanations."""


FEEDBACK_EXTRACTION_WITH_CONTEXT_PROMPT = """You are an AI assistant that extracts structured data from student feedback about university professors at Webster University in Tashkent (WUT).

CONTEXT:
- This is a Telegram group where students share feedback about professors
- Common departments: Computer Science (COSC), Mathematics (MATH), Business (BUSN), etc.
- Languages used: English, Russian, Uzbek
- Academic year typically runs Fall/Spring semesters

{additional_context}

Analyze the following message and extract structured feedback data.

Return ONLY valid JSON with this structure. Do NOT wrap in code fences or extra text:
{{
    "is_feedback": true/false,
    "professor_name": "string or null",
    "professor_name_normalized": "string or null",
    "course_code": "string or null",
    "course_name": "string or null",
    "semester": "string or null",
    "explicit_rating": number 1-5 or null,
    "inferred_rating": number 1-5 or null,
    "sentiment": "positive" | "negative" | "neutral" | "mixed" | null,
    "aspects": {{
        "teaching_quality": {{"score": 1-5, "comment": "brief note"}},
        "grading_fairness": {{"score": 1-5, "comment": "brief note"}},
        "workload": {{"score": 1-5, "comment": "brief note"}},
        "communication": {{"score": 1-5, "comment": "brief note"}},
        "engagement": {{"score": 1-5, "comment": "brief note"}},
        "exams_difficulty": {{"score": 1-5, "comment": "brief note"}}
    }},
    "strengths": ["point 1", "point 2"],
    "weaknesses": ["point 1", "point 2"],
    "confidence": 0.0-1.0,
    "language": "en" | "ru" | "uz",
    "is_appropriate": true/false
}}

For aspects not mentioned, omit them from "aspects" entirely.

STUDENT MESSAGE:
\"\"\"
{message_text}
\"\"\"

Return ONLY the JSON, no explanations."""


# Simpler prompt for batch processing
FEEDBACK_QUICK_CHECK_PROMPT = """Analyze this message and determine:
1. Is this feedback about a professor? (true/false)
2. If yes, what is the professor's name?
3. Overall sentiment? (positive/negative/neutral/mixed)

Message: \"\"\"{message_text}\"\"\"

Return JSON only, no code fences:
{{"is_feedback": bool, "professor_name": "string or null", "sentiment": "string or null"}}"""


# Compact extraction prompt for better JSON reliability
FEEDBACK_MINI_PROMPT = """Extract minimal structured data from this message.

MESSAGE:
\"\"\"{message_text}\"\"\"

Return ONLY valid JSON (no code fences):
{
    "is_feedback": true/false,
    "professor_name": "string or null",
    "professor_name_normalized": "string or null",
    "sentiment": "positive" | "negative" | "neutral" | "mixed" | null,
    "confidence": 0.0-1.0,
    "is_appropriate": true/false
}
"""


# Batch quick-check prompt for efficient filtering
FEEDBACK_BATCH_QUICK_PROMPT = """You are given a JSON array of messages. For EACH message, decide if it is feedback about a professor.

INPUT MESSAGES (JSON array):
{messages_json}

Return ONLY a JSON array, one object per input message, in the same order:
[
    {{
        "id": 123,
        "is_feedback": true/false,
        "professor_name": "string or null",
        "professor_name_normalized": "string or null",
        "sentiment": "positive" | "negative" | "neutral" | "mixed" | null
    }}
]

IMPORTANT:
1. Output must be a JSON array only. No code fences, no extra text.
2. Keep it short. Do NOT include fields other than those listed above.
"""


# Batch prompt for bulk import efficiency
FEEDBACK_BATCH_PROMPT = """You are an AI assistant that extracts structured data from student feedback about university professors.

You will be given a JSON array of messages. For EACH message, extract structured data.

IMPORTANT:
1. Use the message "id" field to link results to the input message.
2. Extract professor name exactly as mentioned (preserve original spelling).
3. Also provide a normalized professor name in Latin script, fixing common misspellings.
4. If information is not mentioned, set it to null.
5. Return one output object per input message.
6. Output must be a JSON array only. No code fences, no extra text.

INPUT MESSAGES (JSON array):
{messages_json}

Return ONLY valid JSON with this exact structure (array of objects):
[
    {{
        "id": 123,
        "is_feedback": true/false,
        "professor_name": "string or null",
        "professor_name_normalized": "string or null",
        "course_code": "string or null",
        "course_name": "string or null",
        "semester": "string or null",
        "explicit_rating": number 1-5 or null,
        "inferred_rating": number 1-5 or null,
        "sentiment": "positive" | "negative" | "neutral" | "mixed" | null,
        "aspects": {{
                "teaching_quality": {{"score": 1-5, "comment": "brief note"}},
                "grading_fairness": {{"score": 1-5, "comment": "brief note"}},
                "workload": {{"score": 1-5, "comment": "brief note"}},
                "communication": {{"score": 1-5, "comment": "brief note"}},
                "engagement": {{"score": 1-5, "comment": "brief note"}},
                "exams_difficulty": {{"score": 1-5, "comment": "brief note"}}
        }},
        "strengths": ["point 1", "point 2"],
        "weaknesses": ["point 1", "point 2"],
        "confidence": 0.0-1.0,
        "language": "en" | "ru" | "uz",
        "is_appropriate": true/false
    }}
]

Return ONLY the JSON array, no explanations."""
