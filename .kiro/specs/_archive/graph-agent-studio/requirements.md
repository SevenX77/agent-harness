# Requirements Document

## Introduction

**Graph Agent Studio** 是 graph_agent 框架的配套 Web 工具，目标是把"给产品经理（PM）的 Agent 最后一公里"落地：让 PM 通过浏览器里的极简界面（而非 IDE 或命令行）完成 skill 的编辑、校验、运行、观察。

**设计哲学纠正（load-bearing）**：SKILL.md 是 Copilot ↔ graph_agent 引擎之间的**严谨工程 DSL 接口**，不是 PM 的阅读界面。PM 不直接编辑 Markdown，只通过对话（Copilot CLI 或未来的内嵌 Copilot）描述意图；DSL 可严谨工程化（含 If/Else、when 条件、并发块等），不必为"PM 可读性"让步。

**本期范围**：P0（契约地基）+ P1 档位 A（PM dogfood 三按钮：Lint / Run / Open CLI）。完整 Copilot 集成、画布 Topology 编辑等属于 Non-Goals，列在 design.md 的 Future Considerations。

**决策背景**：经过 2026-04-21 至 2026-04-22 与 Gemini 的多轮讨论，最终路线图为 P0 → **P1 档位 A** → P1.5 用户验证 → P2+ 按反馈分支（见 research.md）。本 spec 只覆盖已承诺实现的部分。

## Requirements

### Requirement 1: SKILL.md 契约单一事实源（P0）
**Objective:** As a framework maintainer, I want a single Pydantic v2 model that defines the SKILL.md schema, so that parser, loader, compiler, deerflow/skills/parser 共享同一套校验规则，消除"设计使然的双轨校验"技术债。

#### Acceptance Criteria
1. When 新建一个 Pydantic v2 模型 `SkillManifest`（含 frontmatter + body 标签结构），the system shall 把现有 `core/parser.py`、`core/loader.py`、`core/compiler.py`、`deerflow/skills/parser.py` 全部改造为引用同一个 `SkillManifest` 作为校验入口。
2. When 任何 SKILL.md 被加载，the system shall 先经过 `SkillManifest.model_validate()` 做结构校验，再进入业务层。
3. If `SkillManifest.model_validate()` 失败，then the system shall 返回结构化错误（错误 code、字段路径、行号、人类可读原因），不得抛出未包装的 Pydantic 异常。
4. The system shall 对 `SkillManifest` 添加 schema 版本字段 `schema_version: Literal["1.0"]`，未来演进通过版本号区分而非隐式 breaking change。

### Requirement 2: SKILL.md AST 反向序列化（P0）
**Objective:** As a Copilot / 画布编辑器 (future)，I want Pydantic AST → 格式化 SKILL.md 的反向序列化能力，so that 所有修改通道（Copilot diff、画布 Patch、手动编辑）都可以统一收口到 AST，再反向生成文件，消除双向同步地狱。

#### Acceptance Criteria
1. When 传入一个合法的 `SkillManifest` 实例，the system shall 生成格式确定、缩进稳定、属性顺序固定的 SKILL.md 文本。
2. When 同一个 `SkillManifest` 实例被反向序列化多次，the system shall 每次输出字节级一致的结果（幂等）。
3. When 一个人类手写的 SKILL.md 被 parse → serialize round-trip，the system shall 保证语义等价（新文件 parse 结果和原文件 parse 结果相等）；文本差异仅允许在空白/注释规范化范围内。
4. The system shall 提供 `serialize_skill(manifest: SkillManifest) -> str` 作为公开 API。

### Requirement 3: CallbackEvent 类型化（P0）
**Objective:** As a frontend consumer of runtime events, I want CallbackEvent 结构化为 Pydantic 模型并带 schema 版本号，so that 前端可以稳定解析事件流不用追 bug。

#### Acceptance Criteria
1. When 现有的 14 个 Callback 钩子触发，the system shall 发出符合 `CallbackEvent` Pydantic 模型的结构化事件（type 字段做 discriminated union）。
2. The system shall 在事件中包含 `schema_version`、`event_type`、`phase_name`、`timestamp`、`payload` 五个顶层必填字段。
3. When 新增一种事件类型，the system shall 强制在 `CallbackEvent` union 中注册；未注册的 `event_type` 必须被 Pydantic 拒绝。
4. The system shall 提供一个 `tracing.jsonl` 落盘格式，每行一个 `CallbackEvent.model_dump_json()`。

### Requirement 4: Prompt Capture 埋点（P0）
**Objective:** As a PM 调试 skill，I want to inspect the exact prompt sent to the LLM (template + variables + final text), so that 当 LLM 输出异常时能定位是 prompt 问题还是模型问题。

#### Acceptance Criteria
1. When DeerFlow 的 `create_agent()` 即将向 LLM 发出一次请求，the system shall 在发出前通过 Callback 发送一个 `PromptCapturedEvent`，包含：原始模板（`template_source`）、变量字典（`variables`）、注入后最终文本（`final_prompt`）三元组。
2. The system shall 在 trace.json 中保留全部 `PromptCapturedEvent`，PM 可按 phase/轮次定位。
3. When 一次 LLM 调用涉及多轮（agent loop），the system shall 对每一轮分别发出 `PromptCapturedEvent`，并携带 `loop_index` 字段。

### Requirement 5: Lint Button（P1 档位 A）
**Objective:** As a PM，I want a web button that runs compile_skill() on a chosen SKILL.md and shows errors inline, so that 我改完 skill 能立刻知道哪里语法/结构错了。

#### Acceptance Criteria
1. When PM 在 Studio Web 页面选中一个 skill 并点击 [Lint]，the system shall 在后端调用 `compile_skill()`，并把结果渲染为"通过 / 失败 + 错误列表"两态视图。
2. When 校验失败，the system shall 对每条错误显示：文件名、行号（如可得）、错误 code、人类可读原因；点击行号可在只读 Monaco 视图里跳转到该行。
3. When 校验成功，the system shall 显示绿色的 "Lint passed" 状态，并列出 skill 的 phases 简表（name / tier / tools / has_validator）作为确认。
4. The system shall 在 P1 档位 A 阶段**不允许**在 Studio 里直接修改 SKILL.md（不做 inline edit），PM 需通过 Open CLI 按钮在终端里改。

### Requirement 6: Run Button（P1 档位 A）
**Objective:** As a PM，I want a web button that runs the skill with a chosen input and shows a streaming trace, so that 我能直接在浏览器里 dogfood 当前 skill 而不用去命令行。

#### Acceptance Criteria
1. When PM 点击 [Run]，the system shall 弹出输入面板：支持选择预存的 golden input（若存在）或粘贴一段 JSON。
2. When 运行开始，the system shall 通过 WebSocket 把 `CallbackEvent` 流实时推送到前端，按时间顺序渲染为 Trace Timeline。
3. When 运行结束，the system shall 展示最终 `WorkflowState.context`、累计 metrics（tokens / elapsed / fallback 次数）、validator 通过率。
4. When 运行失败（validator fail 或异常），the system shall 把失败节点高亮，点击可展开该节点的 full system prompt + LLM raw output + validation error。
5. The system shall 在 output_dir 下落盘 trace.json 和 metrics.json（见 R3）。

### Requirement 7: Open CLI Button（P1 档位 A）
**Objective:** As a PM，I want a web button that opens a terminal session rooted at the current skill directory with Claude Code CLI ready, so that 我可以直接在熟悉的 Claude Code 里描述意图并让它改 SKILL.md，不需要我们自己造 Copilot。

#### Acceptance Criteria
1. When PM 点击 [Open CLI]，the system shall 在服务器端 spawn 一个终端会话（tmux pane 或 pty）cd 到该 skill 的目录，并预先启动 `claude` 命令。
2. The system shall 通过浏览器里的 xterm.js 把该终端流式展示，支持双向输入输出。
3. The system shall 为每个 PM session 独立分配终端实例，session 结束后自动清理。
4. When PM 在终端里修改了 SKILL.md 并保存，the system shall 通过 filewatcher 检测变更，并自动触发一次 Lint 提示（非阻塞 toast）。
5. The system shall 同时支持 `gemini` CLI 作为备选（配置切换），以应对 Claude 不可用场景。

### Requirement 8: 只读可视化底座（P1 档位 A）
**Objective:** As a PM，I want a read-only visualization of the skill's phase graph and runtime state, so that 我能一眼看清 skill 的结构以及上次 Run 在哪里。

#### Acceptance Criteria
1. When PM 打开一个 skill，the system shall 用 React Flow 渲染该 skill 的 phase 图（仅只读，不支持拖拽连线修改 DSL）。
2. The system shall 在图上标注每个 phase 的 tier / tools / validator 存在性，点击节点展开右侧 detail 面板显示 system_prompt / user_prompt / output_schema / sub_skills。
3. When 有一次 Run 的 trace 可用，the system shall 在图上叠加着色（已完成/进行中/失败/未进入），并在 detail 面板里展示该 phase 的 Prompt Capture 三元组（模板 / 变量 / 最终）。
4. The system shall **明确禁止**在画布上编辑任何 DSL 内容（所有修改走 Open CLI）。这是 P1 的红线，保护 Copilot 单一事实源契约。

### Requirement 9: 用户验证关卡（P1.5）
**Objective:** As the project owner，I want an explicit 2-week dogfood checkpoint after P1 ships, so that 在投入 P2+ 之前验证 PM 的真实工作流是否被满足，避免继续闭门造车。

#### Acceptance Criteria
1. When P1 档位 A 交付后，the system shall 找到 2-3 个真实 PM 做 2 周 dogfood。
2. The system shall 在 dogfood 期间强制收集至少 3 类指标：① PM 自主完成一次 skill 改动的成功率 ② Claude Code CLI 生成的 SKILL.md 首次过 Lint 率 ③ PM 报告的 UX 摩擦点 top 3。
3. When dogfood 结束，the system shall 基于指标决定 P2 方向：(a) 补强 Trace 可视化 (b) 启动内嵌 Copilot 集成 (c) 启动画布 Topology 编辑 — 三选一，不并行。
4. The system shall **禁止**在 P1.5 结果出来前启动 P2 任何工作，这是一条强制 gate。

### Requirement 10: when 条件字段（P0 引擎扩展）
**Objective:** As a Copilot / 引擎，I want a safe expression evaluator for step-level when/skip_if conditions, so that 扁平 step 列表能表达条件分支而不需要引入嵌套 if/else 标签。

#### Acceptance Criteria
1. When a `Step` 定义了 `when: "<expression>"`，the system shall 在进入该 step 前对表达式求值，false 则跳过。
2. The system shall 使用 `simpleeval`（不是 Python eval）作为求值引擎，禁用所有内置函数除 `len`、`str`、`int`、`bool`、`in`、`and`、`or`、`not`。
3. The system shall 向求值上下文注入白名单变量：`context`、`working_memory`、`current_phase_metrics`，其他变量访问必须报错。
4. When 表达式求值抛出异常，the system shall 以 `WhenExpressionError` 包装并作为 validator-level error 上报，不得静默跳过 step。

### Requirement 11: Copilot Fallback 策略（P0 模型层）
**Objective:** As the Studio runtime，I want a layered defense when the primary LLM provider fails, so that PM 不会因上游 API outage 完全无法使用。

#### Acceptance Criteria
1. When 主 provider（Claude 系）失败（rate limit / timeout / API error），the system shall 通过 `ModelResolver` 自动切换到同级别的备用 provider（OpenAI GPT-4o 等），失败事件以 `LLMFallbackEvent` 上报。
2. When 所有配置的代码级别 provider 都不可用，the system shall 降级到"只读模式"：PM 可看 trace、可运行已有 skill，但 Open CLI 在启动后提示 "Copilot 不可用"。
3. The system shall **不** 引入 Gemini CLI 子进程作为 Copilot backup（两套 agent loop 维护成本被判定不值）。
4. The system shall **不** 实现本地队列+重试（超出 30 秒的等待在 PM 对话场景下体验不可接受）。
