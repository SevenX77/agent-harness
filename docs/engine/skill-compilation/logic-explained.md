# skill-compilation 人话功能逻辑解释

skill-compilation 是 V0.3.0 engine 的“开工审图”环节。它不跑任务，不调用模型，不执行 Python action；它只负责把一个 skill 目录读成一份可执行说明书，并在开跑前发现那些“图纸本来就画错了”的问题。

可以把一份 skill 想成一条小型生产线。`GRAPH.md` 是生产线布局图，`io/inputs.json` 是进厂原料清单，`io/outputs.json` 是出厂验收标准，`phases/` 下面每个目录是一台机器自己的操作说明。compile 阶段要做的事，就是确认这条生产线的图纸、原料清单、机器说明和出厂标准都能互相对上。

一份 V0.3.0 skill 的标准形态是目录，不是一个孤立的 Markdown 文件。根目录必须有 `GRAPH.md`，必须有 `io/inputs.json` 和 `io/outputs.json`，必须有 `phases/{name}/` 子目录。每个 phase 目录里只能有一种节点文件：`LOGIC.md`、`SKILL.md` 或 `SUBGRAPH.md`。这个限制不是形式主义，而是为了让 engine 不用猜：看到 `LOGIC.md` 就知道这是确定性 Python action，看到 `SKILL.md` 就知道这是 LLM ReAct phase，看到 `SUBGRAPH.md` 就知道这是固定子图。

举个具体例子。PM 上传一篇产品手册，希望生成“功能摘要 + 风险提示 + 对外说明”。skill 根目录里，`GRAPH.md` 写三步：`clean_manual`、`extract_points`、`write_summary`。`clean_manual/LOGIC.md` 负责清洗文本；`extract_points/SKILL.md` 让 LLM 抽功能点和风险点；`write_summary/LOGIC.md` 把结果整理成最终 JSON。`io/inputs.json` 声明入口只收 `manual_text` 和 `locale`；`io/outputs.json` 声明最终必须有 `summary`、`risks`、`public_copy`。

compile 阶段第一件事，是检查目录硬约束。没有 `GRAPH.md`，engine 不知道路线图在哪里；没有 `phases/`，engine 不知道有哪些机器；phase 目录里同时放了 `LOGIC.md` 和 `SKILL.md`，engine 不知道这台机器到底是确定性 action 还是 LLM 节点；`GRAPH.md` 里引用了不存在的 phase，路线图就断了。这些都应该在 compile 阶段直接失败。

compile 阶段第二件事，是把文本说明读成结构化说明书。人看到的是 Markdown、XML-ish phase 标签、frontmatter、JSON Schema；engine 需要的是 `CompiledSkill`：里面有根图 manifest、phase 列表、每个 phase 的类型、每个 phase 的输入输出声明、action registry、tool registry、subagent metadata、以及 Studio 能用来定位错误的结构化信息。

`CompiledSkill` 可以理解成“开工包”。runtime 后面不应该再靠临场翻 `GRAPH.md` 猜流程，而是拿这份开工包装配执行图。开工包里已经写清楚：这条线有哪些节点，每个节点是什么类型，它能读哪些字段，它会写哪些字段，它能调用哪些工具，它声明了哪些 subagent。

compile 阶段不做真实业务执行。`clean_manual` 的 Python action 可能会把长文本切段，但 compile 不会拿一篇真实手册去切。它只确认 action 被登记了、入口形态合理、不会明显违反工程约束。真正切段要等 runtime 跑到 `clean_manual`。

compile 阶段也不调用真实 LLM。`extract_points/SKILL.md` 可以声明 `llm_role: analyst`，compile 只保留这个角色声明，不去问 Studio 这个 role 现在对应 Claude、GPT 还是某个私有模型。模型解析属于 llm-routing 和 execution-runtime 的运行期职责。

compile 阶段也不校验某一次用户传进来的具体值。比如用户运行时传 `manual_text="..."`、`locale="zh-CN"`、`debug_token="abc"`，compile 不处理这次调用。compile 只确认 `io/inputs.json` 的规则存在且合法。把 `debug_token` 拦掉，是 runtime Input Funnel 的事。

拓扑校验和数据流校验必须分开讲，因为它们解决的是两类不同错误。

拓扑校验检查“路有没有画通”。比如 `write_summary` 依赖 `extract_points`，那 `extract_points` 必须存在；不能出现 `clean_manual` 依赖自己；不能出现 A 依赖 B、B 又依赖 A 的环；也不能有一个孤立 phase 永远不会被执行。拓扑校验像检查生产线皮带有没有接上。

数据流校验检查“货有没有送到”。路线图可能是通的，但字段没接上。比如 `extract_points` 声明要读 `clean_text`，而上游 `clean_manual` 只声明产出 `normalized_text`，这条图拓扑上没问题，数据上却断了。运行到一半才发现 `clean_text` 不存在，会让用户以为是 LLM 或 action 坏了；实际上是图纸里的字段名字没对齐。

所以 V0.3.0 compile 要同时做两件事：先确认 phase 执行顺序合法，再确认每个 phase 声明需要的字段，都能从全局输入或它依赖的上游 phase 输出里找到。只有这样，engine 才能在开跑前告诉 PM：“`extract_points` 要 `clean_text`，但没有任何上游产出它。”

phase-level IO 是数据流校验的基础。每个 phase 都要说清楚自己读什么、写什么。`clean_manual` 读 `manual_text`，写 `clean_text`；`extract_points` 读 `clean_text`，写 `feature_points` 和 `risk_points`；`write_summary` 读 `feature_points`、`risk_points`、`locale`，写 `summary`、`risks`、`public_copy`。如果某个 phase 不声明 IO，engine 就只能让它看整张黑板，这会把数据边界变成猜谜。

LOGIC phase 的 compile 重点，是确认它的 action 是一个受控的确定性步骤。比如 `clean_manual` 声明调用 `actions.clean:run`，compile 会把这个 action 登记进 action registry，并确认它写出的字段不越过自己声明的输出边界。它不会执行 action，但会尽量提前发现“这个 action 说要写一个 schema 之外的字段”这类问题。

SKILL phase 的 compile 重点，是确认 LLM 节点的工作条件完整。它要有 prompt，有 exit contract，有可用工具列表，有 `llm_role`，有 phase IO。比如 `extract_points` 可以声明工具 `read_artifact` 和 subagent `claim_checker`。compile 不会让 LLM 工作，但会把这些工具和 subagent 编成 runtime 能挂载的工具说明。

SUBGRAPH phase 的 compile 重点，是确认固定子图边界清楚。SUBGRAPH 不是“LLM 想调就调”的助手，而是主流程固定会走的一段子流程。它必须声明自己从父图读哪些字段，子图完成后向父图交付哪些字段。这样主图不会把整张黑板一股脑塞给子图，子图也不会把内部临时字段倒回主图。

subagent metadata 在 PM 视角里，就是“LLM 可以叫来的登记助手卡片”。一个 SKILL phase 里可以声明 `claim_checker` subagent。compile 会读取这个 subagent 的说明：它叫什么、做什么、需要什么输入 schema、预期返回什么。runtime 后面会把它变成一个具体工具，比如 `call_subagent_claim_checker`。LLM 在 ReAct loop 里调用这个工具时，只能按这张卡片声明的参数传值。

这和把 subagent 写进 prompt 不一样。写进 prompt 是“口头告诉模型有个助手”，模型可能格式写错、参数乱传、名字拼错。compile 成工具是“把助手登记成一个带入参 schema 的按钮”。模型要调它，就必须按工具 schema 提交参数。这样 Studio trace 也能清楚显示：哪个 SKILL phase 在第几轮调用了 `call_subagent_claim_checker`，传了哪些字段。

compile cache 是加速器，不是发动机。冷编译时，engine 从磁盘读 `GRAPH.md`、phase 文件、IO schema、actions、tools、subagents，整理成 `CompiledSkill`。如果目录没变，下次可以直接从 cache 拿开工包，省掉重复解析。cache 命中和冷编译的结果必须等价；如果 cache 写入失败，compile 也不应该失败，因为任务能不能跑不应该取决于缓存目录能不能写。

用厨房比喻：compile 是厨师开火前把菜单、食材、锅具、工序检查一遍；cache 是昨天整理好的备菜清单。备菜清单能省时间，但如果冰箱标签写不了，厨师也不能因此拒绝做饭。最多是这次重新检查一遍。

错误信息必须结构化，是因为 Studio 需要把错误贴回画布。纯字符串“field clean_text missing”对人勉强能看，对 UI 不够。Studio 需要知道：错误码是什么，哪个 phase 出错，缺哪个字段，这个字段本来应该来自哪些上游，错误对应哪个文件或 phase 区块。这样 Canvas 才能把 `extract_points` 节点标红，把相关边高亮，而不是只弹一个大段异常。

结构化错误也能减少误判。`GRAPH.md` 里依赖了不存在的 phase，这是拓扑错误；`extract_points` 要读 `clean_text` 但上游没产出，这是数据流错误；`io/inputs.json` 不是合法 JSON Schema，这是 IO schema 错误；LOGIC action 想写 schema 之外的字段，这是 action 输出契约错误。它们不应该都叫“compile failed”。

compile 不是为了让 skill 作者多写文件，而是为了把系统边界提前说清楚。目录结构让 engine 知道哪里是图、哪里是输入输出、哪里是节点；phase IO 让 engine 知道字段怎么流；subagent metadata 让 LLM 的动态子任务变成可校验工具；cache 让重复编译更快；结构化错误让 Studio 能精准反馈。

最终心智模型：skill-compilation 是 V0.3.0 engine 的审图员和登记员。它把一个 skill 目录变成可执行说明书；它不替 runtime 干活，但它负责在 runtime 开始前把路线断点、字段断点、工具登记问题和结构错误尽量拦住。图纸过不了审，就不该开工。

