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
import difflib
import hashlib
import inspect
import json
import logging
import secrets
import tempfile
from collections.abc import AsyncIterator, Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, cast
from xml.sax.saxutils import escape

from claude_agent_sdk import (
    ClaudeAgentOptions,
    ClaudeSDKClient,
    ClaudeSDKError,
    CLIConnectionError,
    PermissionResultAllow,
    PermissionResultDeny,
    ProcessError,
    ToolPermissionContext,
)
from claude_agent_sdk.types import (
    AssistantMessage,
    ResultMessage,
    TextBlock,
    ThinkingBlock,
    ToolResultBlock,
    ToolUseBlock,
    UserMessage,
)
from pydantic import SecretStr

from app.core.adapters.gateway import (
    CredentialProviderProtocol,
    GatewayAdapter,
    ResolvedRoute,
)
from app.core.adapters.transport_factory import build_gateway_adapter
from app.models.copilot import (
    CopilotEvent,
    CopilotEventBashApprovalRequired,
    CopilotEventContextResolved,
    CopilotEventDone,
    CopilotEventError,
    CopilotEventPatchProposed,
    CopilotEventText,
    CopilotEventThinking,
    CopilotEventToolUseResult,
    CopilotEventToolUseStart,
    CopilotToolName,
)

SessionKey = tuple[str, str, str]
SessionCacheKey = tuple[str, str, str, str]
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
你是 Studio Copilot —— 精通 graph_skill 搭建的助手，在 Studio 工作台帮用户设计 / 编辑 / 理解 / 验证 / 运行当前 skill。

## 回复语言（硬规则，优先级最高）
**语言跟随用户**：永远用用户**最后一条消息**的语言回复。用户写英文 → 整段回复用英文；写中文 → 用中文。
本提示词和注入上下文是中文，**不代表**回复用中文。例：用户发 "hello" → 用英文回复。代码、标识符、错误码原样保留。

## graph_skill 格式心智模型 (schema v0.3.0)
一个 skill = 根 `GRAPH.md` + 每个 phase 一个目录 `phases/<name>/`：
- **GRAPH.md** frontmatter 必含：`schema_version: "v0.3.0"`(精确)、`name`(`^[a-z][a-z0-9_-]*$`)、
  `phases: [名字列表]`、`io:`(根输入/输出 JSON schema)；可选 `description` / `llm_role`。
- **GRAPH.md body** 用 `<phase>` XML 画 DAG：入口 `depends_on="input"`，下游引用上游 phase 名
  (多依赖空格/逗号分隔)，终点加 `output`。三处名字必须一致：
  frontmatter `phases` = body `<phase>` = `phases/<name>/` 目录。
- **每个 phase 目录恰好一个模式文件**：`LOGIC.md`(确定性 Python，最常见)= frontmatter `io:` +
  body `<action>名</action>` → `phases/<name>/actions/<名>.py`
  (签名 `def 名(inputs): ...`，读上游、返回本 phase 输出，不修改 inputs)。
  另两种模式是 `SUBGRAPH.md`(子图) / `SKILL.md`(委派子 skill)；
  agent 等行为、精确语法与错误码以**挂载的 skill-spec 为准**。

## 生命周期
Compile(校验 DAG + schema)→ Predict(测试输入空跑)→ Run(真跑)。编译/lint 错误码形如 `[F-v3-...]`。

## 工作方式
- **先 Read 后改**：动文件前先读完整内容，别凭空猜；改完该编译就编译验证。
- **主动诊断**：用户问"为啥编译失败"或出现 `[F-v3-...]` → 读相关文件定位根因、给具体修法，不空谈。
- 权威格式细节已挂载(见下)，用 Read 查阅；业务领域知识靠你自带 + 用户喂的文档，不编造领域事实。
- 聚焦 Studio 上下文，但允许任何合理通用问题，不拒答。
""".strip()


def _skill_spec_dir() -> Path | None:
    """The authoritative graph_skill syntax spec dir, mounted for the copilot to
    Read (F3 渐进暴露). Returns None when absent (e.g. a bundled app without docs)."""
    candidate = Path(__file__).resolve().parents[5] / "docs/engine/mvp1/01-contract/02-skill-syntax"
    return candidate if candidate.is_dir() else None


@dataclass(frozen=True)
class ViewContext:
    view: str
    context: dict[str, Any]
    timestamp_ms: int


_sessions: dict[SessionCacheKey, ClaudeSDKClient] = {}
_session_lock = asyncio.Lock()
_session_factory: Callable[[ClaudeAgentOptions], ClaudeSDKClient] = ClaudeSDKClient
_view_contexts: dict[str, ViewContext] = {}
_view_context_lock = asyncio.Lock()
# Session keys only index the in-process ``_sessions`` cache, so the salt just
# needs to stay stable for the process lifetime; a fresh random salt per start
# keeps the derived api_key hash unpredictable (S2053).
_SESSION_KEY_SALT = secrets.token_bytes(16)
_SESSION_KEY_ITERATIONS = 100_000


class CopilotRouteResolutionError(ValueError):
    def __init__(
        self,
        message: str,
        *,
        error_code: str,
        error_payload: dict[str, Any],
    ) -> None:
        super().__init__(message)
        self.error_code = error_code
        self.error_payload = error_payload


def _default_gateway_adapter_factory() -> GatewayAdapter:
    return build_gateway_adapter()


_gateway_adapter_factory: Callable[[], GatewayAdapter] = _default_gateway_adapter_factory


# ── F5 safe-write (model B) ──────────────────────────────────────────────────
#
# The SDK consults ``can_use_tool`` only for tools NOT pre-allowed via
# ``allowed_tools`` (verified by PoC). So safe-write keeps only Read pre-allowed
# and routes Write/Edit/Bash through the callback: Write/Edit emit a
# ``patch_proposed`` event (apply-then-review, non-blocking) then ALLOW; Bash is
# held for human approval (the interactive approve round-trip needs a
# bidirectional WS channel, not yet wired) and surfaced as
# ``bash_approval_required``. The callback feeds events into the active query's
# queue via a per-skill registry — one active query per skill.


@dataclass
class _SafeWriteSink:
    queue: asyncio.Queue[CopilotEvent | object]
    workspace_root: Path


@dataclass(frozen=True)
class _PendingBashApproval:
    command: str
    workspace_root: Path


@dataclass(frozen=True)
class BashApprovalResult:
    tool_use_id: str
    approved: bool
    executed: bool
    success: bool
    stdout: str = ""
    stderr: str = ""
    returncode: int | None = None
    message: str | None = None


_safe_write_sinks: dict[str, _SafeWriteSink] = {}
_pending_bash_approvals: dict[tuple[str, str], _PendingBashApproval] = {}

_STREAM_SENTINEL = object()


def _cleanup_pending_bash_approvals(skill_id: str | None = None) -> int:
    """Drop held Bash approvals that no longer belong to a live session."""

    if skill_id is None:
        count = len(_pending_bash_approvals)
        _pending_bash_approvals.clear()
        return count

    keys = [key for key in _pending_bash_approvals if key[0] == skill_id]
    for key in keys:
        _pending_bash_approvals.pop(key, None)
    return len(keys)


async def _drain_sdk_response(
    client: ClaudeSDKClient,
    tool_names: dict[str, str],
    queue: asyncio.Queue[CopilotEvent | object],
) -> None:
    """Translate the SDK response stream onto the query queue, then close it.

    Module-level (not a per-query closure) so it binds its args explicitly — the
    can_use_tool callback feeds the same queue concurrently, and a sentinel marks
    end-of-stream so the generator stops draining.
    """

    try:
        async for sdk_message in client.receive_response():
            for event in _translate_sdk_message(sdk_message, tool_names):
                await queue.put(event)
    finally:
        await queue.put(_STREAM_SENTINEL)

_BASH_HELD_MESSAGE = "Bash 命令需用户审批（审批 UI 待接入，命令已暂缓执行）"
_SAFE_WRITE_OUTSIDE_WORKSPACE_MESSAGE = "Write/Edit 目标必须位于 workspace 内"


def _resolve_safe_write_target(
    raw_path: object, workspace_root: Path
) -> tuple[Path, str] | None:
    """Resolve a tool path and verify its real target stays inside workspace."""

    workspace_resolved = workspace_root.resolve(strict=False)
    candidate = Path(str(raw_path))
    target = candidate if candidate.is_absolute() else workspace_root / candidate
    try:
        target_resolved = target.resolve(strict=False)
        relative_path = target_resolved.relative_to(workspace_resolved)
    except (OSError, RuntimeError, ValueError) as exc:
        logger.warning(
            "phase=copilot_safe_write target rejected outside workspace: %s (root=%s): %s",
            target,
            workspace_resolved,
            exc,
        )
        return None
    return target_resolved, relative_path.as_posix()


def _compute_after_content(
    tool_name: str, tool_input: Mapping[str, Any], before: str
) -> str:
    """Best-effort applied content for instant diff rendering.

    Authoritative content is the file on disk after the SDK applies; this only
    drives the inline diff bubble, so an approximate Edit replacement is fine.
    """

    if tool_name == "Write":
        return str(tool_input.get("content", ""))
    old = str(tool_input.get("old_string", ""))
    new = str(tool_input.get("new_string", ""))
    if tool_input.get("replace_all"):
        return before.replace(old, new)
    return before.replace(old, new, 1)


def _sha256_text(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _patch_checkpoint_id(skill_id: str, tool_use_id: str, path: str) -> str:
    payload = f"{skill_id}\0{tool_use_id}\0{path}"
    return f"patch:{hashlib.sha256(payload.encode('utf-8')).hexdigest()}"


def _unified_patch_diff(path: str, before: str, after: str, before_existed: bool) -> str:
    fromfile = path if before_existed else "/dev/null"
    return "\n".join(
        difflib.unified_diff(
            before.splitlines(),
            after.splitlines(),
            fromfile=fromfile,
            tofile=path,
            lineterm="",
        )
    )


def _build_patch_proposed_event(
    skill_id: str,
    tool_name: str,
    tool_input: Mapping[str, Any],
    tool_use_id: str,
    workspace_root: Path,
) -> CopilotEventPatchProposed | None:
    """Read pre-edit bytes (a read — D12 sole-writer untouched) and build the diff event."""

    raw_path = tool_input.get("file_path") or tool_input.get("path")
    if not raw_path:
        return None
    safe_target = _resolve_safe_write_target(raw_path, workspace_root)
    if safe_target is None:
        return None
    abs_path, path = safe_target
    existed = abs_path.is_file()
    try:
        before = abs_path.read_text(encoding="utf-8") if existed else ""
    except OSError as exc:
        logger.warning("phase=copilot_safe_write cannot read pre-edit bytes %s: %s", abs_path, exc)
        before = ""
        existed = False
    after = _compute_after_content(tool_name, tool_input, before)
    return CopilotEventPatchProposed(
        tool_use_id=tool_use_id,
        tool_name=cast(Literal["Write", "Edit"], tool_name),
        path=path,
        before_existed=existed,
        before_content=before,
        after_content=after,
        before_hash=_sha256_text(before) if existed else None,
        after_hash=_sha256_text(after),
        diff=_unified_patch_diff(path, before, after, existed),
        checkpoint_id=_patch_checkpoint_id(skill_id, tool_use_id, path),
    )


def _make_safe_write_can_use_tool(
    skill_id: str,
) -> Callable[[str, dict[str, Any], ToolPermissionContext], Any]:
    """Build the per-skill ``can_use_tool`` callback (looks up the active sink)."""

    async def can_use_tool(
        tool_name: str,
        tool_input: dict[str, Any],
        context: ToolPermissionContext,
    ) -> PermissionResultAllow | PermissionResultDeny:
        sink = _safe_write_sinks.get(skill_id)
        tool_use_id = context.tool_use_id or ""
        if tool_name in ("Write", "Edit"):
            if sink is not None:
                raw_path = tool_input.get("file_path") or tool_input.get("path")
                if raw_path and _resolve_safe_write_target(raw_path, sink.workspace_root) is None:
                    return PermissionResultDeny(
                        message=_SAFE_WRITE_OUTSIDE_WORKSPACE_MESSAGE,
                        interrupt=False,
                    )
                event = _build_patch_proposed_event(
                    skill_id, tool_name, tool_input, tool_use_id, sink.workspace_root
                )
                if event is not None:
                    logger.info(
                        "phase=copilot_safe_write action=patch_proposed tool=%s path=%s",
                        tool_name,
                        event.path,
                    )
                    await sink.queue.put(event)
            return PermissionResultAllow()
        if tool_name == "Bash":
            command = str(tool_input.get("command", ""))
            logger.info("phase=copilot_safe_write action=bash_held command=%s", command)
            if sink is not None:
                if tool_use_id:
                    _pending_bash_approvals[(skill_id, tool_use_id)] = _PendingBashApproval(
                        command=command,
                        workspace_root=sink.workspace_root,
                    )
                await sink.queue.put(
                    CopilotEventBashApprovalRequired(tool_use_id=tool_use_id, command=command)
                )
            return PermissionResultDeny(message=_BASH_HELD_MESSAGE, interrupt=False)
        return PermissionResultAllow()

    return can_use_tool


async def resolve_bash_approval(
    skill_id: str,
    tool_use_id: str,
    *,
    approve: bool,
    timeout_s: float = 30.0,
) -> BashApprovalResult:
    """Resolve a held Copilot Bash command exactly once."""

    pending = _pending_bash_approvals.pop((skill_id, tool_use_id), None)
    if pending is None:
        return BashApprovalResult(
            tool_use_id=tool_use_id,
            approved=approve,
            executed=False,
            success=False,
            message="approval_not_found",
        )
    if not approve:
        return BashApprovalResult(
            tool_use_id=tool_use_id,
            approved=False,
            executed=False,
            success=True,
            message="rejected",
        )

    process = await asyncio.create_subprocess_shell(
        pending.command,
        cwd=pending.workspace_root,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout_bytes, stderr_bytes = await asyncio.wait_for(process.communicate(), timeout_s)
    except TimeoutError:
        process.kill()
        stdout_bytes, stderr_bytes = await process.communicate()
        return BashApprovalResult(
            tool_use_id=tool_use_id,
            approved=True,
            executed=True,
            success=False,
            stdout=stdout_bytes.decode("utf-8", errors="replace"),
            stderr=stderr_bytes.decode("utf-8", errors="replace"),
            returncode=process.returncode,
            message="timeout",
        )

    stdout = stdout_bytes.decode("utf-8", errors="replace")
    stderr = stderr_bytes.decode("utf-8", errors="replace")
    return BashApprovalResult(
        tool_use_id=tool_use_id,
        approved=True,
        executed=True,
        success=process.returncode == 0,
        stdout=stdout,
        stderr=stderr,
        returncode=process.returncode,
        message=None if process.returncode == 0 else "command_failed",
    )


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


def _make_session_cache_key(
    skill_id: str,
    model_code: str,
    provider_code: str,
    api_key: str,
    workspace_dir: str | Path,
) -> SessionCacheKey:
    base_skill_id, model_provider, api_key_hash = make_session_key(
        skill_id,
        model_code,
        provider_code,
        api_key,
    )
    workspace_hash = hashlib.sha256(
        str(Path(workspace_dir).resolve(strict=False)).encode("utf-8")
    ).hexdigest()[:16]
    return (base_skill_id, model_provider, api_key_hash, workspace_hash)


def build_options(
    base_url: str | None,
    api_key: str,
    workspace_dir: str | Path,
    *,
    env_overrides: Mapping[str, str] | None = None,
    can_use_tool: Callable[[str, dict[str, Any], ToolPermissionContext], Any] | None = None,
) -> ClaudeAgentOptions:
    """Build per-session Claude Agent SDK options without mutating os.environ.

    With ``can_use_tool`` (the F5 safe-write path) only Read is pre-allowed and
    permission_mode is "default", so the SDK routes Write/Edit/Bash through the
    callback. Without it (the SDK probe path) the legacy acceptEdits + full
    allow-list is kept so the probe applies edits without prompting.
    """

    env = {"ANTHROPIC_API_KEY": api_key}
    if base_url:
        env["ANTHROPIC_BASE_URL"] = base_url
    if env_overrides:
        env.update(env_overrides)

    # F3: mount the authoritative graph_skill spec so the copilot can Read it for
    # exact format/error-code ground-truth (渐进暴露). Skipped if absent.
    spec_dir = _skill_spec_dir()
    add_dirs: list[str | Path] = [str(spec_dir)] if spec_dir is not None else []
    permission_mode: Literal["default", "acceptEdits"]
    if can_use_tool is not None:
        # Pre-allowing a tool makes the SDK skip can_use_tool for it, so keep only
        # Read pre-allowed; Write/Edit/Bash flow through the safe-write callback.
        allowed_tools = ["Read"]
        permission_mode = "default"
    else:
        allowed_tools = _ALLOWED_TOOLS.copy()
        permission_mode = "acceptEdits"
    return ClaudeAgentOptions(
        cwd=workspace_dir,
        permission_mode=permission_mode,
        allowed_tools=allowed_tools,
        env=env,
        can_use_tool=can_use_tool,
        # F1: enable extended thinking so the SDK emits ThinkingBlocks. Adaptive
        # lets the model size its own reasoning per task; display is left at the
        # default (full) — never "summarized"/"omitted" — so the whole reasoning
        # trace streams to the UI (collapsible, not summarized away).
        thinking={"type": "adaptive"},
        add_dirs=add_dirs,
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


def _xml_leaf(tag: str, value: object) -> str:
    """One XML leaf, value JSON-encoded then XML-escaped (safe for dict/scalar)."""

    payload = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, sort_keys=True)
    return f"  <{tag}>{escape(payload)}</{tag}>"


def render_copilot_context_xml(skill_id: str, view: str, context: dict[str, Any]) -> str:
    """F4 4-layer resolver: render injected context as structured XML (not a flat
    JSON dump) so the model can attend to each layer separately.

    Layers: (1) skill basics, (2) current selection (node/edge), (3) lint/compile
    status, (4) explicit @mention content; any remaining keys go under <implicit>.
    Per-value truncation reuses ``_context_for_prompt`` so the >150K reference cap
    still applies. Empty layers are omitted.
    """

    capped = _context_for_prompt(context)
    layers: list[str] = [_xml_leaf("skill", {"id": skill_id, "view": view})]

    selection: list[str] = []
    node = capped.get("selected_node")
    if isinstance(node, dict):
        selection.append("    " + _xml_leaf("node", node).strip())
    edge = capped.get("selected_edge")
    if isinstance(edge, dict):
        selection.append("    " + _xml_leaf("edge", edge).strip())
    if selection:
        layers.append("  <selection>\n" + "\n".join(selection) + "\n  </selection>")

    lint = capped.get("lint_status")
    if lint is not None and lint != "idle":
        layers.append(_xml_leaf("lint_status", lint))

    mentions = capped.get("mentions")
    if mentions:
        layers.append(_xml_leaf("mentions", mentions))

    handled = {"selected_node", "selected_node_id", "selected_edge", "lint_status", "mentions"}
    implicit = {key: value for key, value in capped.items() if key not in handled and value is not None}
    if implicit:
        layers.append(_xml_leaf("implicit", implicit))

    return "<copilot_context>\n" + "\n".join(layers) + "\n</copilot_context>"


def build_system_prompt(skill_id: str) -> str:
    """Build the Copilot system prompt: skill-authoring brain + mounted-spec
    pointer + the latest view context (structured 4-layer XML)."""

    prompt = BASE_SYSTEM_PROMPT_TEMPLATE
    spec_dir = _skill_spec_dir()
    if spec_dir is not None:
        prompt += (
            f"\n\n## 已挂载 skill-spec(权威格式规范)\n{spec_dir}\n"
            "需要精确字段 / 语法 / 错误码时用 Read 查阅该目录下的 .md。"
        )

    view_context = get_view_context(skill_id)
    if view_context is not None:
        prompt += "\n\n## 当前上下文\n" + render_copilot_context_xml(
            skill_id, view_context.view, view_context.context
        )

    return prompt


def _context_resolved_event(
    skill_id: str,
    *,
    judge_context: dict[str, Any] | None = None,
) -> CopilotEventContextResolved:
    """F4: build the first-event echo of what context is injected this turn."""
    spec_mounted = _skill_spec_dir() is not None
    view_context = get_view_context(skill_id)
    parts: list[str] = []
    detail_lines: list[str] = []
    if view_context is not None:
        parts.append(f"view={view_context.view}")
        # Echo the exact structured XML that gets injected, so the user can verify
        # what the model actually receives (anti hidden-prompt-magic, F4).
        detail_lines.append(
            render_copilot_context_xml(skill_id, view_context.view, view_context.context)
        )
    else:
        detail_lines.append("(无 view 上下文)")
    if judge_context is not None:
        parts.append("judge context")
        detail_lines.append(render_copilot_judge_context_xml(judge_context))
    if spec_mounted:
        parts.append("skill-spec 已挂载")
    summary = "本轮注入: " + (" · ".join(parts) if parts else "仅 skill-authoring 基础上下文")
    return CopilotEventContextResolved(summary=summary, detail="\n".join(detail_lines))


def render_copilot_judge_context_xml(judge_context: dict[str, Any]) -> str:
    """Render Golden-owned judge facts as structured prompt context."""

    fields = (
        "compare_result_ref",
        "judge_context_ref",
        "baseline_ref",
        "diff_summary",
    )
    layers = [
        _xml_leaf(field, judge_context[field])
        for field in fields
        if judge_context.get(field) is not None
    ]
    return "<judge_context>\n" + "\n".join(layers) + "\n</judge_context>"


def _resolve_copilot_workspace_dir(
    skill_id: str,
    workspace_root: str | Path | None = None,
) -> Path:
    """Resolve the copilot CLI's cwd to the skill's workspace dir.

    Never falls back to the process CWD: in the packaged app the sidecar's CWD is
    the backend dir *inside the agent-harness repo*, so running the claude CLI
    there makes its `initialize` discover and try to start the repo's MCP servers
    / project settings — which hangs init until the SDK's control-request timeout.
    The skill workspace dir (under STUDIO_CONFIG_DIR) is clean of that config.
    """
    from app.core import config

    requested_workspace = _validate_requested_workspace_root(workspace_root)
    if requested_workspace is not None:
        registered_workspace = _registered_copilot_workspace_root(skill_id)
        if registered_workspace is not None:
            registered_resolved = registered_workspace.resolve(strict=False)
            if requested_workspace != registered_resolved:
                raise ValueError(
                    "workspace_root does not match registered workspace "
                    f"for skill {skill_id}: {requested_workspace}"
                )
            return requested_workspace
        if not _looks_like_copilot_workspace(requested_workspace):
            raise ValueError(
                "workspace_root is not a registered Studio workspace "
                f"for skill {skill_id}: {requested_workspace}"
            )
        return requested_workspace

    skills_root = config.default_workspace_skills_dir()
    skill_dir = skills_root / skill_id
    if skill_dir.is_dir():
        return skill_dir
    skills_root.mkdir(parents=True, exist_ok=True)
    return skills_root


def _validate_requested_workspace_root(workspace_root: str | Path | None) -> Path | None:
    if workspace_root is None:
        return None
    raw_workspace_root = str(workspace_root).strip()
    if not raw_workspace_root:
        return None
    candidate = Path(raw_workspace_root).expanduser()
    if not candidate.is_absolute():
        raise ValueError("workspace_root must be absolute")
    try:
        resolved = candidate.resolve(strict=True)
    except FileNotFoundError as exc:
        raise ValueError(f"workspace_root does not exist: {candidate}") from exc
    except OSError as exc:
        raise ValueError(f"workspace_root cannot be resolved: {candidate}") from exc
    if not resolved.is_dir():
        raise ValueError(f"workspace_root is not a directory: {candidate}")
    return resolved


def _registered_copilot_workspace_root(skill_id: str) -> Path | None:
    from app.core import config

    index_path = config.SKILL_INDEX_PATH
    if not index_path.exists():
        return None
    try:
        raw = json.loads(index_path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(raw, dict):
        return None
    entry = raw.get(skill_id)
    if not isinstance(entry, dict):
        return None
    absolute_path = entry.get("absolute_path")
    if not isinstance(absolute_path, str) or not absolute_path.strip():
        return None
    return Path(absolute_path).expanduser()


def _looks_like_copilot_workspace(path: Path) -> bool:
    return (
        (path / "GRAPH.md").is_file()
        or (path / "SKILL.md").is_file()
        or (path / ".workspace").is_dir()
    )


def _copilot_failure_summary(route_id: str, exc: Exception) -> str:
    return f"{route_id}: {type(exc).__name__}: {_safe_copilot_error_message(exc)}"


def _safe_copilot_error_message(exc: Exception) -> str:
    message = str(exc)
    return "[redacted]" if _contains_sensitive_error_text(message) else message


def _contains_sensitive_error_text(value: str) -> bool:
    lowered = value.lower()
    return any(
        marker in lowered
        for marker in (
            "secret",
            "api_key",
            "apikey",
            "authorization",
            "traceback",
            "token",
            "sk-",
        )
    )


async def stream_query(
    skill_id: str,
    user_message: str,
    model_override: str | None = None,
    workspace_dir: str | Path | None = None,
    role: str | None = None,
    workspace_root: str | Path | None = None,
    judge_context: dict[str, Any] | None = None,
) -> AsyncIterator[CopilotEvent]:
    """Stream one Copilot query using the selected copilot role (default
    copilot_chat) plus an optional finer-grained route override."""

    copilot_role = role or "copilot_chat"
    try:
        routes, credential_provider = _resolve_copilot_runtime(model_override, role=copilot_role)
    except KeyError as exc:
        yield CopilotEventError(message=f"未知模型: {exc}")
        return
    except CopilotRouteResolutionError as exc:
        yield CopilotEventError(
            message=_safe_copilot_error_message(exc),
            error_code=exc.error_code,
            error_payload=exc.error_payload,
        )
        return
    except ValueError as exc:
        yield CopilotEventError(message=_safe_copilot_error_message(exc))
        return

    try:
        resolved_workspace = (
            Path(workspace_dir).resolve(strict=False)
            if workspace_dir is not None
            else _resolve_copilot_workspace_dir(skill_id, workspace_root=workspace_root)
        )
    except ValueError as exc:
        yield CopilotEventError(message=_safe_copilot_error_message(exc))
        return

    # F4: first event echoes the injected context (anti hidden-prompt-magic).
    yield _context_resolved_event(skill_id, judge_context=judge_context)

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
                yield CopilotEventError(message=_safe_copilot_error_message(exc))
                return
            failures.append(_copilot_failure_summary(route.route_id, exc))
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
                workspace_dir=resolved_workspace,
            )
            await _ensure_client_connected(client)

            # F5: register the safe-write sink so the can_use_tool callback can
            # interleave patch_proposed / bash_approval_required events into this
            # query's stream, then drain translated messages + callback events
            # from one queue (preserving arrival order).
            queue: asyncio.Queue[CopilotEvent | object] = asyncio.Queue()
            _safe_write_sinks[skill_id] = _SafeWriteSink(
                queue=queue, workspace_root=resolved_workspace
            )
            consumer: asyncio.Task[None] | None = None
            try:
                await client.query(
                    _prompt_with_system_context(
                        skill_id,
                        user_message,
                        judge_context=judge_context,
                    )
                )
                consumer = asyncio.create_task(
                    _drain_sdk_response(client, tool_names, queue)
                )
                yielded_done = False
                while True:
                    event = await queue.get()
                    if event is _STREAM_SENTINEL:
                        break
                    typed_event = cast(CopilotEvent, event)
                    if isinstance(typed_event, CopilotEventDone):
                        yielded_done = True
                    yield typed_event
                if not yielded_done:
                    yield CopilotEventDone()
            finally:
                _safe_write_sinks.pop(skill_id, None)
                # Pending Bash approvals outlive the response stream so the UI can
                # resolve the approval card once. They are cleared by the approval
                # endpoint itself, reset_session, or cleanup_all_sessions.
                if consumer is not None and not consumer.done():
                    consumer.cancel()
                    try:
                        await consumer
                    except (asyncio.CancelledError, Exception):  # noqa: BLE001
                        pass
            return
        except Exception as exc:  # noqa: BLE001
            if len(routes) == 1:
                yield _error_event_for_exception(exc)
                return
            failures.append(_copilot_failure_summary(route.route_id, exc))
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
        message=_all_copilot_routes_failed_message(
            failures=failures,
            route_ids=[candidate.route_id for candidate in routes],
            failed_route_ids=failed_route_ids,
        )
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
        "error_type": type(error).__name__,
        "exception_type": type(error).__name__,
        "provider_error_type": type(error).__name__,
        "message": _safe_copilot_error_message(error),
    }
    if isinstance(status_code, int):
        payload["status_code"] = status_code
    return payload


def _all_copilot_routes_failed_message(
    *,
    failures: list[str],
    route_ids: list[str],
    failed_route_ids: list[str],
) -> str:
    payload = {
        "error_code": "resource.no_available_route",
        "route_ids": route_ids,
        "failed_route_ids": failed_route_ids,
    }
    suffix = f": {'; '.join(failures)}" if failures else ""
    return f"all configured Copilot providers failed ({json.dumps(payload, ensure_ascii=False)}){suffix}"


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

    session_key = _make_session_cache_key(
        skill_id,
        model_code,
        provider_code,
        api_key,
        workspace_dir,
    )
    async with _session_lock:
        session = _sessions.get(session_key)
        if session is None:
            session = _session_factory(
                build_options(
                    cast(str | None, base_url),
                    api_key,
                    workspace_dir,
                    env_overrides=env_overrides,
                    can_use_tool=_make_safe_write_can_use_tool(skill_id),
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
    if skill_id is None:
        _cleanup_pending_bash_approvals()
    else:
        _cleanup_pending_bash_approvals(skill_id)
    return len(sessions)


async def cleanup_all_sessions() -> None:
    """Close every cached SDK client, intended for application shutdown."""

    async with _session_lock:
        sessions = list(_sessions.values())
        _sessions.clear()

    _cleanup_pending_bash_approvals()
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


def _prompt_with_system_context(
    skill_id: str,
    user_message: str,
    *,
    judge_context: dict[str, Any] | None = None,
) -> str:
    prompt = build_system_prompt(skill_id)
    if judge_context is not None:
        prompt += "\n\n## Copilot Judge Context\n" + render_copilot_judge_context_xml(judge_context)
    return f"{prompt}\n\n## 用户消息\n{user_message}"


def _translate_sdk_message(message: object, tool_names: dict[str, str]) -> list[CopilotEvent]:
    if isinstance(message, AssistantMessage):
        return _translate_assistant_message(message, tool_names)
    if isinstance(message, UserMessage):
        # The SDK delivers tool RESULTS in UserMessage blocks, not AssistantMessage
        # — without this they'd be silently dropped (copilot would show "Reading…"
        # but never the result), violating F1 "不省略".
        return _translate_user_message(message, tool_names)
    if isinstance(message, ResultMessage):
        if message.is_error:
            details = "; ".join(message.errors or [])
            suffix = f": {details}" if details else ""
            return [CopilotEventError(message=f"SDK 返回错误{suffix}")]
        return [CopilotEventDone()]
    return []


def _translate_user_message(
    message: UserMessage, tool_names: dict[str, str]
) -> list[CopilotEvent]:
    content = message.content
    if not isinstance(content, list):
        return []
    events: list[CopilotEvent] = []
    for block in content:
        if isinstance(block, ToolResultBlock):
            events.extend(_tool_result_events(block, tool_names))
    return events


def _tool_result_events(
    block: ToolResultBlock, tool_names: dict[str, str]
) -> list[CopilotEvent]:
    tool_name = tool_names.get(block.tool_use_id, block.tool_use_id)
    result_summary = _tool_result_summary(block.content)
    if block.is_error:
        return [CopilotEventError(message=f"工具 {tool_name} 失败: {result_summary}")]
    return [
        CopilotEventToolUseResult(
            tool_name=tool_name,
            success=True,
            result_summary=result_summary,
        )
    ]


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
            events.extend(_tool_result_events(block, tool_names))
    return events


def _tool_result_summary(content: str | list[dict[str, Any]] | None) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    return json.dumps(content, ensure_ascii=False)


def _resolve_copilot_runtime(
    model_override: str | None,
    role: str = "copilot_chat",
) -> tuple[list[ResolvedRoute], CredentialProviderProtocol]:
    from app.core.adapters.gateway import RegistryResolutionError, ResourceTerminalError
    from app.services.gateway_resolver import build_gateway_route_runtime

    try:
        runtime = build_gateway_route_runtime(
            role,
            route_override=model_override,
        )
    except (ResourceTerminalError, RegistryResolutionError) as exc:
        # The gateway raises ResourceTerminalError (base Exception, NOT a
        # ValueError) when no copilot route resolves — e.g. the configured route
        # is missing/cooling-down. Left uncaught it propagates out of the ws
        # stream loop and the socket dies silently, so the user sees nothing.
        # Preserve the Gateway owner error code/payload while still surfacing a
        # readable message in the panel.
        error_code = getattr(exc, "error_code", "resource.no_available_route")
        error_payload = getattr(exc, "error_payload", None)
        if not isinstance(error_payload, dict):
            error_payload = {"role": role}
        raise CopilotRouteResolutionError(
            f"{role} 无可用 route: {exc}",
            error_code=error_code,
            error_payload=error_payload,
        ) from exc
    if not runtime.routes:
        raise CopilotRouteResolutionError(
            f"{role} role 无可用 route",
            error_code=runtime.error_code or "resource.no_available_route",
            error_payload=runtime.error_payload or {"role": role},
        )
    return runtime.routes, runtime.credential_provider


def _resolve_copilot_routes(
    model_override: str | None, role: str = "copilot_chat"
) -> list[ResolvedRoute]:
    routes, _credential_provider = _resolve_copilot_runtime(model_override, role=role)
    return routes


def _resolve_copilot_route(
    model_override: str | None, role: str = "copilot_chat"
) -> ResolvedRoute:
    return _resolve_copilot_routes(model_override, role=role)[0]


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
        return CopilotEventError(
            message=f"后端连接失败 (DeepSeek 端点不可达 / 大陆需代理): {_safe_copilot_error_message(exc)}"
        )
    return CopilotEventError(message=f"Copilot 请求失败: {_safe_copilot_error_message(exc)}")


# COPILOT_ASSIST-4: the copilot test must exercise the SAME path copilot uses at
# runtime and prove the tool loop. We write a RANDOM token into a temp file and
# ask the model to read it back — the model can only echo the token by actually
# running a tool to read the file, so the verdict is deterministic (not flaky):
# token echoed ⟺ spawn + env + tool loop all worked. (Tool *results* arrive in
# UserMessage blocks the translator drops, so we verify via the echoed token in
# the final answer rather than a tool-result event.)
SDK_TEST_TIMEOUT_S = 120.0
_SDK_TEST_FILE = "copilot_probe.txt"
_SDK_TEST_PROMPT = (
    f"Read the file {_SDK_TEST_FILE} in the current directory and reply with its "
    "exact contents verbatim, and nothing else."
)


def _sdk_test_token() -> str:
    return secrets.token_hex(8)


@dataclass(frozen=True)
class RouteSdkTestResult:
    """Outcome of a real ClaudeSDKClient tool-call test for one route.

    R-F21: ``"cooling_down"`` is a distinct outcome from ``"failed"`` — it means
    the upstream provider explicitly throttled us (429 / rate-limit), so the FE
    can render a gray light + countdown instead of pretending the route is
    broken. ``retry_after_seconds`` carries the suggested cooldown when known.
    """

    route_id: str
    status: Literal["ok", "failed", "cooling_down"]
    message: str | None = None
    retry_after_seconds: int | None = None


# R-F21: substrings observed in CLI subprocess error output that signal upstream
# throttling. Kept narrow to avoid false positives on unrelated 4xx surfaces.
_RATE_LIMIT_HINTS: tuple[str, ...] = (
    "rate limit",
    "rate_limit",
    "ratelimiterror",
    "rate-limit",
    "429",
    "too many requests",
)


def _is_rate_limit_error(exc: Exception) -> bool:
    """Heuristic: does the SDK/process error message look like a 429?

    The Claude Agent SDK wraps the CLI subprocess, so a provider 429 surfaces
    as a ``ProcessError`` / ``ClaudeSDKError`` whose ``str(exc)`` carries the
    upstream message. We pattern-match a few stable substrings rather than
    binding to an ``anthropic.RateLimitError`` class (anthropic SDK is not a
    direct dep — the CLI is the only consumer).
    """
    text = (str(exc) or "").lower()
    if any(hint in text for hint in _RATE_LIMIT_HINTS):
        return True
    # Some SDK errors expose an ``error_code`` attr from the CLI envelope.
    code_attr = getattr(exc, "error_code", None)
    if isinstance(code_attr, str) and any(hint in code_attr.lower() for hint in _RATE_LIMIT_HINTS):
        return True
    return False


def _retry_after_from_exception(exc: Exception) -> int | None:
    """Extract a ``Retry-After`` hint from the CLI error string, if present."""
    text = str(exc) or ""
    import re

    # Common shapes: "retry after 42s" / "retry-after: 42" / "in 42 seconds".
    match = re.search(r"retry[\s\-_]*after[^0-9]*(\d{1,5})", text, re.IGNORECASE)
    if match:
        try:
            value = int(match.group(1))
            return value if value > 0 else None
        except ValueError:
            return None
    match = re.search(r"in\s+(\d{1,5})\s*seconds?", text, re.IGNORECASE)
    if match:
        try:
            value = int(match.group(1))
            return value if value > 0 else None
        except ValueError:
            return None
    return None


async def run_route_sdk_test(
    route: ResolvedRoute,
    credential_provider: CredentialProviderProtocol,
    *,
    timeout_s: float = SDK_TEST_TIMEOUT_S,
) -> RouteSdkTestResult:
    """Drive the real ClaudeSDKClient for one route, forcing a real tool call.

    Spawns the same CLI-subprocess + ANTHROPIC_BASE_URL-env path copilot runs at
    runtime; passes only if the model echoes a random token it could only obtain
    by reading the probe file (proving the tool loop). Owns its client lifecycle
    locally (no global session teardown).
    """
    logger.info("phase=sdk_test action=start route=%s", route.route_id)
    try:
        api_key, base_url, env_overrides = _resolve_route_runtime(route, credential_provider)
    except ValueError as exc:
        logger.warning("phase=sdk_test route=%s config error: %s", route.route_id, exc)
        return RouteSdkTestResult(route.route_id, "failed", str(exc))
    if not api_key:
        return RouteSdkTestResult(
            route.route_id, "failed", f"Endpoint {route.endpoint_id} 未配置 API key"
        )

    with tempfile.TemporaryDirectory(prefix="copilot-sdk-test-") as workspace:
        token = _sdk_test_token()
        (Path(workspace) / _SDK_TEST_FILE).write_text(token, encoding="utf-8")
        options = build_options(base_url, api_key, workspace, env_overrides=env_overrides)
        client = _session_factory(options)
        try:
            async with asyncio.timeout(timeout_s):
                return await _drive_sdk_test(client, route.route_id, token)
        except Exception as exc:  # noqa: BLE001 — mapped to a clear message, not swallowed
            event = _error_event_for_exception(exc)
            # R-F21: a provider 429 / rate-limit surface should NOT light the
            # route red — it's a transient cooldown, not a broken route. We
            # detect it via a small substring heuristic on the wrapped CLI
            # error (anthropic SDK isn't a direct dep, so there's no concrete
            # `RateLimitError` class to bind to). Carries an optional retry-
            # after seconds field so the FE can render a countdown.
            if _is_rate_limit_error(exc):
                retry_after = _retry_after_from_exception(exc)
                logger.warning(
                    "phase=sdk_test route=%s cooling_down type=%s retry_after=%s: %s",
                    route.route_id,
                    type(exc).__name__,
                    retry_after,
                    event.message,
                )
                return RouteSdkTestResult(
                    route.route_id,
                    "cooling_down",
                    event.message,
                    retry_after_seconds=retry_after,
                )
            logger.warning(
                "phase=sdk_test route=%s failed type=%s: %s",
                route.route_id,
                type(exc).__name__,
                event.message,
            )
            return RouteSdkTestResult(route.route_id, "failed", event.message)
        finally:
            await _close_session(client)
            logger.info("phase=sdk_test action=end route=%s", route.route_id)


async def _drive_sdk_test(
    client: ClaudeSDKClient, route_id: str, token: str
) -> RouteSdkTestResult:
    tool_names: dict[str, str] = {}
    answer: list[str] = []
    errors: list[str] = []
    await _ensure_client_connected(client)
    await client.query(_SDK_TEST_PROMPT)
    async for message in client.receive_response():
        for event in _translate_sdk_message(message, tool_names):
            if isinstance(event, CopilotEventError):
                # Don't short-circuit: a mid-run tool error the model recovers
                # from shouldn't fail the test — the echoed token is the verdict.
                errors.append(event.message)
            elif isinstance(event, CopilotEventText):
                answer.append(event.content)
    if token in "".join(answer):
        return RouteSdkTestResult(route_id, "ok", None)
    if errors:
        logger.warning("phase=sdk_test route=%s errors: %s", route_id, errors[-1])
        return RouteSdkTestResult(route_id, "failed", errors[-1])
    return RouteSdkTestResult(
        route_id, "failed", "模型未真实读取文件 (token 未回显), tool loop 未验证"
    )


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
