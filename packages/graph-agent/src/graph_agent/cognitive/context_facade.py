"""Blackboard context facade for V2.1 Logic Actions."""

from __future__ import annotations

from types import MappingProxyType
from typing import Any, Mapping


class Context:
    """Action-facing facade over the workflow blackboard."""

    def __init__(self, blackboard: dict[str, Any], *, phase_id: str, run_id: str) -> None:
        self._blackboard = blackboard
        self._phase_id = phase_id
        self._run_id = run_id

    def get(self, key: str, default: Any = None) -> Any:
        return self._blackboard.get(key, default)

    def set(self, key: str, value: Any) -> None:
        self._blackboard[key] = value

    def update(self, **fields: Any) -> None:
        self._blackboard.update(fields)

    def has(self, key: str) -> bool:
        return key in self._blackboard

    def delete(self, key: str) -> None:
        self._blackboard.pop(key, None)

    def keys(self) -> list[str]:
        return list(self._blackboard.keys())

    @property
    def inputs(self) -> Mapping[str, Any]:
        value = self._blackboard.get("inputs", {})
        if not isinstance(value, dict):
            value = {}
        return MappingProxyType(value)

    @property
    def phase_id(self) -> str:
        return self._phase_id

    @property
    def run_id(self) -> str:
        return self._run_id


__all__ = ["Context"]
