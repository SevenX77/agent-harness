# PR-4 递归编译防护与缓存链路修复要求 (Requirements)

## 1. 目标
修复 V0.3.0 引擎在深度嵌套图中表现出的致命缺陷，包含：修复由于 AST 缓存数据残缺引起的 “二次运行子 Agent 神秘消失” bug、拦截恶意或无意引入的死循环图编译栈溢出、消除深图重复编译以及增加针对缓存损坏的可观测性。

## 2. 具体要求与验收标准 (Acceptance Criteria)

### 2.1 AST 缓存忠实序列化 (Cache Roundtrip)
- **要求**: 
  - `_dehydrate_compiled_skill` 必须序列化并保存 `CompiledSkill` 中的 `phase_tokens` 和 `subagents_by_phase`。对于 `phase_tokens` 中的嵌套属性 `PhaseAttributeSpan` 需要显式拆解。
  - 在序列化 `subagents_by_phase` 列表中的 `CompiledSubagent` 对象时，必须忽略 `input_model` 字段。
  - `_rehydrate_compiled_skill` 必须从 Snapshot 中读回并**严格复原**（含深层 dataclass）这两个字段。针对 `CompiledSubagent`，必须在运行时调用现有的 `build_subagent_input_model(_subagent_input_model_name(parent_phase_id, name), input_schema)` 动态重塑 Pydantic BaseModel。
  - 缓存复水后，必须在返回前补齐漏掉的一步，即重新执行 `_inject_subagent_tools(tools, subagents_by_phase)` 将子 agent 动态桥接到 tools 注册表。
  - 必须在 `cache.py` 中的 `compute_cache_key` 中增加 `"format": "v2"` 强制缓存失效更新。
  - 必须在 `loader.py` 中为 `CompiledSubagent.input_model` 增加 `field(compare=False)` 防止不可比较的 type 对象引发测试断言失效。
- **验收**:
  - 创建一个携带 subagent 的 Skill 单元测试。验证第一次冷编译与第二次缓存命中的 `compile_skill()`，返回的 `CompiledSkill` 对象在片段上满足：`hit.subagents_by_phase == cold.subagents_by_phase`；`hit.tools` 按 ID 包含预期的 `call_subagent_<name>` 动态工具；`hit.phase_tokens` 内部结构（如 `PhaseAttributeSpan`）类型合法。不再断言不可达的整对象 `cold == hit`。

### 2.2 循环引用与递归上限拦截 (Cycle & Depth Guard)
- **要求**: 
  - 贯穿 `SkillLoader.compile_skill` 及 `graph_assembler.py` 内部执行装配阶段的地方（通过重构/包装提供可选传参），透传新参数 `_loading_stack: tuple[str, ...]` 与 `_compilation_cache: dict[str, CompiledSkill]`。其键值**必须固定为** `str(root.resolve())`。
  - **环检测**: 进入编译前，若当前绝对路径已存在于 `_loading_stack` 中，立即抛出附带 `[F-v3-compile-recursion-cycle]` 错误码的 `SkillLoadError`。
  - **上限防爆**: 若当前栈深度 `len(_loading_stack) >= 20`，在入栈前抛出附带 `[F-v3-compile-depth-exceeded]` 的 `SkillLoadError`。
  - 新增的两项错误码必须完整注册到 `src/graph_agent/core/error_registry.py`，配置对应的 level/stage/doc_link。同时修改 `tests/core/test_error_payload_contract.py` 的数量断言（改为 92）及在 `11-error-code-spec.md` 中进行补充说明。
- **验收**:
  - 构造相互引用的 Skill A 和 Skill B (A 包含 subagent B, B 包含 subagent A)。断言编译 A 时准确抛出 `SkillLoadError` 并匹配对应的 `[F-v3-compile-recursion-cycle]` code。

### 2.3 消除同图重复编译 (O(n) Compilation Redundancy)
- **要求**: 
  - 充分利用贯穿传导的 `_compilation_cache`，若同一绝对路径在当前次顶级图编译与装配的生命周期内被多次遇到，直接返回已编译结果引用，跳过所有 IO 与 AST 校验开销。
- **验收**:
  - 用 monkeypatch mock `compile_skill` 拦截或者拦截特定的 AST read 层，在执行包含 3 次引用同一个 subagent (目标 skill C) 的根图 A 的编译时，断言底层针对 C 的真实解析动作只被执行了 1 次。

### 2.4 缓存可观测性增强 (Cache Degrade Observability)
- **要求**: 
  - 在 `cache.py` 顶部实例化 `logger = logging.getLogger(__name__)`。修改 `:41` 处的拦截，在捕获各种解析或读取错误后，通过 `logger.warning` 打印错误原因。
- **验收**:
  - 单元测试或人工确认故意向 cache JSON 写坏字节时，系统能冷重编并通过 log 发出 WARNING，且不会令进程崩溃。
