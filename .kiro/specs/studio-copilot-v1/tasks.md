# Studio Copilot V1 Backend Implementation Tasks

## 总览
- **Scope**: 仅 backend (`apps/studio/backend/**`)；界面实现由另一团队负责，不在本 tasks.md 范围。
- 总工时: **13.0h**，按 `design.md` §7 backend stage 重新合计；只保留 S0/S1/S2/S3/S6 backend 工作。
- Spec 依据: API 数据流见 `.kiro/specs/studio-copilot-v1/design.md:5`，Backend API 见 `.kiro/specs/studio-copilot-v1/design.md:39`，文件清单见 `.kiro/specs/studio-copilot-v1/design.md:136`，AC 见 `.kiro/specs/studio-copilot-v1/requirements.md:14`。
- Backend 文件边界: 重写 `apps/studio/backend/app/routers/copilot.py`、`apps/studio/backend/app/models/copilot.py`，新建 `apps/studio/backend/app/services/copilot.py`、`apps/studio/backend/app/services/copilot_credentials.py`。
- 当前 scaffold: `apps/studio/backend/app/routers/copilot.py:11` 已有 copilot router prefix；`apps/studio/backend/app/models/copilot.py:10` 仍是旧 dispatch schema，需要整体替换。
- 每个 sub-task 包含标题、路径、AC、估时、依赖和可独立 commit 标识；yes 表示完成后 backend pytest/mypy/ruff 应可通过。

## Stage S0: Claude Agent SDK base_url 前置验证 (0.5h)
- **S0 / T0.1: 验证 ClaudeSDKClient base_url 注入机制**
  - 路径: `apps/studio/backend/app/services/copilot.py` (新建前置调查)
  - AC: AC1, AC2 (`requirements.md:15`, `requirements.md:16`)
  - 估时: 0.5h
  - 依赖: 无
  - 可独立 commit: no
  - 实施细节: **这是整个 V1 的 hard prerequisite**，必须在所有其他 task 启动前完成，因为 base_url 是否支持决定整个 `services/copilot.py` 注入策略 (构造参数 vs contextvars)。验证步骤: (1) `pip show claude-agent-sdk` 看版本；(2) `python -c 'from claude_agent_sdk import ClaudeSDKClient; help(ClaudeSDKClient.__init__)'` 看构造参数列表；(3) 不支持时按 `design.md:53` 走 contextvars fallback。验证结论以注释 / NOTE 写到 `services/copilot.py` 头部。

## Stage S1: 基础设施配置 (2.0h)
- **T1.1 实现凭据文件读写 service**
  - 路径: `apps/studio/backend/app/services/copilot_credentials.py` (新建, ~60 lines)
  - AC: AC6 (`requirements.md:20`)
  - 估时: 0.9h
  - 依赖: T0.1
  - 可独立 commit: yes
  - 实施细节: 管理 `~/.studio/copilot.json`，schema 对齐 `design.md:89`；默认包含 claude/deepseek/gemini/openai 四个 key 槽位和 `active_backend`；写入使用临时文件 + atomic replace；创建/更新后强制 `chmod 600`；读文件不存在时返回安全默认值。

- **T1.2 暴露凭据读取与更新契约**
  - 路径: `apps/studio/backend/app/routers/copilot.py` (重写的一部分)
  - AC: AC1, AC2, AC3, AC6 (`requirements.md:15`, `requirements.md:16`, `requirements.md:17`, `requirements.md:20`)
  - 估时: 0.8h
  - 依赖: T1.1
  - 可独立 commit: yes
  - 实施细节: 实现 GET 脱敏 (返回 `has_key: bool`，不返明文 key)；实现 PUT (写文件 atomic + chmod 600)；切换 `active_backend` 或 PUT 凭据更新时主动调 `services/copilot.py` 的 `reset_session` 强制废弃旧 client；Gemini/OpenAI 仅保留占位状态，不进入可用路由。

- **T1.3 定义 backend 枚举与 credential response models**
  - 路径: `apps/studio/backend/app/models/copilot.py` (重写的一部分)
  - AC: AC1, AC2, AC6 (`requirements.md:15`, `requirements.md:16`, `requirements.md:20`)
  - 估时: 0.3h
  - 依赖: T1.1
  - 可独立 commit: yes
  - 实施细节: 定义 `CopilotBackend = Literal["claude", "deepseek", "gemini", "openai"]`、凭据读写 request/response models；所有 model 使用 `ConfigDict(extra="forbid")`，避免前后端契约漂移。

## Stage S2: Claude Agent SDK 接入 (5.0h)
- **T2.2 实现 backend 路由解析与 session key 策略**
  - 路径: `apps/studio/backend/app/services/copilot.py` (新建, session/routing 部分)
  - AC: AC1, AC2, AC3, AC12 (`requirements.md:15`, `requirements.md:16`, `requirements.md:17`, `requirements.md:26`)
  - 估时: 0.8h
  - 依赖: T0.1, T1.1
  - 可独立 commit: yes
  - 实施细节: Claude 使用默认 Anthropic endpoint；DeepSeek 使用 `https://api.deepseek.com/anthropic`，依据 `design.md:18` 和 `design.md:31`；session cache key 不只是 `(skill_id + active_backend)`，必须在 PUT credentials 时也提供显式 `invalidate(skill_id)` hook (或 key 中加 `api_key_hash` 派生字段)；同 backend 但 key 换了也要 reset；切 backend 丢弃旧 session，view context 更新不丢 history。

- **T2.3 实现普通 dict session manager 与 cleanup hook**
  - 路径: `apps/studio/backend/app/services/copilot.py`
  - AC: AC3, AC12 (`requirements.md:17`, `requirements.md:26`)
  - 估时: 0.8h
  - 依赖: T2.2
  - 可独立 commit: yes
  - 实施细节: 使用普通 `dict` 管理 session，禁止 `WeakValueDictionary`，按 `design.md:86`；提供 `reset_session(skill_id, backend)` 公共方法，给 `routers/copilot.py` 的 PUT credentials endpoint 调；并发访问用最小锁保护 session 创建；提供 app shutdown cleanup。

- **T2.4 构造 ClaudeAgentOptions 安全工作区与工具集**
  - 路径: `apps/studio/backend/app/services/copilot.py`
  - AC: AC8 (`requirements.md:22`)
  - 估时: 0.8h
  - 依赖: T2.2
  - 可独立 commit: yes
  - 实施细节: 设置 `ClaudeAgentOptions(cwd=<workspace_dir>, permission_mode="acceptEdits", allowed_tools=["Read", "Write", "Edit", "Bash"])`，对应 `design.md:51`；主控拍板为只依赖 SDK `cwd` 与 allowed_tools 限制，V1 不重写 Bash 校验。

- **T2.5 实现 system prompt 与自动 context 拼装**
  - 路径: `apps/studio/backend/app/services/copilot.py`
  - AC: AC10, AC11, AC12 (`requirements.md:24`, `requirements.md:25`, `requirements.md:26`)
  - 估时: 1.1h
  - 依赖: T2.2, T3.2
  - 可独立 commit: yes
  - 实施细节: base template 必须写明“聚焦 Studio 上下文，但允许任何通用问题，不要拒答”；每次 query 前读取 per-skill 当前 view context，并 prepend 到 system prompt 或 user message；view 切换只更新 context，不重启 session。

- **T2.6 转换 Claude SDK 流事件为 CopilotEvent 并处理错误**
  - 路径: `apps/studio/backend/app/services/copilot.py`
  - AC: AC1, AC2, AC8, AC10 (`requirements.md:15`, `requirements.md:16`, `requirements.md:22`, `requirements.md:24`)
  - 估时: 1.5h
  - 依赖: T2.4, T3.1
  - 可独立 commit: yes
  - 实施细节: 将文本增量映射为 `text_delta`；将 Read/Write/Edit/Bash 调用映射为 `tool_use_start/result`，schema 对齐 `design.md:54`；未配置 key、timeout、backend 不支持、tool failure 均转为 `error` event；DeepSeek usage 字段差异按 `design.md:167` 在 service 层兼容。

## Stage S3: WebSocket endpoint + CopilotEvent + POST /context (3.0h)
- **T3.1 定义 CopilotEvent union 与 context models**
  - 路径: `apps/studio/backend/app/models/copilot.py` (重写, ~60 lines)
  - AC: AC8, AC10, AC11 (`requirements.md:22`, `requirements.md:24`, `requirements.md:25`)
  - 估时: 0.7h
  - 依赖: T1.3
  - 可独立 commit: yes
  - 实施细节: 定义 `CopilotEventText`、`CopilotEventToolUseStart`、`CopilotEventToolUseResult`、`CopilotEventDone`、`CopilotEventError` 与 union，字段对齐 `design.md:55`；新增 context update request model `{ view, context, timestamp: int }`，timestamp 为毫秒级 epoch。

- **T3.2 实现 per-skill view context 缓存与压缩策略**
  - 路径: `apps/studio/backend/app/services/copilot.py`
  - AC: AC10, AC12 (`requirements.md:24`, `requirements.md:26`)
  - 估时: 0.8h
  - 依赖: T3.1
  - 可独立 commit: yes
  - 实施细节: 缓存 keyed by `skill_id` 的当前 view context；5KB 阈值用文件 byte size 判断。超阈值切 Reference 模式: (a) 必须保留完整 YAML frontmatter (从 `---` 到下一 `---` 之间全保留)；(b) 正文 (frontmatter 后内容) 截取前 300 字 (按字符数, UTF-8 安全)；(c) 末尾追加固定字符串 `[Content truncated due to length. Use 'Read' tool to inspect the full file: <absolute_file_path>]`。单元测试覆盖: 无 frontmatter / 单 frontmatter / frontmatter 本身就 > 5KB (此时整 frontmatter 也截断保 first 5KB-overhead)。

- **T3.3 实现 POST context endpoint**
  - 路径: `apps/studio/backend/app/routers/copilot.py` (重写, endpoint 部分)
  - AC: AC10, AC12 (`requirements.md:24`, `requirements.md:26`)
  - 估时: 0.5h
  - 依赖: T3.1, T3.2
  - 可独立 commit: yes
  - 实施细节: `POST /api/skills/{skill_id}/copilot/context` request body 字段包含 `timestamp: int` (毫秒级 epoch, 客户端发出时刻)；Backend 缓存 per-skill 当前 view context 时同时缓存 timestamp，收到新 POST 时若 `new.timestamp <= cached.timestamp` 则丢弃 (out-of-order, 防止防抖竞争下旧 context 覆盖新 context)；响应只确认 accepted/current summary，不启动 LLM query，不重启 session。

- **T3.4 实现 WebSocket endpoint 与 session reset 连接**
  - 路径: `apps/studio/backend/app/routers/copilot.py` (重写, websocket 部分)
  - AC: AC1, AC2, AC3, AC6, AC8, AC10, AC11, AC12 (`requirements.md:15`, `requirements.md:16`, `requirements.md:17`, `requirements.md:20`, `requirements.md:22`, `requirements.md:24`, `requirements.md:25`, `requirements.md:26`)
  - 估时: 1.0h
  - 依赖: T1.2, T2.3, T2.6, T3.3
  - 可独立 commit: yes
  - 实施细节: `/api/skills/{skill_id}/copilot/ws` 接收用户消息，调用 service async stream，并逐条 JSON 发送 `CopilotEvent`；handler 用 `try/except WebSocketDisconnect`，except 块内主动调 `reset_session(skill_id, current_backend)` 清理这个 session 防泄漏；WebSocketDisconnect 是 connection 异常断才 reset，用户主动 close V1 一律 reset，V1.5 看是否引入持久化 history 后区分；active backend 或同 backend key 更新时 reset session，context-only 更新不 reset。

## Stage S6: E2E smoke (2.5h, backend-only)
- **T6.1 跑通 Claude 真 key WebSocket smoke**
  - 路径: `apps/studio/backend/app/routers/copilot.py`, `apps/studio/backend/app/services/copilot.py`
  - AC: AC1, AC8, AC11 (`requirements.md:15`, `requirements.md:22`, `requirements.md:25`)
  - 估时: 0.5h
  - 依赖: T3.4
  - 可独立 commit: no
  - 验证细节: 手工执行，**不放 GitHub Action / 不写 pytest 自动化** (大陆网络代理差异 + 真 API 计费 + key 安全)，在实施 PR 描述里写时间戳 + backend + 测试命令 + 结论；使用本地 `~/.studio/copilot.json` Claude key，通过 WebSocket 发送一条通用问题和一条 Studio 上下文问题；确认收到 `text_delta` 与 `done`，无拒答。

- **T6.2 跑通 DeepSeek 真 key WebSocket smoke**
  - 路径: `apps/studio/backend/app/services/copilot.py`
  - AC: AC2, AC3, AC8 (`requirements.md:16`, `requirements.md:17`, `requirements.md:22`)
  - 估时: 0.5h
  - 依赖: T6.1
  - 可独立 commit: no
  - 验证细节: 手工执行，**不放 GitHub Action / 不写 pytest 自动化** (大陆网络代理差异 + 真 API 计费 + key 安全)，在实施 PR 描述里写时间戳 + backend + 测试命令 + 结论；切换 active backend 到 deepseek 后确认新 session 生效，DeepSeek base_url 命中兼容端点；若 usage 字段差异出现，补 service 层兼容后重跑。

- **T6.3 验证 view context 更新不重启会话**
  - 路径: `apps/studio/backend/app/services/copilot.py`
  - AC: AC10, AC12 (`requirements.md:24`, `requirements.md:26`)
  - 估时: 0.4h
  - 依赖: T3.3, T3.4
  - 可独立 commit: no
  - 验证细节: 手工执行，**不放 GitHub Action / 不写 pytest 自动化** (大陆网络代理差异 + 真 API 计费 + key 安全)，在实施 PR 描述里写时间戳 + backend + 测试命令 + 结论；先建立 WebSocket 会话，再连续 POST 两个不同 view context，下一条 query 应使用最新 context；session history 不清空。

- **T6.4 验证 tool_use 可读写临时 workspace 文件**
  - 路径: `apps/studio/backend/app/services/copilot.py`
  - AC: AC8 (`requirements.md:22`)
  - 估时: 0.6h
  - 依赖: T6.1
  - 可独立 commit: no
  - 验证细节: 手工执行，**不放 GitHub Action / 不写 pytest 自动化** (大陆网络代理差异 + 真 API 计费 + key 安全)，在实施 PR 描述里写时间戳 + backend + 测试命令 + 结论；在临时 workspace 创建测试文件，请 Copilot Read 后 Edit；确认 WebSocket 出现 `tool_use_start/result`，文件 diff 符合预期，且操作限定在 configured `cwd` 内。

- **T6.5 跑 backend 自动化回归验证**
  - 路径: `apps/studio/backend/app/models/copilot.py`, `apps/studio/backend/app/routers/copilot.py`, `apps/studio/backend/app/services/copilot.py`, `apps/studio/backend/app/services/copilot_credentials.py`
  - AC: AC1, AC2, AC3, AC6, AC8, AC10, AC11, AC12
  - 估时: 0.5h
  - 依赖: T6.1, T6.2, T6.3, T6.4
  - 可独立 commit: yes
  - 验证细节: 跑 backend pytest、mypy strict 对 backend app、ruff check；不需要真 key，不依赖网络，不放入 S6 手工 smoke 的 API 计费路径。

## 跨 stage 依赖矩阵
| Task | 必须依赖 | 可并行说明 |
|---|---|---|
| T0.1 | 无 | S0 hard prerequisite，最先做 |
| T1.1 | T0.1 | S1 根任务 |
| T1.2/T1.3 | T1.1 | 二者可并行 |
| T2.2/T2.3 | T0.1, T1.1 | session/routing 先于 SDK query |
| T2.4 | T2.2 | 可与 T3.1 并行 |
| T3.1 | T1.3 | 可与 T2.2/T2.4 并行 |
| T3.2/T3.3 | T3.1 | context service 先于 POST endpoint |
| T2.5 | T2.2, T3.2 | 需要 context 缓存 |
| T2.6 | T2.4, T3.1 | event schema ready 后实现 |
| T3.4 | T1.2, T2.3, T2.6, T3.3 | WebSocket 与 session reset 汇总点 |
| T6.1-T6.5 | S1/S2/S3 全部完成 | 只在最后做 smoke 和回归 |

## 实施 DAG (按依赖并行)
- **S0 prerequisite (顺序最优先)**: T0.1 base_url verify。
- **S1 layer (T0.1 done 后启动)**: T1.1 → (T1.2, T1.3 可并行)。
- **S2 layer (S1 done 后启动)**: T2.2 → (T2.3, T2.4 可并行) → T2.5 (依赖 T3.2) → T2.6 (依赖 T2.4 + T3.1)。
- **S3 layer (跟 S2 部分并行)**: T3.1 (跟 T2.2/T2.4 并行) → (T3.2 跟 T2.4 并行) → T3.3 → T3.4 (汇总 T1.2/T2.3/T2.6/T3.3)。
- **S6 layer (S1+S2+S3 全部 done 后)**: T6.1 → (T6.2, T6.3, T6.4 可并行) → T6.5 (回归)。
