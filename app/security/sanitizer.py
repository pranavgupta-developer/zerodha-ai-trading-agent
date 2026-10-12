import re
import logging
from typing import Any

logger = logging.getLogger(__name__)

class InputSanitizer:
    """
    Sanitizes untrusted external input (like news feeds, external text) 
    to prevent Prompt Injection attacks on the Agent.
    """
    
    # Common prompt injection patterns
    SUSPICIOUS_PATTERNS = [
        r"ignore previous instructions",
        r"system prompt",
        r"you are now",
        r"forget everything",
        r"bypass rules",
        r"override safety",
        r"override restrictions",
    ]
    
    @classmethod
    def sanitize_text(cls, text: str) -> str:
        """Checks for prompt injection and returns sanitized text."""
        if not isinstance(text, str):
            return str(text)
            
        text_lower = text.lower()
        
        for pattern in cls.SUSPICIOUS_PATTERNS:
            if re.search(pattern, text_lower):
                logger.warning(f"SECURITY ALERT: Potential prompt injection detected: {text}")
                # Neutralize the input
                return "[REDACTED - SUSPICIOUS CONTENT]"
                
        # Basic sanitization (remove weird unicode/control chars)
        clean_text = "".join(ch for ch in text if ch.isprintable())
        return clean_text
        
    @classmethod
    def validate_numeric(cls, value: Any, min_val: float = None, max_val: float = None) -> float:
        """Ensures external numerical data is actually a number and within bounds."""
        try:
            val = float(value)
            if min_val is not None and val < min_val:
                raise ValueError(f"Value {val} below minimum {min_val}")
            if max_val is not None and val > max_val:
                raise ValueError(f"Value {val} above maximum {max_val}")
            return val
        except (ValueError, TypeError) as e:
            logger.error(f"Data sanitization failed for {value}: {e}")
            raise ValueError(f"Invalid numeric input: {value}")

