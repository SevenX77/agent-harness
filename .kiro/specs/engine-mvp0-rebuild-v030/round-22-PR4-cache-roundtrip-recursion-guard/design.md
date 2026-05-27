# PR-4 递归编译防护与缓存链路修复设计 (Design)

## 1. 契约继承与变动表 (SOP-06)

本 PR 聚焦于引擎编译期缓存（Cache Roundtrip）及递归编译（Recursive Compilation）链路的修复。属于 charter 范围内的 A 类授权项。

### 1.1 CompiledSkill 与 Cache Snapshot 字段继承表

当前 `CompiledSkill` 包含以下字段：
- `raw: dict[str, Any]` (保留)
- `manifest: GraphManifest` (保留)
- `nodes: list[PhaseDocument]` (保留)
- `actions: ActionRegistry` (保留，原本就由 rehydrate 动态重建)
- `tools: ToolRegistry` (保留，原本就由 rehydrate 动态重建)
- `subagents_by_phase: dict[str, list[CompiledSubagent]]` (**[BREAKING]** 需加入缓存 Snapshot)
- `phase_tokens: dict[str, PhaseTokenInfo]` (**[BREAKING]** 需加入缓存 Snapshot)

| 影响面 | 变更摘要 | 兼容性分类 | 迁移路径 |
| :--- | :--- | :--- | :--- |
| **Cache Key** | 在 `compute_cache_key` 中加入 `"format": "v2"` | [BREAKING] | 自动让旧的失效，重新触发冷编译，无平滑迁移成本。 |
| **Cache Snapshot** | 新增 `subagents_by_phase` 与 `phase_tokens` 节点的序列化。由于 `CompiledSubagent.input_model` (Pydantic type) 不可被 JSON 序列化，Snapshot 中将其剥离，Rehydrate 时通过 `build_subagent_input_model` 动态重建。 | [BREAKING] | 随 Cache Key `v2` 一并更新。 |
| **CompiledSubagent** | 为 `input_model` 字段增加 `field(compare=False)` | [BREAKING] | 修复因 `type[BaseModel]` 导致的对象判等失败（确保复水后缓存的 `CompiledSkill` 能通过片段的 `hit.subagents_by_phase == cold.subagents_by_phase` 测试。注：由于 `actions` 和 `tools` 是不可原样复原身份的动态实例，整对象 `cold == hit` 是结构性不可达的已知行为，故验收需转为片段断言）。 |
| **SkillLoader 递归参数** | `SkillLoader.compile_skill` 新增内部参数 `_loading_stack: tuple[str, ...]` 与 `_compilation_cache: dict[str, CompiledSkill]` | [COMPATIBLE] | 默认参数为 `()` 和 `None`，不影响外部公开 `compile_skill` 门面调用。栈中记录的 key 统一为 `str(root.resolve())`。 |
| **错误码与 Registry** | 新增 `[F-v3-compile-recursion-cycle]` 与 `[F-v3-compile-depth-exceeded]`，并在 `ERROR_REGISTRY` (`error_registry.py`) 注册 | [NEW/BREAKING] | 必须在 `docs/engine/skill-spec/11-error-code-spec.md` 补充定义。同时更新 `tests/core/test_error_payload_contract.py` 中的断言（`len(...) == 92`）以维护契约测试绿灯。 |

## 2. 关键修复设计决策

### 2.1 [Must-Fix] 缓存不忠实导致 subagent 静默丢失
**结论:** 缓存脱水 (`_dehydrate_compiled_skill`) 与复水 (`_rehydrate_compiled_skill`) 遗漏了 V0.3 新增的 `subagents_by_phase` 和 `phase_tokens`。当缓存命中时，`CompiledSkill` 中的这两项变为空，不仅丢失了 Token 溯源信息，更导致 `loader.py:196` 的 `_inject_subagent_tools`（依赖 `subagents_by_phase`）失效，从而在二次编译时 subagent 神秘消失。
**设计:**
1. 在 `cache.py` 的脱水逻辑中，将 `phase_tokens` 转化为可序列化字典。需注意嵌套的 `attr_spans` 也需要被递归地处理。
2. 将 `subagents_by_phase` 脱水，但**显式剔除** `CompiledSubagent` 中的 `input_model` 字段（它是 type 对象，无法序列化）。
3. 在复水逻辑中，还原这些字段，并调用现有的 `build_subagent_input_model(_subagent_input_model_name(parent_phase_id, name), input_schema)` 动态重建 `input_model` 字段。
4. **关键修复:** 重建 `subagents_by_phase` 后，必须重新调用 `_inject_subagent_tools(tools, subagents_by_phase)` 来恢复 `tools` 注册表中的动态子代理工具绑定。
5. 修改 `compute_cache_key` 中的 payload，增加 `"format": "v2"` 来强行作废现有存在缺陷的本地缓存。
6. 为 `CompiledSubagent.input_model` 标记 `field(compare=False)`，使得片段判等 `cold.subagents_by_phase == hit.subagents_by_phase` 能够合法通过。**注意：** 因为 `CompiledSkill` 包含的 `actions` 和 `tools` 均为每次冷/热编译新生成的实例且均未实现值比较，整对象判等 `cold == hit` 是结构上必定为 False 的（预期内行为），故在测试层应当采用逐片段的正向断言（例如检查 `hit.tools` 中是否含特定工具标识，及验证 `hit.phase_tokens` 类型），代替笼统的 `cold == hit`。

### 2.2 [High] 递归编译无防护与深树 O(n) 冗余编译
**结论:** `SkillLoader` 和 `assemble_graph` 在解析/装配 `SUBGRAPH` 和 `subagent` 时，会递归实例化新的 `SkillLoader().compile_skill(...)`。这既没有传递已访问路径（有向有环图引发原生 `RecursionError`），又绕过了上层共享缓存导致 O(n) 重复编译。
**设计:**
1. **统一 Key 与透传状态**: `_loading_stack` 和 `_compilation_cache` 均使用 `str(root.resolve())` 的绝对路径字符串作为唯一 Key。在所有 `SkillLoader().compile_skill` 的调用点（包含 `graph_assembler.py` 中的 `_build_subgraph_node` 和装配 subagent 时）透传这两个参数（在 API 面增加对应私有参数或包装）。
2. **环检测**: 进入编译时，检查当前 `str(root.resolve())` 是否在 `_loading_stack` 中。若存在，立即抛出附带 `[F-v3-compile-recursion-cycle]` 的 `SkillLoadError`。
3. **深度上限**: 在 push 当前 root 到栈之前，检查 `len(_loading_stack) >= 20`（20 是安全的，普通业务图/子代理的逻辑深度不会到达此阈值）。若超过，抛出附带 `[F-v3-compile-depth-exceeded]` 的 `SkillLoadError`。
4. **同图缓存复用**: 若该 `root` 绝对路径已在 `_compilation_cache` 中，则直接返回其 `CompiledSkill` 引用，消除冗余编译。

### 2.3 [Low] 缓存损坏静默 Miss 无日志
**结论:** `cache.py:41` 在遇到 `json.JSONDecodeError`、`TypeError` 等文件损坏情况时，直接 `return None`。这让潜在的 Schema 破坏不可观测。
**设计:**
在 `cache.py` 中补充 `logger = logging.getLogger(__name__)`。在 `except` 块中加入 `logger.warning("[Cache] Failed to load cached compiled skill %s: %s", key, exc)`。维持 `return None` 降级为冷编译的行为，但保证异常情况能留在应用日志中供排查。
