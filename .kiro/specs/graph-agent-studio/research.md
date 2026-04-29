# Research & Design Decisions

## Summary

- **Feature**: `graph-agent-studio`
- **Discovery Scope**: Complex Integration（涉及引擎层改造 + 新前后端 + 外部 CLI 桥接）
- **Key Findings**:
  - PM 不直接编辑 Markdown — SKILL.md 是 Copilot↔引擎的机器 DSL，不是阅读界面
  - 借用 Claude Code CLI 作为 P1 Copilot 远比自造 SDK 集成靠谱
  - 画布化是长期趋势但 graph_agent 是"胖节点"，不能照搬 Coze/ComfyUI

## Research Log

### Topic: SKILL.md 的定位纠正
- **Context**: 初版方案把 SKILL.md 当成"PM 可读配置"，设计各种表单/向导兜底；Owner 明确纠正该定位
- **Sources Consulted**: 与项目 owner 的多轮对话（2026-04-22），Gemini 的反复论证
- **Findings**:
  - SKILL.md 的真实定位是"Copilot↔引擎之间的严谨工程 DSL 接口"
  - PM 主路径是"对话 + 看结果"，不是"直接编辑 Markdown"
  - 写 Python 会带来各种工程问题，graph_agent 的目标是把工程问题**全部内聚到核心**
  - Copilot 作为 engineer assistant，把自然语言翻译成规范化工程语言
- **Implications**:
  - DSL 可严谨工程化（含 If/Else、when、并发块），不必为 PM 可读性让步
  - Studio UI 中心是"对话 + 看结果"，不是"直接编辑"
  - 所有"为 PM 可读性让步"的设计建议（表单、向导、避免嵌套）都被质疑
- **Memory record**: `/home/sevenx/.claude/projects/-home-sevenx-coding-agent-harness/memory/feedback_markdown_as_engineering_dsl.md`

### Topic: P1 应该走完整 Copilot 集成还是极简 dogfood
- **Context**: Gemini 上一轮主张 P0.5 Copilot Core 作为 P1 前置；Owner 纠正说这是"闭门造车"
- **Findings**:
  - 我们不知道 Copilot 会有哪些坑，应该先把 PM 跑通，再决定重做
  - "Open CLI" 按钮借用 Claude Code CLI 的成本是 1-3 天；自造 Copilot SDK 集成是多周
  - Claude Code CLI 已经是全世界最强的 markdown 编辑 Copilot，自造是造轮子
- **Implications**:
  - P1 档位 A = Lint + Run + Open CLI 三按钮，不做 Copilot 集成
  - 强制 P1.5 用户验证关卡，反馈决定 P2 方向
  - 原路线图的 P0.5 Copilot Core 合并到 "P2 候选项"

### Topic: 画布/节点式是 workflow 编排的终极形态吗
- **Context**: Owner 指出 Coze / ComfyUI / Langflow / Dify 都走画布路线
- **Sources Consulted**: 产品调研（Coze / ComfyUI / n8n / Langflow / Flowise / Dify）
- **Findings**:
  - 几乎所有面向非工程师的 workflow 产品最终形态都是画布
  - 但 graph_agent 是"胖节点"（内含完整 DeerFlow loop + prompt + schema + validator），Coze/ComfyUI 是"瘦节点"（原子组件）
  - 胖节点的 Content（prompt/schema/tools/when）无法用画布合理编辑
  - Topology（step 顺序 / retry 连线 / 并行分支）是画布的天然优势
- **Implications**:
  - P1 档位 A 画布只读（明确红线，R8.4）
  - P2+ 若走画布路线，采用 "Topology 归画布、Content 归 Copilot" 混合模式
  - 需补齐 "Pydantic AST → 格式化 SKILL.md 反向序列化"能力作为 AST 单一事实源（已列为 R2）

### Topic: Rust 重写是否对长远有好处
- **Context**: Owner 询问 Rust 整体重写的长期价值
- **Findings**:
  - Agent 编排 99% 耗时在 LLM API 等待（网络 I/O），1% 在 Python 开销
  - LangGraph / DeerFlow / Pydantic / anthropic SDK 主力在 Python，重写意味着放弃 11k 行 DeerFlow 和全部生态
  - Rust 的 LLM 生态（async-openai / rig）功能不全，社区小
  - 招聘成本和迭代效率会显著变差
- **Implications**:
  - 整体重写被明确否决（Out of Scope）
  - 未来如需性能优化，做局部 Rust 扩展（pyo3）而非整体重写
  - 这条决策在 design.md Non-Goals 明确列出

## Architecture Pattern Evaluation

| Option | Description | Strengths | Risks / Limitations | Notes |
|--------|-------------|-----------|---------------------|-------|
| A. 完整 Copilot SDK 集成（P1） | 用 claude-agent-sdk 包 agent loop，做 diff 预览/AST patch | 程序化控制强 | 工期多周，Copilot 坑未知 | 延后到 P2+ |
| **B. 借用 Claude Code CLI（P1 选中）** | **Open CLI 按钮 spawn pty + `claude` 命令** | **1-3 天工期，继承 CLI 全部生态（slash commands / MCP / hooks）** | **部署需要装 Claude Code CLI** | **本期选型** |
| C. 子进程 CLI + 文本流解析 | 解析 stdout JSON 拦截 tool_use | 简单 | 容易漂移，拦截难度大 | 不如直接 pty |
| D. 纯 LLM API 聊天框 | 前端直接喂 API 对话 | 无 CLI 依赖 | 没有工具、没有沙箱、没有 diff 预览 | 档位 B 后备 |

**选型理由**：B 是最短路径，且 Claude Code CLI 自身的 slash command、MCP、hooks、permission 生态不需要我们自造。只有在 P1.5 用户验证发现 "CLI 体验太开发者化 PM 无法上手"时才考虑 A。

## Design Decisions

### Decision: SKILL.md 契约统一到单一 Pydantic 模型（R1）
- **Context**: 当前 `core/parser.py` / `core/loader.py` / `core/compiler.py` / `deerflow/skills/parser.py` 各有校验逻辑，CHANGELOG 说"by design 分居"，实质是技术债
- **Alternatives Considered**:
  1. 保持现状 — 规则不同就是债
  2. 统一到 JSON Schema — 不适合 Python 层的 discriminated union
  3. **统一到 Pydantic v2 `SkillManifest`**
- **Selected Approach**: 统一到 Pydantic v2，带 `schema_version: Literal["1.0"]`，4 处解析器全改为引用
- **Rationale**: Studio 前端和未来 Copilot 都需要稳定契约；Pydantic v2 discriminated union 最适合 `type: graph|code` 这类分支
- **Trade-offs**: 短期工作量 + 现有 5 个 skill 要对齐 strict 校验；长期消除"to 追 bug"
- **Follow-up**: 参见 design.md Migration Strategy 的 5 步过渡

### Decision: AST 反向序列化（R2）引入 ruamel.yaml + 固定 body 格式化规则
- **Context**: 未来画布 Topology / Copilot diff 需要 "Pydantic → SKILL.md" 反向能力；format 不稳会污染 Git diff
- **Alternatives Considered**:
  1. PyYAML dump — 不保留 key 顺序、不保留注释
  2. 自写 YAML emitter — 维护成本大
  3. **ruamel.yaml round-trip 模式**
- **Selected Approach**: frontmatter 用 ruamel.yaml，body 的 `<node>`/`<phase_config>`/`<step>` 用自写固定格式化（缩进 2，属性顺序 alphabetical，EOF 换行）
- **Rationale**: 组合式 — 借用成熟库处理 YAML，body 自控保证字节级幂等
- **Trade-offs**: 需要写单测覆盖幂等；换行/空白策略要和 Claude Code CLI 手写风格对齐否则 diff 噪声
- **Follow-up**: 单测套件覆盖 round-trip 幂等 + 所有现有 5 个 skill

### Decision: Step.when 求值用 simpleeval（R10）
- **Context**: 扁平 step 需要条件跳过能力；不能用 Python eval
- **Alternatives Considered**:
  1. `simpleeval` 1.0 — 纯 AST 求值 + 白名单
  2. `asteval` — 更强但引入较多依赖
  3. 自写 mini 解析器 — 完全可控但维护成本大
  4. Jinja2 条件 — 字符串返回，需要转型
- **Selected Approach**: simpleeval
- **Rationale**:
  - 语法就是标准 Python 表达式，LLM 生成准确率高
  - 直接返回 bool，无需转型
  - 单文件库，轻量
  - 安全（禁用 `__import__` / `getattr` 等）
- **Trade-offs**: simpleeval 功能不如 asteval 丰富，但当前 when 条件场景够用
- **Follow-up**: 需定义 "context 变量类型 schema"，让 Copilot 生成 when 条件时有类型约束 — 列为 P2 待完善项

### Decision: 细粒度模型指定字段（R1 的 model_override）
- **Context**: Owner 指出不仅要 tier（premium/balanced/fast）三档，还要能**确定性指定某个具体模型**做测试
- **Alternatives Considered**:
  1. 只保留 tier — 无法确定性测试单模型
  2. **tier + model_override 双字段（model_override 优先）**
  3. 废掉 tier 全用 model_code — 失去 fallback 能力
- **Selected Approach**: PhaseConfig 同时保留 `tier` 和 `model_override`，`model_override` 非空时跳过 tier 路由，直接用指定模型（仍走 provider fallback）
- **Rationale**: tier 是生产路径，model_override 是 A/B 测试路径，两者正交
- **Trade-offs**: schema 多一个字段；Copilot 必须知道何时用哪个

### Decision: Copilot Fallback 策略（R11）— D + B 组合
- **Context**: 单点依赖 Claude SDK 风险大，需要 fallback
- **Alternatives Considered**:
  1. 方案 A: Gemini CLI 作 backup — 两套 agent loop 维护成本太高，能力不对齐
  2. 方案 B: 只读模式降级 — 最终兜底
  3. 方案 C: 本地队列重试 — 30s+ 等待体验差
  4. **方案 D: LiteLLM 风格多 provider 路由 — 首选**
  5. 方案 D + B 组合
- **Selected Approach**: 主路径 D（ModelResolver 扩展，同级代码模型自动切），兜底 B（全失败时读只读模式）
- **Rationale**: D 无感切换保生产，B 极端情况 degradation
- **Trade-offs**: D 要求 provider 之间有同级模型（Claude Sonnet ↔ GPT-4o），长期需维护映射表；B 需要前端做 degradation UI
- **Follow-up**: A 和 C 明确不做，写入 Non-Goals

### Decision: P1 档位 A — 明确不做 Monaco 内嵌编辑器
- **Context**: 原方案提议 Monaco 做 SKILL.md 编辑 + lint；Owner 纠正说借用 Claude Code CLI 就够了
- **Alternatives Considered**:
  1. Monaco 带 lint 的编辑器 — 工作量大且重复造轮子（Claude Code 已有编辑能力）
  2. **只读 Monaco 显示 + Open CLI 按钮** — 选中
  3. 完全不显示代码 — 过于黑盒
- **Selected Approach**: Studio 里 Monaco 只读显示 SKILL.md（用于 Lint 错误跳行），所有编辑强制走 Open CLI
- **Rationale**: 遵循 "借力 CLI" 原则，一条心路径，避免两套编辑入口冲突
- **Trade-offs**: PM 想快速改小段内容不如直接在浏览器点两下方便；但我们用 "Claude Code CLI 的 Edit 工具" 来补足，PM 对 Claude 说一句话就改完
- **Follow-up**: P1.5 看 PM 是否抱怨 CLI 太开发者化，决定 P2 是否加内嵌编辑

### Decision: 用户验证关卡（R9）必须是强制 gate
- **Context**: 之前路线图没有"用户验证"环节，直接一路冲到 P4，被 Owner 批评"闭门造车"
- **Alternatives Considered**:
  1. 软建议：设计里提一下，实际不执行
  2. **硬 gate：P1.5 未出结果不允许启动 P2 任何工作**
- **Selected Approach**: 硬 gate + 强制收集 3 类指标
- **Rationale**: 不经用户验证的后续功能很可能白做；现有设计的所有假设都需要 PM 真实使用验证
- **Trade-offs**: 会拉长项目周期 2 周；换来的是后续投入方向更准

## Risks & Mitigations

- **R1: SkillManifest 迁移 break 现有 skills** — 分 5 步过渡（design.md Migration），strict_mode 默认 False，逐步收紧
- **R2: serialize_skill 格式与 Claude Code CLI 手写风格不一致导致 diff 噪声** — 单测强制 round-trip，并对现有 5 个 skill 做 baseline 对比
- **R3: PTY 跨平台兼容问题（macOS/Linux/Windows）** — P1 只支持 macOS/Linux，Windows 推迟
- **R4: PM 验证关卡找不到真人 dogfood** — 提前协调至少 2 个 PM 同意；若找不到，用内部工程师模拟 PM 作用降级
- **R5: Claude Code CLI 突然变更命令接口** — Open CLI 的 `claude` 调用保持最朴素（不 pass 特殊 flag），减少耦合；gemini 作为备选显式配置
- **R6: simpleeval 的安全边界不够严** — 所有 when 表达式在 CI 增加模糊测试（尝试 `__import__` 等攻击），拒绝任何绕过白名单的 payload
- **R7: WebSocket 在 LLM 吐字快时丢序** — 使用 asyncio Queue + 单 consumer，严禁跨协程并发 send

## References

- 内部：`plan.md`（对话还原 + 第 1 版框架评估，已过时于 v2）
- 内部：`docs/superpowers/plans/2026-04-08-story-deconstruction.md`（Superpowers plan 样板）
- 内部：`/home/sevenx/.claude/rules/ccb-collaboration.md`（多 AI 协作规范）
- External: [simpleeval](https://github.com/danthedeckie/simpleeval) — 安全 AST 求值
- External: [ruamel.yaml](https://yaml.readthedocs.io/) — round-trip YAML
- External: [Claude Agent SDK](https://docs.claude.com/en/docs/claude-code/sdk.md) — 未来 P2 集成参考
- External: [React Flow](https://reactflow.dev/) — 画布库选型
