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


class CanvasSerializerFatal(Exception):
    """Raised when the Canvas serialize helper rejects graph topology."""

    def __init__(
        self,
        *,
        code: str,
        message: str,
        detail: dict[str, object] | None = None,
        elapsed_ms: float = 0,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.detail = detail or {}
        self.elapsed_ms = elapsed_ms
