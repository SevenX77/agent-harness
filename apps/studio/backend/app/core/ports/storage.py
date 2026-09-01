"""Storage port for Studio text and directory objects."""

from __future__ import annotations

from typing import Protocol


class StorageBackend(Protocol):
    """Async file/blob operations used by Studio services."""

    async def read_text(self, path: str) -> str:
        """Read a UTF-8 text object."""
        ...

    async def read_authored_text(self, path: str) -> str:
        """Read a text object a PERSON may have written with an outside editor.

        Two read methods rather than one because the two answer different
        questions, and the caller is the only one that knows which it is asking.
        What separates them is AUTHORSHIP, not location: `read_text` is for files
        Studio itself produced (run records included, though they sit under the
        workspace too), and this one is for files a person may have written or
        edited elsewhere, where a leading byte-order mark is encoding an editor
        added rather than a character the author typed. The rule it applies is
        `app.core.authored_text`'s — see that module for what the mark costs when
        a reader keeps it, and that module's own docstring for the scope in full.
        """
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
