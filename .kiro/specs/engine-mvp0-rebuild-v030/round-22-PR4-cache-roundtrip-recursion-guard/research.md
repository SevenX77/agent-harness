# PR-4 递归编译防护与缓存链路修复 (Research)

## 1. 核心问题定位实证

### 1.1 缓存的 `CompiledSkill` 丢失信息
- **涉及文件**: `packages/graph-agent/src/graph_agent/core/cache.py` (L81-123)
- **事实依据**:
  `_dehydrate_compiled_skill` 中硬编码了返回字典只包含 `raw`, `manifest`, `nodes`。
  `_rehydrate_compiled_skill` 在重建 `CompiledSkill` 时，利用 snapshot 创建实例，由于缺漏，`subagents_by_phase` 和 `phase_tokens` 这两个带有默认空字典的字段在复水后变为空。对于 `phase_tokens`，其深层结构包含了嵌套的 `PhaseAttributeSpan` frozen dataclass，使用 `dataclasses.asdict` 会连同里层一起字典化，因此在复水时必须显式重构嵌套的数据类 (Finding D1)。
- **关联影响**: `loader.py:196` 会通过 `_inject_subagent_tools(tools, subagents_by_phase)` 将子 agent 作为工具绑定。如果冷编译因为未缓存拿到了正确值，工具存在；如果是缓存命中，`subagents_by_phase` 是空字典，或者没有在缓存命中后重新执行 `_inject_subagent_tools` (Finding D2)，则工具丢失，这是极其危险的静默正确性回归（Silent correctness regression）。

### 1.2 递归调用的死循环与冗余问题
- **涉及文件**: `packages/graph-agent/src/graph_agent/core/loader.py` (L499, L565) 以及 `packages/graph-agent/src/graph_agent/core/graph_assembler.py` (L254, L913)
- **事实依据**:
  当引擎处理 SUBGRAPH 节点或 Agent 节点的 subagents 声明时，以及在装配图（`assemble_graph` 链路）需要编译下层节点时，会直接调用：
  ```python
  child = SkillLoader(validate_context_writes=False).compile_skill(child_root, skill_resolver=resolver)
  ```
  这里**重新实例化**了 `SkillLoader`，且没有传递任何关于当前已编译链路的 `_loading_stack` 与 `_compilation_cache` 状态。
  - **无状态 (M2)**: 不仅是 loader.py 内部，装配器 `graph_assembler.py` 也在实例化新的 Loader。如果没有打通这一层，即使编译期拦截了，在装配期 A 调用 B，B 又引用 A 仍会陷入死循环，最终引发 `RecursionError`，掩盖框架的 `[F-v3-...]` (Finding D6 `SkillLoadError`) 错误体系。递归路径中的 key 判定必须严格使用 `str(root.resolve())` 防止别名绕过 (Finding D4)。
  - **无缓存**: 因为是新实例，同一个子 agent 若在 3 个不同阶段被引用，会在单次图编译与装配中被执行 3 次完整的 AST 冷解析与 Schema 校验，造成极大的 O(n) 开销。栈深度校验应使用 `len(_loading_stack) >= 20` 作为拦截阈值 (Finding D5)。

### 1.3 `cache.py` 静默吞错
- **涉及文件**: `packages/graph-agent/src/graph_agent/core/cache.py` (L41)
- **事实依据**:
  ```python
  except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError):
      return None
  ```
  没有任何 `logging` 输出（当前文件甚至缺失 `logger = logging.getLogger(__name__)`，Finding D7）。当文件系统故障或者某次由于 Pydantic 升级导致反序列化 `TypeError` 爆发时，系统会表现为“永远不命中缓存”且排查无门。按照成熟系统的 Logging discipline，这必须发出 `WARNING` 级别日志。

## 2. Pydantic 模型与 Dataclass 序列化限制
在 `loader.py` 中：
```python
@dataclass(frozen=True)
class CompiledSubagent:
    # ...
    input_model: type[BaseModel]
```
`input_model` 是 `type[BaseModel]`，即 Python 类。这是不可序列化的。脱水时必须抛弃，而在复水时，必须使用官方规范的方法 `build_subagent_input_model(_subagent_input_model_name(parent_phase_id, name), input_schema)` 来保障与框架生成模型的行为完全一致，绝不可私自用 `create_model` 造轮子 (Finding D3)。
同时，因其为 `type` 对象重建后 `id()` 改变，为保证 `cold == hit`，此字段需添加 `field(compare=False)` (Finding M3)。
