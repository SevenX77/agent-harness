"""Studio Copilot service - Claude Agent SDK integration.

NOTE (T0.1 base_url verify, 2026-05-09):
- claude-agent-sdk version: 0.1.80
- ClaudeSDKClient.__init__ accepts base_url=...: False
- Injection strategy: per-session ClaudeAgentOptions.env
- Verification command showed __init__(self, options=None, transport=None).
- See design.md:59 for the subprocess env injection decision.
"""

from __future__ import annotations

import asyncio
import hashlib
import inspect
from collections.abc import Callable
from pathlib import Path
from typing import Any

from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKClient

from app.models.copilot import CopilotBackend

SessionKey = tuple[str, CopilotBackend, str]

_DEEPSEEK_ANTHROPIC_BASE_URL = "https://api.deepseek.com/anthropic"
_ALLOWED_TOOLS = ["Read", "Write", "Edit", "Bash"]

_sessions: dict[SessionKey, ClaudeSDKClient] = {}
_session_lock = asyncio.Lock()
_session_factory: Callable[[ClaudeAgentOptions], ClaudeSDKClient] = ClaudeSDKClient


def make_session_key(skill_id: str, backend: CopilotBackend, api_key: str) -> SessionKey:
    """Build a cache key that changes when credentials rotate."""

    api_key_hash = hashlib.sha256(api_key.encode("utf-8")).hexdigest()[:16]
    return (skill_id, backend, api_key_hash)


def resolve_base_url(backend: CopilotBackend) -> str | None:
    """Return the Anthropic-compatible base URL for a V1 backend."""

    if backend == "claude":
        return None
    if backend == "deepseek":
        return _DEEPSEEK_ANTHROPIC_BASE_URL
    raise NotImplementedError(f"Backend '{backend}' is reserved for V1.5")


def build_options(
    backend: CopilotBackend,
    api_key: str,
    workspace_dir: str | Path,
) -> ClaudeAgentOptions:
    """Build per-session Claude Agent SDK options without mutating os.environ."""

    env = {"ANTHROPIC_API_KEY": api_key}
    base_url = resolve_base_url(backend)
    if base_url is not None:
        env["ANTHROPIC_BASE_URL"] = base_url

    return ClaudeAgentOptions(
        cwd=workspace_dir,
        permission_mode="acceptEdits",
        allowed_tools=_ALLOWED_TOOLS.copy(),
        env=env,
    )


async def get_or_create_session(
    skill_id: str,
    backend: CopilotBackend,
    api_key: str,
    workspace_dir: str | Path,
) -> ClaudeSDKClient:
    """Return a cached SDK client for the skill/backend/credential tuple."""

    session_key = make_session_key(skill_id, backend, api_key)
    async with _session_lock:
        session = _sessions.get(session_key)
        if session is None:
            session = _session_factory(build_options(backend, api_key, workspace_dir))
            _sessions[session_key] = session
        return session


async def reset_session(skill_id: str | None, backend: CopilotBackend | None) -> int:
    """Drop cached sessions matching skill and/or backend filters."""

    async with _session_lock:
        matched_keys = [
            session_key
            for session_key in _sessions
            if (skill_id is None or session_key[0] == skill_id)
            and (backend is None or session_key[1] == backend)
        ]
        sessions = [_sessions.pop(session_key) for session_key in matched_keys]

    await _close_sessions(sessions)
    return len(sessions)


async def cleanup_all_sessions() -> None:
    """Close every cached SDK client, intended for application shutdown."""

    async with _session_lock:
        sessions = list(_sessions.values())
        _sessions.clear()

    await _close_sessions(sessions)


async def _close_sessions(sessions: list[ClaudeSDKClient]) -> None:
    for session in sessions:
        await _close_session(session)


async def _close_session(session: ClaudeSDKClient) -> None:
    close_method: Any = getattr(session, "disconnect", None) or getattr(session, "close", None)
    if close_method is None:
        return

    result = close_method()
    if inspect.isawaitable(result):
        await result
