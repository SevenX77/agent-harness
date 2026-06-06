---
module: 02_capabilities/copilot-assist
doc: mvp1-alignment
status: FROZEN（SDK 对话 live，但仍直写、session 内存态、ThinkingBlock 未翻译，Settings 里的 SDK 测试路径与真实 chat 不等价 ⚠️。；目标结构已按 R4-R8 retrofit）
binds_baseline: ./baseline.md
units: [copilot-sdk-test-parity, copilot-session-persistence]
aligns_with: 01_workflows/00_settings-ux-spec.md（Copilot SDK test）· 01_workflows/04_run-and-verify.md（analysis bar）
---

# copilot-assist — MVP1 Alignment

> **Tier**: capability | **Owns**: `copilot-sdk-test-parity`（真实 SDK smoke 路径）+ `copilot-session-persistence`（多 session / 消息渲染） | **现状**: SDK 对话 live，但仍直写、session 内存态、ThinkingBlock 未翻译，Settings 里的 SDK 测试路径与真实 chat 不等价 ⚠️。 | **Related**: [baseline](./baseline.md)（双向）· `copilot` region · `studio-settings` · `golden-eval` · `publish` · `native-fs` · `llm-copilot-http-api`

## 1. 定义
copilot-assist = skill 工作台右侧 copilot 助手的端到端行为：一个**懂搭 skill + 懂业务领域**的对话助手，能精确取上下文（@mention）、安全改文件（diff 提案）、对话式建技能、承载 judge/打磨、跑完主动提分析。

## 2. 数据流 / 机制（设计细节）
### 功能逐项（原 F 段迁移）

### F1 对话 + 流式输出（折叠不省略）
- **机制**：用户发消息 → 后端 SDK → 全部 block 流式回 → 前端按 block 类型折叠渲染(ThinkingBlock→Thought ▾ / 读类工具→Explored ▾ / 写类→Worked ▾ / Bash→Ran ▾ / TextBlock=答复正文)。
- **决策+动机**：**全部思考 + 全部 tool call 全程流式、折叠仅视觉(默认折起点开看全部)、绝不摘要替代/不丢步**。渲染随 SDK 输出结构定(非 PM 设计)。现码 `copilot.py:382-400` 丢 `ThinkingBlock` → 必修。砍"可操作错误卡"(过度设计)。
- **原话**：「整个思考过程 tool call过程都要全部流式输出出来呀, 可以折叠但是不要省略」/「这需要我设计吗?? Claude sdk怎么输出的?」
- **status**：流式 live(75ms 批)；ThinkingBlock 补翻 + 折叠 = target。
- **测试点**：全部 thinking+tool call 流式、折叠可展开看全部、不丢(回归现码丢 thinking)。
- **归属**：region [[copilot]]。

### F2 多 session（顶部 tab + new chat）
- **机制**：copilot 面板顶部一条 tab 栏 = 并列多个 session tab + 一个 `+`(new chat)；切 tab=切 session；一 skill 多条 session 全持久化、退出恢复全部 + 上次活跃 tab。
- **决策+动机**：一 skill **多条** session(抄 Cursor chat 历史)；session 必持久化(D8 MUST)，落盘归 [[native-fs]](Rust 按 skill 存多 session 文件，跨窗口)；写盘/读回失败→显式告警不静默。
- **原话**：「要,顶部tab多个session和一个+(new chat),抄cursor」/「后者多条session」/(D8)「copilot对话不能丢, 退出再进去要打开一摸一样的对话, session记录都要在, 和cursor一样, 这点必须要做到」
- **status**：现纯内存(丢)= target。
- **测试点**：开 N 条/切 tab/退出恢复全部 session + 活跃 tab(不串/不丢)；写盘失败显式告警。
- **归属**：region [[copilot]] · platform [[native-fs]]。

### F3 领域脑子（搭 skill + 业务领域 + 主动诊断）
- **机制**：`system_prompt` 薄层(skill-authoring 浓缩) + `engine-authoring` plugin + `add_dirs`(skill-spec)渐进暴露；compile/lint 诊断经 context resolver 注入。
- **决策+动机**：**范围 = 搭 skill + 业务领域**(搭 skill 靠 skill-spec 注入；业务领域**靠模型自带 + 用户喂文档**@file/拖，**不做专门 KB**，真不够再加)。**主动性 = 主动诊断+给修法**(编译错/数据断层/违 FROZEN → 主动诊断，含 F7 分析 bar)。**架构 = SDK + 知识插件**(覆盖 D5「copilot 自身=graph skill」；现码 SDK 路线对，补知识注入)。
- **原话**：「1.现在是mvp1. 2.做全」/「领域知识先不做具体设计, 靠模型自带领域知识或用户直接喂文档」
- **status**：现 3 行通用 prompt(`copilot.py:70`)= target。
- **测试点**：问"为啥编译失败"→读 skill-spec 给 ground-truth；帮写领域 prompt→读 skill 文件不空谈；违 FROZEN→compile 报 `F-v3`→主动给修法。
- **归属**：platform engine(skill-spec 知识源)；触发粒度待细化(见 gaps)。

### F4 @mention + 隐式上下文 + 上下文回显
- **机制**：① 显式 @ → 输入框弹 MentionMenu(files/phases/dots/errors/trace，键盘导航，模糊过滤 <50ms)；② 自动 mention(点画布节点→@phase / 点 dot→@黑板 / 点文件→@file)；③ 隐式上下文(view/选中/活跃文件/dirty buffer)随消息发；④ 后端 4 层 resolver(skill 基本/选中节点/@内容/lint错误)→XML 喂 prompt；⑤ 发送后**第一条**回显本轮注入清单。
- **决策+动机**：**composer = 输入框内联彩色 pill**(需 tiptap 类富文本，react-mentions overlay 渲染不了真 DOM pill)；**dot=黑板**(对齐 trace 走查，取代旧 @edge_context 边语义)；**上下文回显插在 agent 开跑前、第一条**(可折叠、点开看实际内容/文档，反 hidden prompt magic，与 F1"不省略"一套)。
- **原话**：「输入框内联彩色 pill」/「能否插入在 agent 开始任务的前面... user输入完按发送后, 第一条弹出的就是这个信息, 可折叠, 可查看具体内容或文档」
- **status**：现纯空壳(占位符 + disabled "Add context")= target。
- **测试点**：输入 `@plan`→菜单过滤高亮、选中成内联 pill 可删；点节点/dot/文件自动 @；dirty 文件 @ 拿草稿；发送后第一条=注入清单点开看内容；大工程菜单 <50ms / 超 150K 截断告警。
- **归属**：region [[copilot]](菜单/pill/回显)；自动触发跨 [[canvas]]/[[editor]]/[[timeline]]。

### F5 安全写 + diff 气泡 + Bash 审批
- **机制**：Write/Edit 经 SDK 回调拦成 `patch_proposed` → diff 气泡(Apply/Reject/Open Compare 并排 Monaco) → Apply 写编辑器 buffer(开着)或 Rust 落盘(没开) → 冲突复用 `SaveConflict` → 自动 compile 回灌气泡。Bash 命令逐条审批卡。
- **决策+动机**：**P0-A + D12**(写入唯一权威=编辑器 save 契约，落盘走 Rust；copilot 只产提案+UI，写/冲突/编译委托编辑器已有能力)。**Bash 抄 Cursor**(保留 Bash 但 human-in-the-loop：文件写走 Edit/Write→提案，Bash 命令逐条审批，只读类可配自动允许，`cat>file` 也拦成审批，闭环不绕过)。
- **原话**：「抄cursor」(Bash 处置)。
- **status**：现 `acceptEdits` 直写、无 patch_proposed = target。
- **测试点**：改文件出 diff 气泡不直写；`cat>file`/`sed -i` 拦成审批卡(拒了文件不变)；Apply 走 SaveConflict + compile。
- **归属**：region [[copilot]] + [[editor]] · platform [[native-fs]](Rust 写)。

### F6 建技能向导
- **机制**：copilot-SDK 调一个**独立 brainstorming graph skill**(graph 背景知识 + skill-spec 渐进暴露 + template few-shot)对话设计新 skill(问需求→定 io schema→生成骨架)；产出落盘归 [[skill-workspace]] + [[native-fs]]。
- **决策+动机**：**实现 = 独立 brainstorming graph skill(保留 D5)**(与 F3"copilot 自身=SDK"不矛盾：向导是它调的工具型 skill，要结构化、模板可独立迭代)。**两入口**(新建 skill 时可选 + chat 说"帮我建个 X")。区别默认新建(模板文件夹 logic→agent，不调 copilot，D-1-4)。
- **原话**：实现「独立 brainstorming graph skill(D5)」/ 触发「都要」/(D5)「Copilot 对话式建技能, 需要一个类似brainstorming的skill, 加入graph_skill背景知识+skill spec(渐进式暴露)+各种template few shot模版」
- **status**：D5 graph skill 待建 = target。
- **测试点**：两入口都进向导；产出合 FROZEN 骨架(GRAPH.md+logic/agent)可直接编译。
- **归属**：engine(brainstorming graph skill 工件)；copilot-assist 调 + [[skill-workspace]] 落盘。

### F7 judge / 打磨 / commit-msg + 分析 bar（跨能力载体）
- **机制**：judge(artifact vs golden 打分+评述)/打磨/commit-msg 都在 copilot 对话里跑，**数据流归别处**(judge·打磨→[[golden-eval]]，commit-msg→[[publish]])，copilot 只渲染。**分析 bar**：predict/run 跑完 → copilot 输入框上方**瞬时弹窗**「是否自动分析」(样式参考 PM 贴图细长 bar) → 确认 → 无 golden 节点自动写 golden(有的不动) → **确认/忽略后消失**。
- **决策+动机**：所有权不变量——数据流归各自能力，copilot 只作 chat 载体+渲染，只链接不重述。分析 bar = F3 主动诊断的具体落点 + **细化 [[golden-eval]] g-e 批量入口**(sonner→弹窗)。
- **原话**：「每次跑完predict或者run, copilot输入框上方弹出一个小bar: 是否自动分析, 给用户确认. 没有写golden的节点自动写golden」/「这个bar是弹窗, 你确定了之后他就会消失, 我只是让你看下布局样式」
- **status**：judge 现不可达(view='eval' 无人传)= target；分析 bar = target。
- **测试点**：predict/run 完弹窗；确认→无 golden 节点写 golden；确认后消失；judge/打磨/commit-msg 跑在对话里、数据流落各自能力。
- **归属**：copilot-assist 拥有分析弹窗 UI；数据流 [[golden-eval]]/[[publish]]。**回写** g-e + workflow [[04_run-and-verify]]。

### F8 生命周期（出现 / Home 卸载 / 下钻无缝）
- **机制 + 决策**：出现时机=随 skill(新建空 skill 即有；welcome 屏无 copilot，Q4)；Back-to-Home 卸载→对话靠 F2 session 恢复，打开 Settings 不卸载(Q3)；下钻子图**无缝**(不切工程，copilot cwd 已含子图 path，随时切回无需缓存，T6)。
- **原话**：(Q4)copilot 随 skill、welcome 无；(Q3)Settings 不卸载；(T6)「子图下钻... assets、copilot 都不用动... copilot无缝衔接, 随时切回父图不用缓存」
- **status**：出现/卸载 live；下钻无缝 = target。
- **测试点**：welcome 无 copilot / 新建空 skill 即有；Home 卸载靠 session 恢复；下钻不切工程、copilot 接得上子图。
- **归属**：region [[copilot]] + [[shell-layout]]。

---

## 3. 接口契约
- **copilot WS（① 前端 → ③a studio backend）**：`WS /api/skills/{skill_id}/copilot/ws`（现 `routers/copilot.py:34`）。请求(MVP1 扩展)`{user_message, model_override?, mentions[], implicit_context, attachments[]（图片 base64,新）, request_id}`；响应事件 union `text_delta | thinking_delta(新) | tool_use_start | tool_use_result | patch_proposed(新) | context_resolved(新) | tool_approval_request(新) | error | done`。字段 SSOT = `apps/studio/backend/app/models/copilot.py`(实现时扩展)。错误→`error` 事件不甩 raw traceback。
- **调用 SDK（③a → claude_agent_sdk）**：copilot 自身 = `ClaudeSDKClient`；block 类型 SSOT = `claude_agent_sdk/types.py`(Text/Thinking/ToolUse/ToolResult/ServerTool)；`can_use_tool`/PreToolUse 回调拦截 Write/Edit→提案、Bash→审批(需 PoC)。
- **安全写落盘 → [[native-fs]](Rust, D12)**：Apply→编辑器 buffer(开着)或 Rust 文件命令(没开)→`SaveConflict`→compile。写入唯一权威=Rust，落点 SSOT 在 native-fs。
- **跨能力边界(数据流归别处)**：judge/打磨→[[golden-eval]]；commit-msg→[[publish]]；模型选择→[[studio-settings]]；role→route→[[gateway]] `resolve_routes("copilot_chat")`。

---

## 4. 设计决策基础（PM 原话）
> **组织方式**：**以每个功能为索引** —— 每个功能(F1–F8)一段，把它的机制/决策+动机/原话/测试点/status/归属**全收在自己段里**；仅「定义」「接口契约」是模块级总览。现状基线见 [baseline](./baseline.md)。
> **框架决策(PM 原话)**：「1.现在是mvp1. 2.做全」—— chat-shell（@mention/pill/安全写/diff）+ brain 全纳入，不再 deferred；copilot 一等能力、全功能不延后。

## 5. 决策 + 动机
| ID | 决策 | 动机 |
|---|---|---|
| COPILOT_ASSIST-1 | ThinkingBlock | 单元 `copilot-session-persistence`；**为什么**：全流式消息(含 ThinkingBlock)要完整翻译渲染、不省略 |
| COPILOT_ASSIST-2 | 安全写 | 单元 `copilot-session-persistence`；**为什么**：SDK acceptEdits 直接落盘有风险，须经提案/安全写边界 |
| COPILOT_ASSIST-3 | session | 单元 `copilot-session-persistence`；**为什么**：退出再进对话一模一样、session 必须落盘不丢(D8 MUST) |
| COPILOT_ASSIST-4 | SDK 测试 | 单元 `copilot-sdk-test-parity`；**为什么**：copilot test 必须走真实 `ClaudeSDKClient`，不能用 AsyncAnthropic 假路径 |

## 6. 测试关键点
1. ThinkingBlock: baseline 现状为 `_translate_sdk_message` 丢 ThinkingBlock ⚠️；目标为 thinking/tool call 全量流式，折叠但不省略。
2. 安全写: baseline 现状为 SDK `acceptEdits` 直写 ⚠️；目标为 Write/Edit 变 diff proposal，Apply 走 Rust/编辑器保存与冲突处理。
3. session: baseline 现状为 前端 store reset 后内存态丢失 ⚠️；目标为 一 skill 多 session 持久化，退出恢复全部与活跃 tab。
4. SDK 测试: baseline 现状为 Settings probe 走 `AsyncAnthropic` ⚠️；目标为 短 smoke 走真实 `ClaudeSDKClient` chat 路径。

## 7. 涉及 region / platform
`copilot` region · `studio-settings` · `golden-eval` · `publish` · `native-fs` · `llm-copilot-http-api`

## 8. gaps / 报警
- 🚨 ThinkingBlock: `_translate_sdk_message` 丢 ThinkingBlock ⚠️；目标 thinking/tool call 全量流式，折叠但不省略。
- 🚨 安全写: SDK `acceptEdits` 直写 ⚠️；目标 Write/Edit 变 diff proposal，Apply 走 Rust/编辑器保存与冲突处理。
- 🚨 session: 前端 store reset 后内存态丢失 ⚠️；目标 一 skill 多 session 持久化，退出恢复全部与活跃 tab。
- 🚨 SDK 测试: Settings probe 走 `AsyncAnthropic` ⚠️；目标 短 smoke 走真实 `ClaudeSDKClient` chat 路径。

> 旧迁移附录暂存 [`_migrated-coverage-drift.md`](../../_migrated-coverage-drift.md#02-capabilities-copilot-assist)（迁移期安全网，代码实现验证后删）。

## 交叉引用（链接, 不复制）
[baseline](./baseline.md)（现状,双向）· `copilot` region · `studio-settings` · `golden-eval` · `publish` · `native-fs` · `llm-copilot-http-api`
