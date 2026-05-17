# Graph Agent 模块运行执行流程 (Execution Flow) 综合报告

日期: 2026-04-30
分析目标: 本文档旨在针对 `graph_agent` 框架的核心组件，详细描述其在运行时的真实执行流程（Control Flow / Sequence），侧重于模块间的协同方式。

---

## 1. md2json 格式解析与纠错流程
**核心文件**: `src/core/graph_agent/tools/md_to_json.py` 和内置技能 `src/core/graph_agent/skills/builtin/md-patch/SKILL.md`。

**执行流程**:
1. **文本摄入**: 当 LLM 输出包含数据的 Markdown 文本后，进入 `md_to_json(md_text, schema)` 统一执行流。
2. **结构化切分**: 调用 `parse_md()`，利用正则表达式将长段的 Markdown 依据 `##` (Item 边界) 和 `-` (Bullet list 字段) 结构硬切分为一组原始字典组成的 `ParsedBlock` 列表。
3. **精准诊断**: 调用 `diagnose(blocks, schema)`，对每个 block 进行 Pydantic `model_validate` 测试。该步骤分离出【校验成功项】与【校验失败项】（如缺括号、编码转义错误、字段类型不匹配等），并生成 `DiagnosticReport`。
4. **LLM 手术级修复 (Surgical Patch)**: 
   - 对于校验成功的数据，直接入库保存。
   - 针对校验失败的这 ~5-10% 项，系统主动唤起内部路由：执行 `run_skill("md-patch", inputs=...)`，即挂载一个隐式的 Builtin Agent。将原版出问题的残缺 Markdown 片段和报错栈（Traceback）交给专门负责纠错的修复型大模型。
5. **重组与失败控制**: 纠错完成后，再次尝试合并解析。如果仍然失败，根据上层规则抛出异常（Raise Error），在 LangGraph 的 Agent Loop 中由中间件转换回 Retry Feedback 扔给业务 LLM 再次尝试。

---

## 2. LLM 角色决议流 (Role Resolution Flow)
**核心文件**: `src/core/graph_agent/config/llm_config.py`, `src/core/graph_agent/models/resolver.py`。

**执行流程**:
1. **热加载配置**: 运行时触发 `get_role_config()`，`_RoleConfigHolder` 检查 `mtime`，如更新则重新加载 `llm_roles.yaml`（分为 `models`, `providers`, `roles` 三段式）。
2. **角色定位**: 引擎传递请求参数（如 `role="premium"`），调用 `resolve_role(role_name)`。
3. **调用链 (Call Chain) 组装**: 
   - 首选激活 `active_model`。
   - 去 `models` 中获取对应大模型支持的所有 `providers`（例如 `OC_CL_ANT, WS_LLM` 等），按配置文件列表顺序构建当前模型的 Provider 优先级链。
   - 如果开启了 `model_fallback=True`，继续把当前 Role 中除 active 之外的其他模型及其下属的 Providers 全部追挂到 Fallback 长链的尾部。
   - 跨级平级替换：如果在上述步骤耗尽仍失败，系统查找 `peer_model_groups` 组装同级别的替代模型继续兜底。
4. **属性透传**: 组装好的对象向下携带从 Role 和 Provider 继承而来的 `temperature`、`timeout` 参数，并在模型工厂（Factory）实例化时精确注入 `system_prompt_prefix` 与推理标识 `thinking_enabled`。

---

## 3. 全局熔断系统流程 (Circuit Breaker & Gateway)
**核心文件**: `src/core/graph_agent/models/llm_client_manager.py` 和 `gateway_chat_model.py`。

**执行流程**:
1. **连接池就绪**: `LLMClientManager` 作为进程全局单例懒加载初始化。其内部持有针对各个厂商（OpenAI/Anthropic/Gemini）的 HTTPX 原生复用 Client 对象，以防因为 Graph 状态机频繁销毁导致 TCP 时间积压（TIME_WAIT）。
2. **请求分发与事前检查**: 当 `GatewayChatModel._generate` 尝试轮询 Provider 时，首查本地内存字典 `_is_provider_marked_down()`，若处在冷却期直接跳过该节点。
3. **微型探测 (Active Probing)**: 针对未知的网络提供商发起调用时，`_probe_provider()` 会以 `max_tokens=1` 发送一条空请求进行探路。探针能以不到 1s 的延迟感知节点是否瘫痪，一旦抛出 HTTP 超时或网络层拒绝，直接调用 `_mark_provider_down()`。
4. **退避轮询与 5xx 拦截**: `_dispatch_provider_call()` 向目标发送请求。若遇到 WaveSpeed 这类网关的高频 502/503/504 错误，系统将在底层网络库中自动按照 `10 * 2**attempt` 秒进行指数退避原地重试，而不会将偶发错误抛上业务层。
5. **事件打点与 Fallback**: 只有在确凿捕获到了探测失败、或是多次 Retry 后仍然崩溃的情况下，系统才会真实对外发送 `LLMFallbackEvent` 事件，从而保证可观测看板（Studio Trace）对网络问题的精准性，彻底杜绝预测式无用打点。

---

## 4. PhaseNode 多态执行与分发 (Polymorphic Phase Executor)
**核心文件**: `src/core/graph_agent/core/phase_executor.py`, `phase_nodes/factory.py`, `llm_phase_node.py`。

**执行流程**:
1. **编译期节点化**: 旧有的 1130 行 God Class 被抹除。在图编译阶段，`Factory` 分析 `Phase` 对象的特征（例如 `is_validation` 标识、`requires_llm` 动作）。
2. **动态构造**: 依照分析派生 `LLMPhaseNode`、`CodePhaseNode` 等子类实例。
3. **容器生命周期注入**: `DependencyContainer` (存放了 callbacks、io_manager、resolver 等系统级横跨图声明周期的基础设施对象) 被精准一次性注入给所有 PhaseNode 子类的基类属性 `self.container`。
4. **主循环运转 (invoke)**:
   - 子类的 `execute(phase, state)` 进入流转。
   - LLMPhaseNode 会触发回调（`on_phase_start`），将 Tool Wrapper 挂载入 LangChain。
   - `create_agent` 创建内部 Agent 后调用 `.invoke()` 进入基于 Tool-calling 的推理交互。
   - 交互完毕通过 `_apply_io_hoist()` 利用 IOManager 把结构化数据提升 (Hoist) 进入 `BusinessData`，并触发 `on_phase_end` 返回更新后的 WorkflowState。

---

## 5. 编译期验证防线 (Compile-Time Validation)
**核心文件**: `src/core/graph_agent/core/skill_validator.py`, `compiler.py`。

**执行流程**:
1. **静态摄取**: `SkillLoader` 载入 `SKILL.md` 中的 YAML Frontmatter 后并解析成原生的 Schema。
2. **严格审查栈**: 流经 Validator 的拦截链条。
   - **Schema 2.0 Strict Gate**: 核心路径。只要当前 SKILL 的节点调用涉及大模型的结构化输出或自带 Runtime Validator 属性，引擎强制检查是否挂载了明确定义的 `output_schema`（不允许回退到模糊的 Schema is None）。
   - **Tool Path 解析**: 防止沙箱越权与非法加载。
   - **Persona 验证**: 识别其是否仅为注入 Prompt 的无运行图结构角色类型。
3. **聚合阻塞**: 如果任何检查抛出异常，所有结构化且含有具体代码行号（Line Location）的 `CompileIssue` 将被整合，并最终引发 `SkillCompileError` 在程序真正运转前实现 "Fail Fast" 阻断。

---

## 6. finish_task 核心契约与认知管道
**核心文件**: `src/core/graph_agent/middleware/cognitive_flow.py`, `cognitive/finish.py`。

**执行流程**:
1. **隐式挂载**: 在 `LLMPhaseNode` 中，将封装有退出动作的 `finish_task` 作为 LangChain 的一员通过 `bind_tools(tools)` 抛给模型。
2. **中间件拦截**: 模型决定完成任务发送 `finish_task`。由于工具行为涉及业务校验，指令不会立即生效，而是在 `CognitiveFlowMiddleware.intercept_tool_call` 层被拦截劫持。
3. **Pydantic 硬校验**: 中间件取出大模型传输的 `business_data_md` 参数。借助 `SchemaEngine`，对照该 Phase 的 `output_schema` 进行强制 Pydantic 反射加载与规则比对验证。
4. **业务软拦截**: 若 Pydantic 硬性约束通过，引擎紧接着分发给 `SKILL.md` 中指派的 `business_validator` 代码块，并传递已解析好的 `list[dict[str, Any]]` 参数去校验纯业务规则。
5. **重定向路由**: 
   - 任意一项验证失败，中间件会构建明确带有报错栈的 Retry Feedback 作为 System 响应欺骗大模型工具调用失败，要求大模型在同一个 Phase 中就地进行复核与重建，直至修复通过。
   - 校验成功，则放行写入并退出当前 Phase，控制权交还 LangGraph State Manager。