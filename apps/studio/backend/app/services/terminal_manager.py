"""PTY terminal session management for Studio."""

from __future__ import annotations

import asyncio
import re
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fastapi import WebSocket
from ptyprocess import PtyProcess

from app.core import config
from app.core.exceptions import error_response, raise_error_response, standard_http_exception
from app.models.terminal import TerminalSession

_SKILL_ID_RE = re.compile(r"^[a-z0-9-]+$")
_ALLOWED_COMMANDS = {
    ("claude",),
    ("gemini",),
    ("bash", "--noprofile", "--norc"),
}


@dataclass
class TerminalRecord:
    """Active PTY process and its metadata."""

    term_id: str
    process: Any
    cwd: str
    expires_at: float


class TerminalManager:
    """Creates, bridges, and reaps PTY-backed terminal sessions."""

    def __init__(self) -> None:
        self._sessions: dict[str, TerminalRecord] = {}
        self._reaper_task: asyncio.Task[None] | None = None
        self.command: list[str] = ["claude"]

    def create_terminal(self, skill_id: str) -> TerminalSession:
        self.reap_expired()
        if len(self._sessions) >= config.MAX_CONCURRENT_TERMINALS:
            response = error_response(
                error_code="TERMINAL_LIMIT_REACHED",
                http_status=503,
                message="Terminal session limit reached",
                details={"limit": config.MAX_CONCURRENT_TERMINALS},
                retry_strategy="backoff",
            )
            raise_error_response(response)

        skill_dir = _resolve_terminal_cwd(skill_id)
        command = _validated_command(self.command)
        term_id = uuid.uuid4().hex[:12]
        try:
            process = PtyProcess.spawn(command, cwd=str(skill_dir))
        except Exception as exc:
            response = error_response(
                error_code="TERMINAL_SPAWN_FAILED",
                http_status=500,
                message=f"Failed to spawn terminal for skill {skill_id}: {exc}",
                details={"skill_id": skill_id, "command": command},
                retry_strategy="idempotent",
            )
            raise_error_response(response)

        self._sessions[term_id] = TerminalRecord(
            term_id=term_id,
            process=process,
            cwd=str(skill_dir),
            expires_at=time.monotonic() + config.TERMINAL_SESSION_TTL_SECONDS,
        )
        return TerminalSession(
            term_id=term_id,
            ws_url=f"/ws/terminal/{term_id}",
            cwd=str(skill_dir),
            ttl_seconds=config.TERMINAL_SESSION_TTL_SECONDS,
        )

    async def bridge(self, websocket: WebSocket, term_id: str) -> None:
        record = self._sessions.get(term_id)
        if record is None:
            raise standard_http_exception(
                "TERMINAL_SPAWN_FAILED",
                f"Terminal session not found: {term_id}",
                {"term_id": term_id},
            )
        await websocket.accept()
        reader = asyncio.create_task(self._read_pty_loop(websocket, record))
        writer = asyncio.create_task(self._write_pty_loop(websocket, record))
        done, pending = await asyncio.wait(
            {reader, writer},
            return_when=asyncio.FIRST_COMPLETED,
        )
        for task in pending:
            task.cancel()
        await asyncio.gather(*done, *pending, return_exceptions=True)

    def start_reaper(self) -> None:
        if self._reaper_task is None or self._reaper_task.done():
            self._reaper_task = asyncio.create_task(self._reap_loop())

    async def shutdown(self) -> None:
        if self._reaper_task is not None:
            self._reaper_task.cancel()
            await asyncio.gather(self._reaper_task, return_exceptions=True)
            self._reaper_task = None
        for term_id in list(self._sessions):
            self.close(term_id)

    def close(self, term_id: str) -> None:
        record = self._sessions.pop(term_id, None)
        if record is None:
            return
        process = record.process
        try:
            process.terminate(force=True)
        except TypeError:
            process.terminate()
        except Exception:
            return

    def reap_expired(self) -> None:
        now = time.monotonic()
        for term_id, record in list(self._sessions.items()):
            if record.expires_at <= now:
                self.close(term_id)

    async def _reap_loop(self) -> None:
        while True:
            self.reap_expired()
            await asyncio.sleep(config.TERMINAL_REAPER_INTERVAL_SECONDS)

    async def _read_pty_loop(self, websocket: WebSocket, record: TerminalRecord) -> None:
        while record.term_id in self._sessions:
            data = await asyncio.to_thread(_read_nonblocking, record.process)
            if not data:
                await asyncio.sleep(0.05)
                continue
            if isinstance(data, str):
                await websocket.send_text(data)
            else:
                await websocket.send_bytes(data)

    async def _write_pty_loop(self, websocket: WebSocket, record: TerminalRecord) -> None:
        while record.term_id in self._sessions:
            message = await websocket.receive()
            if message.get("type") == "websocket.disconnect":
                return
            data = message.get("bytes")
            if data is None:
                text = message.get("text")
                data = text if isinstance(text, str) else ""
            if data:
                await asyncio.to_thread(record.process.write, data)


def _read_nonblocking(process: Any) -> bytes | str | None:
    try:
        data = process.read_nonblocking(size=4096, timeout=0.1)
    except Exception:
        return None
    if isinstance(data, (bytes, str)):
        return data
    return None


def _validated_command(command: list[str]) -> list[str]:
    if tuple(command) not in _ALLOWED_COMMANDS:
        response = error_response(
            error_code="TERMINAL_SPAWN_FAILED",
            http_status=500,
            message="Terminal command is not allowed",
            details={"command": command},
            retry_strategy="idempotent",
        )
        raise_error_response(response)
    return list(command)


def _resolve_terminal_cwd(skill_id: str) -> Path:
    if _SKILL_ID_RE.fullmatch(skill_id) is None:
        raise ValueError(f"SKILL_NOT_FOUND: Skill not found: {skill_id}")

    candidates = (
        config.default_workspace_skills_dir() / skill_id,
        config.SKILLS_DIR / skill_id,
    )
    allowed_roots = (
        config.default_workspace_skills_dir().resolve(),
        config.SKILLS_DIR.resolve(),
    )

    for candidate, root in zip(candidates, allowed_roots, strict=True):
        resolved = candidate.resolve()
        if not resolved.is_relative_to(root):
            continue
        if (
            not resolved.is_relative_to(config.WORKSPACES_DIR.resolve())
            and not resolved.is_relative_to(config.SKILLS_DIR.resolve())
        ):
            continue
        if (resolved / "GRAPH.md").is_file():
            return resolved

    raise ValueError(f"SKILL_NOT_FOUND: Skill not found: {skill_id}")


terminal_manager = TerminalManager()
