"""Shared v0.3.0 phase validator runtime contract.

The compiler/runtime use this module as the single place for the sibling
``validator.py`` signature and fatal error-code contract.
"""

from __future__ import annotations

VALIDATOR_SIGNATURE = "def validate(output: dict, state_slice: dict, **kwargs) -> None | dict"

VALIDATOR_ERROR_CODES: tuple[str, ...] = (
    "[F-v3-agent-validator-failed]",
    "[F-v3-subgraph-validator-failed]",
    "[F-v3-logic-validator-failed]",
)

__all__ = [
    "VALIDATOR_ERROR_CODES",
    "VALIDATOR_SIGNATURE",
]
