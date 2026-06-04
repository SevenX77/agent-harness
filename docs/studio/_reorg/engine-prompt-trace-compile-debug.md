请用中文回答。

你是一位资深的执行引擎 / 可观测性后端架构师。下面是 graph skill 工作流引擎里 **compile(编译校验)+ trace(去黑盒可观测)+ debug(干预续跑)** 三块的**前后端边界**与**对引擎的设计需求**。前端的渲染/交互我们已设计好(见配套文档),这里只问**引擎要补什么**。请先确认现状、再设计缺口。

# 一、前后端边界(总原则)
- **引擎(后端)负责**:① 编译校验并产出**带定位的结构化错误**;② 把运行过程 emit 成**结构化事件流**(trace);③ 持有**运行时状态机 + checkpoint**,支持精准续跑/干预。
- **前端负责**:把错误**上下文化呈现**(节点/属性/编辑器)、把事件流**渲染成可读 trace**(可折叠分类摘要、时间线、dot 黑板卡片、Prompt 透视)、把干预做成**节点/dot 上的就地操作**。
- 所以本文只问引擎:**现有能力覆盖到哪、缺口怎么补**。

# 二、compile(编译校验)
**现状(已核实,大多就绪)**:引擎 Loader 校验结构/字段/拓扑/IO 数据流/mention,产出 `CompileError`,已带 `severity`(fatal/warning)+ `phase_name` + `file` + `line` + `field` + `message`。
**前端要把错误标在 3 处**:① canvas 对应**节点**上的警告/错误小标志 ② properties/io 面板对应**字段**旁 ③ 编辑器对应**行**(IDE 式)。
**需引擎确认/补的**:每一条 error/warning 是否**始终**带齐 `节点(phase) + field + file:line + severity` 这套定位?哪些错误码目前缺某一维(尤其能定位到具体节点/字段的)?补齐定位粒度,前端才能精准放标记。

# 三、trace(去黑盒)
**现状(已核实,事件流很丰富,34 类)**:`PhaseStart/PhaseEnd`(均带 `context` = 该边界处的黑板快照)、`LLMCall`(messages/tokens/response)、`ToolCall`(name/args/result/duration)、`WorkingMemoryUpdate`(全文)、`FinishTask`(reasoning/evidence)、`Validation*/Retry/Nudge`、`Compaction`(removed_summary + sidecar content_ref)、`PromptCaptured`、`AmbiguityReport`、`Interrupted/Resumed`、`ParallelMapGroup*`、`ArtifactSaved` 等。

前端要渲染:agent 节点输出做成**可折叠分类摘要**(思考/探索/工具/输出)、时间线、**点边上的 dot 看"节点间状态机"**、Prompt 三视图、节点内部执行子树内联展开。

**需引擎设计的缺口**:
1. **节点间操作事件(dot 的内容)**:dot = 两节点之间的转移点,代表"上节点 end 后、下节点 start 前的所有状态机操作"。黑板**快照**已有(PhaseEnd/PhaseStart 的 `context`),但**操作本身**——黑板 reduce/聚合(节点输出如何并入黑板)、并联节点输入的**筛选/分发**、截断/摘要/落盘——是否都显式 emit 了?(目前只见 Compaction/ArtifactSaved 等零散)。需要把这些"边上的操作"成系列 emit,前端点 dot 才能看到完整操作记录,而非只有前后快照。
2. **嵌套/父子链路**:节点内部微观执行 + **嵌套子图**时,事件是否带 `parent_node_id / node_type / 嵌套路径`?前端要据此组装"节点内部执行子树"和嵌套结构(现有 phase_name + run_id 是否够,还是需显式父链路?)。
3. **reducer 级前后态 diff(REQ-7)**:前端可用 PhaseEnd[A].context vs PhaseStart[B].context 做近似 diff;但"哪个 reducer 改了哪个 key"的权威 diff 需引擎 emit。请判断:引擎 emit 权威 reducer diff,还是前端近似就够?
4. **Prompt 三视图**:`PromptCaptured` 是否同时带 模板 / 喂入变量 / 渲染后 三者?若只有渲染后(LLMCall.messages),需补模板+变量。

# 四、debug(干预续跑)—— 与 trace 事件流 / runtime 状态机强耦合,一并设计
前端干预都锚在节点/dot 上:节点级 [Resume]、HitL 顶部问题框、点 dot 篡改黑板续跑。需引擎:
5. **节点级 checkpoint**:每节点输出存 checkpoint(现仅 thread/run 级),"从节点 X 续"才能复用 1..X-1 不重跑。
6. **checkpoint 有效性/失效**:上游节点/拓扑/输出 schema 改 → 判定哪些下游 checkpoint 失效(支撑前端"脏状态 [Resume] 置灰")。
7. **HitL 通道**:`AmbiguityReport` 已 emit 问题 → 需"答案注入 + 从断点续"的入口(前端事件映射 + resume API)。
8. **篡改后从某点续跑**:接受"某点被改过的黑板态" + 从该点续跑下游(resume 端点现为 501)。

> ⚠️ **耦合提醒**:#5/#6 的 checkpoint/状态机 与 **batch/loop 的 loop 累积态**(另一份给你的设计)本质同源(都是"存状态以便续/迭代")。请设计**统一的 checkpoint/状态机**,不要两套。

# 五、配套前端设计文档(请读)
- compile: `docs/studio/mvp1/02_capabilities/compile-lint.md`
- trace: `docs/studio/mvp1/02_capabilities/trace-observability.md`(含 dot 定义、agent 折叠渲染、回看交互)
- debug: `docs/studio/mvp1/02_capabilities/debug-resume.md`(三场景 UX)

> 若能读到,请先简述你读到的"dot = 节点间状态机转移点"和"节点级 checkpoint"两点,确认没读偏再继续。

# 六、请你给出
对二/三/四,**先确认现有引擎已覆盖哪些**(避免重造),再设计缺口:① compile 错误定位补齐;② trace 的节点间操作事件 + 嵌套链路 + reducer diff;③ debug 的节点级 checkpoint + 失效追踪 + HitL 注入续跑 + 篡改续跑(与 batch/loop 状态机统一)。请给具体方案、事件/接口 schema、关键取舍、最易错处。

## 用户原始指令(原文 —— dot 定义 + debug 取舍)
> dot就是langgraph的中间节点, 在进入一个节点之前以及从一个节点出来后的所有操作, 主要围绕状态机黑板, 还有输入文件、输出文件, 还有一些状态机操作比如截断摘要存储等等. 所以点dot看黑板状态机当时的内容, 并联线从dot出发是因为所有并联节点的输入是由这里的状态机统一筛选的; 点击dot, trace timeline显示从上个节点end, 到下个节点start之间的所有操作记录

> 节点级 checkpoint 粒度 要; 编辑器复用; (事件→节点态派生器归 trace)
