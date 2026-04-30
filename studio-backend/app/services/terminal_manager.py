"""PTY terminal session management for Studio."""

from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass
from typing import Any

from fastapi import WebSocket
from ptyprocess import PtyProcess

from app.core.exceptions import error_response, raise_error_response, standard_http_exception
from app.models.terminal import TerminalSession
from app.services.skills import resolve_skill_dir

_TERMINAL_TTL_SECONDS = 3600
_MAX_TERMINALS = 3


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
        if len(self._sessions) >= _MAX_TERMINALS:
            response = error_response(
                error_code="TERMINAL_SPAWN_FAILED",
                http_status=500,
                message="Terminal session limit reached",
                details={"limit": _MAX_TERMINALS},
                retry_strategy="idempotent",
            )
            raise_error_response(response)

        skill_dir = resolve_skill_dir(skill_id)
        term_id = uuid.uuid4().hex[:12]
        try:
            process = PtyProcess.spawn(self.command, cwd=str(skill_dir))
        except Exception as exc:
            response = error_response(
                error_code="TERMINAL_SPAWN_FAILED",
                http_status=500,
                message=f"Failed to spawn terminal for skill {skill_id}: {exc}",
                details={"skill_id": skill_id, "command": self.command},
                retry_strategy="idempotent",
            )
            raise_error_response(response)

        self._sessions[term_id] = TerminalRecord(
            term_id=term_id,
            process=process,
            cwd=str(skill_dir),
            expires_at=time.monotonic() + _TERMINAL_TTL_SECONDS,
        )
        return TerminalSession(
            term_id=term_id,
            ws_url=f"/ws/terminal/{term_id}",
            cwd=str(skill_dir),
            ttl_seconds=_TERMINAL_TTL_SECONDS,
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
        if self._reaper_task is None:
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
            await asyncio.sleep(30)

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


terminal_manager = TerminalManager()
