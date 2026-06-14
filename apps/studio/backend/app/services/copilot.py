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
import logging
import secrets
from collections.abc import AsyncIterator, Callable, Mapping
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
    ThinkingBlock,
    ToolResultBlock,
    ToolUseBlock,
)
from pydantic import SecretStr

from app.core.adapters.gateway import (
    CredentialProviderProtocol,
    GatewayAdapter,
    ResolvedRoute,
)
from app.models.copilot import (
    CopilotEvent,
    CopilotEventDone,
    CopilotEventError,
    CopilotEventText,
    CopilotEventThinking,
    CopilotEventToolUseResult,
    CopilotEventToolUseStart,
    CopilotToolName,
)

SessionKey = tuple[str, str, str]
logger = logging.getLogger(__name__)

MAX_REFERENCE_BYTES = 5 * 1024
_BODY_REFERENCE_CHARS = 300
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
# Session keys only index the in-process ``_sessions`` cache, so the salt just
# needs to stay stable for the process lifetime; a fresh random salt per start
# keeps the derived api_key hash unpredictable (S2053).
_SESSION_KEY_SALT = secrets.token_bytes(16)
_SESSION_KEY_ITERATIONS = 100_000


def _default_gateway_adapter_factory() -> GatewayAdapter:
    return GatewayAdapter(transport="in_process")


_gateway_adapter_factory: Callable[[], GatewayAdapter] = _default_gateway_adapter_factory


def make_session_key(
    skill_id: str,
    model_code: str,
    provider_code: str,
    api_key: str,
) -> SessionKey:
    """Build a cache key that changes when credentials rotate."""

    api_key_hash = hashlib.pbkdf2_hmac(
        "sha256",
        api_key.encode("utf-8"),
        _SESSION_KEY_SALT,
        _SESSION_KEY_ITERATIONS,
        dklen=8,
    ).hex()[:16]
    model_provider = f"{model_code}:{provider_code}"
    return (skill_id, model_provider, api_key_hash)


def build_options(
    base_url: str | None,
    api_key: str,
    workspace_dir: str | Path,
    *,
    env_overrides: Mapping[str, str] | None = None,
) -> ClaudeAgentOptions:
    """Build per-session Claude Agent SDK options without mutating os.environ."""

    env = {"ANTHROPIC_API_KEY": api_key}
    if base_url:
        env["ANTHROPIC_BASE_URL"] = base_url
    if env_overrides:
        env.update(env_overrides)

    return ClaudeAgentOptions(
        cwd=workspace_dir,
        permission_mode="acceptEdits",
        allowed_tools=_ALLOWED_TOOLS.copy(),
        env=env,
        # F1: enable extended thinking so the SDK emits ThinkingBlocks. Adaptive
        # lets the model size its own reasoning per task; display is left at the
        # default (full) — never "summarized"/"omitted" — so the whole reasoning
        # trace streams to the UI (collapsible, not summarized away).
        thinking={"type": "adaptive"},
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
    return f"{BASE_SYSTEM_PROMPT_TEMPLATE}\n\n## 当前 View: {view_context.view}\n{formatted_context}"


async def stream_query(
    skill_id: str,
    user_message: str,
    model_override: str | None = None,
    workspace_dir: str | Path | None = None,
) -> AsyncIterator[CopilotEvent]:
    """Stream one Copilot query using the copilot_chat role and optional model override."""

    try:
        routes, credential_provider = _resolve_copilot_runtime(model_override)
    except KeyError as exc:
        yield CopilotEventError(message=f"未知模型: {exc}")
        return
    except ValueError as exc:
        yield CopilotEventError(message=str(exc))
        return

    failures: list[str] = []
    failed_route_ids: list[str] = []
    retry_counts: dict[str, int] = {}
    route_by_id = {route.route_id: route for route in routes}
    route: ResolvedRoute | None = routes[0]
    while route is not None:
        try:
            api_key, base_url, env_overrides = _resolve_route_runtime(
                route,
                credential_provider,
            )
        except ValueError as exc:
            if len(routes) == 1:
                yield CopilotEventError(message=str(exc))
                return
            failures.append(f"{route.route_id}: {exc}")
            route = _next_copilot_route(
                routes=routes,
                route_by_id=route_by_id,
                current_route=route,
                failed_route_ids=failed_route_ids,
                retry_counts=retry_counts,
                error=exc,
            )
            continue
        if not api_key:
            if len(routes) == 1:
                yield CopilotEventError(message=f"Endpoint {route.endpoint_id} 未配置 API key")
                return
            failures.append(f"{route.route_id}: missing API key")
            route = _next_copilot_route(
                routes=routes,
                route_by_id=route_by_id,
                current_route=route,
                failed_route_ids=failed_route_ids,
                retry_counts=retry_counts,
                error=ValueError("missing API key"),
            )
            continue

        tool_names: dict[str, str] = {}
        try:
            client = await get_or_create_session(
                skill_id=skill_id,
                model_code=route.provider_model_id,
                provider_code=route.endpoint_id,
                base_url=base_url,
                api_key=api_key,
                env_overrides=env_overrides,
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
            return
        except Exception as exc:  # noqa: BLE001
            if len(routes) == 1:
                yield _error_event_for_exception(exc)
                return
            failures.append(f"{route.route_id}: {type(exc).__name__}: {exc}")
            route = _next_copilot_route(
                routes=routes,
                route_by_id=route_by_id,
                current_route=route,
                failed_route_ids=failed_route_ids,
                retry_counts=retry_counts,
                error=exc,
            )
            continue

    yield CopilotEventError(
        message="all configured Copilot providers failed" + (f": {'; '.join(failures)}" if failures else "")
    )


def _next_copilot_route(
    *,
    routes: list[ResolvedRoute],
    route_by_id: dict[str, ResolvedRoute],
    current_route: ResolvedRoute,
    failed_route_ids: list[str],
    retry_counts: dict[str, int],
    error: Exception,
) -> ResolvedRoute | None:
    attempted_failed = list(failed_route_ids)
    current_attempt = retry_counts.get(current_route.route_id, 0)
    if current_attempt > 0 and current_route.route_id not in attempted_failed:
        attempted_failed.append(current_route.route_id)

    try:
        decision = _gateway_adapter_factory().decide_fallback(
            {
                "fallback_chain": [{"route_id": route.route_id} for route in routes],
                "current_route_id": current_route.route_id,
                "failed_route_ids": attempted_failed,
                "error": _fallback_error_context(error),
            }
        )
    except Exception as exc:
        logger.warning(
            "Gateway fallback decision failed for current_route_id=%s",
            current_route.route_id,
            exc_info=exc,
        )
        return None
    action = str(decision.get("decision") or decision.get("action") or "")
    if action == "retry_same" and current_attempt == 0:
        retry_counts[current_route.route_id] = current_attempt + 1
        return current_route

    if current_route.route_id not in failed_route_ids:
        failed_route_ids.append(current_route.route_id)

    if action != "switch_route":
        return None
    next_route_id = decision.get("route_id") or decision.get("next_route_id")
    if not isinstance(next_route_id, str):
        return None
    return route_by_id.get(next_route_id)


def _fallback_error_context(error: Exception) -> dict[str, Any]:
    status_code = getattr(error, "status_code", None)
    response = getattr(error, "response", None)
    if status_code is None and response is not None:
        status_code = getattr(response, "status_code", None)
    payload: dict[str, Any] = {
        "exception_type": type(error).__name__,
        "message": str(error),
    }
    if isinstance(status_code, int):
        payload["status_code"] = status_code
    return payload


async def get_or_create_session(
    skill_id: str,
    model_code: str,
    provider_code: str | None = None,
    base_url: str | Path | None = None,
    api_key: str | None = None,
    env_overrides: Mapping[str, str] | None = None,
    workspace_dir: str | Path | None = None,
) -> ClaudeSDKClient:
    """Return a cached SDK client for the skill/model/provider/credential tuple."""

    if provider_code is None or api_key is None or workspace_dir is None:
        raise TypeError("provider_code, api_key, and workspace_dir are required")

    session_key = make_session_key(skill_id, model_code, provider_code, api_key)
    async with _session_lock:
        session = _sessions.get(session_key)
        if session is None:
            session = _session_factory(
                build_options(
                    cast(str | None, base_url),
                    api_key,
                    workspace_dir,
                    env_overrides=env_overrides,
                )
            )
            _sessions[session_key] = session
        return session


async def reset_session(
    skill_id: str | None,
    model_code: str | None = None,
) -> int:
    """Drop cached sessions matching skill and/or model filters."""

    async with _session_lock:
        matched_keys = [
            session_key
            for session_key in _sessions
            if (skill_id is None or session_key[0] == skill_id)
            and (model_code is None or session_key[1] == model_code or session_key[1].startswith(f"{model_code}:"))
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
        if isinstance(block, ThinkingBlock):
            # F1: stream the whole reasoning trace; the UI collapses but never
            # drops it. Skip empty deltas to avoid blank Thought blocks.
            if block.thinking:
                events.append(CopilotEventThinking(content=block.thinking))
        elif isinstance(block, TextBlock):
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


def _resolve_copilot_runtime(
    model_override: str | None,
) -> tuple[list[ResolvedRoute], CredentialProviderProtocol]:
    from app.services.gateway_resolver import build_gateway_model_resolver

    resolver = build_gateway_model_resolver()
    resolved = resolver.resolve_routes(
        "copilot_chat",
        route_override=model_override,
    )
    if not resolved.routes:
        raise ValueError("copilot_chat role 无可用 route")
    return list(resolved.routes), resolver.credential_provider


def _resolve_copilot_routes(model_override: str | None) -> list[ResolvedRoute]:
    routes, _credential_provider = _resolve_copilot_runtime(model_override)
    return routes


def _resolve_copilot_route(model_override: str | None) -> ResolvedRoute:
    return _resolve_copilot_routes(model_override)[0]


def _resolve_route_runtime(
    route: ResolvedRoute,
    credential_provider: CredentialProviderProtocol,
) -> tuple[str, str | None, dict[str, str]]:
    if not route.credential_ref:
        raise ValueError(f"route has no credential_ref: {route.route_id}")
    try:
        secret = credential_provider.get(route.credential_ref)
    except Exception as exc:
        raise ValueError(f"Endpoint {route.endpoint_id} 未配置 API key") from exc
    api_key = _secret_value(secret).strip()
    base_url = route.base_url.strip() or None
    env_overrides: dict[str, str] = {}
    if route.call_method_id == "ark_anthropic_messages":
        base_url = _ark_anthropic_base_url(route.base_url)
        env_overrides["ANTHROPIC_AUTH_TOKEN"] = api_key
        env_overrides["ANTHROPIC_MODEL"] = route.provider_model_id
    elif route.call_method_id == "deepseek_anthropic_messages":
        base_url = _deepseek_anthropic_base_url(route.base_url)
        env_overrides["ANTHROPIC_MODEL"] = route.provider_model_id
    return api_key, base_url, env_overrides


def _secret_value(secret: SecretStr | str) -> str:
    return secret.get_secret_value() if isinstance(secret, SecretStr) else secret


def _ark_anthropic_base_url(base_url: str) -> str:
    normalized = base_url.rstrip("/")
    if normalized.endswith("/api/v3"):
        normalized = normalized[: -len("/api/v3")]
    if normalized.endswith("/api/compatible"):
        return normalized
    return f"{normalized}/api/compatible"


def _deepseek_anthropic_base_url(base_url: str) -> str:
    normalized = base_url.rstrip("/")
    if normalized.endswith("/v1"):
        normalized = normalized[:-3]
    if normalized.endswith("/anthropic"):
        return normalized
    return f"{normalized}/anthropic"


def _error_event_for_exception(exc: Exception) -> CopilotEventError:
    if isinstance(exc, TimeoutError):
        return CopilotEventError(message="请求超时, 检查网络 / 代理")
    if isinstance(exc, (CLIConnectionError, ProcessError, ClaudeSDKError)):
        return CopilotEventError(message=f"后端连接失败 (DeepSeek 端点不可达 / 大陆需代理): {exc}")
    return CopilotEventError(message=f"Copilot 请求失败: {exc}")


def _context_for_prompt(context: dict[str, Any]) -> dict[str, Any]:
    file_path = _file_path_from_context(context)
    return {key: _context_value_for_prompt(key, value, file_path) for key, value in context.items()}


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
