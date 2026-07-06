---
module: 02_capabilities/copilot-assist
doc: mvp1-alignment
status: FROZEN（SDK 对话 live；Write/Edit 直写为 MVP1 允许口径，仍缺 diff 审阅体验；session/window persistence live，ThinkingBlock 未翻译，Settings 里的 SDK 测试路径与真实 chat 不等价 ⚠️。；目标结构已按 R4-R8 retrofit）
binds_baseline: ./baseline.md
units: [copilot-sdk-test-parity, copilot-session-persistence]
aligns_with: 01_workflows/00_settings-ux-spec.md（Copilot SDK test）· 01_workflows/04_run-and-verify.md（analysis bar）
---

# copilot-assist — MVP1 Alignment

> **Tier**: capability | **Owns**: `copilot-sdk-test-parity`（真实 SDK smoke 路径）+ `copilot-session-persistence`（多 session / 消息渲染） | **现状**: SDK 对话 live；Write/Edit 直写为 MVP1 允许口径，仍缺 diff 审阅体验；session/window persistence live，ThinkingBlock 未翻译，Settings 里的 SDK 测试路径与真实 chat 不等价 ⚠️。 | **Related**: [baseline](./baseline.md)（双向）· `copilot` region · `studio-settings` · `golden-eval` · `publish` · `native-fs` · `llm-copilot-http-api`

## 1. 定义
copilot-assist = skill 工作台右侧 copilot 助手的端到端行为：一个**懂搭 skill + 懂业务领域**的对话助手，能精确取上下文（@mention）、允许 SDK 在 workspace 内自行读写文件并配套审阅回显、对话式建技能、承载 judge/打磨、跑完主动提分析。

## 2. 数据流 / 机制（设计细节）
### 功能逐项（原 F 段迁移）

### F1 对话 + 流式输出（折叠不省略）
- **机制**：用户发消息 → 后端 SDK → 全部 block 流式回 → 前端按 block 类型折叠渲染(ThinkingBlock→Thought ▾ / 读类工具→Explored ▾ / 写类→Worked ▾ / Bash→Ran ▾ / TextBlock=答复正文)。
- **决策+动机**：**全部思考 + 全部 tool call 全程流式、折叠仅视觉(默认折起点开看全部)、绝不摘要替代/不丢步**。渲染随 SDK 输出结构定(非 PM 设计)。现码 `copilot.py:382-400` 丢 `ThinkingBlock` → 必修。砍"可操作错误卡"(过度设计)。
- **原话**：「整个思考过程 tool call过程都要全部流式输出出来呀, 可以折叠但是不要省略」/「这需要我设计吗?? Claude sdk怎么输出的?」
- **status**：流式 live(75ms 批)；ThinkingBlock 补翻 + 折叠 = target。
- **测试点**：全部 thinking+tool call 流式、折叠可展开看全部、不丢(回归现码丢 thinking)。
- **归属**：region [[copilot]]。

### F2 多 session（顶部 tab + new chat / restore chat）
- **机制**：copilot 面板顶部一条 tab 栏 = 并列多个 session tab + 一个 `+` 动作菜单（`New chat` / `Restore chat`）；切 tab=切 session；一 skill 多条 session 文件全持久化为历史库，同时每个 skill 有 `_window.json` 窗口状态文件，记录 `openSessionIds` + `activeSessionId`。打开 skill 时只恢复 `_window.json` 里上次打开的 tab 集合与活跃 tab，不自动打开该 skill 下所有历史 session 文件。`openSessionIds=[]` 是合法窗口状态：面板显示一个不落盘的临时草稿 tab，用户首条发送才物化为真实 session 文件并写回 `_window.json`。
- **决策+动机**：一 skill **多条** session(抄 Cursor chat 历史)；session 必持久化(D8 MUST)，落盘归 [[native-fs]](Rust 按 skill 存多 session 文件，跨窗口)；关闭 tab 只从窗口状态移除，不删除 transcript 文件；关闭最后一个 tab 只把 `_window.json` 写成空窗口状态，不创建新的空 transcript 文件；`New chat` 是显式用户动作，可立即创建空 session；`Restore chat` 通过原生文件选择器默认打开本 skill 的 session 目录并把选中的合法 `<sessionId>.json` 加回窗口。写盘/读回失败→显式告警不静默。
- **原话**：「要,顶部tab多个session和一个+(new chat),抄cursor」/「后者多条session」/(D8)「copilot对话不能丢, 退出再进去要打开一摸一样的对话, session记录都要在, 和cursor一样, 这点必须要做到」
- **status**：live。
- **测试点**：开 N 条/切 tab/关闭部分 tab/退出恢复同一窗口 tab 集合 + 活跃 tab(不串/不丢、不复活未打开历史)；关闭 tab 不删除 transcript；关闭最后一个 tab 写空窗口状态且不创建新 transcript；空窗口 panel 仍显示临时草稿 tab 与 `+` 菜单；首条消息物化真实 session；`+ → Restore chat` 默认打开本 skill session 目录并恢复选中文件；写盘失败显式告警。
- **归属**：region [[copilot]] · platform [[native-fs]]。

### F3 领域脑子（搭 skill + 业务领域 + 主动诊断）
- **机制**：`system_prompt` 薄层(skill-authoring 浓缩) + `engine-authoring` plugin + `add_dirs`(skill-spec)渐进暴露；compile/lint 诊断经 context resolver 注入。
- **决策+动机**：**范围 = 搭 skill + 业务领域**(搭 skill 靠 skill-spec 注入；业务领域**靠模型自带 + 用户喂文档**@file/拖，**不做专门 KB**，真不够再加)。**主动性 = 主动诊断+给修法**(编译错/数据断层/违 FROZEN → 主动诊断，含 F7 分析 bar)。**架构 = SDK + 知识插件**(覆盖 D5「copilot 自身=graph skill」；现码 SDK 路线对，补知识注入)。
- **原话**：「1.现在是mvp1. 2.做全」/「领域知识先不做具体设计, 靠模型自带领域知识或用户直接喂文档」
- **status**：现 3 行通用 prompt(`copilot.py:70`)= target。
- **测试点**：问"为啥编译失败"→读 skill-spec 给 ground-truth；帮写领域 prompt→读 skill 文件不空谈；违 FROZEN→compile 报 `F-v3`→主动给修法。
- **归属**：platform engine(skill-spec 知识源)；触发粒度待细化(见 gaps)。

### F4 @mention + 显式请求上下文 + 上下文回显
- **机制**：① 显式 @ → 输入框弹 MentionMenu(files/phases/dots/errors/trace，键盘导航，模糊过滤 <50ms)；② 只有用户在 composer 中选择/保留的 @mention 随本次 Copilot 消息发送；③ 禁止点画布节点/dot/文件后自动把对象送给 Copilot，禁止隐式 view/选中/dirty buffer 后台同步；④ 后端 resolver 只处理当前 WS 消息 payload 中的显式 mentions/attachments/judge context；⑤ 发送后**第一条**回显本轮实际注入清单。
- **决策+动机**：**composer = 输入框内联彩色 pill**(需 tiptap 类富文本，react-mentions overlay 渲染不了真 DOM pill)；**dot=黑板**(对齐 trace 走查，取代旧 @edge_context 边语义)；**上下文回显插在 agent 开跑前、第一条**(可折叠、点开看实际内容/文档，反 hidden prompt magic，与 F1"不省略"一套)。
- **原话**：「输入框内联彩色 pill」/「能否插入在 agent 开始任务的前面... user输入完按发送后, 第一条弹出的就是这个信息, 可折叠, 可查看具体内容或文档」
- **status**：现纯空壳(占位符 + disabled "Add context")= target。
- **测试点**：输入 `@plan`→菜单过滤高亮、选中成内联 pill 可删；点击画布节点/dot/文件本身不触发后端 Copilot 请求；发送消息时 payload 只包含 composer 内显式 mentions；发送后第一条=注入清单点开看内容；大工程菜单 <50ms / 超 150K 截断告警。
- **归属**：region [[copilot]](菜单/pill/回显)；可提名对象来自 [[canvas]]/[[editor]]/[[timeline]]，但提名只由 composer 内显式选择触发。

### F5 Copilot 自写 + diff 气泡 + Bash 审批
- **机制**：MVP1 明确允许 Copilot SDK `Read/Write/Edit` 在当前 workspace/cwd/add_dirs 范围内自行读写文件；Studio 不要求把 Write/Edit 拦成 Rust 写入或 `patch_proposed` 才算合规。工具事件仍要回显，能拿到前后内容时展示 diff 气泡 / Open Compare；写后 compile/predict/run 使用磁盘上的最新结果。Bash 命令仍逐条审批卡(human-in-the-loop)，因为 Bash 可执行任意 shell 与重定向写入。
- **决策+动机**：PM 2026-06-14 对 Copilot Write/Edit 作 MVP1 例外：这条“放过”，允许 copilot 自己读写。D12 仍约束 Studio 自有本地写入（编辑器保存、脚手架、graph serialize、test_inputs/golden/runs/artifacts、publish 打包等）走 [[native-fs]]；Copilot SDK 工具 runner 视为外部 agent runtime 的受控 workspace 操作，不再作为 D12 阻断项。**Bash 抄 Cursor**(保留 Bash 但 human-in-the-loop:Bash 命令逐条审批,只读类可配自动允许,`cat>file`/`sed -i` 这类 shell 写入也走审批,闭环不绕过)。
- **原话**：「抄cursor」(Bash 处置) / 「Copilot Write/Edit 这条放过,在 MVP1 设计文档里也注明一下,允许 copilot 自己读写」。
- **status**：SDK `acceptEdits` 直写 = MVP1 允许；diff 审阅 / Open Compare / 工具事件回显强化 = target，不再把 Write/Edit 直写标为 D12 违规。
- **测试点**：Write/Edit 可在 workspace 内直接修改文件且不触发 D12 违规报警；改后 predict/run 读取最新文件；工具事件展示文件名与 diff/summary（可取到前后内容时）；Bash 审批拒绝后不执行。
- **归属**：Write/Edit 自写归 region [[copilot]] / `copilot-assist`；Studio 自有写入仍归 platform [[native-fs]]。

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
- **机制 + 决策**：出现时机=随 skill(新建空 skill 即有；welcome 屏无 copilot，Q4)；Copilot 的会话加载、窗口状态恢复、WebSocket 生命周期绑定「打开/关闭 skill」，不绑定右侧 panel 展开/收起；panel 展开/收起只影响 UI 呈现。Back-to-Home 卸载→对话靠 F2 session 恢复，打开 Settings 不卸载(Q3)；下钻子图**无缝**(不切工程，copilot cwd 已含子图 path，随时切回无需缓存，T6)。
- **原话**：(Q4)copilot 随 skill、welcome 无；(Q3)Settings 不卸载；(T6)「子图下钻... assets、copilot 都不用动... copilot无缝衔接, 随时切回父图不用缓存」
- **status**：出现/卸载 live；会话加载/WS 生命周期随 skill live；下钻无缝 = target。
- **测试点**：welcome 无 copilot / 新建空 skill 即有；Home 卸载靠 session 恢复；下钻不切工程、copilot 接得上子图。
- **归属**：region [[copilot]] + [[shell-layout]]。

---

## 3. 接口契约
- **copilot WS（① 前端 → ③a studio backend）**：`WS /api/skills/{skill_id}/copilot/ws`（现 `routers/copilot.py:34`）。请求(MVP1 扩展)`{user_message, model_override?, mentions[], attachments[]（图片 base64,新）, request_id}`；响应事件 union `text_delta | thinking_delta(新) | tool_use_start | tool_use_result | patch_applied(新) | context_resolved(新) | tool_approval_request(新) | error | done`。字段 SSOT = `apps/studio/backend/app/models/copilot.py`(实现时扩展)。错误→`error` 事件不甩 raw traceback。
- **调用 SDK（③a → claude_agent_sdk）**：copilot 自身 = `ClaudeSDKClient`；block 类型 SSOT = `claude_agent_sdk/types.py`(Text/Thinking/ToolUse/ToolResult/ServerTool)；MVP1 允许 SDK `Read/Write/Edit` 自行读写 workspace；`can_use_tool`/PreToolUse 主要用于 Bash 审批与必要的 workspace 边界控制。
- **Copilot Write/Edit 例外（D12 carve-out）**：Copilot SDK 工具 runner 的 Write/Edit 不走 [[native-fs]] 也不算 D12 违规；Studio 负责事件回显、diff/summary、必要时刷新编辑器视图。D12 仍适用于 Studio 自有写入链路（editor save、graph serialize、test_inputs/golden/runs/artifacts、publish package 等）。
- **跨能力边界(数据流归别处)**：judge/打磨→[[golden-eval]]；commit-msg→[[publish]]；模型选择→[[studio-settings]]；role→route→[[gateway]] `resolve_routes("copilot_chat")`。

---

## 4. 设计决策基础（PM 原话）
> **组织方式**：**以每个功能为索引** —— 每个功能(F1–F8)一段，把它的机制/决策+动机/原话/测试点/status/归属**全收在自己段里**；仅「定义」「接口契约」是模块级总览。现状基线见 [baseline](./baseline.md)。
> **框架决策(PM 原话)**：「1.现在是mvp1. 2.做全」—— chat-shell（@mention/pill/diff/Bash 审批）+ brain 全纳入，不再 deferred；copilot 一等能力、全功能不延后。

## 5. 决策 + 动机
| ID | 决策 | 动机 |
|---|---|---|
| COPILOT_ASSIST-1 | ThinkingBlock | 单元 `copilot-session-persistence`；**为什么**：全流式消息(含 ThinkingBlock)要完整翻译渲染、不省略 |
| COPILOT_ASSIST-2 | Copilot Write/Edit 自写例外 | 单元 `copilot-session-persistence`；**为什么**：MVP1 允许 SDK Write/Edit 直接读写 workspace，保留 diff/summary 审阅体验；D12 继续约束 Studio 自有写入，Bash 仍逐条审批 |
| COPILOT_ASSIST-3 | session | 单元 `copilot-session-persistence`；**为什么**：退出再进对话一模一样、session 必须落盘不丢(D8 MUST) |
| COPILOT_ASSIST-4 | SDK 测试 | 单元 `copilot-sdk-test-parity`；**为什么**：copilot test 必须走真实 `ClaudeSDKClient`，不能用 AsyncAnthropic 假路径 |

## 6. 测试关键点
1. ThinkingBlock: baseline 现状为 `_translate_sdk_message` 丢 ThinkingBlock ⚠️；目标为 thinking/tool call 全量流式，折叠但不省略。
2. Copilot Write/Edit 自写例外: baseline 现状为 SDK `acceptEdits` 直写；目标为 允许直写 workspace，同时回显工具事件与 diff/summary，Bash 仍 human-in-the-loop。
3. session: 现状为 一 skill 多 session 历史持久化，并用 `_window.json` 恢复上次打开的 tab 集合与活跃 tab；空窗口状态合法,首条消息才把临时草稿物化为真实 session。
4. SDK 测试: baseline 现状为 Settings probe 走 `AsyncAnthropic` ⚠️；目标为 短 smoke 走真实 `ClaudeSDKClient` chat 路径。

## 7. 涉及 region / platform
`copilot` region · `studio-settings` · `golden-eval` · `publish` · `native-fs` · `llm-copilot-http-api`

## 8. gaps / 报警
- 🚨 ThinkingBlock: `_translate_sdk_message` 丢 ThinkingBlock ⚠️；目标 thinking/tool call 全量流式，折叠但不省略。
- ⚠️ diff 审阅体验: SDK `acceptEdits` 直写为 MVP1 允许；剩余目标是稳定回显工具事件、diff/summary 与 Open Compare，不再把 Write/Edit 直写列为 D12 阻断。
- ✅ session: 一 skill 多 session 历史持久化 + `_window.json` 窗口恢复已 live；空窗口状态合法,临时草稿首发才落盘。
- 🚨 SDK 测试: Settings probe 走 `AsyncAnthropic` ⚠️；目标 短 smoke 走真实 `ClaudeSDKClient` chat 路径。

> 旧迁移附录暂存 [`_migrated-coverage-drift.md`](../../_migrated-coverage-drift.md#02-capabilities-copilot-assist)（迁移期安全网，代码实现验证后删）。

## 交叉引用（链接, 不复制）
[baseline](./baseline.md)（现状,双向）· `copilot` region · `studio-settings` · `golden-eval` · `publish` · `native-fs` · `llm-copilot-http-api`
