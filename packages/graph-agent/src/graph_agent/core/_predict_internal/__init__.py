"""Private Predict V2 integration hooks.

This module is intentionally not re-exported from ``graph_agent``.  It exists
only for SDK/Studio-internal wiring while preserving the locked top-level ABI.
"""

from __future__ import annotations

from typing import TypeVar

from graph_agent.core._predict_internal.strategy import BaseMockStrategy

_T = TypeVar("_T")

_PREDICT_STRATEGY_ATTR = "_graph_agent_predict_mock_strategy"


def bind_predictor(target: _T, mock_strategy: BaseMockStrategy) -> _T:
    """Attach a Predict mock strategy to an internal SDK runtime object.

    P-T1 only establishes the private binding surface.  Later Predict tasks
    will decide which concrete runtime objects call this hook and how strategy
    lookup works across a full graph run.
    """

    setattr(target, _PREDICT_STRATEGY_ATTR, mock_strategy)
    return target


__all__ = ["bind_predictor"]
