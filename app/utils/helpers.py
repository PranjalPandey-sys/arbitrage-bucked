"""Helper utilities for the arbitrage detection system."""

import re
import asyncio
from typing import List, Optional, Union, Any
from datetime import datetime, timedelta
from urllib.parse import urlparse, urljoin


def clean_text(text: str) -> str:
    """Clean and normalize text content."""
    if not text:
        return ""
    
    # Remove extra whitespace and normalize
    cleaned = re.sub(r'\s+', ' ', text.strip())
    
    # Remove special characters that might interfere with matching
    cleaned = re.sub(r'[^\w\s\-.]', ' ', cleaned)
    
    return cleaned


def extract_numeric_value(text: str) -> Optional[float]:
    """Extract first numeric value from text."""
    if not text:
        return None
    
    # Find decimal numbers
    pattern = r'[-+]?\d*\.?\d+'
    match = re.search(pattern, str(text))
    
    if match:
        try:
            return float(match.group())
        except ValueError:
            return None
    
    return None


def is_valid_odds(odds: Union[str, float, int]) -> bool:
    """Check if odds value is valid."""
    try:
        odds_value = float(odds)
        return 1.01 <= odds_value <= 1000.0
    except (ValueError,