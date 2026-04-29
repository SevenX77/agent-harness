"""MVP-3 middleware package: 4 core middleware (B3 simplification).

ProtocolValidationMiddleware (T7) is the first to land. CognitiveFlow,
ExecutionControl, and Logging follow in T8 / T9. The legacy modules
under ``cognitive/`` remain wired during the transition; T8 retires
them in a single commit alongside CognitiveFlow.
"""

from __future__ import annotations

from .protocol_validation import ProtocolValidationMiddleware

__all__ = ["ProtocolValidationMiddleware"]
