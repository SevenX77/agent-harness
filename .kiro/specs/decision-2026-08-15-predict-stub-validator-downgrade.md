# 决议:predict 用占位 mock 时,作者相位校验器失败降级为诊断(2026-08-15)

## 问题链(一手实证,2026-08-15)

1. **现象**:story-deconstruction skill 编译全绿(0 issue)后,predict 在
   `segment` 阶段致命失败。父图里表现为
   `[F-v3-agent-exit-control-failed] max iterations (20) reached without a valid
   finish_task marker`;把 `text-segmentation` 子图单独 predict,表现为
   `GraphAgentFatalError: phase validator failed: ValueError: Last segment must
   end at line 6, got 999`。
2. **控制变量实验(决定性)**:同一子图、同样输入、同一引擎——
   - `validator: true`(原样)→ predict 致命失败;
   - 把两处 `validator: true` 改成 `false` 并移走 `validator.py` → `PREDICT
     STATUS: success`,整条链(含嵌套数组输出)跑通。
   变量只有校验器一个。
3. **对照组**:一个最小的单 agent 阶段 skill(无 validator)predict 成功。
   所以不是"agent 阶段在 predict 下都不行"。
4. **机制**:`packages/graph-agent/src/graph_agent/runtime/state_mapper.py`
   `_run_phase_validator`(L351-362)对 predict 模式零感知——`grep predict` 在该
   文件无命中。作者校验器在 predict 与真跑中同样执行,任何异常都变成
   `GraphAgentFatalError`。
5. **为什么必然失败**:P2 占位 stub 按 io.outputs schema 合成数据,**schema 合法但
   语义编造**(`end_line: 999`)。而作者校验器做的正是语义校验(分段必须恰好覆盖
   章节行范围)。占位数据**原理上不可能**满足语义校验——这不是 skill 的缺陷,是把
   校验器用在了它无法适用的对象上。
6. **影响面**:相位校验器是引擎一等公民(frontmatter `validator: true`、专属错误码
   `[F-v3-{node_kind}-validator-failed]`、编译期校验其存在)。凡带校验器的 skill,
   predict 恒失败;Studio 又有 `RUN_REQUIRES_PREDICT`(409, not_retryable)硬闸——
   这类 skill 在 Studio 里**永远无法运行**。

## 设计依据

- `docs/studio/mvp1/02_capabilities/predict/mvp1-alignment.md:15`:
  > `predict` = 编译后、运行前的"试飞":按节点 i/o 配置跑图、验 schema 与逻辑、
  > 确定性执行 logic 节点、mock agent 节点而不烧真 token。是 Run 的硬前置。
- 同文件 L20(mock 源的三级精度):
  > **agent mock by golden**:agent 节点不调真模型;按节点 **golden 状态**选 mock
  > —— 无 golden → 占位 mock;有 golden → golden case。**golden 非前置**,只换 mock 源。

即:设计把"agent 节点的输出真实度"明确建模成**分级的 mock 源**,并明说 golden
不是前置。既然设计允许"无 golden 就用占位 mock 试飞",试飞就不能要求占位数据通过
只有真实输出才可能通过的语义校验——否则"golden 非前置"这句话在任何带校验器的
skill 上都是空头支票。

引擎侧 mock 策略已经具备这条判别轴(`core/_predict_internal/strategy.py`):
`has_golden_case`(P0)/ `has_manual_override`(P1)/ 否则 P2 heuristic stub。

## 决定

**predict 模式下,当某相位的 agent 输出来自 P2 占位 stub 时,作者相位校验器抛出
异常不再是 fatal:记为一条 predict 诊断,保留 mock 的 schema 合法输出继续试飞。**

配套三条:

1. **P0 golden / P1 manual override 不降级。** 那是真实录制或人工指定的输出,
   校验器拒绝它是**真信号**(golden 与它自己相位的校验器矛盾),必须照旧 fatal。
2. **校验器照常执行,只改失败的处置。** 不是"跳过校验器"——照常调用,这样
   校验器自身写坏(NameError / 拿错字段名)仍会被试飞抓到并报告;校验器若在占位
   数据上侥幸通过并做了 enrichment,其 enrich 结果照常采用。
3. **降级必须显形,不许悄悄变绿。** 每条降级写进该相位的 `PhaseRecord`
   (`validator_downgraded` 字段),随 `RunResult.phases` 返回并落进 predict 的
   `result.json` / summary 产物,能数出"本次试飞有 N 个相位的校验器被降级"。
   一次校验器全被降级的 predict 不得被读成"验过了"。
   (trace.jsonl 是事件流,本次不新增事件类型;要在事件流里也显形需另立一条
   typed event,留作后续。)

## 非目标

- 不改真跑(run)路径的校验器语义:真跑中校验器失败仍是 fatal。
- 不改 Studio 的 `RUN_REQUIRES_PREDICT` 闸(它有设计依据:predict 是 Run 的硬前置)。
- 不做"让 mock 变聪明到能过语义校验"(校验器是任意 Python,原理上不可解)。
- 不动 golden 的录制/回放机制本身。

## 验收判据

- 新 TDD 测试(先红后绿):
  1. 带 `validator: true`、校验器必然抛异常的单 agent 阶段 skill → predict 成功,
     且结果里能查到该相位的校验器降级记录;
  2. 同一 skill,给该相位喂 P0 golden 输出 → 校验器照旧 fatal(不降级);
  3. 真跑路径下校验器失败仍 fatal(回归锁)。
- `D:/coding/skills/story-deconstruction-v3-lab` 的完整 predict 不再死于
  `segment` 相位的校验器。
- 引擎全套 + gateway + studio backend 测试、ruff、mypy --strict、pip-audit 全绿。


## 附:同一现场的另一个引擎缺陷(不在本改动内)

并行调查(工作流 wqpczc27w,37 个 agent)在同一现场找到**另一个更靠前的**缺陷,
与本决议是两回事,须单独立项:

`core/runner.py:324-334` 为启发式桩收集 `phase_schemas` 时**只遍历根 skill 的
`compiled.nodes`**;而子图是在装配期由 `graph_assembler.py:1552` 另起一次
`compile_skill` 产生的,其相位从不进根 `compiled.nodes`。于是**嵌在子图内的 agent
相位拿不到自己的 io.outputs**,桩退化成 `{"value": "<mock_unknown>"}`,finish_task
每轮被 schema 闸驳回,直到 `max_iterations` 抛
`[F-v3-agent-exit-control-failed]`——这正是 story-deconstruction 父图里看到的
20 轮空转,与本决议处理的校验器降级是**不同的失败**(本决议的现场是把子图单独
predict、相位成为根节点、schema 可得之后才暴露出来的下一层)。

该缺陷已核实(runner.py:324-334 原文 + graph_assembler.py:1552 另起编译),
修复落点应在装配期把相位自己的 schema 交给 predict 模型,而不是在 runner 里
重建一份并行真相。另立决议与 PR。
