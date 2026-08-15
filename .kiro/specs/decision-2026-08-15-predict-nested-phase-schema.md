# 决议:predict 的相位输出 schema 由装配期就地供给,不在 runner 里重建(2026-08-15)

## 问题链(一手实证)

1. **现象**:story-deconstruction 父图 predict 死在
   `[F-v3-agent-exit-control-failed] Phase 'segment' failed: max iterations (20)
   reached without a valid finish_task marker`。
2. **根因**:`packages/graph-agent/src/graph_agent/core/runner.py:324-334` 为启发式桩
   预填 `phase_schemas` 时**只遍历根 skill 的 `compiled.nodes`**:
   ```python
   phase_schemas = {}
   for node in compiled.nodes:
       if hasattr(node, "ast") and hasattr(node.ast, "io") and node.ast.io and node.ast.io.outputs:
           ...
   if hasattr(strategy, "_phase_schemas"):
       strategy._phase_schemas.update(phase_schemas)
   ```
   而子图是在**装配期**由 `graph_agent/core/graph_assembler.py:1552` 另起一次
   `compile_skill` 产生的,其相位从不进根 `compiled.nodes`;subagent 子技能
   (`graph_assembler.py:2796`)是第三条同样不进根的编译入口。
3. **后果**:嵌在子图内的 agent 相位拿不到自己的 `io.outputs`,
   `_predict_internal/stub.py:18-21` 在 schema 缺失时退化成
   `{"value": "<mock_unknown>"}`;该输出过不了 finish 闸的 schema 校验,每轮被驳回,
   直到 `max_iterations` 抛 exit-control fatal。
4. **分档**(判据不是"有没有 agent 相位"):
   - 顶层 agent 相位 + schema 非退化 → 能过(现有测试只覆盖这一档);
   - agent 相位嵌在子图 / subagent 子技能内 → **结构性必挂**;
   例外仅当该相位 `io.outputs` 恰好只声明一个名为 `value` 的字段,或它有
   golden case / `mock_llm` override。
5. **本 skill 的处境**:根 `phases/` 下 4 个全是 `SUBGRAPH.md`,**零个顶层 agent
   相位**;18 个 agent 相位全部命中"必挂"档。

## 设计依据

- `docs/engine/mvp1/02-mechanism/07-runtime/mvp1-alignment.md:13`:
  > `run_skill`(真跑)/ `predict_skill`(干跑)是**两个执行模式**(同一图,predict 换 mock model)
- `docs/studio/mvp1/02_capabilities/golden-eval/mvp1-alignment.md:34`:
  > no-golden predict emits schema-shaped placeholder … no real provider call occurs

即设计承诺:predict 跑的是**同一张图**,无 golden 时产出**符合 schema 的占位**。
当前实现对子图内相位产出的是与 schema 无关的 `{"value": "<mock_unknown>"}`,
两条都违背。

## 决定

**删除 runner 里那份按根节点重建的 `phase_schemas` 预填;改由装配期把相位自己的
`io.outputs` 就地交给 predict 模型。**

落点:`graph_assembler._build_skill_node`(约 :1784,:1849 处已持有
`output_schema = phase_ast.io.outputs`)经既有参数链传到
`_resolve_phase_chat_model`(:2214-2226,构造 `PredictGatewayChatModel` 的唯一活
路径),在那里把该相位的 schema 注册进 mock strategy。

**为什么是这一层(而不是"给 runner 加递归")**:
一个 agent 相位的 `io.outputs` 的唯一 owner 是装配它的那段代码——它必然在手
(同处 :2000-2002 已经把同一份 schema 编成 Pydantic 模型交给 finish 闸做驳回校验)。
runner 那张表是**在错误的层重建的第二份真相**,而且结构上不可能看全(编译入口有
三个)。同一份 schema 一边用于造假、一边用于校验,却来自两个来源——这正是
"事实唯一所有权"被破坏的形态。递归收集只是让第二份真相多爬一层,下一个编译入口
出现时会再漏一次;按无向后兼容纪律,应删旧路径而非加分支。

## 非目标

- 不动 exit-control 的预算语义(`max_iterations` 是 skill 自己声明的;它不是病因,
  加大预算只会把 20 轮空转变成 N 轮空转)。
- 不动 Studio 的 `RUN_REQUIRES_PREDICT` 闸。
- 不在 `stub.py` 里为具体字段名(如 `end_line`)加特判。
- 校验器与占位数据的冲突已由
  `.kiro/specs/decision-2026-08-15-predict-stub-validator-downgrade.md` 单独裁决,
  不在本改动内。

## 验收判据

- 新 TDD 测试(先红后绿):
  1. **predict × 子图内 agent 相位**:父 skill 只含一个 SUBGRAPH 相位,子图内是
     agent 相位且 `io.outputs` 声明具名字段 → predict 成功,且该相位的产出是按
     schema 成形的(不是 `{"value": "<mock_unknown>"}`);
  2. 启发式桩驱动真 agent 循环(不经 `mock_llm` override)→ finish 闸接受;
  3. 顶层相位回归锁不破。
- `D:/coding/skills/story-deconstruction-v3-lab` 完整 predict 不再死于 exit-control。
- 引擎全套 + gateway + studio backend、ruff、mypy --strict、pip-audit 全绿。

## 同批文档纠偏

`docs/engine/mvp1/02-mechanism/05-run-inner/06-golden-eval/baseline.md:35` 仍写
`interception.py` 是 skeleton、"无 resolver 接线 → 现状不 live",与
`graph_assembler.py:2214-2226` 的活调用点矛盾,同 PR 改正。
