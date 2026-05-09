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
import json
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from claude_agent_sdk import (
    ClaudeAgentOptions,
    ClaudeSDKClient,
    ClaudeSDKError,
    CLIConnectionError,
    ProcessError,
)
from claude_agent_sdk.types import (
    AssistantMessage,
    ResultMessage,
    TextBlock,
    ToolResultBlock,
    ToolUseBlock,
)

from app.models.copilot import (
    CopilotBackend,
    CopilotEvent,
    CopilotEventDone,
    CopilotEventError,
    CopilotEventText,
    CopilotEventToolUseResult,
    CopilotEventToolUseStart,
    CopilotToolName,
)

SessionKey = tuple[str, CopilotBackend, str]

MAX_REFERENCE_BYTES = 5 * 1024
_BODY_REFERENCE_CHARS = 300
_DEEPSEEK_ANTHROPIC_BASE_URL = "https://api.deepseek.com/anthropic"
_ALLOWED_TOOLS = ["Read", "Write", "Edit", "Bash"]
_ALLOWED_TOOL_SET = set(_ALLOWED_TOOLS)
_FILE_CONTENT_KEYS = {
    "content",
    "file_content",
    "markdown",
    "skill_md_text",
    "phase_config_yaml",
}
_FILE_PATH_KEYS = ("absolute_file_path", "file_path", "path")

BASE_SYSTEM_PROMPT_TEMPLATE = """
你是 Studio Copilot，负责协助用户编辑、理解、验证和运行当前 Studio skill。
请聚焦 Studio 上下文，但允许任何通用问题；不要拒答用户的合理问题。
当上下文不足时，先说明缺口并提出下一步；涉及文件内容时优先使用 Read 工具读取完整文件。
""".strip()


@dataclass(frozen=True)
class ViewContext:
    view: str
    context: dict[str, Any]
    timestamp_ms: int

_sessions: dict[SessionKey, ClaudeSDKClient] = {}
_session_lock = asyncio.Lock()
_session_factory: Callable[[ClaudeAgentOptions], ClaudeSDKClient] = ClaudeSDKClient
_view_contexts: dict[str, ViewContext] = {}
_view_context_lock = asyncio.Lock()


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


async def set_view_context(
    skill_id: str,
    view: str,
    context: dict[str, Any],
    timestamp_ms: int,
) -> bool:
    """Cache the newest known Studio view context for a skill."""

    async with _view_context_lock:
        cached = _view_contexts.get(skill_id)
        if cached is not None and timestamp_ms <= cached.timestamp_ms:
            return False
        _view_contexts[skill_id] = ViewContext(
            view=view,
            context=dict(context),
            timestamp_ms=timestamp_ms,
        )
        return True


def get_view_context(skill_id: str) -> ViewContext | None:
    """Return the latest cached view context for a skill."""

    return _view_contexts.get(skill_id)


def truncate_for_reference(content: str, file_path: str | None) -> str:
    """Trim large file references while preserving YAML frontmatter when possible."""

    if len(content.encode("utf-8")) <= MAX_REFERENCE_BYTES:
        return content

    marker = _truncation_marker(file_path)
    marker_bytes = len(marker.encode("utf-8"))
    budget = max(MAX_REFERENCE_BYTES - marker_bytes, 0)
    frontmatter = _extract_yaml_frontmatter(content)

    if frontmatter is None:
        return content[:_BODY_REFERENCE_CHARS] + marker

    frontmatter_bytes = len(frontmatter.encode("utf-8"))
    if frontmatter_bytes > budget:
        return _trim_utf8_bytes(frontmatter, budget) + marker

    body = content[len(frontmatter) :]
    return frontmatter + body[:_BODY_REFERENCE_CHARS] + marker


def build_system_prompt(skill_id: str) -> str:
    """Build the Copilot system prompt with the latest view context injected."""

    view_context = get_view_context(skill_id)
    if view_context is None:
        return BASE_SYSTEM_PROMPT_TEMPLATE

    formatted_context = json.dumps(
        _context_for_prompt(view_context.context),
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    )
    return (
        f"{BASE_SYSTEM_PROMPT_TEMPLATE}\n\n"
        f"## 当前 View: {view_context.view}\n{formatted_context}"
    )


async def stream_query(
    skill_id: str,
    backend: CopilotBackend,
    api_key: str | None,
    user_message: str,
    workspace_dir: str | Path | None = None,
) -> AsyncIterator[CopilotEvent]:
    """Stream one Copilot query as Studio CopilotEvent objects."""

    if not api_key:
        yield CopilotEventError(message=f"未配置 {backend} backend 的 API key")
        return

    tool_names: dict[str, str] = {}
    try:
        if backend not in ("claude", "deepseek"):
            raise NotImplementedError
        client = await get_or_create_session(
            skill_id=skill_id,
            backend=backend,
            api_key=api_key,
            workspace_dir=workspace_dir or Path.cwd(),
        )
        await _ensure_client_connected(client)
        await client.query(_prompt_with_system_context(skill_id, user_message))

        yielded_done = False
        async for sdk_message in client.receive_response():
            for event in _translate_sdk_message(sdk_message, tool_names):
                if isinstance(event, CopilotEventDone):
                    yielded_done = True
                yield event
        if not yielded_done:
            yield CopilotEventDone()
    except Exception as exc:  # noqa: BLE001
        yield _error_event_for_exception(backend, exc)


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


async def _ensure_client_connected(client: ClaudeSDKClient) -> None:
    if getattr(client, "_query", None) is not None:
        return
    await client.connect()


def _prompt_with_system_context(skill_id: str, user_message: str) -> str:
    return f"{build_system_prompt(skill_id)}\n\n## 用户消息\n{user_message}"


def _translate_sdk_message(message: object, tool_names: dict[str, str]) -> list[CopilotEvent]:
    if isinstance(message, AssistantMessage):
        return _translate_assistant_message(message, tool_names)
    if isinstance(message, ResultMessage):
        if message.is_error:
            details = "; ".join(message.errors or [])
            suffix = f": {details}" if details else ""
            return [CopilotEventError(message=f"SDK 返回错误{suffix}")]
        return [CopilotEventDone()]
    return []


def _translate_assistant_message(
    message: AssistantMessage,
    tool_names: dict[str, str],
) -> list[CopilotEvent]:
    events: list[CopilotEvent] = []
    for block in message.content:
        if isinstance(block, TextBlock):
            events.append(CopilotEventText(content=block.text))
        elif isinstance(block, ToolUseBlock):
            if block.name not in _ALLOWED_TOOL_SET:
                events.append(CopilotEventError(message=f"V1 不支持工具 {block.name}"))
                continue
            tool_names[block.id] = block.name
            events.append(
                CopilotEventToolUseStart(
                    tool_name=cast(CopilotToolName, block.name),
                    tool_input=block.input,
                )
            )
        elif isinstance(block, ToolResultBlock):
            tool_name = tool_names.get(block.tool_use_id, block.tool_use_id)
            result_summary = _tool_result_summary(block.content)
            if block.is_error:
                events.append(CopilotEventError(message=f"工具 {tool_name} 失败: {result_summary}"))
            else:
                events.append(
                    CopilotEventToolUseResult(
                        tool_name=tool_name,
                        success=True,
                        result_summary=result_summary,
                    )
                )
    return events


def _tool_result_summary(content: str | list[dict[str, Any]] | None) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    return json.dumps(content, ensure_ascii=False)


def _error_event_for_exception(backend: CopilotBackend, exc: Exception) -> CopilotEventError:
    if isinstance(exc, TimeoutError):
        return CopilotEventError(message="请求超时, 检查网络 / 代理")
    if isinstance(exc, NotImplementedError):
        return CopilotEventError(message=f"V1.5 backend ({backend}) 暂不可用")
    if isinstance(exc, (CLIConnectionError, ProcessError, ClaudeSDKError)):
        return CopilotEventError(
            message=f"后端连接失败 (DeepSeek 端点不可达 / 大陆需代理): {exc}"
        )
    return CopilotEventError(message=f"Copilot 请求失败: {exc}")


def _context_for_prompt(context: dict[str, Any]) -> dict[str, Any]:
    file_path = _file_path_from_context(context)
    return {
        key: _context_value_for_prompt(key, value, file_path)
        for key, value in context.items()
    }


def _context_value_for_prompt(key: str, value: Any, file_path: str | None) -> Any:
    if isinstance(value, str) and _is_file_content_key(key):
        return truncate_for_reference(value, file_path)
    return value


def _is_file_content_key(key: str) -> bool:
    return (
        key in _FILE_CONTENT_KEYS
        or key.endswith("_text")
        or key.endswith("_yaml")
        or key.endswith("_md")
        or key.endswith("_markdown")
    )


def _file_path_from_context(context: dict[str, Any]) -> str | None:
    for key in _FILE_PATH_KEYS:
        value = context.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def _truncation_marker(file_path: str | None) -> str:
    path = file_path or "<unknown>"
    return f"[Content truncated due to length. Use 'Read' tool to inspect the full file: {path}]"


def _extract_yaml_frontmatter(content: str) -> str | None:
    lines = content.splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        return None
    for index in range(1, len(lines)):
        if lines[index].strip() == "---":
            return "".join(lines[: index + 1])
    return None


def _trim_utf8_bytes(content: str, max_bytes: int) -> str:
    if max_bytes <= 0:
        return ""
    encoded = content.encode("utf-8")
    return encoded[:max_bytes].decode("utf-8", errors="ignore")
