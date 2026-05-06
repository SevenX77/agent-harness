# PREDICT_SPEC (智能预测与模拟执行)

**版本**: 1.0
**日期**: 2026-05-06
**作者**: a2 Gemini (全局长远架构顾问)
**状态**: 设计草案 (V2 路线图储备)

---

## 1. Executive Summary (执行摘要)

在 Skill Studio 的标准 PM 工作流中，介于**静态编译 (Compile)**和**真实执行 (Run)**之间，存在一个巨大的反馈鸿沟。`compile_skill` 只能捕获语法、拼写和静态 Schema 错误，而 `run_skill` 则会产生真实的 Token 消耗和较长的等待时间（Latency）。对于拥有数十个节点的复杂 Agent Workflow，PM 往往需要经历多次昂贵的“试错运行”才能验证业务流转的正确性。

**Predict (预测/虚拟执行)** 功能旨在填补这一鸿沟。它通过**模拟 LLM 的响应而不产生实际的外部 API 调用**，在极短的时间内“沙盘推演”整个 Skill 的执行路径。Predict 的输出形态与真实的 Run 完全一致（生成完整的 Trace 和 WorkflowResult），从而让 PM 在不烧一分钱、不等待几十秒的前提下，直观地评估业务逻辑走向、上下文传递 (Context Mapping) 以及中间件的清洗能力。

Predict 功能将严格遵循现有的 SDK 13-export 契约，通过向 `run_skill` 注入 `mock` 参数的非破坏性方式实现，是 Agent Harness V2 迈向“所见即所得” IDE 体验的关键基石。

---

## 2. PM 用户故事 (User Stories)

Predict 功能致力于解决 PM 在日常 Prompt Engineering 和 Workflow 编排中的高频痛点：

*   **场景 1：零成本验证数据流向 (The Data Flow Check)**
    *   *“我在 Phase 1 定义了一个极其复杂的提取 Schema，并将其映射到 Phase 3 的输入中。我不确定中间的 Context Mapping 有没有写错。我不想烧 GPT-4 的 Token 来测试这个纯结构问题。我在 Studio 里点击 'Predict'，秒出 Trace 树，点开 Phase 3 的输入节点，发现参数确实传错了，立刻修改。”*
*   **场景 2：安全测试 Fallback 逻辑 (The Circuit Breaker Test)**
    *   *“我的 Agent 有一个重试和容错机制。我想测试当 LLM 彻底胡言乱语或者返回格式完全损坏时，系统的鲁棒性如何。我配置 Predict 模式注入预设的 '乱码输出'，运行推演，成功看到系统按预期触发了 MaxRetriesExceeded 的兜底降级处理。”*
*   **场景 3：快速预览 Prompt 结构 (The Prompt Inspection)**
    *   *“我刚在一个 Phase 里组合了 5 个不同的 Tools，并写了一大段 System Prompt。我想看看最终喂给 LLM 的 messages 数组到底拼成了什么样子（包括 Tool Definitions 的 JSON Schema）。我点 Predict，在虚拟 Trace 里清晰地看到了完整的 Request Payload，而不必真的发给 OpenAI。”*
*   **场景 4：回归测试沙盒 (The Sandbox CI)**
    *   *“我们的自动化 CI 每天要跑几百个 Skill 的回归测试。全用真模型太贵且极其容易因网络抖动而 Flaky。我们给绝大部分断言业务逻辑走向的测试用例启用了 `mock_llm=True`，让 CI 兼顾了速度、确定性和低成本。”*

---

## 3. 技术设计 (Technical Design)

为了在不打破现有 API 边界的情况下实现上述用户故事，Predict 必须作为 `run_skill` 的一种**特殊执行模式**存在。

### 3.1 Mock Provider 接入点

当前 `graph_agent` 的模型解析与调用由 `models/resolver.py` 和底层的 LangChain/GatewayChatModel 负责。

**架构决策**：拦截位置在 **Harness 初始化 StateGraph builder 时通过依赖注入替换 `ModelResolver` 的底层实例**——而不是魔改底层 Resolver 内部实现，也不在 runtime 中途切换。这样:
- StateGraph 编译期就锁定 mock 模式,Phase 节点构造时拿到的就是 `MockChatModel`
- 节点不感知自己跑的是真还是假 (interface 一致),不需要每个 phase 自己判断
- 不污染 Resolver 实现 (生产路径完全干净)

**设计方案**：
通过向 `run_skill` 暴露一个布尔开关 (或 dict 载荷), 在 Harness 构造 StateGraph 节点时,将真实的 `ChatModel` 替换为自定义的 `MockChatModel`（继承自 `BaseChatModel` 或实现相同鸭子类型）。

```python
# 理想的 Mock 接口
class MockChatModel(BaseChatModel):
    def _generate(self, messages: List[BaseMessage], stop: Optional[List[str]] = None, **kwargs) -> ChatResult:
        # 1. 记录被调用的 messages 和 kwargs (供 Trace 捕获)
        # 2. 根据规则、模板或预设生成假回复
        # 3. 返回构造好的 ChatResult
```

### 3.2 输出形态 (Mock Generation Strategy)

不真调 LLM 时，Mock 必须生成能让状态机继续运转的“合理占位符”。有三种选项：

*   **选项 A：廉价小模型跑单轮 (DeepSeek-R1 / GPT-4o-mini)**
    *   *机制*：真发网络请求，但使用极低成本模型，并强制限制 `max_tokens=50` 或关闭工具调用。
    *   *利弊*：真实度高；但依然有网络 Latency，且小模型经常不严格遵守强制的 JSON Schema 输出，容易导致 Workflow 意外崩溃（解析错误），偏离了“测逻辑流向”的初衷。
*   **选项 B：纯规则与启发式模板 (Rule-based Heuristics)**
    *   *机制*：不发任何网络请求。拦截器读取当前 Phase 的 `io.outputs` Schema，利用 `Faker` 或 Pydantic 的 `BaseModel.model_construct()` 自动生成符合 Schema 的默认 JSON 字符串返回。如果要求输出纯文本，则返回 `"Lorem ipsum simulated response..."`。
    *   *边界 case (Phase 没声明 `io.outputs` 时, 比如旧版未强制)*: Mock 降级为返回 `{"mock_response": "<phase_name> simulated output"}` 的 stub dict, 让流程能继续走。这种情况下 Predict 的"语义有效性"几乎为 0,但**至少能验证 phase 路由 + state transition 不崩**, 这就是核心价值。Studio 前端拿到这种 stub 应在 Trace 节点上额外标 "Schema 缺失, mock 极简" 警告。
    *   *利弊*：极速（毫秒级），绝对确定，Schema 绝对正确能保证流程跑通；但内容无语义价值。
*   **选项 C：用户预设/注入输出 (Deterministically Injected Output)**
    *   *机制*：PM 可以在 Studio 或请求参数中显式提供一个映射表：`{"phase_1": "{"extracted_name": "John"}", "phase_2": "Error!"}`。系统严格按预设返回。
    *   *利弊*：最适合做特定场景的断言测试和错误恢复压测；但配置成本高，不适合 PM 的一键“盲测”。

**最终推荐决策：B + C 混合策略**
默认使用 **选项 B（启发式模板）**。当 PM 只是想一键打通全链路看 Trace 时，SDK 自动根据 Schema 伪造合法载荷让流程走完。如果 PM 传入了特定的 Mock 配置，则降级为 **选项 C**。坚决摒弃选项 A（既不快也不绝对省钱，且不稳定）。

### 3.3 跟 SDK 13-Export 集成的兼容性

必须坚守“不增加新顶层 API”的契约。我们对现有的核心入口进行扩展：

```python
# 扩展 run_skill 的签名 (保持向下兼容)
def run_skill(
    skill_path: str | Path,
    *,
    trace_dir: str | Path | None = None,
    thread_id: str | None = None,
    unattended: bool = False,
    callbacks: list[Callback] | None = None,
    artifact_saver: ArtifactSaver | None = None,
    initial_context: dict[str, Any] | None = None,
    cleanup_checkpoints_on_finish: bool = True,
    # 新增 Predict 专用参数
    mock_llm: bool | dict[str, Any] = False, 
    **inputs: Any,
) -> WorkflowResult:
    ...
```

*   **为什么这么做最干净？**
    *   如果 `mock_llm=True`，启用选项 B（启发式生成）。
    *   如果 `mock_llm={"phase_1": "预设值"}`，启用选项 C（精确控制）。
    *   外部用户（如 Studio 后端）无需 import 任何新的类或函数，仅需改变布尔值即可完成 Predict 的闭环。
    *   返回的 `WorkflowResult` 依然是强类型的标准结果，不会破坏下游消费方（如 Studio 的结果展示）。

### 3.4 Trace 标记与前端区分

Predict 模式不能与真实的生产 Run 混淆。我们需要在数据的每一层打上烙印：

1.  **Metrics 层**：`WorkflowResult.metrics.input_tokens` 和 `output_tokens` 强制设为 `0`（或 `-1` 表示无计量），`total_cost` 设为 `0`。
2.  **Trace 文件层**：`TracingCallback` 在写入 `.trace.json` 时，在 Root 级别增加 `"is_mock": true` 的 metadata。在每一个被 Mock 的 LLM Call Span 中，添加 `"mocked_response": true` 标签。
3.  **Studio 前端视觉层**：
    *   当读取到 `is_mock` 属性时，Trace 时间轴的背景色使用不同的色系（如虚线边框或淡紫色背景）。
    *   顶部标题栏显示显著的 "PREDICTION MODE" Badge。
    *   耗时（Duration）显示为类似 `~2ms (Simulated)`，防止误导性能评估。

### 3.5 跟 Compile 的边界与协同

*   **分工明确**：`compile_skill` 是静态编译器（不感知输入数据，纯静态 lint）；`load_workflow_from_md` 是动态加载器（解析 + 构造 Harness 实例）；Predict 是动态推演器，需要 `inputs` 走完整 graph。三者职责不交叉。
*   **执行顺序**：`run_skill` 内部（无论是真实跑还是 Predict 跑）的首个步骤**必须**是 `compile_skill` 静态校验; **第二个步骤**才是 `load_workflow_from_md` 把 manifest 编译成可执行 Harness。这两步顺序固定,不能互换或省略。
*   Predict 额外能发现的动态错误：
    *   Jinja2 模板渲染错误（变量未定义等 `TemplateRenderError`）。
    *   `ContextBridge` (或同等机制) 在运行时传递类型不匹配。
    *   动态生成的 Tool 路径或环境依赖不可用。

---

## 4. 实施任务拆解 (Task Breakdown for a1 codex)

Predict 功能被设计为 V2 储备，当被激活执行时，推荐按以下 4 个解耦的 Task 进行：

### Task 1: 核心 Mock 引擎实现 (核心 SDK)
*   **目标**: 编写 `MockChatModel` 类，实现基于 Pydantic Schema 的自动 Dummy 数据生成。
*   **涉及文件**: 新增 `graph_agent/models/mock_provider.py`。
*   **估时**: 4h。
*   **验收标准**: 给定一个带有复杂 Schema 的 Prompt，MockModel 能够稳定返回符合结构、不引发 ValidationError 的 AIMessage。
*   **依赖**: 无。

### Task 2: `run_skill` 注入与 Trace 改造 (核心 SDK)
*   **目标**: 扩展 `run_skill` 参数，实现 Provider 路由；修改 `TracingCallback`。
*   **涉及文件**: `graph_agent/core/runner.py`, `graph_agent/callbacks/tracing.py`, `graph_agent/__init__.py`。
*   **估时**: 6h。
*   **验收标准**: 跑 `run_skill(..., mock_llm=True)` 能在一秒内结束，返回 Success 的 Result，且生成的 trace 文件包含 `is_mock` 标记。
*   **依赖**: Task 1。

### Task 3: Studio 后端接入 (应用层 Backend)
*   **目标**: 在 FastAPI 暴露给前端的 `/api/skills/{id}/runs` 接口中，支持接收 `is_predict=True` 标志，并透传给 `run_skill` (作为 `mock_llm=True`)。
*   **涉及文件**: `apps/studio/backend/app/routers/runs.py` (现有), `apps/studio/backend/app/models/runs.py` (现有 — 跟 SDK manifest 无关, 是 Studio 自己的 request/response schema)。
*   **估时**: 2h。
*   **验收标准**: 通过 Swagger UI 发送 Predict 请求能成功触发后端并返回 Mock Trace ID。
*   **依赖**: Task 2。

### Task 4: Studio 前端集成 (应用层 Frontend)
*   **目标**: 在 HeaderBar 增加醒目的 "Predict" 按钮；在 TracePanel 中适配 Mock 视觉样式。
*   **涉及文件**: `apps/studio/frontend/src/components/HeaderBar.tsx`, `apps/studio/frontend/src/components/trace/TracePanel.tsx`。
*   **估时**: 4h。
*   **验收标准**: PM 点击 Predict，几乎瞬间在右侧看到紫色的虚拟 Trace 树，并能展开查看生成的假负载。
*   **依赖**: Task 3。

---

## 5. 风险与未知 (Risks & Unknowns)

1.  **“看起来合理”的标准难以把握**：选项 B 的启发式生成可能会产生极度同质化或荒谬的文本（如把所有 String 字段都填上 `"mock_string"`）。这可能导致依赖正则表达式或高级 NLP 分析的后置 Phase 在 Predict 模式下抛出业务异常。
    *   *缓解策略*：初期接受这种降级，明确告知 PM Predict 的目的是“验证连通性”而非“语义正确性”。未来可引入更复杂的类型种子（如识别字段名为 `email` 时生成符合邮箱格式的假词）。
2.  **重试风暴与 Gateway 交互**：真实的 `GatewayChatModel` 会处理 Provider 回退。Mock 模式完全绕过了这层壳。如果 PM 想测试的是“当 OpenAI 挂了转 Anthropic”的路由逻辑，Predict 将无能为力。
    *   *权衡*：保持 Predict 作为逻辑连通性工具的定位，不承担底层网络/网关级的容灾测试职责。
3.  **循环结构死锁**：如果在 StateGraph 中配置了 `while len(items) > 0:` 的循环，且 Mock 生成的 Dummy 数据无法使条件收敛，Predict 会陷入无限死循环（直到触发 Max Iterations）。
    *   *缓解策略*：**只在 `mock_llm=True` 模式下生效** —— 底层 Harness 启动时检测 mock 模式,把 phase 配置里的 `max_iterations` 上限**强制夹紧到 5**(原配置 100+ 也只跑 5 轮)。生产 (mock_llm=False) 模式下原配置不变。这条限制写在 Harness 初始化的 mock-mode 钩子里, 不需要修改任何 phase 业务代码。

---

## 6. 跟 V2 路线对接与实施时点 (Roadmap Alignment)

根据 `v1-reset-direction.md` 的战略规划，Predict 明确属于 **V2 版本** 的核心 Feature。

*   **实施时机 (Activation Trigger)**：
    当前 (V1 阶段) 项目处于“物理拆分”与“Tauri 桌面端基建 (T1-T4)”的深水区。Predict 功能**不应在当前 Sprint 立刻启动**。
    只有当满足以下条件时，此 Spec 才转为开发就绪（Ready for Dev）状态：
    1. Tauri Python Sidecar (Phase T2) 集成稳定运行。
    2. Input Playground (文件输入验证) 重构完成。
    3. Monorepo 拆分彻底闭环，`video-analysis` 等下游应用成功迁移至新版本 13-export 契约。
*   **V2 节奏预判**：
    Predict 将作为 V2 的“杀手级体验”之一，与“复杂断点调试”和“Agent 模板市场”共同构成下一代 Skill Studio 的产品护城河。

*(End of Spec)*
