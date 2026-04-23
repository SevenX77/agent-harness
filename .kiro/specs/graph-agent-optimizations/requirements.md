# Requirements Document

## Introduction

这份 spec 整合 Skill Studio 项目推进过程中识别出的、**graph_agent 核心引擎侧需要的所有优化需求**。这些改动由 Owner 自己负责实施（不是 Studio 开发团队的工作），但它们是 Studio 能按 `docs/studio/README.md` 的 MVP Roadmap 顺利落地的**前置条件**。

Scope：只覆盖 graph_agent 引擎层（`src/core/graph_agent/` 及嵌入的 `deerflow/`），**不包含 Studio UI 层实现**。

需求来源：
- `plan.md` 里 Owner 在原始对话中提过的优化项
- `docs/graph_agent_docs/FRAMEWORK_UNDERSTANDING.md` 里发现的 bug 和缺口
- `docs/studio/README.md` 第三部分引用的 graph_agent 能力（需要先落地才能让 Studio 消费）
- Gemini Round A/A+/B 分析中识别的架构优化点
- 本人对 DeerFlow 上游 (https://github.com/bytedance/deer-flow) 2026-03-28 至 2026-04-23 commits 的调研

需求组织按功能模块分类，每条需求给 EARS 格式的 Acceptance Criteria + 引用原始来源。

## Requirements

### Requirement 1: SKILL.md 中 Phase/Node 术语统一
**Objective:** As a skill author / PM / Copilot, I want consistent `<phase>` terminology across SKILL.md, code, directories, so that 不再混淆 SKILL.md 里的 `<node>` 标签和代码里的 `Phase` dataclass 两套词。

#### Acceptance Criteria
1. When parser 读取 SKILL.md，the system shall 同时接受 `<phase id="...">` 和 `<node id="...">`（向后兼容）的标签格式，并按同一路径处理
2. When compiler 运行，the system shall 对 `<node>` 标签发出 Warning（建议迁移到 `<phase>`），对 `<phase>` 标签无警告
3. The system shall 把现有 6 个业务 skill 目录下的 `nodes/` 重命名为 `phases/`，`<node id="...">` 标签统一改成 `<phase id="...">`
4. The system shall 保留代码层 `Phase` dataclass 名字不变（只改 SKILL.md 标签和目录约定，不改 Python 类名）

### Requirement 2: Compiler FATAL 规则补齐（Subgraph 互斥）
**Objective:** As a skill author / Copilot, I want compile-time errors when writing invalid phase config mixing subgraph with incompatible fields, so that 不会在运行时才发现配置被静默丢弃。

#### Acceptance Criteria
1. When `phase_config` 同时有 `subgraph:` 字段和非空 `tools:` 列表，the system shall 在 `skills/compiler/data/rules.yaml` 定义一条 FATAL 规则 `F-subgraph-exclusive-tools`，compiler 报错提示 "subgraph 模式下 tools 无效，请挪到独立的 code-only phase"
2. When `phase_config` 同时有 `subgraph:` 字段和 `<system_prompt>` 或 `<user_prompt>` 标签，the system shall 定义一条 FATAL 规则 `F-subgraph-exclusive-prompt`，compiler 报错提示 "subgraph 模式下 prompt 无效，请删除或改用 Agent-Loop 模式 phase"
3. When `phase_config` 同时有 `subgraph:` 字段和非空 `sub_skills:` 列表，the system shall 定义 FATAL 规则 `F-subgraph-exclusive-sub-skills`，compiler 报错
4. The system shall 在 `skills/examples/bad-samples/` 下提供触发这三条规则的反模式 skill 作为 compiler 测试素材

### Requirement 3: Step 规范化标签
**Objective:** As a skill author / Copilot, I want a structured `<step>` tag to break down agent loop instructions, so that SKILL.md 的 prompt 可以结构化地告诉 LLM "按以下 step 执行"，Copilot 生成和修改更稳定。

#### Acceptance Criteria
1. The system shall 支持在 `<system_prompt>` 或 `<user_prompt>` 里写嵌入的 `<step name="..." goal="...">` 标签
2. When parser 处理 `<step>` 标签，the system shall **不做表达式求值或条件判断**（`<step>` 只作为 prompt 结构化片段，framework 不解释它的语义，只保留原始文本交给 LLM）
3. The system shall 在 compiler 规则里对 `<step>` 做基础格式校验（name 字段必填、goal 字段必填），不校验 step 之间的逻辑
4. The system shall **不引入** `when` / `skip_if` / `if` / `else` 等表达式字段（违反 F006 规则：framework 不执行业务逻辑）

### Requirement 4: builtin `parallel_map` 内置并发工具
**Objective:** As a skill author, I want a framework-level parallel_map tool that lets an agent loop concurrently invoke the same child skill over a list of items, so that 不用每次都手写 Python dispatcher 胶水绕过框架。

#### Acceptance Criteria
1. The system shall 在 `src/core/graph_agent/tools/builtin/parallel_map.py` 提供 `parallel_map(skill_path, item_list, item_as, ...)` 工具
2. When agent loop 调用 `parallel_map(...)`，the system shall 用 ThreadPoolExecutor 并发执行子 skill，**默认 max_workers=3**（对齐 DeerFlow 内置 subagent 保守值）
3. The system shall 让每个子 skill 走完整的 `run_skill()` 路径（包含认知循环约束、callback 事件、validator），**不允许**绕过框架直接调 LLM
4. The system shall 支持通过参数覆盖 max_workers（允许 PM 在确认稳定后逐步放开）
5. The system shall 把每个子 skill 的 CallbackEvent 正确 propagate 到父 skill 的 callback 系统（保证可观察性不断）
6. When 多个子 skill 并发运行，the system shall 为每个子 skill 的 run 分配一个唯一的 `sub_run_id` 和共享的 `group_key`（标识同一次 parallel_map 调用）；所有子 skill 的 CallbackEvent 在 propagate 到父 callback 时**必须携带 `sub_run_id` + `group_key`** 字段。这样 Studio 前端可以把并发事件归入同一个折叠组展示，避免 Timeline 上 10 个子 skill 的 `phase_start` 挤在一起显示混乱

### Requirement 5: StorageManager 内置化（合并 DataManager + ArtifactManager）
**Objective:** As a PM using Studio / a host project integrator, I want a default artifact storage mechanism built into graph_agent, so that PM 不写 Python 就能让产出自动落盘；host project 仍可注入自定义 `artifact_saver` 覆盖默认行为。

#### Acceptance Criteria
1. The system shall 在 `src/core/graph_agent/io/storage.py` 新增 `StorageManager` 类，签名 `StorageManager(workspace_root: Path, skill_id: str, run_id: str, *, history_retention: int = 10)`，**不引入 user_id 概念**（user 是 Studio 的概念，不是 framework 的）
2. The system shall 提供方法 `get_output_dir(pipeline_prefix: str | None = None) -> Path`，默认路径模板 `{workspace_root}/{skill_id}/runs/{run_id}/`；有 `pipeline_prefix` 时在 `workspace_root` 和 `skill_id` 之间插入 prefix
3. The system shall 提供 `save_artifact(name, content, *, phase=None) -> Path`；传 `phase` 时文件名自动加 phase 前缀（如 `setup_output.json`），产出目录扁平化
4. The system shall 在 `IOManager` 里把 `StorageManager` 作为 default saver：当 SKILL.md 声明 `io.outputs: [{target: artifact_manager}]` 且 caller 没注入 `artifact_saver` 时，fallback 到 StorageManager
5. When caller 注入 `artifact_saver`，the system shall 优先使用 caller 的 saver，**不破坏 Kitchen-Pass 红线**（保留 host project 自定义自由度）
6. The system shall 从 SKILL.md 的 phases 顺序自动推导 pipeline 编号（不依赖任何外部 `pipeline.yaml` 文件）
7. The system shall 保留现有 `src/core/data_manager.py` 和 `src/core/artifact_manager.py` 作为 legacy（避免破坏 host project 现有代码），但加 deprecated 日志警告，引导迁移到 StorageManager

### Requirement 6: History 自动清理 + Golden 锁定
**Objective:** As a PM running many experiments in Studio, I want old runs auto-cleaned to prevent disk bloat, but with a way to preserve important baselines, so that 磁盘不会被 LLM 生成的图片音频撑爆，但重要的 golden baseline 不会被误删。

#### Acceptance Criteria
1. When `StorageManager.get_output_dir()` 创建新 `run_id` 目录，the system shall 同步触发 `.history/` 下非 `.golden` 后缀目录数量检查
2. If 检查发现超过 `history_retention` 个，the system shall **物理删除**最老的（按目录修改时间排序），**不做回收站**；删除时必须在日志中 INFO 级别输出被删除目录的完整 `run_id` 和本次清理腾出的磁盘空间（字节数或 MB），方便管理员事后排查
3. The system shall **永不删除** 任何后缀带 `.golden` 的目录
4. The system shall 支持通过 SKILL.md 的 `io.history_retention: N` 字段覆盖 StorageManager 的默认保留数
5. The system shall 默认保留数为 `10`（对 PM dogfood 阶段的试错 / 对比 prompt 场景足够）

### Requirement 7: TracingClientProxy（Prompt Capture 埋点）
**Objective:** As a PM debugging a skill, I want to see the exact prompt sent to LLM at every agent loop turn, so that 我能准确判断问题出在 prompt 写法、变量注入还是模型能力。

#### Acceptance Criteria
1. The system shall 实现一个 `TracingClientProxy` 外层包装 LLM client（不改 DeerFlow 源码）
2. When Harness 注入 LLM client 到 DeerFlow `create_agent()`，the system shall 自动把 client 包装成 Proxy
3. When Proxy 的 `chat(messages, **kwargs)` 被调用，the system shall 在真正调用 LLM 之前 emit `prompt_captured` 事件，payload 包含 `template_source`、`variables`、`final_prompt` 三元组，以及 `loop_index`、`llm_role`、`resolved_model`
4. The system shall 保证 Proxy 对 DeerFlow 透明（DeerFlow 内部逻辑完全感知不到 Proxy 存在，仍以为自己用的是普通 client）

### Requirement 8: CallbackEvent Pydantic 类型化
**Objective:** As a frontend / Studio consumer of runtime events, I want typed CallbackEvent schema with version, so that 前端可以稳定解析事件流，不用追 bug。

#### Acceptance Criteria
1. The system shall 在 `src/core/graph_agent/callbacks/events.py` 定义 Pydantic v2 discriminated union，覆盖现有 12 个事件类型：`phase_start`、`phase_end`、`llm_call`、`tool_call`、`validation_fail`、`retry`、`finish_task`、`nudge`、`working_memory_update`、`dead_end_pruned`、`compaction`、`ambiguity_report`
2. The system shall 新增 2 个事件类型：`prompt_captured`（由 R7 TracingClientProxy emit）+ `llm_fallback`（由 R9 ModelResolver fallback 触发）
3. Each event shall 含 `schema_version: Literal["1.0"]`、`event_type: Literal[具体名]`、`timestamp: datetime`、`phase_name: str | None`、`payload: 对应 payload 类`
4. The system shall 修改 callbacks/base.py 的 14 个钩子让它们 emit 对应的 Pydantic 事件（不是旧的 dict）
5. The system shall 提供 `TracingCallback` 落盘 `tracing.jsonl`，每行一个 `event.model_dump_json()`
6. The system shall **不发明**除 `prompt_captured` + `llm_fallback` 之外的新事件类型

### Requirement 9: ModelResolver 扩展 — 独立模型指定 + 同级 fallback
**Objective:** As a PM testing with a specific model, I want to pin a phase to one exact model (bypassing tier fallback) for A/B testing, so that 能确定性测试某个模型的表现；同时 tier 模式下主 provider 失败能无感切到同级备用 provider。

#### Acceptance Criteria
1. The system shall 给 `PhaseConfig` dataclass 加 `model_override: str | None = None` 字段（优先于 tier）
2. When phase 有 `model_override`，the system shall 跳过 `tier` 路由，直接用指定模型（仍经过 provider fallback）
3. The system shall 在 `config/llm_roles.yaml` 支持"单模型 role"配置格式 —— role 只绑定一个 model_code，没有 fallback 链（用于确定性测试）
4. The system shall 在 tier 路由失败时，基于 `peer_model_groups` 配置自动切到同级别代码模型（比如 Claude Sonnet ↔ GPT-4o），emit `llm_fallback` 事件（见 R8.2）
5. The system shall 把现在写死的熔断阈值（30min 窗口 + 30 次错误）从 `llm_roles.yaml` 读取，支持 per-provider 配置
6. The system shall 在 compiler 规则里新增 Warning 规则 `W-invalid-model-override`：校验 `phase_config.model_override` 填写的字符串是否在 `llm_roles.yaml` 的 `models` 段定义中；未定义则 Lint 给出警告（防止 PM 填错模型名导致运行时失败）

### Requirement 10: Nudge 默认值降权
**Objective:** As a skill author, I want Nudge to be less aggressive by default, so that agent loop 不会因为一个 text-only 输出就被疯狂打断。

#### Acceptance Criteria
1. The system shall 把 `max_nudges` 的 dataclass 默认值从 `3` 改为 `1`
2. The system shall 允许 skill 作者在 `<phase_config>` 里显式覆盖 `max_nudges`，例如高精度校验环节可以设为更高
3. The system shall 在 Nudge 预算耗尽时 emit `nudge` 事件（payload 带当前 count + 上限），便于 Studio 可视化

### Requirement 11: 仓库结构整理 — graph_agent 独立子包
**Objective:** As a developer, I want `graph_agent` physically organized as an independent Python sub-package, so that 生产端和 Studio 可以从清晰的 import path 消费同一份引擎代码。

#### Acceptance Criteria
1. The system shall 把 `src/core/graph_agent/` 目录整体移到 `packages/graph-agent/src/graph_agent/`
2. The system shall 为 `packages/graph-agent/` 添加独立的 `pyproject.toml`，定义 package 名 `graph-agent`、版本号、依赖
3. The system shall 更新所有 `from src.core.graph_agent` import 路径到 `from graph_agent`
4. The system shall **不引入 uv workspace**（留到 Studio 项目启动时再引入），本期只做物理整理 + 独立 pyproject.toml
5. The system shall 保证现有 host project（story_forge）代码不破（可能需要加一个兼容 shim）

### Requirement 12: Story-deconstruction 样板改造
**Objective:** As a PM / Copilot learning the framework, I want a correctly-organized reference skill demonstrating `subgraph:` composition, so that 有正确示范可以参考；同时保留错误样板作为 compiler 反模式测试。

#### Acceptance Criteria
1. The system shall 把当前 `skills/story-deconstruction/` 整体移到 `skills/examples/bad-samples/story-deconstruction-python-glue/`
2. The system shall 新建 `skills/story-deconstruction/`，用 `subgraph:` 嵌入 `text-segmentation`、`event-extraction`、`batch-analysis`、`global-synthesis` 四个子 skill
3. The system shall 为新版 story-deconstruction 提供 `context_bridge` 映射，确保父子 skill 的 context 字段正确对接
4. The system shall 把错误样板加入 compiler 测试套件，验证 compiler 能识别 Python 胶水反模式并给出重构建议（建议用 R2 的 F-* 规则之外的 W-* 规则）

### Requirement 13: DeerFlow 上游 bug fix 同步
**Objective:** As a framework maintainer, I want known bugs in the vendored DeerFlow (2026-03-28 snapshot) fixed, so that 框架稳定性和业务可靠性提升，特别是影响数据完整性的严重 bug。

#### Acceptance Criteria
1. The system shall 同步 DeerFlow PR **#2251** (2026-04-17) — Memory update system cache corruption + data loss + thread-safety bugs（位置：`deerflow/agents/memory/`）
2. The system shall 同步 DeerFlow PR **#2107** (2026-04-20) — tool duplication + skill parser YAML 不一致（自定义 parser 改用 `yaml.safe_load`）
3. The system shall 同步 DeerFlow PR **#2305** (2026-04-18) — subagent 继承父 agent 的 tool_groups（影响 R4 parallel_map 场景）
4. The system shall 同步 DeerFlow PR **#2350/#2351** (2026-04-19) — clarification messages 幂等（影响人工接入点可靠性）
5. The system shall 同步 DeerFlow PR **#2321** (2026-04-19) — 防止 LLM 幻觉 HTML tag 渲染成 DOM 元素
6. The system shall 同步 DeerFlow PR **#2332** (2026-04-18) — uploads 显式 opt-in（安全加固）
7. When 同步时遇到已修改的 DeerFlow 文件（`models/factory.py` / `agents/lead_agent/agent.py` / `agents/middlewares/tool_error_handling_middleware.py`，带 `# MODIFIED` 标记），the system shall 小心 merge 保留本地修改

### Requirement 14: Subagent 中间件继承
**Objective:** As a parent skill using subagent for concurrent sub-tasks, I want child subagents to inherit parent's middleware stack (WorkingMemory, DeadEndPruning), so that 子 agent 也有认知约束，不会行为失控。

#### Acceptance Criteria
1. When DeerFlow 的 SubagentExecutor 创建子 agent（内部调用 `make_lead_agent()`），the system shall 让子 agent 默认继承父 agent 的中间件配置栈（WorkingMemory + DeadEnd + Clarification + DanglingToolCall）
2. The system shall 通过修改 `make_lead_agent()` 签名支持 `inherit_middlewares: bool = True` 参数
3. The system shall 让 `INTEGRATION_GUIDE.md` 末尾关于 "Subagent Middleware 限制" 的说明失效（变成 obsolete），因为 subagent 现在天然带中间件

### Requirement 15: Checkpointer GC 策略（长任务优化）
**Objective:** As a skill author running long tasks (like 50-iteration batch_loop), I want checkpoint state not to bloat disk indefinitely, so that `.deer-flow/checkpoints.db` 不会变得超大导致读写变慢。

#### Acceptance Criteria
1. The system shall 在 `deerflow/agents/checkpointer/provider.py` 的 Checkpointer 封装层暴露 `max_checkpoints_per_thread` 参数（默认 100）
2. When checkpoint 数量超过上限，the system shall 自动删除最老的 checkpoint（保留最近 N 个）
3. The system shall 提供一个独立的 `ccb-compact-checkpoints` 或类似管理命令，允许 Owner 手动清理历史 checkpoint

### Requirement 16: Plan Mode (TodoList) 和 WorkingMemory 职责边界梳理
**Objective:** As an LLM running inside graph_agent, I want one clear "task tracking" mechanism, so that LLM 不会被 "TodoList middleware + WorkingMemory" 两套看起来重叠的机制搞糊涂。

#### Acceptance Criteria
1. The system shall 审计 DeerFlow 原生 `plan_mode`（启用 TodoList middleware）和外层 `WorkingMemory` 的语义
2. When `graph_agent` 被使用时，the system shall 默认**关闭** DeerFlow 的 `plan_mode`（因为外层已有 WorkingMemory），避免两套并存
3. The system shall 在文档里明确说明两个机制的关系 + 为什么选用 WorkingMemory
4. If 两个机制确有互补价值，the system shall 把它们融合成统一的 `TaskTrackerMiddleware`（此为可选高级优化，P2 再考虑）

### Requirement 17: Studio 场景默认 Checkpointer 配置
**Objective:** As a Studio user, I want checkpoint to persist across Studio restarts, so that 断点续跑能跨 Studio 重启工作（PM 关掉浏览器后再打开还能 Resume）。

#### Acceptance Criteria
1. The system shall 提供一个推荐的 Studio 启动配置（比如 `STUDIO_CHECKPOINTER=sqlite:.studio/checkpoints.db`），让 Studio server 启动时自动用 SQLite 持久化 checkpoint
2. The system shall 在 `harness.py` 的 checkpointer `auto` 解析逻辑里加对环境变量 `STUDIO_CHECKPOINTER` 的检测（优先级高于默认 `get_checkpointer()` 返回的 None）
3. If PM 显式要 in-memory 模式（开发时跑完就扔），the system shall 通过 `STUDIO_CHECKPOINTER=memory` 支持

### Requirement 18: 清理遗留文件（.gitignore + 副本）
**Objective:** As a maintainer, I want runtime files and duplicated patch_tools removed from source control, so that 仓库干净、PR diff 不被噪声污染。

#### Acceptance Criteria
1. The system shall 把 `.ccb/` 目录加入 `.gitignore`（runtime session 文件不应 commit）
2. The system shall 把 `*.pyc` 和 `__pycache__/` 加入 `.gitignore`
3. The system shall 把 `.studio_state/`、`.deer-flow/checkpoints.db`、`workspaces/` 加入 `.gitignore`
4. The system shall 删除 `skills/builtin/script/patch_tools.py`（与 `skills/builtin/md-patch/script/patch_tools.py` 重复）
5. The system shall 清理 `.pyc` 副本、`src/visual_learning/phase1_gt_extraction_v1.py.bak` 等 legacy 文件

### Requirement 19: 多模态工具单测补齐
**Objective:** As a maintainer, I want multimodal tools (generate_video, synthesize_speech, understand_video) to have unit tests, so that 这些长期没被测的工具在升级依赖时不会静默失效。

#### Acceptance Criteria
1. The system shall 为 `src/core/graph_agent/tools/generate_video.py` / `synthesize_speech.py` / `understand_video.py` 至少各加一个 happy-path 单测（可以 mock 外部 API）
2. The system shall 把这些单测加入 CI

### Requirement 20: Harness.py 拆分（技术债）
**Objective:** As a maintainer, I want the 952-line `core/harness.py` split into logical collaborators, so that 改任何一处不用通读全文。

#### Acceptance Criteria
1. The system shall 把 `core/harness.py` 拆成 `GraphBuilder`（`_build_graph` 相关）、`PhaseExecutor`（phase 执行节点）、`RetryRouter`（`_should_retry` 等）、`NudgeInjector`（planning/selfcheck nudge 逻辑）四个合作者
2. The system shall 保持 `GraphAgentHarness` 作为对外的 Facade，内部委派给上述合作者
3. The system shall 保证所有现有测试和业务 skill 在拆分后行为不变（回归测试）
4. The system shall 引入一个显式的 `RunContext` dataclass 在 4 个合作者之间传递共享状态（`thread_id` / `callbacks` / `run_options` / `runtime_inputs`），**不再依赖 `threading.local()` 作隐式传递**。目的：在 parallel_map 的线程池场景下（R4），每个子 skill 跑在独立线程里，显式 RunContext 能避免上下文丢失或跨线程污染

### Requirement 21: 文档合并和清理
**Objective:** As a reader, I want one authoritative set of graph_agent docs instead of two duplicate directories, so that 不用猜哪份是最新的。

#### Acceptance Criteria
1. The system shall 合并 `src/core/graph_agent/docs/` 和 `docs/graph_agent_docs/` 两个目录为一份权威文档
2. The system shall 把另一份目录改为 symlink 或构建时复制
3. The system shall 更新所有文档交叉引用到合并后的路径
