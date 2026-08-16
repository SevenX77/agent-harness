---
module: 02-mechanism/04-run-outer/01-graph-exec
doc: mvp1-alignment
status: drafted（**U4(LOGIC)单元锁定 2026-06-06**;LOGIC 干净契约 LE1-3 已定、live drift→refactor-target 归 kiro;AGENT run_context/io_manager 已成段(源 11-io)、nudge 归 `05-exit-control`(已成段,graph-exec 仅 AGENT 委派);文件未 FROZEN——graph-exec 还参与 U3/U11）
binds_baseline: ./baseline.md
aligns_with: ../../../00-architecture-overview.md（§3 机制层 B·运行外层）
---

# 01-graph-exec — 机制 B · 图执行(运行外层)

> **Tier**: 机制层 B · 运行·外层(图编排,确定性) | **Owns**: StateMapper slice/merge · 拓扑调度 · run_context/io_manager · **LOGIC 执行(action 范式)** · SUBGRAPH 调用 | **现状**: ⏳(LOGIC 干净契约已定 2026-06-04;live drift 列 refactor-target 归 kiro) | **Related**: `data-contracts`(blackboard)· `04-tools`(action vs tool)· `02-iterate`(声明式编排)· `03-checkpoint` · `05-run-inner`(AGENT 委派)

## 1. 定义
graph-exec = 运行时**按 DAG 执行 phase**,用 blackboard(`WorkflowState.data`)统一状态。三种 phase 范式:**LOGIC**(确定性 action,引擎调)/ **AGENT**(内层 agent loop,委派 `05-run-inner`)/ **SUBGRAPH**(子图调用)。io 经 StateMapper 从黑板切片/回写。

## 2. 数据流 / 机制
`graph.invoke(inputs)` → 校验 inputs → blackboard init → `for phase in topological_order`:StateMapper.slice(state, phase.io.inputs) → **run phase** → 校验 output vs phase.io.outputs → StateMapper.merge → 终态校验。(运行时流的完整机制正文 🚨 待 mvp1 自写,见 `07-runtime`;mvp0 已弃用。)
- **LOGIC(V4 干净契约,2026-06-04 定稿)**:action = **确定性纯变换**:
  - 签名 `def <action_name>(inputs) -> dict`(函数名=action 名,自文档);`inputs` = **只读** io.inputs 切片。
  - **纯返回**:返回 dict、key ⊂ io.outputs;**不写黑板**——砍掉 Context 的 `set/update/delete/__setitem__`(action 不能 mutate)。
  - **硬禁**:action 里**不许** `run_skill`(编排)、文件系统、`sys.path` hack、import 越界、往黑板塞非序列化对象——purity 扫描器扩展拦掉(归 `01-compile`)。
  - **编排/循环/累积全是声明式的活**:每项跑子 skill → `02-iterate`(batch)+ `SUBGRAPH`;累积 → `iterate.accumulate`。action 只做纯 transform。
  - validator 后置钩子保留(`validator.py`);失败报 `[F-v3-logic-*]`,不回写。`core/actions.py` 注册表,与 `04-tools` tool(LLM 调)两套。
  > **这是把 live drift 重构掉的目标契约**,不是照抄 live。live 现状(11 action 全用可变 Context facade、3 个跑 run_skill、5 个碰 FS、黑板塞 `BatchAccumulator` 对象)= §8 的 refactor-target。
- **AGENT**:委派 `05-run-inner` 跑内层 loop → finish_task。
- **SUBGRAPH**:child compiled graph invoke,失败冒泡包 parent context。
- **run_context / io_manager(节点间黑板/IO 操作,源 11-io;现状见 baseline §4/§5)**:
  - **子图 io 放宽(E1,已完成并在 2026-06-20 扩到 outputs)**:删对 **inputs** 的 1:1 强制——子图像普通节点用自己 `io.inputs` 经 StateMapper 从黑板切片(机制现成)。**outputs 的相等校验此后也一并移除**(commit `cad7dbc0`,PM 授权):本条原写"outputs 保留相等校验(下游契约)",与 `01-contract/02-skill-syntax/mvp1-alignment.md` §3.4「父图和子图 IO 不需要字段全集一一相等」及其 §4 把「父子图 IO 1:1 强绑定」列为 drift 相冲突,以后者为准。outputs 边界由运行期 `StateMapper` 按声明 schema 守,越界写回记 `[F-v3-runtime-state-mapping-failed]`;`[F-v3-subgraph-io-mismatch]` 仅保留 registry 条目、**无发出点**。
  - **文件导入→黑板(E2,新能力)**:节点声明"导入文件 → 注入字段",**跑到该节点才 lazy 注入**(非图启动);落点 `_wrap_phase_runtime_node`(`graph_assembler.py:287`)进节点前,复用 read_file 工具(`make_read_file_tool`,`tools/builtin/read_file.py:43`)读路径 + `StateManager.update_business`(`state.py:225`)写黑板,再 StateMapper 切片;发 `InputFileInjectedEvent`(归 `observability`)。
  - **io.outputs artifact 扩展(E3)**:路径标注更丰富(一/多文件、filename-only 默认 `.workspace/artifacts`);**md 输出取 `business_data_md`(`CognitiveFlowMiddleware` 保留的原始 md,`cognitive_flow.py:536`)原样写,不做 json→md 回转**——⚠️ 现状未接:主路径 finish_task 工具(`finish_task.py:51`)走 `markdown`→parsed `data`,`business_data_md` 在中间件侧;接线改取它(`save_artifact` 对 str 原样写,`storage.py:167`)而非 parsed json。
  - **黑板切片(FROZEN-4)引擎侧已成(StateMapper),不改**(前端 canvas 可视化另算)。

## 3. 接口契约
StateMapper 规则(init/slice/merge/final;`[F-v3-runtime-state-mapping-failed]`):slice 要求 required 字段在 state;merge output key ⊂ io.outputs.properties。blackboard = `WorkflowState.data`(归 `data-contracts`);**LOGIC action 调度契约**:`def <action_name>(inputs) -> dict` 纯返回、只读 inputs(见 §2 / §5 LE1-3)。

## 4. 设计决策基础(用户原话)
> 重构 ≠ 拿 live 当真理(2026-06-04 PM):"我们在做mvp重构优化, 你拿live当真理?? 从第一性原理思考" —— live 是被重构对象,drift 是退化证据,code 向干净设计对齐。
> LOGIC 干净目标(2026-06-04 PM,三问拍板):**纯返回 / 硬禁 / 反写** —— action 纯返回不写黑板、硬禁 action 里 run_skill/FS、干净契约反写进 spec。
AGENT 侧的 run_context/io_manager/nudge 收口待成段(决策依据见 §5)。

## 5. 决策 + 动机
| ID | 决策 | 动机 |
|---|---|---|
| GE1 | 三 phase 范式;AGENT 委派内层,LOGIC/SUBGRAPH 在外层 | 外/内主轴;LOGIC=确定性、AGENT=LLM 驱动 |
| GE2 | **LOGIC = 第二执行范式**(action,引擎调,确定性) | 与 AGENT(tool,LLM 调)对照,两套不混 |
| GE3 | io 经 StateMapper 切片/回写,blackboard 单一真相 | 去子图 io 1:1 |
| **LE1** | LOGIC action = **纯返回**:只读 inputs → 返回 dict;砍 Context mutation(`set/update/delete`) | 可测、可序列化、不破 checkpoint;消除"action 写黑板"不可控 |
| **LE2** | **硬禁** action 里 `run_skill`/FS/sys.path/import 越界(扩 purity 扫描器) | 逼回声明式 iterate/SUBGRAPH;否则声明式编排永远是摆设 |
| **LE3** | 干净契约**反写进 `compile-rules`+`skill-syntax`**(解冻 `03-logic-md-spec`) | spec = V4 真相,code 向它对齐(非 spec 向退化 code 投降) |
| **E1** | 子图 io 放宽:**只放 inputs**(从黑板切片),outputs 保留相等校验 | 子图像普通节点;outputs 仍需对齐否则下游取不到(源 11-io;studio FROZEN-1 只点名 inputs) |
| **E2** | 文件导入→黑板 **lazy**(跑到节点才注入,非图启动) | 按需注入;落 `_wrap_phase_runtime_node` 前置步,复用 read_file + StateManager |
| **E3** | md artifact 来源 = validated `business_data_md`(中间件保留)原样,不 json→md 回转 | 避免解析-回写丢格式;现工具走 parsed data,接线改取 business_data_md(`save_artifact` 对 str 原样写) |
| **E4** | 黑板切片(FROZEN-4)引擎侧已成(StateMapper),本块不改 | 前端 canvas 可视化另算 |

## 6. 测试关键点
1. StateMapper slice/merge:required 缺失报错;merge 越界 key 报错。
2. **LOGIC action 确定性**(同输入同输出,无 LLM)。
3. SUBGRAPH 失败冒泡保留 child code + parent context。

## 7. 涉及 region / platform
engine 全权。

## 8. gaps / 待设计(refactor-target,归 kiro;设计已定 §2/§5 LE1-3)
LOGIC 干净契约已定;**live 的 drift = 要重构掉的反模式**(不是真相):
1. Context facade 砍 mutation(`set/update/delete`)→ 纯返回。
2. 3 个 action 里的 `run_skill`(story-deconstruction `segment_all_chapters`/`run_batch_loop`/`extract_all_events`)→ 声明式 `02-iterate`(batch)+ SUBGRAPH。
3. 5 个 action 碰 FS/sys.path/硬编码路径 → purity 扫描器扩展硬禁(归 `01-compile`)。
4. 黑板里非序列化对象(`BatchAccumulator`)→ `iterate.accumulate` + 序列化数据(checkpoint 前提)。
5. 死簇 `code_phase_node`/`phase_executor` 删(live 用 `_build_logic_node`)。
6. 反写:解冻 `03-logic-md-spec` 改 action 契约(归 `compile-rules`/`skill-syntax`)。
7. action/tool 统一 capability:spec 已固定 Action≠Tool,纯 action(read-only dict)与 tool(StructuredTool)本质不同 → **不统一**。
+ run_context/io_manager 收口(源 11-io,本轮成段):子图 inputs 放宽(改 `loader.py:528` 只校 outputs)、文件导入→黑板(`_wrap_phase_runtime_node` 前置步,新能力)、io.outputs artifact 路径标注扩展 + md 取 business_data_md——均 TDD 归 kiro;边操作**事件**(BlackboardReduce/InputDispatch/InputFileInjected)归 `observability`(双向)。nudge/after_agent 闸 owner = `05-exit-control`(已成段),graph-exec 的 AGENT 分支(§2)委派内层即可、无额外 io 收口。
+ **FROZEN 解冻(源 11-io)**:`04-subgraph-md-spec` 删 inputs 1:1(归 `skill-syntax`/`compile-rules`)、io.outputs 加 artifact 路径标注 + file-import 声明(归 `skill-syntax`)。

## 交叉引用(链接, 不复制)
**`baseline`(现状,双向)** · 00-architecture-overview §3 · `04-tools`(action/tool)· `02-iterate` · `03-checkpoint` · `05-run-inner`(AGENT)· `data-contracts`
