# MVP-2 Design — A5 SchemaEngine + A7 IOManager 抽出

> 整合 Gemini independent design (job_dc2b328ebc8e Part B-G) + 主控决策（research.md D1-D8）+ MVP-1 design 对接。

## §1 SchemaEngine 接口

### §1.1 文件位置 + 类签名

```python
# src/core/graph_agent/core/schema_engine.py
from __future__ import annotations
from dataclasses import dataclass
from functools import lru_cache
from typing import Any
from pydantic import BaseModel


@dataclass(frozen=True)
class SchemaObject:
    """中间表示: 解析后的 schema 抽象, 跨 SchemaEngine 函数传递。
    
    frozen=True 让 SchemaObject 可 hash, 用于 lru_cache key。
    """
    fields: tuple[tuple[str, type], ...]  # (field_name, python_type) tuples
    required: frozenset[str]
    output_example_md: str | None  # 原始 output_example 文本片段
    raw_schema_dict: dict[str, Any]  # 原 schema dict 备份, 给 md_to_json 用


@dataclass(frozen=True)
class ValidationResult:
    """validate() 返回值。"""
    ok: bool
    errors: tuple[str, ...]
    parsed: dict[str, Any] | None  # 校验通过时的字段 dict


class SchemaEngine:
    """统一处理 SKILL.md output_schema/output_example 的解析、校验、转换。
    
    替代散落在 loader/finish/md_to_json/manifest/artifact_manager 5 处的解析逻辑。
    """

    def parse_from_md(self, md_content: str) -> SchemaObject: ...
    def get_pydantic_model(self, schema: SchemaObject) -> type[BaseModel]: ...
    def validate(self, data: Any, schema: SchemaObject) -> ValidationResult: ...
    def get_json_schema(self, schema: SchemaObject) -> dict[str, Any]: ...
    def validate_spec_dict(self, spec: dict[str, Any]) -> tuple[bool, list[str]]: ...
```

### §1.2 各方法行为

| 方法 | 输入 | 输出 | 内部行为 |
|---|---|---|---|
| `parse_from_md` | SKILL.md 中 `output_schema:` / `output_example:` 字段下的文本片段 | SchemaObject | 复用 loader.py 现有正则 (D7), 提取字段名+类型+required, 不重写 |
| `get_pydantic_model` | SchemaObject | `type[BaseModel]` (动态生成的 Pydantic 类) | 用 `pydantic.create_model` 构造, lru_cache on schema id |
| `validate` | data 任意 dict, schema SchemaObject | ValidationResult | 调用 get_pydantic_model().model_validate, 失败时返 errors list |
| `get_json_schema` | SchemaObject | dict (JSON Schema 格式) | 调用 get_pydantic_model().model_json_schema(), 给 md_to_json prompt |
| `validate_spec_dict` | 原 manifest dict | (ok, errors) | 编译期校验 manifest 中 output_schema 字段格式合法 |

### §1.3 Cache 策略

```python
@lru_cache(maxsize=128)
def _get_pydantic_model_cached(schema_hash: str) -> type[BaseModel]:
    schema = self._schema_registry[schema_hash]
    return create_model(
        f"BusinessSchema_{schema_hash[:8]}",
        **{name: (typ, ... if name in schema.required else None) for name, typ in schema.fields},
    )

def get_pydantic_model(self, schema: SchemaObject) -> type[BaseModel]:
    h = hashlib.sha256(repr(schema).encode()).hexdigest()
    self._schema_registry[h] = schema  # 保引用避免 GC
    return self._get_pydantic_model_cached(h)
```

## §2 IOManager 接口

### §2.1 文件位置 + 类签名

```python
# src/core/graph_agent/core/io_manager.py
from __future__ import annotations
from typing import Any
from .state import BusinessData, FrameworkState
from .manifest import IODef
from .schema_engine import SchemaEngine, SchemaObject


class IOManager:
    """根据 SKILL.md io.outputs 把 finish_task 输出搬运到 BusinessData。
    
    替代 loader 硬编码 hoist_to + finish.py 手工赋值 + tools/io/manager.py 局部 resolver。
    """

    def __init__(
        self,
        io_specs: list[IODef],
        schema_engine: SchemaEngine,
    ) -> None: ...

    def resolve_hoist(
        self,
        source_data: dict[str, Any],
        target_data: BusinessData,
        target_schema: SchemaObject | None = None,
    ) -> tuple[BusinessData, list[str]]: ...

    def validate_spec(self, spec: dict[str, Any]) -> tuple[bool, list[str]]: ...
```

### §2.2 各方法行为

| 方法 | 输入 | 输出 | 行为 |
|---|---|---|---|
| `__init__` | io_specs (manifest 解析结果) + schema_engine | None | 缓存 io_specs, 持有 schema_engine 引用做类型预检 |
| `resolve_hoist` | source_data (来自 FrameworkState.finish_task_result), target_data (BusinessData), target_schema (可选, 用于类型预检) | (新 BusinessData, io_errors) | 按 io_specs 把 source_data 字段搬到 target_data, 类型不匹配时记 io_errors |
| `validate_spec` | 原 manifest io_specs dict | (ok, errors) | 编译期校验 io_specs 合法性 (路径合法、字段名合法等) |

### §2.3 数据流

```
LLM finish_task call
   ↓ (生成 dict)
StateManager.route_finish_task
   ↓ (写到 FrameworkState.finish_task_result)
phase_executor (phase 收尾)
   ↓ (调用 io_manager.resolve_hoist)
IOManager.resolve_hoist(source=flow.finish_task_result, target=state["data"])
   ↓
state["data"] (新 BusinessData) + flow.io_errors (累积 io_errors list)
```

## §3 ContextBridge 演化

### §3.1 当前 (MVP-1 后)

`src/core/graph_agent/core/manifest.py:138-150`:

```python
class ContextBridge(BaseModel):
    model_config = ConfigDict(extra="forbid")
    inputs: dict[str, str] = Field(default_factory=dict)
    outputs: dict[str, str] = Field(default_factory=dict)
```

仅 schema 占位, V2 跨 skill 委派复用。MVP-1 design §5.1 提到将增加 `to_business_data_schema()` 方法。

### §3.2 MVP-2 改造

按 research D2: ContextBridge 不合并到 SchemaEngine, 但内部所有 schema 相关动作通过 SchemaEngine 中介:

```python
class ContextBridge(BaseModel):
    model_config = ConfigDict(extra="forbid")
    inputs: dict[str, str] = Field(default_factory=dict)
    outputs: dict[str, str] = Field(default_factory=dict)

    def to_business_data_schema(
        self, schema_engine: SchemaEngine
    ) -> SchemaObject:
        """通过 SchemaEngine 取目标 BusinessData 的 schema。
        
        当前实现可以是简化版 (返回空 SchemaObject), V2 委派启用时再补完。
        """
        ...
```

ContextBridge 内不含任何 markdown 解析、Pydantic 类构造逻辑。

## §4 loader.py / finish.py 改造点

### §4.1 loader.py 改造

**当前**: schema 解析逻辑硬编码（`re.compile` / `json.loads` 散落多处）。

**改造后**:
```python
# src/core/graph_agent/core/loader.py 顶部
from .schema_engine import SchemaEngine

class SkillLoader:
    def __init__(self):
        self._schema_engine = SchemaEngine()

    def compile_skill(self, skill_path: str) -> CompiledSkill:
        # ... 读取 SKILL.md ...
        for phase in manifest.phases:
            if phase.output_schema:
                schema_obj = self._schema_engine.parse_from_md(phase.output_schema)
                phase.compiled_schema = schema_obj  # 存 SchemaObject 不存 dict
        # ...
```

**验收**: `grep -E 're\.compile|json\.loads' src/core/graph_agent/core/loader.py` 在 schema 解析相关上下文 0 hits（其他用途如 import path 仍可保留）。

### §4.2 finish.py 改造

**当前** (cognitive/finish.py): finish_task 工具调用时手动把字段移到 context。

**改造后**:
```python
# src/core/graph_agent/cognitive/finish.py
from ..core.io_manager import IOManager
from ..core.schema_engine import SchemaEngine

def finish_task(ctx, *, business_data_md, diagnostics_md):
    # 1. 解析 business_data_md → dict (现有逻辑保留)
    parsed_dict = _md_to_dict(business_data_md)

    # 2. 通过 SchemaEngine 校验
    schema = ctx.get_compiled_schema()  # 由 phase_executor 注入
    result = schema_engine.validate(parsed_dict, schema)
    if not result.ok:
        return {"errors": result.errors}

    # 3. 不再手动赋值 — 把 result.parsed 写到 finish_task_result, 
    #    由 phase_executor 触发 IOManager.resolve_hoist
    return {"finish_task_result": result.parsed, "diagnostics": diagnostics_md}
```

**验收**: `grep -E 'state\["data"\]\[.*\] *=' src/core/graph_agent/cognitive/finish.py` 0 hits。

### §4.3 phase_executor.py 改造（最小改动）

phase_executor 在 phase 收尾时调用 IOManager:

```python
# src/core/graph_agent/core/phase_executor.py (在 LLM phase 收尾段)
finish_result = state["flow"].finish_task_result
if finish_result and self._io_manager is not None:
    new_data, io_errors = self._io_manager.resolve_hoist(
        source_data=finish_result,
        target_data=state["data"],
        target_schema=phase.compiled_schema,
    )
    state = StateManager.update_business(state, **new_data.model_dump())
    if io_errors:
        existing = list(state["flow"].io_errors)
        state = StateManager.update_framework(
            state, io_errors=existing + io_errors
        )
```

注意: phase_executor 整体重画归 MVP-4, MVP-2 只加这一段调用。

## §5 跟 MVP-1 BusinessData 对接

### §5.1 BusinessData 子类工厂

新增 `core/state.py:build_business_data_for_skill`（不破坏 MVP-1 BusinessData 基类）:

```python
def build_business_data_for_skill(
    skill_manifest, schema_engine: SchemaEngine
) -> type[BusinessData]:
    """根据 SKILL output_schema 动态生成 BusinessData 子类。"""
    if not skill_manifest.output_schema_md:
        return BusinessData  # 老 SKILL 无 schema, 用基类
    schema = schema_engine.parse_from_md(skill_manifest.output_schema_md)
    pydantic_model = schema_engine.get_pydantic_model(schema)
    return create_model(
        f"BusinessData_{skill_manifest.name}",
        __base__=BusinessData,
        **pydantic_model.model_fields,
    )
```

### §5.2 loader 用此工厂构造 initial_state

```python
# loader.compile_skill (改造后伪代码)
business_cls = build_business_data_for_skill(manifest, schema_engine)
initial_state["data"] = business_cls(**user_inputs)
```

### §5.3 io_errors 写入 FrameworkState

按 research D6, 全部写到 `state["flow"].io_errors: list[str]`（MVP-1 已声明字段）, 不用 metrics 子键。

## §6 Baseline diff 验证

| 指标 | Baseline (T0 prep 测) | After MVP-2 | 验证命令 |
|---|---|---|---|
| `loader.py` 总行数 | (T0 prep 测) | 减少 ≥ 30% | `wc -l src/core/graph_agent/core/loader.py` |
| `finish.py` 总行数 | (T0 prep 测) | 减少 ≥ 80 | `wc -l src/core/graph_agent/cognitive/finish.py` |
| schema 解析路径数 | 5 | 1 (SchemaEngine) | grep schema regex/json.loads 站点统计 |
| `loader.py` 中 `re.compile.*output_schema` | (T0 prep 测) | 0 | grep |
| `finish.py` 中 `state\["data"\]\[.*\] =` | (T0 prep 测) | 0 | grep |
| `tools/md_to_json.py` 访问 Manifest 私有方法 | (T0 prep 测) | 0 (改用 SchemaEngine.get_json_schema) | grep |
| pytest 全过 (--ignore test_strict_v2) | 599 (MVP-1 baseline) | ≥ 599 + 新单测 | pytest |
| 4 SKILL compile 状态 | WARN-only / 1 PASS | unchanged | scripts/compile_all.py |
| 4 SKILL e2e smoke (1 chapter) | pass | pass | smoke 脚本 |
| SchemaEngine 单元测试覆盖 | N/A | ≥ 95% | coverage |
| IOManager 单元测试覆盖 | N/A | ≥ 95% | coverage |

## §7 跟 MVP-3 接口约定

### §7.1 MVP-3 启动前的契约

- loader.py 内**不再**含任何 schema 文本 → dict 的 regex 或 json.loads 解析（MVP-2 已剥离）
- loader.py 中 schema 流转只通过 `SchemaObject` 对象, 不传 raw dict / str
- output_schema 路径解析（A9 hack）**仍在 loader 内**, 不归 SchemaEngine 管（A9 是路径问题, A5 是内容问题）

### §7.2 MVP-3 时 loader 拆解 (Parser / ManifestValidator / ...)

- `Parser` 读 SKILL.md, 调用 `SchemaEngine.parse_from_md` 把 schema 文本转 SchemaObject
- `ManifestValidator` 调用 `SchemaEngine.validate_spec_dict` 编译期校验
- `PhaseBuilder` 把 SchemaObject 注入 Phase 对象, 跨 phase 流转

### §7.3 SchemaEngine 单例 vs 多实例

**MVP-2 决定**: 每次 `SkillLoader.__init__` 创建一个 SchemaEngine 实例, **不**做全局单例。

**理由**: 
- 不同 SKILL 可能有不同 schema 注册库, 隔离更安全
- lru_cache 在实例方法上是 per-instance, 不会污染
- MVP-3 时如果发现需要单例可以再改, MVP-2 不做过度设计

## §8 Invariants（运行时检查）

```python
def _verify_mvp2_invariants(state: WorkflowState, io_manager: IOManager) -> None:
    """MVP-2 启动期 + phase 收尾期必过的不变量。"""
    # 1. SchemaEngine 解析后的 SchemaObject 是 frozen
    # 2. IOManager 持有的 io_specs 不在运行时被 mutate
    # 3. io_errors 只增不减 (累积语义)
    assert isinstance(state["flow"].io_errors, list)
    # 4. BusinessData 子类的字段 schema 来自 SchemaEngine, 不是别处构造
    # 5. finish.py 不直接修改 state["data"] (通过 IOManager.resolve_hoist 间接修改)
```

## §9 风险点 + 回滚路径

### §9.1 风险

- **R1: output_example 缩进解析破坏 (Gemini Part F 警告)**
  - 缓解: T1 完全复制现有正则, 不重写; 新增 4 SKILL 的 compile 单测对比 baseline
  - 触发: 4 SKILL compile WARN/PASS 状态变化 = 必须回滚 T1 改动
- **R2: BusinessData 子类 + extra="allow" 互动**
  - 缓解: T2 单测覆盖动态字段+任意附加字段共存场景; 测 model_dump round-trip
  - 触发: pytest 退步 = 回滚 T2
- **R3: IOManager 类型预检过严卡死老 SKILL**
  - 缓解: 类型预检失败时降级为"记 io_errors + 仍执行搬运" (warning 模式), 不抛错
  - 触发: 4 SKILL e2e smoke 失败 = 把类型预检改为 advisory mode
- **R4: SchemaEngine 单例还是多实例选错**
  - 缓解: 设计层选 per-instance, 行为通过单测约束
  - 触发: 实测发现性能问题或类身份不一致 = 改单例（小改动）

### §9.2 回滚

MVP-2 拆 4 commit:
1. T1+T2 (SchemaEngine 创建)
2. T3 (IOManager 创建)
3. T4-T7 (调用方改造)
4. T8 (单测补全)

任一 commit 后 4 SKILL e2e + pytest 退步, 回滚该 commit, 不影响前序。
