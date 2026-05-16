"""Canvas/skill snapshot conflict errors."""

from __future__ import annotations


class CanvasConflictError(Exception):
    """Raised when a Canvas snapshot is older than the current GRAPH.md."""

    def __init__(
        self,
        *,
        current_hash: str,
        current_markdown_content: str,
        current_phase_count: int | None = None,
    ) -> None:
        super().__init__("Canvas snapshot is stale")
        self.current_hash = current_hash
        self.current_markdown_content = current_markdown_content
        self.current_phase_count = current_phase_count
