# PR-3 Design v4: Persona与死码簇清理、旧入口收口与 Context 断层修复

## 1. 契约继承与变动表 (SOP-06)

本 PR **不修改**任何现有 Pydantic schema 或 API 字段，主要是对废弃代码的拆除和对缺失行为的补充（Additive）。

| 影响面 | 变更摘要 | 兼容性分类 | 迁移路径 |
| :--- | :--- | :--- | :--- |
| `build_graph_nodes` 死码簇 (含 Persona) | 彻底移除 `build_graph_nodes` 函数簇（含 `_inject_persona`, `_phase_from_*` 等）及 `TYPE_CHECKING` 中失效的 import。 | [BREAKING] | 此相关功能在 V0.3.0 早已被彻底废弃，属 100% 零 caller 的纯死码，直接安全拆除。 |
| `run_skill` (入口) | 对传入普通文件 (如单文件 `SKILL.md`) 时，内部拦截并返回包含明确 `[F-v3-]` Payload 的失败结果，不再因目录断层抛出深层 Python 异常。 | [COMPATIBLE] | **保留现有公开契约**：不会向调用方抛出异常，而是安全地返回 `WorkflowResult(success=False, error=...)`，调用方无需修改异常捕获代码。 |
| `Context` 类 | 增加 `__getitem__`, `__setitem__`, `__contains__`, `setdefault` 魔术方法。 | [NEW] | 向上兼容标准的 `dict` 操作语法。 |

## 2. 关键修复设计决策

### 2.1 `build_graph_nodes` 及其 Persona 死码簇整簇拆除 (Finding A & B)
**结论:** 经过实证，`skill_builder.py` 中的 `build_graph_nodes`、`_inject_persona` 及各类 `_phase_from_*` 等函数均无任何外部 caller，且其内部引用的 schema 类（如 `AgentSkillDef`, `LLMPhase` 等）在 V0.3 切量时已被删除。这不仅是 Persona 遗迹，更是只要调用就会触发 `ImportError` 的整块历史死码；同时 `TYPE_CHECKING` 块中引用的失效类名称亦会引发 mypy 检查失败。
**设计:** 
基于“干净拆除”和“零回归风险”，采取**PR-3 内整簇删除**策略：
1. 清空/删除 `core/personas.py` 文件及相关对外暴露。
2. 从 `skill_builder.py` 中连根拔起 `build_graph_nodes`、`_inject_persona`、`_phase_from_agent_manifest_for_nodes`、`_llm_phase_for_node`、`_phase_from_agent_skill`、`_phase_from_graph_phase` 等死码函数。
3. 清理 `skill_builder.py` 顶部的 `TYPE_CHECKING` 块，删除 `AgentSkillDef`, `LLMPhase`, `LogicPhase`, `PersonaSkillDef` 等失效的导入。
4. **测试迁移 (非删除):** `test_personas_relative_path.py`, `test_persona_resolution_validation_error.py`, `test_compile_skill_persona_resolution_integration.py` 实际上在守护 V2.1 root 的拒绝逻辑（`_guard_v030_root`）。**必须保留这些断言**，仅将测试名称“去 persona 化”（例如更名为 `test_guard_v030_root_rejection` 等），`adopted_persona` 只是作为测试数据载体，可留可换。

### 2.2 Context 门面兼容性 (最小覆盖补充)
**结论:** 活的 Action（例如被集成测试执行的 `score.py:2` fixture：`context["segments"]`）广泛使用了字典下标取值。
**设计:**
为避免过度设计，仅为 `Context` 补充能覆盖真实用例的 4 个方法，不要求全量实现 `MutableMapping`：
```python
def __getitem__(self, key: str) -> Any:
    if key not in self._blackboard:
        raise KeyError(key)
    return self._blackboard[key]

def __setitem__(self, key: str, value: Any) -> None:
    self.set(key, value)

def __contains__(self, key: str) -> bool:
    return self.has(key)

def setdefault(self, key: str, default: Any = None) -> Any:
    if not self.has(key):
        self.set(key, default)
    return self.get(key)
```

### 2.3 `run_skill` 入口 Fail-Loud 与 `md_to_json` 防御
**问题:** `run_skill` 对旧的单文件 `SKILL.md` 处理混乱；`md_to_json.py` 指向了因工具签名而被新引擎禁止的旧版 `md-patch` 技能。
**设计:**
1. **`run_skill` 干净失败 (Finding C 与遗迹清理):** 在 `_run_skill_dict` 开头，若 `skill_path` 不是包含 `GRAPH.md` 的文件夹，立刻抛出附带 `[F-v3-...]` Payload 的 `SkillLoadError`。由于 `run_skill` 包装层（`runner.py:213`）会将其转换为 `error=str(exc)`，要求底层 `make_error_payload` 生成的 `SkillLoadError` 的 `str()` 表达必须包含 `code` 文本本身，这样公开调用方才会获得包含此标准错误码的 `WorkflowResult(success=False)`。**同时记录：**在此入口 guard 落地后，`_run_skill_dict` 下方原用于处理非 `GRAPH.md` 的 legacy 执行体（包括 `harness` 缓存、基于 `.run_id` 文件的断点续传、旧版 predict 绑定等共计 182 行）在逻辑上已成为不可达的死码。本 PR 按照“干净拆除”原则，将其连同一并整段移除，彻底关停旧版 Harness 路径。
2. **`md_to_json` Deferred Path Guard:** 将彻底修复 `md_to_json` 和 `md-patch` 的重任**显式延后到 PR-6**。但在本 PR 中必须补上一条防御：当 `md_to_json` 调用 `run_skill` 后，必须检查 `result.success`；如果为 `False`（例如因上述拦截导致），则立即抛出清晰的 `SkillLoadError` 或不支持的异常，**严禁裸漏 `KeyError("final_results")`**。

## 3. Tests-First 策略 (诚实红灯)

1. **Context 红灯:** 编写针对 `Context` 类的单元测试，以及**至少一个运行逻辑 Action 的集成测试（例如触发 `score.py`）**，断言在使用下标访问和 `setdefault` 时能够通过（初始跑将抛出 `TypeError`）。
2. **run_skill 干净拦截红灯:** 编写测试（独立于上述被迁移的 3 个测试），直接调用 `run_skill("SKILL.md")`。断言 `run_skill` **返回**的 `WorkflowResult.success == False` 并且 `error` payload 字符串中包含预期的 `[F-v3-...]` 错误码（当前因内部 KeyError 抛错无法稳定返回此类 error，且有 `str(exc)` 隐藏真实 code 的隐患）。
3. **Deferred Path Guard 红灯:** 针对 `md_to_json` 工具，构造强制走 patch 路径的数据，断言它在拦截到 `run_skill` 失败后抛出带清晰消息的 `SkillLoadError`，而不是 `KeyError`。
4. **RG Gate 归零约束:** PR 验收时，必须确保 `rg "build_graph_nodes|_inject_persona|PersonaSkillDef|adopted_persona|resolve_persona|core\.personas" src/graph_agent tests` 输出为空，杜绝死代码及死链接残留。同时确认 `skill_builder.py` 的 mypy 检查绿灯。
