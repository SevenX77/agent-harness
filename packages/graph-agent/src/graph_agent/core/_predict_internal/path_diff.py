"""Path diff helpers for Predict V2 backtest route validation."""

from __future__ import annotations

from collections import Counter
from difflib import SequenceMatcher

from graph_agent.core._predict_internal.models import PathDiff


def compute_diff(expected_path: list[str], actual_path: list[str]) -> PathDiff:
    """Compare expected and actual phase paths with an LCS-style diff."""
    matcher = SequenceMatcher(a=expected_path, b=actual_path, autojunk=False)
    missing: list[str] = []
    extra: list[str] = []

    for tag, expected_start, expected_end, actual_start, actual_end in matcher.get_opcodes():
        if tag == "equal":
            continue
        if tag in {"delete", "replace"}:
            missing.extend(expected_path[expected_start:expected_end])
        if tag in {"insert", "replace"}:
            extra.extend(actual_path[actual_start:actual_end])

    order_mismatch = not missing and not extra and expected_path != actual_path
    if missing or extra:
        expected_counts = Counter(expected_path)
        actual_counts = Counter(actual_path)
        if expected_counts == actual_counts and expected_path != actual_path:
            missing = []
            extra = []
            order_mismatch = True

    return PathDiff(
        expected_path=expected_path,
        actual_path=actual_path,
        missing=missing,
        extra=extra,
        order_mismatch=order_mismatch,
    )


__all__ = ["compute_diff"]
