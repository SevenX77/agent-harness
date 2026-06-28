from __future__ import annotations

import re

_SNAKE_CASE = re.compile(r"^[a-z][a-z0-9]*(?:_[a-z0-9]+)*$")


def validate(output: dict, state_slice: dict, **kwargs) -> dict:
    """Validate dynamic dimension identifiers."""
    dynamic_dimensions = output.get("dynamic_dimensions") or []
    if not isinstance(dynamic_dimensions, list):
        raise ValueError("dynamic_dimensions must be an array")
    if not 1 <= len(dynamic_dimensions) <= 10:
        raise ValueError("dynamic_dimensions count must be between 1 and 10")

    normalized = []
    for item in dynamic_dimensions:
        if not isinstance(item, str) or not item:
            raise ValueError("dynamic_dimensions items must be non-empty strings")
        if not _SNAKE_CASE.match(item):
            raise ValueError(f"dynamic dimension must be snake_case: {item}")
        normalized.append(item)

    return {"dynamic_dimensions": normalized}
