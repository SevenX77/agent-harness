请用中文回答。

你是一位资深的执行引擎 / 后端架构师。下面是一套"graph skill 工作流引擎"里 **predict(试飞)+ golden(逐节点验收)+ run(真跑)** 这三块的**已定设计**。请你**设计后端实现方案**:哪些复用现有、哪些要改、哪些新建,数据模型 / 接口 / 落盘怎么做,以及最容易出错的地方。**本次不涉及 batch/loop**(它另有独立设计)。

# 一、系统是什么
- 一个技能 = 一个 DAG,由 `GRAPH.md` 定义;节点分 agent(调 LLM)、logic(纯 Python)、subgraph(调子图)。
- 引擎接收"图 + 输入",按拓扑跑一遍,节点间通过共享黑板(blackboard)传数据。
- 现有后端**已具备**:`predict_skill`(试飞执行)、`run_skill`(真跑)、WS 流式 trace、运行成功自动 git commit(autocommit)、一个"predict trace 不可固化为 golden"的 409 守卫、批量运行路由。

# 二、三块的已定设计(需要你设计后端)

## A. golden —— 这是最大的改动(模型要换)
**现状(要被取代)**:golden = 整次运行跑完后捕获的快照(把整次 `final_state.json` copy 成 baseline)。
**新模型**:golden = **逐个 agent 节点的"期望输出"**,由作者 / copilot **事先定义**(不是从某次运行捕获)。用途两个:
1. **predict 回放**:有 golden 的 agent 节点,predict 时直接吐出它的 golden 当输出(不调真模型);
2. **run 后对比**:真跑产生实际输出,和该节点的 golden 做**字段级 diff**。

需要你设计的后端点:
1. **逐节点 golden 的存储模型**(取代"整次快照"):每个 agent 节点一份期望输出,存哪、什么结构、怎么和节点身份绑定。
2. **golden 回放**:predict 时,引擎对"有 golden 的 agent 节点"用 golden 当输出(对应现有 `mocked_source=golden_case` 的逐节点版)。
3. **逐节点 diff**:run 后该节点实际输出 vs 该节点 golden 的字段级比较。
4. **golden 失效校验**:当某节点的**输出 schema 改了、导致 golden 缺了新要求的字段**时,要能检测出来并**作为编译错误暴露**(必须补齐才能 predict)。改 prompt / 改 agent 内部设置则**不**失效(golden 只绑输出 schema)。
5. **空 golden 模版自动生成**:按节点的 `io.outputs` schema 生成一个空 golden 模版(给作者手填)。
6. 现有 409 守卫(predict trace 不可晋升 golden)在新模型下**继续成立**(golden 是作者定 / 手填,本就不从 trace 捕获)。

## B. predict —— 小改
- **mock 策略由 golden 状态自动决定**:agent 节点**无 golden → 启发式占位**(免费假输出,只验链路);**有 golden → 回放 golden**。不需要前端手动选 mock 策略。(现状 `mock_llm=Any=None`,无逐节点 golden 驱动的自动选择。)
- predict 的职责 = **把逻辑跑通 + 确认输入/输出 schema 真没问题**(它是 run 的硬前提);logic 节点 predict 时照常真跑。请确认现有 `predict_skill` 是否已做 schema 校验,缺什么补什么。

## C. run —— 大多复用
- `run_skill` / autocommit / WS / 运行历史 大多已就绪。新增的主要是 **run 后的逐节点 golden diff**(见 A.3)。请指出哪些直接复用、哪些要配合 golden 新模型调整。

# 三、配套设计文档(请阅读)
- predict 设计: `docs/studio/mvp1/02_capabilities/predict.md`
- golden 机制(含状态机/创建两路/失效规则/测试关键点): `docs/studio/mvp1/02_capabilities/golden-eval.md`
- run 设计: `docs/studio/mvp1/02_capabilities/run-execution.md`
- 引擎物理/格式契约: `docs/engine/mvp0/skill-spec/`、`docs/engine/mvp0/workspace-spec/baseline.md`

> 若你能读到这些文件,请先简述你读到的"golden 新模型"要点再继续,确认没读偏。

# 四、请你给出
针对 A/B/C,给出后端设计:数据模型(尤其逐节点 golden 的存储)、接口/调用点改动、predict 的 mock 自动选择落点、逐节点 diff 实现、golden 失效校验怎么接进编译期、以及哪些复用现有代码。请标出关键取舍和最易出错处。**不要设计 batch/loop。**

---

## 用户原始指令(原文,一字不改 —— golden 机制的设计依据)

> 我来模拟一下用户心智: 设计完compile没问题,第一次点击predict, 测试逻辑链路跑通没问题, agent node 状态从未测试变成逻辑OK(根据io设置), 测试完弹出popover 问你需不需要现在copilot帮你一起完成golden设计(?icon,解释一下golden是什么, 这套机制怎么运作的, 没有golden时, 只要运行一次predict或者run,都会弹一次), 用户选择要, 自动新建一个chat发送prompt(需设计) 给copilot, 帮你预测结果(copilot根据你的整个graph: 1. 分析你需要什么结果; 2.这个节点预计真跑起来会得到什么结果; 3. 分析差距, 建议修改方案), 直到你和copilot讨论出来golden是什么, 改变这个node的golden参数. 如果有多个agent 节点, popover依次弹出,确认完一个, 弹下一个; agent节点需要一个新状态标签, 有没有golden? 有的情况下predict按照golden输出走; golden相关设置放在i/o 面板, 因为和输出什么直接相关; 没有golden时,会根据输出schema自动创建一个符合schema的golden模版, 你可以通过i/o panel, 打开golden的json文件, 手动填入golden数据; 一旦golden有数据了, 状态自动切换到golden, predict按照golden输出运行. run运行后可以进行实际结果和golden的diff对比.

> g-d 看改什么, 改prompt,改agent内部设置都没事, 只有改输出schema后, golden字段缺失需要的字段, 需要弹警告⚠️,触发编译错误, 必须补上才能跑predict

> predict是硬前提, 但是golden不是. predict的任务是把逻辑跑通, 确认逻辑、输入输出schema等等真的没问题, 才能进入run; 有没有golden的区别只在于predict在agent节点拿哪个mock数据输出而已
