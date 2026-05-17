"""Canvas/skill snapshot conflict errors."""

from __future__ import annotations


class CanvasConflictError(Exception):
    """Raised when client snapshot hash mismatches current disk GRAPH.md."""

    def __init__(
        self,
        *,
        current_hash: str,
        current_markdown_content: str,
    ) -> None:
        super().__init__("Skill snapshot is stale")
        self.current_hash = current_hash
        self.current_markdown_content = current_markdown_content
