# PR G 实施要求 (Requirements)

## 范围边界
本 PR 仅做“减法”和“平替”，不引入新的 V0.3.0 功能特性。只执行 V0.3.0 收尾所需的死代码清理，严守 Import-Graph 与 Ground-Truth 判定基准。

## 具体执行点

1. **Codemod 清理**
   - 删除整个 `src/graph_agent/codemod/` 目录。
   - 删除 `tests/core/test_v21_codemod.py` 及专属的 `codemod_v20` 隔离 fixture（不影响通用业务 fixture 的前提下）。

2. **Context Mapping 切断**
   - 删除 `src/graph_agent/io/context_resolver.py`。
   - 从 `harness.py` 的 `__init__` 和 `run` 相关方法中剔除 `context_mapping` 入参及其对 `ContextResolver` 的调用。
   - 从 `runner.py`、`GraphSkillDef` 以及相关的 validators (`prompt_quality.py`, `template_variables.py`) 中移除所有的 `context_mapping` 参数和解析调用。
   - 从 `io/__init__.py` 等顶层出口移除相关的 export。

3. **Cognitive 模块注释放毒 (Do Not Delete Logic)**
   - **绝对禁止**删除 `cognitive/finish.py`, `finish_task.py`, `md2json.py`, `md_patch.py` 及相关核心文件。
   - 仅限：修改上述文件中的 docstring，删除 "V2.1", "legacy" 等不符合其 V0.3.0 主干身份的误导性词汇。

4. **`<steps>` & `python_callable` 清除**
   - 彻底移除 `skill_builder.py` 中的 `<steps>` 字符串拼装逻辑（因其违反了 V0.3.0 禁复数壳的要求）。
   - 在 JSON Schema 与相关遗留的烟雾测试中，清除所有对 `.ast.python_callable` 字段的赋值与断言。

5. **V2.1 Tests 清理与迁移**
   - 盘点 26 个 `tests/**/test_*v21*.py` 文件。
   - **直接删除**: 验证已退役架构的 `tests/core/test_v21_*.py`。
   - **智能判定 e2e**: 逐个检查 `tests/e2e/test_*_v21.py`。如果 V0.3.0 测试 (如 `test_round14_compiler_e2e.py`) 已经覆盖该技能流，则直接删除该旧文件。如果没有覆盖，必须将其迁移为 V0.3.0 engine 的驱动方式并重命名为 `_v030.py`。
   - **红线警告**：严禁修改或误删 `skills/` 下的任何多版本业务语料（fixture corpus）。
