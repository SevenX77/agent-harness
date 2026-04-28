# MVP-0 Design — Baseline Cleanup

**Spec:** `v1-reset-mvp-0-baseline-cleanup`
**Date:** 2026-04-28
**Parent:** `docs/superpowers/specs/2026-04-28-v1-reset-direction.md`
**Status:** Draft — pending Gemini design review

---

## 0. Design Overview

MVP-0 是纯减法 + 异常体系 / ContextBridge 收尾。**不引入任何新业务能力**，只清理。

实施分两条并行线：

| 线 | 派给 | 范围 |
|---|---|---|
| 重型线 | a1 codex | A6 异常体系重画 + silent failure 重构 + B3+B4 vendored deerflow 删除 |
| 短链线 | a3 claude | B1 parallel_delegate / subgraph 删除 + B2 multimodal tools 删除 + B5 dead code 删除 + A8 ContextBridge 合并 |
| 交叉审 | a1 codex | a3 编码完后 codex 审一遍（按用户铁律） |
| design 审 | a2 gemini | 本 design.md 派给 gemini 偏离审 |

每一条 commit 必须 self-contained（自带相关测试更新），方便有问题时 git revert 单条。

---

## 1. 异常体系（A6）

### 1.1 完整继承树

`src/core/graph_agent/core/exceptions.py` 重画为：

```python
"""Exception hierarchy for graph_agent framework.

All graph_agent errors inherit from GraphAgentError. Catch the most
specific class possible at boundary; let unexpected errors bubble.
"""

from __future__ import annotations

from typing import Any


class GraphAgentError(Exception):
    """Base for all graph_agent framework errors.
    
    Never catch this directly — catch a specific subclass.
    """

    def __init__(self, message: str, *, context: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.context = context or {}


# === Loader-time errors (SKILL load / parse / module / phase build) ===

class LoaderError(GraphAgentError):
    """SKILL loading failed before any execution."""


class SkillParseError(LoaderError):
    """SKILL.md text could not be parsed (frontmatter / structure)."""


class SkillModuleLoadError(LoaderError):
    """SKILL's script/ Python module failed to import."""


class PhaseBuildError(LoaderError):
    """Phase definition could not be built into runtime form."""


# === Validation errors (schema / contract / pre-flight) ===

class ValidationError(GraphAgentError):
    """Validation failed (schema, contract, pre-flight)."""


class SchemaValidationError(ValidationError):
    """Pydantic / business schema rejected the data."""


class ContractValidationError(ValidationError):
    """Cross-module contract (IO ref, pipeline alignment) rejected."""


# === Execution errors (phase execution / state transformation) ===

class ExecutionError(GraphAgentError):
    """Runtime execution failed."""


class PhaseExecutionError(ExecutionError):
    """A specific phase failed during run."""


class StateTransformError(ExecutionError):
    """State transformation (deepcopy / merge / hoist) failed."""


# === Tool execution errors ===

class ToolExecutionError(GraphAgentError):
    """A registered tool raised during execution.
    
    NOTE: Currently MVP-0 establishes this class but does NOT migrate
    tool_wrapper.py:138 string-error path. That migration is in MVP-4
    when finish_task itself is rewritten as control-flow primitive.
    """


# === IO errors (persistence / checkpoint / artifact) ===

class PersistenceError(GraphAgentError):
    """Persistence layer failed (file / artifact / checkpoint / trace).
    
    Note: Named PersistenceError instead of IOError to avoid shadowing
    Python builtin IOError (which is alias of OSError). Catching IOError
    in user code would otherwise unintentionally catch graph_agent's
    framework errors mixed with native filesystem errors.
    """


class CheckpointError(PersistenceError):
    """Checkpoint save/load failed."""


class TraceWriteError(PersistenceError):
    """Trace persistence failed."""


class ArtifactError(PersistenceError):
    """Artifact save/load failed."""
```

**Why this hierarchy**:
- 5 大类别：`LoaderError` / `ValidationError` / `ExecutionError` / `ToolExecutionError` / `PersistenceError` 对齐生命周期阶段
- 每类下有 2-4 个子类对应具体场景，让 catch 可以精确
- `GraphAgentError` 作为 base 永远不直接 catch（避免吃掉所有错误）

### 1.2 mypy 要求

```toml
[tool.mypy]
python_version = "3.11"
strict = true
warn_return_any = true
disallow_any_generics = true
disallow_any_unimported = true

[[tool.mypy.overrides]]
module = ["langgraph.*", "langchain.*", "langchain_core.*"]
ignore_missing_imports = true  # 上游 stubs 不全的临时豁免；MVP-5 改 strict
```

**所有 exceptions.py 内代码** mypy strict 必通过。

---

## 2. silent failure 替换策略（A6 范围）

每条按 `research.md` D4 决策实施。

### 2.1 抛错类（PersistenceError / LoaderError / ExecutionError）

**Pattern A — 抛错替换静默：**

```python
# Before
try:
    do_thing()
except OSError:
    pass

# After
try:
    do_thing()
except OSError as exc:
    raise PersistenceError(f"do_thing failed: {exc}", context={"path": ...}) from exc
```

适用：
- `runner.py:227` (checkpoint cleanup) → `PersistenceError`
- `runner.py:336` (import) → `LoaderError`
- `core/harness.py:307` (deepcopy) → `StateTransformError`
- `core/harness.py:431` (auto-checkpointer init) → `CheckpointError`
- `core/harness.py:715` (trace save) → `TraceWriteError`

### 2.2 显式降级类（保留行为但加可观测性）

**Pattern B — 显式降级 + 结构化 log：**

```python
# Before
try:
    do_thing()
except (TypeError, ValueError):
    return {}

# After
try:
    return do_thing()
except (TypeError, ValueError) as exc:
    logger.warning(
        "phase=%s action=%s fallback from=parse to=empty_dict reason=%s",
        phase_name, action, type(exc).__name__,
    )
    return {}
```

适用：
- `models/resolver.py:626` (circuit breaker — 设计本意降级)
- `core/validators/tool_paths.py:228` (path 不存在是预期场景)
- `config/llm_config.py:594` (LLM config OSError — 这条 design 时再确认是抛 vs 降级)

### 2.3 LLM 错误反馈类（替代静默 sentinel — Gemini design review 修正）

**Pattern C — Command(goto="model") + ToolMessage(status="error")：**

适用于 middleware 在拦截 LLM 输出 / tool args 时遇到 parse 失败的场景。**不能**返回 `{}` 或 sentinel（实质是变相静默吞错；下游 tool 用空 dict 会抛更难懂的 KeyError），应该把 parse 失败信息**丢回给 LLM** 触发自我纠错。

```python
# Before
try:
    parsed = json.loads(tool_args)
except (TypeError, ValueError):
    return {}

# After (Pattern C — LLM-feedback)
from langgraph.types import Command
from langchain_core.messages import ToolMessage

try:
    parsed = json.loads(tool_args)
except (TypeError, ValueError) as exc:
    error_msg = f"JSON parse failed: {exc}. Please retry with valid JSON."
    logger.warning(
        "phase=%s action=middleware fallback from=parse_json to=llm_retry reason=%s",
        phase_name, type(exc).__name__,
    )
    return Command(
        goto="model",
        update={"messages": [ToolMessage(status="error", content=error_msg)]},
    )
```

适用：
- `cognitive/middlewares.py:336` (parse JSON 失败 — 改 Pattern C 让 LLM 重试)
- `cognitive/middlewares.py:615` (同上)

**Why Pattern C not Pattern B**: Gemini design review 2026-04-28 明确指出（`/tmp/gemini-mvp-0-design-reply.txt`）："显式降级 + 返回 sentinel 或 `{}`" 依然是变相静默吞错。返回 `{}` 后下游 tool 因为缺必填字段抛 `KeyError` / `TypeError`，错误信息更难追溯到根因。**Pattern C 让 LLM 自己看到"你的 JSON 不对，请重写"，能在 agent loop 内修复**，符合 framework 应有的错误反馈纪律。

### 2.3 顶层 catch + Result 包装（harness.run）

`harness.run()` 顶层应该 catch 所有 `GraphAgentError`，转成包含 status 的 Result 对象给调用方：

```python
@dataclass(frozen=True)
class RunResult:
    status: Literal["ok", "error"]
    state: WorkflowState | None
    error: GraphAgentError | None
    elapsed_ms: float
```

**注意**：`RunResult` 类的具体 schema 在 MVP-5 装配阶段最终定型；MVP-0 内只在 `exceptions.py` 内引用 `GraphAgentError`，`RunResult` 不在本 MVP 范围。

---

## 3. ContextBridge 单一来源（A8）

### 3.1 现状

```python
# src/core/graph_agent/core/types.py:17
@dataclass
class ContextBridge:
    ...

# src/core/graph_agent/core/manifest.py:180
class ContextBridge(BaseModel):
    ...
```

两份定义同名同字段（codex audit 已确认）。

### 3.2 决策：保留 manifest.py 版本

理由：Pydantic 版本提供 model_validate / model_dump / serialization 一站式能力，dataclass 版本不能。下游 strict_v2 / loader / executor 已经 mix 引用两版，统一到 Pydantic 一致性更好。

### 3.3 实施步骤

1. `grep -rn "from .* import ContextBridge\|from .*types.* import" src/core/graph_agent` 列所有引用
2. 把所有 `from graph_agent.core.types import ContextBridge` 改为 `from graph_agent.core.manifest import ContextBridge`
3. 验证字段对齐：dataclass 版本 vs BaseModel 版本逐字段比对，差异字段合并到 BaseModel 版本
4. 删除 `types.py:17` 的 dataclass 定义（保留 `types.py` 文件本身——它还有其他 type alias，但移除 ContextBridge 那块）
5. `pytest tests/graph_agent/` 验证不退步

### 3.4 Acceptance

- `grep -rn "class ContextBridge" src/core/graph_agent` 输出仅 1 行（`manifest.py`）
- 所有 import 统一指向 `manifest.ContextBridge`

---

## 4. 删除清单（B1 / B2 / B5）

### 4.1 B1 parallel_delegate + subgraph

**删除文件**:
- `src/core/graph_agent/core/parallel_delegate.py`
- `src/core/graph_agent/core/subgraph.py`
- `src/core/graph_agent/core/validators/subgraph_cycle.py`

**修改文件**:
- `src/core/graph_agent/core/manifest.py`：移除 `LLMPhase` / `LogicPhase` 中 `subgraph` / `parallel_delegate` / `aggregate_to` / `parallel_outputs` 等字段
- `src/core/graph_agent/core/loader.py`：移除 `_resolve_subgraph` / `build_subgraph_node` / `build_parallel_delegate_node` 等加载逻辑
- `src/core/graph_agent/core/__init__.py`：移除相关 export
- `src/core/graph_agent/core/validators/__init__.py`：移除 subgraph_cycle 注册

**删除测试**:
- `tests/graph_agent/core/test_parallel_delegate.py`
- `tests/graph_agent/core/test_subgraph.py`（如存在）
- `tests/graph_agent/core/validators/test_subgraph_cycle.py`（如存在）

**story-deconstruction SKILL 处理**: 移到 `skills/_v2_pending/story-deconstruction/`（不删除文件），同目录加 `README.md` 说明 v1 期间不可用。

### 4.2 B2 multimodal tools

**删除文件**:
- `src/core/graph_agent/tools/generate_image.py`
- `src/core/graph_agent/tools/generate_video.py`
- `src/core/graph_agent/tools/understand_video.py`
- `src/core/graph_agent/config/multimodal_config.py`

**修改文件**:
- `src/core/graph_agent/tools/__init__.py`：移除 multimodal tool 注册
- `pyproject.toml`：移除 multimodal 相关依赖（如 PIL / opencv-python / 等）

**删除测试**:
- `tests/graph_agent/tools/test_multimodal*.py`
- `tests/graph_agent/tools/test_generate_image*.py`
- `tests/graph_agent/tools/test_generate_video*.py`
- `tests/graph_agent/tools/test_understand_video*.py`

### 4.3 B5 dead code + 冗余 parser

**修改文件**:
- `src/core/graph_agent/core/loader.py`：删除 `_phase_string` / `_phase_int` / `_phase_bool` / `_phase_string_list`（行 308-380 范围）

**删除文件**:
- `src/core/graph_agent/deerflow/skills/parser.py`（与 `core/parser.py` 冗余；按 B4 一起处理）

---

## 5. B3+B4 vendored deerflow 拆解（合并处理）

### 5.1 设计前置：deerflow 上游确认（design.md 阶段必做）

**Q1**：deerflow 是否有公开 PyPI release？

**做法**：
```bash
pip search deerflow  # 或
curl -s https://pypi.org/pypi/deerflow/json | jq .info.version
```

**两种结果分支**:
- **结果 A**: 有公开 release → 在 `pyproject.toml` 添加 `deerflow>=X.Y`
- **结果 B**: 没有公开 release → inline 复制方案

### 5.2 deerflow primitives 引用 grep（design.md 阶段必做）

**做法**: 列出 graph_agent 真正用到 deerflow 的所有 import：
```bash
grep -rn "from graph_agent.deerflow\|import graph_agent.deerflow\|from .deerflow\|import .deerflow" src/core/graph_agent --include="*.py" | grep -v "deerflow/"
```

输出预期：< 30 处 import，每条对应 graph_agent 用了 deerflow 的某个具体类 / 函数。

### 5.3 inline 复制方案（如 deerflow 无公开 release）

按 grep 输出列出"必须 inline 的 deerflow 内部类 / 函数"，复制到 graph_agent 内部。**inline 时**：
- 在每个被 inline 的文件顶部加 docstring：`"""Inlined from deerflow upstream commit <sha>; do not edit upstream-tracked code without first updating <sha>."""`
- 复制最小 closure（不无脑全部复制 deerflow，只复制 graph_agent 真用到的）

### 5.4 引用整改（必做）

**修改文件清单**:
- `src/core/graph_agent/__init__.py`：移除 sys.path hack（vendored deerflow 绝对导入用的）
- `src/core/graph_agent/models/resolver.py`：移除 `SummarizationMiddleware` 相关 metadata attach 逻辑
- `src/core/graph_agent/cognitive/middlewares.py`：如果直接 import 了 deerflow 的 middleware，改 import path 或一并删除（这部分等 design 确认后定）

### 5.5 双 pyproject 整合（B4 子项）

**保留**: 根目录 `pyproject.toml`（`/home/sevenx/coding/agent-harness/pyproject.toml`）

**删除**: `src/core/graph_agent/pyproject.toml`

**整合规则**:
- 把内层 pyproject 里独有的依赖 / 配置合并进根 pyproject
- 内层独有 metadata（package name `graph-agent` / version `1.0.0`）废弃，根 pyproject 用 `graph-agent-harness` 0.x.y 作为单一发布单元
- 在根 pyproject `[project.optional-dependencies]` 里加 `dev = [pytest>=7, mypy>=1.10, ruff>=0.6, pre-commit>=3.6, ...]`

---

## 6. baseline snapshot（删除前必做）

`docs/v1-reset/mvp-0-baseline-snapshot.md` 内容：

```markdown
# MVP-0 Baseline Snapshot — 2026-04-28T<HH:MM>Z

## SKILL.md compile status

| SKILL | FATAL | WARNING | Status |
|---|---|---|---|
| text-segmentation | 0 | 1 | WARN(1) |
| event-extraction | 0 | 1 | WARN(1) |
| batch-analysis | 0 | 1 | WARN(1) |
| global-synthesis | 0 | 0 | PASS |
| story-deconstruction | 2 | 9 | FATAL(2) |
| adaptation_v1 | 0 | 0 | PASS |
| producer | 0 | 0 | PASS |
| ... |

## pytest output

\`\`\`
<full pytest output>
\`\`\`

## Python file line counts

\`\`\`
<find ... | xargs wc -l output>
\`\`\`
```

主控用 baseline 跟 MVP-0 完成后的对比，确保过度激进清理没破坏 4 SKILL 之外的隐藏用例。

---

## 7. 验证规则（MVP-0 完成判定）

主控在每条删除 commit 后运行：

```bash
# 1. 静态 grep（应该全部 0 hit）
grep -rn "parallel_delegate\|class Subgraph\|generate_image\|generate_video\|understand_video\|_phase_string\|_phase_int\|SummarizationMiddleware\|LoopDetectionMiddleware" src/ | wc -l

# 2. 双 pyproject 检查
find . -name pyproject.toml -not -path "*/node_modules/*" -not -path "*/.venv/*" | wc -l  # 应输出 1

# 3. silent failure 检查
python3 -c "
import re, pathlib
hits = 0
for p in pathlib.Path('src/core/graph_agent').rglob('*.py'):
    if 'deerflow' in str(p): continue
    src = p.read_text()
    if re.search(r'except\s+[^\n]+:\s*\n\s+pass\s*$', src):
        hits += 1
        print(p)
print(f'hits={hits}')
"  # 应输出 0

# 4. 单元测试
pytest tests/graph_agent/ -x --tb=short

# 5. e2e smoke
python3 /tmp/e2e_chain.py  # 跑通 1 章

# 6. baseline diff
# (主控对比 MVP-0 完成前后的 baseline snapshot)

# 7. mypy strict（新代码）
mypy --strict src/core/graph_agent/core/exceptions.py src/core/graph_agent/core/manifest.py
```

任一不通过 → MVP-0 不能 ship。

---

## 8. Risk & 回滚

| Risk | 影响 | 缓解 |
|---|---|---|
| 删 vendored deerflow 后某 import 漏改 | 启动时 ImportError | 删除 commit 落地后立刻跑全套 import smoke test |
| inline 复制 deerflow 时漏复制依赖闭包 | 运行时 ModuleNotFoundError | grep 验证时不仅看 graph_agent → deerflow，还要看 deerflow 内部互相依赖 |
| ContextBridge dataclass vs BaseModel 字段不一致 | 切换后 AttributeError | 字段对比清单 + 失败字段合并到 BaseModel 版 |
| silent failure 改抛后影响某 graceful path | 用户期望的降级变 crash | D4 决策矩阵已每条 case-by-case；如果发现某条改抛后破 e2e，回到 Pattern B 显式降级 |
| 4 SKILL 之外的隐藏 SKILL 依赖被删 feature | hidden e2e 崩 | baseline snapshot diff |

每条删除 commit 都必须独立可 revert（不打包多个删除到一个 commit）。

---

## 9. Future MVP 影响（前向兼容）

- A1 (MVP-1) WorkflowState 拆解 → 本 MVP 异常体系 + StateTransformError 用得上
- A5 (MVP-2) SchemaEngine → 本 MVP 异常体系 SchemaValidationError 用得上
- A7 (MVP-2) IOManager StorageAdapter → 本 MVP 异常体系 ArtifactError / PersistenceError 用得上
- A2 (MVP-3) loader 拆解 → 本 MVP 异常体系 LoaderError 用得上
- A3 (MVP-4) phase_executor 拆解 → 本 MVP 异常体系 PhaseExecutionError 用得上
- A4 (MVP-4) finish_task 重画 → 本 MVP 推迟的 tool_wrapper.py:138 在 MVP-4 一起改

异常体系**先于**所有重画建立，确保下游重画时有合适的异常类可抛。
