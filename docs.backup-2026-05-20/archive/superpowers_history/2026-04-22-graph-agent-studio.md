# Graph Agent Studio — Implementation Plan (P0 + P1 档位 A)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **Kiro spec**: `.kiro/specs/graph-agent-studio/{requirements,design,tasks,research}.md` 是权威决策源。本 plan 是可执行版本。

**Goal**: 把 graph_agent 的"契约地基"做干净 + 给 PM 上线最小可用 Web Studio（Lint / Run / Open CLI 三按钮），**不**自造 Copilot，借用 Claude Code CLI。

**Architecture**: 两部分 —
1. **Engine 地基（P0）**：单一 `SkillManifest` Pydantic 契约 + AST 反向序列化 + `CallbackEvent` 类型化 + Prompt Capture 埋点 + `Step.when` simpleeval + `ModelResolver` fallback
2. **Studio 档位 A（P1）**：FastAPI + React + 只读画布 + pty 终端桥接 Claude Code CLI

**Tech Stack**: Python 3.12+（engine 和 server）、Pydantic v2、simpleeval、ruamel.yaml、watchdog、FastAPI、uvicorn、ptyprocess、React 18、Vite、TypeScript、React Flow 11、xterm.js、Monaco (read-only)、Playwright（E2E）。

**Non-Goals（明确 out of scope）**: 完整 Copilot SDK 集成 / 画布 Topology 编辑 / SKILL.md 内嵌编辑 / Rust 重写 / Sandbox 容器化 / 版本管理 / Golden Dataset 对话录入。全部推迟到 P1.5 验证后决定。

---

## File Structure

```
# Engine 新增/改造
src/core/graph_agent/
├── core/
│   ├── manifest.py                  # 新增：SkillManifest Pydantic 契约
│   ├── parser.py                    # 改：喂 dict 给 SkillManifest
│   ├── loader.py                    # 改：引用 SkillManifest
│   ├── compiler.py                  # 改：在 Manifest 之上跑 rules.yaml
│   └── types.py                     # 改：Step/PhaseConfig 扩展 when/model_override
├── callbacks/
│   ├── events.py                    # 新增：CallbackEvent discriminated union
│   └── tracing.py                   # 改：落盘 tracing.jsonl
├── cognitive/
│   └── prompt.py                    # 改：emit PromptCapturedEvent
├── models/
│   └── resolver.py                  # 改：fallback 扩展 + LLMFallbackEvent
├── tools/
│   └── serialize.py                 # 新增：serialize_skill(manifest) 反向序列化
└── deerflow/skills/parser.py        # 删或改为引用 SkillManifest

# Studio 全新
studio/
├── server/
│   ├── __init__.py
│   ├── app.py                       # FastAPI 入口
│   ├── api/
│   │   ├── skills.py                # /api/skills/*
│   │   ├── run.py                   # /api/skills/{id}/run + WebSocket
│   │   └── terminal.py              # /api/skills/{id}/terminal + WebSocket
│   ├── services/
│   │   ├── skill_registry.py        # 扫描 skills/ 返回列表
│   │   ├── runner.py                # 子进程 run_skill
│   │   ├── terminal_mgr.py          # pty 会话管理
│   │   └── filewatcher.py           # watchdog 监听
│   ├── schemas.py                   # Response 模型
│   └── config.py                    # 配置：host/port/cli_cmd
├── web/
│   ├── package.json
│   ├── vite.config.ts
│   ├── src/
│   │   ├── main.tsx
│   │   ├── App.tsx
│   │   ├── pages/
│   │   │   ├── SkillsList.tsx       # Skill 列表 + 三按钮
│   │   │   └── SkillDetail.tsx      # 详情 + 画布 + Run / Terminal
│   │   ├── components/
│   │   │   ├── SkillGraph.tsx       # React Flow 只读
│   │   │   ├── DetailPanel.tsx      # 右侧 prompt/schema/...
│   │   │   ├── LintDrawer.tsx
│   │   │   ├── RunPanel.tsx
│   │   │   ├── TraceTimeline.tsx
│   │   │   ├── PromptInspector.tsx  # 三 tab 弹窗
│   │   │   └── TerminalPanel.tsx    # xterm.js
│   │   ├── lib/
│   │   │   ├── api.ts
│   │   │   ├── ws.ts
│   │   │   └── events.ts            # CallbackEvent 类型定义（从 Pydantic 生成）
│   │   └── styles/
│   └── index.html
└── tests/
    ├── server/
    │   ├── test_lint_api.py
    │   ├── test_run_api.py
    │   ├── test_terminal_api.py
    │   └── test_filewatcher.py
    └── e2e/
        ├── lint.spec.ts
        ├── run.spec.ts
        └── terminal.spec.ts

# Kiro spec 已落盘（参考源）
.kiro/specs/graph-agent-studio/
├── requirements.md
├── design.md
├── research.md
└── tasks.md

# 前置清理
.gitignore                           # 加入 .ccb/ *.pyc .studio_state/
```

---

## Source Code Reference Map

| Target | Source File | Key Logic |
|---|---|---|
| `core/manifest.py` | `core/parser.py` 既有 schema + CHANGELOG 描述的 4 份校验 | 合并为单一 Pydantic v2 模型 |
| `tools/serialize.py` | `tools/md_to_json.py`（正向） | 反向：manifest → 格式化 Markdown，ruamel.yaml round-trip |
| `callbacks/events.py` | `callbacks/` 现有 14 钩子 | 抽象成 discriminated union 的 payload 子类 |
| `cognitive/prompt.py` | 现有 prompt 组装代码 | 在 LLM 调用前 emit 三元组事件 |
| `models/resolver.py` | 现有 provider failover 逻辑 | 扩展 emit `LLMFallbackEvent`，同级别模型配对 |
| `studio/server/app.py` | — | 全新 |
| `studio/web/*` | — | 全新 |

---

## Phase 0: Engine 地基

### Task 0.1: 新建 `SkillManifest` Pydantic 契约

**Files:**
- Create: `src/core/graph_agent/core/manifest.py`
- Create: `tests/core/test_manifest.py`

**Why**: 4 处校验逻辑合并为单一事实源（`core/parser.py` / `core/loader.py` / `core/compiler.py` / `deerflow/skills/parser.py`），消除"by design 分居"的技术债。

- [ ] **Step 1: 定义顶层 SkillManifest**

```python
# src/core/graph_agent/core/manifest.py
from __future__ import annotations
from typing import Literal
from pydantic import BaseModel, Field, ConfigDict

class IoDeclaration(BaseModel):
    inputs: list[IoInput]
    outputs: list[IoOutput]

class IoInput(BaseModel):
    name: str
    source: Literal["runtime", "file"]
    type: str | None = None
    default: object | None = None

class IoOutput(BaseModel):
    name: str
    target: Literal["file", "artifact_manager"]
    path: str | None = None

class Step(BaseModel):
    name: str
    goal: str
    tools: list[str] = []
    validator: str | None = None
    when: str | None = None          # simpleeval 表达式
    skip_if: str | None = None

class PhaseConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    tier: Literal["premium", "balanced", "fast"] | None = None
    model_override: str | None = None   # 优先于 tier
    tools: list[str] = []
    steps: list[Step] = []
    validator: str | None = None
    retry_target: str | None = None
    max_retries: int = 3
    max_nudges: int = 1
    output_schema: str | None = None

class SubSkillSpec(BaseModel):
    name: str
    skill_path: str

class SkillManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal["1.0"]
    name: str
    description: str = Field(max_length=1024)
    type: Literal["graph", "code"]
    io: IoDeclaration
    phases: list[PhaseConfig]
    sub_skills: list[SubSkillSpec] = []
    context_mapping: dict[str, str] = {}
```

- [ ] **Step 2: 写单测覆盖所有现有 skills**

```python
# tests/core/test_manifest.py
import pytest
from pathlib import Path
from graph_agent.core.manifest import SkillManifest
from graph_agent.core.parser import parse_skill_file  # 改造后的 parser

@pytest.mark.parametrize("skill_path", [
    "skills/story-deconstruction/SKILL.md",
    # ... 5 个现有 skills
])
def test_manifest_validates_existing_skills(skill_path: str):
    manifest_dict = parse_skill_file(Path(skill_path))
    manifest = SkillManifest.model_validate(manifest_dict)
    assert manifest.schema_version == "1.0"
    assert manifest.name
```

**Acceptance**: 5 个业务 skills 全部通过 `SkillManifest.model_validate()`，discriminated union on `type` 工作正常，未知字段被 `extra="forbid"` 拒绝。

---

### Task 0.2: `serialize_skill()` AST 反向序列化

**Files:**
- Create: `src/core/graph_agent/tools/serialize.py`
- Create: `tests/tools/test_serialize.py`
- Modify: `src/core/graph_agent/__init__.py`（导出 `serialize_skill`）

**Why**: 是画布 / Copilot diff / 未来任何修改通道的公共出口，保证格式稳定不污染 Git diff。

- [ ] **Step 1: 实现 frontmatter 序列化（ruamel.yaml round-trip）**

```python
# src/core/graph_agent/tools/serialize.py
from __future__ import annotations
from io import StringIO
from ruamel.yaml import YAML
from graph_agent.core.manifest import SkillManifest

_yaml = YAML()
_yaml.indent(mapping=2, sequence=4, offset=2)
_yaml.preserve_quotes = True

def _serialize_frontmatter(m: SkillManifest) -> str:
    buf = StringIO()
    _yaml.dump(m.model_dump(exclude={"phases"}, exclude_none=True), buf)
    return buf.getvalue().rstrip() + "\n"
```

- [ ] **Step 2: 实现 body 序列化（自写 formatter，固定格式）**

```python
def _serialize_phase(p, indent: int = 0) -> str:
    pad = " " * indent
    attrs = []
    if p.tier: attrs.append(f'tier="{p.tier}"')
    if p.model_override: attrs.append(f'model_override="{p.model_override}"')
    if p.tools: attrs.append(f'tools="{p.tools}"')
    if p.output_schema: attrs.append(f'output_schema="{p.output_schema}"')
    attrs_str = " ".join(attrs)
    lines = [f'{pad}<node id="{p.name}">']
    lines.append(f'{pad}  <phase_config {attrs_str}>')
    for s in p.steps:
        lines.append(_serialize_step(s, indent + 4))
    lines.append(f'{pad}  </phase_config>')
    lines.append(f'{pad}</node>')
    return "\n".join(lines)

def _serialize_step(s, indent: int = 0) -> str:
    pad = " " * indent
    attrs = [f'name="{s.name}"']
    if s.when: attrs.append(f'when="{s.when}"')
    if s.skip_if: attrs.append(f'skip_if="{s.skip_if}"')
    if s.validator: attrs.append(f'validator="{s.validator}"')
    if s.tools: attrs.append(f'tools="{s.tools}"')
    return f'{pad}<step {" ".join(attrs)}>\n{pad}  {s.goal}\n{pad}</step>'

def serialize_skill(manifest: SkillManifest, *, indent: int = 2) -> str:
    fm = _serialize_frontmatter(manifest)
    body = "\n\n".join(_serialize_phase(p) for p in manifest.phases)
    return f"---\n{fm}---\n\n{body}\n"
```

- [ ] **Step 3: round-trip 幂等性单测**

```python
# tests/tools/test_serialize.py
import pytest
from pathlib import Path
from graph_agent.core.parser import parse_skill_file
from graph_agent.core.manifest import SkillManifest
from graph_agent.tools.serialize import serialize_skill

@pytest.mark.parametrize("skill_path", [...])
def test_roundtrip_idempotent(skill_path: str):
    m1 = SkillManifest.model_validate(parse_skill_file(Path(skill_path)))
    s1 = serialize_skill(m1)
    m2 = SkillManifest.model_validate(parse_skill_file_from_string(s1))
    s2 = serialize_skill(m2)
    assert s1 == s2, "serialize is not idempotent"
    assert m1 == m2, "parse(serialize(m)) != m"
```

**Acceptance**: 所有现有 skill 和人造 edge case 通过 round-trip 幂等测试。输出字节级稳定。

---

### Task 0.3: 4 处 SKILL.md 校验统一

**Files:**
- Modify: `src/core/graph_agent/core/parser.py`
- Modify: `src/core/graph_agent/core/loader.py`
- Modify: `src/core/graph_agent/core/compiler.py`
- Delete or Modify: `src/core/graph_agent/deerflow/skills/parser.py`

**Why**: 消除"by design 分居"债，保证所有路径看到同一个 Manifest。

- [ ] **Step 1: `parser.py` 只做 YAML+XML → dict 的底层解析**
  - 移除其中的业务规则校验
  - 对外导出 `parse_skill_file(path) -> dict`
- [ ] **Step 2: `loader.py` 调 `parse_skill_file` → `SkillManifest.model_validate()` → 构建 `GraphAgentHarness`**
- [ ] **Step 3: `compiler.py` 基于 `SkillManifest` 跑 `rules.yaml`（业务规则）**
  - 结构错误交给 Manifest，规则错误交给 compiler
  - 返回 `CompileResult{status, errors, warnings}`
- [ ] **Step 4: `deerflow/skills/parser.py` 优先删除**
  - 如果外部引用无法消除，改为薄封装引用 `core/parser.py`
  - 更新 CHANGELOG 说明整合完成

**Acceptance**: 所有 4 处 import 路径都走同一条链路；"校验规则分居"债清零。

---

### Task 0.4: CallbackEvent 类型化

**Files:**
- Create: `src/core/graph_agent/callbacks/events.py`
- Modify: `src/core/graph_agent/callbacks/*.py`（14 个钩子）
- Modify: `src/core/graph_agent/callbacks/tracing.py`

- [ ] **Step 1: 定义 CallbackEvent discriminated union**

```python
# callbacks/events.py
from __future__ import annotations
from typing import Annotated, Literal, Union
from datetime import datetime
from pydantic import BaseModel, Field

class BaseEvent(BaseModel):
    schema_version: Literal["1.0"] = "1.0"
    timestamp: datetime
    phase_name: str | None = None

class PhaseStartPayload(BaseModel): ...
class PhaseEndPayload(BaseModel): ...
class LLMCallPayload(BaseModel): ...
class LLMFallbackPayload(BaseModel):
    from_provider: str
    to_provider: str
    reason: str
class ToolCallPayload(BaseModel): ...
class ToolResultPayload(BaseModel): ...
class ValidatorStartPayload(BaseModel): ...
class ValidatorEndPayload(BaseModel):
    ok: bool
    errors: list[str]
class NudgeInjectedPayload(BaseModel): ...
class DeadEndDetectedPayload(BaseModel): ...
class SubgraphStartPayload(BaseModel): ...
class SubgraphEndPayload(BaseModel): ...
class CheckpointCompactedPayload(BaseModel): ...
class FinishTaskCalledPayload(BaseModel): ...
class PromptCapturedPayload(BaseModel):
    template_source: str
    variables: dict[str, object]
    final_prompt: str
    loop_index: int
    llm_role: str
    resolved_model: str

class PhaseStartEvent(BaseEvent):
    event_type: Literal["phase_start"]
    payload: PhaseStartPayload
# ... 每个事件一个子类

CallbackEvent = Annotated[
    Union[PhaseStartEvent, PhaseEndEvent, LLMCallEvent, LLMFallbackEvent,
          ToolCallEvent, ToolResultEvent, ValidatorStartEvent, ValidatorEndEvent,
          NudgeInjectedEvent, DeadEndDetectedEvent, SubgraphStartEvent, SubgraphEndEvent,
          CheckpointCompactedEvent, FinishTaskCalledEvent, PromptCapturedEvent],
    Field(discriminator="event_type"),
]
```

- [ ] **Step 2: 14 个钩子改为 emit 类型化事件**
  - 改造 `callbacks/base.py` 的 `Callback` 基类增加 `def emit(self, event: CallbackEvent)`
  - 各 on_xxx 方法构造具体 Event 子类后 emit
- [ ] **Step 3: `TracingCallback` 落盘 `tracing.jsonl`**
  - 每行 `event.model_dump_json()`
  - 按 timestamp 单调

**Acceptance**: 跑一遍现有 e2e 测试，所有事件都能成功解析为 `CallbackEvent` union 成员；`tracing.jsonl` 每行都能 `model_validate_json` 回 Pydantic。

---

### Task 0.5: Prompt Capture 埋点

**Files:**
- Modify: `src/core/graph_agent/cognitive/prompt.py` 或新建 wrapper
- Modify: DeerFlow agent 调用点（外层拦截，不改 DeerFlow 源码）

- [ ] **Step 1: 在 DeerFlow `create_agent()` 外层包 LLM 拦截**
  - 每次 LLM 调用前捕获 template_source + variables + final_prompt
  - emit `PromptCapturedEvent{loop_index, llm_role, resolved_model, ...}`
- [ ] **Step 2: 对 agent loop 多轮调用递增 `loop_index`**
- [ ] **Step 3: 单测：跑一个 2 轮的 echo skill，断言 tracing.jsonl 里有 2 条 prompt_captured**

**Acceptance**: PM 能在 Studio 的 Prompt Inspector 里看到每轮的三元组；失败定位时间 < 1 分钟。

---

### Task 0.6: `Step.when` simpleeval 求值

**Files:**
- Create: `src/core/graph_agent/core/when_eval.py`
- Modify: `core/harness.py` 或 runner 集成点
- Create: `tests/core/test_when_eval.py`

- [ ] **Step 1: 写受限求值器**

```python
# core/when_eval.py
from __future__ import annotations
from simpleeval import SimpleEval, FunctionNotDefined, NameNotDefined

class WhenExpressionError(Exception): ...

_WHITELIST_FUNCS = {"len": len, "str": str, "int": int, "bool": bool}

def eval_when(expr: str, *, context: dict, working_memory: dict, metrics: dict) -> bool:
    ev = SimpleEval(functions=_WHITELIST_FUNCS, names={
        "context": context,
        "working_memory": working_memory,
        "current_phase_metrics": metrics,
    })
    try:
        result = ev.eval(expr)
    except (FunctionNotDefined, NameNotDefined) as e:
        raise WhenExpressionError(f"disallowed ref: {e}") from e
    except Exception as e:
        raise WhenExpressionError(f"eval failed: {e}") from e
    return bool(result)
```

- [ ] **Step 2: Runner 在进入 step 前调用 `eval_when`，false 则跳过**
- [ ] **Step 3: 模糊测试**

```python
# tests/core/test_when_eval.py
import pytest
from graph_agent.core.when_eval import eval_when, WhenExpressionError

@pytest.mark.parametrize("expr", [
    "__import__('os')",
    "getattr(context, '__class__')",
    "().__class__.__bases__[0].__subclasses__()",
    "open('/etc/passwd')",
])
def test_when_eval_rejects_dunder_attacks(expr):
    with pytest.raises(WhenExpressionError):
        eval_when(expr, context={}, working_memory={}, metrics={})

def test_when_eval_boolean_ops():
    assert eval_when("context.scene_id == '001' and len(working_memory.entities) > 0",
                     context={"scene_id": "001"}, working_memory={"entities": [1]}, metrics={}) is True
```

**Acceptance**: 白名单生效，攻击 payload 全部被拒；正常业务表达式工作。

---

### Task 0.7: `ModelResolver` fallback 扩展

**Files:**
- Modify: `src/core/graph_agent/models/resolver.py`
- Modify: `config/llm_roles.yaml`（声明同级模型配对）
- Create: `tests/models/test_fallback.py`

- [ ] **Step 1: `llm_roles.yaml` 增加同级映射**

```yaml
peer_model_groups:
  code_strong:
    - {provider: OC_CL, model: claude-sonnet-4-6}
    - {provider: OPENAI, model: gpt-4o}
```

- [ ] **Step 2: resolver 失败路径按 peer_model_groups 切换，emit `LLMFallbackEvent`**
- [ ] **Step 3: 全部失败抛 `FallbackExhaustedError`**
- [ ] **Step 4: 熔断阈值参数化（30min/30 从 yaml 读）**

**Acceptance**: 模拟主 provider 返回 500，resolver 自动切到 peer，emit fallback event，business 层无感。

---

## Phase 1: Studio 档位 A

### Task 1.1: Studio Server 骨架

**Files:**
- Create: `studio/server/app.py`
- Create: `studio/server/config.py`
- Create: `studio/server/schemas.py`
- Create: `studio/README.md`

- [ ] **Step 1: FastAPI app 初始化**

```python
# studio/server/app.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .api import skills, run, terminal
from .services.skill_registry import SkillRegistry

def create_app(*, host: str = "127.0.0.1", skill_dir: str = "skills") -> FastAPI:
    app = FastAPI(title="Graph Agent Studio")
    app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173"])
    app.state.registry = SkillRegistry(skill_dir)
    app.include_router(skills.router)
    app.include_router(run.router)
    app.include_router(terminal.router)
    return app
```

- [ ] **Step 2: config 模块（host/port/cli_cmd）**
  - 默认 `host=127.0.0.1`、`port=8787`、`cli_cmd=claude`
  - README 警告远程部署需显式 `--host 0.0.0.0` 且自带认证
- [ ] **Step 3: 启动脚本 `python -m studio.server`**

**Acceptance**: `curl localhost:8787/health` 返回 200。

---

### Task 1.2: SkillRegistry + REST `/api/skills`

**Files:**
- Create: `studio/server/services/skill_registry.py`
- Create: `studio/server/api/skills.py`
- Create: `studio/tests/server/test_skills_api.py`

- [ ] **Step 1: SkillRegistry 扫描 `skills/` 目录**
  - 递归找 `SKILL.md`，解析 frontmatter 的 `name`
  - 缓存 + 监听目录变更（watchdog）
- [ ] **Step 2: `/api/skills` 返回 `SkillSummary[]`**

```python
class SkillSummary(BaseModel):
    id: str          # 相对路径，如 "story-deconstruction"
    name: str
    description: str
    type: Literal["graph", "code"]
    phase_count: int

@router.get("/api/skills")
def list_skills(registry = Depends(get_registry)) -> list[SkillSummary]:
    return registry.list()
```

- [ ] **Step 3: `/api/skills/{id}` 返回 `SkillDetail{manifest, file_paths, has_golden}`**
- [ ] **Step 4: 单测**

**Acceptance**: 列表返回所有 5 个现有 skill；详情含完整 SkillManifest。

---

### Task 1.3: Lint API

**Files:**
- Create: `studio/server/api/skills.py`（continued）
- Create: `studio/tests/server/test_lint_api.py`

- [ ] **Step 1: `POST /api/skills/{id}/lint`**

```python
class LintError(BaseModel):
    code: str
    message: str
    field_path: str
    line: int | None = None
    hint: str | None = None

class LintResult(BaseModel):
    status: Literal["passed", "failed"]
    errors: list[LintError]
    phases: list[PhaseSummary]   # 仅在 passed 时返回
```

- [ ] **Step 2: 实现内部逻辑**
  - 调用 `graph_agent.compile_skill(path)`
  - 把 Pydantic `ValidationError` / `CompileError` 转成 `LintError`
  - 保留原始 yaml/xml 行号（parser 已有 location tracking）
- [ ] **Step 3: 单测 — 故意损坏 SKILL.md 触发各类错误**

**Acceptance**: 损坏的 skill 返回结构化错误，行号可点击；正常 skill 返回 phase 列表。

---

### Task 1.4: Run API + WebSocket

**Files:**
- Create: `studio/server/api/run.py`
- Create: `studio/server/services/runner.py`
- Create: `studio/tests/server/test_run_api.py`

- [ ] **Step 1: `Runner` 子进程管理**

```python
# studio/server/services/runner.py
import multiprocessing as mp
from graph_agent import run_skill

class Runner:
    def __init__(self):
        self.runs: dict[str, RunState] = {}

    def start(self, skill_id: str, input_data: dict) -> str:
        run_id = uuid4().hex
        q = mp.Queue()
        p = mp.Process(target=_worker, args=(skill_id, input_data, run_id, q))
        p.start()
        self.runs[run_id] = RunState(pid=p.pid, queue=q, started_at=...)
        return run_id

def _worker(skill_id, input_data, run_id, q):
    from studio.server.services.ws_bus import WebSocketCallback
    cb = WebSocketCallback(q)
    run_skill(f"skills/{skill_id}/SKILL.md", **input_data, callbacks=[cb])
```

- [ ] **Step 2: `POST /api/skills/{id}/run` 返回 `{run_id}`**
- [ ] **Step 3: `WS /ws/run/{run_id}` 推送 CallbackEvent 流**
  - 后端 asyncio 监听 `Runner` 的 queue，通过 WebSocket 单 consumer send
  - 断开重连时提供 "从最近 N 条事件恢复"（依赖 tracing.jsonl）
- [ ] **Step 4: `GET /api/skills/{id}/trace/{run_id}` 返回历史全量事件**
- [ ] **Step 5: 单测 — 跑一个 echo skill，断言事件序**

**Acceptance**: 完整一次 run 可通过 WebSocket 观察；tracing.jsonl 落盘；失败情况下错误细节可点击展开。

---

### Task 1.5: TerminalManager + Terminal WebSocket

**Files:**
- Create: `studio/server/api/terminal.py`
- Create: `studio/server/services/terminal_mgr.py`
- Create: `studio/tests/server/test_terminal_api.py`

- [ ] **Step 1: TerminalManager 用 ptyprocess 启动**

```python
# studio/server/services/terminal_mgr.py
import ptyprocess
import os
from pathlib import Path

class TerminalManager:
    def __init__(self, cli_cmd: str = "claude", skill_root: Path = Path("skills")):
        self.sessions: dict[str, ptyprocess.PtyProcess] = {}
        self.cli_cmd = cli_cmd
        self.skill_root = skill_root.resolve()

    def spawn(self, skill_id: str) -> str:
        cwd = (self.skill_root / skill_id).resolve()
        if not cwd.is_relative_to(self.skill_root):
            raise ValueError("path escape detected")
        pty = ptyprocess.PtyProcess.spawn(
            [self.cli_cmd],
            cwd=str(cwd),
            env={**os.environ, "SKILL_DIR": str(cwd)},
        )
        term_id = uuid4().hex
        self.sessions[term_id] = pty
        return term_id
```

- [ ] **Step 2: `POST /api/skills/{id}/terminal` 返回 `{term_id}`**
- [ ] **Step 3: `WS /ws/terminal/{term_id}` 双向字节透传**
  - 客户端发来字节 → pty.write
  - pty.read → 客户端
- [ ] **Step 4: TTL 1h 自动 reap**
- [ ] **Step 5: 单测（pty spawn + `pwd` 返回 skill 目录）**

**Acceptance**: PM 能在浏览器里用 Claude Code CLI 跑 `/init`、Edit SKILL.md、看 lint 结果。PTY 路径越权测试通过。

---

### Task 1.6: FileWatcher

**Files:**
- Create: `studio/server/services/filewatcher.py`
- Modify: `studio/server/app.py`（启动 watcher）

- [ ] **Step 1: watchdog 监听 `skills/` 目录**
- [ ] **Step 2: SKILL.md 变更触发 `skill.changed` WebSocket broadcast**
- [ ] **Step 3: Studio 前端订阅后自动显示 toast**

**Acceptance**: 在 Terminal 里保存 SKILL.md，前端 <2s 内收到 toast 提示。

---

### Task 1.7: 前端 — Skill 列表页

**Files:**
- Create: `studio/web/src/pages/SkillsList.tsx`
- Create: `studio/web/src/lib/api.ts`

- [ ] **Step 1: `api.ts` 封装 fetch 调用**
- [ ] **Step 2: `SkillsList.tsx` 渲染卡片 + 三按钮**
  - [Lint]：调用 `/lint`，drawer 展开结果
  - [Run]：跳转详情页并弹输入面板
  - [Open CLI]：调用 `/terminal`，新 tab 打开终端

**Acceptance**: 列表显示 5 个 skill，三按钮分别工作。

---

### Task 1.8: 前端 — 详情页 + 画布 + Lint Drawer

**Files:**
- Create: `studio/web/src/pages/SkillDetail.tsx`
- Create: `studio/web/src/components/SkillGraph.tsx`
- Create: `studio/web/src/components/DetailPanel.tsx`
- Create: `studio/web/src/components/LintDrawer.tsx`

- [ ] **Step 1: React Flow 布局（Dagre）**
  - nodes: phases；edges: 顺序 + retry_target
  - 禁用拖拽连线（`edgesUpdatable={false}` / `nodesConnectable={false}`）
- [ ] **Step 2: DetailPanel：只读 Monaco 显示 system/user_prompt/output_schema/validator/tools/sub_skills**
- [ ] **Step 3: LintDrawer：成功/失败两态 + 错误跳行**

**Acceptance**: 画布只读验证（尝试拖拽连线无反应）；点击节点展开 detail；Lint 错误跳转正确。

---

### Task 1.9: 前端 — Run 面板 + Trace Timeline + Prompt Inspector

**Files:**
- Create: `studio/web/src/components/RunPanel.tsx`
- Create: `studio/web/src/components/TraceTimeline.tsx`
- Create: `studio/web/src/components/PromptInspector.tsx`
- Create: `studio/web/src/lib/ws.ts`
- Create: `studio/web/src/lib/events.ts`

- [ ] **Step 1: RunPanel 输入选择器（golden 下拉 / 粘贴 JSON）**
- [ ] **Step 2: TraceTimeline 订阅 `/ws/run/{run_id}`**
  - 事件卡片按时间顺序 append
  - 卡片显示 event_type / phase / elapsed / payload 摘要
- [ ] **Step 3: PromptInspector 弹窗**
  - 三 tab：Template / Variables / Final Prompt
  - 支持复制
- [ ] **Step 4: 在 CallbackEvent 着色画布节点（idle/running/passed/failed）**

**Acceptance**: 跑一次 skill，Timeline 实时推进；点 prompt_captured 事件打开 Inspector 看到三元组。

---

### Task 1.10: 前端 — Terminal 面板

**Files:**
- Create: `studio/web/src/components/TerminalPanel.tsx`

- [ ] **Step 1: 集成 xterm.js**
- [ ] **Step 2: `ws.ts` 提供 WebSocket 双向字节 helper**
- [ ] **Step 3: 深色主题 + 等宽字体 + resize 自适应**
- [ ] **Step 4: 连接断开 toast + 重连按钮**

**Acceptance**: 能在浏览器里用 Claude Code CLI；复制粘贴正常；终端尺寸自适应。

---

### Task 1.11: 只读模式（Copilot Fallback）

**Files:**
- Modify: `studio/server/api/*` — 检测 `FallbackExhaustedError`
- Modify: `studio/web/src/App.tsx` — 全局 banner

- [ ] **Step 1: 后端拦截 `FallbackExhaustedError`，broadcast `copilot.offline`**
- [ ] **Step 2: 前端展示 banner "Copilot 不可用" + Run 按钮禁用**
- [ ] **Step 3: Lint / Open CLI 仍可用**

**Acceptance**: 模拟 provider 全断，前端进入只读，PM 仍可观察 + 用 CLI 改（CLI 不受影响）。

---

### Task 1.12: E2E Playwright

**Files:**
- Create: `studio/tests/e2e/lint.spec.ts`
- Create: `studio/tests/e2e/run.spec.ts`
- Create: `studio/tests/e2e/terminal.spec.ts`

- [ ] **Step 1: Lint spec — 损坏 skill → 错误可点击跳行**
- [ ] **Step 2: Run spec — 跑 echo skill → Timeline 出现预期事件**
- [ ] **Step 3: Terminal spec — 启动 → pwd 正确**

**Acceptance**: CI 集成 Playwright，3 条 spec 全过。

---

## Phase 1.5: 用户验证关卡（Hard Gate）

### Task 1.5.1: 招募 2-3 个真实 PM

- [ ] 协调 2-3 个 PM 做 2 周 dogfood
- [ ] 准备好 "如何使用 Graph Agent Studio" 的短文档（半页）

### Task 1.5.2: 指标收集

- [ ] PM 自主完成一次 skill 改动的成功率（计数 + 视频录屏抽样）
- [ ] Claude Code CLI 生成的 SKILL.md 首次过 Lint 率
- [ ] UX 摩擦点 top 3（访谈）

### Task 1.5.3: P2 方向决策

- [ ] 输出决策 memo：(a) Trace 补强 / (b) 内嵌 Copilot / (c) 画布 Topology —— 三选一
- [ ] P2 spec 启动

**Gate**: P1.5 未完成前**禁止**启动 P2 任何工作。

---

## 前置清理（与 Phase 0 并行）

- [ ] **C1**: 拆分 `harness.py` 952 行为 `GraphBuilder` / `PhaseExecutor` / `RetryRouter` / `NudgeInjector` 4 个合作者
- [ ] **C2**: 合并 `src/core/graph_agent/docs/` 与 `docs/graph_agent_docs/`；一份做 symlink
- [ ] **C3**: 删除 `skills/builtin/script/patch_tools.py` 副本
- [ ] **C4**: `.gitignore` 加入 `.ccb/`、`*.pyc`、`.studio_state/`
- [ ] **C5**: 补多模态工具单测

---

## Verification & Acceptance

完成 Phase 0 + Phase 1 后：

1. `uv run pytest tests/ -x` 全绿
2. `uv run pytest studio/tests/ -x` 全绿
3. `python -m studio.server` 启动；浏览器打开 `localhost:5173`
4. 手动验收：
   - 选一个 skill → [Lint] 显示绿
   - [Run] 跑 echo → Trace 正常
   - [Open CLI] → 终端里 `claude` 正常启动
   - 故意改坏 SKILL.md → [Lint] 红，错误可点击跳行
5. 进入 Phase 1.5 真实 PM dogfood

## Requirements Traceability

| Phase Task | Requirements |
|---|---|
| 0.1 | 1 |
| 0.2 | 2 |
| 0.3 | 1 |
| 0.4 | 3 |
| 0.5 | 4 |
| 0.6 | 10 |
| 0.7 | 11 |
| 1.1-1.3 | 5 |
| 1.4 | 6 |
| 1.5-1.6 | 7 |
| 1.7-1.10 | 5, 6, 7, 8 |
| 1.11 | 11 |
| 1.12 | 5, 6, 7, 8 |
| 1.5.1-1.5.3 | 9 |
