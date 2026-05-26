"""Isolated builtin reference reader runtime."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from graph_agent.core.exceptions import GraphAgentFatalError
from graph_agent.runtime.state import BlackboardState
from graph_agent.runtime.state_mapper import ReaderSandboxState
from graph_agent.tools.builtin.read_reference import read_resource_file


@dataclass(frozen=True)
class ReferenceReaderRuntime:
    """Run reference reading in an isolated sandbox state."""

    skill_id: str
    phase_id: str
    root: Path
    references: list[dict[str, Any]] | None = None
    max_output_tokens: int = 3000
    language: str = "zh"
    timeout_s: int = 60

    def initial_state(self) -> BlackboardState:
        return ReaderSandboxState(
            skill_id=self.skill_id,
            phase_id=self.phase_id,
            root=self.root,
            references=self.references,
            max_output_tokens=self.max_output_tokens,
            language=self.language,
            timeout_s=self.timeout_s,
        ).to_blackboard()

    def run(self) -> dict[str, str]:
        self.initial_state()
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(self._read_references)
            try:
                return {"markdown": future.result(timeout=self.timeout_s)}
            except FutureTimeoutError as exc:
                raise GraphAgentFatalError("[F-v3-reference-reader-failed] timeout") from exc

    def _read_references(self) -> str:
        chunks: list[str] = []
        for spec in self.references or []:
            reference_id = spec.get("id")
            summary = spec.get("summary", "")
            path = spec.get("path", "")
            body = read_resource_file(
                root=self.root,
                relative_path=path,
                error_code="[F-v3-resource-reference-path-invalid]",
            )
            chunks.append(f"## {reference_id}: {summary}\n\n{_truncate_tokens(body, self.max_output_tokens)}")
        return "\n\n".join(chunks) if chunks else "无预读取参考资料"


def _truncate_tokens(text: str, max_tokens: int) -> str:
    tokens = text.split()
    if len(tokens) <= max_tokens:
        return text
    return " ".join(tokens[:max_tokens])


__all__ = ["ReferenceReaderRuntime"]
