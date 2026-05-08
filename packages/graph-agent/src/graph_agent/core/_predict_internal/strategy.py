"""Predict mock strategy skeletons."""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Literal

from pydantic import TypeAdapter, ValidationError

from graph_agent.core._predict_internal.models import GoldenCase

MockedSource = Literal["golden_case", "copilot", "heuristic_stub", "manual"]


class BaseMockStrategy(ABC):
    """Minimal Predict strategy contract for phase-name based lookup."""

    @abstractmethod
    def has_phase(self, phase_name: str) -> bool:
        """Return whether this strategy has data or behavior for ``phase_name``."""

    def has_golden_case(self, phase_name: str) -> bool:
        """Return whether P0 golden output is available for ``phase_name``."""
        return False

    def get_golden_output(self, phase_name: str) -> dict[str, Any]:
        """Return P0 golden output for ``phase_name``."""
        raise KeyError(phase_name)

    def has_manual_override(self, phase_name: str) -> bool:
        """Return whether P1 manual/Copilot output is available for ``phase_name``."""
        return False

    def get_manual_override(self, phase_name: str) -> dict[str, Any]:
        """Return P1 manual/Copilot override for ``phase_name``."""
        raise KeyError(phase_name)

    def get_manual_source(self, phase_name: str) -> MockedSource:
        """Return the P1 source label for ``phase_name``."""
        return "manual"

    def get_phase_schema(self, phase_name: str) -> dict[str, Any] | None:
        """Return the io.outputs schema used for P2 heuristic stubs."""
        return None


MockLLMParam: TypeAdapter[None | dict[str, Any] | Path | list[GoldenCase]] = TypeAdapter(
    None | dict[str, Any] | Path | list[GoldenCase]
)


class PredictMockStrategyError(ValueError):
    """User-facing Predict mock parameter error."""


class HeuristicStubStrategy(BaseMockStrategy):
    """P2 strategy that always falls back to schema-driven heuristic stubs."""

    def __init__(self, phase_schemas: dict[str, dict[str, Any]] | None = None) -> None:
        self._phase_schemas = phase_schemas or {}

    def has_phase(self, phase_name: str) -> bool:
        return True

    def get_phase_schema(self, phase_name: str) -> dict[str, Any] | None:
        return self._phase_schemas.get(phase_name)


class OverrideStrategy(HeuristicStubStrategy):
    """P1 strategy for manual or Copilot-provided per-phase overrides."""

    def __init__(
        self,
        overrides: dict[str, Any],
        *,
        phase_schemas: dict[str, dict[str, Any]] | None = None,
    ) -> None:
        super().__init__(phase_schemas=phase_schemas)
        self._overrides = overrides

    def has_phase(self, phase_name: str) -> bool:
        return phase_name in self._overrides or super().has_phase(phase_name)

    def has_manual_override(self, phase_name: str) -> bool:
        return phase_name in self._overrides

    def get_manual_override(self, phase_name: str) -> dict[str, Any]:
        value = self._overrides[phase_name]
        if _is_wrapped_override(value):
            output = value["output"]
            return output if isinstance(output, dict) else {"value": output}
        return value if isinstance(value, dict) else {"value": value}

    def get_manual_source(self, phase_name: str) -> MockedSource:
        value = self._overrides.get(phase_name)
        if isinstance(value, dict) and value.get("source") == "copilot":
            return "copilot"
        return "manual"


class GoldenCaseStrategy(HeuristicStubStrategy):
    """P0 strategy backed by one validated GoldenCase."""

    def __init__(
        self,
        golden_case: GoldenCase,
        *,
        phase_schemas: dict[str, dict[str, Any]] | None = None,
    ) -> None:
        super().__init__(phase_schemas=phase_schemas)
        self.golden_case = golden_case
        self.expected_path = _expected_path(golden_case)

    def has_phase(self, phase_name: str) -> bool:
        return self.has_golden_case(phase_name) or super().has_phase(phase_name)

    def has_golden_case(self, phase_name: str) -> bool:
        return phase_name in self.golden_case.expected_traces

    def get_golden_output(self, phase_name: str) -> dict[str, Any]:
        return self.golden_case.expected_traces[phase_name]


class BacktestStrategy(HeuristicStubStrategy):
    """P0 strategy backed by a batch of validated GoldenCase objects."""

    def __init__(self, golden_cases: list[GoldenCase]) -> None:
        super().__init__()
        self.golden_cases = golden_cases
        self.expected_path = _expected_path(golden_cases[0]) if golden_cases else []
        self._outputs: dict[str, dict[str, Any]] = {}
        for case in golden_cases:
            self._outputs.update(case.expected_traces)

    def has_phase(self, phase_name: str) -> bool:
        return self.has_golden_case(phase_name) or super().has_phase(phase_name)

    def has_golden_case(self, phase_name: str) -> bool:
        return phase_name in self._outputs

    def get_golden_output(self, phase_name: str) -> dict[str, Any]:
        return self._outputs[phase_name]


class MockStrategy:
    """Factory for the polymorphic ``mock_llm`` parameter."""

    @classmethod
    def from_param(cls, param: Any) -> BaseMockStrategy:
        try:
            parsed = MockLLMParam.validate_python(param)
        except ValidationError as exc:
            raise PredictMockStrategyError(f"Invalid mock_llm parameter: {exc}") from exc

        if parsed is None:
            return HeuristicStubStrategy()
        if isinstance(parsed, Path):
            return GoldenCaseStrategy(_load_golden_case(parsed))
        if isinstance(parsed, list):
            try:
                cases = [
                    case if isinstance(case, GoldenCase) else GoldenCase.model_validate(case)
                    for case in parsed
                ]
            except ValidationError as exc:
                raise PredictMockStrategyError(f"Invalid golden case schema: {exc}") from exc
            return BacktestStrategy(cases)
        if isinstance(parsed, dict):
            return OverrideStrategy(parsed)

        raise PredictMockStrategyError(f"Unsupported mock_llm parameter: {type(parsed).__name__}")


def _load_golden_case(path: Path) -> GoldenCase:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise PredictMockStrategyError(f"Invalid golden case JSON at {path}: {exc}") from exc
    except OSError as exc:
        raise PredictMockStrategyError(f"Unable to read golden case file {path}: {exc}") from exc

    try:
        return GoldenCase.model_validate(raw)
    except ValidationError as exc:
        raise PredictMockStrategyError(f"Invalid golden case schema at {path}: {exc}") from exc


def _expected_path(golden_case: GoldenCase) -> list[str]:
    raw = golden_case.metadata.get("expected_path")
    if isinstance(raw, list):
        return [str(item) for item in raw]
    return list(golden_case.expected_traces)


def _is_wrapped_override(value: object) -> bool:
    return isinstance(value, dict) and "output" in value


__all__ = [
    "BacktestStrategy",
    "BaseMockStrategy",
    "GoldenCaseStrategy",
    "HeuristicStubStrategy",
    "MockLLMParam",
    "MockStrategy",
    "MockedSource",
    "OverrideStrategy",
    "PredictMockStrategyError",
]
