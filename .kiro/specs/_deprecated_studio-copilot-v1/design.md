# Studio Copilot V1 Design

## §1. 整体架构

**数据流：**
```text
[Frontend Studio (React/Tauri 常驻 side panel)]
   |
   | view 切换 → POST /api/skills/{skill_id}/copilot/context (update view context)
   | user message → WebSocket /api/skills/{skill_id}/copilot/ws
   v
[FastAPI Router]
   |
   | services/copilot.py 拼装 system prompt = base template + current view context
   | ClaudeSDKClient(base_url=<根据 active_backend>) query 流式回流
   v
[Backend Routing]
   +--- Claude → Anthropic API (默认 base_url)
   +--- DeepSeek → https://api.deepseek.com/anthropic (Anthropic 兼容)
   (Gemini / OpenAI: V1.5 才加, 那时引入 LiteLLM 子进程做协议转换)
```

**V1 设计原则:**
- **不嵌 LiteLLM** (DeepSeek 原生 Anthropic 兼容, 不需协议转换)。
- 切 backend = sidecar 重新构造 ClaudeSDKClient, session 重起。
- 前端 view 切换 = 后端 context 更新, **chat 历史保留**。

## §2. LiteLLM proxy 嵌入方案 (V1 不实施, V1.5 待办)

V1 砍掉 LiteLLM 子进程嵌入。理由:
- DeepSeek 提供原生 Anthropic 兼容端点 (`https://api.deepseek.com/anthropic`)，直切 base_url 即可。
- Claude API 默认 Anthropic，不需 proxy。
- LiteLLM 嵌入仅在引入 Gemini/OpenAI (协议转换) 时才必要。
- 砍掉 V1 LiteLLM 节省 ~2.5h 工时，留给 4 维度 UX 实现。

V1.5 引入 LiteLLM 时:
- 将设计子进程启动、random master_key 及 dynamic port（继承前期规划），当前版本不展开。

## §3. Backend (Python FastAPI) API 设计
**路由改造与新增：**
- **新 endpoint** `POST /api/skills/{skill_id}/copilot/context`：前端 view 切换时调用，body: `{ view: Literal[...], context: dict, timestamp: int }` (毫秒级 epoch)。Backend 缓存 per-skill 的 view context 与 timestamp，若收到新 POST 的 `timestamp <= cached.timestamp` 则丢弃（防止防抖竞争下旧 context 覆盖新 context）。
- **WebSocket Endpoint** `/api/skills/{skill_id}/copilot/ws`。
- **新 endpoint** `GET /api/copilot/credentials`：返回脱敏后的凭据状态。
  - 返回格式：`{backends: {claude: {has_key: bool}, deepseek: {has_key: bool}, gemini: {has_key: bool, V1_5_PLACEHOLDER: true}, openai: {has_key: bool, V1_5_PLACEHOLDER: true}}, active_backend: str}`。
- **新 endpoint** `PUT /api/copilot/credentials`：更新凭据或切换 active backend。
  - Body：`{backend: Literal["claude","deepseek","gemini","openai"], api_key: str | None, set_active: bool}`。
  - 逻辑：后端写入 `~/.studio/copilot.json` (atomic + chmod 600)，同时调用 `services/copilot.py` 的 `reset_session` 失效该 backend 当前所有 session。

**关键注记**：**后端是 `~/.studio/copilot.json` 的唯一写入路径**，前端禁止直接通过 Tauri FS API 写该文件（chmod 600 在前端权限不可靠）。前端读取也应优先走 GET endpoint 拿脱敏数据。

**WebSocket 消息流转流程：**
1. 获取当前 active_backend 的 `base_url` 与 `api_key`。
2. 拉取当前 view context (从 per-skill 缓存中读取)。
3. 拼装 system prompt = base template (要求业务聚焦 + 允许回答通用问题) + view context。
4. 调 `ClaudeSDKClient(base_url=..., system=...)` query。
5. 流式返回 `CopilotEvent`。

**关键配置与 SDK 注入：**
- **Tool use 启用**: 配置 `ClaudeAgentOptions(permission_mode='acceptEdits', allowed_tools=['Read', 'Write', 'Edit', 'Bash'])`。
- **base_url 注入**: `claude-agent-sdk` 内部通过 `SubprocessCLITransport` 启动 Claude Code CLI 子进程。`ClaudeAgentOptions` 提供了 `env: dict[str, str]` 参数，该字典会在拉起子进程时与继承的环境变量合并。因此，**必须通过 `ClaudeAgentOptions(env={"ANTHROPIC_BASE_URL": "...", "ANTHROPIC_API_KEY": "..."})` 进行注入**。这实现了安全的 per-invocation 隔离，绝不会污染全局 `os.environ`，也无需使用 Hacky 的 `contextvars` 机制。(挑刺 #1 修订, T0.1 verify 后)
- **WebSocket 事件补充**:
```python
from typing import Any, Literal, Union
from pydantic import BaseModel

class CopilotEventBase(BaseModel): pass

class CopilotEventText(CopilotEventBase):
    type: Literal["text_delta"] = "text_delta"
    content: str

class CopilotEventToolUseStart(CopilotEventBase):
    type: Literal["tool_use_start"] = "tool_use_start"
    tool_name: Literal["Read", "Write", "Edit", "Bash"]
    tool_input: dict[str, Any]  # 文件路径 / Bash 命令 / Edit diff

class CopilotEventToolUseResult(CopilotEventBase):
    type: Literal["tool_use_result"] = "tool_use_result"
    tool_name: str
    success: bool
    result_summary: str  # 给前端展示用 (例如 "Edited X.py: +5 -2 lines")

class CopilotEventDone(CopilotEventBase):
    type: Literal["done"] = "done"

class CopilotEventError(CopilotEventBase):
    type: Literal["error"] = "error"
    message: str

CopilotEvent = Union[CopilotEventText, CopilotEventToolUseStart, CopilotEventToolUseResult, CopilotEventDone, CopilotEventError]
```

**Session 缓存【修订 (挑刺 #5)】：**
- 必须使用普通的 `dict` 加上显式的 cleanup hook 进行管理（抛弃存在隐患的 `WeakValueDictionary`）。

## §4. 4 路 backend 配置 schema + 凭据存储
**配置文件结构 (`~/.studio/copilot.json`)：**
```json
{
  "backends": {
    "claude": { "api_key": "" },
    "deepseek": { "api_key": "" },
    "gemini": { "api_key": "", "V1_5_PLACEHOLDER": true },
    "openai": { "api_key": "", "V1_5_PLACEHOLDER": true }
  },
  "active_backend": "claude"
}
```
- **存储**：明文文件，由后端执行 `chmod 600` 保障基本安全。
- **权限边界**：**后端是该文件的唯一写入路径** (通过 `PUT /api/copilot/credentials` endpoint)，前端禁止直接写文件；读取走 `GET /api/copilot/credentials` endpoint 拿脱敏视图，禁止前端直接读文件（保障一致性并降低未来加密迁移成本）。

## §5. Frontend (React) UX

### §5.1 CopilotPanel 常驻 side panel
- **位置**: 右侧固定宽度 380px (左侧通常是项目导航, 右侧给 Copilot)。
- **挂载**: `App.tsx` 主布局区改为 `[main view] [CopilotPanel right]` 两栏。
- **panel 内容自上而下**:
  1. `ModelPicker` (顶部) — 4 卡位下拉 (Claude / DeepSeek / Gemini disabled / OpenAI disabled)。
  2. `ChatHistory` (中部, scrollable) — ChatBubble list。
  3. `MessageInput` (底部) — textarea + Send button。
  4. `SettingsButton` (右上角齿轮) — 弹 SettingsModal。

### §5.2 ChatBubble (含 tool_use 展示)
- `text_delta` → 流式 Markdown 渲染。
- `tool_use_start` → 显示 "🔧 正在 Read /path/to/file" / "✏️ 正在 Edit X.py" / "💻 正在跑 npm test"。
- `tool_use_result` → 显示 "✅ 已 Edit X.py (+5 -2 lines)" 或 "❌ 命令失败: ..."。
- `error` → 红色错误展示。

### §5.3 自动 context 注入 (view → context POST)
- **新建 hook** `useCopilotContext(viewName, viewState)`:
  - 监听 view 及其关键 state 的变化，防抖 500ms 后发起 `POST /api/skills/{skill_id}/copilot/context`。
  - Body 格式: `{ view, context, timestamp }`。
  - context 内容按 view 定义，如编辑 view 提供 `{ skill_md_text, phase_config_yaml }`，Compile view 提供 `{ compile_result, errors }`。

### §5.4 拆分 (沿用 Round 7 design §5 拆分)
在 `apps/studio/frontend/src/components/CopilotPanel/` 中新建：
1. `index.tsx` — 主容器 (~70 lines, 加 always-on 布局)。
2. `ModelPicker.tsx` — 模型下拉 (~80 lines)。
3. `ChatBubble.tsx` — 流式 + tool_use UI (~150 lines)。
4. `SettingsModal.tsx` — API key 配置 (~70 lines)。
5. `MessageInput.tsx` — 输入框 + Send (~50 lines)。
6. 在 `hooks/` 下新建 `useCopilotContext.ts` — view 监听 + context POST (~80 lines)。

## §6. 集成路径 (V1 文件改动清单)

| 路径 | 操作 | 大致行数 | 说明 |
|---|---|---|---|
| `apps/studio/backend/app/routers/copilot.py` | 重写 | ~120 | 提供 WebSocket、`/context` 及凭据 GET/PUT 端点 |
| `apps/studio/backend/app/models/copilot.py` | 重写 | ~80 | 定义 `CopilotEvent` union type、Context 更新及凭据 Schema |
| `apps/studio/backend/app/services/copilot.py` | 新建 | ~130 | Session dict 管理, base_url 注入, 拼装自动 Context |
| `apps/studio/frontend/src/components/CopilotPanel/index.tsx` | 新建 | ~70 | Copilot 主常驻容器 |
| `apps/studio/frontend/src/components/CopilotPanel/ModelPicker.tsx` | 新建 | ~80 | 4状态卡位控制 |
| `apps/studio/frontend/src/components/CopilotPanel/ChatBubble.tsx` | 新建 | ~150 | 流式 Markdown 渲染及 `tool_use` 展现 |
| `apps/studio/frontend/src/components/CopilotPanel/MessageInput.tsx` | 新建 | ~50 | 消息输入及发送逻辑 |
| `apps/studio/frontend/src/components/CopilotPanel/SettingsModal.tsx` | 新建 | ~70 | API Key 持久化配置界面 |
| `apps/studio/frontend/src/hooks/useCopilot.ts` | 新建 | ~80 | 维护 WebSocket 与会话数组 |
| `apps/studio/frontend/src/hooks/useCopilotContext.ts` | 新建 | ~80 | 视口变化监听与 Context 上报 |
| `apps/studio/frontend/src/App.tsx` | 改 | ~30 | 改写布局，新增右侧常驻 Panel 支持 |

## §7. 工作量重估 (主控给的目标 ~18h)
- S1 基础设施配置 (处理 `config.json` 读写及局部变量封装) — **2.0h**
- S2 Claude Agent SDK 接入 (base_url 构造参数 + Read/Write/Edit/Bash 工具开启 + tool_use 转发) — **5.5h**
- S3 WebSocket endpoint + CopilotEvent + 新 context POST endpoint — **3.0h**
- S4 Frontend (常驻 panel + 4+2 子文件 + tool_use UI + view hook) — **6.0h**
- S5 Settings Modal + 文件凭据 — **2.0h**
- S6 E2E smoke (Claude + DeepSeek + 验证 view 切换 context 更新 + 验证 tool_use 工作) — **2.5h**
- 减: S1 LiteLLM 子进程取消 — **-2.5h**
- **合计: 18.5h** (超 PM 原 16h 预算 2.5h，主控已拍板接受)

## §8. 真实风险 + 缓解 (V1 = 2 路 后)
1. **Claude SDK 局部变量注入失败 / 全局污染**
   - [证据 H] [影响 H] [置信度 A]
   - *风险*: 若不能通过构造参数，使用 `os.environ` 存在线程安全问题。
   - *方案*: a1 实施时严格检查并优先通过 `contextvars` 注入。
2. **DeepSeek 原生 Anthropic 接口字段缺失**
   - [证据 M] [影响 M] [置信度 B]
   - *风险*: DeepSeek 兼容端点若返回的 usage 字段存在差异，可能造成 Parser 异常。
   - *方案*: 在开发 S6 阶段进行实际调用，必要时在 `services/copilot.py` 中写中间件补齐。
3. **大陆网络限制 API 阻断**
   - [证据 H] [影响 H] [置信度 A]
   - *风险*: API 直连请求 Timeout。
   - *方案*: WebSocket 层抛出高辨识度 Error，提示用户配置代理。
4. **Tool use UI 信息密度 vs 渲染性能**
   - [证据 M] [影响 M] [置信度 B]
   - *风险*: `tool_use_start` / `result` event 流量大，导致 ChatBubble list 重渲染卡顿。
   - *方案*: ChatBubble 必须使用 `React.memo` 优化，长列表考虑按需开启虚拟化。
5. **自动 context 注入引发 prompt token 暴涨**
   - [证据 H] [影响 H] [置信度 A]
   - *风险*: PM 编辑大 `SKILL.md` (10KB+) 时，导致单次请求 Input Token 超 5K+，成本飙升。
   - *方案*: a1 实施时需在后端增加 View Context 大小阈值检测 (>2KB 时改 Reference 模式，仅附加文件路径和前 200 字摘要，让 Copilot 自己用 Read 工具去拉取)。
6. **Permission acceptEdits 安全风险**
   - [证据 H] [影响 H] [置信度 A]
   - *风险*: 自动接受 Edit 可能误改用户重要文件。
   - *方案*: V1 必须在 `services/copilot.py` 配置 SDK 时强制限定 `cwd` 为当前 Workspace (`~/.studio/workspaces/{current_workspace}/`)，禁止越权操作。且前端明确呈现 unified diff 给予反馈。