"""Internal md-patch client abstraction for V2.1 finish_task repair."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable, Sequence
from typing import Any


class MdPatchClient(ABC):
    """Internal patcher protocol; not exposed as a phase ReAct tool."""

    @abstractmethod
    def patch(
        self,
        markdown: str,
        output_schema: dict[str, Any] | None,
        validation_errors: list[dict[str, Any]],
        attempt: int,
    ) -> str:
        """Return patched Markdown."""


class FakeMdPatchClient(MdPatchClient):
    """Deterministic patcher for tests."""

    def __init__(
        self,
        patches: Sequence[str] | Callable[[str, dict[str, Any] | None, list[dict[str, Any]], int], str],
    ) -> None:
        self._patches = patches
        self.calls: list[dict[str, Any]] = []

    def patch(
        self,
        markdown: str,
        output_schema: dict[str, Any] | None,
        validation_errors: list[dict[str, Any]],
        attempt: int,
    ) -> str:
        self.calls.append(
            {
                "markdown": markdown,
                "output_schema": output_schema,
                "validation_errors": validation_errors,
                "attempt": attempt,
            }
        )
        if callable(self._patches):
            return self._patches(markdown, output_schema, validation_errors, attempt)
        index = min(attempt - 1, len(self._patches) - 1)
        return self._patches[index]


class LLMMdPatchClient(MdPatchClient):
    """Placeholder for the T1.5 LangGraph-backed md-patch bridge."""

    def patch(
        self,
        markdown: str,
        output_schema: dict[str, Any] | None,
        validation_errors: list[dict[str, Any]],
        attempt: int,
    ) -> str:
        raise NotImplementedError("LLMMdPatchClient wired in T1.5 LangGraph build")


__all__ = ["FakeMdPatchClient", "LLMMdPatchClient", "MdPatchClient"]
