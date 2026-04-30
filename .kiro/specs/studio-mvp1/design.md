# Design Document

## 1. Overview & Goals / Non-Goals

本文档描述 Studio 下一个 MVP 阶段的架构与 API 接口设计。基于当前 `graph_agent` 的进展和 `mvp0` 现状，我们将**完全重写后端 (FastAPI)**，**深度重构前端 (React 19)**，并确立满足未来迭代的 Pydantic 数据契约与通信协议。

**Goals**:
- 规范化 API，消除前端正则解析债。
- 提供稳定的 WebSocket 流式反馈及终端交互能力。
- 设计覆盖 MVP1~MVP3 的全集 Pydantic 模型和错误码标准。

**Non-Goals**:
- 不实现真实的断点续跑和人工介入（仅定义接口，返回 501）。
- 不包含多租户鉴权体系和用户级文件隔离（P1.5）。
- 不提供画图节点的增删改拖拽（只读模式）。

## 2. Existing Architecture Analysis (mvp0 处置方案)

- **前端 (`studio-frontend/src/App.tsx`)**: 
  - **现状**: 界面底座（Tailwind、Lucide、ReactFlow）很完善，但数据层是“硬正则解析 Markdown”。
  - **处置**: **Refactor (重构)**。保留 UI 骨架，彻底剔除正则逻辑，对接 `GET /api/skills/{id}` 获取 `SkillManifest` JSON，动态渲染。保留 Monaco 编辑器，对接 `PUT` 接口保存。
- **后端 (`studio-backend/main.py`)**:
  - **现状**: 145 行的纯 Mock stub。
  - **处置**: **Rewrite (重写)**。引入工程化的 FastAPI 路由结构，集成真实的 `graph_agent` API，对接 `TraceCallback` 和真实的 subprocess `run_skill`。
- **graph_agent 引擎 & Phase 0**:
  - 已 merge: `SkillManifest` (Pydantic v2), `serialize_skill()` AST, `CallbackEvent` union。可以直接作为后端核心依赖消费。

## 3. Architecture Pattern

采用 **Ports & Adapters (Hexagonal)** 模式。
Studio Backend 作为 Adapter，不侵入 Engine 内部逻辑，严格消费以下暴露的 Port：
- `graph_agent.core.manifest.SkillManifest` (Pydantic model)
- `graph_agent.callbacks.events.CallbackEvent` (Discriminated Union)
- `graph_agent.api.run_skill` / `compile_skill` / `load_workflow_from_md`

### Data Flow Diagram
```mermaid
flowchart TD
    subgraph Browser
        UI[React SPA]
        RF[ReactFlow Graph]
        Monaco[Monaco Editor]
        XTerm[Terminal CLI]
    end
    
    subgraph Studio Backend (FastAPI)
        API[REST Routers]
        WS_Run[Run WS Manager]
        WS_Term[PTY Terminal Manager]
        FW[FileWatcher]
    end
    
    subgraph Engine (graph_agent)
        Runner[run_skill Subprocess]
        Compiler[compile_skill]
        Parser[Manifest Parser]
    end

    UI -- GET /api/skills/{id} --> API
    API -- Parse SKILL.md --> Parser
    Parser -- SkillManifest --> API
    API -- JSON --> RF
    
    Monaco -- PUT (Save) --> API
    API -- Trigger --> Compiler
    
    UI -- POST /run --> API
    API -- Spawn --> Runner
    Runner -- CallbackEvent 流 --> WS_Run
    WS_Run -- WS JSONL --> UI
    
    XTerm -- WS Byte Stream --> WS_Term
    WS_Term -- PTY / claude CLI --> FileSystem
    FileSystem -- Change Event --> FW
    FW -- WS Event --> UI
```

## 4. API Surface Specification (核心)

### 4.1 REST Endpoints 全表

| Method | Path | Request Pydantic | Response Pydantic | Error Codes | MVP Phase |
|---|---|---|---|---|---|
| GET | `/api/skills` | - | `list[SkillSummary]` | 500 | MVP1 |
| POST | `/api/skills` | `CreateSkillReq` | `SkillSummary` | 400, 500 | MVP1 |
| GET | `/api/skills/{id}` | - | `SkillDetail` | 404, 500 | MVP1 |
| PUT | `/api/skills/{id}` | `UpdateSkillReq` | `SkillDetail` | 400, 404, 422 | MVP1 |
| POST | `/api/skills/{id}/lint` | - | `LintResult` | 404 | MVP1 |
| POST | `/api/skills/{id}/runs` | `RunRequest` | `RunMetadata` | 400, 404, 500 | MVP1 |
| GET | `/api/skills/{id}/runs` | - | `list[RunMetadata]` | 404 | MVP1 |
| GET | `/api/skills/{id}/runs/{run_id}` | - | `RunDetail` | 404 | MVP1 |
| POST | `/api/skills/{id}/runs/{run_id}/resume`| `ResumeReq` | `RunMetadata` | 400, 404 | **MVP2** |
| POST | `/api/skills/{id}/terminal` | - | `TerminalSession` | 500 | MVP1 |
| GET | `/api/skills/{id}/test_inputs` | - | `list[TestInputMetadata]` | 404 | **MVP2** |
| POST | `/api/skills/{id}/test_inputs` | `multipart/form-data` | `TestInputMetadata` | 400 | **MVP2** |
| GET | `/api/skills/{id}/golden` | - | `list[GoldenBaseline]` | 404 | **MVP2** |
| POST | `/api/skills/{id}/golden` | `SetGoldenReq` | `GoldenBaseline` | 404 | **MVP2** |
| POST | `/api/skills/{id}/runs/{run_id}/compare` | - | `CompareResult` | 404 | **MVP2** |
| POST | `/api/skills/{id}/copilot/dispatch` | `CopilotDispatchReq` | `CopilotResponse` | 400, 500 | **MVP3** |
| GET | `/api/skills/{id}/runs/{run_id}/audit` | - | `AuditResult` | 404 | **MVP3** |

*Auth Note*: 从 P1.5 开始，所有接口要求 Header `X-Studio-User-ID`。

### 4.2 WebSocket Channels 全表

| Channel | Direction | Message Type / Payload Schema | Description |
|---|---|---|---|
| `/ws/runs/{run_id}` | Server -> Client | `CallbackEvent` (graph_agent engine 提供) | 引擎的执行事件流 |
| `/ws/runs/{run_id}` | Server -> Client | `{"type": "ask_human_input", "question": str}` | Agent Loop 暂停，请求人为输入 |
| `/ws/runs/{run_id}` | Client -> Server | `{"type": "human_input_response", "payload": dict}` | 用户通过 UI 提供的问答回复 |
| `/ws/terminal/{term_id}` | Bi-directional | Raw Binary/Text (bytes) | XTerm <-> PTY 字节透传 |
| `/ws/events` | Server -> Client | `{"type": "skill_changed", "skill_id": str}` | FileWatcher 发现文件变更通知 |

### 4.3 Data Contracts (Pydantic Models)

复用的 Engine 模型：`SkillManifest`, `PhaseConfig`, `CallbackEvent` (均直接使用 `graph_agent` 的 Pydantic v2 模型)。

Studio 专属 API 模型（包含字段及复用说明）：

```python
from pydantic import BaseModel
from typing import Any, Literal, Optional
from datetime import datetime

# Graph Agent 模型引用占位
# from graph_agent.core.manifest import SkillManifest
# from graph_agent.callbacks.events import CallbackEvent

class ErrorResponse(BaseModel):
    error_code: str
    http_status: int
    message: str
    details: dict[str, Any] | None = None
    retry_strategy: Literal["idempotent", "not_retryable", "backoff"]

class LintError(BaseModel):
    line: int | None = None
    column: int | None = None
    error_code: str
    severity: Literal["error", "warning"]
    message: str
    phase_name: str | None = None

class LintResult(BaseModel):
    status: Literal["passed", "failed"]
    errors: list[LintError]
    phases_summary: list[dict[str, Any]] | None = None  # name, tier, has_validator

class SkillSummary(BaseModel):
    id: str
    name: str
    description: str
    phase_count: int
    has_golden: bool
    last_run_at: datetime | None = None

class RunMetadata(BaseModel):
    run_id: str
    status: Literal["running", "success", "failed"]
    started_at: datetime
    metrics: "TokensMetrics | None" = None

class SkillDetail(BaseModel):
    manifest: "SkillManifest" # 直接复用 graph_agent.core.manifest.SkillManifest
    file_paths: dict[str, str] # SKILL.md 路径等
    has_golden: bool
    latest_run_metadata: RunMetadata | None = None

class CreateSkillReq(BaseModel):
    template_id: str | None = None
    description: str | None = None # 用于未来 Copilot 生成

class UpdateSkillReq(BaseModel):
    content: str # 完整的 SKILL.md 内容

class RunRequest(BaseModel):
    input_data: dict[str, Any] | None = None
    golden_id: str | None = None
    paste_json: str | None = None

class RunDetail(BaseModel):
    metadata: RunMetadata
    events: list["CallbackEvent"] # 复用 graph_agent.callbacks.events.CallbackEvent
    final_context: dict[str, Any] | None = None
    artifacts: list[str] | None = None

class ResumeReq(BaseModel):
    context_overrides: dict[str, Any] | None = None
    human_input: str | None = None

class TerminalSession(BaseModel):
    term_id: str
    ws_url: str
    cwd: str
    ttl_seconds: int

class TestInputMetadata(BaseModel):
    id: str
    name: str
    created_at: datetime
    size_bytes: int
    content_preview: str

class GoldenBaseline(BaseModel):
    id: str
    linked_input_id: str
    created_at: datetime
    locked: bool
    content_path: str

class SetGoldenReq(BaseModel):
    run_id: str
    lock: bool

class TokensMetrics(BaseModel):
    input_tokens: int
    output_tokens: int
    total_tokens: int
    cost_estimate: float | None = None

class CompareResult(BaseModel):
    differences: list[dict[str, Any]]
    score: float

class CopilotDispatchReq(BaseModel):
    target: Literal["gemini", "claude_code"]
    context: dict[str, Any]

class CopilotResponse(BaseModel):
    response_text: str

class AuditResult(BaseModel):
    drift_score: float
    violations: list[str]
```

### 4.4 System Flows

**Flow 1: Lint Flow**
```mermaid
sequenceDiagram
    participant PM
    participant UI as Studio UI
    participant API as Studio API
    participant Engine as graph_agent.compile_skill
    
    PM->>UI: 点击 [Lint]
    UI->>API: POST /api/skills/{id}/lint
    API->>Engine: compile_skill()
    alt Compile Success
        Engine-->>API: CompileResult
        API-->>UI: LintResult (status=passed, errors=[])
    else Compile/Validation Error
        Engine-->>API: CompileIssue / ValidationError
        API-->>UI: LintResult (status=failed, errors=List[LintError])
    end
    UI->>PM: 前端高亮 Monaco 行号，展示 Error Drawer
```

**Flow 2: Run Flow**
```mermaid
sequenceDiagram
    participant PM
    participant UI as Studio UI
    participant API as Studio API
    participant Subprocess as run_skill (隔离)
    participant Engine as graph_agent

    PM->>UI: 点击 [Run]
    UI->>API: POST /api/skills/{id}/runs (input_data)
    API->>Subprocess: spawn process / thread
    Subprocess->>Engine: harness.run()
    API-->>UI: {run_id: "..."}
    
    UI->>API: WebSocket /ws/runs/{run_id}
    
    loop Engine Execution
        Engine->>Subprocess: 发出 CallbackEvent
        Subprocess->>API: push to asyncio Queue
        API-->>UI: WS 流式推送单 consumer 保序
        UI->>PM: 渲染 Trace Timeline / Prompt Inspector 弹窗
    end
```

**Flow 3: Open CLI Flow**
```mermaid
sequenceDiagram
    participant PM
    participant UI as Studio UI
    participant API as Studio API
    participant PTY as ptyprocess
    participant CLI as claude
    participant FW as FileWatcher

    PM->>UI: 点击 [Open CLI]
    UI->>API: POST /api/skills/{id}/terminal
    API->>PTY: spawn (cwd=skill_dir, exec=claude)
    API-->>UI: {term_id, ws_url}
    
    UI->>API: WebSocket /ws/terminal/{term_id}
    
    loop Bi-directional Comm
        PM->>UI: 在 xterm.js 键入
        UI->>API: 字节流透传
        API->>PTY: stdin 写入
        PTY->>CLI: 执行
        CLI-->>PTY: stdout
        PTY-->>API: stdout 读取
        API-->>UI: 字节流返回 xterm.js
    end
    
    CLI->>FileSystem: 保存修改的 SKILL.md
    FileSystem->>FW: inotify 捕捉
    FW-->>API: 触发事件
    API-->>UI: WS `/ws/events` skill_changed
    UI->>PM: Toast 提示文件更新
```

**Flow 4: Dual-Track Edit Flow**
```mermaid
sequenceDiagram
    participant PM
    participant UI as Studio UI
    participant API as Studio API
    participant PTY as Terminal(CLI)
    participant FW as FileWatcher

    %% Track A
    PM->>UI: Monaco 修改并 Ctrl+S
    UI->>API: PUT /api/skills/{id}
    API->>FileSystem: 写入 SKILL.md
    API-->>UI: 返回最新 LintResult

    %% Track B
    PM->>PTY: claude CLI 编辑结构
    PTY->>FileSystem: 写入 SKILL.md
    FileSystem->>FW: inotify
    FW-->>API: 发现更新
    API-->>UI: WS 推送 skill_changed
    UI->>API: 重新 GET /api/skills/{id}
    API-->>UI: 渲染新拓扑
```

**Flow 5: Resume Flow**
```mermaid
sequenceDiagram
    participant PM
    participant UI as Studio UI
    participant API as Studio API
    participant Engine as graph_agent.harness
    participant Ckpt as LangGraph Checkpointer

    PM->>UI: 在 History 选中失败 Run
    PM->>UI: 修改部分 Context，点击 [Resume]
    UI->>API: POST /api/skills/{id}/runs/{run_id}/resume (context_overrides)
    API->>Engine: harness.resume(state, human_input, thread_id)
    Engine->>Ckpt: 拉取最近 valid state
    Ckpt-->>Engine: 还原状态
    Engine->>Engine: 应用 context_overrides
    Engine-->>API: 触发新事件流... (复用 WS 逻辑)
```

### 4.5 Error Code Standard

| Error Code | HTTP Status | When Raised | Retry Strategy |
|---|---|---|---|
| `SKILL_NOT_FOUND` | 404 | 请求不存在的 skill_id | `not_retryable` |
| `MANIFEST_VALIDATION_FAILED` | 422 | Pydantic `SkillManifest.model_validate()` 失败 | `not_retryable` (需修改文件) |
| `COMPILE_FAILED` | 200 (LintResult 中) | `compile_skill()` 业务规则失败，非系统错误 | `not_retryable` |
| `RUN_SPAWN_FAILED` | 500 | `run_skill` subprocess 或线程池拉起失败 | `idempotent` (可重试) |
| `TERMINAL_SPAWN_FAILED` | 500 | `ptyprocess` 无法初始化 CLI | `idempotent` |
| `WEBSOCKET_DISCONNECTED` | N/A (WS断开) | 客户端或服务端连接意外中断 | `backoff` (自动重连) |
| `LLM_FALLBACK_EXHAUSTED` | 502 | 所有配置的 provider 全部 down | `backoff` |
| `RESUME_CHECKPOINT_NOT_FOUND` | 404 | 提供 `run_id` 对应的 `thread_id` 在 DB 无记录 | `not_retryable` |

## 5. Technology Stack
- **Frontend**: React 19.2, Vite 8, ReactFlow 11.11, Monaco Editor 4.7, xterm.js 5.3, Tailwind 4.2.
- **Backend**: FastAPI 0.115, Uvicorn, Python 3.12.
- **Tools/Libs**: `ptyprocess` (Terminal proxy), `watchdog` (FileWatcher), `simpleeval` (When 表达式安全求值), `ruamel.yaml` (YAML round-trip).

## 6. Migration Strategy
mvp0 到新 MVP 的过渡策略：
1. **Frontend Refactor**: 
   - 彻底删除 `CustomNodes.tsx` 和其他地方的正则匹配 `SKILL.md` 逻辑。
   - 引入 SWR，基于 `/api/skills/{id}` 的 `SkillManifest` JSON 重写 ReactFlow 节点生成逻辑。
2. **Backend Rewrite**: 
   - 弃用现有的 `main.py` mock stub。
   - 按照标准分层（Routers, Services, Models）重写，直接 import `graph_agent` 的 `compile_skill` 等公开方法。
3. **SKILL.md 兼容性**: 无需专门 migration，`graph_agent` 核心引擎已处理了向上兼容，所有有效的业务 skill 都能被 `SkillManifest` 直接解析。

## 7. Future Considerations
后续功能的 API 扩展设计：
- **P1.5 用户隔离**: 在请求头引入 `X-Studio-User-ID`。不修改接口路径，后端通过依赖注入将其解析为文件系统工作区前缀 `workspaces/<uid>/skills/`。
- **MVP2 Golden Baseline & History**: 使用预留的 `/api/skills/{id}/golden` 获取基准数据。增加 `POST /api/skills/{id}/runs/{run_id}/compare` 接口实现输出与基准的差分比对。
- **MVP3 CCB Multi-Copilot**: 新增 `POST /api/skills/{id}/copilot/dispatch`，请求体包含 `{target: "gemini" | "claude_code", context: dict}`，让后端的 Terminal Manager 将意图分发给相应的 Copilot 引擎。
- **MVP3 Intent Drift Detection**: 新增 `GET /api/skills/{id}/runs/{run_id}/audit`，返回 `AuditResult`，包含根据 `plan_checklist` 和实际 `trace` 计算出的偏离度及详细指标。
