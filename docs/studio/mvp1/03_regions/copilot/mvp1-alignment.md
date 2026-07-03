---
module: 03_regions/copilot
doc: mvp1-alignment
status: FROZEN（面板与 WS live；session 仍易丢，ThinkingBlock/@mention/analysis bar 未落，且 Workspace 传 outer `skillId` 有下钻风险 ⚠️。；目标结构已按 R4-R8 retrofit）
binds_baseline: ./baseline.md
units: [copilot-session-persistence, copilot-sdk-test-parity]
aligns_with: 01_workflows/04_run-and-verify.md（analysis bar）· 01_workflows/00_settings-ux-spec.md（copilot route）
---

# copilot — MVP1 Alignment

> **Tier**: region | **Owns**: `copilot-session-persistence` 的 UI/session 渲染切面；`copilot-sdk-test-parity` 的配置结果消费切面 | **现状**: 面板与 WS live；session 仍易丢，ThinkingBlock/@mention/analysis bar 未落，且 Workspace 传 outer `skillId` 有下钻风险 ⚠️。 | **Related**: [baseline](./baseline.md)（双向）· `copilot-assist` · `studio-settings` · `settings` · `native-fs` · `golden-eval`

## 1. 定义
`copilot` owns the right-side assistant panel UI: message list, tool/diff rendering, route picker, composer, chat connection status, and contextual empty states.

Source workflow basis: `01_workflows/00_settings-ux-spec.md:433`, `01_workflows/04_run-and-verify.md:124`.

## 2. 数据流 / 机制（设计细节）
### F1. Chat Panel And Connection State

- 机制: show connection status, reconnect delay, messages, errors, and composer in the side panel.
- 约束(2026-07-02 R4):**回复语言跟随用户输入语言**——用户写英文回英文、写中文回中文;系统提示词自身语言不决定回复语言(落点:后端 `BASE_SYSTEM_PROMPT_TEMPLATE` 显式语言规则,`test_copilot_system_prompt` 锁存在性)。
- 约束(2026-07-02 R3):连接状态**不占独立一行**——连接正常(open)时什么都不显示;仅断连/重连时在标题旁显示紧凑提示 chip(含 retry 倒计时)。会话 tab 条 = 单行横向滚动(本地 ScrollArea,绝不出现系统滚动条控件),**每个 tab 带关闭按钮**:关闭 = 删除该会话及其落盘文件(D8 真相在盘上,关掉的对话不得在 hydrate 时复活);关到最后一个时留一个全新空会话;关闭当前活跃 tab 时激活其前一个邻居。
- 约束(2026-07-02 R5-B,PM「多chat没有出现横向滚动条,鼠标滚轮操作应该横向滚动」):tab 条上**纵向滚轮转横向滚动**——条内容溢出时,滚轮 deltaY 直接驱动 scrollLeft(阻止页面纵滚);触控板原生横向手势(|deltaX|≥|deltaY|)不拦截。溢出可见性:悬停 tab 条时显示**细横向滚动条**(本地 ScrollArea 的 hover 型 ScrollBar,细样式、语义 token),替代 R3 的"完全隐藏"——完全隐藏让 PM 无从判断还有更多 tab。无溢出时滚轮不拦、条不出现。
- 约束(2026-07-02 R5-E,PM「一般 copilot 通常是一个人的名字,有没有类似织神之类的美好的神话人物」→ 定名 MoirAI):**助手身份 = MoirAI**,取自古希腊命运三女神 **Moirai**——神话里每个生命是一根线,三姐妹分工:Clotho 纺线、Lachesis 量长短、Atropos 剪断。映射到本 copilot 陪一个 skill 的线走完一生的三段:**Clotho = 设计 skill**(把散落意图纺成 GRAPH.md + phases)、**Lachesis = 编译 + 修 bug**(比照该有的尺寸量准修顺)、**Atropos = 整体 eval**(对整张 graph 的运行结果下不可撤销的终判);终判反馈回流 Clotho 重新设计 = 迭代循环。现状**只有 Clotho 这只手落座**(今天的 copilot);Lachesis/Atropos 是已命名、已划职、**未实现**的保留席位——UI 不得凭空显示未实现的角色。名字双关 **Moir-AI**(词尾即 AI)。读音:MoirAI ≈「莫伊莱」(/ˈmɔɪraɪ/),Clotho /ˈkloʊθoʊ/、Lachesis /ˈlækɪsɪs/、Atropos /ˈætrəpɒs/(=「不可转」)。命名历程:织女 (Zhinü) 已被 MoirAI 取代;Ariadne(阿里阿德涅之线 = DAG 寻路)、Clotho 曾入围;MoirAI 系**产品内 agent 人格名、非产品名 / 公司名**,故与同名者(Salesforce MoiraiAgent、moirai-solutions 等)不构成冲突(PM 2026-07-02 拍板)。功能域名称(Settings 的 Copilot tab、copilot_* role key、API 路径)**不改**——改的是 agent 人格名,不是系统术语。
- 约束(2026-07-02 R5-E 图标 + 开关,PM「找一个类似 m 的星座图标」「把 copilot 开关换成圆形 m 图标放在 canvas 上,点击展开面板做过渡动画,再点收起」):身份标 = **仙后座(Cassiopeia)五星连线**自绘 SVG(`components/copilot/moirai-mark.tsx`,`currentColor` 主题化),一形三读——字母 **M**、**星座**、**节点 + 边的图(DAG)**。面板开关**从顶栏移到画布**(顶栏原 `Sparkles` 删除),面板收起时画布上浮现圆形 FAB(`copilot-fab.tsx`),PM 二轮定型:**① 默认右上角**;**② 画布范围内可自由拖动**(pointer 拖拽 + 边界夹取,拖/点用位移阈值区分,位置本会话持久);**③ 小尺寸(36px)、无边框**;**④ 配色 = 面板同款**——底用 `--studio-canvas-surface`(与 copilot 面板一致)、标用 `--studio-canvas-accent`(与 header 标一致),即「把 header logo 摘到画布上」而非实心高亮块。开合动画 PM 定型为**多段位移**:点 FAB → 先**垂直**移到 header 行高、再**水平**移到 panel header logo 落点(`headerLogoTarget`,WAAPI L 路径 ~440ms),到位后面板从该角展开(`origin-top-left` fade+zoom+slide,zoom/slide 仅 `motion-safe`,reduced-motion 退纯 fade / 无位移直接开);header 收起控件(`PanelRightClose`)收回。纯几何(默认位/夹取/logo 落点/L 路径/点击判定)抽 `copilot-fab-geometry.ts` 并 TDD。
- 决策: Copilot is a side assistant, not a blocking modal.
- 原话/来源: `01_workflows/00_settings-ux-spec.md:433` assigns Copilot configuration and runtime dependency.
- 测试: closed websocket disables send; reconnect updates status; switching skills resets messages/context.
- Status: live with skill prop risk.
- 归属: region `copilot`; capability `copilot-assist`.

### F2. View Context Sync

- 机制: selected node/edge/lint/view state posts to copilot context endpoint with compaction.
- 决策: chat should understand current screen without pasting huge payloads.
- 原话/来源: `01_workflows/00_settings-ux-spec.md:462` lists cross-cutting settings/copilot dependencies.
- 测试: selecting node updates context; large context is summarized with fingerprint.
- Status: live.
- 归属: region `copilot`; capability `copilot-assist`.

### F3. Role & Route Picker（composer 与 Settings 同源）

- 机制: composer 的 role 下拉与 Settings Copilot tab 的角色卡**同一份派生真相**(`deriveCopilotDisplayRoles`,吃 `GET /api/llm/roles` + registry `model_groups`),route 下拉(model_override)从**选中显示角色的 `fallback_chain`** 派生、可用性用 registry `provider_routes` 投影。**不得**把 `GET /api/llm/registry` 的 roles 物化投影当第二份 role 真相读。
- 约束(同步契约,2026-07-01 PM 决策"copilot role 和 settings 页 roles 不同步"是缺陷):
  1. composer 只列**已绑定 model group**(fallback_chain 非空)的 copilot 角色;Settings 里的空草稿卡(未选组的 `copilot_custom_N`)不出现在 composer——它还不是可用角色。
  2. 无任何持久化 copilot 角色时,Settings 浮出的内置默认(atom-56 语义,rendered-not-persisted)**同样出现在 composer**;首次用它发消息 = "动了" → 前端先按 Settings 同一物化路径(`buildCopilotRoleEntry` + `copilot_<slug>` key,PUT /api/llm/roles)落库,再以持久化 key 发送。
  3. 默认选中 = 派生列表第一项;**删除前端写死的 `copilot_chat` 默认常量**(旧路径,不向后兼容);后端 ws 契约里 `role` 缺省仍按约定名解析,但面板一律显式传 role。
  4. `roles_changed` / `registry_changed` 事件驱动刷新,Settings 改完 composer 实时跟上。
  5. **加载态可见(2026-07-02 R5-C,PM「启动时下方 copilot role 没读出来时,加一个 skeleton 占位或 loading 状态」)**:roles + registry 两个请求**都落定**(成功或失败)之前,设置行的 role/route 槽位渲染 shadcn Skeleton 占位(registry 冷启动探测可达 ~45s,空槽会被误读为"没有 role 功能");失败也算落定——骨架必须撤下,换成落定后的 role 锚点(见约束 7),不许永挂。
  6. **图标语义(R5-C,PM「UserCog 违和,他不是一个真的 role」)**:role picker 触发器图标 = lucide `BrainCircuit`——选的是"这次对话背后的模型 persona/脑子",不是用户配置齿轮。
  7. **role 锚点永不消失(2026-07-02 R6-1,PM「为什么我删了两个 role,copilot 面板的模型选择没有了?能不能不管怎么样都显示着,哪怕没有模型」)**:落定后 role picker(`RolePicker`)**始终渲染一个可见锚点**——这**推翻**了旧 F6「no dead placeholder controls / options ≤1 就 render null」规则(它导致删到只剩 1 个浮出默认时整个模型选择消失)。三态:①**0 个**可用角色 → 渲染禁用态空锚点(`BrainCircuit` + "No copilot role" + tooltip 指向 Settings→Copilot);②**≥1 个** → 渲染下拉(1 个时下拉里就 1 项,但锚点+当前角色名可见);route picker(`ModelPicker`,次要)可在 role 缺失或链上 ≤1 条路时继续隐藏——锚点职责由 role picker 承担。
- 决策: route/role config comes from Settings; chat only consumes it — consuming 的派生函数也必须同一份,不许面板自养第二套判定。
- 原话/来源: `01_workflows/00_settings-ux-spec.md:433` assigns Copilot settings; `01_workflows/00_settings-ux-spec.md:395` assigns role mapping; 浮出/物化语义见 settings copilot 设计 atom-55/56(`docs/studio/mvp1/_impl/frontend-handbook/tpl-copilot-design.json` 派生视图,源头 `00_settings-ux-spec.md` §3.2)。
- 测试: composer 选项集合 == Settings displayRoles(配置完成子集);空草稿不出现;浮出角色首发消息触发物化并用持久化 key;changing route affects future messages; unavailable config shows scoped error; Settings 增删/换组后 composer 经事件刷新对齐。
- Status: live(2026-07-01 收敛落地:面板 registry.roles 第二真相 / 浮出角色被滤 / 空草稿可选 / copilot_chat 写死默认均已删,composer 与 Settings 同源)。
- 归属: region `copilot`; capability `studio-settings`.

### F4. Tool And Diff Rendering

- 机制: tool calls and edit diffs render inside assistant messages with expandable details.
- 决策: assistant actions need inspectable output, especially for code/doc edits.
- 原话/来源: `01_workflows/04_run-and-verify.md:79` uses copilot-like output as the reference for trace folding; same pattern applies here.
- 测试: Read/Edit/Bash events show start/result; diff bubble only appears when diff text exists.
- Status: live.
- 归属: region `copilot`; capability `copilot-assist`.

### F5. Golden Design Entry

- 机制: trace/golden flows can open copilot chats for missing node golden design.
- 决策: golden creation 有 trace-local 入口 + **批量 = Copilot 分析 bar**(predict/run 后弹窗,sonner→弹窗),见 `copilot-assist` F7。
- 原话/来源: `01_workflows/04_run-and-verify.md:124` lists copilot golden creation; `01_workflows/04_run-and-verify.md:137` requires both entries.
- 测试: golden CTA starts a chat seeded with graph/node/output context.
- Status: target-design.
- 归属: region `copilot`; capability `golden-eval`.

### F6. Message Scrolling & Composer（2026-07-01 新增）

- 机制: 消息区滚动遵循 shadcn radix **message-scroller** 交互契约(`https://ui.shadcn.com/docs/components/radix/message-scroller`):流式回复时贴底自动跟随(live edge);用户上滚离开底部即释放跟随、绝不抢滚;露出「回到底部」按钮;新一轮用户消息锚定在视口顶部附近(turn anchoring);布局变化(markdown 展开/图加载)保持阅读位置。落地为 `src/components/ui/message-scroller.tsx` 的 shadcn 风格封装(缺原语先补 ui/ 再用,FRONTEND_UI_SPEC §2.1),面板消息区不再用裸 `overflow-y-auto` 承担主滚动(§2.6)。
- Composer(布局按 PM 2026-07-02 截图纠正:**发送在输入框盒内,设置在盒外**):
  1. 输入框默认可视高度 **≈3 行**(单行太小,PM 2026-07-01),随内容自增到上限(~160px)后内部滚动。
  2. **边框盒内只有 textarea + 右下角发送按钮**(流式期间应变为停止按钮,依赖 F7-③ interrupt,未落地前保持发送禁用态);**所有设置控件在边框盒外的下方一行**(Claude Code 布局,PM 2026-07-02「text area 里面只有发送和停止的按钮。其他设置按钮在 text area 的下方」):左侧 = 上下文动作(附件 / @mention,F7,可用后才渲染),右侧 = role 选择 + route 选择。
  3. route 下拉 = 在选中角色兜底链内临时指定本次对话优先线路(model_override);**兜底链 ≤1 条时隐藏**,不渲染禁用占位。
  4. **不渲染任何无功能占位按钮**——附件/@/停止只在真实可用后出现(本文件历史教训:死占位按钮误导 PM)。
  5. Enter 发送、Shift+Enter 换行;IME 组合输入(`isComposing`)期间 Enter 不发送。
  6. **消息布局(2026-07-02 R3,PM 原话「不需要空一栏给图标,也不需要分 you 和 copilot,左右布局就能分辨」)**:左右气泡布局——用户消息右对齐、`bg-muted` 圆角气泡、纯文本 pre-wrap;助手消息左对齐、无气泡纯排版(markdown);**不渲染 You/Copilot 名字标签、状态文字和头像列**。落地用本地 `components/ui/message.tsx`(shadcn message 原语,align start/end)。
  7. **等待可见(thinking)**:从发送瞬间到首个可见活动之间必须有可见等待指示(shadcn **shimmer** 文字 Thinking…,官方 loading-text 处理)——覆盖两段:①助手消息尚未创建的事件前空窗;②助手消息已建但 `status=running` 且无可见活动(冷启动 spawn 可达 10-30s;context_resolved 回显不算可见活动、不清除它)。F8 真流式落地后,**thinking 增量内容本身就是等待可见性的主体**:首个 thinking token 或正文 token 一到,shimmer 即撤,由实时转录接棒。
  8. 排版:消息与 composer 正文用 `text-sm leading-relaxed`(此前 text-xs/leading-snug 过挤);消息区视口 `p-4`、消息间距 `gap-3`(R4,PM「左边边距窄」;参照官方 message-scroller 示例 `p-6/gap-4` 按窄面板收敛一档)。**markdown 排版真相 = `.copilot-prose`(index.css,全语义 token + `--font-mono` 代码块)**——R5-D 根因:旧代码的 `prose prose-sm …` 全是死类(`@tailwindcss/typography` 从未安装),助手 markdown 一直是浏览器默认样式(标题不分级、列表序号丢、代码块裸排),这就是 PM「排版丑、和整个 app 不在一个世界」的结构性原因;修法是自建 token 化样式而**不是**装 typography 插件(插件自带灰阶调色 = 又一个第二世界)。
  10. **信息层次(R5-D,PM「挂载或者工具调用结果都会用淡一号的字」)**:两级层次——正文与用户消息全对比(text-foreground);**次级信息**(context_resolved 卡 / 工具卡 / Thought / unknown)标签行统一 `text-muted-foreground`,hover 恢复全对比作可点暗示;工具失败保持 destructive 色。用户气泡改用本地 `ui/bubble.tsx`(shadcn Bubble 原语,variant=muted align=end)替代手搓 `div.bg-muted`(shadcn chat.md 契约:message surface 必须是 Bubble)。
  9. 前端引入 `shadcn` tailwind 工具包(`@import "shadcn/tailwind.css"`):激活 shimmer 与 ui/message-scroller 自带的 scrollbar-*/scroll-fade-* 工具类(此前这些类是死类)。
- 决策: 聊天区的滚动/输入行为向官方 message-scroller 契约看齐,不自造第二套滚动启发式。
- 原话/来源: PM 2026-07-01(本轮任务原话):「参考这个官方组件 ui,优化现在的 copilot 面板」「下方的输入窗口默认只有一行有点太小了」「我比较喜欢 Claude code 的布局方式,功能在输入框下方」。
- 测试: 流式输出时列表贴底;上滚后新增内容不抢滚、出现回底按钮;点击回底恢复跟随;composer 默认高度≈3 行;Enter 发送/Shift+Enter 换行/IME 不误发;占位按钮不存在。
- Status: live(2026-07-01 滚动+三行;2026-07-02 布局纠正 + R3 气泡左右布局/thinking 可见/排版/状态条收敛/会话 tab 关闭)。
- 归属: region `copilot`; capability `copilot-assist`.

### F7. Composer 上下文与控制(2026-07-02 新增,target-design)

- 机制: composer 的三个待落地控制,各自独立成 PR、全栈落地(不做前端假按钮):
  1. **@mention 弹出器**:textarea 中键入 `@` 在光标处弹节点选择 popover(数据源=当前 skill 图节点),选中插入 `@<node_id>` token 并把该节点加入 mentions;发送前 mentions 随 view-context POST `/skills/{id}/copilot/context` 注入——**后端 mentions 层已就绪**(`app/services/copilot.py` context 压缩已渲染 `mentions` XML 层),缺的只是前端选择器与采集链路。
  2. **附件(外部文件/图片)**:PM 2026-07-02 决策反转本文件 §4 旧条目「砍掉 Attach file」——**附件按钮要保留且做真**:「添加附件还是要的啊,添加外部的文件、图片等,和 @mention 是两码事」。@mention=图内节点上下文,附件=外部文件输入,二者并存。入口三个:附件按钮(系统文件选择)+ 拖拽 + 粘贴;格式与大小约束沿用 §4(Claude 原生组:PNG/JPEG/GIF/WebP ≤~5MB / PDF / 文本类);链路 = 前端把附件(base64+media_type)放进 ws send payload → studio 后端转 `claude_agent_sdk` 内容块(ImageContent 等)→ 非 vision 模型给「不支持图片」降级提示。后端目前无此通路(copilot.py 无 ImageContent),需后端新增。
  3. **停止按钮**:流式期间发送按钮变停止;ws 增加控制消息(如 `{"type":"interrupt"}`)→ 后端对当前 `ClaudeSDKClient` 调 `interrupt()`。后端 ws 循环目前无 interrupt 通道,需后端新增。
- 决策: 三个控制都是「可用才渲染」;各自单独 PR 排队(mention → interrupt → attach,按后端工作量升序),不把 composer 布局修正(F6)拖在一起。
- 原话/来源: PM 2026-07-02 本轮反馈原话(见上);mentions 后端座:`apps/studio/backend/app/services/copilot.py` context 压缩 `mentions` 层。
- 测试: @ 键入弹出/选中插入 token/context POST 含 mentions;附件选择/拖拽/粘贴后 chips 呈现、payload 带内容块、非 vision 降级提示;流式中点停止 → 流即断、消息态落 stopped。
- Status: target-design(2026-07-02,分 PR 落地)。
- 归属: region `copilot`; capability `copilot-assist`(附件链路含 studio 后端)。

### F8. 真流式输出(token-level streaming,2026-07-02 R5 新增)

- 机制(wire 协议语义锁定:`text_delta` / `thinking_delta` 事件名本来就是**增量片段**;把一整块当一个"delta"发 = 违反本契约):
  1. **后端逐 token 翻译**:`ClaudeAgentOptions` 开 `include_partial_messages=True`;SDK `StreamEvent`(raw Anthropic stream event)中 `content_block_delta` 的 `text_delta` → `CopilotEventText`、`thinking_delta` → `CopilotEventThinking`,按到达顺序立即入流;`signature_delta` / `input_json_delta` / 生命周期事件(message_start 等)不产生 UI 事件;带 `parent_tool_use_id` 的子流不进主转录。
  1a. **thinking display 必须显式 `"summarized"`**:CLI 的 thinking display 只有 `summarized | omitted` 两档(**不存在 "full"**,旧实现注释"默认 full"是误认知);不设 display 时 ThinkingBlock 到达即被剥空(`thinking=""`,探针实证 2026-07-02)——这是 R5「thinking 从来不显示」的最终根因。`{"type":"adaptive","display":"summarized"}` 下推理内容以 thinking_delta 逐段流出(实测 17 deltas / 722 chars),是 CLI 能提供的最大暴露,即 F1「不省略」在 CLI 约束下的落地上限。
  2. **完整消息去重**:开启 partial 后,同一条助手消息流完仍会收到完整 `AssistantMessage`——翻译器是**有状态**的:该消息已流出过 text/thinking 增量时,完整消息里的 TextBlock/ThinkingBlock 不再重复发;`ToolUseBlock` 恒从完整消息发 `tool_use_start`(工具入参只有整块才有;它在工具执行前到达,满足「每个工具调用实时出现」),工具结果仍从后续 UserMessage 的 ToolResultBlock 发。
  3. **无流降级**:某轮若没有收到任何 partial 增量(异构 anthropic-compat 端点不吐 stream event),完整消息按整块发——宁整块勿丢字。
  3a. **转录如实,政策在 SDK 层**:翻译器对**每一个** `ToolUseBlock` 按真实工具名登记并发 `tool_use_start`,不设翻译层白名单——SDK 实际会执行预允许清单之外的只读工具(live 证据 2026-07-02:模型用了 Glob/Grep 且真的执行了),旧的「V1 不支持工具 X」error 是在对既成事实撒谎,还令后续 tool_result 因名字未登记只能显示裸 `toolu_…` id。允许/拦截哪些工具由 SDK 选项(`allowed_tools` / `can_use_tool`)决定,转录层永不编造。
  3b. **error 语义收窄(事件契约)**:`CopilotEventError` **只保留给终结流的致命错误**(route 解析失败、SDK 连接失败等,发出后本轮流即结束);**工具失败是可恢复事实**(模型通常会绕过重试),一律走 `tool_use_result(success=false)`。前端因此可以放心把 error 事件作为消息状态机的终结输入——旧行为里一条中途工具报错会把助手消息切断、后续事件漂进新消息。
  4. **前端消息状态机**:助手消息 `status` 是消息级生命周期 `running → success | error`,**只由终结事件(done/error)驱动**;中间事件(context_resolved / tool_* / thinking)一律不得覆盖消息 status(R5 根因:context_resolved 事件级 status=success 把消息翻成 success,thinking 指示当场消失)。
  5. **前端实时转录渲染**:events 数组保存了完整到达时序(text_delta 也入 events)——助手消息按 events 重建分段转录:连续 text 增量合并为一个 markdown 段、连续 thinking 增量合并为一个 Thought 块、工具卡片按时序插在段间;不再把整段 `content` 渲染在事件区上方(时序错乱),`content` 仍作为持久化与纯文本真相累积。增量入 store 按 ~75ms 窗口合并(text 与 thinking 同一队列),避免逐 token 重渲染与 events 无界膨胀。
- 决策: 流式是聊天面板的基础可用性,不是视觉糖;去重靠翻译器状态而不是靠猜 provider 行为,降级路径保证异构端点不丢内容。
- 原话/来源: PM 2026-07-02 R5:「我输入hello之后,只有spec已挂载,完全没有thinking之类的提示,结果也是一下子出现的,完全没有流式输出」;PM 补充:「thinking...只是状态,真正的thinking/reasoning内容也要流式输出,每个工具调用也要流式输出」。
- 测试: 后端 translator 单测(StreamEvent delta→事件、同消息完整块去重、无流降级整块发、忽略 signature/input_json/子流);前端单测(中间事件不覆盖消息 status;delta 队列合并;events→分段转录:text/thinking 归并、工具按时序插段);live 私有 sidecar 验证短问题逐 token、thinking 内容实时、工具调用逐个出现。
- Status: 设计定稿(2026-07-02)→ 实施中。
- 归属: region `copilot`; capability `copilot-assist`(后端 translator 在 studio 后端)。

### F9. 转录阅读体验(2026-07-02 R7-A 新增)

流式已经能跑(F8),但「读」得很差(PM 2026-07-02 R7:「不会自动往下拉显示最新结果」「中间过程完成后不收束、loading 圈继续转」「thinking 不自动滚」「字体再小一号」「最后只保留最终输出,把上面所有过程收束到一个折叠的过程行,加处理时间,类似 processed 44s ›」;另 item7「去掉对话小字前面那根竖线」、item3「聊天内容无法选择」)。约束:

  1. **过程/答案分层(`partitionAssistantView`)**:一个 turn 拆成 **PROCESS**(thinking / 工具卡 / context / 中间叙述)和 **ANSWER**(最后一段文本)。
     - **流式中**:PROCESS 实时内联展开(看着它发生)+ ANSWER 边流边出。
     - **结束(done)后**:PROCESS **整体收进一个默认折叠的 `<details>`**,summary = 「`Processed {Ns} ›`」(`formatProcessedDuration`,时长 = done.receivedAt − message.createdAt),下面只留 ANSWER 展开。ANSWER = 最后一段 text run;无最终文本(纯工具 turn)时 answer=null、全部进 PROCESS。
  2. **自动滚底**:流式时视口黏底,跟随 thinking + 答案增长(MessageScroller `autoScroll`;实测 atBottom 全程保持)。
  3. **工具卡 spinner 只在流式转**:`ToolCallBubble` 收 `streaming` prop——`tool_use_start` 的 `Loader2 animate-spin` 只在 `streaming` 时转;turn 结束后过程折叠、spinner 随之消失(修 R7「loading 圈继续转」)。
  4. **thinking 自动滚**:`ThinkingBlock` 的 `<pre>` 在流式时把 scrollTop 顶到 scrollHeight,始终显示最新推理。
  5. **无竖线**:转录内所有二级信息块(thinking / 工具 / context / error / unknown)一律去掉 `border-l` 左规,改用留白/缩进(PM item7)。
  6. **字体降一档**:ANSWER `text-[13px]`,PROCESS 二级信息 `text-xs`。
  7. **可选中**:消息容器 + thinking `<pre>` spread `allowTextSelectionProps()` 进入全局文本选择白名单(FRONTEND_UI_SPEC §2.11,PM item3)。
- 决策: 「过程」是可展开的审计轨,不是要一直占屏的东西——默认收束成一行 + 处理时间,把注意力还给最终答案;这是 F1「不省略」(过程仍可展开逐步查看)和「可读」的平衡。
- 测试: 前端单测 `partitionAssistantView`(过程/答案分离、纯工具 turn answer=null、流式中 duration=null)+ `formatProcessedDuration`(秒/分秒);live 验证流式黏底 + done 后折叠成 `Processed Ns ›` + 竖线消除。
- Status: 设计定稿 + 实施(2026-07-02)。
- 归属: region `copilot`; capability `copilot-assist`。

## 3. 接口契约
- Inputs: current skill id, current view context, copilot role route data, websocket events.
- Outputs: user message, optional route override, attach/context selection requests.
- Capability links: `copilot-assist`, `studio-settings`, `golden-eval`, `debug-resume`.
- Platform link: `gateway`.

## 4. 设计决策基础（PM 原话）
- ~~砍掉旧 Attach file / Add context 占位按钮(上下文统一走 F4 @mention)~~ **已被 PM 2026-07-02 反转**:「添加附件还是要的啊,添加外部的文件、图片等,和@mention 是两码事」——附件按钮保留且必须做真(外部文件/图片入口,F7-②);@mention 负责图内节点上下文(F7-①)。仍然成立的部分:**无功能的占位死按钮不许渲染**。
- **composer 新增图片附加**:① 拖拽图片文件;② 粘贴剪贴板图片(= "截图后加载":系统截图到剪贴板再 ⌘V)。**可行性已核**:`claude_agent_sdk` 有 `ImageContent` 输入类型 + `query` 收 message dict(含图)+ Claude 多模态 → 收图 OK;拖拽/粘贴纯前端、无需新 Tauri 插件。
- **不做应用内截图按钮**:截图统一靠系统快捷键 + 粘贴(② 已覆盖)——Mac `⌘⌃⇧4` / Windows `Win+Shift+S` 都框选到剪贴板、跨平台都简单;应用内 capture 要写三套原生代码、不值。
- **文件格式**:仅支持 Claude 原生组——图片(PNG/JPEG/GIF/WebP,单张 ≤~5MB)/ PDF / 文本类(md/code/json/csv 当文本读);**不支持格式给清晰提示**(转 PDF/图片/文本)。**自动转格式不在 copilot 做**,归 DEF-012(引擎内置转换 tools)、技能图按需调。
- **前提**:copilot 角色须用 vision 模型(Claude 系);非 vision 模型给"不支持图片"降级提示。

## 5. 决策 + 动机
| ID | 决策 | 动机 |
|---|---|---|
| COPILOT-1 | session UI | 单元 `copilot-session-persistence`；**为什么**：退出再进对话一模一样，session 渲染基于持久化(D8) |
| COPILOT-2 | analysis bar | 单元 `copilot-session-persistence`；**为什么**：copilot 分析 bar 是 golden/诊断入口，挂在会话流里 |
| COPILOT-3 | 下钻 skillId | 单元 `copilot-session-persistence`；**为什么**：下钻子图时 copilot 用 currentSkillId、cwd 含子图 path，不丢上下文 |
| COPILOT-4 | message-scroller + composer(F6) | PM 2026-07-01；**为什么**：流式聊天贴底/释放/回底与三行 composer 是基础可用性，向 shadcn 官方契约看齐、不自造滚动启发式 |
| COPILOT-5 | role/route 同源(F3) | PM 2026-07-01「role 不同步」；**为什么**：composer 与 Settings 必须同一份派生真相 + 同一物化路径，否则两处各自为政必然漂移 |

## 6. 测试关键点
1. session UI: baseline 现状为 内存态 / skill 切换 reset 风险 ⚠️；目标为 顶部多 session tab 持久化并恢复。
2. analysis bar: baseline 现状为 旧 golden 入口/sonner 口径残留 ⚠️；目标为 predict/run 后输入框上方弹 analysis bar，确认后消失。
3. 下钻 skillId: baseline 现状为 Panel 收 outer `skillId`，非 `currentSkillId` ⚠️；目标为 子图下钻时 copilot 上下文与 currentSkillId 一致。

## 7. 涉及 region / platform
`copilot-assist` · `studio-settings` · `settings` · `native-fs` · `golden-eval`

## 8. gaps / 报警
- 🚨 session UI: 内存态 / skill 切换 reset 风险 ⚠️；目标 顶部多 session tab 持久化并恢复。
- 🚨 analysis bar: 旧 golden 入口/sonner 口径残留 ⚠️；目标 predict/run 后输入框上方弹 analysis bar，确认后消失。
- 🚨 下钻 skillId: Panel 收 outer `skillId`，非 `currentSkillId` ⚠️；目标 子图下钻时 copilot 上下文与 currentSkillId 一致。

## 交叉引用（链接, 不复制）
[baseline](./baseline.md)（现状,双向）· `copilot-assist` · `studio-settings` · `settings` · `native-fs` · `golden-eval`
