# execution-runtime 人话功能逻辑解释

execution-runtime 是 V0.3.0 engine 真正“开跑”的部分。skill-compilation 负责审图，state-and-io-contract 负责规定黑板边界，llm-routing 负责把角色变成模型，tracing 负责记录过程；execution-runtime 把这些东西串起来，按图执行每个 phase。

PM 点击运行后，engine 内部不是直接冲进某个 `SKILL.md` 开始叫模型。它先找到 skill 根目录，调用 compile 得到 `CompiledSkill`，再把 `CompiledSkill` 装配成一张可执行图。然后 runtime 建立本次 run 的初始黑板：外部输入经过 Input Funnel 后进入 `data.inputs`，框架控制信息进入 `flow`，LLM 对话进入 `messages`，本次运行有一个 `run_id`。最后 runtime 调用图执行，让 LangGraph 按依赖关系调度节点。

可以把一次 run_skill 想成一次剧场演出。compile 阶段是排练前确认剧本和分场；runtime 是正式演出时的舞台监督。舞台监督知道第一幕谁上场，第二幕谁接，哪里要叫灯光，哪里要让演员拿道具。演员真正表演时，舞台监督不替演员念台词，但负责让每一幕按顺序发生、把结果交给下一幕。

runtime 里的 phase 有三类。LOGIC phase 跑确定性 Python 函数。SKILL phase 让 LLM 在工具和最终交卷之间循环工作。SUBGRAPH phase 跑一张固定子图。三类 phase 都是图里的节点，但执行方式完全不同。

LOGIC phase 像流水线上的固定机器。它拿到 StateMapper 切出来的 `phase_input`，调用登记好的 Python action，然后把 action 返回值包装到自己的 `phase_outputs["phase_id"]` 命名空间。比如 `clean_manual` 读 `manual_text`，返回 `clean_text`。它不看整张黑板，也不自己决定下一步走向。

LOGIC 的优点是可预测。清洗文本、拆段、格式转换、拼接 JSON、计算 hash、做轻量校验，都适合放 LOGIC。它不需要 LLM 的判断力，也不应该承担“读一大段文字后总结观点”这类开放任务。

SKILL phase 是 LLM ReAct 节点。ReAct 可以理解成“想一下、调工具、看结果、再想一下”的循环。engine 给 LLM 一组消息、一个 system prompt、当前 phase 的输入、可用工具、subagent 工具、exit contract 和 `finish_task`。LLM 每轮可以直接回答，也可以调用工具；工具结果回来后，LLM 再基于结果继续推理。直到它调用 `finish_task` 交卷，或者达到轮次上限。

举例：`extract_points` 是 SKILL phase。它拿到 `clean_text` 后，第一轮模型可能先调用 `read_artifact` 读取附录；第二轮调用 `call_subagent_claim_checker` 核验某个功能声明；第三轮用 `finish_task` 提交 `feature_points` 和 `risk_points`。runtime 在每一轮都负责把模型回复、工具调用、工具结果放进 messages，并把最终交卷结果写进 phase 输出。

ReAct loop 需要上限。没有上限，模型可能陷入“继续思考、继续调工具、继续修正”的无限循环。V0.3.0 的 loop 有最大轮次；接近上限时，exit_contract 会提醒模型必须收束；到达严格上限时，runtime 不再放任模型继续拖延，而是按错误体系结束。这不是惩罚模型，而是保护 run 不被一个 phase 无限占住。

exit_contract 是 SKILL phase 的“交卷规则”。它告诉 LLM 最终必须用什么格式、交哪些字段、什么时候算完成。Q11 决策后的形态是：每轮临时注入，不永久污染 messages；倒数第一轮给 graceful warning，也就是“你快到上限了，请尽快按格式交卷”；最后一轮如果仍未交卷，进入 strict error，也就是明确失败并给结构化错误。

这个设计解决两个问题。第一，exit_contract 每轮都要被模型看到，否则模型容易忘记交卷格式。第二，它不能每轮都被永久追加进历史，否则 messages 会堆满重复规则。正确做法像监考老师每次提醒“请按答题卡作答”，但不会把每次提醒都写进考生答案本里。

SUBGRAPH phase 是固定流程里的子图。它不是 LLM 想调才调，而是主图走到这个 phase 时必然执行。比如主图里有 `quality_review`，这个 phase 内部是一张子图：先检查字段完整性，再让 critic 审核，再生成修复建议。主图不关心子图内部每一步，只关心它最终按契约交回什么。

SUBGRAPH 像生产线里嵌入的一段标准检测工序。每件产品到这里都要过检测，不是某个工人临时决定。它的输入来自主图显式映射，输出也按声明回到主图。它不应该默认继承父图整张黑板。

subagent 和 subgraph 的区别非常重要。subgraph 是固定拓扑节点，流程走到那里就执行；subagent 是 SKILL phase 内 LLM 主动调用的子任务。subgraph 像审批流程里固定存在的“法务复核”环节；subagent 像某个分析员工作时主动叫来“事实核查助手”帮忙。

举例：`extract_points` 这个 SKILL phase 在分析产品手册时，模型发现一句话像夸大宣传，于是调用 `call_subagent_claim_checker`，把 `claim` 和 `source_text` 传给子 agent。这个子 agent 不是主图固定步骤，而是 LLM 在某一轮 ReAct 中主动触发的工具。Trace 里应该看到它是一次 tool call，而不是主图里的固定 phase。

subagent_depth 是防递归失控的保险丝。一个 subagent 里面可能也有 SKILL phase，理论上它也能调用另一个 subagent。如果不设上限，A 叫 B，B 叫 C，C 又叫 A，或者模型不断生成新的子任务，就会出现 fork-bomb 式递归，把运行资源耗尽。`subagent_depth` 就是记录“现在嵌套到第几层”，超过上限就拒绝继续进入。

用办公室比喻：经理可以叫一个同事帮忙，同事也可以请另一个同事查资料，但不能无限转包。转包层级太深，责任链断了，成本也失控。runtime 的 depth cap 就是“最多转包几层”的制度。

真实 LLM 的注入由 llm-routing 负责。runtime 不自己读取 provider key，也不直接决定 `analyst` 用哪个模型。Studio 在运行前实例化符合 `ModelResolverProtocol` 的 resolver，传给 engine。runtime 执行 SKILL phase 时，根据 phase 的 `llm_role` 向 resolver 要一个 ChatModel。engine 只认 Protocol，不绑死具体 Studio 实现。

这里不展开 provider、fallback、MockModelResolver 等细节；它们在 llm-routing 文档里解释。execution-runtime 只需要知道：跑到 SKILL phase 时，能按 role 拿到一个可调用、可绑定工具的 chat model；拿不到时，抛结构化错误。

异常归一化是 runtime 的另一项职责。V0.3.0 的错误码体系使用 `F-v0.3-*` 这类前缀，让 Studio、CLI 和测试能按错误类型处理。比如输入漏斗失败、phase IO 缺字段、模型解析失败、工具参数非法、subagent 深度超限、所有 provider fallback 用尽，都不应该只是一段随意字符串。

结构化异常不是为了“看起来专业”，而是为了把错误贴回正确位置。`F-v0.3-model-unavailable` 应该告诉 Studio 是哪个 phase 的哪个 `llm_role` 没拿到模型；`F-v0.3-subagent-depth` 应该告诉 Studio 是哪个 subagent 调用链超过深度；`F-v0.3-exit-contract` 应该告诉 Studio 哪个 SKILL phase 到最后一轮仍没按规则交卷。

runtime 和 state contract 的配合也很关键。LOGIC、SKILL、SUBGRAPH 都不应该直接拿全局 `data`。runtime 在每个 node 开始前让 StateMapper 生成 `phase_input`；node 结束后把输出包装到 `phase_outputs["phase_id"]`。这样下游 phase 只有在声明依赖对应上游和字段时，才能读到这些输出。

举例：`clean_manual` 产出 `phase_outputs["clean_manual"]["clean_text"]`。`extract_points` 声明依赖 `clean_manual` 并读取 `clean_text`，StateMapper 才把这个字段切给它。另一个不依赖 `clean_manual` 的 phase，即使在同一张图里，也不会自动看到 `clean_text`。

runtime 和 tracing 的配合也很直接。每个 phase 开始前发 `NODE_START`，记录 `phase_input`；结束后发 `NODE_END`，记录 phase 输出；SKILL 调模型前后发 LLM 事件；调用 subagent 前后发 SUBAGENT 事件；真正失败时发 EXCEPTION。trace 不是 runtime 外部猜出来的，而是 runtime 在真实调用点发出的。

最终心智模型：execution-runtime 是 V0.3.0 engine 的现场调度层。它拿 compile 的图纸，按 state contract 切输入，按 LLM routing 拿模型，按 graph 拓扑跑 LOGIC / SKILL / SUBGRAPH，按错误体系归一化失败，按 tracing 体系记录过程。它不负责定义所有规则，但它负责让规则在真实运行中生效。

