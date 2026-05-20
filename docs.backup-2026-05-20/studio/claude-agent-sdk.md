# Claude Agent SDK Python — API Reference

> 本地落盘版本: 0.1.80 (Alpha)  
> Source: pip `claude-agent-sdk`, 由 Anthropic 维护  
> 官方文档: https://platform.claude.com/docs/en/agent-sdk/python  
> Last verified against installed: 2026-05-19  
> 本文只依据本仓库虚拟环境内已安装 SDK 与 bundled CLI 验证；未主动访问外网。

## 1. 安装 + Prerequisites

安装:

```bash
pip install claude-agent-sdk
```

本地包元数据:

| 项 | 值 | 本地依据 |
|---|---|---|
| 包名 | `claude-agent-sdk` | `.venv/lib/python3.12/site-packages/claude_agent_sdk-0.1.80.dist-info/METADATA:2` |
| 版本 | `0.1.80` | `.venv/lib/python3.12/site-packages/claude_agent_sdk-0.1.80.dist-info/METADATA:3` |
| 状态 | Alpha | `.venv/lib/python3.12/site-packages/claude_agent_sdk-0.1.80.dist-info/METADATA:12` |
| Python | `>=3.10` | `.venv/lib/python3.12/site-packages/claude_agent_sdk-0.1.80.dist-info/METADATA:21` |
| 依赖 | `anyio>=4.0.0`, `mcp>=1.19.0`, `sniffio>=1.0.0` | `.venv/lib/python3.12/site-packages/claude_agent_sdk-0.1.80.dist-info/METADATA:22-24` |
| bundled CLI | 包内自动包含 Claude Code CLI | `.venv/lib/python3.12/site-packages/claude_agent_sdk-0.1.80.dist-info/METADATA:57` |

CLI 查找顺序:

1. 优先使用包内 `_bundled/claude`。`SubprocessCLITransport._find_cli()` 先调用 `_find_bundled_cli()`，命中后直接返回。
2. 若没有 bundled CLI，再查找系统 `claude` 和常见安装路径。
3. 仍找不到则抛 `CLINotFoundError`，错误消息提示可用 `ClaudeAgentOptions(cli_path="/path/to/claude")` 指定路径。

本地依据: `.venv/lib/python3.12/site-packages/claude_agent_sdk/_internal/transport/subprocess_cli.py:81-112`。

本机 bundled CLI 检测:

```text
/home/sevenx/coding/agent-harness/.venv/lib/python3.12/site-packages/claude_agent_sdk/_bundled/claude
version: 2.1.138 (Claude Code)
```

`ClaudeAgentOptions.cli_path` 可覆盖默认 CLI 路径；字段定义见 `.venv/lib/python3.12/site-packages/claude_agent_sdk/types.py:1701-1705`。

## 2. 两种入口对比

| 入口 | 适合场景 | 是否支持 custom tools | 是否支持 hooks |
|---|---|---|---|
| `query()` async 函数 | 简单单轮、批处理、脚本化、CI；所有输入预先已知 | 否。不适合 in-process custom tools 的交互控制 | 否。不适合 hooks 控制流 |
| `ClaudeSDKClient` async context manager | 双向交互、长会话、聊天 UI、根据响应继续发消息、interrupt/session control | 是。通过 `@tool` + `create_sdk_mcp_server()` + `mcp_servers` | 是。`hooks` 由 client 转换并传入内部 Query |

依据:

- `query()` docstring 明确它是 one-shot/unidirectional/stateless/simple/no interrupts，并建议 stateful conversation 使用 `ClaudeSDKClient`: `.venv/lib/python3.12/site-packages/claude_agent_sdk/query.py:17-43`。
- `ClaudeSDKClient` docstring 明确它 bidirectional/stateful/interactive/support interrupts/session management: `.venv/lib/python3.12/site-packages/claude_agent_sdk/client.py:26-47`。
- README 明确 custom tools 和 hooks 是 `ClaudeSDKClient` 的额外能力: `.venv/lib/python3.12/site-packages/claude_agent_sdk-0.1.80.dist-info/METADATA:127-133`。

`query()` 最小例子:

```python
from claude_agent_sdk import query

async for message in query(prompt="What is 2 + 2?"):
    print(message)
```

`ClaudeSDKClient` 最小例子:

```python
from claude_agent_sdk import ClaudeSDKClient

async with ClaudeSDKClient() as client:
    await client.query("Summarize this project.")
    async for message in client.receive_response():
        print(message)
```

`ClaudeSDKClient.__aenter__` 会自动 `connect()`，`__aexit__` 会 `disconnect()`，见 `.venv/lib/python3.12/site-packages/claude_agent_sdk/client.py:619-626`。

## 3. ClaudeAgentOptions 完整字段表

字段定义从 `.venv/lib/python3.12/site-packages/claude_agent_sdk/types.py:1577-1931` 提取。默认值为 dataclass 默认值。

| 字段 | Type | 默认值 | 含义 / 例子 | 本地依据 |
|---|---|---|---|---|
| `tools` | `list[str] | ToolsPreset | None` | `None` | 指定可用 built-in tools 基础集合；`[]` 禁用 built-in tools；`{"type":"preset","preset":"claude_code"}` 使用默认 Claude Code 工具集。 | `types.py:1581-1590` |
| `allowed_tools` | `list[str]` | `[]` | 权限 allowlist，列出的工具自动批准；不是工具可见性控制。例: `["Read", "Bash(git *)"]`。 | `types.py:1592-1602` |
| `system_prompt` | `str | SystemPromptPreset | SystemPromptFile | None` | `None` | 三种系统提示词入口: 裸字符串、`claude_code` preset、文件。 | `types.py:1604-1612` |
| `mcp_servers` | `dict[str, McpServerConfig] | str | Path` | `{}` | MCP server 配置，或 MCP config JSON 文件路径。SDK server 类型为 `{"type":"sdk","name":...,"instance":...}`。 | `types.py:1614-1619`, `types.py:626-636` |
| `strict_mcp_config` | `bool` | `False` | 只使用 `mcp_servers` 传入的 MCP，忽略项目/用户/plugin 其他 MCP。映射 `--strict-mcp-config`。 | `types.py:1621-1626` |
| `permission_mode` | `PermissionMode | None` | `None` | `"default"`, `"acceptEdits"`, `"plan"`, `"bypassPermissions"`, `"dontAsk"`, `"auto"`。 | `types.py:23-26`, `types.py:1628-1636` |
| `continue_conversation` | `bool` | `False` | 继续当前目录最近会话；与 `resume` 互斥。 | `types.py:1638-1640` |
| `resume` | `str | None` | `None` | 指定 session ID 恢复历史。 | `types.py:1642-1643` |
| `session_id` | `str | None` | `None` | 指定会话 UUID；不能和 continue/resume 混用，除非 `fork_session`。 | `types.py:1645-1650` |
| `max_turns` | `int | None` | `None` | 最大对话轮数。 | `types.py:1652-1656` |
| `max_budget_usd` | `float | None` | `None` | 达到美元预算后停止。 | `types.py:1658-1663` |
| `disallowed_tools` | `list[str]` | `[]` | 明确禁用工具；从上下文移除且不可用。 | `types.py:1665-1670` |
| `model` | `str | None` | `None` | 模型名或 CLI 默认；例 `claude-sonnet-4-5`。 | `types.py:1672-1676` |
| `fallback_model` | `str | None` | `None` | 主模型失败或不可用时 fallback。 | `types.py:1678-1679` |
| `betas` | `list[SdkBeta]` | `[]` | SDK beta header；当前本地 type 只有 `context-1m-2025-08-07`。 | `types.py:28-29`, `types.py:1681-1689` |
| `permission_prompt_tool_name` | `str | None` | `None` | 将 permission request 路由给指定 MCP tool。 | `types.py:1691-1696` |
| `cwd` | `str | Path | None` | `None` | Claude Code 子进程工作目录；默认当前 Python 进程 cwd。 | `types.py:1698-1699` |
| `cli_path` | `str | Path | None` | `None` | Claude Code CLI 可执行文件路径；默认 bundled executable。 | `types.py:1701-1705` |
| `settings` | `str | None` | `None` | 额外 settings JSON 文件路径或 JSON 字符串；最高优先级 flag settings layer。 | `types.py:1707-1713` |
| `add_dirs` | `list[str | Path]` | `[]` | 允许 Claude 访问 cwd 之外的额外目录；应传绝对路径。CLI flag 是 repeatable `--add-dir`。 | `types.py:1715-1719` |
| `env` | `dict[str, str]` | `{}` | 传给 Claude Code 子进程的环境变量；可设 `CLAUDE_AGENT_SDK_CLIENT_APP` 标识应用。 | `types.py:1721-1726` |
| `extra_args` | `dict[str, str | None]` | `{}` | 透传未来 CLI 参数；`None` 表示 boolean flag。 | `types.py:1728-1733` |
| `max_buffer_size` | `int | None` | `None` | CLI stdout JSON 读取 buffer 最大字节数；默认 1MiB。 | `types.py:1735-1736`, `subprocess_cli.py:30` |
| `debug_stderr` | `Any` | `sys.stderr` | 已废弃，不再由 transport 读取；用 `stderr` callback。 | `types.py:1738-1739` |
| `stderr` | `Callable[[str], None] | None` | `None` | 接收 Claude Code stderr 行，用于日志/调试。 | `types.py:1741-1745` |
| `can_use_tool` | `CanUseTool | None` | `None` | 自定义权限处理器，只在权限规则评估为 ask 时触发；要观察所有工具调用用 `PreToolUse` hook。 | `types.py:1747-1757` |
| `hooks` | `dict[HookEvent, list[HookMatcher]] | None` | `None` | 注册各 hook 事件回调。 | `types.py:1759-1764` |
| `user` | `str | None` | `None` | 子进程 OS user 参数。 | `types.py:1766-1767`, `subprocess_cli.py:481` |
| `include_partial_messages` | `bool` | `False` | 输出 partial/streaming message event。 | `types.py:1769-1773` |
| `include_hook_events` | `bool` | `False` | 把 hook lifecycle event 作为 `HookEventMessage` 发到消息流。 | `types.py:1775-1781` |
| `fork_session` | `bool` | `False` | resume 时 fork 到新 session，而不是继续原 session。 | `types.py:1783-1785` |
| `agents` | `dict[str, AgentDefinition] | None` | `None` | 程序化定义 custom subagents，可由 Agent tool 调用。 | `types.py:1787-1791` |
| `setting_sources` | `list[SettingSource] | None` | `None` | 控制加载 user/project/local settings；`None` 加载全部，`[]` 禁用文件系统 settings；包含 `"project"` 才加载 CLAUDE.md。 | `types.py:1793-1803` |
| `skills` | `list[str] | Literal["all"] | None` | `None` | 主 session 启用 skills；设置后 SDK 自动 allow `Skill`/`Skill(name)` 并默认 setting_sources 为 user/project。 | `types.py:1805-1823`, `subprocess_cli.py:183-219` |
| `sandbox` | `SandboxSettings | None` | `None` | Bash sandbox 配置；文件/网络限制仍通过 permission rules 表达。 | `types.py:1825-1835` |
| `plugins` | `list[SdkPluginConfig]` | `[]` | 本地 plugin 目录；当前仅支持 `{"type":"local","path":...}`。 | `types.py:823-830`, `types.py:1837-1842` |
| `max_thinking_tokens` | `int | None` | `None` | 已废弃；用 `thinking`。 | `types.py:1844-1852` |
| `thinking` | `ThinkingConfig | None` | `None` | `adaptive` / fixed budget `enabled` / `disabled`。优先级高于 `max_thinking_tokens`。 | `types.py:1554-1574`, `types.py:1854-1865` |
| `effort` | `"low" | "medium" | "high" | "xhigh" | "max" | None` | `None` | 控制推理 effort，与 adaptive thinking 配合。 | `types.py:1867-1880` |
| `output_format` | `dict[str, Any] | None` | `None` | 结构化输出配置；`{"type":"json_schema","schema":...}` 映射 CLI `--json-schema`。 | `types.py:1882-1888`, `subprocess_cli.py:395-404` |
| `enable_file_checkpointing` | `bool` | `False` | 开启文件 checkpoint，配合 `ClaudeSDKClient.rewind_files()`。 | `types.py:1890-1896`, `client.py:370-400` |
| `session_store` | `SessionStore | None` | `None` | 将本地 transcript 镜像到外部 store，并支持 resume materialize。 | `types.py:1898-1904` |
| `session_store_flush` | `"batched" | "eager"` | `"batched"` | transcript mirror flush 策略。 | `types.py:1906-1914` |
| `load_timeout_ms` | `int` | `60000` | session store resume 时每次 `load()` / `list_subkeys()` 超时。 | `types.py:1916-1923` |
| `task_budget` | `TaskBudget | None` | `None` | API-side task token budget；映射 CLI `--task-budget`。 | `types.py:62-72`, `types.py:1925-1931` |

字段命名注意:

- 本地 SDK 字段名是 `setting_sources`，不是 `settings_sources`。
- 本地 SDK 字段名是 `add_dirs`，不是 `additional_directories`。

## 4. System Prompt 三种用法

`system_prompt` 支持三种形式，见 `.venv/lib/python3.12/site-packages/claude_agent_sdk/types.py:1604-1612`。

### 4.1 preset: Claude Code 默认 system prompt

```python
from claude_agent_sdk import ClaudeAgentOptions

options = ClaudeAgentOptions(
    system_prompt={
        "type": "preset",
        "preset": "claude_code",
    },
)
```

`SystemPromptPreset` 字段:

| 字段 | Type | 说明 | 本地依据 |
|---|---|---|---|
| `type` | `"preset"` | 固定值 | `types.py:35-39` |
| `preset` | `"claude_code"` | 使用 Anthropic bundled Claude Code 默认 prompt | `types.py:35-40` |
| `append` | `str` optional | 在默认 prompt 后追加指令；CLI 映射 `--append-system-prompt` | `types.py:40`, `subprocess_cli.py:235-238` |
| `exclude_dynamic_sections` | `bool` optional | 剥离 working directory、auto-memory、git status 等动态段以利于 prompt-caching；内容会重新注入首条 user message | `types.py:41-52` |

追加指令例子:

```python
options = ClaudeAgentOptions(
    system_prompt={
        "type": "preset",
        "preset": "claude_code",
        "append": "<skill_metadata>...</skill_metadata>",
        "exclude_dynamic_sections": True,
    },
)
```

CLI 行为:

- 如果 preset 带 `append`，SDK 传 `--append-system-prompt <append>`: `.venv/lib/python3.12/site-packages/claude_agent_sdk/_internal/transport/subprocess_cli.py:235-238`。
- `exclude_dynamic_sections` 不在 `_build_command()` 中变成 CLI flag，而是在 `ClaudeSDKClient` 初始化 Query 时作为 initialize 字段传入；旧 CLI 会忽略未知 initialize 字段: `.venv/lib/python3.12/site-packages/claude_agent_sdk/client.py:207-215`, `.venv/lib/python3.12/site-packages/claude_agent_sdk/client.py:224-237`。

### 4.2 file: 从文件加载 system prompt

```python
options = ClaudeAgentOptions(
    system_prompt={
        "type": "file",
        "path": "/absolute/path/to/system-prompt.md",
    },
)
```

`SystemPromptFile` 只有 `type: "file"` 与 `path: str`，见 `.venv/lib/python3.12/site-packages/claude_agent_sdk/types.py:55-60`。CLI 映射是 `--system-prompt-file <path>`，见 `.venv/lib/python3.12/site-packages/claude_agent_sdk/_internal/transport/subprocess_cli.py:232-235`。

### 4.3 裸 `str`: 完全自定义 prompt

```python
options = ClaudeAgentOptions(
    system_prompt="You are Studio Copilot. Follow the workspace file model.",
)
```

裸字符串映射 `--system-prompt <text>`，见 `.venv/lib/python3.12/site-packages/claude_agent_sdk/_internal/transport/subprocess_cli.py:227-231`。注意: 如果 `system_prompt is None`，SDK 会传 `--system-prompt ""`，见同一段源码。

### 4.4 Studio 渐进式披露最佳实践

对 Studio Copilot，不建议把全部上下文一次性塞进裸 `system_prompt`。推荐:

1. 使用 `claude_code` preset 保留默认 Claude Code 行为。
2. 用 `append` 放稳定的 Studio/Skill 元数据与全局规则。
3. 用首轮/后续 user message 按需注入 Layer 2-4 上下文。
4. 多轮交互用 `ClaudeSDKClient`，而不是 `query()`。

```python
options = ClaudeAgentOptions(
    cwd=workspace_root,
    system_prompt={
        "type": "preset",
        "preset": "claude_code",
        "append": render_layer_1_skill_metadata(skill),
        "exclude_dynamic_sections": True,
    },
    tools={"type": "preset", "preset": "claude_code"},
    allowed_tools=["Read", "Grep", "Glob"],
    permission_mode="dontAsk",
)
```

## 5. Tools (preset / custom)

### 5.1 ToolsPreset

```python
options = ClaudeAgentOptions(
    tools={"type": "preset", "preset": "claude_code"},
)
```

`ToolsPreset` 只有两个字段: `type: "preset"`、`preset: "claude_code"`，见 `.venv/lib/python3.12/site-packages/claude_agent_sdk/types.py:74-79`。

CLI 映射:

- `tools is None`: 不传 `--tools`，让 CLI 使用默认行为。
- `tools=[]`: 传 `--tools ""` 禁用 built-in tools。
- `tools=["Bash","Read"]`: 传 `--tools Bash,Read`。
- `tools={"type":"preset","preset":"claude_code"}`: 传 `--tools default`。

依据: `.venv/lib/python3.12/site-packages/claude_agent_sdk/_internal/transport/subprocess_cli.py:240-250`。

### 5.2 默认工具清单

本地 SDK README 只实证默认 Claude Code toolset 包含 `Read`, `Write`, `Edit`, `Bash`, and others，并说明完整清单应看 Claude Code documentation: `.venv/lib/python3.12/site-packages/claude_agent_sdk-0.1.80.dist-info/METADATA:99-101`, `.venv/lib/python3.12/site-packages/claude_agent_sdk-0.1.80.dist-info/METADATA:313-315`。

本地 `types.py` docstring/注释还出现以下 built-in tool 名称示例:

- `Bash`, `Read`, `Edit`: `.venv/lib/python3.12/site-packages/claude_agent_sdk/types.py:1581-1585`
- `Write`, `MultiEdit`, `Edit`: hook matcher 示例 `.venv/lib/python3.12/site-packages/claude_agent_sdk/types.py:587-590`
- `WebFetch`: sandbox permission rule 说明 `.venv/lib/python3.12/site-packages/claude_agent_sdk/types.py:880-883`
- `Skill`: skills 机制自动 allow 的工具名 `.venv/lib/python3.12/site-packages/claude_agent_sdk/_internal/transport/subprocess_cli.py:183-219`

常见 Claude Code 工具名通常包括 `Read`, `Write`, `Bash`, `Edit`, `MultiEdit`, `Grep`, `Glob`, `WebFetch`, `WebSearch`, `Task`, `TodoWrite`, `NotebookRead`, `NotebookEdit` 等；但这些完整名称没有在本地 Python SDK 源码内形成可引用的单一枚举。设计阶段若要做强校验，应调用 bundled CLI/官方工具文档或运行时 `/context`/server info，而不是硬编码本文这行。

### 5.3 Custom tools: `@tool` + in-process MCP

Custom tools 通过 SDK MCP server 暴露，不需要额外 subprocess。

依据:

- `@tool` 创建 `SdkMcpTool`，要求 handler 是 async，返回带 `content` 的 dict；错误可用 `is_error: True`: `.venv/lib/python3.12/site-packages/claude_agent_sdk/__init__.py:165-218`。
- `create_sdk_mcp_server()` 创建 in-process MCP server；同进程、无 IPC、可访问应用状态: `.venv/lib/python3.12/site-packages/claude_agent_sdk/__init__.py:306-377`。
- server 最终返回 `McpSdkServerConfig(type="sdk", name=name, instance=server)`: `.venv/lib/python3.12/site-packages/claude_agent_sdk/__init__.py:518-519`。

例子:

```python
from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKClient, create_sdk_mcp_server, tool

@tool("lookup_phase", "Read Studio phase metadata", {"phase_id": str})
async def lookup_phase(args):
    phase = load_phase(args["phase_id"])
    return {
        "content": [{"type": "text", "text": phase.to_markdown()}],
    }

studio_server = create_sdk_mcp_server(
    name="studio",
    version="1.0.0",
    tools=[lookup_phase],
)

options = ClaudeAgentOptions(
    mcp_servers={"studio": studio_server},
    allowed_tools=["mcp__studio__lookup_phase"],
)

async with ClaudeSDKClient(options=options) as client:
    await client.query("Use lookup_phase for planner.")
    async for msg in client.receive_response():
        print(msg)
```

### 5.4 `allowed_tools` + `permission_mode`

`allowed_tools` 是自动批准列表，不是工具可见性列表；要限制工具可见性用 `tools`，要禁用用 `disallowed_tools`。本地 README 对此有明确说明: `.venv/lib/python3.12/site-packages/claude_agent_sdk-0.1.80.dist-info/METADATA:99-101`。

`permission_mode` 值:

- `default`: 标准权限行为，危险操作会提示。
- `acceptEdits`: 自动接受文件编辑。
- `plan`: plan-only，不执行工具。
- `bypassPermissions`: 绕过所有权限检查。
- `dontAsk`: 不提示；未预批准则拒绝。
- `auto`: 模型分类器审批/拒绝工具调用。

值集合见 `.venv/lib/python3.12/site-packages/claude_agent_sdk/types.py:23-26`；`query()` docstring 解释见 `.venv/lib/python3.12/site-packages/claude_agent_sdk/query.py:54-62`。

## 6. Hooks 机制

Hook 是由 Claude Code application 调用的 Python 函数，不是模型自己调用。README 说明见 `.venv/lib/python3.12/site-packages/claude_agent_sdk-0.1.80.dist-info/METADATA:229-231`。

### 6.1 HookEvent 全清单

`HookEvent` literal 包含:

- `PreToolUse`
- `PostToolUse`
- `PostToolUseFailure`
- `UserPromptSubmit`
- `Stop`
- `SubagentStop`
- `PreCompact`
- `Notification`
- `SubagentStart`
- `PermissionRequest`

依据: `.venv/lib/python3.12/site-packages/claude_agent_sdk/types.py:257-269`。

### 6.2 HookMatcher

```python
from claude_agent_sdk import HookMatcher

HookMatcher(
    matcher="Bash",
    hooks=[check_bash_command],
    timeout=30,
)
```

字段:

| 字段 | Type | 默认 | 说明 |
|---|---|---|---|
| `matcher` | `str | None` | `None` | 工具名或组合表达式；例 `Bash`、`Write|MultiEdit|Edit` |
| `hooks` | `list[HookCallback]` | `[]` | Python async hook 函数 |
| `timeout` | `float | None` | `None` | 秒；默认 CLI/SDK 行为为 60s |

依据: `.venv/lib/python3.12/site-packages/claude_agent_sdk/types.py:582-598`。

### 6.3 Hook callback 和输出

Hook callback 签名:

```python
async def hook(input: HookInput, tool_use_id: str | None, context: HookContext) -> HookJSONOutput:
    ...
```

依据: `.venv/lib/python3.12/site-packages/claude_agent_sdk/types.py:562-579`。

Python 字段名注意:

- 使用 `async_`，SDK/CLI 会转换成 wire 字段 `async`。
- 使用 `continue_`，SDK/CLI 会转换成 wire 字段 `continue`。

依据: `.venv/lib/python3.12/site-packages/claude_agent_sdk/types.py:493-559`。

### 6.4 完整 deny example

```python
from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKClient, HookMatcher

async def deny_rm_rf(input_data, tool_use_id, context):
    if input_data["hook_event_name"] != "PreToolUse":
        return {}
    if input_data["tool_name"] != "Bash":
        return {}

    command = input_data["tool_input"].get("command", "")
    if "rm -rf" not in command:
        return {}

    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": "Studio blocks destructive rm -rf commands.",
        }
    }

options = ClaudeAgentOptions(
    allowed_tools=["Bash"],
    hooks={
        "PreToolUse": [
            HookMatcher(matcher="Bash", hooks=[deny_rm_rf]),
        ],
    },
)

async with ClaudeSDKClient(options=options) as client:
    await client.query("Run rm -rf /tmp/demo")
    async for message in client.receive_response():
        print(message)
```

本地 README 的 Bash deny 示例同样使用 `permissionDecision: "deny"` 与 `permissionDecisionReason`，见 `.venv/lib/python3.12/site-packages/claude_agent_sdk-0.1.80.dist-info/METADATA:237-279`。`PreToolUseHookSpecificOutput` 字段定义见 `.venv/lib/python3.12/site-packages/claude_agent_sdk/types.py:410-419`。

## 7. Subagent (`AgentDefinition`)

`AgentDefinition` 是 dataclass，字段见 `.venv/lib/python3.12/site-packages/claude_agent_sdk/types.py:81-100`。

| 字段 | Type | 默认 | 说明 |
|---|---|---|---|
| `description` | `str` | 必填 | agent 描述 |
| `prompt` | `str` | 必填 | agent system/prompt 指令 |
| `tools` | `list[str] | None` | `None` | 已废弃: 这里传 `"Skill"` 已 deprecated；用 `skills` |
| `disallowedTools` | `list[str] | None` | `None` | 禁用工具 |
| `model` | `str | None` | `None` | 模型 alias `sonnet`/`opus`/`haiku`/`inherit` 或完整 model ID |
| `skills` | `list[str] | None` | `None` | agent 可用 skills |
| `memory` | `"user" | "project" | "local" | None` | `None` | memory scope |
| `mcpServers` | `list[str | dict[str, Any]] | None` | `None` | server 名称或 inline `{name: config}` |
| `initialPrompt` | `str | None` | `None` | 初始 prompt |
| `maxTurns` | `int | None` | `None` | 最大 turn |
| `background` | `bool | None` | `None` | 后台 agent |
| `effort` | `"low" | "medium" | "high" | "xhigh" | "max" | int | None` | `None` | effort / thinking 深度 |
| `permissionMode` | `PermissionMode | None` | `None` | agent 权限模式 |

在 `ClaudeSDKClient` 中，`options.agents` 会经 `asdict()` 转为 dict 并在 initialize request 发送；不是 CLI flag。依据:

- 转换 agents: `.venv/lib/python3.12/site-packages/claude_agent_sdk/client.py:216-222`
- 传给 Query initialize: `.venv/lib/python3.12/site-packages/claude_agent_sdk/client.py:224-237`
- transport 注释写明 agents always sent via initialize request, no `--agents` CLI flag needed: `.venv/lib/python3.12/site-packages/claude_agent_sdk/_internal/transport/subprocess_cli.py:349-350`

例子:

```python
from claude_agent_sdk import AgentDefinition, ClaudeAgentOptions

options = ClaudeAgentOptions(
    agents={
        "studio-reviewer": AgentDefinition(
            description="Review Studio skill graph changes",
            prompt="Inspect the changed phase files and report risks first.",
            model="sonnet",
            skills=["code-review"],
            effort="high",
            permissionMode="dontAsk",
        )
    }
)
```

## 8. 错误类型

异常层级:

```text
ClaudeSDKError
├── CLIConnectionError
│   └── CLINotFoundError
├── ProcessError
├── CLIJSONDecodeError
└── MessageParseError
```

字段/行为:

| Error | 说明 | 特有字段 | 本地依据 |
|---|---|---|---|
| `ClaudeSDKError` | 所有 SDK error 基类 | 无 | `_errors.py:6-7` |
| `CLIConnectionError` | 无法连接/启动 Claude Code | 无 | `_errors.py:10-11` |
| `CLINotFoundError` | 未找到 CLI | 可带 `cli_path` 拼入 message | `_errors.py:14-22` |
| `ProcessError` | CLI process 失败 | `exit_code`, `stderr` | `_errors.py:25-39` |
| `CLIJSONDecodeError` | CLI 输出 JSON 解析失败 | `line`, `original_error` | `_errors.py:42-48` |
| `MessageParseError` | 消息解析失败 | `data` | `_errors.py:51-56` |

`SubprocessCLITransport` 在 CLI 返回非零 exit code 时会抛 `ProcessError`，见 `.venv/lib/python3.12/site-packages/claude_agent_sdk/_internal/transport/subprocess_cli.py:694-707`。

## 9. CLI 实际行为 (`subprocess_cli.py` 映射表)

`SubprocessCLITransport._build_command()` 起始命令固定为:

```text
<cli_path> --output-format stream-json --verbose
```

并最终追加 `--input-format stream-json`。依据: `.venv/lib/python3.12/site-packages/claude_agent_sdk/_internal/transport/subprocess_cli.py:221-225`, `.venv/lib/python3.12/site-packages/claude_agent_sdk/_internal/transport/subprocess_cli.py:406-408`。

| SDK option | CLI flag / behavior | 本地依据 |
|---|---|---|
| `system_prompt is None` | `--system-prompt ""` | `subprocess_cli.py:227-228` |
| `system_prompt: str` | `--system-prompt <text>` | `subprocess_cli.py:229-231` |
| `system_prompt {"type":"file"}` | `--system-prompt-file <path>` | `subprocess_cli.py:232-235` |
| `system_prompt {"type":"preset","append":...}` | `--append-system-prompt <append>` | `subprocess_cli.py:235-238` |
| `tools=[]` | `--tools ""` | `subprocess_cli.py:240-246` |
| `tools=["A","B"]` | `--tools A,B` | `subprocess_cli.py:243-248` |
| `tools preset claude_code` | `--tools default` | `subprocess_cli.py:248-250` |
| `allowed_tools` | `--allowedTools <comma-list>`，但先叠加 skills 默认 allow | `subprocess_cli.py:252-258` |
| `max_turns` | `--max-turns <n>` | `subprocess_cli.py:259-260` |
| `max_budget_usd` | `--max-budget-usd <amount>` | `subprocess_cli.py:262-263` |
| `disallowed_tools` | `--disallowedTools <comma-list>` | `subprocess_cli.py:265-266` |
| `task_budget` | `--task-budget <total>` | `subprocess_cli.py:268-269` |
| `model` | `--model <model>` | `subprocess_cli.py:271-272` |
| `fallback_model` | `--fallback-model <model>` | `subprocess_cli.py:274-275` |
| `betas` | `--betas <comma-list>` | `subprocess_cli.py:277-278` |
| `permission_prompt_tool_name` | `--permission-prompt-tool <name>` | `subprocess_cli.py:280-283` |
| `permission_mode` | `--permission-mode <mode>` | `subprocess_cli.py:285-286` |
| `continue_conversation` | `--continue` | `subprocess_cli.py:288-289` |
| `resume` | `--resume <id>` | `subprocess_cli.py:291-292` |
| `session_id` | `--session-id <uuid>` | `subprocess_cli.py:294-295` |
| `settings` + `sandbox` | `--settings <file-or-json>`，sandbox 会 merge 成 JSON | `subprocess_cli.py:129-181`, `subprocess_cli.py:297-300` |
| `add_dirs` | repeated `--add-dir <path>` | `subprocess_cli.py:302-305` |
| `mcp_servers` dict | `--mcp-config {"mcpServers":...}`；SDK server 会剥离 `instance` | `subprocess_cli.py:307-329` |
| `mcp_servers` path/string | `--mcp-config <value>` | `subprocess_cli.py:330-332` |
| `include_partial_messages` | `--include-partial-messages` | `subprocess_cli.py:334-335` |
| `include_hook_events` | `--include-hook-events` | `subprocess_cli.py:337-338` |
| `strict_mcp_config` | `--strict-mcp-config` | `subprocess_cli.py:340-341` |
| `fork_session` | `--fork-session` | `subprocess_cli.py:343-344` |
| `session_store` | `--session-mirror` | `subprocess_cli.py:346-347` |
| `setting_sources` | `--setting-sources=user,project,...` | `subprocess_cli.py:352-353` |
| `plugins` local | repeated `--plugin-dir <path>` | `subprocess_cli.py:355-361` |
| `extra_args` | `--flag` or `--flag <value>` | `subprocess_cli.py:363-370` |
| `thinking={"type":"adaptive"}` | `--thinking adaptive` | `subprocess_cli.py:372-378` |
| `thinking={"type":"enabled","budget_tokens":N}` | `--max-thinking-tokens N` | `subprocess_cli.py:378-380` |
| `thinking={"type":"disabled"}` | `--thinking disabled` | `subprocess_cli.py:380-381` |
| `thinking.display` | `--thinking-display <display>` | `subprocess_cli.py:383-386` |
| `max_thinking_tokens` | `--max-thinking-tokens <n>` | `subprocess_cli.py:387-390` |
| `effort` | `--effort <level>` | `subprocess_cli.py:392-393` |
| `output_format json_schema` | `--json-schema <schema-json>` | `subprocess_cli.py:395-404` |
| `enable_file_checkpointing` | env `CLAUDE_CODE_ENABLE_SDK_FILE_CHECKPOINTING=true` | `subprocess_cli.py:464-466` |
| `env` | merge 到子进程 env；SDK 设置 `CLAUDE_CODE_ENTRYPOINT=sdk-py` 和 `CLAUDE_AGENT_SDK_VERSION` | `subprocess_cli.py:423-436` |
| `cwd` | 子进程 `cwd=<cwd>` 且 env `PWD=<cwd>` | `subprocess_cli.py:468-480` |
| `stderr` callback | 仅注册 callback 时 pipe stderr | `subprocess_cli.py:471-494` |

## 10. Studio 渐进式 Copilot 集成参考片段

项目 spec 要求 Copilot 后端按渐进式披露组装 prompt:

- Layer 1 Always: Skill 基本信息。
- Layer 2 按需: 当前选中节点 detail。
- Layer 3 按需: 用户 `@` mention 的 nodes/files 内容。
- Layer 4 按需: Lint 状态 / Compile errors。

依据: `.kiro/specs/copilot-context-design/requirements.md:38-43`。research 还建议后端组装 `mentions`，前端只传结构化 payload，见 `.kiro/specs/copilot-context-design/research.md:26-29`, `.kiro/specs/copilot-context-design/research.md:56-60`。

### 10.1 数据结构建议

```python
from dataclasses import dataclass

@dataclass
class CopilotMention:
    type: str  # "file" | "phase" | "edge_context" | "system_error"
    id: str

@dataclass
class CopilotPayload:
    message: str
    active_skill_id: str
    selected_node_id: str | None
    mentions: list[CopilotMention]
    has_compile_errors: bool
```

### 10.2 Layer 1: preset + stable append

```python
from claude_agent_sdk import ClaudeAgentOptions, ToolsPreset

def build_options(payload: CopilotPayload, workspace_root: str) -> ClaudeAgentOptions:
    layer_1 = render_skill_metadata(payload.active_skill_id)
    return ClaudeAgentOptions(
        cwd=workspace_root,
        system_prompt={
            "type": "preset",
            "preset": "claude_code",
            "append": layer_1,
            "exclude_dynamic_sections": True,
        },
        tools={"type": "preset", "preset": "claude_code"},
        allowed_tools=["Read", "Grep", "Glob"],
        permission_mode="dontAsk",
        max_turns=8,
    )
```

### 10.3 Layer 2-4: 多 turn 按需注入

`ClaudeSDKClient.query()` 支持连接后继续发送 string prompt 或 AsyncIterable message，见 `.venv/lib/python3.12/site-packages/claude_agent_sdk/client.py:283-312`。因此 Studio 可以先以 Layer 1 初始化，再把 Layer 2-4 作为用户消息前置块注入。

```python
from claude_agent_sdk import ClaudeSDKClient

async def run_copilot(payload: CopilotPayload, workspace_root: str):
    options = build_options(payload, workspace_root)

    async with ClaudeSDKClient(options=options) as client:
        contextual_prompt = "\n\n".join(
            part for part in [
                render_selected_node(payload.selected_node_id),      # Layer 2
                render_mentions(payload.mentions),                   # Layer 3
                render_compile_errors() if payload.has_compile_errors else "",  # Layer 4
                payload.message,
            ] if part
        )

        await client.query(contextual_prompt)
        async for message in client.receive_response():
            yield message
```

### 10.4 用 custom tool 延迟读取大上下文

如果 mention 很多或文件很大，不要直接注入全文。可以把 mention manifest 注入 prompt，再提供 custom tool 让 Claude 按需读取。

```python
from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKClient, create_sdk_mcp_server, tool

@tool("read_mention", "Read one Studio mention by id", {"mention_id": str})
async def read_mention(args):
    content = read_mention_content(args["mention_id"])
    return {"content": [{"type": "text", "text": content}]}

server = create_sdk_mcp_server("studio-context", tools=[read_mention])

options = ClaudeAgentOptions(
    mcp_servers={"studio_context": server},
    allowed_tools=["mcp__studio_context__read_mention"],
    system_prompt={
        "type": "preset",
        "preset": "claude_code",
        "append": render_layer_1_skill_metadata(skill),
        "exclude_dynamic_sections": True,
    },
)
```

这符合 SDK custom tools 的 in-process MCP 模型，见 `.venv/lib/python3.12/site-packages/claude_agent_sdk/__init__.py:306-377`。

## 相关

- spec: `.kiro/specs/copilot-context-design/`
- bundled CLI 路径: `/home/sevenx/coding/agent-harness/.venv/lib/python3.12/site-packages/claude_agent_sdk/_bundled/claude`
- SDK exports: `.venv/lib/python3.12/site-packages/claude_agent_sdk/__init__.py:21-145`, `.venv/lib/python3.12/site-packages/claude_agent_sdk/__init__.py:522-560`
- 官方文档: https://platform.claude.com/docs/en/agent-sdk/python
