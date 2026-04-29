# MVP-3 Design — A2 Loader / A9 hack / B3 Middleware 落地设计

> 整合 Gemini independent design (job_d22adb45e517 Part B-H) + 主控决策 (research.md D1-D6) + MVP-1 / MVP-2 spec 衔接。

## §1 Loader 三阶段 Pipeline

### §1.1 文件位置 + 函数签名

```python
# src/core/graph_agent/core/loader.py (重画后, ≤ 200 行)
from __future__ import annotations
from typing import Any, Callable
from .manifest import SkillManifest, IODef
from .schema_engine import SchemaEngine
from .io_manager import IOManager
from .module_sandbox import ModuleSandbox
from .phase_node import PhaseNode


def parse_skill_md(text: str) -> dict[str, Any]:
    """Phase 1: markdown → raw dict. 仅做结构化分割 + 基础正则提取, 无对象引用。
    
    复用 MVP-2 SchemaEngine 的内部正则不适用于此 (此处只切顶层 markdown 块)。
    """
    ...


def validate_manifest(
    raw: dict[str, Any],
    schema_engine: SchemaEngine,
    io_manager_factory: Callable[[list[IODef]], IOManager],
) -> SkillManifest:
    """Phase 2: raw dict → 强类型 SkillManifest。
    
    - 调 schema_engine.validate_spec_dict 校验 manifest 整体格式
    - 对每个 phase 的 output_schema 字段, 调 schema_engine.parse_from_md 转 SchemaObject
    - 对 io.outputs, 用 io_manager_factory(io_specs).validate_spec 校验路径合法
    """
    ...


def build_graph_nodes(
    manifest: SkillManifest,
    schema_engine: SchemaEngine,
    module_sandbox: ModuleSandbox,
) -> list[PhaseNode]:
    """Phase 3: SkillManifest → list[PhaseNode] (LangGraph 节点)。
    
    - 不再读 markdown, 仅消费 SkillManifest 字段
    - 调 build_business_data_for_skill(manifest, schema_engine) 生成 BusinessData 子类
    - 通过 module_sandbox.import_class(path) 解析 output_schema_path / validator path
    """
    ...
```

### §1.2 Class wrapper (依赖注入)

```python
class SkillLoader:
    """三阶段 Pipeline 的 thin orchestrator。
    
    保留 SkillLoader 名字给调用方稳定, 内部全部委托给三阶段函数。
    """

    def __init__(
        self,
        schema_engine: SchemaEngine | None = None,
        module_sandbox: ModuleSandbox | None = None,
    ) -> None:
        self._schema_engine = schema_engine or SchemaEngine()
        self._module_sandbox = module_sandbox or ModuleSandbox()

    def compile_skill(self, skill_path: str) -> CompiledSkill:
        text = self._read_file(skill_path)
        raw = parse_skill_md(text)
        manifest = validate_manifest(
            raw, self._schema_engine, lambda specs: IOManager(specs, self._schema_engine)
        )
        nodes = build_graph_nodes(manifest, self._schema_engine, self._module_sandbox)
        return CompiledSkill(manifest=manifest, nodes=nodes)
```

## §2 SkillManifest Pydantic 全量模型

`core/manifest.py` 现有 `GraphSkillDef` / `PhaseDef discriminated union` / `IoDef` / `ContextBridge` 等组件。MVP-3 把它们整合为顶层 SkillManifest:

```python
# core/manifest.py 扩展
class SkillManifest(BaseModel):
    """编译期产物, 给运行时 (build_graph_nodes / IOManager / harness.run) 消费。"""
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["2.0"] = "2.0"
    name: str = Field(min_length=1, max_length=64)
    description: str = Field(max_length=1024)
    skill_type: Literal["graph", "logic", "subskill"]
    phases: list[PhaseDef] = Field(default_factory=list)
    io: IoDef = Field(default_factory=IoDef)
    context_bridge: ContextBridge | None = None
    
    # 编译期填入: parse_from_md(phase.output_schema_md) 的结果
    compiled_schemas: dict[str, SchemaObject] = Field(default_factory=dict)
```

## §3 Bootstrap + Settings 启动序列

### §3.1 文件位置

```
src/core/graph_agent/
├── bootstrap.py          # Bootstrap 类
├── settings.py           # Settings dataclass
├── module_sandbox.py     # ModuleSandbox 类 (A9-original)
└── patches/              # monkey-patch 集中目录
    ├── __init__.py       # apply_all() 入口
    ├── langchain_compat.py
    └── pydantic_compat.py
```

### §3.2 Bootstrap 类签名

```python
# src/core/graph_agent/bootstrap.py
from __future__ import annotations
from .settings import Settings
from . import patches


class Bootstrap:
    """框架启动序列固化点。"""

    def __init__(self) -> None:
        self._patched = False
        self._settings: Settings | None = None

    def apply_patches(self) -> None:
        """启动序列第 1 步: 集中调用所有 monkey-patch。仅可调一次。"""
        if self._patched:
            raise RuntimeError("Bootstrap.apply_patches() called twice")
        patches.apply_all()
        self._patched = True

    def load_settings(self, env_overrides: dict[str, str] | None = None) -> Settings:
        """启动序列第 2 步: 显式构造 Settings, 不再 os.environ.set。"""
        self._settings = Settings.from_env(env_overrides=env_overrides)
        return self._settings
```

### §3.3 Settings dataclass

```python
# src/core/graph_agent/settings.py
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    """显式 Settings 对象, 替代 os.environ 散落访问。"""
    openai_api_key: str | None = None
    anthropic_api_key: str | None = None
    log_level: str = "INFO"
    debug_mode: bool = False
    # ... (从 T0-prep grep runner.py 得到的全部 env 变量)

    @classmethod
    def from_env(cls, env_overrides: dict[str, str] | None = None) -> "Settings":
        ...
```

## §4 ModuleSandbox (A9-original output_schema 路径 hack 剥离)

### §4.1 当前 hack

`loader.py` 现有 `_resolve_output_schema_path` 函数把 SKILL.md 中 `output_schema_path: "skills.foo.v3.schemas.MyClass"` 字符串解析为类对象, 实现里:
1. `importlib.import_module("skills.foo.v3.schemas")` 导入模块
2. fallback: `sys.modules["skills.foo.v3.schemas"] = ...` 写入
3. `getattr(module, "MyClass")` 取类

**问题**: sys.modules 写入产生 "幽灵模块名" — 调试时 `sys.modules` 含 SKILL 局部模块名, 污染 import 行为。

### §4.2 改造后 (PEP 451 importlib namespace)

```python
# src/core/graph_agent/core/module_sandbox.py
from __future__ import annotations
import importlib
import importlib.machinery
import importlib.util
from pathlib import Path
from typing import Any


class ModuleSandbox:
    """SKILL local 模块解析, 不污染 sys.modules。
    
    使用 PEP 451 importlib namespace + spec_from_file_location,
    在 sandbox 内部维护私有 module 注册表, 不写 sys.modules。
    """

    def __init__(self, search_paths: list[Path] | None = None) -> None:
        self._search_paths = search_paths or []
        self._cache: dict[str, type[Any]] = {}

    def import_class(self, dotted_path: str) -> type[Any]:
        """解析 'pkg.module.ClassName' → class object, 不写 sys.modules。"""
        if dotted_path in self._cache:
            return self._cache[dotted_path]
        module_path, _, class_name = dotted_path.rpartition(".")
        spec = importlib.util.find_spec(module_path)
        if spec is None:
            raise ImportError(f"ModuleSandbox: cannot find {module_path!r}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)  # 不写 sys.modules
        cls = getattr(module, class_name)
        self._cache[dotted_path] = cls
        return cls
```

## §5 Middleware 简化为 4 核心

### §5.1 4 核心 middleware 文件结构

```
src/core/graph_agent/middleware/
├── __init__.py                    # 导出 4 核心类
├── protocol_validation.py         # ProtocolValidationMiddleware
├── cognitive_flow.py              # CognitiveFlowMiddleware (含 finish_task / clarification)
├── execution_control.py           # ExecutionControlMiddleware (retry / loop / metrics)
└── logging.py                     # LoggingMiddleware
```

旧目录 `cognitive/middlewares.py` (含 ValidationMiddleware / UnattendedClarification) + `cognitive/clarification_middleware.py` 整体并入新目录后**物理删除**。

### §5.2 ProtocolValidationMiddleware

唯一负责契约校验。整合 MVP-1 BusinessData / FrameworkState extra 校验 + MVP-2 SchemaEngine 校验:

```python
class ProtocolValidationMiddleware(AgentMiddleware):
    """每个 LLM step 前后校验状态契约。"""

    def __init__(self, schema_engine: SchemaEngine, current_phase_schema: SchemaObject) -> None: ...
    def before_model(self, state: WorkflowState) -> WorkflowState: ...  # 校验 state["data"] / state["flow"]
    def after_model(self, state: WorkflowState) -> WorkflowState: ...   # 同上 + finish_task 后校验
```

### §5.3 CognitiveFlowMiddleware

整合 finish_task interception + Clarification (旧 ClarificationMiddleware + UnattendedClarificationMiddleware):

```python
class CognitiveFlowMiddleware(AgentMiddleware):
    """处理所有非业务输出 (Tool Call / Interceptor)。"""

    def __init__(
        self,
        io_manager: IOManager,
        unattended: bool = False,
    ) -> None: ...

    def intercept_tool_call(self, tool_name: str, args: dict, state: WorkflowState) -> tuple[bool, Any]:
        """- finish_task → 调 io_manager.resolve_hoist + StateManager.update_business
           - ask_clarification (attended mode) → 触发 human-in-loop
           - ask_clarification (unattended mode) → 自动用 default 答复"""
        ...
```

### §5.4 ExecutionControlMiddleware

retry / loop detection / metrics:

```python
class ExecutionControlMiddleware(AgentMiddleware):
    def __init__(
        self,
        max_retries: int,
        max_iterations: int,
    ) -> None: ...
    def on_retry(self, phase: str, errors: list[str]) -> None: ...
    def on_loop_detected(self, phase: str) -> None: ...
    def collect_metrics(self, state: WorkflowState) -> dict: ...
```

### §5.5 LoggingMiddleware

统一 callback 触发, 不含业务逻辑:

```python
class LoggingMiddleware(AgentMiddleware):
    def __init__(self, callbacks: list[Callback]) -> None: ...
    # 把 LangGraph 事件桥接到 callbacks (MVP-1 已存的 TracingCallback / MetricsCallback 等)
```

### §5.6 顺序契约 + 拓扑测试

```python
# src/core/graph_agent/middleware/__init__.py
DEFAULT_MIDDLEWARE_ORDER = [
    ProtocolValidationMiddleware,
    CognitiveFlowMiddleware,
    ExecutionControlMiddleware,
    LoggingMiddleware,
]
```

`tests/graph_agent/conftest.py` 加:
```python
def test_middleware_topological_order():
    assert [m.__name__ for m in DEFAULT_MIDDLEWARE_ORDER] == [
        "ProtocolValidationMiddleware",
        "CognitiveFlowMiddleware",
        "ExecutionControlMiddleware",
        "LoggingMiddleware",
    ]
```

## §6 启动延迟基准 + 性能验收

### §6.1 baseline 测量 (T0-prep)

```python
# 测量脚本: scripts/measure_startup_latency.py
import time
from graph_agent.core.loader import SkillLoader

def measure() -> float:
    t0 = time.perf_counter()
    loader = SkillLoader()
    compiled = loader.compile_skill("skills/text-segmentation/v3/SKILL.md")
    first_node = compiled.nodes[0]
    # 模拟第一个 phase 入口 (不实际跑 LLM)
    _ = first_node.execute_dry_run()
    return time.perf_counter() - t0
```

T0-prep 跑 10 次取中位数, 记录到 `docs/v1-reset/mvp-3-baseline-snapshot.md`。

### §6.2 验收阈值

MVP-3 收尾后再跑同脚本, 中位数应 ≤ baseline × 0.8 (下降 ≥ 20%)。

## §7 验收 baseline diff 标准

| 指标 | Baseline (T0-prep) | After MVP-3 | 验证命令 |
|---|---|---|---|
| `loader.py` 逻辑行数 (SLOC) | ~500 (MVP-2 后) | ≤ 200 | `cloc src/core/graph_agent/core/loader.py` |
| middleware 物理文件数 | T0-prep 测 | 4 | `ls src/core/graph_agent/middleware/*.py \| grep -v __init__` |
| `runner.py` 内 `os.environ.set` 站点 | T0-prep 测 | 0 | grep |
| `runner.py` 内 `sys.path.append` 站点 | T0-prep 测 | 0 | grep |
| `_resolve_output_schema_path` 内 sys.modules 写入 | T0-prep 测 (≥ 1) | 0 | grep |
| 启动延迟中位数 | T0-prep 测 | ≤ baseline × 0.8 | scripts/measure_startup_latency.py |
| pytest 全过 (--ignore test_strict_v2) | MVP-2 baseline | ≥ MVP-2 baseline | pytest |
| 4 SKILL compile 状态 | WARN-only / 1 PASS | unchanged | scripts/compile_all.py |
| 4 SKILL e2e smoke (1 chapter) | pass | pass | smoke 脚本 |
| 4 SKILL persona 渲染 snapshot | T0-prep 存 | byte-equal | regression-by-snapshot |
| 各模块单测覆盖率 | N/A | ≥ 95% | coverage |

## §8 Invariants (运行时 + 编译期)

```python
def _verify_mvp3_invariants(skill_loader: SkillLoader) -> None:
    """启动期 + 编译期不变量。"""
    # 1. SkillLoader 实例化没有副作用 (没写 sys.modules / sys.path / os.environ)
    # 2. compile_skill 是确定性函数 (同一 SKILL.md 输入 → 同一 SkillManifest 输出)
    # 3. 4 middleware 顺序不可改 (从 DEFAULT_MIDDLEWARE_ORDER 取)
    # 4. ModuleSandbox 解析的类对象不出现在 sys.modules (sandboxed)
    # 5. parse_skill_md 输入只有 str, 输出只有 dict (无对象引用)
```

## §9 风险点 + 回滚路径

### §9.1 风险

- **R1: persona 渲染细微差异 (Gemini Part G 警告)**
  - 缓解: T0-prep 存 4 SKILL persona 渲染快照, 验收阶段 byte-equal 比对
  - 触发: snapshot 不一致 = 必须回滚 persona 改动 (T5 最可能引入)
- **R2: middleware 顺序敏感性 (Gemini Part G)**
  - 缓解: conftest.py 加拓扑序回归 + 每次 PR review 强制看 DEFAULT_MIDDLEWARE_ORDER 改动
  - 触发: 顺序变化 = pytest 拓扑测试红
- **R3: ModuleSandbox 跟现有 SKILL 附件脚本 (skills/*/scripts/) 兼容性**
  - 缓解: T0-prep 列出当前 sys.modules 写入的所有路径, ModuleSandbox 必须支持每一条
  - 触发: 4 SKILL compile fail = 回退到旧 _resolve_output_schema_path
- **R4: a2 design A9 误读 (research D2)**
  - 缓解: research D2 已纠正, A9-bis (启动 hack) + A9-original (output_schema hack) 双线做
  - 触发: 实施时如果发现两线冲突 (例如启动 hack 清理后 _resolve_output_schema_path 仍被 bypass) = 主控介入决定优先级
- **R5: Loop Detection 在新 ExecutionControlMiddleware 下行为变化 (Gemini Part F T12)**
  - 缓解: T12 集成压测验证 (4 SKILL e2e 加压跑 10 次, 检测 loop 命中率不变)
  - 触发: 命中率变化 = 回滚 ExecutionControlMiddleware 的 loop detection 实现

### §9.2 回滚

MVP-3 拆 ~6 commit (按子任务粒度):
1. T1+T2 (Bootstrap + SkillManifest 模型)
2. T3+T4+T5 (三阶段 Pipeline + ModuleSandbox)
3. T6 (废弃旧 SkillLoader)
4. T7+T8+T9 (3 middleware 整合)
5. T10 (runner.py 清理)
6. T11+T12 (单测 + 集成压测)

任一 commit 后 4 SKILL e2e + pytest 退步, 回滚该 commit, 不影响前序。
