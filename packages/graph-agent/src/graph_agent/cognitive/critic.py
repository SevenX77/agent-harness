"""V2.1 critic/reviewer/auditor ReAct tool support."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
import json
from typing import Any

from langchain_core.messages import HumanMessage
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field


@dataclass(frozen=True)
class CriticVerdict:
    """Structured verdict returned by a critic client."""

    passed: bool
    reasons: list[str] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


class CriticClient(ABC):
    """Critic sub-agent abstraction. Real LLM wiring lands in T1.5."""

    @abstractmethod
    def review(
        self,
        target_text: str,
        criteria: str,
        attempt: int = 1,
    ) -> CriticVerdict:
        """Return critic verdict for target_text against criteria."""


class FakeCriticClient(CriticClient):
    """Test fake with a fixed verdict."""

    def __init__(self, verdict: CriticVerdict) -> None:
        self._verdict = verdict
        self.calls: list[dict[str, Any]] = []

    def review(
        self,
        target_text: str,
        criteria: str,
        attempt: int = 1,
    ) -> CriticVerdict:
        self.calls.append(
            {
                "target_text": target_text,
                "criteria": criteria,
                "attempt": attempt,
            }
        )
        return self._verdict


class LLMCriticClient(CriticClient):
    """Placeholder for the T1.5 LangGraph-backed critic bridge."""

    def __init__(self, chat_model: Any | None = None) -> None:
        self.chat_model = chat_model

    def review(
        self,
        target_text: str,
        criteria: str,
        attempt: int = 1,
    ) -> CriticVerdict:
        if self.chat_model is None:
            raise NotImplementedError("LLMCriticClient wired in T1.5 LangGraph build")
        prompt = (
            "You are a critic. Review the text against the criteria. "
            "Respond only as JSON with keys: passed (boolean), reasons (list), "
            "suggestions (list).\n\n"
            f"Text:\n{target_text}\n\nCriteria:\n{criteria}"
        )
        response = self.chat_model.invoke([HumanMessage(content=prompt)])
        parsed = _parse_json_object(str(getattr(response, "content", "")))
        return CriticVerdict(
            passed=bool(parsed.get("passed", False)),
            reasons=_string_list(parsed.get("reasons")),
            suggestions=_string_list(parsed.get("suggestions")),
            metadata={"attempt": attempt},
        )


class CriticToolInput(BaseModel):
    """Input schema for critic tools exposed inside a SKILL phase."""

    target_text: str = Field(description="The text to review.")
    criteria: str = Field(description="Review criteria (what to check for).")


@dataclass
class CriticMetrics:
    """Per-tool-instance invocation counters."""

    invocations: int = 0
    passed: int = 0
    rejected: int = 0

    def record(self, verdict: CriticVerdict) -> None:
        self.invocations += 1
        if verdict.passed:
            self.passed += 1
        else:
            self.rejected += 1


def build_critic_tool(
    name: str,
    description: str,
    client: CriticClient,
    metrics: CriticMetrics | None = None,
) -> tuple[StructuredTool, CriticMetrics]:
    """Build a critic Tool for a SKILL phase ReAct loop."""

    if metrics is None:
        metrics = CriticMetrics()

    def _critic_invoke(target_text: str, criteria: str) -> dict[str, Any]:
        verdict = client.review(target_text, criteria, attempt=metrics.invocations + 1)
        metrics.record(verdict)
        return {
            "passed": verdict.passed,
            "reasons": verdict.reasons,
            "suggestions": verdict.suggestions,
            "metadata": verdict.metadata,
        }

    tool = StructuredTool.from_function(
        func=_critic_invoke,
        name=name,
        description=description,
        args_schema=CriticToolInput,
    )
    return tool, metrics


def _parse_json_object(text: str) -> dict[str, Any]:
    stripped = text.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        if len(lines) >= 2 and lines[-1].strip() == "```":
            stripped = "\n".join(lines[1:-1]).strip()
    try:
        value = json.loads(stripped)
    except json.JSONDecodeError:
        return {"passed": False, "reasons": [text], "suggestions": []}
    return value if isinstance(value, dict) else {}


def _string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value]
    if value is None:
        return []
    return [str(value)]


__all__ = [
    "CriticClient",
    "CriticMetrics",
    "CriticToolInput",
    "CriticVerdict",
    "FakeCriticClient",
    "LLMCriticClient",
    "build_critic_tool",
]
