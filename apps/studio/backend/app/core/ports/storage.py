"""Storage port for Studio text and directory objects."""

from __future__ import annotations

from typing import Protocol


class StorageBackend(Protocol):
    """Async file/blob operations used by Studio services."""

    async def read_text(self, path: str) -> str:
        """Read a UTF-8 text object."""
        ...

    async def write_text(self, path: str, content: str) -> None:
        """Write a UTF-8 text object, creating parents as needed."""
        ...

    async def exists(self, path: str) -> bool:
        """Return whether an object or directory exists."""
        ...

    async def list_dirs(self, path: str) -> list[str]:
        """Return child directory names under a directory."""
        ...

    async def copy_tree(self, src: str, dst: str) -> None:
        """Recursively copy a directory tree."""
        ...

    async def move(self, src: str, dst: str) -> None:
        """Move one object or directory tree."""
        ...

    async def delete(self, path: str) -> None:
        """Delete one object or directory tree if it exists."""
        ...
