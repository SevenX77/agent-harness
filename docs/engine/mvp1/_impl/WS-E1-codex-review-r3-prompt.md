> 存档:发给 codex(reviewer)的 WS-E1 任务书 round-3 复核 prompt。round-2 给 FAIL(5.6),设计方据其六条 finding 返工(基本全采纳,含纠正自身 11-io 一处误判)。本轮验证返工是否落地 + 找迁移新断点。CCB 桥接断时人工转发。

---

[PLAN REVIEW REQUEST] WS-E1 任务书 round-3 复核

你 round-2 给了 FAIL(5.6/10),六条 finding 基本全中。设计方(Claude)**逐条打开 LangChain/LangGraph 真源码核实后**返工了任务书 `docs/engine/mvp1/_impl/WS-E1-create-agent-core.md`(+ 配套改 `docs/engine/mvp1/_impl/IMPL_PLAN.md`)。请你 round-3 复核:**直接读这两个更新后的文件 + 仓库真源码**,独立判断返工是否真落地、有没有新引入或仍遗留的问题。结论与设计方相反就直说。

## 一、round-2 finding × 本次返工(请逐条对着更新后的文件验真)

1. **[P0] create_agent 默认 AgentState 裁掉 data/flow** → 返工:§5 第一条 + §7 步骤1 列 `state_schema=WorkflowState` 为必接运行边界;§6/§8 加 ★"data/flow 不被裁掉(反例对照)"测试。
   - 验:措辞是否把"必须传 state_schema(或中间件 union 进 WorkflowState)"写成硬验收?反例对照测试设计是否真能抓到裁剪?

2. **[P0] finish_task schema 冲突**(工具 `_finish_task(markdown)` vs 中间件读 `business_data_md/reasoning/diagnostics_md`)→ 返工:§5 加"finish_task schema 对齐"契约,owns 纳入 `cognitive/finish_task.py` + `middleware/cognitive_flow.py`,§6/§8 加 ★ 测试。
   - 验:对齐方向(改工具 schema 还是改中间件读取)是否说清?把这两个文件纳入 E1 owns 是否与其它 WS 冲突?finish 的**结构化输出落 state**这条是否被测到?

3. **[P0] checkpointer 只编译期接受不够** → 返工:§5/§8 改"可运行验收"(invoke 给 thread_id+checkpoint_ns、小N真跑、不污染外层 state),delta/compaction 明确归 E5。
   - 验:这条是否仍可能"E1 声明完成但 loop 实际不可用"?"不污染外层 state"如何可测?

4. **[P1] max_iterations 被 recursion_limit=10000 吞** → 返工:§5/§6/§8 加 max_iterations 保活(超限即停)。
   - 验:phase max_iterations 与 create_agent 迭代约束的接法是否写清(它不是 recursion_limit 同义词)?

5. **[P1] LLMCallEvent 无接替者** → 返工:§5/§8 要求 bridge 把 usage 发进引擎事件流,**或**显式 defer E4 + 测 message metadata 可见 + 记录 defer,二选一不静默丢。
   - 验:二选一是否构成可验收契约?有没有遗漏其它现状由手写 loop 发的事件(ToolCallEvent 等)?

6. **[P1] 11-io owns 违 IR1**(设计方 round-2 曾错误反驳)→ 返工:**纠错采纳**——11-io 收敛为仅子图 io 放宽(`loader.py:528`);文件导入 lazy(E2)+ artifact business_data_md(E3)**拆出为 WS-E1-io**(依赖 E4/E5,跨 read_file/storage/runner),登记在 `IMPL_PLAN.md` §二/§三。
   - 验:拆分边界对不对?WS-E1-io 的 owns(`tools/builtin/read_file.py`/`core/storage.py`/`core/runner.py:598` + 协调 E4/E5)是否完整、与 E4/E5 owns 是否真不相交?子图 io 放宽留在 E1 是否确实 owns 内可完成?

7. **[返工] run_skill xfail 稀释退出** → 返工:§8 改 ordering 二选一(E6 run_skill 扫描码先于 E1 LOGIC 子步 / 或 E1 LOGIC 显式降级 scope "纯返回 runtime + FS/Context purity,不声明完整 LOGIC 干净"),禁中间态;IMPL_PLAN 标 E6→E1-LOGIC ordering。
   - 验:二选一是否消除了"声明 LOGIC 干净但 run_skill 能溜进去"的洞?depends_on 把 E6 标 soft 是否够(还是该硬依赖)?

## 二、本轮重点找新断点(create_agent 迁移易假绿处,请基于源码判断任务书有没有漏)

- **return-direct**:手写 loop 对 finish_task 用 `handle_finish_task_tool_result` 短路返回(`graph_assembler.py:563`);create_agent 下 finish/return-direct 语义是否被任务书覆盖?
- **tool-call id 配对 / ToolMessage 序列化**:手写 loop 手动配 `tool_call_id`(`graph_assembler.py:556-561`);迁 create_agent 后由原生 ToolNode 接管,任务书是否要求测多工具并发调用的 id 配对?
- **未知工具处理**:手写 loop 对未知工具 `_graph_fatal`(`:533`);create_agent 下是否保留同等 fatal?
- **其它**:中间件顺序对 create_agent 的 before/after_model 假设;subagent 重接闭包在 create_agent 的 ToolNode wrap 下能否真拿到 state(round-2 你已确认方向可行,这轮看任务书是否把"传 state_schema 才能拿到 state"这条因果写对)。

## 三、输出要求

1. 逐条给 round-2 finding 的"返工是否落地"判定(已解决 / 仍需返工 / 新引入问题),附 file:line。
2. 列任何新发现(P0/P1/P2)。
3. 评分(沿用前两轮 Rubric 六维),每维分数 + Overall。**通过线:Overall ≥ 7.0 且无单项 ≤ 3**。JSON:
```json
{"dimensions": {"<维度>": {"score": 0.0, "reason": "..."}}, "overall": 0.0, "verdict": "PASS|FAIL", "resolved": ["..."], "still_open": ["..."], "new_findings": ["..."]}
```

## 用户原始指令(原文)
> 生成prompt
（注:本轮为 round-2 返工后的复核,延续上一轮"生成prompt"的 peer-review 节奏)
