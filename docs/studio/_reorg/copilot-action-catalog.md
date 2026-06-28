# Copilot-assist 侧边栏 — 原子动作走查 (PM 2026-06-03)

> 走查 `copilot-assist` 能力(skill 工作台右侧 copilot chat 面板)的原子动作。方式同 settings §2/§3:从**权威层**拉动作 + **现码**定 status,逐 stage 在 chat 过,PM 逐条裁定,**原话留底**。走查完并入 `mvp1/02_capabilities/copilot-assist.md` + `03_regions/copilot.md`。
>
> **源优先级(PM 2026-06-03 锁)**:
> - **权威** = `01_workflows/` + `workflow-action-catalog.md` + `alignment-notes.md`(D5/D8/Q3/Q4/T6 等)+ PM 本走查裁定。
> - **格式/字段** → FROZEN `docs/engine/skill-spec`;**实现/status** → 当前代码。
> - **参考(非权威)** = `.kiro/specs/studio-feature-copilot-chat`(reframe + 12 REQ + pm-pending)、`copilot-context-design`(@mention)。其结论只作走查参考,PM 当场确认才算数。
> - 现码 status 源 = mvp0 `copilot-chat/baseline.md`(2026-05-20);定稿写入时复核当前码 `file:line`。

---

## §0 框架决策 (PM 2026-06-03)

> 原话: **"1.现在是mvp1. 2.做全"**

- **范围 = 做全(不降级)**: copilot-assist 本轮(MVP1)范围 = **领域脑子**(知识注入 + 场景细化)+ **完整 chat-shell**(@mention 菜单/彩色 pill/安全写拦截/diff 气泡)+ **建技能向导**(D5)+ **session 持久化**(D8)+ **judge/打磨**(跨能力)+ **生命周期**(出现/卸载/下钻)。全部在范围内。
- **作废过去设计的 "MVP0 staging"**: 参考 design.md 把 chat-shell 列 Deferred、把 brain 场景细化列 MVP1 后续——PM 定"现在是 mvp1 + 做全",**这些延后项全部纳入本轮**,不再 deferred。
- **动机**: copilot 是一等能力,PM 反复强调"全功能不延后"(alignment-notes line 350/646)。
- **他属(不在本能力,但走查内要点到边界)**: 连接/路由测试/选模型机制 → `studio-settings`(§3 已走:动态浮出 opus4.8→4.7、eligible、真 SDK 测试、draft);copilot 聊天 session 落盘的 Rust 实现 → `native-fs`(D8);judge/打磨的评分数据流 → `golden-eval`;建技能向导的 graph skill → D5(独立 graph skill)。本能力**只链接**,不重述。
- **独立 P0(仍要在本走查定)**: Bash 旁路 + 安全写拦截机制(pm-pending §P0-B 的 B1 移除 Bash / B2 沙箱 cwd 二选一)。

---

## §1 基础对话 + 生命周期 (PM 2026-06-03 走查)

### 决策 + 动机
- **A3 流式折叠摘要 = Claude 自定(非 PM 设计)**: PM 原话「这需要我设计吗?? Claude sdk怎么输出的?」——渲染随 SDK 输出结构定,不是 PM 判断。**已核 `claude_agent_sdk/types.py`**:AssistantMessage.content 吐 `TextBlock`(答复)/ `ThinkingBlock`(推理,:927)/ `ToolUseBlock`/ `ToolResultBlock`/ `ServerToolUse*`。**折叠映射**:ThinkingBlock→「Thought ▾」· 读类工具(Read/未来 Grep/Glob)→「Explored ▾」· 写类(Edit/Write)→「Worked ▾」(展开看 diff)· Bash→「Ran ▾」· TextBlock=最终答复正文。**现码 gap**:`copilot.py:382-400` 只翻 Text/ToolUse/ToolResult,**丢了 ThinkingBlock**(要 Thought 折叠必须补翻)+ SystemMessage(TaskStarted/Progress/Notification)未捕获 → 接线工程。
  - **PM 2026-06-03 补正(原话「整个思考过程 tool call过程都要全部流式输出出来呀, 可以折叠但是不要省略」)**:**全部** ThinkingBlock + **全部** tool call 过程**全程流式、一条不省**;折叠(Thought/Explored/Worked/Ran)仅**视觉收纳**(默认折起、点开看全部),**绝不用摘要替代、不丢任何一步**。同 trace 走查 P2 风格。
- **A6 可操作错误卡 = 砍(过度设计)**: PM「没必要,过度设计」。连接/模型失败不做专门"指向 settings 的可操作卡",普通错误显示即可(选模型/key 配置本在 settings)。撤回参考 REQ-10。
- **A7 顶部多 session tab + new chat = 要(抄 Cursor)**: PM「要,顶部tab多个session和一个+(new chat),抄cursor」。copilot 面板**顶部一条 tab 栏**:并列多个 session tab + 一个 `+`(new chat)。切 tab=切 session;`+`=开新对话。
- **B4 一 skill 多条 session = 后者**: PM「后者多条session」。一个 skill 可有**多条** session(像 Cursor chat 历史),全部持久化、可切换/新建。**升级 D8**:session 持久化从「一 skill 一条」改「一 skill N 条」,native-fs 按 skill 存多 session 文件;退出再进恢复全部 session + 上次活跃 tab。

### 原子动作表
| # | 动作 | status | 归属/权威 |
|---|---|---|---|
| A1 | 面板随 skill 出现(新建空 skill 即有;welcome 无) | live | ✓ Q4 · region `copilot` |
| A2 | 发消息(payload 现仅 `user_message`+`model_override`;@mention 扩展见 §3) | live | — |
| A3 | **全部思考+tool call 全程流式、可折叠不省略**(Thought/Explored/Worked/Ran 默认折起、点开看全部)+ 末尾答复 | 流式 live;ThinkingBlock 补翻+折叠 = target | Claude 定(SDK 驱动) |
| A4 | 工具气泡(Read/Write/Edit/Bash 结果→diff/summary) | live | — |
| A5 | 模型选择器(选哪个 model/role 跑) | live | 机制他属 settings §3 |
| ~~A6~~ | ~~可操作错误卡~~ | **砍** | PM 砍 |
| A7 | 顶部 session tab 栏 + `+`(new chat),抄 Cursor | target(新增 UI) | PM 定 · region `copilot` |
| B1 | 出现时机:随 skill;welcome 无 | live | ✓ Q4 |
| B2 | Back-to-Home 卸载(对话靠 session 恢复);Settings 不卸载 | live | ✓ Q3 |
| B3 | 下钻子图无缝(cwd 含子图 path,不切工程/无缓存) | target | ✓ T6 |
| B4 | session 持久化:**一 skill 多条 session**,落盘 by skill,退出恢复全部+活跃 tab;跨窗口 | 现纯内存(丢)= target | ✓ D8(升级多 session)· platform `native-fs` |
| B5 | session 写盘/读回失败→显式告警不静默 | target | ✓ D8 配套 |

### 测试关键点
- ThinkingBlock 补翻后 Thought 折叠块出现可展开;回归现码丢 thinking。
- 多 session:开 N 条/切 tab/退出再进恢复全部 session + 上次活跃 tab(不串/不丢)。
- session 写盘失败→显式告警(非静默吞)。

---

## §2 领域脑子 (PM 2026-06-03 走查)

### 决策 + 动机
- **范围 = 搭 skill + 业务领域**(PM 选): copilot 既懂「怎么搭 skill」(拓扑/写 phase/io schema/修 `F-v3` 编译错误),也懂「这个 skill 的业务领域」(skill 做短剧拆解 → 也帮写"分析情绪节奏"这类领域 prompt 内容)。动机: copilot 是一等创作助手,不只当语法工具。
  - **搭 skill 知识来源(Claude 定)**: = 引擎 skill-spec(13 份)+ authoring playbook(渐进暴露,§2 注入机制)。
  - **业务领域知识 = 模型自带 + 用户直接喂文档(PM 2026-06-03 定:不做专门设计)**: 原话「领域知识先不做具体设计,靠模型自带领域知识或用户直接喂文档」——靠 ① 模型自身领域知识 ② 用户 @file/拖文档直接喂(走 §3 @mention/文件导入);**不做专门领域知识库**(真不够再加)。
- **主动性 = 主动诊断+给修法**(PM 选): 编译错误 / 数据断层 / 违 FROZEN 写法出现时,copilot 像 agent IDE 那样**主动**跳诊断 + 提修改方案,不只被动应答。
  - **触发机制(Claude 定/待细化)**: compile/lint 诊断经 context resolver 注入;主动触发 = compile-fail 事件 → copilot 主动消息,或错误旁一键"让 copilot 修"。不打扰的度待实现细化。
- **架构 = SDK + 知识插件**(PM 选,**覆盖 D5「copilot 自身=graph skill」**): copilot 自身 = `claude_agent_sdk`(`ClaudeSDKClient`),用 Claude Code 原生编辑/工具能力 + 叠加引擎知识插件。**现码 SDK 路线正确**,只需补知识注入。注: D5「建技能向导用 brainstorming graph skill」是否仍适用**建技能场景**,§5 单独定(copilot 自身实现 ≠ 建技能向导调的 skill)。
  - **注入机制(Claude 定)**: `system_prompt` = preset(claude_code)+ append(skill-authoring 薄层);engine-authoring plugin(`skills=`)渐进暴露;`add_dirs` 指向 `docs/engine/skill-spec`(只链接不复制、防漂移)。

### 原子动作
| # | 动作 | status | 归属 |
|---|---|---|---|
| BR1 | 灌 skill-authoring 知识(薄层+渐进暴露)→ grounded 改图/写 phase/读编译错误 | target | Claude(SDK 配置) |
| BR2 | 懂业务领域 = 模型自带 + 用户喂文档(@file/拖,走 §3)→ 帮写领域 prompt | target | PM 定·不做专门 KB |
| BR3 | 主动诊断:编译错误/数据断层/违 FROZEN → 主动跳诊断+给修法 | target | 触发机制待细化 |
| BR4 | (现码 gap)ThinkingBlock 补翻 → 推理可见(Thought 折叠,§1 A3) | target | Claude |

### 测试关键点
- 给真 skill 问"这个 phase 为啥编译失败" → copilot 按需读到对应 skill-spec 给 ground-truth 答案(非通用臆测)。
- 业务领域:让 copilot 帮写某 agent 的领域 prompt → 它读了 skill 现有文件/模板,不空谈。
- 主动诊断:故意写个违 FROZEN 的 phase → compile 报 `F-v3` → copilot 主动给修法。

---

## §3 @mention + 上下文注入 (PM 2026-06-03 走查)

### 决策 + 动机
- **范围 = 做全**(§0): @mention 菜单 + 自动 mention + 彩色 pill + 隐式上下文 + 后端 4 层 resolver 全建(现码纯空壳:占位符 + disabled 按钮)。
- **composer 形态 = 输入框内联彩色 pill**(PM 选,REQ-3 原版): @ 选中后在输入框内变彩色不可编辑胶囊(可删)。**工程后果(Claude 定)**: 需 tiptap 类富文本/contenteditable(react-mentions 的 textarea overlay 渲染不了真 DOM pill,pm-pending P1-E 已指出),接受此复杂度。
- **可 @ 对象集 + 自动 mention(PM 默认通过,已对齐新 canvas)**:
  | @ 类型 | 自动触发 | 注入 |
  |---|---|---|
  | `@file:path` | 点文件树/编辑器文件 | 文件全文(优先未保存草稿) |
  | `@phase:id` | 点画布节点 | phase AST(tools/prompt/io)+ 源码 |
  | `@黑板:dot` | 点线上 dot | 那刻黑板状态(**对齐 trace 走查 dot=节点间状态机**,取代旧 `@edge_context` 边语义) |
  | `@error:F-v3-x` | 点编译错误 | 结构化错误+file:line(喂 §2 主动诊断) |
  | `@trace:event` | 点 trace 事件 | 事件输入输出 |
- **隐式上下文(每条消息自动附)**: 当前 view、选中节点/边 id、打开文件、**未保存 dirty buffer**(只附 @ 的或活跃文件,非全部 open buffer)。
- **后端 4 层渐进式组装(Claude 定,SDK 工程)**: ① skill 基本信息(总在)② 选中节点 detail ③ @ 的内容 ④ lint/compile 错误。性能(参考 copilot-context-design §6):500 文件菜单 <50ms;组装超 ~150K token 截断/告警。
- **【新增】输入上下文回显(PM 2026-06-03,要做)**: 原话「能否插入在 agent 开始任务的前面... user输入完按发送后, 第一条弹出的就是这个信息, 可折叠, 可查看具体内容或文档」。即**每次发消息后、agent 开跑前,第一条就显示本轮注入了哪些上下文**(@了什么 / 当前文件 / 编译错误 / 隐式上下文),**可折叠**,**可点开看具体注入内容/文档**。动机: 与「全部不省略」(§1 A3)一套——拒绝 hidden prompt magic,你看得见 copilot 到底拿到了什么。

### 原子动作
| # | 动作 | status | 归属 |
|---|---|---|---|
| AT1 | 输入 `@` 弹 MentionMenu(files/phases/dots/errors/trace;键盘导航;模糊过滤 <50ms) | target(现纯占位符) | region `copilot` |
| AT2 | 自动 mention:点画布节点→@phase / 点 dot→@黑板 / 点文件→@file | target | 跨 region(canvas/editor/timeline → copilot) |
| AT3 | 选中 mention = 输入框内联彩色不可编辑 pill(可删) | target | region `copilot`(tiptap 类编辑器) |
| AT4 | 隐式上下文(view/选中/活跃文件/dirty buffer)随消息发 | 现 `useCopilotContext` 只发 view 快照 = 部分 | region `copilot` |
| AT5 | 后端 resolver 把 mention/隐式上下文展开成 4 层 XML 喂 system prompt | target(现只注 view JSON) | platform(copilot service) |
| AT6 | **输入上下文回显**:发送后第一条 = 本轮注入上下文清单(@/文件/错误/隐式),可折叠、可点开看具体内容/文档 | target | region `copilot` |

### 测试关键点
- 输入 `@plan` → 菜单实时过滤高亮,Enter 选中 → 输入框出现彩色 pill,可点 × 删。
- 点画布节点 → 输入框自动出 `@phase:<id>` pill;点 dot → `@黑板` pill。
- dirty 文件:编辑器改了没存,@ 它 → copilot 拿到草稿内容(非磁盘旧版)。
- 大工程(500+ 文件)@ 菜单 <50ms;上下文超 150K → 截断+告警(非静默 OOM)。
- 发送消息 → **第一条**是"本轮注入上下文"回显,可折叠、点开看实际注入的文件内容/AST/错误(拒绝 hidden prompt magic)。

---

## §4 Copilot 自写 + diff 气泡 (PM 2026-06-03 走查; 2026-06-14 例外更新)

### 决策 + 动机
- **范围 = 做全**: Copilot SDK `Read/Write/Edit` 允许自行读写 workspace;Studio 负责工具事件、diff 气泡、Open Compare 等审阅回显。`acceptEdits` 直写在 MVP1 不再算 D12 违规。
- **Write/Edit 数据流 = 2026-06-14 PM 放行**: 文件写由 SDK 工具 runner 在 workspace/cwd/add_dirs 范围内直接执行;Studio 在工具事件前后尽量采集 diff/summary,并刷新编辑器视图。D12 仍约束 Studio 自有写入(editor save / graph serialize / test_inputs / golden / runs / artifacts / publish package),不约束 Copilot SDK Write/Edit。
- **diff 气泡**: 每次改动尽量出气泡,带 **Accept/Keep**(确认保留)/ **Reject**(还原或提示手动回退)/ **Open Compare**(并排 Monaco diff)。
- **Bash 处置 = 抄 Cursor(PM 原话「抄cursor」)**: 保留 Bash/终端但 **human-in-the-loop**——
  - **文件写**走 Write/Edit → SDK 直接读写 + diff/summary 审阅(引导 model 用编辑工具,不用 Bash 重定向)。
  - **Bash 命令**(build/test/git/grep/ls)→ **每条命令卡呈现,你 Approve/Reject 才执行**(同 Cursor 终端审批);只读/安全命令可配**自动允许**白名单,写/破坏性必审批。
  - **闭环不绕过**:Bash 里 `cat > file` 也拦成待审批命令,你看得到可拒。
  - **机制(2026-06-14 更新)**: SDK `can_use_tool`/PreToolUse 对 Write/Edit 放行;对 Bash 做审批卡。(pm-pending §P0-B 的拦截机制;design 阶段 PoC 已核实 allow=SDK 直写、deny=工具失败,没有"自行 Rust 写后告诉模型成功"的中间态。)
  - ⚠️ 我对 Cursor 的理解 = 命令审批 + 编辑走 diff;若"抄 Cursor"指别的细节(auto-run 默认/allowlist 范围)点我。

### 原子动作
| # | 动作 | status | 归属 |
|---|---|---|---|
| SW1 | Write/Edit 允许 SDK 直写 workspace + 回显 diff/summary | live/target polish | platform(copilot service)+ region `copilot` |
| SW2 | diff 气泡:Apply / Reject / Open Compare(并排 Monaco) | target | region `copilot` + `editor` |
| SW3 | 改动后刷新编辑器视图;Accept/Reject 后自动 compile | target | region `copilot` + `editor` + `compile-lint` |
| SW4 | Bash 命令审批卡:Approve/Reject 才跑;只读类可配自动允许 | target(现 Bash 直跑) | region `copilot` + SDK 回调 |

### 测试关键点
- copilot Write/Edit 改文件 → 允许磁盘立即变化,并出 diff/summary 气泡。
- 文件在编辑器开着且 dirty → 工具写后编辑器视图刷新/冲突提示不静默覆盖。
- Bash `cat > x.md` / `sed -i` → 拦成审批卡,拒了文件不变(闭环不绕过)。
- 只读命令(ls/grep)→ 在 allowlist 则自动跑,否则也审批。

---

## §5 建技能向导 (PM 2026-06-03 走查, D5)

### 决策 + 动机
- **范围**: 让 copilot 从零帮你设计新 skill(对话式:问需求→定 io schema→生成骨架)。区别于默认新建(模板文件夹 logic→agent,不调 copilot,D-1-4)。
- **实现 = 独立 brainstorming graph skill(PM 选,保留 D5)**: 专门一个 graph skill 驱动向导(graph 背景知识 + skill-spec 渐进暴露 + template few-shot),copilot-SDK 调它。**与 §2 不矛盾**: §2 是 copilot **自身**实现(SDK+plugin);建技能向导是 copilot **调的一个工具型 graph skill**(D5)。动机: 向导要结构化、模板/few-shot 可独立迭代更新。
- **触发 = 都要(PM 选)**: ① 新建 skill 流程给"要 copilot 帮设计吗"入口;② chat 里说"帮我建个做 XX 的 skill" → copilot 起向导。
- **跨能力**: 向导对话/触发归本能力(copilot-assist);被调的 brainstorming graph skill = 独立 graph skill 工件(engine 跑);生成的 skill 文件/脚手架落盘归 `skill-workspace` + `native-fs`(Rust)。

### 原子动作
| # | 动作 | status | 归属 |
|---|---|---|---|
| CW1 | 新建 skill 流程入口"要 copilot 帮设计吗" | target | region `welcome`/`copilot` + skill-workspace |
| CW2 | chat 触发"帮我建个做 X 的 skill" → 起向导 | target | region `copilot` |
| CW3 | 向导 = copilot 调独立 brainstorming graph skill(背景知识+skill-spec 渐进+模板 few-shot)对话设计 | target(D5 graph skill 待建) | 独立 graph skill(engine)← copilot-assist 调 |
| CW4 | 向导产出 → 生成合 FROZEN 的 skill 骨架(GRAPH.md+phases)落盘 | target | skill-workspace + native-fs(Rust) |

### 测试关键点
- 新建选"copilot 帮设计" → 进向导;chat 说"帮我建个 X" → 同样进向导。
- 向导走完 → 生成合 FROZEN 的 skill 骨架(GRAPH.md + logic/agent),可直接编译。
- 向导用独立 graph skill(模板/few-shot 可独立更新),非硬编码 prompt。

---

## §6 judge / 打磨 / commit-msg + 分析 bar (PM 2026-06-03 走查, 跨能力)

### 决策 + 动机
- **三个跨能力动作 = copilot 承载、数据流归别处**(所有权不变量,copilot-assist 只作 chat 载体 + 渲染,只链接不重述):
  - **judge**(artifact vs golden 打分+意图偏离评述)→ 数据流归 `golden-eval`(g-a..g-f 已走查);copilot 跑 judge 对话。入口 g-e 已定。
  - **打磨(polish)**(predict 后对比打磨 / golden 打磨编排)→ 归 `golden-eval`/`predict`;copilot 跑打磨对话。
  - **commit-msg**(publish 自动生成发布说明)→ 归 `publish`(stale-doc:走 Artifact Registry 非 git);copilot 生成 msg。
- **【新增】post-predict/run 分析 bar(PM 2026-06-03)**:
  > 原话: **"每次跑完predict或者run, copilot输入框上方弹出一个小bar: 是否自动分析, 给用户确认. 没有写golden的节点自动写golden"**
  - 每次 predict/run 跑完 → copilot **输入框上方**弹**小 bar**「是否自动分析?」→ 用户确认 → copilot 自动分析结果,**对没有 golden 的节点自动设计/写 golden**(有 golden 的不动)。
  - **bar 形态(PM 2026-06-03 厘清:是弹窗)**: = 输入框**上方弹出的瞬时弹窗**(popup),**确认/忽略后即消失**(不常驻)。视觉样式参考 PM 贴图(那条细长 bar:简短状态/摘要 + 一个动作按钮),**图只示意布局样式、非常驻 git-bar**。此处 = 「是否自动分析」+ 确认按钮,点完消失。
  - **归属**: bar = **copilot-assist 拥有的 UI affordance**(copilot 面板输入框上方);golden 设计**数据流**归 `golden-eval`。
  - **关系 g-e #2(需回写)**: 这个 bar = 批量 golden 设计触发面的**细化** —— 把 g-e #2 的"sonner 确认框批量入口"落到"copilot 输入框上方小 bar"(更持久可见);g-e #1 的"占位节点旁单节点按钮"仍并存。→ **回写** `golden-eval` g-e + `01_workflows/03_prediction`。
  - **关系 §2 主动诊断**: 这是 §2「主动诊断/分析」的具体落点(跑完主动问要不要分析)。
  - **动机**: 跑完即提示补 golden,把"哪些节点还没 golden"的批量收口收到一个低打扰确认 bar。

### 原子动作
| # | 动作 | status | 归属 |
|---|---|---|---|
| JD1 | judge 对话(artifact vs golden 打分+评述) | target | 数据流 `golden-eval`;copilot 载体 |
| JD2 | 打磨对话(对比打磨 / golden 打磨编排) | target | 数据流 `golden-eval`/`predict`;copilot 载体 |
| JD3 | commit-msg 自动生成 | target | 数据流 `publish`;copilot 生成 |
| JD4 | **post-predict/run 分析弹窗**(输入框上方瞬时 popup,确认后消失,样式如图;"是否自动分析"→确认→给无 golden 节点自动写 golden) | target | **copilot-assist 拥有 UI** · golden 数据流 `golden-eval` · 回写 g-e/03 |

### 测试关键点
- predict/run 跑完 → copilot 输入框上方出现"是否自动分析"bar;确认 → 无 golden 的节点被自动设计 golden(有 golden 的不动)。
- bar = 低打扰确认(不自动跑,要用户点);拒绝则不分析。
- judge/打磨/commit-msg 跑在 copilot 对话里,数据流落各自能力(copilot 只渲染)。

---

<!-- 后续:§7 测试关键点汇总 + 开放项 + 收尾(并进 copilot-assist.md + copilot.md) -->
