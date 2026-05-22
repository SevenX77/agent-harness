# llm-routing 人话功能逻辑解释

llm-routing 负责回答一个问题：V0.3.0 skill 里的 SKILL phase 到底用哪个大模型。skill 作者不应该在 phase 里写死“调用某个厂商、某个模型、某个 API key”。他应该声明这个 phase 需要什么角色，比如 `analyst`、`critic`、`writer`。把角色翻译成具体模型，是 routing 的职责。

最简单的比喻是“岗位排班”。流程里写“这一步需要分析员”，不是写“请张三用自己的钥匙打开某间办公室”。Studio 或独立的模型配置层维护排班表：`analyst` 今天由 Claude Sonnet 负责，`critic` 由 GPT-4o 负责，`writer` 由公司私有网关负责。engine 只按岗位要人。

一个 V0.3.0 skill 拿到 LLM 的路径是这样的：`SKILL.md` 里声明 `llm_role: analyst`；runtime 执行到这个 phase；engine 调用传入的 `ModelResolverProtocol`，问“请给我 analyst 对应的 ChatModel”；resolver 查 routing 配置和用户可用 provider；resolver 返回一个 LangChain-compatible ChatModel；engine 把 phase tools 绑定上去，然后进入 ReAct loop。

这里的重点是：phase 不直接知道 model。`extract_points` 只知道自己需要 `analyst`；`review_claims` 只知道自己需要 `critic`。这样同一份 skill 可以在不同 Studio workspace 里用不同模型运行。A workspace 的 `analyst` 是 Claude，B workspace 的 `analyst` 是 GPT，skill 文件本身不用改。

routing config 可以很直观。比如：`{"default": "anthropic:claude-sonnet", "critic": "openai:gpt-4o", "fast": "wavespeed:any-llm"}`。更真实的配置会有候选链：`analyst` 首选 `anthropic:claude-sonnet`，失败后试 `openai:gpt-4o`，再失败试 `gemini:pro`。ModelResolver 把 role 展开成这条候选链。

role 到 model 通常分两层。第一层是“岗位选哪个模型档位”：`analyst -> sonnet_4`，`critic -> gpt_4o`。第二层是“这个模型档位有哪些 provider 候选”：`sonnet_4 -> anthropic primary, openai-compatible fallback`。第一层是业务角色，第二层是供应商路由。把这两层分开，PM 才能理解为什么“critic 换模型”和“provider 临时不可用”不是同一个问题。

ModelResolver 是调度员。它看 role、model override、workspace 配置、provider 可用性策略，产出一个可调用的 ChatModel。engine 不关心它怎么查配置，不关心它在哪里读用户 key，不关心它是否做了权限判断。engine 只要求它满足 Protocol：给我一个 role，返回一个能被 SKILL phase 调用的模型对象。

GatewayChatModel 是司机。resolver 交给它一条候选路线，它真正负责开车。调用模型时，如果第一个 provider 503、超时或被临时标记为 down，GatewayChatModel 自动换下一个候选。它还负责记录 usage、provider down TTL、fallback event，并把最终成功结果包装成 LangChain 期望的消息。

举例：`extract_points` 使用 `llm_role: analyst`。Studio routing 里 analyst 的候选链是 Claude -> GPT -> Gemini。运行时 Gateway 先调 Claude，Claude 超时；Gateway 把 Claude 暂时标记为 down，继续调 GPT；GPT 成功返回 tool call。对 phase 来说，这一轮 LLM 调用成功。用户不需要手动重试，Studio trace 可以记录发生过 fallback。

只有所有候选都失败，错误才应该抛给 engine。比如 Claude 超时，GPT 也 503，Gemini credential 失效，候选链全部耗尽。GatewayChatModel 这时抛出模型不可用错误，runtime 把它归一化成 `F-v0.3-*` 错误，trace 发 EXCEPTION，Studio 把对应 SKILL phase 标红。

单个 provider 失败不是 phase 失败。这个限定很重要。否则任何一次 503 都会让用户看到红色节点，即使系统已经自动 fallback 成功。正确心智模型是：provider fail 是 Gateway 内部路由事件；所有候选 fail 才是 engine runtime 失败。

为什么具体 ModelResolver 不放在 engine？因为 engine 是图执行引擎，不是用户配置中心。engine 应该知道怎么跑 LOGIC、SKILL、SUBGRAPH，怎么切 phase input，怎么绑定工具，怎么记录 trace。它不应该知道某个 Studio workspace 配了哪些 provider key，不应该知道 Anthropic/OpenAI 的 credential 存在哪里，也不应该知道某个用户有没有权限用某个模型。

Studio backend 或一个独立 package 才适合放具体 ModelResolver。它知道用户配置、provider key、workspace policy、roles YAML、OAuth 或密钥管理。具体物理位置由 PM 拍：可以在 Studio backend，也可以在独立 package。logic 层只固定边界：具体 resolver 不属于 engine core。

engine 只认 `ModelResolverProtocol` 的意义，是把执行和配置解耦。Protocol 像插座规格：engine 只要求“插进来以后能给我 ChatModel”。至于插头背后是 Studio resolver、测试 MockModelResolver、企业私有 resolver，还是未来另一个配置系统，engine 都不需要改。

这也避免 engine 绑死具体 SDK。engine 不应该因为要运行一张图，就直接 import Anthropic SDK、OpenAI SDK、Google SDK、某个私有 provider SDK。SDK 的复杂性应该被 GatewayChatModel / LLMClientManager / Studio resolver 这些配套层消化。engine 主执行链只看到统一 ChatModel。

测试时用 MockModelResolver。它实现同一个 Protocol，但不查真实配置、不拿真实 key、不发真实网络请求。测试可以规定：`analyst` 返回 FakeChatModel，第一次回复调用工具，第二次调用 `finish_task`；`critic` 返回另一个 FakeChatModel，直接给审核通过。这样 runtime 测试仍然走真实 role resolve 形状，但成本和外部依赖为零。

Predict 模式也可以看成一种特殊 resolver。它不是返回真实 provider-backed Gateway，而是返回能标记 mocked_source 的模型 wrapper。这样 golden_case、copilot、heuristic_stub、manual 都能进入同一条 runtime 入口，而不是给 runner 再开一个 `mock_llm` 后门。

llm-routing 和 execution-runtime 的边界也要清楚。runtime 只在 SKILL phase 需要模型时问 resolver；resolver 返回 ChatModel；runtime 把 tools bind 上去并进入 ReAct loop。runtime 不应该在每轮里自己决定 fallback，也不应该自己读 roles 配置。fallback 在 Gateway，配置在 resolver，执行在 runtime。

llm-routing 和 tracing 的关系是：Gateway 内部 fallback 可以产生日志或 fallback event，但不等于 runtime EXCEPTION。Trace 里可以展示“本次 LLM 调用从 provider A fallback 到 provider B”，但 Canvas 不应该因为 provider A 挂了就标红，只要 provider B 成功。所有候选失败时，才由 runtime 发 EXCEPTION。

llm-routing 和 skill-compilation 的关系是：compile 只保留 `llm_role` 声明，不解析真实模型。这样 skill 在没有 provider key 的环境里也能编译；运行时再由 Studio resolver 绑定真实模型。把模型解析放到 compile，会让“静态审图”依赖“用户运行环境”，边界会变脏。

举一个完整场景：PM 上传产品手册，运行 `manual_summary` skill。`clean_manual` 是 LOGIC，不需要 LLM。`extract_features` 是 SKILL，声明 `llm_role: analyst`。`risk_review` 是 SKILL，声明 `llm_role: critic`。Studio resolver 查配置后，analyst 返回 Claude/GPT fallback 链，critic 返回 GPT/Claude fallback 链。runtime 执行到对应 phase 时各拿各的 ChatModel。Claude 超时时 analyst 自动 fallback 到 GPT；critic 一次成功。最终 trace 显示 analyst 有 fallback，critic 没 fallback，整张图成功。

最终心智模型：V0.3.0 skill 不“直接调用某个模型”，而是“声明需要某类模型能力”。Studio backend 或独立 resolver 把能力映射成模型候选链，engine 通过 Protocol 拿到 ChatModel，Gateway 在调用时处理 provider fallback。这样 skill 文件稳定，engine 边界干净，Studio 配置灵活，测试也能用 MockModelResolver 走同一套入口。

