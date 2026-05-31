# PR G (Schema Cleanup) 设计方案

## §0.1 设计原则 (Hard Cutover)
PR G 是 V0.3.0 引擎重建的收官之战。核心目标是清理真正退役的旧格式字段与死代码。判定“死与活”必须严格依赖 **V0.3.0 Ground-Truth 格式规范**和 **Import-Graph 可达性**。严禁仅凭误导性的 "legacy/v2.1" 注释进行盲删。删除时必须执行 "Cutover Discipline"：同步清理测试、入口和 API 暴露点。

## §0.5 继承字段表 (Schema Cleanup)

| Schema 字段 / 模块 / 机制 | V0.3.0 现状 (Import / Ground-Truth) | 目标动作 | 分类 |
| --- | --- | --- | --- |
| `context_mapping` | **Dead-but-wired**: 格式已剔除，但 harness/runner 仍在显式传参引用 | **彻底移除**。切断 harness/runner 及 API 暴露点 | A类 |
| `cognitive` 模块群 | **LIVE**: V0.3.0 主干 (`llm_phase_node.py` 等) 强依赖 | **保留模块**。仅清理 docstring 的误导字眼 | N/A |
| `python_callable` | **Dead**: 已被 `execute_steps` 替代，无主路径引用 | **移除**。从 AST 和测试中断言中抹除 | A类 |
| `codemod` 工具目录 | **Dead**: 离线脚本，无任何主路径引用 | **移除**。连同其测试废弃 | A类 |
| `<steps>` 注入 | **Dead**: V0.3.0 明确禁止复数壳，原生渲染替代 | **移除**。从 `skill_builder.py` 切除组装逻辑 | A类 |
| `test_*_v21.py` 测试 | 26 个驱动 V2.1 流的测试 | **分流：覆盖即删，缺失即迁**。不动 fixture | A类 |

### [BREAKING] 判级说明
本次清理条目 (除 cognitive 保留外) 均属于 **A 类 (A-Class)**。
**理由**：属于 V0.3.0 Hard Cutover 的必然收尾，是已被 Ground-Truth 定稿废弃的机制 (如 `context_mapping`, `python_callable`, `<steps>`)。直接执行清理路径即可，无需 PM 再次功能定夺。

## §0.2 清理方案 (唯一推荐路径)

1. **Codemod 全面下线**：
   - 彻底删除 `src/graph_agent/codemod/` 目录及其测试 `tests/core/test_v21_codemod.py`。这是安全的死代码切割。

2. **Context Mapping 连根拔起** (Cutover Discipline)：
   - 删除 `src/graph_agent/io/context_resolver.py`。
   - 必须同步切除：`harness.py` (361, 372, 852 行) 和 `runner.py` 中关于 `context_mapping` 的构造参传递及初始上下文构建逻辑。
   - 移除 `io/__init__.py` 等 Public API 处的暴露点。

3. **Cognitive 模块误导性注释清理 (非删除)**：
   - 维持 `finish.py`, `finish_task.py`, `md2json.py`, `md_patch.py` 逻辑不动。
   - 全局搜索这四个文件，删除诸如 "V2.1 finish_task LangChain tool factory", "legacy parallel pipeline is gone" 等容易导致后续开发误判的注释和 docstring。

4. **`<steps>` & `python_callable` 切除**：
   - 按照 Ground-Truth，删除 `skill_builder.py` 里的 XML `<steps>` 硬编码拼接段。
   - 剔除 JSON Schema 和残留烟雾测试中对 `.ast.python_callable` 的校验。

5. **V2.1 Tests 彻底交接**：
   - 对于纯机制的 `tests/core/test_v21_*.py` (如 AST/Loader 旧版测试)：直接删除。
   - 对于 `tests/e2e/test_*_v21.py`：核对 V0.3.0 e2e 测试集。若同名 fixture 已有新版测试驱动，则删除该 V2.1 测试文件；若缺失，则修改引擎驱动入口为 V0.3.0 兼容格式，并更名为 `_v030.py`。
