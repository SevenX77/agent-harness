from __future__ import annotations

import json
import logging
import re

logger = logging.getLogger(__name__)


def safe_parse_json_list(raw: str, label: str) -> list:
    """Extract JSON list from LLM output.
    
    Supports markdown code block extraction and handles truncation.
    """
    if not raw:
        logger.warning(f"{label}: Empty raw output")
        return []
    
    # Extract from markdown code block if present
    pattern = r"```(?:json)?\s*([\s\S]*?)```"
    match = re.search(pattern, raw)
    if match:
        raw = match.group(1).strip()
    
    # Detect truncation
    if _is_truncated_json(raw):
        logger.warning(f"{label}: JSON appears truncated")
    
    try:
        data = json.loads(raw)
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            return [data]
        logger.warning(f"{label}: Expected list, got {type(data).__name__}")
        return []
    except json.JSONDecodeError as e:
        logger.warning(f"{label}: JSON decode error: {e}")
        return []


def _is_truncated_json(raw: str) -> bool:
    """Detect if JSON is truncated."""
    raw = raw.strip()
    if not raw:
        return False
    
    # Check for unbalanced brackets
    open_braces = raw.count("{")
    close_braces = raw.count("}")
    open_brackets = raw.count("[")
    close_brackets = raw.count("]")
    
    if open_braces != close_braces or open_brackets != close_brackets:
        return True
    
    # Check for trailing comma or incomplete string
    if raw.rstrip().endswith(",") or raw.rstrip().endswith('"'):
        return True
    
    return False


def clamp(value: float, low: float, high: float) -> float:
    """Clamp value to range [low, high]."""
    if value < low:
        return low
    if value > high:
        return high
    return value


def safe_get_str(d: dict, key: str, default: str = "") -> str:
    """Safely get string value from dict."""
    if key not in d:
        return default
    val = d[key]
    if isinstance(val, str):
        return val
    return str(val) if val is not None else default


def safe_get_list(d: dict, key: str) -> list:
    """Safely get list value from dict."""
    if key not in d:
        return []
    val = d[key]
    if isinstance(val, list):
        return val
    if isinstance(val, tuple):
        return list(val)
    return [val] if val is not None else []
