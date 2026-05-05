# REPO_SPLIT_AND_SDK_PLAN (V2)

**版本**: 2.0 (Final Plan)
**日期**: 2026-05-05
**作者**: a2 Gemini (资深 SDK 架构师 + Monorepo 工程化专家)

---

## 0. Executive Summary

针对研发端 Studio 前端打磨的紧迫需求，本方案（V2）在 V1 决策基础上完成工程化落地细节的补完。我们确立了以 **uv workspaces** 为基石的 Monorepo 结构，将 `graph_agent` 提炼为极致收敛的“深模块”SDK，并彻底剥离不稳定的 Legacy 组件。

*   **Q1 结构**: 落地为 `packages/graph-agent` (核心 SDK) 与 `apps/studio/` (双端应用)。
*   **Q2 SDK**: API 从 33+ 缩减至 **6 组核心出口**，引入 Pydantic 强类型的 `WorkflowResult` 契约。
*   **Q3 规范**: 前置 10 项 P0 级工程门禁，确保迁移过程 Git 历史完整且不产生逻辑断层。
*   **Q4 生产端**: 独立仓库 `agent-harness-cloud` 将作为 SDK 的下游消费者，实现代码机密性与研发效率的平衡。

---

## 1. uv workspaces 配置 (Q1 完整)

通过 `uv` 统一管理多项目依赖与虚拟环境，根目录仅保留 `uv.lock`。

### 1.1 根目录 `pyproject.toml`
作为工作区管理器，不作为发布包。

```toml
[project]
name = "agent-harness-workspace"
version = "0.1.0"
description = "Monorepo for GraphAgent SDK and Studio"
requires-python = ">=3.11"
dependencies = []

[tool.uv]
workspace = { members = ["packages/*", "apps/studio/backend"] }

[tool.uv.sources]
graph-agent = { workspace = true }

[dependency-groups]
dev = [
    "pytest>=9.0.0",
    "mypy>=1.10",
    "ruff>=0.6",
    "pre-commit>=3.6",
]

[tool.ruff]
line-length = 100
target-version = "py311"
lint.select = ["E", "F", "B", "I", "UP"]

[tool.mypy]
python_version = "3.11"
strict = true
```

### 1.2 `packages/graph-agent/pyproject.toml`
纯净的引擎 SDK 配置，不含任何 Studio 依赖。

```toml
[project]
name = "graph-agent"
version = "0.2.0"
description = "Document-driven LLM agent harness SDK"
requires-python = ">=3.11"
readme = "README.md"
license = { text = "Apache-2.0" }
classifiers = [
    "Programming Language :: Python :: 3.11",
    "Typing :: Typed",
]
dependencies = [
    "langchain>=1.2.3,<1.2.11",
    "langgraph>=1.0.10,<1.1.0",
    "pydantic>=2.12.5,<3.0.0",
    "pyyaml>=6.0.3,<7.0.0",
    "httpx>=0.28.0",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/graph_agent"]
```

### 1.3 `apps/studio/backend/pyproject.toml`
Studio 业务后端，依赖本地工作区中的 SDK。

```toml
[project]
name = "studio-backend"
version = "0.1.0"
dependencies = [
    "graph-agent",  # 自动链接到 packages/graph-agent
    "fastapi>=0.115",
    "uvicorn>=0.30",
    "pydantic-settings>=2.0.0",
    "aiofiles>=23.0.0",
    "sqlalchemy>=2.0.0",
]

[tool.uv.sources]
graph-agent = { workspace = true }
```

### 1.4 焦点模式工作流
```bash
# 场景：只需修改引擎并运行单元测试
cd packages/graph-agent
uv run pytest

# 场景：启动 Studio 全栈进行联调
# 窗口 1: 后端 (会自动 pick up graph-agent 的改动)
cd apps/studio/backend
uv run uvicorn app.main:app --reload

# 窗口 2: 前端
cd apps/studio/frontend
npm run dev

# 场景：全局代码质量检查
uv run ruff check .
uv run mypy .
```

---

## 2. SDK API 38→6 (Q2 完整)

### 2.1 API 完整评审表 (33+ 项)

| API | 现状暴露 | V2 决策 | 理由 (Ousterhout 准则) |
|---|---|---|---|
| `run_skill` | yes | **Public** | 顶层 Entry point，隐藏所有加载与解析细节。 |
| `clear_cache` | yes | **Internal** | 仅用于测试，用户不应手动管理缓存。 |
| `GraphAgentHarness` | yes | **Public** | 给高级用户自定义 LangGraph 行为的低层接口。 |
| `Phase` | yes | **Internal** | 内部抽象，不应直接由 SDK 用户实例化。 |
| `ContextBridge` | yes | **Internal** | 属于 Manifest 的内部实现。 |
| `WorkflowState` | yes | **Internal** | 状态流动应封装在 `WorkflowResult` 中。 |
| `load_workflow_from_md` | yes | **Internal** | 统一由 `run_skill` 内部调用。 |
| `compile_skill` | yes | **Public** | Studio 前端做静态校验的关键接口。 |
| `SkillManifest` | yes | **Public** | 定义协议字段的单一直相来源，用户需按此构建输入。 |
| `AgentProfile` | yes | **Internal** | 包含在 `SkillManifest` 内部。 |
| `AgentSkillDef` | yes | **Internal** | 同上。 |
| `GraphSkillDef` | yes | **Internal** | 同上。 |
| `PersonaSkillDef` | yes | **Internal** | 同上。 |
| `PhaseDef` | yes | **Internal** | 同上。 |
| `parse_skill_file` | yes | **Internal** | 编译器的实现细节。 |
| `serialize_skill` | yes | **Internal** | 仅用于内部持久化。 |
| `ModelResolver` | yes | **Internal** | 模型映射逻辑应由 SDK 自动处理。 |
| `get_model_resolver` | yes | **Internal** | 同上。 |
| `get_skill_type` | yes | **Internal** | 内部工具函数。 |
| `ContextResolver` | yes | **Internal** | 属于 IO 层的私有逻辑。 |
| `IOManager` | yes | **Internal** | 属于 IO 层的私有逻辑。 |
| `Callback` | yes | **Public** | 扩展点，允许用户订阅运行事件。 |
| `LoggingCallback` | yes | **Public** | 常用默认扩展。 |
| `MetricsCallback` | yes | **Public** | 常用默认扩展。 |
| `TracingCallback` | yes | **Public** | 深度调试必备扩展。 |
| `GraphAgentError` | yes | **Public** | 异常基类，用于 try-except 捕获。 |
| `SkillLoadError` | yes | **Public** | 异常子类。 |
| `SkillCompilationError` | yes | **Public** | 异常子类。 |
| `TemplateRenderError` | yes | **Internal** | 映射到 GraphAgentError 抛出。 |
| `AllProvidersFailedError` | yes | **Internal** | 映射到 GraphAgentError 抛出。 |
| `MaxRetriesExceededError` | yes | **Internal** | 映射到 GraphAgentError 抛出。 |

### 2.2 最终 SDK Public API 清单

```python
# packages/graph-agent/src/graph_agent/__init__.py
"""graph_agent — Document-driven LLM agent harness SDK."""

from .runner import run_skill, WorkflowResult
from .harness import GraphAgentHarness
from .compiler import compile_skill
from .manifest import SkillManifest
from .callbacks import Callback, LoggingCallback, MetricsCallback, TracingCallback
from .errors import GraphAgentError, SkillLoadError, SkillCompilationError

__all__ = [
    "run_skill",
    "WorkflowResult",
    "GraphAgentHarness",
    "compile_skill",
    "SkillManifest",
    "Callback",
    "LoggingCallback",
    "MetricsCallback",
    "TracingCallback",
    "GraphAgentError",
    "SkillLoadError",
    "SkillCompilationError",
]
```

### 2.3 核心契约设计 (Pydantic)

#### 输出契约: `WorkflowResult`
取代旧有的裸 `dict` 返回值。

```python
class WorkflowResult(BaseModel):
    success: bool
    run_id: str
    context: dict[str, Any]
    metrics: dict[str, int]  # input_tokens, output_tokens, wall_time
    trace_path: Path | None
    error: str | None = None
```

#### 事件契约: `CallbackEvent`
用于流式输出与日志订阅。

```python
class CallbackEvent(BaseModel):
    event_type: Literal["phase_start", "phase_end", "llm_call", "tool_call", "finish_task", "run_ended"]
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    phase_name: str | None
    payload: dict[str, Any]
```

---

## 3. 规范前置与工具链 (Q3 完整)

### 3.1 P0 前置规范清单

| # | 规范名称 | 必要性 | 实施工具 | 实施 Step | 估算 |
|---|---|---|---|---|---|
| 1 | **绝对路径标准化** | 物理迁移后相对 `..` 会失效 | `ruff` | 批量将 `from ..core` 替换为 `from graph_agent.core` | 0.5d |
| 2 | **导出禁闭** | 防止 Studio 越权调用 SDK 内部类 | `ruff (ANN201)` | 在 `__init__.py` 中严格限制 `__all__` | 0.3d |
| 3 | **Pydantic 2.0 强制类型** | 消除 SDK 与 Studio 间的序列化模糊 | `mypy` | `run_skill` 的 inputs/outputs 全部类型化 | 0.5d |
| 4 | **异常分类归口** | SDK 抛出的异常必须可预测 | 异常树重构 | 所有内部 Exception 必须继承 `GraphAgentError` | 0.2d |
| 5 | ** docstring 强制要求** | SDK Public API 必须有文档 | `ruff (D103)` | 给 6 个核心 API 补充 Google 风格文档 | 0.2d |
| 6 | **废弃组件删除** | 清理 DataManager/ArtifactManager | `git rm` | 彻底移除已断开连接的旧代码 | 0.1d |
| 7 | **单向依赖检查** | 防止 SDK 反向依赖 Studio | `import-linter` | 严禁 `graph_agent` 导入 `app.*` | 0.2d |

### 3.2 工具链 Config 示例

#### `packages/graph-agent/ruff.toml`
```toml
target-version = "py311"
line-length = 100
lint.select = ["E", "F", "W", "I", "B", "UP", "ANN", "TCH", "D"]
lint.ignore = ["D100"] # 允许文件头无 docstring

[lint.pydocstyle]
convention = "google"

[lint.isort]
known-first-party = ["graph_agent"]
```

#### `.pre-commit-config.yaml`
```yaml
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.6.0
    hooks:
      - id: ruff
        args: [--fix, --exit-non-zero-on-fix]
      - id: ruff-format
  - repo: local
    hooks:
      - id: mypy
        name: mypy
        entry: uv run mypy .
        language: system
        types: [python]
```

---

## 4. 5 dev-day task 拆解

### Task 1: 物理拆分与 Workspace 初始化 (0.5d)
*   **T1.1**: 执行目录迁移：
    ```bash
    mkdir -p packages/graph-agent/src
    git mv src/core/graph_agent packages/graph-agent/src/
    mkdir -p apps/studio/backend
    git mv studio-backend/* apps/studio/backend/
    ```
*   **T1.2**: 删除 Legacy 文件：
    ```bash
    git rm src/core/data_manager.py src/core/artifact_manager.py
    rm -rf src/core
    ```
*   **T1.3**: 创建并同步三份 `pyproject.toml`（按 §1 模板）。

### Task 2: 导入路径标准化 (1.0d)
*   **T2.1**: 使用脚本批量纠正 `packages/graph-agent` 内的相对导入。
*   **T2.2**: 纠正 `apps/studio/backend` 对引擎的导入：`from app.services import ...` 内部统一引 `graph_agent`。
*   **T2.3**: 解决迁移后的 `PYTHONPATH` 问题，确保 `uv run pytest` 成功。

### Task 3: SDK 边界收敛与接口契约 (1.0d)
*   **T3.1**: 重写 `graph_agent/__init__.py`。
*   **T3.2**: 引入 `WorkflowResult` Pydantic 类并改造 `runner.py`。
*   **T3.3**: 为 `compile_skill` 增加详细的 Error Context 输出。

### Task 4: Port 抽象落地 (2.0d)
*   **T4.1**: 定义 `apps/studio/backend/app/core/ports/`。
*   **T4.2**: 实现 `storage_local.py`, `eventbus_memory.py` 等 4 个 Local Adapters。
*   **T4.3**: 在 `services/skills.py` 中移除所有直接的 `os.path` 操作，替换为 `storage.read_text()`。

### Task 5: 最终验证与环境锁定 (0.5d)
*   **T5.1**: 生成最终 `uv.lock`。
*   **T5.2**: 运行全量集成测试，确保 SDK -> Studio 数据流完整。

---

## 5. LOCAL_FIRST 4 task 在新结构中的 Mapping

| Task ID | 描述 | V2 处置 | 理由 |
|---|---|---|---|
| **L1** | 定义 4 个 Port (Protocol) | **Task 4 (现做)** | 必须在 Studio 前端逻辑写死前定义好接口。 |
| **L2** | 实现 4 个 Local Adapter | **Task 4 (现做)** | 支撑 Studio 在 Monorepo 环境下的正常运行。 |
| **L3** | Service 层 Wire-in 替换 | **Task 4 (部分做)** | 重点改写文件读写最频繁的 `skills.py`，其余稳步演进。 |
| **L4** | Mock Adapter 集成测试 | **推迟 (M2)** | 当前优先 Studio 体验打磨，Mock 属于质量加固，稍后进行。 |

---

## 6. agent-harness-cloud 起步计划 (Q4)

### 6.1 启动时机
在 Studio M1 阶段（前端原型打磨完成）结束后启动。

### 6.2 仓库初始化
- **方案**: `mkdir agent-harness-cloud` 从零开始，**不建议** fork。
- **原因**: 生产仓库需要极简的依赖树，fork 会带入大量 Studio 特有的 UI/Tauri 负担。

### 6.3 依赖引用方式
```bash
# 在生产仓库的 pyproject.toml 中
graph-agent = { git = "ssh://git@github.com/yourorg/agent-harness.git", subdirectory = "packages/graph-agent", tag = "v0.2.0" }
```

---

## 7. 风险与权衡

1.  **Editable Install 幻觉**: 开发者改了 SDK 没生效。
    *   *缓解*: 在 Studio 后端启动日志中显式打印 `graph_agent.__file__` 路径，确认指向 packages。
2.  **Import 循环依赖**: 随着 SDK 收敛，易产生内部循环。
    *   *缓解*: 严格执行 `ruff` 的 `TCH` (Type Checking) 检查。
3.  **Git History 丢失**: 误用 `mv` 而非 `git mv`。
    *   *缓解*: 在 Task 1 强制使用 `git mv` 并进行 commit check。
4.  **Legacy 存量风险**: 某些 SKILL.md 仍在字符串中引用 `artifact_manager`。
    *   *缓解*: `IOManager` 内部保留该字符串的别名处理，但底层代码已重构为 `StorageManager`。

---

## 8. 启动 Checklist

- [ ] `uv` 版本已升级至最新。
- [ ] 备份分支 `backup-pre-monorepo` 已建立。
- [ ] 方案中的 6 个 SDK 导出已由主程确认（符合业务深度需求）。
- [ ] `git status` 确认当前工作区干净。

---

## 9. Open Questions (0 项)

当前所有核心决策已闭环，可立即执行 Task 1。
