---
module: 02-mechanism/07-runtime
doc: baseline
status: drafted（现状对齐 pinned 代码 7cd4b9c；run/predict live、__all__=19 干净;GraphAgentHarness 死簇已删）
---

# 07-runtime — Baseline(当下代码实现逻辑)

> **Scope**: 引擎最顶层公共入口的现状:`run_skill`/`predict_skill`(runner.py)、bootstrap 装配、public API surface(`__all__`)。
> **现状一句话**:`run_skill`(`runner.py:376`)/ `predict_skill`(`:163`)live,经 `_run_v030_skill_dict`(`:623`)做 bootstrap(`resolve_checkpointer` + model_resolver + `compile_skill` + `assemble_graph`)→ 跑外层 StateGraph → 返回 `RunResult`。public `__all__` **19 个稳定导出**、干净(`test_public_api_contract` 守)。⚠️ 旧文档提到的入口类 `GraphAgentHarness` **已被本次 reorg 删除**(`core/harness.py` 不存在)——"待删"已落实。

## UI/UX
N/A。

## 前端逻辑
N/A —— public API surface 被 studio / 外部 SDK 消费者依赖。

## 后端功能

### 1. 顶层入口(runner.py)
- `run_skill(skill_path, *, workspace_dir, thread_id?, unattended?, event_subscriber?, skill_resolver=None, model_resolver?, **inputs) -> RunResult`(`:376`)——真跑;省略 resolver 时使用围绕 skill/cwd 的默认本地 resolver。
- `predict_skill(...)`(`:163`)——干跑(换 mock model 的同一图执行)。
- 两者经 `_run_skill_dict`(`:456`)→ V0.3.0 走 `_run_v030_skill_dict`(`:623`)。
> **run/predict 是两个执行模式,不是独立域**:同一张图,predict 换 mock model(归 `06-seam/01-models`)。

### 2. bootstrap(_run_v030_skill_dict)
`_run_v030_skill_dict`(`:623`):`resolve_checkpointer("auto")`(`:663`,归 `03-checkpoint`)+ model_resolver + `compile_skill`(`:666`,归 `01-compile`)+ `assemble_graph`(`:667`,归 `03-assemble`)→ `graph.invoke(thread_id=run_id)` → `RunResult`。runtime 是顶层组装者,把各模块拼成可调用引擎。

### 3. public API surface(__init__.py)
`packages/graph-agent/src/graph_agent/__init__.py` 的 `__all__` = **19 个符号**(run_skill/predict_skill/compile_skill/assemble_graph/RunResult/CompiledSkill/CompiledStateGraph/BlackboardState/LocalWorkspaceResolver/SkillManifest/serialize_skill + 异常树等),`mypy --strict no_implicit_reexport` + `test_public_api_contract` 守。**已干净,非待设计。**

## API
- `run_skill(...) -> RunResult` / `predict_skill(...) -> RunResult`(`runner.py:376/163`)——签名权威归 `03-api-contract`,RunResult 形状归 `data-contracts`。
- public `__all__`(19 符号,`__init__.py`)——对外稳定 ABI。

## Data Model / State
入口收 skill+输入 → bootstrap → 跑图 → `RunResult`(归 `data-contracts`)。`__all__` surface 被外部依赖。

## 当前边界(这个模块现在不是什么)
- **public API 已干净**(19 导出 + 契约测试守)——非待设计;增删过 `test_public_api_contract` 即可。
- **缺的是顶层契约文档,不是代码**:`run_skill`/bootstrap/public API 均 live,缺成文的顶层契约。
- **GraphAgentHarness 已删**:旧文档的"入口类"已不存在(本次 reorg 删 `core/harness.py`)——live 走 runner→assemble_graph。

## baseline / alignment 差异(测试锚点)
| 维度 | 现状(baseline) | mvp1 目标 |
|---|---|---|
| 顶层契约 | 代码 live、无成文契约 | run_skill/bootstrap/public API 顶层契约成文 |
| public API | 19 导出、`test_public_api_contract` 守 | 维持;增删过契约 |
| GraphAgentHarness | 已删(`core/harness.py` 不存在) | 引用清净(已落实) |

> **验"是否按 mvp1 改了"**:① `test_public_api_contract` 守住 `__all__`(19 符号、增删显式过契约);② run_skill 端到端 skill+输入→RunResult、各模块正确组装;③ predict 模式换 mock、`RunResult.source="predict"`;④ 文档/代码无 `GraphAgentHarness` 残留引用。

## 读代码主路径提示
`run_skill`(`runner.py:376`)/ `predict_skill`(`:163`)→ `_run_v030_skill_dict`(`:623`,bootstrap)→ compile(`:666`)+ assemble(`:667`)+ invoke。public surface 看 `__init__.py` 的 `__all__`。

## 交叉引用(链接, 不复制)
mvp1-alignment(目标)· `03-api-contract`(实现它)· `03-assemble`(assemble_graph)· `01-compile`(compile_skill)· `03-checkpoint`(resolve_checkpointer)· `data-contracts`(`__all__`/RunResult)· `02-resolver`(DI 注入)
