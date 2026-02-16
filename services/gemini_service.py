"""
Gemini AI service for WUT Feedback Bot.

Handles all interactions with Google Gemini API including:
- Feedback extraction from unstructured text
- Query response generation
- Content moderation
"""

import json
import re
from typing import Dict, Any, Optional, List

import google.generativeai as genai
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from config import Config
from prompts.extraction_prompts import (
    FEEDBACK_EXTRACTION_PROMPT,
    FEEDBACK_QUICK_CHECK_PROMPT,
    FEEDBACK_BATCH_PROMPT,
    FEEDBACK_BATCH_QUICK_PROMPT,
    FEEDBACK_MINI_PROMPT,
)
from prompts.query_prompts import (
    QUERY_RESPONSE_PROMPT,
    PROFESSOR_COMPARISON_PROMPT,
    COURSE_RECOMMENDATION_PROMPT,
    NATURAL_QUERY_INTENT_PROMPT,
)
from prompts.moderation_prompts import MODERATION_PROMPT, CONTENT_FILTER_PROMPT
from utils.logger import get_logger

logger = get_logger(__name__)


class GeminiServiceError(Exception):
    """Custom exception for Gemini service errors."""
    pass


class GeminiService:
    """
    Service for all Gemini AI interactions.
    
    Provides methods for:
    - Extracting structured feedback from text
    - Generating query responses
    - Content moderation
    """
    
    def __init__(self, api_key: str = None):
        """
        Initialize Gemini service.
        
        Args:
            api_key: Gemini API key. Uses Config if not provided.
        """
        self.api_key = api_key or Config.GEMINI_API_KEY
        if not self.api_key:
            raise GeminiServiceError("Gemini API key is required")
        
        genai.configure(api_key=self.api_key)
        
        # Generation config for structured output
        try:
            self.json_config = genai.types.GenerationConfig(
                temperature=0.2,  # Low temperature for consistent extraction
                top_p=0.8,
                max_output_tokens=2048,
                response_mime_type="application/json",
            )
        except TypeError:
            # Older google-generativeai versions do not support response_mime_type
            self.json_config = genai.types.GenerationConfig(
                temperature=0.2,
                top_p=0.8,
                max_output_tokens=2048,
            )
        
        # Generation config for natural responses
        self.response_config = genai.types.GenerationConfig(
            temperature=0.7,  # Higher for more natural responses
            top_p=0.9,
            max_output_tokens=1024,
        )
        
        model_name = self._resolve_model_name()
        self.model = genai.GenerativeModel(model_name)
        
        logger.info(f"Gemini model selected: {model_name}")
        logger.info("Gemini service initialized")

    @staticmethod
    def _model_name_matches(preferred: str, candidate: str) -> bool:
        """Check if model names match with or without the 'models/' prefix."""
        if preferred == candidate:
            return True
        if preferred.startswith("models/") and preferred == candidate:
            return True
        if candidate.startswith("models/") and candidate.endswith("/" + preferred):
            return True
        return False

    def _resolve_model_name(self) -> str:
        """Select a Gemini model that supports generateContent."""
        preferred = []
        if Config.GEMINI_MODEL:
            preferred.append(Config.GEMINI_MODEL)
        
        preferred.extend([
            "gemini-1.5-flash",
            "gemini-1.5-flash-latest",
            "gemini-1.5-pro",
            "gemini-1.5-pro-latest",
            "gemini-1.0-pro",
            "gemini-pro",
        ])
        
        try:
            models = list(genai.list_models())
            supported = [
                model for model in models
                if "generateContent" in getattr(model, "supported_generation_methods", [])
            ]
            
            for pref in preferred:
                for model in supported:
                    if self._model_name_matches(pref, model.name):
                        return model.name
            
            if supported:
                return supported[0].name
        except Exception as e:
            logger.warning(f"Failed to list Gemini models: {e}")
        
        return Config.GEMINI_MODEL or "gemini-1.5-flash"
    
    # ==================== Feedback Extraction ====================
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((Exception,)),
    )
    async def extract_feedback(self, message_text: str) -> Dict[str, Any]:
        """
        Extract structured feedback data from a message.
        
        Args:
            message_text: Raw message text
        
        Returns:
            Dictionary with extracted data:
            - is_feedback: bool
            - professor_name: str or None
            - course_code: str or None
            - sentiment: str or None
            - aspects: dict
            - strengths: list
            - weaknesses: list
            - confidence: float
            - is_appropriate: bool
        """
        if not message_text or len(message_text.strip()) < 10:
            return self._empty_extraction_result()
        
        prompt = FEEDBACK_EXTRACTION_PROMPT.format(message_text=message_text)
        
        try:
            response = await self._generate_async(prompt, self.json_config)
            try:
                result = self._parse_json_response(response)
            except GeminiServiceError as e:
                # Parsing errors should not trigger retries
                logger.warning(f"Failed to parse extraction JSON: {e}")
                # Retry with compact prompt to reduce truncation
                mini_prompt = FEEDBACK_MINI_PROMPT.format(message_text=message_text)
                try:
                    mini_response = await self._generate_async(mini_prompt, self.json_config)
                    mini_result = self._parse_json_response(mini_response)
                    return self._normalize_extraction_result(mini_result)
                except Exception as mini_error:
                    logger.warning(f"Mini extraction failed: {mini_error}")
                    return self._empty_extraction_result()
            
            # Validate and normalize
            result = self._normalize_extraction_result(result)
            
            logger.debug(f"Extracted feedback: is_feedback={result['is_feedback']}, "
                        f"professor={result.get('professor_name')}, "
                        f"confidence={result.get('confidence', 0):.2f}")
            
            return result
            
        except Exception as e:
            # Fail closed: treat as non-feedback and continue processing
            logger.warning(f"Feedback extraction failed: {e}")
            return self._empty_extraction_result()
    
    async def quick_check_feedback(self, message_text: str) -> Dict[str, Any]:
        """
        Quick check if a message is feedback (for initial filtering).
        
        Args:
            message_text: Raw message text
        
        Returns:
            Dictionary with is_feedback, professor_name, sentiment
        """
        if not message_text or len(message_text.strip()) < 10:
            return {"is_feedback": False, "professor_name": None, "sentiment": None}

    async def quick_check_feedback_batch(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Quick check for a batch of messages.

        Args:
            messages: List of dicts with {id, text}

        Returns:
            List of dicts with {id, is_feedback, professor_name, professor_name_normalized, sentiment}
        """
        if not messages:
            return []

        prompt = FEEDBACK_BATCH_QUICK_PROMPT.format(
            messages_json=json.dumps(messages, ensure_ascii=False)
        )

        try:
            response = await self._generate_async(prompt, self.json_config)
            result = self._parse_json_array_response(response)

            if isinstance(result, dict):
                for key in ("results", "items", "data"):
                    if key in result:
                        result = result.get(key)
                        break

            if isinstance(result, dict) and "id" in result:
                result = [result]

            if not isinstance(result, list):
                raise GeminiServiceError("Batch quick-check response is not a list")

            cleaned = []
            for item in result:
                if not isinstance(item, dict):
                    continue
                cleaned.append({
                    "id": item.get("id"),
                    "is_feedback": bool(item.get("is_feedback", False)),
                    "professor_name": item.get("professor_name"),
                    "professor_name_normalized": item.get("professor_name_normalized"),
                    "sentiment": item.get("sentiment"),
                })

            return cleaned

        except Exception as e:
            logger.warning(f"Batch quick-check failed: {e}")
            return []

        prompt = FEEDBACK_QUICK_CHECK_PROMPT.format(message_text=message_text)

        try:
            response = await self._generate_async(prompt, self.json_config)
            return self._parse_json_response(response)
        except Exception as e:
            logger.warning(f"Quick check failed: {e}")
            return {"is_feedback": False, "professor_name": None, "sentiment": None}

    async def extract_feedback_batch(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Extract structured feedback data from a batch of messages.

        Args:
            messages: List of dicts with {id, text}

        Returns:
            List of extraction results with matching id fields
        """
        if not messages:
            return []

        prompt = FEEDBACK_BATCH_PROMPT.format(
            messages_json=json.dumps(messages, ensure_ascii=False)
        )

        try:
            response = await self._generate_async(prompt, self.json_config)
            result = self._parse_json_array_response(response)

            if isinstance(result, dict):
                for key in ("results", "items", "data"):
                    if key in result:
                        result = result.get(key)
                        break

            if isinstance(result, dict) and "id" in result:
                result = [result]

            if not isinstance(result, list):
                raise GeminiServiceError("Batch extraction response is not a list")

            normalized_results = []
            for item in result:
                if not isinstance(item, dict):
                    continue
                normalized = self._normalize_extraction_result(item)
                if "id" in item:
                    normalized["id"] = item.get("id")
                normalized_results.append(normalized)

            return normalized_results

        except Exception as e:
            logger.warning(f"Batch extraction failed: {e}")
            return []
    
    def _empty_extraction_result(self) -> Dict[str, Any]:
        """Return empty extraction result."""
        return {
            "is_feedback": False,
            "professor_name": None,
            "professor_name_normalized": None,
            "course_code": None,
            "course_name": None,
            "semester": None,
            "explicit_rating": None,
            "inferred_rating": None,
            "sentiment": None,
            "aspects": {},
            "strengths": [],
            "weaknesses": [],
            "confidence": 0.0,
            "language": None,
            "is_appropriate": True,
        }
    
    def _normalize_extraction_result(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize and validate extraction result."""
        base = self._empty_extraction_result()
        
        # Merge with defaults
        for key in base:
            if key in result and result[key] is not None:
                base[key] = result[key]
        
        # Validate rating ranges
        for rating_key in ['explicit_rating', 'inferred_rating']:
            if base[rating_key] is not None:
                try:
                    rating = float(base[rating_key])
                    base[rating_key] = max(1.0, min(5.0, rating))
                except (ValueError, TypeError):
                    base[rating_key] = None
        
        # Validate confidence
        try:
            base['confidence'] = max(0.0, min(1.0, float(base.get('confidence', 0))))
        except (ValueError, TypeError):
            base['confidence'] = 0.0
        
        # Ensure lists are lists
        for list_key in ['strengths', 'weaknesses']:
            if not isinstance(base[list_key], list):
                base[list_key] = []
        
        # Ensure aspects is dict
        if not isinstance(base['aspects'], dict):
            base['aspects'] = {}
        
        return base
    
    # ==================== Query Response Generation ====================
    
    async def generate_query_response(
        self,
        user_query: str,
        professor_data: Dict[str, Any],
        feedbacks: List[Dict[str, Any]],
    ) -> str:
        """
        Generate response to student query about a professor.
        
        Args:
            user_query: Student's question
            professor_data: Professor information dict
            feedbacks: List of recent feedbacks
        
        Returns:
            Generated response text
        """
        # Format feedbacks for context
        feedbacks_text = self._format_feedbacks_for_context(feedbacks)
        
        prompt = QUERY_RESPONSE_PROMPT.format(
            professor_name=professor_data.get('name', 'Unknown'),
            department=professor_data.get('department', 'Unknown'),
            courses=', '.join(professor_data.get('courses', []) or ['Not specified']),
            overall_rating=professor_data.get('overall_rating', 0) or 0,
            total_feedbacks=professor_data.get('total_feedbacks', 0) or 0,
            positive_count=professor_data.get('positive_feedbacks', 0) or 0,
            negative_count=professor_data.get('negative_feedbacks', 0) or 0,
            neutral_count=professor_data.get('neutral_feedbacks', 0) or 0,
            avg_teaching_quality=self._format_rating(professor_data.get('avg_teaching_quality')),
            avg_grading_fairness=self._format_rating(professor_data.get('avg_grading_fairness')),
            avg_workload=self._format_rating(professor_data.get('avg_workload')),
            avg_communication=self._format_rating(professor_data.get('avg_communication')),
            avg_engagement=self._format_rating(professor_data.get('avg_engagement')),
            feedbacks_text=feedbacks_text,
            user_query=user_query,
        )
        
        try:
            response = await self._generate_async(prompt, self.response_config)
            return response.strip()
        except Exception as e:
            logger.error(f"Query response generation failed: {e}")
            return "I encountered an error generating the response. Please try again."
    
    async def generate_comparison_response(
        self,
        user_query: str,
        prof1_data: Dict[str, Any],
        prof2_data: Dict[str, Any],
    ) -> str:
        """
        Generate comparison response for two professors.
        
        Args:
            user_query: Student's question
            prof1_data: First professor data
            prof2_data: Second professor data
        
        Returns:
            Generated comparison text
        """
        prompt = PROFESSOR_COMPARISON_PROMPT.format(
            prof1_name=prof1_data.get('name', 'Unknown'),
            prof1_rating=prof1_data.get('overall_rating', 0) or 0,
            prof1_feedback_count=prof1_data.get('total_feedbacks', 0) or 0,
            prof1_department=prof1_data.get('department', 'Unknown'),
            prof1_teaching=self._format_rating(prof1_data.get('avg_teaching_quality')),
            prof1_grading=self._format_rating(prof1_data.get('avg_grading_fairness')),
            prof1_workload=self._format_rating(prof1_data.get('avg_workload')),
            prof1_strengths=', '.join(prof1_data.get('top_strengths', ['N/A'])),
            prof1_weaknesses=', '.join(prof1_data.get('top_weaknesses', ['N/A'])),
            prof2_name=prof2_data.get('name', 'Unknown'),
            prof2_rating=prof2_data.get('overall_rating', 0) or 0,
            prof2_feedback_count=prof2_data.get('total_feedbacks', 0) or 0,
            prof2_department=prof2_data.get('department', 'Unknown'),
            prof2_teaching=self._format_rating(prof2_data.get('avg_teaching_quality')),
            prof2_grading=self._format_rating(prof2_data.get('avg_grading_fairness')),
            prof2_workload=self._format_rating(prof2_data.get('avg_workload')),
            prof2_strengths=', '.join(prof2_data.get('top_strengths', ['N/A'])),
            prof2_weaknesses=', '.join(prof2_data.get('top_weaknesses', ['N/A'])),
            user_query=user_query,
        )
        
        try:
            response = await self._generate_async(prompt, self.response_config)
            return response.strip()
        except Exception as e:
            logger.error(f"Comparison response generation failed: {e}")
            return "I encountered an error generating the comparison. Please try again."
    
    async def analyze_query_intent(self, user_query: str) -> Dict[str, Any]:
        """
        Analyze natural language query to determine intent.
        
        Args:
            user_query: Raw user query
        
        Returns:
            Dictionary with intent, professor_names, course_code, etc.
        """
        prompt = NATURAL_QUERY_INTENT_PROMPT.format(user_query=user_query)
        
        try:
            response = await self._generate_async(prompt, self.json_config)
            return self._parse_json_response(response)
        except Exception as e:
            logger.warning(f"Intent analysis failed: {e}")
            return {
                "intent": "unknown",
                "professor_names": [],
                "course_code": None,
                "specific_aspect": None,
            }
    
    # ==================== Content Moderation ====================
    
    async def moderate_content(self, message_text: str) -> Dict[str, Any]:
        """
        Check if content is appropriate.
        
        Args:
            message_text: Text to moderate
        
        Returns:
            Dictionary with:
            - is_appropriate: bool
            - violations: list
            - severity: str
            - reason: str or None
        """
        prompt = MODERATION_PROMPT.format(message_text=message_text)
        
        try:
            response = await self._generate_async(prompt, self.json_config)
            result = self._parse_json_response(response)
            
            return {
                "is_appropriate": result.get("is_appropriate", True),
                "violations": result.get("violations", []),
                "severity": result.get("severity", "none"),
                "reason": result.get("reason"),
            }
        except Exception as e:
            logger.warning(f"Moderation check failed: {e}")
            # Default to appropriate on error to avoid blocking
            return {
                "is_appropriate": True,
                "violations": [],
                "severity": "none",
                "reason": None,
            }
    
    async def quick_filter(self, message_text: str) -> bool:
        """
        Quick content filter check.
        
        Args:
            message_text: Text to check
        
        Returns:
            True if content passes filter
        """
        prompt = CONTENT_FILTER_PROMPT.format(message_text=message_text)
        
        try:
            response = await self._generate_async(prompt, self.json_config)
            result = self._parse_json_response(response)
            return result.get("pass", True)
        except Exception:
            return True  # Default to pass on error
    
    # ==================== Helper Methods ====================
    
    async def _generate_async(
        self, 
        prompt: str, 
        config: genai.types.GenerationConfig
    ) -> str:
        """
        Generate content asynchronously.
        
        Args:
            prompt: Prompt text
            config: Generation config
        
        Returns:
            Generated text
        """
        response = await self.model.generate_content_async(
            prompt,
            generation_config=config,
        )
        
        if not response.text:
            raise GeminiServiceError("Empty response from Gemini")
        
        return response.text
    
    def _parse_json_response(self, response: str) -> Dict[str, Any]:
        """
        Parse JSON from Gemini response.
        
        Handles common issues like markdown code blocks.
        
        Args:
            response: Raw response text
        
        Returns:
            Parsed dictionary
        """
        text = response.strip()
        
        # Remove markdown code blocks
        if text.startswith('```'):
            # Find the content between code blocks
            match = re.search(r'```(?:json)?\s*(.*?)```', text, re.DOTALL)
            if match:
                text = match.group(1).strip()
            else:
                # Handle truncated code fences by stripping the opening fence
                text = re.sub(r'^```(?:json)?\s*', '', text).strip()
        
        # If response is a JSON array, try parsing directly
        if text.lstrip().startswith('['):
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                pass

        # Try to find JSON object
        json_match = re.search(r'\{.*\}', text, re.DOTALL)
        if json_match:
            text = json_match.group(0)
        else:
            # Handle responses missing outer braces
            if text.startswith('"') and '"is_feedback"' in text:
                text = "{" + text
            if not text.endswith('}') and '"is_appropriate"' in text:
                text = text + "}"
        
        try:
            return json.loads(text)
        except json.JSONDecodeError as e:
            # Try to parse the first JSON object from the text
            try:
                decoder = json.JSONDecoder()
                obj, _ = decoder.raw_decode(text)
                if isinstance(obj, dict):
                    return obj
            except json.JSONDecodeError:
                pass

            repaired = self._attempt_repair_json(text)
            if repaired:
                try:
                    return json.loads(repaired)
                except json.JSONDecodeError:
                    pass
            logger.warning(f"JSON parse error: {e}, text: {text[:200]}")
            raise GeminiServiceError(f"Failed to parse JSON: {e}")

    def _parse_json_array_response(self, response: str) -> Any:
        """Parse JSON arrays that may include extra data or concatenated objects."""
        text = response.strip()

        # Remove markdown code blocks
        if text.startswith('```'):
            match = re.search(r'```(?:json)?\s*(.*?)```', text, re.DOTALL)
            if match:
                text = match.group(1).strip()
            else:
                text = re.sub(r'^```(?:json)?\s*', '', text).strip()

        # Fast path: valid JSON array or object
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        decoder = json.JSONDecoder()
        idx = 0
        results = []
        while idx < len(text):
            # Skip whitespace
            while idx < len(text) and text[idx].isspace():
                idx += 1
            if idx >= len(text):
                break

            try:
                obj, end = decoder.raw_decode(text, idx)
            except json.JSONDecodeError:
                break

            if isinstance(obj, list):
                results.extend(obj)
            else:
                results.append(obj)

            idx = end

        if results:
            return results

        # Fall back to object parser with repair attempts
        return self._parse_json_response(response)

    @staticmethod
    def _attempt_repair_json(text: str) -> Optional[str]:
        """Try to repair common truncation issues in JSON strings."""
        start = text.find("{")
        if start == -1:
            return None

        candidate = text[start:]
        # Drop any trailing code fence if present
        if "```" in candidate:
            candidate = candidate.split("```", 1)[0]

        if "}" in candidate:
            candidate = candidate[:candidate.rfind("}") + 1]

        open_count = candidate.count("{")
        close_count = candidate.count("}")
        if open_count > close_count:
            candidate = candidate + ("}" * (open_count - close_count))

        return candidate.strip() if candidate else None
    
    def _format_feedbacks_for_context(
        self, 
        feedbacks: List[Dict[str, Any]], 
        max_feedbacks: int = 5
    ) -> str:
        """Format feedbacks for prompt context."""
        if not feedbacks:
            return "No feedbacks available."
        
        lines = []
        for i, fb in enumerate(feedbacks[:max_feedbacks], 1):
            sentiment = fb.get('sentiment', 'unknown')
            rating = fb.get('final_rating')
            rating_str = f" ({rating}/5)" if rating else ""
            
            # Truncate message
            msg = fb.get('original_message', '')[:200]
            if len(fb.get('original_message', '')) > 200:
                msg += "..."
            
            lines.append(f"{i}. [{sentiment.upper()}{rating_str}] {msg}")
        
        return "\n".join(lines)
    
    @staticmethod
    def _format_rating(value: Optional[float]) -> str:
        """Format rating value for display."""
        if value is None:
            return "N/A"
        return f"{value:.1f}"


# Singleton instance
_gemini_service: Optional[GeminiService] = None


def get_gemini_service(api_key: str = None) -> GeminiService:
    """Get or create Gemini service singleton."""
    global _gemini_service
    if _gemini_service is None:
        _gemini_service = GeminiService(api_key)
    return _gemini_service
