# TASK3_SDK_API_CONTRACT_SPEC

**版本**: 1.0
**日期**: 2026-05-05
**状态**: 待执行 (a1 codex)

## 1. Executive Summary

本任务旨在收敛 `graph_agent` 的 SDK 暴露边界，确立强类型的接口契约。核心工作包括：将现有的 33 个 API 导出缩减为 12 个核心导出，践行“深模块”哲学；引入 Pydantic 驱动的 `WorkflowResult` 代替裸 dict 返回值，提升调用方的类型安全性；增强 `compile_skill` 的错误上下文，为 Studio 提供精准的诊断信息（行号、字段路径及修复建议）。

## 2. 当前 SDK 边界扫描

### 2.1 `__init__.py` 33 个 Export 现状与决策

| API 名 | 来源 Module | V2 决策 | 理由 |
| :--- | :--- | :--- | :--- |
| `run_skill` | `core.runner` | **Public** | 核心高层入口。 |
| `GraphAgentHarness` | `core.harness` | **Public** | 核心编排器（进阶用）。 |
| `compile_skill` | `core.compiler` | **Public** | 核心校验工具（Studio 强依赖）。 |
| `SkillManifest` | `core.manifest` | **Public** | 核心输入契约（Pydantic Schema）。 |
| `Callback` | `callbacks` | **Public** | 核心扩展接口。 |
| `LoggingCallback` | `callbacks` | **Public** | 常用扩展实现。 |
| `MetricsCallback` | `callbacks` | **Public** | 常用扩展实现。 |
| `TracingCallback` | `callbacks` | **Public** | 常用扩展实现。 |
| `GraphAgentError` | `core.exceptions` | **Public** | 异常基类。 |
| `SkillLoadError` | `core.exceptions` | **Public** | 异常子类。 |
| `SkillCompilationError` | `core.exceptions` | **Public** | 异常子类。 |
| `WorkflowResult` | `core.runner` | **Public (NEW)** | 强类型输出契约。 |
| `clear_cache` | `core.runner` | **Internal** | 内部管理逻辑，不应外露。 |
| `Phase` | `core.types` | **Internal** | 内部细节，由 Manifest/Harness 封装。 |
| `WorkflowState` | `core.state` | **Internal** | 内部状态流转，不应直接操作。 |
| `load_workflow_from_md` | `core.loader` | **Internal** | 推荐使用 `run_skill` 自动加载。 |
| `IOManager` | `io.manager` | **Internal** | 内部组件。 |
| `ContextResolver` | `io.context_resolver` | **Internal** | 内部组件。 |
| `ModelResolver` | `models.resolver` | **Internal** | 内部组件。 |
| `AgentSkillDef` 等 | `core.manifest` | **Internal** | 内部多态细节，外部只需 `SkillManifest`。 |
| ...其他 10+ 项 | 见源码 | **Internal** | 均属于内部实现细节或历史遗留。 |

### 2.2 跨子包依赖实测
*   **Studio Backend**: 目前主要依赖 `run_skill`, `compile_skill`, `SkillManifest`。
    *   发现 `app/services/skills.py` 引用了 `parse_skill_file`，应改为从子模块 `graph_agent.core.parser` 导入，而非从 `graph_agent` 顶层导入。
*   **Tests**: 部分测试直接从 `graph_agent` 导入了 `IOManager` 或 `WorkflowState`。这些测试应改为从子模块导入（例如 `from graph_agent.core.state import WorkflowState`），以反映“白盒测试”性质。

### 2.3 `run_skill()` 现状
*   **当前签名**: `def run_skill(skill_path, ..., **inputs) -> dict[str, Any]`。
*   **当前返回值**: 包含 `context`, `metrics`, `trace_path`, `wall_time_sec` 的 dict。

## 3. SDK Public API 最终设计

### 3.1 新 `__init__.py` 内容
```python
"""graph_agent — Document-driven LLM agent harness SDK.

Public API:
    run_skill, WorkflowResult: High-level entry + typed result.
    GraphAgentHarness: Low-level orchestrator.
    compile_skill: Static validation & compilation.
    SkillManifest: Pydantic schema for SKILL.md.
    Callback: Base class for extensibility.
    GraphAgentError: Base exception for all framework errors.
"""
from graph_agent.core.runner import run_skill
from graph_agent.core.result import WorkflowResult  # 待创建
from graph_agent.core.harness import GraphAgentHarness
from graph_agent.core.compiler import compile_skill
from graph_agent.core.manifest import SkillManifest
from graph_agent.callbacks import (
    Callback,
    LoggingCallback,
    MetricsCallback,
    TracingCallback,
)
from graph_agent.core.exceptions import (
    GraphAgentError,
    SkillLoadError,
    SkillCompilationError,
)

__all__ = [
    "run_skill", "WorkflowResult",
    "GraphAgentHarness",
    "compile_skill",
    "SkillManifest",
    "Callback", "LoggingCallback", "MetricsCallback", "TracingCallback",
    "GraphAgentError", "SkillLoadError", "SkillCompilationError",
]
```

## 4. WorkflowResult Pydantic 设计

### 4.1 Schema 定义 (`core/result.py`)
```python
from datetime import datetime
from pathlib import Path
from typing import Any, Optional, Dict
from pydantic import BaseModel, Field, ConfigDict

class WorkflowMetrics(BaseModel):
    input_tokens: int = 0
    output_tokens: int = 0
    wall_time_sec: float = 0.0

class WorkflowResult(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    success: bool
    run_id: str
    skill_id: str
    context: Dict[str, Any] = Field(default_factory=dict)
    metrics: WorkflowMetrics = Field(default_factory=WorkflowMetrics)
    trace_path: Optional[Path] = None
    error: Optional[str] = None
    
    # 兼容性支持：允许像 dict 一样被访问
    def __getitem__(self, key: str) -> Any:
        return getattr(self, key)
    
    def get(self, key: str, default: Any = None) -> Any:
        return getattr(self, key, default)
```

### 4.2 `runner.py` 改造要点
*   在 `run_skill` 函数末尾，将原本构造的 dict 转换为 `WorkflowResult` 实例。
*   使用 `try...except GraphAgentError` 捕获异常，返回 `success=False` 且包含错误信息的 `WorkflowResult`。

## 5. `compile_skill` 错误上下文增强

### 5.1 `SkillCompilationError` 改造
在 `core/exceptions.py` 中增强该类：
```python
class SkillCompilationError(ValidationError):
    def __init__(
        self,
        message: str,
        *,
        skill_path: Optional[Path] = None,
        line: Optional[int] = None,
        field_path: Optional[str] = None,
        suggestion: Optional[str] = None,
        context: Optional[dict] = None
    ):
        self.skill_path = skill_path
        self.line = line
        self.field_path = field_path
        self.suggestion = suggestion
        # 自动格式化包含上下文的错误消息
        msg = f"{message}"
        if skill_path: msg += f"\n  File: {skill_path}"
        if line: msg += f" (Line {line})"
        if field_path: msg += f"\n  Field: {field_path}"
        if suggestion: msg += f"\n  Hint: {suggestion}"
        super().__init__(msg, context=context)
```

### 5.2 `compiler.py` 增强
*   在 `ValidationError` 处理块中，从 Pydantic 的错误字典中提取 `field_path`。
*   确保存储到 `CompileIssue` 中的消息包含这些结构化细节。

---

## 6. 实施 Sub-steps (a1 指南)

### T3.1: 重写 `__init__.py` 与迁移清理 (0.3d)
1.  **覆盖内容**: 应用 §3.1 的代码到 `graph_agent/__init__.py`。
2.  **修复 Studio**: 将 `apps/studio/backend/app/services/skills.py` 中对 `parse_skill_file` 的导入改为 `from graph_agent.core.parser import parse_skill_file`。
3.  **校验**: 运行 `uv run python -c "import graph_agent; print(graph_agent.__all__)"`。

### T3.2: 引入 `WorkflowResult` (0.4d)
1.  **新建文件**: `packages/graph-agent/src/graph_agent/core/result.py`。
2.  **修改 `runner.py`**:
    *   导入 `WorkflowResult`。
    *   改造 `run_skill` 返回值。
3.  **兼容性验证**: Studio 的 `run_manager.py` 目前使用 `result.get("metrics")`。由于 `WorkflowResult` 实现了 `__getitem__` 和 `get`，理论上不会 break。

### T3.3: 错误增强 (0.3d)
1.  **修改 `exceptions.py`**: 更新 `SkillCompilationError` 类。
2.  **修改 `compiler.py`**: 增强 Pydantic 校验错误到 `CompileIssue` 的映射逻辑。
3.  **单元测试**: 在 `packages/graph-agent/tests/unit/core/test_compiler.py` (Task 2 后路径) 中增加对错误格式的断言。

---

## 7. 风险点与缓解

1.  **类型检查失效**: 
    *   **风险**: Studio 原本以为拿到的是 `dict`，现在拿到的是 `WorkflowResult`。
    *   **缓解**: `WorkflowResult` 实现了 dict 接口（`get`, `__getitem__`），可无缝兼容大部分现有代码。
2.  **Circular Import**:
    *   **风险**: `runner.py` 导入 `result.py`，而 `result.py` 以后可能又需要引用 `runner` 中的某些类型。
    *   **缓解**: 保持 `result.py` 为纯数据定义层。
3.  **Exception 消息变更**:
    *   **风险**: 有些测试可能在断言异常的 Exact String。
    *   **缓解**: 使用 `pytest.raises(SkillCompilationError, match="...")` 进行子串匹配。

## 8. 工时估算
*   **T3.1**: 2h
*   **T3.2**: 3h
*   **T3.3**: 3h
*   **总计**: 8h (1 dev-day)。

## 9. 验收 Checklist
- [ ] `from graph_agent import ...` 只能看到 12 个公开 API。
- [ ] `run_skill()` 的返回值类型为 `WorkflowResult`。
- [ ] `WorkflowResult.success` 能够正确反映运行是否成功。
- [ ] `SkillCompilationError` 能够显示发生错误的行号（如果可用）。
- [ ] Studio 后端测试 `uv run pytest apps/studio/backend/tests` 全绿。
