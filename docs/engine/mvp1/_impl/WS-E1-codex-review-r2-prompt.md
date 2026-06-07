> 存档:发给 codex(reviewer)的 WS-E1 任务书 round-2 复核 prompt。round-1 见对话记录;本轮验证 round-1 处置是否正确落地 + 找新问题。CCB 桥接断时由人工转发。

---

[PLAN REVIEW REQUEST] WS-E1 任务书 round-2 复核

你在 round-1 复核了 `docs/engine/mvp1/_impl/WS-E1-create-agent-core.md`(graph-agent 引擎把手写 ReAct loop 迁到 LangGraph 原生 `create_agent` 的 keystone 任务书),给了 7 条 findings,核心建议"打回、拆成 E1a-E1e"。

设计方(Claude)逐条**打开源码核实**后做了处置:部分采纳改了任务书,部分推翻并附了证据(尤其没采纳"拆成 5 个 WS")。现在请你 **round-2 复核**:不是让你确认设计方对,而是请你**独立判断**——逐条核源验证每个处置是否站得住,并找出任何**新引入或仍遗留**的问题。如果你的结论和设计方相反,请直接说。

## 一、复核方式(请基于仓库真实源码,给 file:line)

仓库根:`agent-harness`。关键源码:
- `packages/graph-agent/src/graph_agent/core/graph_assembler.py`(图装配器:create_agent 构造、手写 loop、subagent 派发、LOGIC/iterate/11-io 接线)
- `packages/graph-agent/src/graph_agent/core/loader.py`(技能加载器:子图 io 强校 `:528`、subagent 工具 placeholder `:709`、LOGIC purity FATAL `:367/770`)
- `packages/graph-agent/src/graph_agent/core/purity.py`(LOGIC 动作纯度扫描器)
- `packages/graph-agent/src/graph_agent/middleware/factory.py` / `__init__.py`(6 槽中间件链 + 顺序)
- `packages/graph-agent/src/graph_agent/core/manifest.py`(BatchSpec)
- 依赖图/分区:`docs/engine/mvp1/_impl/IMPL_PLAN.md`

## 二、round-1 findings × 设计方处置(请逐条独立验真)

1. **[P0] subagent 断裂** —— 处置:**采纳**。称 `graph_assembler.py:535-544` 手写 loop 按工具名拦截 subagent 转 `_invoke_subagent_tool_t21`,而 `loader.py:709` placeholder 抛 `NotImplementedError`;删 loop 裸交 tools 给 create_agent 会命中 placeholder。已在 §5 加存活契约、§7 步骤 2 拎成独立 gated 步、§6/§8 加 ★ 回归测试,修复落在已 owns 的 graph_assembler(`_invoke_subagent_tool_t21`/`_subagent_runtime_map`/`_subagent_tool_map` 三符号均在该文件)。
   - 请验:断裂判断是否属实?把 subagent 工具 func"重接到引擎派发闭包"这个修复方向在 create_agent 工具节点模型下**技术上可行吗**?有没有更隐蔽的失败(如 create_agent 内部对 tool 的 schema/return-direct/中间件交互假设,会让重接的闭包失效)?gated 步放在 create_agent 构造之后是否正确顺序?

2. **[P0] checkpoint E1/E5 边界含糊** —— 处置:**采纳**。§5/§6/§8 划清:E1 仅"接线"checkpointer(create_agent 接受参数 + `ns` 挂共享 base),delta/compaction/state 模型优化归 E5。
   - 请验:这条边界划得干净吗?E1 "只接线不优化"是否会留下一个**实际跑不起来或会爆体积**的中间态(即 E5 没做前 loop=B 是否真能跑、checkpoint 是否会大到不可用)?IMPL_PLAN 里 E5 依赖 E1,边界这么划是否制造了"E1 声明完成但 loop 实际不可用"的假完成?

3. **[P0→部分] owns 漏 purity** —— 处置:**部分采纳/部分推翻**。称 `core/purity.py` §3 早已明划 WS-E6(非漏);FS 写 FATAL(`loader.py:367/770`)现成可测;但 `purity.py` 确不扫 `run_skill`。于是 §5/§8 拆成:FS-FATAL(E1 现在可测)vs run_skill-FATAL(gated 在 E6,未就绪标 xfail/skip 不阻塞退出)。
   - 请验:FS 写 FATAL 是否真的现成(`purity.py` + `loader.py:367/770`)?把 run_skill 禁令标 gated/xfail、"不阻塞 E1 退出"是否**埋了 LOGIC 纯净性的洞**(E1 声明 LOGIC 干净,但实际 run_skill 还能溜进去直到 E6)?这个 gated 是否应该反过来——E6 先于 E1 的 LOGIC 步?

4. **[P1] §6 缺 predict/thinking/usage** —— 处置:**推翻 + 采纳实质**。称旧 §6 已列(codex 漏看),但写太浅;已改成具体契约:predict_context 透传 + `PredictGatewayChatModel.bind_tools()` 仍拦截 + gateway 模型路径(非仅 fake)。
   - 请验:旧版是否真列了(承认漏看与否不重要,重点是现版够不够)?现在的 predict/usage/thinking 测试契约**覆盖完整吗**?有没有还缺的迁移回归(如 finish_task 的结构化输出、return-direct、tool-call id 配对、多轮 thinking 累积)?

5. **[P1] 11-io 越界 io/manager/storage/read_file** —— 处置:**推翻**。称 graph_assembler 仅 import io helper `phase_inputs_from_state`、不编辑 io 模块;落点 `loader.py:528`(已 owns)+ `:287`;不预认领 io 模块,impl 期确需再追加 owns。
   - 请验:"文件导入→黑板 lazy 注入"(§5/§7 步骤 5)这个目标,**真能不碰** `io/storage.py` / `tools/builtin/read_file.py` 完成吗?还是设计方低估了改动面、把一个会越界的项写成了"owns 内可完成"?

6. **[P1] §7 顺序** —— 处置:**采纳**。create_agent + 6 槽合并为一垂直切片(create_agent 构造要消费 6 槽)。
   - 请验:合并后的 §7 五步顺序(1 create_agent+6槽 → 2 subagent → 3 LOGIC → 4 iterate → 5 11-io)是否合理?有没有隐藏依赖错位(如 iterate 的 loop=B 依赖 checkpoint 策略、11-io 依赖 events/runner 边界)?

7. **[P1] WS-E1 过大,拆 E1a-E1e** —— 处置:**不采纳(架构裁定)**。理由:五关注点全改 `graph_assembler.py` 同一文件,拆多 WS 零并发收益(同文件不能并行锁,你自己也承认子 WS 仍串行),只增协调开销;违 IMPL_PLAN §一"串行热点=一条链"+ gateway WS1 范例。改为 §7 逐步 gated TDD 检查点 + subagent 独立 gated 步,保单一文件锁。
   - 请验:这个"同文件→拆了零并发收益→不拆、改 gated 步"的论证你接受吗?还是你坚持拆(若坚持,请给出**拆了能带来什么 gated 检查点给不了的具体收益**——而不只是"更小")?有没有折中(如保 1 个 WS 但把验收清单按子步骤分段,使每段可独立 review/回退)?

## 三、输出要求

1. 逐条给"处置是否站得住"的判定(确认 / 需返工 / 仍遗留),每条附 file:line 证据。
2. 列任何**新发现**的问题(P0/P1/P2 分级),尤其:迁移到 create_agent 后可能断的其他现状能力(finish_task 结构化提交、return-direct、token usage 归属、中间件顺序对 create_agent 的假设)。
3. 评分(沿用 round-1 Rubric 维度),给每维分数 + Overall。**通过线:Overall ≥ 7.0 且无单项 ≤ 3**。给 JSON:
```json
{"dimensions": {"<维度>": {"score": 0.0, "reason": "..."}}, "overall": 0.0, "verdict": "PASS|FAIL", "must_fix": ["..."], "new_findings": ["..."]}
```

## 用户原始指令(原文)
> 生成prompt
