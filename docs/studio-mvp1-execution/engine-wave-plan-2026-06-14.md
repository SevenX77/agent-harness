# Engine-first wave plan (2026-06-14)

> PM 指令(2026-06-14):先做 engine 相关改动(engine/gateway 后端架构),再做前端适配;每个功能实施前先计划 + subagent 独立审计是否符合 MVP1+three-module,实施完再独立审计;规划不冲突任务并行实施,把关设计审计。

## 方法:对每个"已知 engine 缺口"先核实真实状态(verify-before-asking)

PM 审计提到的 `wave2-safety` P0(engine→gateway concrete import, D4 依赖倒置)经**真跑设计自带 RED 测试**核实 = **不是违规**:
- `test_importing_graph_agent_does_not_require_gateway_concrete_module`(productization RED)只禁**import-time** gateway 依赖;`interception.py:169` / `llm_phase_node.py:135` 是**懒加载**(函数内 try/except import,call-time 才触发)→ `import graph_agent` 不拉 `graph_agent_gateway` → **测试通过(21/21)**。设计接受懒加载;重构掉它 = 逆设计而行。**不动。**

## 三个 subagent 调查结论(各读真代码 + 真设计 + file:line)

| 项 | 设计单元 | 结论 | 动作 |
|---|---|---|---|
| **A** per-node golden 输出 | D7 | **真 engine 缺口·低风险**:`_with_phase_outputs`(graph_assembler.py:403)只在 batch/iterate/terminal 路径调;简单线性 phase 走 `StateMapper.wrap_phase_output`(state_mapper.py:77/218)**不写** `phase_outputs` map → e2e-fast 这类扁平结果技能无 per-node 输出 → Studio `golden_headless._node_outputs`(golden_headless.py:98)退化 run-level。Studio 已有 RED 测试。 | **做(第一)** |
| **B** edge transition 事件 | trace F4 / DEF-005 | **engine 侧已做**:`InputDispatchEvent`/`BlackboardReduceEvent`/`InputFileInjectedEvent`(events.py:256-283)已在每条边发 `from/to_phase`+`blackboard_snapshot`(graph_assembler.py:703-746)。剩 Studio 前端消费(替 `getMockEdgeContext`)= 前端(后端之后)+ 部分挂 DEF-005 延期。 | engine 不动;前端轮再做 |
| **C** DEF-029 per-node 输出路径 schema | input F3 | **真 engine 工作·MVP1-scope**(F3 target-design),但**改 frozen schema = 高风险**(Phase/IODef/parser/runner)。过三关(general/necessary/only-engine)。 | 做(第二,A 落地后,full focus + 强 pre-audit) |
| **D** D10 lease/fencing 接入 resume | D10 | **设计正确延期**:设计「现在只留接口位、不做恢复逻辑」,multi-host lease 在延期清单;单用户 MVP1 进程内独占,无需 lease。 | 不做(延期正确) |

## 增量 A 实施方案(本轮先做)

**目标**:让**所有**技能(含简单线性 phase 如 e2e-fast)的 run result 含真 `phase_outputs`(node_id→outputs dict),使 D7 per-node golden 在真跑上不退化。

**改动点(单文件,engine 核心执行)**:`packages/graph-agent/src/graph_agent/runtime/state_mapper.py` 的 `StateMapper.wrap_phase_output`:
- 在现有 schema 校验 + `StateManager.update_business(state, **updates_dict)`(line 146)**之后**,把本 phase 写出的业务 keys(`updates_dict`)记进 `phase_outputs[self.phase_id]`,merge 进已有 map,再 `update_business(new_state, phase_outputs=merged)`。
- **关键纪律**:`phase_outputs` 必须在 schema 校验**之后**写(否则被当 undeclared key 拒,违 line 135-143);这与 `_with_phase_outputs` 绕过 wrap 校验的做法一致。
- 忠实镜像 `_with_phase_outputs`(graph_assembler.py:403-417)的累积语义:read 已有 phase_outputs → copy → set `[phase_id]` → update。

**为何在 wrap_phase_output**:它是简单 phase 唯一的输出收口(state_mapper.py:218 唯一调用点),且持有 `self.phase_id`。batch/iterate 已在 graph_assembler 侧写,简单 phase 在此对称补齐。

**风险/边界**:
- BusinessData `__getitem__` 对 `phase_outputs` 有 synthetic compat 层(state.py:91-124,硬编码 skill 字段名);存真 extra 后 `model_dump()["phase_outputs"]`=真值、`data["phase_outputs"]`=synthetic。**此分歧 batch 路径已存在并被容忍**;Studio 读 model_dump 的真值。不新增分歧。
- 不碰 frozen 契约、不改 engine↔gateway 边界、不改 studio 自算任何 gateway 态。纯 engine 内部、owner=engine。

**验证(真跑,不伪绿)**:
1. engine 全量 `uv run pytest packages/graph-agent/tests/ -q`(尤其 productization 21 + 任何依赖 BusinessData/__getitem__ synthetic 层的测试)。
2. Studio RED 转 GREEN:`apps/studio/backend/tests/services/test_productization_golden_headless_red.py`。
3. **真跑 e2e-fast**:compile→run → 读 final_state.json 确认含 `phase_outputs={step1:..,step2:..,step3:..}`。

**门禁**:engine mypy/ruff clean;Studio 后端 pytest 全绿;api/llm.ts + KEEP-MAIN 零改动;never main。

## 增量 C 实施方案(A 之后,独立轮)
DEF-029 per-node 输出路径 schema:`types.py` Phase 加 output-path、`io_manager.py` IODef 扩展、`parser.py` 解析 GRAPH.md frontmatter per-phase output-path、`runner.py` 按节点落产物。**frozen-schema 变更 = 强 pre-audit + 向后兼容(字段可选、缺省 = 现 run-level 行为)**。

## 工作流纪律(本轮)
A:① 本计划已落盘 ② pre-audit subagent 核计划 vs D7/three-module ③ 我实现(单文件核心改,自己做+gatekeep,不外包)④ post-audit subagent 核实现 vs 设计 + 真跑门禁。
