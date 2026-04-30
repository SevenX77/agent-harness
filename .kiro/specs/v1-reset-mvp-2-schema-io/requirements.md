# MVP-2 Requirements — A5 SchemaEngine + A7 IOManager 抽出

## 背景

graph_agent v1-reset 序列 MVP-2 (依据 docs/superpowers/specs/2026-04-28-v1-reset-direction.md §4 MVP-2 + Appendix B A5/A7 维度)。MVP-1 (feat/v1-reset-mvp-1) 已把 WorkflowState 拆为 BusinessData / FrameworkState 物理隔离。MVP-2 在此基础上把"散落在 loader.py / finish.py / md_to_json.py / artifact_manager.py / phase_executor.py 等 5 处的 schema 解析 + io 路由逻辑"收拢成两个独立基础设施模块: SchemaEngine 和 IOManager。

## 业务目标

把 `output_schema` / `output_example` 的解析与校验逻辑从 5 处弥散路径收拢成 1 条明确路径 (`SchemaEngine`); 把 `io.outputs` / `hoist_to` 的定向搬运逻辑从 `loader.py` 硬编码 + `finish.py` 手工赋值 + `manager.py` 局部 resolver 收拢到 1 个明确职责模块 (`IOManager`)。让 `loader.py` 瘦身 >30%, `finish.py` 不再有 `state["data"][key] = ...` 手工赋值, 为 MVP-3 loader 重画 + MVP-4 phase_executor 拆分扫清前置障碍。

## EARS 需求

### Req 1 — SchemaEngine 模块存在

**WHEN** 任意运行时模块需要解析 SKILL.md 的 `output_schema` / `output_example` 字段，**THE SYSTEM SHALL** 提供 `src/core/graph_agent/core/schema_engine.py:SchemaEngine` 类，对外暴露:
- `parse_from_md(md_content: str) -> SchemaObject`: 把 SKILL.md 文本片段解析为内部 SchemaObject
- `get_pydantic_model(schema: SchemaObject) -> type[BaseModel]`: 把 SchemaObject 转为 Pydantic 模型类（含 cache）
- `validate(data: Any, schema: SchemaObject) -> ValidationResult`: 用 schema 校验业务数据
- `get_json_schema(schema: SchemaObject) -> dict`: 给 md_to_json prompt 渲染用的 JSON Schema 视图

### Req 2 — IOManager 模块存在

**WHEN** 任意运行时模块需要把 finish_task 输出按 `io.outputs` / `hoist_to` 搬到业务空间，**THE SYSTEM SHALL** 提供 `src/core/graph_agent/core/io_manager.py:IOManager` 类，对外暴露:
- `__init__(io_specs: list[IODef])`: 用 manifest 解析出的 IODef 列表初始化
- `resolve_hoist(source_data: dict, target_data: BusinessData) -> tuple[BusinessData, list[str]]`: 按 io_specs 把 source_data 字段搬到 target_data，返回更新后的 BusinessData + io_errors
- `validate_spec(spec: dict) -> tuple[bool, list[str]]`: 编译期校验 io_specs 合法性

### Req 3 — Schema 解析路径收拢

**WHEN** MVP-2 收尾，**THE SYSTEM SHALL** 满足:
- `src/core/graph_agent/core/loader.py` 内不再含 `re.compile(r".*output_schema.*")` 或 `json.loads(schema)` 直接解析逻辑
- `src/core/graph_agent/cognitive/finish.py` 内不再含 schema 字符串解析逻辑（全部委托 SchemaEngine）
- `src/core/graph_agent/tools/md_to_json.py` 通过 `SchemaEngine.get_json_schema` 取 prompt 视图，不再访问 `Manifest` 私有方法
- `src/core/graph_agent/core/artifact_manager.py` 旧 schema 解析逻辑（如有）全部移除

### Req 4 — IO 搬运路径收拢

**WHEN** finish_task 触发输出搬运，**THE SYSTEM SHALL** 通过 `IOManager.resolve_hoist` 完成以下全部动作:
- 从 `FrameworkState.finish_task_result` 读 source_data
- 按 io_specs 把字段搬到 BusinessData
- io_errors（缺失字段、类型不匹配等）写入 `FrameworkState.io_errors`（沿用 MVP-1 design §1.1 已声明字段）
- `cognitive/finish.py` 内不存在 `state["data"][key] = ...` 这种手工赋值

### Req 5 — 与 MVP-1 BusinessData / FrameworkState 对接

**WHEN** SchemaEngine / IOManager 跟状态层交互，**THE SYSTEM SHALL**:
- BusinessData 实例的字段类型由 `SchemaEngine.get_pydantic_model` 提供（动态字段 schema 注入），不破坏 `extra="allow"` 兼容性
- io_errors 写到 `FrameworkState.io_errors: list[str]`（MVP-1 已声明字段，不新加）
- 不引入任何 `_underscore` 字段污染 BusinessData

### Req 6 — ContextBridge 演化

**WHEN** SKILL.md 中含 sub-skill / context bridge 字段（V2 跨 skill 委派预留），**THE SYSTEM SHALL** 让 `core/manifest.py:ContextBridge` 降级为"视图层"——它通过调用 `SchemaEngine.get_pydantic_model` 获取目标 schema 类型，而不在自己内部含任何解析逻辑。

### Req 7 — Baseline diff 验证

**WHEN** MVP-2 收尾，**THE SYSTEM SHALL** 满足下列 baseline diff 指标:
- `loader.py` 行数减少比例 > 30%（baseline 由 T0 prep 测得）
- `finish.py` 行数减少 ≥ 80 行（schema 校验 + 搬运逻辑剥离）
- 解析路径数: 从 5 条弥散路径（manifest / loader / finish / md_to_json / artifact_manager）收拢为 1 条（loader → SchemaEngine → cache）
- pytest 全过（不退步），test_strict_v2 14 pre-existing failures 仍 isolated
- 4 核心 SKILL（text-segmentation v0/v1/v2/v3 + md-patch + finish-validator + clarification）compile 状态不变（WARN-only / 1 producer PASS）
- 4 SKILL e2e smoke 跑 1 chapter 不破裂

### Req 8 — SchemaEngine 单元测试覆盖

**WHEN** SchemaEngine 提供生产可用，**THE SYSTEM SHALL** 满足:
- 单元测试覆盖率 ≥ 95%（按 v1-reset-direction §7 工程门禁基线，新代码 strict scope）
- 至少 10 个畸形 SKILL.md 片段（缺字段 / 错类型 / 重复 key / output_example 缩进敏感等）的负向测试
- 至少 5 个合法片段的正向测试 + Pydantic round-trip 测试

### Req 9 — IOManager 单元测试覆盖

**WHEN** IOManager 提供生产可用，**THE SYSTEM SHALL** 满足:
- 单元测试覆盖率 ≥ 95%
- 覆盖场景: 字段缺失、类型不匹配、嵌套字段路径、batch hoist、空 io_specs

## Out of scope（MVP-2 不做）

- A2 loader.py 完整拆分为 Parser / ManifestValidator / ModuleSandbox / PhaseBuilder → MVP-3
- A9 `_resolve_output_schema_path` PEP 451 importlib 改写 → MVP-3
- A3 phase_executor 拆解 → MVP-4
- A4 finish_task 控制流原语化（不再是 LangChain Tool） → MVP-4
- A10 harness.run 拆解 → MVP-5
- 全库 mypy strict / ruff strict / coverage ≥85% 整体收紧 → MVP-5
- 4 SKILL e2e 全部断言（仅做 1 chapter smoke 不破裂） → MVP-5
- 旧 SKILL output_example 缩进敏感性的根治（MVP-2 期间保持完全一致的解析行为，不重写正则）→ MVP-3 / MVP-5
