# Predict V2 Research — 架构决策基石调研

> 本文档为 Predict V2 设计提供落地调研依据。
> 向上承接 `requirements.md`，向下指导 `design.md` 的技术选型。

## 1. LLM 拦截后填充机制 (Filling Strategy on Interception)

**现状调研**
根据 Round 8 新 framing，Predict 不再因遇到 LLM 节点而默认挂起。当在 `GatewayChatModel._generate` 等钩子处拦截外部 LLM 请求后，系统需要根据 Req 4.1 优先级（P0/P1/P2），直接构造并返回包含 Mock 数据的 `ChatResult` 对象，以实现控制流贯通，继续执行下游的所有 LogicPhase。

**候选对比**
*   **A. 返回构造好的 `ChatResult` 对象**：在 `_generate` 钩子内部，直接依据优先级注入对应数据，并将其包装为标准 `ChatResult(generations=[...])` 返回，完全绕过真实的远端 HTTP 请求。
*   **B. Monkey-patch 整个 `GatewayChatModel`**：动态替换模型的 `_generate` 乃至 `_agenerate` 方法。
*   **C. 在 ModelResolver 层注入 Fake Provider**：配置并实例化一个类似于 `FakeListChatModel` 的对象。

*注：在旧 framing 中推荐的抛出 `SuspensionException` / LangGraph `interrupt()` 机制因不符合“确保流程不中断”的原则，已被淘汰。*

**推荐 + 理由**
**推荐方案 A (直接返回构造好的 `ChatResult` 对象)。**
这种方式在当前执行栈最底层进行截断和伪造返回，实现最为直接、清晰，且完全不需要碰 13-export ABI，做到了最好的隔离。

**未知 + 风险**
在构造 `ChatResult` 时，如何合理填充相关的元字段（如 `id`, `created`, `usage` 等）以防止框架上层解析异常；此外，如果框架期待的是 Streaming 模式的 Chunk Iterator，直接返回整块数据是否需要额外适配。

---

## 2. LLM 拦截点对比

**现状调研**
在 `graph_agent` 的现有实现中，LangChain 模型构建经过 `ModelResolver` (解析角色与模型映射)，最终实例化为 `GatewayChatModel` (继承自 `BaseChatModel`)。实际的网络调用发生在 `GatewayChatModel._generate` 中。

**候选对比**
*   **A. `ModelResolver` 替换**：拦截在模型实例化阶段。实现容易，但拦截发生时还没有拿到具体的 Prompt 内容，无法做到基于请求上下文的精细挂起。
*   **B. `GatewayChatModel._generate` 钩子**：在实际调用 LLM API 的最后一刻拦截。此时可以拿到完全组装好的 Prompt 字符串和预期的 `io.outputs` schema。
*   **C. Phase 节点构造时注入**：在 `Harness` 层注入 Fake Provider。安全性高，但侵入性强，需要修改 Graph 节点的构建逻辑。
*   **D. LangGraph 增加 Interceptor Node**：在 LLMPhase 之前插入新节点。严重违背不改 Graph 拓扑的原则。
*   **E. Callback `on_llm_start` 拦截**：在回调中抛异常。反模式（Anti-pattern），Callback 应只做旁路观测，不应干涉主控制流。

**推荐 + 理由**
**推荐方案 B (`GatewayChatModel._generate` 钩子)。**
它在 LangChain 的最后一层，既不破坏 13-export ABI，又不修改图结构。在此处拦截，可以拿到最完整的 `LanguageModelInput`，直接返回构造好的启发式存根 `ChatResult` (按 Req 4.1 P0/P1/P2 优先级)，从而实现拦截后注入填充，确保流程不中断。

**未知 + 风险**
Streaming 模式下，注入 Mock 数据是否需要伪造一个完整的 AsyncIterator 来满足上层对于 Streaming chunk 的消费预期。

---

## 3. mock_llm 多态参数 dispatch 模式

**现状调研**
`run_skill` 将扩展接受多模态的 `mock_llm` 参数 `Union[None, dict, Path, List[GoldenCase]]`。在新 framing 下，`None` 默认值将触发 **P2 启发式存根**，而其他类型触发 P0 Golden Case 注入路径。Python 处理 `Union` 类型的常用模式包括 `functools.singledispatch`、Pattern Matching (Python 3.10+) 和 Pydantic 的 Discriminator。

**候选对比**
*   **A. `functools.singledispatch`**：标准库提供，基于类型分发。缺点是对于 `List[GoldenCase]` 这种带泛型的类型注解支持极弱。
*   **B. `match-case` (Python 3.10+)**：结构化模式匹配。语法清晰，但在运行时处理复杂嵌套 Pydantic Model 时，类型验证能力不如专用库。
*   **C. Pydantic `TypeAdapter` / Discriminator**：强大的运行时类型解析和验证。
*   **D. 自定义工厂类 (MockStrategy.from_param)**：手动 `isinstance` 检查并返回对应的 Strategy 实例。

**推荐 + 理由**
**推荐方案 C (Pydantic 验证) + 方案 D (工厂模式) 的结合。**
使用 Pydantic 的 `TypeAdapter(Union[None, dict, Path, List[GoldenCase]])` 进行严格的输入反序列化和校验，然后传入一个简单的工厂方法生成对应的 `MockProvider`。这样保证了类型安全和扩展性。

**未知 + 风险**
如果传入的 `Path` 是一个损坏的 JSON，Pydantic 解析时的错误堆栈可能对外部用户（如 CLI 用户）不够友好，需要做一层错误包装 (Error Wrapping)。

---

## 4. prompt + io.outputs schema hash 算法

**现状调研**
Golden Case 失效预警依赖于 Hash 对比。必须忽略无关紧要的空格、换行和 JSON Key 的顺序，否则会导致大量的 False Positive (假阳性) 失效。

**候选对比**
*   **A. SHA256 + 原始字符串**：极其脆弱，任何空格改变都会导致 Hash 变化。
*   **B. Python AST Hash**：极其严格，但实现复杂，且 Prompt Template 只是字符串，AST 无法应用。
*   **C. Canonical JSON + 字符串 Normalization + SHA256**：对 Schema 字典执行 `json.dumps(..., sort_keys=True)` 后哈希；对 Prompt 模板先执行正则表达式 `re.sub(r'\s+', ' ', text).strip()` 将多重空白规范化为单空格，再做哈希。

**推荐 + 理由**
**推荐方案 C (Normalization + Canonical JSON)。**
实现简单且完美契合业务需求。PM 在 IDE 里加个空行、调整一下 schema 字段顺序，不应导致黄金用例断裂，此方案能保证 Hash 稳定。

**未知 + 风险**
如果 Prompt 模板中依赖了特定的换行符作为业务语义（例如要求输出 markdown 列表），空白字符 Normalization 可能会掩盖这种结构性破坏。

---

## 5. Path Diff 数据结构 + 算法

**现状调研**
Req 3.2 要求验证 Graph 路由是否按预期访问了每一个节点。LangGraph 在 `GraphAgentHarness` 中的执行基本是状态机的串行跳跃，因此执行路径本质上是一个一维的节点序列 (List of phase names)。

**候选对比**
*   **A. Set Difference (集合差集)**：只比较访问了哪些节点，忽略顺序。无法捕获诸如 "A -> B -> C" 变成 "A -> C -> B" 的路由逻辑错误。
*   **B. DAG Diff**：图结构的 Diff，过于复杂，不适用于单次运行的线性轨迹。
*   **C. Longest Common Subsequence (LCS, 最长公共子序列)**：标准的字符串/列表差异比较算法，如 Python 内置的 `difflib.SequenceMatcher`。

**推荐 + 理由**
**推荐方案 C (LCS)。**
Expected Path 存储为一个 `List[str]` (Phase 名称序列)。运行时实际产生一个 Actual Path `List[str]`。运行结束后使用 `difflib` 计算差异，能直接生成类似 `+ Phase_New`, `- Phase_Old` 的直观差异报告，满足业务流转校验。

**未知 + 风险**
如果存在合法的循环路由（例如 `Phase_A -> Phase_B -> Phase_A`），列表会变长，Diff 报告可能不够直观。

---

## 6. Diagnostic Export JSON schema 借鉴

**现状调研**
Copilot 需要消费 Predict 产生的执行追踪。业界现有的 Schema 比如 LangSmith 的 Run Tree (包含 RunID, Name, RunType, Inputs, Outputs, Error) 非常成熟，但字段极其庞大。OpenTelemetry 则偏向于微服务的 Span。

**候选对比**
*   **A. LangSmith Run Schema**：字段详尽，但携带了太多关于 Token、Latency、Server IP 等在 Predict 模式下无用的信息。
*   **B. OpenTelemetry Trace**：过于底层，难以表达 `io.outputs` Schema 这种高阶业务概念。
*   **C. 极简业务扁平 Schema (类似 W3C Trace 变体)**：仅保留：`trace_id`, `phases: List[PhaseRecord]`。其中 `PhaseRecord` 包含 `phase_name`, `type` (logic/llm), `inputs`, `outputs`, `mocked_source: str | None` (取值 `golden_case` / `copilot` / `heuristic_stub` / `manual` / `null`)。

**推荐 + 理由**
**推荐方案 C (极简业务扁平 Schema)。**
因为下游消费者（内置 Copilot）只需要业务流的高保真切片来进行语义推断。参考 LangSmith 的结构，但进行深度的字段裁剪，去掉所有耗时/网络/资源统计，只留强业务字段，并与 Req 5.1 来源对齐。

**未知 + 风险**
大体积的 `inputs`/`outputs`（例如长文本、大数组）可能会导致序列化出的 JSON 突破 Copilot 的上下文窗口上限，需考虑是否引入截断机制 (Truncation)。

---

## 7. 副作用透明性 + 循环死锁

**现状调研**
在新的 P2 启发式存根框架下，因存根是确定性的结构化占位符（如固定返回值 `category="C"`），某些基于 LLM 输出路由判断的 Graph 可能会无限期走入同一分支。

**候选对比 (循环死锁)**
*   **A. 废除 `max_iterations=5` hack**：旧推荐。在 Backtest 模式下，因注入数据代表完整成功路径，此方案安全；但在 P2 存根模式下，存在高死循环风险。
*   **B. 引入专门的“启发式存根迭代上限”**：取代粗暴的图执行限制，监控针对同一路由的反复访问次数，超过阈值则退出并暴露问题。

**候选对比 (副作用透明性)**
*   `LogicPhase` 如果有写库、发邮件操作，它无法被自动拦截。需要通过约定的观测点暴露。

**推荐 + 理由**
**死锁推荐：废除原 `max_iterations=5` hack，并为 P2 存根模式引入专用的“启发式存根迭代/路由上限”。**
在注入 Golden Case (P0) 时因数据真实性有保证可以放心放开限制；而在 P2 模式下，确定性的假数据极易产生逻辑卡死，引入专门的路由循环检测可以作为安全网，既保证后续节点覆盖，又不陷入死循环。
**副作用透明性推荐：** 在 `TracingCallback` 中新增标准事件 `on_side_effect(action: str, payload: dict)`，建议 (但不强制) `LogicPhase` 的开发者在执行写库等危险操作前调用该回调，实现界面着色。

**未知 + 风险**
如果真实的图拓扑本身需要合法的高频循环，如何区分“正常的多次迭代”和“由于假数据引发的死锁”将是一个挑战。

---

## 总结

### 跨主题关键 Trade-off
*   **拦截点 (主题2) vs 注入填充机制 (主题1)**：选择在 `GatewayChatModel._generate` (主题2) 进行拦截，并直接返回构造的 ChatResult (主题1方案A)，从而确保流程贯通跑穿所有下游 Logic。这一调整消除了抛出异常导致的挂起现象，牺牲了部分动态状态捕获，但极大满足了“提前扫清 Logic 障碍”的业务目标。

### Research-driven Outline 修订建议 (针对 Round 1 Outline)
1.  **明确拦截点定义**：Outline 第二节需要明确拦截点具体为 `GatewayChatModel._generate`，以便获取动态 Runtime Prompt 并注入 `ChatResult`。
2.  **细化死循环防护机制**：Outline 必须补充一节说明，废除 V1.0 的强制 `max_iterations=5`，但在 P2 启发式存根模式下启用专门的“路由死循环上限防护”。
3.  **细化 Hash 算法边界**：Outline 第四节需补充：Hash 算法**必须且仅能**包含经过空白符规范化 (Normalization) 的字符串，绝不可对原始文本直哈希。
