"""Local filesystem StorageBackend adapter."""

from __future__ import annotations

import asyncio
import shutil
from pathlib import Path

import aiofiles  # type: ignore[import-untyped]


class LocalFilesystemBackend:
    """Async wrapper around local filesystem operations."""

    def __init__(self, base_dir: Path) -> None:
        self._base_dir = base_dir.resolve()

    async def read_text(self, path: str) -> str:
        """Read UTF-8 text from a local path."""
        async with aiofiles.open(self._resolve(path), encoding="utf-8") as file:
            return str(await file.read())

    async def write_text(self, path: str, content: str) -> None:
        """Write UTF-8 text to a local path."""
        target = self._resolve(path)
        await asyncio.to_thread(target.parent.mkdir, parents=True, exist_ok=True)
        async with aiofiles.open(target, "w", encoding="utf-8") as file:
            await file.write(content)

    async def exists(self, path: str) -> bool:
        """Return whether a path exists."""
        return await asyncio.to_thread(self._resolve(path).exists)

    async def list_dirs(self, path: str) -> list[str]:
        """Return child directory names under a path."""
        root = self._resolve(path)
        if not await asyncio.to_thread(root.exists):
            return []
        return await asyncio.to_thread(
            lambda: sorted(child.name for child in root.iterdir() if child.is_dir()),
        )

    async def copy_tree(self, src: str, dst: str) -> None:
        """Copy a directory tree, replacing existing files."""
        source = self._resolve(src)
        target = self._resolve(dst)
        await asyncio.to_thread(target.parent.mkdir, parents=True, exist_ok=True)
        await asyncio.to_thread(shutil.copytree, source, target, dirs_exist_ok=True)

    async def move(self, src: str, dst: str) -> None:
        """Move a file or directory tree."""
        source = self._resolve(src)
        target = self._resolve(dst)
        await asyncio.to_thread(target.parent.mkdir, parents=True, exist_ok=True)
        await asyncio.to_thread(shutil.move, str(source), str(target))

    async def delete(self, path: str) -> None:
        """Delete a file or directory tree if present."""
        target = self._resolve(path)
        if not await asyncio.to_thread(target.exists):
            return
        if await asyncio.to_thread(target.is_dir):
            await asyncio.to_thread(shutil.rmtree, target)
        else:
            await asyncio.to_thread(target.unlink)

    def _resolve(self, path: str) -> Path:
        candidate = Path(path)
        if candidate.is_absolute():
            return candidate.resolve()
        resolved = (self._base_dir / candidate).resolve()
        if not resolved.is_relative_to(self._base_dir):
            raise ValueError(f"Path escapes storage root: {path}")
        return resolved
