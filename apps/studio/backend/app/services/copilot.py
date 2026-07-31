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
import os
import secrets
import shutil
import tempfile
from collections.abc import AsyncIterator, Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, cast
from xml.sax.saxutils import escape

from claude_agent_sdk import (
    AgentDefinition,
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
    HookCallback,
    HookContext,
    HookEvent,
    HookInput,
    HookJSONOutput,
    HookMatcher,
    McpServerConfig,
    ResultMessage,
    StreamEvent,
    SystemPromptPreset,
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
    ProviderRoute,
    ResolvedRoute,
    VerifiedProfile,
    apply_call_method_base_url,
    call_method_auth_token_env,
    call_method_client_compatibility,
    call_method_ids_for_client,
    call_method_ids_for_endpoint,
)
from app.core.adapters.transport_factory import build_gateway_adapter
from app.models.copilot import (
    CopilotEvent,
    CopilotEventContextResolved,
    CopilotEventDone,
    CopilotEventError,
    CopilotEventPatchProposed,
    CopilotEventText,
    CopilotEventThinking,
    CopilotEventToolApprovalRequired,
    CopilotEventToolUseResult,
    CopilotEventToolUseStart,
)
from app.services import agent_assets
from app.services.copilot_tools import build_copilot_mcp_servers

SessionKey = tuple[str, str, str]
SessionCacheKey = tuple[str, str, str, str]
logger = logging.getLogger(__name__)

_ALLOWED_TOOLS = ["Read", "Glob", "Grep", "Write", "Edit", "Bash", "Skill"]

COPILOT_SDK_SUPPORTED_METHOD_IDS = call_method_ids_for_client("anthropic_messages_client")

# 读/探测类 MCP 工具声明式直放(R8.1/R9.1/R10.2):由后端实现并自校验参数、
# 只读或只探测,天然安全。写/执行工具(配置真相:create/update/delete role ·
# endpoint/route 增删 · apply profile;skill 实体:create_skill;真实执行:
# run_skill)一律不在此列 —— 它们走 can_use_tool 挂起审批(实测:MCP 工具无
# Bash 式沙箱自动放行,移出白名单即触发 can_use_tool)。Write/Edit/Bash 同样
# 留在 "ask" 审批路径。
_DECLARATIVE_ALLOWED_TOOLS = [
    "Read",
    "Glob",
    "Grep",
    "mcp__studio__get_llm_roles",
    "mcp__studio__search_llm_registry",
    "mcp__studio__compile_skill",
    "mcp__studio__run_role_test",
    "mcp__studio__predict_skill",
    "mcp__studio__get_run_detail",
    "mcp__studio__test_llm_endpoint",
    "mcp__studio__test_llm_endpoint_models",
    "mcp__studio__probe_llm_route",
]

# 需审批的 MCP 写/执行工具(配置真相:凭据/路由/角色 + skill 实体 + 真实执行):
# 必须经事前审批,绝不进免审批白名单。命名与 copilot_tools.py 的 @tool 名一一
# 对应;can_use_tool 据此拦截并挂起。
_MCP_APPROVAL_WRITE_TOOLS = frozenset(
    {
        "mcp__studio__create_skill",
        "mcp__studio__run_skill",
        "mcp__studio__create_llm_role",
        "mcp__studio__update_llm_role",
        "mcp__studio__delete_llm_role",
        "mcp__studio__apply_model_profile_to_role",
        "mcp__studio__upsert_llm_endpoint",
        "mcp__studio__delete_llm_endpoint",
        "mcp__studio__update_llm_route",
        "mcp__studio__delete_llm_route",
    }
)

_WRITE_TOOL_ACTION_LABELS = {
    "mcp__studio__create_skill": "Create Skill",
    "mcp__studio__run_skill": "Run Skill",
    "mcp__studio__create_llm_role": "Create LLM Role",
    "mcp__studio__update_llm_role": "Update LLM Role",
    "mcp__studio__delete_llm_role": "Delete LLM Role",
    "mcp__studio__apply_model_profile_to_role": "Apply Model Profile to Role",
    "mcp__studio__upsert_llm_endpoint": "Upsert Provider Endpoint",
    "mcp__studio__delete_llm_endpoint": "Delete Provider Endpoint",
    "mcp__studio__update_llm_route": "Update Provider Route",
    "mcp__studio__delete_llm_route": "Delete Provider Route",
}
_WRITE_TOOL_REDACTED_KEYS = ("api_key",)


def _build_write_tool_approval_detail(
    tool_name: str, tool_input: Mapping[str, Any]
) -> str:
    """人机审批明细:工具动作标签 + 参数(敏感字段硬脱敏)。密钥明文绝不进入
    审批卡片渲染或日志(不变量 3)。"""

    clean: dict[str, Any] = dict(tool_input)
    for key in _WRITE_TOOL_REDACTED_KEYS:
        if clean.get(key):
            clean[key] = "******** (hidden)"
    label = _WRITE_TOOL_ACTION_LABELS.get(tool_name, tool_name)
    params = json.dumps(clean, ensure_ascii=False, indent=2, sort_keys=True)
    return f"Action: {label}\nParameters:\n{params}"


def _materialize_copilot_skills(workspace_dir: str | Path) -> list[str]:
    """把随包的场景技能(app/agents/skills)物化进 workspace 的 .claude/skills/,
    供 CLI 发现。

    每次会话创建都覆盖写(以随包版本为准,幂等);`.claude/` 是 Studio 的运行时
    供给目录,不属于 D12「skill 源文件唯一写者」管辖的 skills/ 用户源文件。"""

    names = agent_assets.skill_names()
    if not names:
        return []
    src_root = agent_assets.agents_dir() / "skills"
    dest_root = Path(workspace_dir) / ".claude" / "skills"
    for name in names:
        shutil.copytree(src_root / name, dest_root / name, dirs_exist_ok=True)
    return names


def _mounted_doc_dirs() -> list[tuple[str, Path]]:
    """挂载给 copilot 只读查阅的目录 —— 收敛为随包知识库一条(R4.4/4.5):
    契约事实全部在 knowledge/(KB-00 为路由入口),不再挂开发仓 docs
    (打包版没有它们,挂了也是静默消失的假依赖)。"""

    return [("graph_skill knowledge base (start at KB-00)", agent_assets.knowledge_dir())]


_sessions: dict[SessionCacheKey, ClaudeSDKClient] = {}
_session_lock = asyncio.Lock()
_session_factory: Callable[[ClaudeAgentOptions], ClaudeSDKClient] = ClaudeSDKClient
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


# ── F5 safe-write + 读护栏 + 挂起式审批 ─────────────────────────────────────
#
# The SDK consults ``can_use_tool`` only for tools NOT pre-allowed via
# ``allowed_tools`` (verified by PoC), so NOTHING is pre-allowed and every tool
# flows through the callback:
# - Write/Edit: workspace 圈定(出界拒绝) + ``patch_proposed`` diff 事件后放行。
# - Read/Glob/Grep: workspace + 挂载 spec 目录内直接放行;出圈挂起等用户审批。
# - Bash: 一律挂起等审批。批准 = callback 返回 Allow → CLI 自己执行,结果回到
#   模型上下文(旧「先拒绝 + 后端代跑」已删:代跑输出只到前端,模型看到的是
#   deny,断掉了基于结果的续推)。审批经 ``tool_approval_required`` 事件 →
#   前端卡片 → POST /copilot/tool-approval → resolve_tool_approval。
# The callback feeds events into the active query's queue via a per-skill
# registry — one active query per skill.


@dataclass
class _SafeWriteSink:
    queue: asyncio.Queue[CopilotEvent | object]
    workspace_root: Path


@dataclass(frozen=True)
class ToolApprovalResolution:
    """Outcome of resolving a held tool approval (no execution here — approval
    flows back into the awaiting ``can_use_tool`` and the CLI runs the tool
    itself, so its result lands in the model's context)."""

    tool_use_id: str
    approved: bool
    resolved: bool
    message: str | None = None


_safe_write_sinks: dict[str, _SafeWriteSink] = {}
_pending_tool_approvals: dict[tuple[str, str], asyncio.Future[bool]] = {}
# R7-I stop button: the skill's currently-streaming SDK client, set for the
# duration of one turn so the interrupt endpoint can call client.interrupt()
# (SDK-native) on it. Cleared when the turn ends (stream_query's finally).
_active_clients: dict[str, ClaudeSDKClient] = {}

_STREAM_SENTINEL = object()


def _cleanup_pending_tool_approvals(skill_id: str | None = None) -> int:
    """Deny-and-drop held tool approvals that no longer belong to a live session."""

    keys = [key for key in _pending_tool_approvals if skill_id is None or key[0] == skill_id]
    for key in keys:
        future = _pending_tool_approvals.pop(key, None)
        if future is not None and not future.done():
            future.set_result(False)
    return len(keys)


async def interrupt_active_query(skill_id: str) -> bool:
    """Interrupt the copilot's active streaming turn for a skill (R7-I stop button).

    Uses the SDK-native ``ClaudeSDKClient.interrupt()`` on the skill's currently
    streaming client. Returns False when no turn is active — a stop click after the
    turn already finished is a harmless no-op. The interrupted turn ends its stream,
    so the panel settles the message like any normal completion.
    """

    client = _active_clients.get(skill_id)
    if client is None:
        return False
    await client.interrupt()
    return True


async def _drain_sdk_response(
    client: ClaudeSDKClient,
    translator: SdkMessageTranslator,
    queue: asyncio.Queue[CopilotEvent | object],
) -> None:
    """Translate the SDK response stream onto the query queue, then close it.

    Module-level (not a per-query closure) so it binds its args explicitly — the
    can_use_tool callback feeds the same queue concurrently, and a sentinel marks
    end-of-stream so the generator stops draining.
    """

    try:
        async for sdk_message in client.receive_response():
            for event in translator.translate(sdk_message):
                await queue.put(event)
    finally:
        await queue.put(_STREAM_SENTINEL)

_SAFE_WRITE_OUTSIDE_WORKSPACE_MESSAGE = "Write/Edit target must stay inside the workspace"
# 审批可等待时限(R8.4):默认 30 分钟,可经环境变量调;超时 = 停任务保会话,
# 不再是静默拒绝后继续跑(deny-and-continue 会让 agent 拿超时当"用户拒绝"续推)。
_TOOL_APPROVAL_TIMEOUT_S = float(os.environ.get("STUDIO_TOOL_APPROVAL_TIMEOUT_S", "1800"))
_WRITE_CLASS_TOOLS = ("Write", "Edit", "MultiEdit", "NotebookEdit")
_WRITE_BOUNDARY_MATCHER = "|".join(_WRITE_CLASS_TOOLS)


def _is_under(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except (OSError, RuntimeError, ValueError):
        return False
    return True


def _write_boundary_violation(raw_path: str, workspace_root: Path) -> str | None:
    """硬边界规则(R8.2):写目标必须落在 workspace ∪ skills root,且显式排除
    llm/ 配置真相目录与 app_settings.json(排除项优先于白名单——即使白名单
    未来扩到 settings 目录,配置真相仍不可写)。返回违规原因,None = 合规。"""

    from app.core import config
    from app.core.paths import app_settings_path, default_skills_root

    target = Path(raw_path)
    if not target.is_absolute():
        target = workspace_root / target
    resolved = target.resolve(strict=False)
    settings_dir = Path(config.APP_SETTINGS_DIR).resolve(strict=False)
    if resolved == app_settings_path(settings_dir).resolve(strict=False) or _is_under(
        resolved, (settings_dir / "llm").resolve(strict=False)
    ):
        return (
            f"{raw_path} is LLM/app configuration truth; the copilot never writes it"
            " directly (use the config tools or the Settings UI)."
        )
    allowed_roots = (
        workspace_root.resolve(strict=False),
        default_skills_root(settings_dir).resolve(strict=False),
    )
    if any(_is_under(resolved, root) for root in allowed_roots):
        return None
    return f"{raw_path} is outside the write whitelist (workspace ∪ skills root)."


async def _bash_requires_approval_hook(
    raw_input: HookInput, tool_use_id: str | None, context: HookContext
) -> HookJSONOutput:
    """R8.3: Bash 一律走用户审批。CLI 对"安全只读命令"的沙箱自动放行会绕过
    can_use_tool(实测:`find | wc -l` 直接执行,审批卡片没出现)——这里用
    PreToolUse 的 "ask" 决策把每次 Bash 都压回权限流,由 can_use_tool 挂起
    等待前端审批卡片。"""

    del raw_input, tool_use_id, context
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "ask",
            "permissionDecisionReason": "Bash always requires user approval in Studio.",
        }
    }


def _make_write_boundary_hook(skill_id: str) -> HookCallback:
    """硬边界层 = PreToolUse hook(R8.2):每次工具调用必然触发,不受
    allowed_tools / acceptEdits 绕过(SDK 契约:can_use_tool 仅在权限规则判
    "ask" 时触发)。这消除了「Write 必须恒处 ask 态」的隐含不变量——即使
    Write 被误放进 allowed_tools,越界写仍被这里 deny。"""

    async def write_boundary_hook(
        raw_input: HookInput, tool_use_id: str | None, context: HookContext
    ) -> HookJSONOutput:
        del tool_use_id, context
        input_data = cast("dict[str, Any]", raw_input)

        def deny(reason: str) -> HookJSONOutput:
            return {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": reason,
                }
            }

        tool_name = str(input_data.get("tool_name", ""))
        if tool_name not in _WRITE_CLASS_TOOLS:
            return {}
        tool_input = input_data.get("tool_input") or {}
        raw_path = (
            tool_input.get("file_path")
            or tool_input.get("path")
            or tool_input.get("notebook_path")
        )
        sink = _safe_write_sinks.get(skill_id)
        if sink is None:
            return deny("no active session stream, write boundary cannot be resolved")
        if raw_path is None or not str(raw_path).strip():
            return deny(f"{tool_name} call carries no target path")
        violation = _write_boundary_violation(str(raw_path), sink.workspace_root)
        if violation is not None:
            logger.info(
                "phase=copilot_guardrail action=write_boundary_deny tool=%s path=%s",
                tool_name,
                raw_path,
            )
            return deny(violation)
        # 合规写不给 allow——留给正常权限流(ask → can_use_tool → patch 卡)。
        return {}

    return write_boundary_hook


async def _hold_for_tool_approval(
    skill_id: str,
    sink: _SafeWriteSink,
    *,
    tool_name: str,
    detail: str,
    tool_use_id: str,
) -> PermissionResultAllow | PermissionResultDeny:
    """挂起式审批:await 前端批复后才返回 Allow/Deny。批准 = 返回 Allow,由 CLI
    自己执行、结果回到模型上下文 —— 取代旧的「先拒绝 + 后端代跑」(代跑输出只到
    前端、模型永远看到 deny,是缺陷)。超时视为拒绝。"""

    if not tool_use_id:
        return PermissionResultDeny(
            message=(
                f"{tool_name} request is missing tool_use_id, so it cannot enter approval."
            ),
            interrupt=False,
        )
    future: asyncio.Future[bool] = asyncio.get_running_loop().create_future()
    _pending_tool_approvals[(skill_id, tool_use_id)] = future
    logger.info(
        "phase=copilot_guardrail action=approval_held tool=%s detail=%s", tool_name, detail
    )
    await sink.queue.put(
        CopilotEventToolApprovalRequired(
            tool_use_id=tool_use_id, tool_name=tool_name, detail=detail
        )
    )
    try:
        approved = await asyncio.wait_for(future, _TOOL_APPROVAL_TIMEOUT_S)
    except TimeoutError:
        # R8.4/8.5: 超时 = 停任务(interrupt)但保会话——用户回来直接续对话;
        # 不折算成"用户拒绝"让 agent 带着错误信号继续跑。
        message = (
            f"{tool_name} approval timed out after {int(_TOOL_APPROVAL_TIMEOUT_S)}s"
            " — task stopped, session preserved; send a new message to continue."
        )
        await sink.queue.put(
            CopilotEventError(message=message, error_code="tool_approval_timeout")
        )
        return PermissionResultDeny(message=message, interrupt=True)
    finally:
        _pending_tool_approvals.pop((skill_id, tool_use_id), None)
    if approved:
        return PermissionResultAllow()
    return PermissionResultDeny(message=f"User denied this {tool_name} call.", interrupt=False)


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
            if sink is None:
                return PermissionResultDeny(
                    message=(
                        "Bash requires user approval, but there is no active session stream."
                    ),
                    interrupt=False,
                )
            return await _hold_for_tool_approval(
                skill_id, sink, tool_name="Bash", detail=command, tool_use_id=tool_use_id
            )
        if tool_name in _MCP_APPROVAL_WRITE_TOOLS:
            # R10.2 (revised): writes (config truth: credentials/routes/roles;
            # skill entities: create_skill) are never zero-approval — they hold
            # for an explicit approval card before the CLI executes the tool, so
            # nothing is written pre-consent. The old zero-approval +
            # before/after undo path is deleted.
            if sink is None:
                return PermissionResultDeny(
                    message=(
                        f"{tool_name} requires user approval, but there is no active"
                        " session stream."
                    ),
                    interrupt=False,
                )
            return await _hold_for_tool_approval(
                skill_id,
                sink,
                tool_name=tool_name,
                detail=_build_write_tool_approval_detail(tool_name, tool_input),
                tool_use_id=tool_use_id,
            )
        return PermissionResultAllow()

    return can_use_tool


def resolve_tool_approval(
    skill_id: str,
    tool_use_id: str,
    *,
    approve: bool,
) -> ToolApprovalResolution:
    """Resolve a held Copilot tool call exactly once.

    只负责把批复喂给正在 await 的 ``can_use_tool``;批准后的执行由 CLI 自己完成,
    工具结果因此回到模型上下文(旧的后端代跑路径已删除)。"""

    future = _pending_tool_approvals.get((skill_id, tool_use_id))
    if future is None or future.done():
        return ToolApprovalResolution(
            tool_use_id=tool_use_id,
            approved=approve,
            resolved=False,
            message="approval_not_found",
        )
    future.set_result(approve)
    return ToolApprovalResolution(
        tool_use_id=tool_use_id,
        approved=approve,
        resolved=True,
        message=None,
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
    model: str | None = None,
    env_overrides: Mapping[str, str] | None = None,
    can_use_tool: Callable[[str, dict[str, Any], ToolPermissionContext], Any] | None = None,
    write_boundary_hook: HookCallback | None = None,
) -> ClaudeAgentOptions:
    """Build per-session Claude Agent SDK options without mutating os.environ.

    ``model`` is the selected route's ``provider_model_id`` — it reaches the CLI
    natively via ``ClaudeAgentOptions.model`` so EVERY route sends the right model
    (R7-H). None falls back to the CLI default; production always passes one.

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

    # 挂载收敛(R4.4/4.5):只剩随包知识库一条,KB-00 路由入口随手册进 append。
    add_dirs: list[str | Path] = [str(path) for _label, path in _mounted_doc_dirs()]
    permission_mode: Literal["default", "acceptEdits"]
    skills: list[str]
    mcp_servers: dict[str, McpServerConfig]
    agents: dict[str, AgentDefinition] | None
    hooks: dict[HookEvent, list[HookMatcher]] | None = None
    if can_use_tool is not None:
        # 读类三件 + 零审批 MCP 声明式直放(R8.1;这些不再进 can_use_tool);
        # Write/Edit/Bash 留在 "ask" 路径:白名单圈定 + 审批 UX 照旧。硬边界
        # 由 PreToolUse hook 承担(每次调用必触发,不受 allowed_tools 绕过)。
        allowed_tools = _DECLARATIVE_ALLOWED_TOOLS.copy()
        permission_mode = "default"
        # 场景技能白名单:只启用随包物化进 workspace/.claude/skills 的技能
        # (SDK 会自动配好 Skill 工具,types.py skills 文档)。
        skills = agent_assets.skill_names()
        mcp_servers = build_copilot_mcp_servers()
        agents = _goddess_agent_definitions()
        # R8.3: Bash 强制 "ask"(压掉 CLI 沙箱自动放行);R8.2: 写类硬边界。
        pre_tool_use = [HookMatcher(matcher="Bash", hooks=[_bash_requires_approval_hook])]
        if write_boundary_hook is not None:
            pre_tool_use.insert(
                0, HookMatcher(matcher=_WRITE_BOUNDARY_MATCHER, hooks=[write_boundary_hook])
            )
        hooks = {"PreToolUse": pre_tool_use}
    else:
        allowed_tools = _ALLOWED_TOOLS.copy()
        permission_mode = "acceptEdits"
        # SDK probe 路要确定性输出,压掉技能 / MCP / subagents(R6.6 裸配置)。
        skills = []
        mcp_servers = {}
        agents = None
    return ClaudeAgentOptions(
        cwd=workspace_dir,
        # R7-H: send the route's own model natively. Missing this made generic
        # (call_method_id=None) routes run on the CLI default (opus), so a non-opus
        # endpoint like deepseek got a model it doesn't serve and stalled.
        model=model,
        permission_mode=permission_mode,
        allowed_tools=allowed_tools,
        env=env,
        can_use_tool=can_use_tool,
        agents=agents,
        hooks=hooks,
        # 会话基座 = 完整 claude_code preset,MoirAI 资产以 append 叠加(R6.1;
        # 纯字符串会整体替换基座,是已定谳的缺陷用法);当前请求显式携带的上下文
        # 走每轮 turn prompt,见 _prompt_with_turn_context。
        system_prompt=_session_system_prompt(),
        # SDK 隔离模式:不加载开发机 ~/.claude 等文件系统配置,copilot 行为不随
        # 宿主机个人配置漂移;MCP 只认显式传入的(当前为空)。
        setting_sources=[],
        strict_mcp_config=True,
        skills=skills,
        mcp_servers=mcp_servers,
        # F1/F8: enable extended thinking so the SDK emits ThinkingBlocks.
        # Adaptive lets the model size its own reasoning per task. display MUST
        # be "summarized": the CLI only offers summarized|omitted (there is no
        # "full"), and leaving it unset strips the content — ThinkingBlocks
        # arrive with thinking="" and nothing ever reaches the UI (R5 root
        # cause, probe-verified 2026-07-02). With "summarized" the reasoning
        # also streams as thinking_delta stream events.
        thinking={"type": "adaptive", "display": "summarized"},
        # F8: without this the SDK only yields whole AssistantMessages, so the
        # panel gets the answer in one burst instead of token-level deltas.
        include_partial_messages=True,
        add_dirs=add_dirs,
    )


def _xml_leaf(tag: str, value: object) -> str:
    """One XML leaf, value JSON-encoded then XML-escaped (safe for dict/scalar)."""

    payload = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, sort_keys=True)
    return f"  <{tag}>{escape(payload)}</{tag}>"


def _session_system_prompt() -> SystemPromptPreset:
    """会话级 system prompt = 完整 claude_code preset + MoirAI 资产 append
    (moirai 角色 + 操作手册 + panel 表面薄层;KB-00 路由入口在手册里,R3.8)。

    只有当前请求显式携带的上下文会走 ``_prompt_with_turn_context`` 注入到
    当轮消息,绝不进会话级 —— 三层分离:基座+资产 / 链路装载 / 请求上下文。"""

    return {
        "type": "preset",
        "preset": "claude_code",
        "append": agent_assets.assemble_inline(
            ["roles/moirai.md", "operating-manual.md", "contexts/panel.md"]
        ),
    }


# 三女神 AgentDefinition 的职责一句话(description 供 MoirAI 判定派遣契合度;
# 台词层人格在 roles/*.md,这里只是调度语义)。
_GODDESS_DESCRIPTIONS = {
    "clotho": (
        "Designs what the skill should be: overall capability, domain analysis,"
        " node orchestration, and agent prompt design."
    ),
    "lachesis": (
        "Makes the skill real and runnable: engineering conventions, engine"
        " contracts, compile-clean guarantees, and the compile→predict"
        " diagnostic chain."
    ),
    "atropos": (
        "Judges finished work on real run evidence: final verdicts and"
        " feedback that flows back into the next iteration."
    ),
}

_GODDESS_TOOLS: dict[str, list[str]] = {
    "clotho": ["Read", "Glob", "Grep"],
    "lachesis": [
        "Read",
        "Glob",
        "Grep",
        "mcp__studio__compile_skill",
        "mcp__studio__predict_skill",
    ],
    "atropos": ["Read", "Glob", "Grep"],
}


def _goddess_agent_definitions() -> dict[str, AgentDefinition]:
    """三女神 = SDK 原生 subagents(R6.2/6.3)。prompt 运行于薄 harness 基座
    (spike 定谳,research §T6),因此带上自足的操作手册;model 不设,继承
    会话路由;skills 与 ah 路同源派生自 agent-skill-map.json(R5.5)。"""

    skill_map = agent_assets.load_skill_map()
    return {
        name: AgentDefinition(
            description=_GODDESS_DESCRIPTIONS[name],
            prompt=agent_assets.assemble_inline(
                [f"roles/{name}.md", "operating-manual.md"]
            ),
            tools=_GODDESS_TOOLS[name],
            skills=skill_map[name],
        )
        for name in ("clotho", "lachesis", "atropos")
    }


def _context_resolved_event(
    skill_id: str,
    *,
    judge_context: dict[str, Any] | None = None,
) -> CopilotEventContextResolved:
    """Build the first-event echo of explicit request context injected this turn."""
    del skill_id
    parts: list[str] = []
    detail_lines: list[str] = []
    if judge_context is not None:
        parts.append("judge context")
        detail_lines.append(render_copilot_judge_context_xml(judge_context))
    parts.append(f"assets@{agent_assets.assets_fingerprint()}")
    summary = "Injected this turn: " + " · ".join(parts)
    detail = "\n".join(detail_lines) if detail_lines else "(no request context)"
    return CopilotEventContextResolved(summary=summary, detail=detail)


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

    skills_root = config.DEFAULT_SKILLS_ROOT
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
        yield CopilotEventError(message=f"Unknown model: {exc}")
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
                yield CopilotEventError(message=f"Endpoint {route.endpoint_id} is missing an API key")
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

        translator = SdkMessageTranslator()
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
            # interleave patch_proposed / tool_approval_required events into this
            # query's stream, then drain translated messages + callback events
            # from one queue (preserving arrival order).
            queue: asyncio.Queue[CopilotEvent | object] = asyncio.Queue()
            _safe_write_sinks[skill_id] = _SafeWriteSink(
                queue=queue, workspace_root=resolved_workspace
            )
            # R7-I: expose this turn's streaming client so the interrupt endpoint
            # can stop it mid-flight; cleared in the finally when the turn ends.
            _active_clients[skill_id] = client
            consumer: asyncio.Task[None] | None = None
            try:
                await client.query(
                    _prompt_with_turn_context(
                        skill_id,
                        user_message,
                        judge_context=judge_context,
                    )
                )
                consumer = asyncio.create_task(
                    _drain_sdk_response(client, translator, queue)
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
                _active_clients.pop(skill_id, None)
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
            _materialize_copilot_skills(workspace_dir)
            session = _session_factory(
                build_options(
                    cast(str | None, base_url),
                    api_key,
                    workspace_dir,
                    model=model_code,
                    env_overrides=env_overrides,
                    can_use_tool=_make_safe_write_can_use_tool(skill_id),
                    write_boundary_hook=_make_write_boundary_hook(skill_id),
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
        _cleanup_pending_tool_approvals()
    else:
        _cleanup_pending_tool_approvals(skill_id)
    return len(sessions)


async def cleanup_all_sessions() -> None:
    """Close every cached SDK client, intended for application shutdown."""

    async with _session_lock:
        sessions = list(_sessions.values())
        _sessions.clear()

    _cleanup_pending_tool_approvals()
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


def _prompt_with_turn_context(
    skill_id: str,
    user_message: str,
    *,
    judge_context: dict[str, Any] | None = None,
) -> str:
    """Current turn prompt = explicit request context + user message."""

    layers: list[str] = []
    del skill_id
    if judge_context is not None:
        layers.append(
            "## Copilot Judge Context\n" + render_copilot_judge_context_xml(judge_context)
        )
    if not layers:
        return user_message
    return "\n\n".join(layers) + f"\n\n## 用户消息\n{user_message}"


def _result_error_detail(message: ResultMessage) -> str:
    """从 SDK ResultMessage 里挤出真实失败原因,让 "SDK 返回错误" 后面带上到底为什么 ——
    协议不匹配 / 404 / model 不存在等,而不是一句干巴巴的通用错。errors 空时退回
    result / api_error_status / subtype。"""
    errors = "; ".join(item for item in (message.errors or []) if item and item.strip())
    if errors:
        return errors
    parts: list[str] = []
    result = getattr(message, "result", None)
    if isinstance(result, str) and result.strip():
        parts.append(result.strip())
    status = getattr(message, "api_error_status", None)
    if status:
        parts.append(f"HTTP {status}")
    subtype = getattr(message, "subtype", None)
    if not parts and isinstance(subtype, str) and subtype.strip() and subtype != "error":
        parts.append(subtype)
    return " · ".join(parts)


class SdkMessageTranslator:
    """Stateful SDK→CopilotEvent translator for one query stream (F8).

    With ``include_partial_messages`` on, text/thinking arrive twice: first as
    ``StreamEvent`` token deltas, then again inside the complete
    ``AssistantMessage``. The translator streams the deltas immediately and
    remembers it did, so the complete message only contributes what the deltas
    cannot carry (tool_use blocks — their input exists only whole). A message
    that produced no deltas (no-stream provider) still emits its whole blocks,
    so heterogeneous anthropic-compat endpoints never lose content.
    """

    def __init__(self) -> None:
        self.tool_names: dict[str, str] = {}
        self._streamed_text = False
        self._streamed_thinking = False

    def translate(self, message: object) -> list[CopilotEvent]:
        if isinstance(message, StreamEvent):
            return self._translate_stream_event(message)
        if isinstance(message, AssistantMessage):
            return self._translate_assistant_message(message)
        if isinstance(message, UserMessage):
            # The SDK delivers tool RESULTS in UserMessage blocks, not
            # AssistantMessage — without this they'd be silently dropped
            # (copilot would show "Reading…" but never the result),
            # violating F1 "不省略".
            return self._translate_user_message(message)
        if isinstance(message, ResultMessage):
            if message.is_error:
                detail = _result_error_detail(message)
                suffix = f": {detail}" if detail else ""
                return [CopilotEventError(message=f"SDK returned an error{suffix}")]
            return [CopilotEventDone()]
        return []

    def _translate_stream_event(self, message: StreamEvent) -> list[CopilotEvent]:
        if message.parent_tool_use_id is not None:
            # Subagent stream — not part of the main transcript.
            return []
        raw = message.event
        if raw.get("type") != "content_block_delta":
            return []
        delta = raw.get("delta")
        if not isinstance(delta, dict):
            return []
        if delta.get("type") == "text_delta":
            text = delta.get("text")
            if isinstance(text, str) and text:
                self._streamed_text = True
                return [CopilotEventText(content=text)]
        elif delta.get("type") == "thinking_delta":
            thinking = delta.get("thinking")
            if isinstance(thinking, str) and thinking:
                self._streamed_thinking = True
                return [CopilotEventThinking(content=thinking)]
        # signature_delta / input_json_delta carry no UI-visible content.
        return []

    def _translate_user_message(self, message: UserMessage) -> list[CopilotEvent]:
        content = message.content
        if not isinstance(content, list):
            return []
        events: list[CopilotEvent] = []
        for block in content:
            if isinstance(block, ToolResultBlock):
                events.extend(self._tool_result_events(block))
        return events

    def _tool_result_events(self, block: ToolResultBlock) -> list[CopilotEvent]:
        # F8: a failed tool is a recoverable fact (the model usually works
        # around it) — transcribe it as success=False, never as
        # CopilotEventError, which is reserved for fatal stream-ending errors
        # (the frontend settles the message state machine on it).
        tool_name = self.tool_names.get(block.tool_use_id, block.tool_use_id)
        return [
            CopilotEventToolUseResult(
                tool_name=tool_name,
                success=not block.is_error,
                result_summary=_tool_result_summary(block.content),
            )
        ]

    def _translate_assistant_message(self, message: AssistantMessage) -> list[CopilotEvent]:
        streamed_text, self._streamed_text = self._streamed_text, False
        streamed_thinking, self._streamed_thinking = self._streamed_thinking, False
        events: list[CopilotEvent] = []
        for block in message.content:
            if isinstance(block, ThinkingBlock):
                # F1: stream the whole reasoning trace; the UI collapses but
                # never drops it. F8: skip when the deltas already streamed it.
                if block.thinking and not streamed_thinking:
                    events.append(CopilotEventThinking(content=block.thinking))
            elif isinstance(block, TextBlock):
                if not streamed_text:
                    events.append(CopilotEventText(content=block.text))
            elif isinstance(block, ToolUseBlock):
                # F8: transcribe every tool call by its real name — the SDK
                # executes read-only tools beyond the pre-allowed list
                # (Glob/Grep), and policy lives in the SDK options, not here.
                self.tool_names[block.id] = block.name
                events.append(
                    CopilotEventToolUseStart(
                        tool_name=block.name,
                        tool_input=block.input,
                    )
                )
            elif isinstance(block, ToolResultBlock):
                events.extend(self._tool_result_events(block))
        return events


def _tool_result_summary(content: str | list[dict[str, Any]] | None) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    # MCP 工具结果是内容块数组;纯文本块直接取正文拼接——否则前端拿到的是
    # `[{"type":"text","text":"{...}"}]` 包装层,变更卡片解析不到、气泡也难读。
    texts = [
        block.get("text")
        for block in content
        if isinstance(block, dict) and block.get("type") == "text"
    ]
    if texts and len(texts) == len(content) and all(isinstance(t, str) for t in texts):
        return "\n".join(cast("list[str]", texts))
    return json.dumps(content, ensure_ascii=False)


def resolved_route_has_copilot_sdk_method(route: ResolvedRoute) -> bool:
    return getattr(route, "call_method_id", None) in COPILOT_SDK_SUPPORTED_METHOD_IDS


def select_copilot_sdk_verified_profile(route: ProviderRoute) -> VerifiedProfile | None:
    supported_profiles = [
        profile
        for profile in route.verified_profiles
        if profile.status == "ready" and profile.method_id in COPILOT_SDK_SUPPORTED_METHOD_IDS
    ]
    if not supported_profiles:
        return None
    return sorted(
        supported_profiles,
        key=lambda profile: (not profile.default, profile.fallback_rank, profile.profile_id),
    )[0]


def resolved_route_with_verified_profile(
    route: ResolvedRoute,
    profile: VerifiedProfile,
) -> ResolvedRoute:
    updates = {
        "selected_profile_id": profile.profile_id,
        "selected_profile_capability": profile.capability,
        "call_method_id": profile.method_id,
        "request_mapper_id": profile.request_mapper_id,
    }
    model_copy = getattr(route, "model_copy", None)
    if callable(model_copy):
        return cast(ResolvedRoute, model_copy(update=updates))
    for key, value in updates.items():
        setattr(route, key, value)
    return route


def _resolved_route_with_call_method(route: ResolvedRoute, method_id: str) -> ResolvedRoute:
    updates = {"call_method_id": method_id}
    model_copy = getattr(route, "model_copy", None)
    if callable(model_copy):
        return cast(ResolvedRoute, model_copy(update=updates))
    route.call_method_id = method_id
    return route


def _copilot_sdk_candidate_method_id(route: ResolvedRoute) -> str | None:
    for method_id in call_method_ids_for_endpoint(
        getattr(route, "protocol", None),
        getattr(route, "base_url", None),
    ):
        if (
            method_id in COPILOT_SDK_SUPPORTED_METHOD_IDS
            and call_method_client_compatibility(method_id, "anthropic_messages_client")
            == "supported"
        ):
            return method_id
    return None


def resolved_route_with_copilot_sdk_candidate_method(route: ResolvedRoute) -> ResolvedRoute:
    if resolved_route_has_copilot_sdk_method(route):
        return route
    method_id = _copilot_sdk_candidate_method_id(route)
    if method_id is None:
        return route
    return _resolved_route_with_call_method(route, method_id)


def _prefer_copilot_sdk_profiles(routes: list[ResolvedRoute]) -> list[ResolvedRoute]:
    if all(resolved_route_has_copilot_sdk_method(route) for route in routes):
        return routes

    from app.services.llm_credentials import load_credentials

    credentials = load_credentials()
    prepared_routes: list[ResolvedRoute] = []
    for route in routes:
        if resolved_route_has_copilot_sdk_method(route):
            prepared_routes.append(route)
            continue
        stored_route = credentials.provider_routes.get(route.route_id)
        if stored_route is None:
            prepared_routes.append(route)
            continue
        selected_profile = select_copilot_sdk_verified_profile(stored_route)
        prepared_routes.append(
            resolved_route_with_verified_profile(route, selected_profile)
            if selected_profile is not None
            else resolved_route_with_copilot_sdk_candidate_method(route)
        )
    return prepared_routes


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
            f"{role} has no available route: {exc}",
            error_code=error_code,
            error_payload=error_payload,
        ) from exc
    if not runtime.routes:
        raise CopilotRouteResolutionError(
            f"{role} role has no available route",
            error_code=runtime.error_code or "resource.no_available_route",
            error_payload=runtime.error_payload or {"role": role},
        )
    return _prefer_copilot_sdk_profiles(list(runtime.routes)), runtime.credential_provider


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
        raise ValueError(f"Endpoint {route.endpoint_id} is missing an API key") from exc
    api_key = _secret_value(secret).strip()
    base_url = apply_call_method_base_url(route.call_method_id, route.base_url).strip() or None
    env_overrides: dict[str, str] = {}
    auth_token_env = call_method_auth_token_env(route.call_method_id)
    if auth_token_env:
        env_overrides[auth_token_env] = api_key
    return api_key, base_url, env_overrides


def _secret_value(secret: SecretStr | str) -> str:
    return secret.get_secret_value() if isinstance(secret, SecretStr) else secret


def _error_event_for_exception(exc: Exception) -> CopilotEventError:
    if isinstance(exc, TimeoutError):
        return CopilotEventError(message="Request timed out. Check network or proxy settings.")
    if isinstance(exc, (CLIConnectionError, ProcessError, ClaudeSDKError)):
        return CopilotEventError(
            message=(
                "Backend connection failed. Check endpoint reachability and proxy settings: "
                f"{_safe_copilot_error_message(exc)}"
            )
        )
    return CopilotEventError(message=f"Copilot request failed: {_safe_copilot_error_message(exc)}")


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
            route.route_id, "failed", f"Endpoint {route.endpoint_id} is missing an API key"
        )

    with tempfile.TemporaryDirectory(prefix="copilot-sdk-test-") as workspace:
        token = _sdk_test_token()
        (Path(workspace) / _SDK_TEST_FILE).write_text(token, encoding="utf-8")
        options = build_options(
            base_url,
            api_key,
            workspace,
            model=route.provider_model_id,
            env_overrides=env_overrides,
        )
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
    translator = SdkMessageTranslator()
    answer: list[str] = []
    errors: list[str] = []
    await _ensure_client_connected(client)
    await client.query(_SDK_TEST_PROMPT)
    async for message in client.receive_response():
        for event in translator.translate(message):
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
        route_id,
        "failed",
        "The model did not read the probe file (the token was not echoed), so the SDK tool loop was not verified.",
    )
