# 决议:iterate.over 统一为业务字段引用(2026-08-15)

## 问题链(全部一手实证,2026-08-15)

1. **产品契约教裸字段名**:MoirAI 知识库
   `apps/studio/backend/app/agents/knowledge/KB-06-iterate.md`(L23-24 `over: chapters`,
   L44 `over: paragraphs`)与 `KB-01-skill-anatomy.md`(L88 `over: chapters`)全部以
   **裸业务字段名**示范 `iterate.over`。
2. **真实 skill 全按裸名写**:story-deconstruction-v3 的全部 4 处 iterate 声明
   (`phases/segmentation/SUBGRAPH.md` `over: chapters`、event-timeline `extrac`
   `over: segmentation_result`、`stitch` `over: chapter_event_timeline`、story-analysis
   `analyze_batches` `over: event_batches`)均为裸名。
3. **引擎运行时不解析裸名**:`graph_assembler._resolve_iterate_items` 只按
   WorkflowState 状态路径遍历(`data.…` / legacy `data.inputs.…` 回退),裸名
   `chapters` 解析 `_MISSING` → `[F-v3-iterate-over-not-list]` FATAL。离线复现:
   新旧引擎同错 `iterate over path 'chapters' must resolve to list`(predict_probe,
   旧=repo root venv / 新=worktree venv,2026-08-15)。
4. **编译期对 over 零校验**:`over: chapter_event_timeline`(字段根本不存在)与
   `over: chapters` 一样编译全绿;缺陷被推迟到 predict/run 运行期才爆。
5. **连锁放大**:Studio 把该 FATAL 吞成 predict `status: crashed`(trace 只有
   run_started→run_ended,无错误详情),而 run 有 `RUN_REQUIRES_PREDICT`(409)硬闸
   —— predict 一崩,skill 整体锁死,agent 无路可走。
6. **引擎自测全用状态路径**:12 处 over 全部 `data.*` 形
   (`data.inputs.items` ×9 等),没有任何产品面教这种写法——测试与产品契约脱节,
   所以引擎测试常绿而真实 skill 必死。

## 决定(第一性原理:一个契约只有一种合法语法)

1. **契约**:`iterate.over` = 当前 phase 可见黑板 business namespace 中的**裸字段名**,
   运行期必须解析为 list。状态路径形(`data.*`、`data.inputs.*`)**不是契约的一部分,
   删除支持**(no-backward-compat:同一改动内替换旧设计并删除旧路径)。
   设计落点:`docs/engine/mvp1/01-contract/02-skill-syntax/mvp1-alignment.md`
   iterate 条目写明 over 语法;错误码表 `[F-v3-iterate-over-not-list]` 行已声明
   编译期/运行期双相,语义不变。
2. **运行时**:`_resolve_iterate_items` 直接在 `state["data"]`(BusinessData)上取
   裸字段;删除 `_resolve_legacy_data_input_path` 与状态路径遍历依赖。
   `accumulate.var/from`、`item_var` 语义不动。
3. **编译期**:over 纳入既有 dataflow 校验面——over 引用的字段必须有可解析来源
   (root input / 上游 phase output / runtime_config import),无来源即在编译期报
   `[F-v3-iterate-over-not-list]`(复用现码的编译相,不新增码);可静态判定
   schema 非 array 时同码编译期报。
4. **测试迁移**:引擎测试 12 处 `over: data.*` 机械迁到裸名——契约收敛的直接后果。

## 非目标

- 不动 graph 级 iterate 的声明位置与 accumulate 语义。
- 不动 Studio 的 predict crash 吞错与 RUN_REQUIRES_PREDICT 闸(另立观察项,属 Studio)。
- 不为旧状态路径写任何兼容/迁移逻辑。

## 验收判据

- 新 TDD 测试:裸名 batch 解析执行(`over: chapters` root-input 场景)+ 编译期
  over 无来源拒绝,先红后绿。
- predict_probe 在 story-deconstruction-v3-lab 上跑过 segmentation 批(不再
  `over-not-list` FATAL)。
- 引擎全套 + gateway + studio backend 测试、ruff、mypy --strict、pip-audit 全绿。
