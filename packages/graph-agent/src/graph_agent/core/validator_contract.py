"""γ0 validator contract placeholders.

Runtime validator loading is implemented in later PRs. This module only pins
the signature and error-code contract so compile/runtime work cannot drift.
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
