# PR G (Schema Cleanup) Research

## 1. 现状调研 (基于 Import-Graph 与 V0.3.0 Ground-Truth 的重判)

针对 PR G (V0.3.0 hard cutover 尾声) 的 legacy 入口，本次调研摒弃了脆弱的 "string-match" 策略，严格基于 `import-graph` 可达性以及 V0.3.0 格式权威 (`00-FORMAT-GROUND-TRUTH.md`) 进行了重新评估。

### 1.1 `context_mapping` / `ContextResolver`
- **Grep 实证**: 扫描命中 `harness.py`, `runner.py`, `src/graph_agent/io/context_resolver.py`；validator 侧命中属于无 live caller 的死模块残留，不是 V0.3.0 wired 路径。
- **Ground-Truth 校验**: 阅读 `docs/engine/mvp0/skill-spec/00-FORMAT-GROUND-TRUTH.md`，V0.3.0 格式的 `io` 机制已改为 inline dict (基于 StateMapper)，frontmatter 中已彻底移除 `context_mapping`。
- **Import-Graph 校验**: `harness.py:361/372/852` 和 `runner.py` 仍在主动 import 并调用 `ContextResolver`。
- **状态判定**: **DEAD-BUT-WIRED (死且连线，可删但需全链路切除)**。
- **理由**: 在 V0.3.0 格式中已退役，但目前仍错误地挂载在主执行入口 (harness/runner) 和 Public API 上。清理时必须连同所有的入参和解析路径一同抹除。

### 1.2 `cognitive` 模块 (`finish.py`, `finish_task.py`, `md2json.py`, `md_patch.py`)
- **Import-Graph 校验**:
  - `finish.py` 被 V0.3.0 主路 `harness.py` 和 `llm_phase_node.py` 调用，`nudge_injector.py` 也在引用它。
  - `finish_task.py` 被 `graph_assembler.py` 引用。
  - `md2json.py` 和 `md_patch.py` 均为上述链条的底层依赖。
- **状态判定**: **LIVE (存活，严禁删除)**。
- **理由**: 它们是 V0.3.0 认知流和交卷机制的核心模块。docstring 中的 "v2.1" 或 "legacy" 字样为过渡期遗留的误导性注释。只应清理注释，不准删除模块本身或修改其核心逻辑。

### 1.3 `codemod` / `v21_migrator.py`
- **Import-Graph 校验**: `src/graph_agent/codemod/v21_migrator.py` 及其测试，无任何主路径 (non-test) 的 import。
- **状态判定**: **DEAD (该删)**。
- **理由**: 独立的一次性隔离迁移工具，且彻底无人调用。

### 1.4 `python_callable`
- **Ground-Truth 校验**: V0.3.0 LOGIC AST 中已被 `execute_steps` 替代。
- **Import-Graph 校验**: 仅存在于 `v21_migrator.py` 和旧版 schema/测试断言中。
- **状态判定**: **DEAD (该删)**。
- **理由**: V0.3.0 彻底弃用，无存活引用链。

### 1.5 `skill_builder.py` 中的 `<steps>` legacy
- **Ground-Truth 校验**: `00-FORMAT-GROUND-TRUTH.md` 明确规定："明令禁止复数壳 `<steps>`"。
- **状态判定**: **DEAD (该删)**。
- **理由**: V0.3.0 装配时已直接将单数标签脱壳渲染，`skill_builder.py` 遗留的硬编码 `<steps>` 组装逻辑必须切除。

### 1.6 `V2.1 e2e 测试群` (`test_*_v21.py`)
- **扫描结果**: 共计 26 个文件。
- **状态判定**: **逐案裁决 (Migrate/Delete)**。
- **理由**: 
  - 若其驱动的是已彻底废弃的旧 V2.1 AST (如 `test_v21_ast_schema.py`)，**直接删除**。
  - 若测试覆盖的是特定业务 fixture (如 `event_extraction`, `hello_world`)：
    - 若 V0.3.0 新版测试 (如 `test_round14_compiler_e2e.py`) 已经覆盖了该 fixture 的核心流，**删除该 V2.1 测试**。
    - 若尚无 V0.3.0 测试覆盖，则必须将其引擎调用点迁移至 V0.3.0 API，并重命名为 `_v030.py`。
  - `skills/` 下的多版本 fixture corpus 必须保留。
