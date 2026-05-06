"""Structural serialization helper for CallbackEvent payloads (T-A3).

Converts arbitrary Python objects into a JSON-safe ``dict`` / ``list`` /
primitive tree before they land in ``tracing.jsonl``. This lets events
that carry raw workflow context (``RunStartedEvent``, ``PhaseEndEvent``,
etc.) round-trip cleanly regardless of what the running skill happens
to have stuffed into the context.

Type-dispatch table comes from Gemini's Q4 review:

    BaseMessage      →  {"_type": "BaseMessage", "role": ..., "content": ...}
    BaseModel        →  obj.model_dump()
    Path             →  str(path)
    datetime         →  obj.isoformat()
    UUID             →  str(uuid)
    Decimal          →  str(decimal)      # preserve precision
    set / frozenset  →  sorted list
    dict / list /    →  recurse into contents
    tuple
    str/int/float/bool/None → passthrough
    anything else    →  {"_repr": repr(obj), "_warning": "unsupported_type"}
"""

from __future__ import annotations

import logging
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import UUID

from pydantic import BaseModel

logger = logging.getLogger(__name__)

_BaseMessage: type[Any] | None
try:
    # Lazy import so callbacks/serialize.py does not force a langchain load
    # on installs that never touch LangChain message objects (e.g. tests).
    from langchain_core.messages import BaseMessage as _ImportedBaseMessage
except ImportError:  # pragma: no cover — exercised only without langchain
    _BaseMessage = None
else:
    _BaseMessage = _ImportedBaseMessage


_UNSUPPORTED_FALLBACK = "unsupported_type"
_MAX_DEPTH = 20


def to_jsonable_dict(data: Any, *, _depth: int = 0) -> Any:
    """Return a JSON-serialisable version of ``data``.

    The function is total — it never raises. Anything the dispatch table
    cannot understand falls back to ``{"_repr": repr(obj), "_warning":
    "unsupported_type"}`` so the event still round-trips.
    """
    if _depth > _MAX_DEPTH:
        return {"_repr": repr(data)[:200], "_warning": "max_depth_exceeded"}

    # primitives
    if data is None or isinstance(data, (str, bool, int, float)):
        return data

    # common stdlib structural types
    if isinstance(data, Path):
        return str(data)
    if isinstance(data, datetime):
        return data.isoformat()
    if isinstance(data, UUID):
        return str(data)
    if isinstance(data, Decimal):
        return str(data)

    # collection types — recurse
    if isinstance(data, dict):
        out: dict[str, Any] = {}
        for key, value in data.items():
            # JSON keys must be strings.
            out[str(key)] = to_jsonable_dict(value, _depth=_depth + 1)
        return out
    if isinstance(data, (list, tuple)):
        return [to_jsonable_dict(item, _depth=_depth + 1) for item in data]
    if isinstance(data, (set, frozenset)):
        try:
            ordered = sorted(data, key=lambda x: str(x))
        except Exception as exc:  # noqa: BLE001
            logger.debug(
                "to_jsonable_dict: set/frozenset sort failed (%s); using unsorted list",
                exc,
            )
            ordered = list(data)
        return [to_jsonable_dict(item, _depth=_depth + 1) for item in ordered]

    # LangChain message objects — preserve role / content structure
    if _BaseMessage is not None and isinstance(data, _BaseMessage):
        return {
            "_type": "BaseMessage",
            "role": getattr(data, "type", None) or getattr(data, "role", None),
            "content": to_jsonable_dict(getattr(data, "content", None), _depth=_depth + 1),
        }

    # Pydantic models — lean on their own JSON-safe serialisation
    if isinstance(data, BaseModel):
        try:
            return data.model_dump(mode="json")
        except Exception as exc:  # noqa: BLE001
            logger.debug(
                "to_jsonable_dict: BaseModel %s model_dump failed (%s); using repr fallback",
                type(data).__name__,
                exc,
            )
            return {"_repr": repr(data), "_warning": _UNSUPPORTED_FALLBACK}

    # callables — document rather than serialise
    if callable(data):
        return {
            "_type": "callable",
            "name": getattr(data, "__name__", None) or repr(data),
        }

    # fallback
    return {"_repr": repr(data), "_warning": _UNSUPPORTED_FALLBACK}


__all__ = ["to_jsonable_dict"]
