"""Internal md-patch client abstraction for V2.1 finish_task repair."""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from collections.abc import Callable, Sequence
from typing import Any

from langchain_core.messages import HumanMessage


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

    def __init__(self, chat_model: Any | None = None) -> None:
        self.chat_model = chat_model

    def patch(
        self,
        markdown: str,
        output_schema: dict[str, Any] | None,
        validation_errors: list[dict[str, Any]],
        attempt: int,
    ) -> str:
        if self.chat_model is None:
            raise NotImplementedError("LLMMdPatchClient wired in T1.5 LangGraph build")
        prompt = (
            "You are a Markdown format repair tool. Fix only formatting and mechanical "
            "type issues so the markdown matches the JSON Schema. Return only patched "
            "Markdown.\n\n"
            f"Attempt: {attempt}\n"
            f"Schema:\n{json.dumps(output_schema or {}, ensure_ascii=False)}\n\n"
            f"Validation errors:\n{json.dumps(validation_errors, ensure_ascii=False)}\n\n"
            f"Markdown:\n{markdown}"
        )
        response = self.chat_model.invoke([HumanMessage(content=prompt)])
        return str(getattr(response, "content", "")).strip()


__all__ = ["FakeMdPatchClient", "LLMMdPatchClient", "MdPatchClient"]
