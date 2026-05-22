# state-and-io-contract 人话功能逻辑解释

state-and-io-contract 是 V0.3.0 engine 的数据纪律。它规定每次运行时数据放在哪里，外部输入怎么进来，每个 phase 能看什么，phase 输出怎么存，父子图之间怎么隔离，以及多个节点同时写数据时怎么合并。

如果没有这套纪律，整张图就像所有人围着一块白板工作：谁都能看，谁都能改，谁都能擦。小 demo 里这很方便，真实系统里会变成灾难。一个 phase 可能读到不该读的字段，一个子图可能误改父图数据，两个并行分支可能同时写同一个 key，trace 里可能泄露调试 token。

黑板 `BlackboardState` 是每次 run 的共享工作表。它不是一个单纯的业务 dict，而是分层状态。`data` 放业务数据，比如用户输入、phase 输出、最终结果；`flow` 放框架控制信息，比如 subagent 深度、重试次数、critic 指标、finish 状态；`messages` 放 LLM 对话历史，比如 system prompt、模型回复、tool result。

用办公室比喻，`data` 是客户资料和每个部门交付的成果；`flow` 是内部流转单、审批章、计时器和控制标记；`messages` 是 LLM 分析员的聊天记录。三者分开，才能避免把“内部处理状态”误当业务结果，或把“模型聊天过程”误当最终输出。

Input Funnel 是入口安检。用户调用 skill 时可能传很多参数：`--scene_id=42 --debug_token=xyz --article_text=...`。如果 `io/inputs.json` 只声明 `scene_id` 和 `article_text`，那 `debug_token` 就应该被丢弃或按 strict 策略拒绝。它不能因为用户传了，就自动进入黑板。

这个例子非常重要。没有 Input Funnel，`debug_token` 进入 `data` 后，某个 LOGIC action 可能不小心读到它，某个 SKILL phase 可能把它发给 LLM，trace 可能把它写进文件。Input Funnel 的任务就是在入口处说：这张图只接收声明过的业务字段，其他东西不能混进去。

Input Funnel 不只是丢字段。它还要检查 required 字段是否存在，类型是否能接受，默认值是否能补。比如 schema 声明 `scene_id` 是 integer，用户从 CLI 传来字符串 `"42"`，engine 可以按规则安全转成 `42`；如果传来 `"abc"`，就应该报输入错误，而不是让后面的 phase 自己撞墙。

每个 phase 只看到自己声明的字段，这件事由 StateMapper 负责。StateMapper 像资料管理员：它看当前 phase 的 `io.inputs`，再从 `data.inputs` 和上游 `phase_outputs` 中取字段，组装一份小而干净的 `phase_input`。phase 运行时只拿到这份 `phase_input`，不是整张黑板。

比如 `summarize` 声明读取 `clean_text` 和 `locale`。StateMapper 会从 `phase_outputs["clean"]["clean_text"]` 拿清洗后的文本，从 `data.inputs["locale"]` 拿语言设置，组合成 `{clean_text: "...", locale: "zh-CN"}`。它不会把 `raw_pdf_bytes`、`debug_token`、`internal_notes` 一起交给 `summarize`。

phase_outputs 命名空间是“每个 phase 自己的抽屉”。一个 phase 结束后，它的输出不直接撒到 `data` 顶层，而是放到 `phase_outputs["phase_id"]` 下面。`summarize` 产出的 `summary` 字段会进入 `phase_outputs["summarize"]["summary"]`；下游声明依赖 `summarize` 且声明读取 `summary`，才能拿到它。

这种命名空间能解决很多混乱。假设 `extract_title` 和 `extract_tags` 并行运行，它们都想产出一个叫 `result` 的字段。如果直接写顶层 `data["result"]`，engine 不知道该保留谁。放进命名空间后，它们分别是 `phase_outputs["extract_title"]["result"]` 和 `phase_outputs["extract_tags"]["result"]`，不会互相覆盖。

如果下游 `assemble` 想同时读这两个结果，它必须明确声明来源或字段映射。否则两个上游都叫 `result`，StateMapper 应该报“输入来源不明确”，而不是随机拿一个。这种错误越早越好，最好 compile 阶段就发现；runtime 也要继续守住边界。

smart_dict_reducer 取代 shallow_dict_merge，是因为合并数据时要区分“顺序覆盖”和“并行冲突”。旧的浅合并只要看到同名 key 就报错，这太粗。它能防止并行分支冲突，但也误伤合法的顺序更新。

顺序覆盖的例子：`draft_summary` 先产出 `summary="初稿"`，后面的 `polish_summary` 明确依赖它，并产出 `summary="润色稿"`。这是一条线上的后一步更新前一步，业务上合理。并行冲突的例子：`branch_a` 和 `branch_b` 同时产出顶层 `summary`，下游没有说明该用谁，这就是冲突。

smart_dict_reducer 的心智模型是：同一条顺序路径上，后一步可以在规则允许的输出位置更新；同一个并行 fan-in 步里，两个来源同时写同一位置，要阻断。它不是简单“谁后到谁赢”，也不是简单“同名就死”。它要知道冲突发生在什么执行语境里。

父子图隔离是 V0.3.0 的硬边界。subgraph 和 subagent 调用时，子图初始 `data` 只来自显式传入的参数，而不是父图整个 `data` 的拷贝。尤其是 subagent：父 SKILL phase 的 LLM 必须通过 tool call kwargs 明确传入字段，子 agent 只能看到这些 kwargs 经过 schema 校验后的结果。

举例：父图里有 `customer_profile`、`contract_text`、`debug_token`、`internal_notes`。LLM 调用 `call_subagent_clause_checker` 时，只传 `{clause_text: "...", jurisdiction: "US"}`。子 agent 的初始 data 就只有这两个字段。它不能自动看到 `customer_profile`，更不能看到 `debug_token`。

这就是 Q13 和 A6 的协同。Q13 把 subagent / subgraph 编译成带 schema 的具体工具，比如 `call_subagent_clause_checker`，要求 LLM 按 schema 传参；A6 规定子图初始黑板只来自这些已校验参数，不隐式继承父图黑板。一个管入口形状，一个管状态隔离。

SUBGRAPH phase 也要隔离。虽然它是固定流程拓扑里的节点，不是 LLM 主动工具调用，但它也应该有明确 input mapping。父图把哪些字段交给子图，子图把哪些字段交回父图，都要写清楚。否则一个质量检查子图可能无意读到主图所有临时字段，甚至把内部 `scratch` 写回父图。

深拷贝是防止引用共享的保险。Python 里的 dict/list 是可变对象。如果父图把一个嵌套 list 交给子图，子图只是 append 一项，父图可能也被悄悄改了。看起来子图没有返回任何修改，父图却变了。这种 bug 很难查。

所以 runtime 构造 `phase_input`、child data、child flow 时，需要做结构化复制。普通 JSON-like 数据可以 deep copy；不能安全复制的大对象，比如打开的文件句柄、SDK client、DataFrame，不应该直接塞进黑板。它们要么被拒绝，要么转成显式 artifact 引用。

flow 也要小心。子图可以继承必要控制字段，比如 run id、trace context、subagent_depth，但不能共享同一个可变 flow dict。否则子图改了重试计数或临时状态，父图可能被污染。正确做法是复制后写入新的 depth 和 child context。

messages 的边界也要清楚。父 SKILL phase 的对话历史不应该自动成为子 agent 的对话历史。子 agent 应该从自己的 system prompt 和自己的输入开始工作。父 LLM 可以把必要上下文作为 tool args 传进去，但不能把整段父会话直接当作子会话。

这套状态规则会让 tracing 更可靠。`NODE_START` 记录的就是 StateMapper 切出来的 `phase_input`；`NODE_END` 记录的就是这个 phase 的输出命名空间；Edge Inspection 展示的就是上游 phase 输出到下游 phase 输入的字段。没有 state contract，trace 只能记录一团全局 data，PM 看不出哪条边传了什么。

最终心智模型：黑板不是公共涂鸦墙，而是带权限、带抽屉、带安检的工作台。Input Funnel 控制外部输入；StateMapper 控制每个 phase 能看什么；phase_outputs 控制每个 phase 产出放哪里；smart_dict_reducer 控制多路结果怎么合并；深拷贝和父子图隔离控制引用和隐式继承。这样图跑起来才可解释、可审计、可调试。

