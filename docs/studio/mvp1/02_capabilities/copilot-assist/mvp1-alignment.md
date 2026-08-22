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
- **status**：线上契约、后端 resolver 与 composer 的 ①②③ 均已 live——composer 是一台 ProseMirror(tiptap)编辑器,键入 `@` 弹 MentionMenu(五类、模糊过滤、键盘导航),选中落成一枚带 `(kind, ref, label)` 的原子 pill,发送时 pill 变成正文里的 `@label` 加 `mentions[]` 里的一条身份(COPILOT_ASSIST-10 ①);resolver 按 COPILOT_ASSIST-8 分「读正文」与「只给引用」两类,⑤ 的回显逐条说明每一条实际变成了什么。附图入口按 COPILOT_ASSIST-11 落地:剪贴板粘贴与一颗附图按钮两个入口,输入框上方逐张显示缩略图与体积、可逐张移除,一轮图片总量 8 MB(前端在挑选那一刻拒、后端在边界再拒,两处同一个数由测试钉住),超限或类型不在四种之内当场点名拒收、绝不悄悄压缩。**F4 全部五条已 live。**
- **测试点**：输入 `@plan`→菜单过滤高亮、选中成内联 pill 可删；点击画布节点/dot/文件本身不触发后端 Copilot 请求；发送消息时 payload 只包含 composer 内显式 mentions；发送后第一条=注入清单点开看内容；大工程菜单 <50ms / 超 150K 截断告警。
- **归属**：region [[copilot]](菜单/pill/回显)；可提名对象来自 [[canvas]]/[[editor]]/[[timeline]]，但提名只由 composer 内显式选择触发。
- **决策 COPILOT_ASSIST-8(一次提名是用户挑出来的一个东西,不是一段被猜出来的上下文;2026-08-20 立,问题台账 CP1)**:
  F4 已经说清「谁能被提名」和「什么时候注入」,没说**一次提名在线上长什么样**。这条把它定死。
  - **提名的身份 = `(kind, ref)`,两者都由发出这条消息的前端给出**,后端不反查、不补全、不猜。
    `kind` 是封闭集 `file | phase | dot | error | trace`——正是 ① 列的五类;`ref` 在该 kind 内
    唯一定位那个对象(file=工作区相对路径;phase=相位 id,子图内的写成 `<subgraph>/<phase>`;
    dot=黑板键 `<phase>.<key>`;error=诊断 code 加位置;trace=`<run_id>#<event_index>`)。
  - **为什么 `ref` 必须由前端给**:提名这个动作发生在 composer 里,那一刻用户看着的是哪个对象
    **只有前端知道**。让后端拿显示名去反查,等于把「用户挑了哪一个」变成一次模糊匹配——而 ③
    禁的正是「系统替用户决定上下文是什么」。同理,一条提名解析不到东西时不许**顺手换一个近似的**。
  - **`label` 只用于回显,不参与定位**。显示名会变(相位改个名),而已经发出去的那条消息里,
    用户当时看见的就该是当时那个字——把 label 当 id 会让历史消息在改名后指向别处。
  - **附件的内容随消息走,不是一个待解引用的路径**:`attachments[]` 每项是 `kind: "image"` +
    `media_type` + base64 `data` + 可选 `name`。图片没有「工作区里的稳定坐标」——用户是从剪贴板
    或文件对话框拿来的,下一秒那个文件可能就不在了。这与 mention 用 `ref` 恰恰相反,分界是
    **这个东西在工作区里有没有一个改天还找得到的地址**。
  - **注入内容还是注入引用,按「这个东西在工作区里有没有一份可以现在读出来的正文」分**:
    `file` 与 `phase` 指向工作区里的真文件,后端**读出正文注入**(超出预算按 F4 ① 的
    150K 告警口径截断并在回显里说明截了);`dot` / `error` / `trace` 指向的是**某一次运行或某一次
    编译期间才存在的东西**,后端不去解引用,只把 `(kind, ref, label)` 原样作为结构化引用注入——
    copilot 手上本来就有取它们的工具,而后端替它取一次,等于把「哪一次 run 的哪个值」这个判断
    从模型手里挪走,又绕回 ③ 禁止的那条路。**这是能力边界,不是省事**:注入引用的那三类,回显
    里写明「给的是引用不是正文」,用户看得见自己得到的是哪一种。
  - **解析失败当场说,不静默丢**:取正文的两类,`ref` 解析不到(文件被删、相位被改名)时,
    ⑤ 的回显里逐条明写「这一条没解析到」,并**照常发出这一轮**——不悄悄摘掉(用户会以为它
    进去了),也不因此拒绝整条消息(用户的问题本身仍然有效)。呼应 F1「不省略」:
    **注入清单说的必须是实际注入的**。
  - **边界**:resolver 的输入只有本条 WS 消息里的 `mentions` / `attachments` / `judge_context`,
    不读「当前选中的节点」「最近打开的文件」这类会话侧状态——③④ 在这里没有留任何入口。
  - **借了什么拒了什么**:身份用 `(kind, ref)` 两段而不是一个大字符串,借的是 URI 的
    scheme+path 分法——kind 决定 ref 该怎么解释,于是加一类可提名对象不需要改解析规则;
    **拒**了真的用 URI 字符串(`file://…`),因为那要求每一类都能编码进一套转义规则,而
    `dot` 的键、`trace` 的事件下标本来就不是路径,硬套只会让前后端各写一份易错的拆分。
- **决策 COPILOT_ASSIST-10(提名在屏幕上、在正文里、在菜单里各长什么样;2026-08-21 立,问题台账 CP1)**:
  COPILOT_ASSIST-8 定死了一次提名在**线上**的形状 `(kind, ref, label)`,没说它在**屏幕上**
  和在 `user_message` **正文里**长什么样。这条把剩下的三处定死。
  - **① 一枚 pill 在正文里就是 `@<label>`,在它原来的位置**。`mentions[]` 携带身份,
    `user_message` 携带的是**一句话**——模型读到的必须仍然是一句通顺的话。把 pill 从正文里
    抹掉,「看一下 @plan 再改」会变成「看一下  再改」,模型只能去 `<mentions>` 块里猜它
    原本指着句子的哪个位置。用 `@label` 而不是 `ref`,是因为**用户当时看见的就是 label**:
    正文、屏幕、⑤ 的回显三处说的是同一个字。身份仍然只走 `mentions[]`——正文里那个 `@label`
    不定位任何东西,这正是 COPILOT_ASSIST-8「label 只回显不定位」在正文这一侧的同一条规矩。
  - **② 同一个 `(kind, ref)` 提两次,只读一次正文;正文里两个 `@label` 都留着**。
    去重发生在**后端 resolver**,因为 150K 的注入预算是后端的规矩(`MENTION_CONTENT_BUDGET`,
    一轮共用一份)——同一份文件读两遍不多给出任何信息,却可能把第二条提名挤出预算。
    放在前端去重会让这条规矩依赖客户端守规矩,而预算的 owner 不是客户端(「Fail fast,
    在边界校验」)。**这不是替用户决定上下文是什么**:被合并的两条指的是同一个对象,
    不存在「挑了哪一个」的判断;⑤ 的回显仍逐条说明,合并了就说合并了。
  - **③ 菜单按 ① 列的顺序分组:file → phase → dot → error → trace,每组至多 8 条,
    被截断的组在组头写明还有多少条没显示**。分组而不是按分数混排,是因为五类是 F4 立的
    词表,用户想找一个相位时不该在文件里翻;每组设上限,是因为一个大工程的文件数会把另外
    四类挤出屏幕,而 F4 的「大工程菜单 <50ms」本来就要求菜单不能无限长。**截断必须说出来**:
    一个没说自己被截断的清单,会让用户以为那个对象不存在——这与 F13「一个看不出理由的命中,
    比没有命中更坏」是同一条:**屏幕不能让人得出错误结论,哪怕它显示的每一条都是对的**。
  - **④ composer 是一台 ProseMirror 编辑器(tiptap 是它的 React 绑定)**。F4 已经判定需要
    「tiptap 类富文本」,这条记下**借了什么、拒了什么**:
    **借**的是 ProseMirror 的两样东西——一是 `atom: true` 的行内节点,它让一枚 pill 在
    退格时**整枚消失**而不是掉一个字母(自己用 `contenteditable` 搭的话,这一条要靠手写
    选区逻辑去猜);二是它对**输入法组合态**的处理(`DOMObserver` 在 `compositionstart`
    与 `compositionend` 之间挂起 DOM 观察),而本产品的主力输入是中文——手搓 contenteditable
    在输入法上翻车是这类编辑器最常见的死法,那正是「凭直觉发明」。
    **拒**的是 tiptap 的 `StarterKit` 与官方 `@tiptap/extension-mention`:composer 的文档
    只有「一段文字 + 若干原子」,没有标题、列表、加粗,装 StarterKit 等于为用不上的 schema
    付体积;而官方 mention 扩展的属性是 `(id, label)` 两段,套不进 COPILOT_ASSIST-8 的
    `(kind, ref, label)` 三段——改造它的 schema 比自己声明一个 40 行的 Node 更绕。
    保留的第三方件是 `@tiptap/suggestion`:它负责「`@` 从哪个位置开始、查询串到哪结束、
    这个位置在后续 transaction 里漂到哪去」,这套位置跟踪是真正难写对的部分。
  - **⑤「彩色 pill」= 一眼看出这不是打出来的字,不是给五个 kind 配五种色**。
    F4 的原话是「输入框内联彩色 pill」,它要解决的问题是**pill 与正文文字混在一起分不开**;
    而把 kind 编进色相会撞上 `FRONTEND_UI_SPEC.md` §2.2 立的那条硬规则——
    **颜色只表达严重度,不表达分类**,判据是「把一屏截图去饱和,信息不该丢失」。
    五个色相扛五个 kind,去饱和之后 kind 就没了,直接判负。那条规则不是审美偏好,
    它带着实证:2026-08-08 的 Trace 面板 40 条事件里 39 条带彩色胶囊,颜色的信噪比归零,
    真正出错的那一条反而不突出。
    所以 pill 只有**一种**呈现(`bg-primary/10` 淡底 + `text-foreground`,§2.2 认可的
    「承载文字的主色面」写法),kind 按 §2.2 指定的方式用**文字**承载:菜单在**挑选那一刻**
    就按 kind 分了组,label 本身也自带区分度(`plan` / `plan.outline` / `GRAPH.md`);
    唯一会歧义的情形——同名的一个文件和一个相位——由 pill 的 hover title `kind · ref` 消歧。
    **设计源这条措辞据此订正**:两份文档只有一份能对,而针对颜色语义、带判据和实证的那一份
    更专门,所以 §2.2 赢,F4 的「彩色」按其本意读作「与正文可区分」。
- **决策 COPILOT_ASSIST-11(一张图怎么进来、多大算太大、太大时说什么;2026-08-21 立,问题台账 CP1)**:
  COPILOT_ASSIST-8 已定死附件在线上的形状(`kind: "image"` + `media_type` + base64 `data` +
  可选 `name`),并说清了它**按值走**的理由——图片在工作区里没有一个改天还找得到的地址。
  这条补上它在**界面上**和**边界上**的三件事。
  - **① 两个入口,都由用户显式动手:composer 里粘贴,和一颗附图按钮**。COPILOT_ASSIST-8 已经
    写明来源是「剪贴板或文件对话框」,这里把两者都做出来。按钮用 `<input type="file">` 而不是
    Tauri 原生对话框:原生对话框返回的是一条**路径**,而附件要的是**字节**,再绕一次 Rust 读盘
    只是把「按值」这件事重新变成一次解引用;`<input type="file">` 在 Tauri webview 里同样弹
    系统对话框,却直接给到 `File`。**这不与 D12 冲突**:D12 约束的是「谁能往磁盘上**写** skill
    文件」,附图是读一个工作区之外的文件,不产生任何写入。
  - **② 一轮的图片总量上限 8 MB(解码后字节),超了当场拒收,并说出它有多大**。
    这个数不是拍脑袋:整条消息(正文 + `mentions[]` + `attachments[]`)装在**一个 WebSocket
    帧**里发出去,而 uvicorn 的帧上限 `ws_max_size` 默认是 16 MiB
    (`.venv/Lib/site-packages/uvicorn/config.py:189`,`16 * 1024 * 1024`)——**超限不是报错,
    是连接被掐掉、这条消息无声消失**,用户看不到任何解释。base64 把字节撑成 4/3,8 MB 图片
    编码后约 10.7 MiB,给正文和提名留出充裕余量。
    **只设一轮总量,不另设单张上限**:总量已经把「一张巨图」挡住了,再加一条单张规则不多挡任何
    东西,只多一句要解释的话。
  - **③ 太大就拒收,绝不悄悄压缩**。自动降采样看起来体贴,实际是**把用户交上来的证据换掉**——
    他截图给 copilot 看的可能正是某个一像素的错位。这与 F4 ⑤「回显说的必须是实际注入的」、
    与 COPILOT_ASSIST-8「解析失败当场说,不静默丢」是同一条纪律:**屏幕上说的,必须是真的发生的**。
    同理,`media_type` 不在那四种之内的文件当场拒收并点名它是什么类型,不猜、不改扩展名。
  - **④ 上限由后端拥有,前端照着做,并有门禁钉住两边是同一个数**。真正的边界是后端
    (`CopilotWsRequestPayload` 校验一轮总量,不合格立刻拒),因为一条规矩不能指望客户端记得守;
    但只让后端拒,用户要**打完整条消息、按下发送**才知道图太大,而那时他已经没得选。所以前端在
    **挑选那一刻**用同一个数拒收。两处各写一个常量本来就是两份真相,所以加一条后端测试去读前端
    那个 TS 常量、断言两个数字相等——把「两份拷贝」变成「一份真相加一面被检查的镜子」,
    与本仓已有的文档哈希锁、颜色语言扫描是同一套手法。
  - **⑤ 屏幕上看得见自己附了什么**:每张图在输入框上方是一枚缩略图卡片,带文件名、体积和一个
    移除控件;发送成功后清空。理由同 F4 ⑤ 的回显:**用户必须能在按下发送之前看清这一轮到底带了什么**。
  - **⑥ 一张图本身就是一整轮:没有文字也能发,发完历史里仍看得出它带过什么**(2026-08-21 立,
    问题台账 CP1)。「这里哪儿不对?」问的常常就是那张截图本身,要求必须再打几个字,等于在**最常见
    的问法上**把发送键置灰。由此定死三处:
    - **「这一轮是不是空的」只有一个判据,一处定义**:正文与附件**都**为空才算空。发送键的可用态、
      发送处理、真正写进 socket 的那一步,读的必须是**同一个**判据函数,不是各写一份看起来一样的
      条件。**这条不是洁癖,是实证**:三处各自判断时,前两处放行、第三处按「正文为空」拦下,结果是
      **按键亮着、按下去什么也不发生、也不报错**——2026-08-21 真机点验抓到的就是这个,而当时接缝
      测试全绿,因为测试替身里没有第三处那条守卫。
    - **发给模型的那条消息里,不放空的文本块**:图片自己成块,前面不挂一个空字符串——
      provider 拒收空文本块,而这个拒收发生在用户看不见的地方。
    - **历史里这一轮要说得出自己带过图**:纯图片的一轮在记录里不能是一个空气泡。会话文件每来一条
      消息就整份重写,所以**存的是描述(文件名、类型、字节数),不是图片本身**——字节已经送到模型
      手里了,把它再抄进每一份会话快照,只会让历史文件按 MB 长而没有任何读者需要它。

### F5 Copilot 自写 + diff 气泡 + Bash 审批
- **机制**：MVP1 明确允许 Copilot SDK `Read/Write/Edit` 在当前 workspace/cwd/add_dirs 范围内自行读写文件；Studio 不要求把 Write/Edit 拦成 Rust 写入或 `patch_proposed` 才算合规。工具事件仍要回显，能拿到前后内容时展示 diff 气泡 / Open Compare；写后 compile/predict/run 使用磁盘上的最新结果。Bash 命令仍逐条审批卡(human-in-the-loop)，因为 Bash 可执行任意 shell 与重定向写入。
- **决策+动机**：PM 2026-06-14 对 Copilot Write/Edit 作 MVP1 例外：这条“放过”，允许 copilot 自己读写。D12 仍约束 Studio 自有本地写入（编辑器保存、脚手架、graph serialize、test_inputs/golden/runs/artifacts、publish 打包等）走 [[native-fs]]；Copilot SDK 工具 runner 视为外部 agent runtime 的受控 workspace 操作，不再作为 D12 阻断项。**Bash 抄 Cursor**(保留 Bash 但 human-in-the-loop:Bash 命令逐条审批,只读类可配自动允许,`cat>file`/`sed -i` 这类 shell 写入也走审批,闭环不绕过)。
- **原话**：「抄cursor」(Bash 处置) / 「Copilot Write/Edit 这条放过,在 MVP1 设计文档里也注明一下,允许 copilot 自己读写」。
- **status**：SDK `acceptEdits` 直写 = MVP1 允许；diff 审阅 / Open Compare / 工具事件回显强化 = target，不再把 Write/Edit 直写标为 D12 违规。
- **决策 COPILOT_ASSIST-6(用户的决议归消息记录所有,不归卡片;2026-08-20 立,问题台账 CP6)**：
  用户在卡片上做出的决议——批准这条 Bash、接受这个补丁——是**关于那条消息的事实**,
  所以它写在**事件对象本身**上(审批卡 `decision: pending|approved|denied`,补丁气泡
  `review: pending|accepted|rejected`),随会话一起落盘。
  卡片**只渲染记录里写着的东西**,自己不记任何记录里没有的状态;组件本地 state 只留
  「这一刻正在提交」这种真·瞬态。
  **为什么**:此前决议只活在卡片的 `useState` 里,而会话是要序列化成 JSON 写盘的——
  于是存下去的永远是卡片刚到时的样子:仍然 pending、按钮仍然可点。面板收起再展开、
  切会话标签、冷启后 Restore chat,**每一张已决议的卡片都复活成未决议**,再点一下就得到
  一条红 toast。这不是渲染 bug,是**状态放错了 owner**(呼应通用工程原则「显式状态与唯一
  owner」)。落盘时机也随之收紧:决议要**立刻**持久化,不能等消息 settle——模型正**阻塞在
  这条审批上**,消息恰恰要等这个决议才settle得了。
- **决策 COPILOT_ASSIST-7(挂起没了要说清是哪一种没了;2026-08-20 立,问题台账 CP6)**：
  后端对一条不再挂起的审批,必须区分**三种**结局并各自回一句人话:①**已决议过**
  (重复点击 / 陈旧卡片);②**超时,任务已停**;③**这个会话已经不在了**(app 或会话重启)。
  从前三种一律回 `approval_not_found`,前端还在外面套一层「Approval expired:」——
  把其中一种当成事实断言,而它三次里有两次是错的。
  实现上后端**按会话记住每条已结束审批的结束原因**(参照 supervisor 记录子进程退出原因:
  「没了」和「因为超时没了」不是同一个答案),生命周期与会话同长,`_cleanup_pending_tool_approvals`
  清挂起时一并清掉——所以它不会无限增长,而一个已被清掉的会话里的审批号,本来就正是第③种。
- **决策 COPILOT_ASSIST-9(挂起自己过期时,要在它那张卡上说出来;2026-08-20 立,问题台账 CP7)**：
  一条挂起审批到时无人应答,后端**停任务、保会话**(`can_use_tool` 回 `interrupt=True`)。
  这里**刻意不折算成「用户拒绝」**:把一个没有人做过的拒绝喂给模型,它会带着一个错误
  信号继续往下跑。而这件事**必须回到那张卡上**:过期事件要**指名 `tool_use_id`**,
  前端据此把那一张卡 settle 成 `decision: timed_out` —— 按钮消失,文案从
  「Waiting for approval.」换成「超时,任务已停,发新消息可继续」。
  **为什么做成 `decision` 的第四个取值,而不是另开一个字段**:这一个字段回答的正是
  「这次挂起是怎么结束的」;再加一个字段回答同一个问题,就多了一个随时会跟它打架的
  东西(呼应通用工程原则「显式状态与唯一 owner」)。**没有人决议本身就是一种结局**,
  它该被记下来,而不是靠另一个布尔值旁注。
  **为什么过期事件必须自报家门**:它从前是一条泛型 `error` —— 能说「有东西过期了」,
  说不出**是哪一张卡**。于是没有任何一张卡认得出这是在说自己,它们全都继续停在
  「Waiting for approval.」、按钮照样可点,而背后的任务早就停了。这正是仓规
  「事件说不清是哪份数据变了,就去修事件契约」的原样场景。
  **与 COPILOT_ASSIST-7 的分工**:两者是同一条挂起生命周期的两半 —— 7 管**用户来问**
  的时候(点了一张陈旧的卡)后端要如实答出是哪一种结局;9 管**没有人问**的时候后端要
  主动说,而且要说给具体的那一张卡听。
- **测试点**：Write/Edit 可在 workspace 内直接修改文件且不触发 D12 违规报警；改后 predict/run 读取最新文件；工具事件展示文件名与 diff/summary（可取到前后内容时）；Bash 审批拒绝后不执行；挂起超时后那张卡自报 `timed_out`、按钮消失、并说明任务已停。
- **归属**：Write/Edit 自写归 region [[copilot]] / `copilot-assist`；Studio 自有写入仍归 platform [[native-fs]]。

### F6 建技能向导
- **机制**：copilot **自己**主持向导对话(问需求 → 定 root io schema → 生成骨架 → 当场编译),
  依据是一份随包发布的 **brainstorming 技能资产**(`app/agents/skills/brainstorming/`:graph 背景知识
  按需引 KB、skill-spec 渐进暴露、几份 template few-shot);产出落盘归 [[skill-workspace]] + [[native-fs]]。
- **决策+动机**：**两入口**(新建 skill 时可选 + chat 说"帮我建个 X")与**产出判据**(合 FROZEN 骨架、
  可直接编译)都不变;**变的只有「谁来主持这段对话」**。
  **原方案是「copilot-SDK 调一个独立 brainstorming *graph* skill」,2026-08-22 实施时判定不成立**,
  两条证据,都不是成本问题而是**做不出来**:
  1. **它没有地方可住**。桌面 app 打包的资源只有 `vendor/**/*`
     (`apps/studio/tauri/tauri.conf.json` 的 `bundle.resources`),仓里也不再有 bundled skill 根
     ——bundled skill 在 **#377「bundled 脱主仓」**里被特意移走了。一个 graph skill 必须**先作为
     skill 装在用户机器上**才跑得起来,所以这条路要先重新造一套「随 app 发布 + 首次运行安装 +
     写进 skill_index」的分发子系统,而那正是上一轮刚拆掉的东西。
  2. **它在需要它的那一刻还跑不起来**。graph skill 的 agent 相位要经 gateway 解析 **LLM role**;
     而向导要服务的正是**刚点下 New Skill、一个 role 都还没配**的人。copilot 用的是自己的凭据,
     不受这个 bootstrap 影响——**这正是它该主持这段对话的原因**,不是权宜。
  与 F3「copilot 自身 = SDK」一致:向导是**它的对话脚本**,不是它调的外部工件。原方案想要的
  「结构化、模板可独立迭代」由**技能资产文件**照样满足——`SKILL.md` 独立于代码迭代,
  改它不用改一行 Python。
  **这份资产挂在 MoirAI 名下**(`agent-skill-map.json` 的 `moirai` 行),不走三女神派工:
  copilot.py 里那条「整池给她会让派工失去理由」的注释针对的是**专家的设计技能**
  (给她 `agent-prompt-design`,她每次都会自己干而不派 Clotho);向导是**前台的流程脚本**,
  流程内部该派 Clotho 做领域分析/图设计时照派不误。
  区别默认新建(模板文件夹 logic→agent,不调 copilot,D-1-4):New Skill 对话框给**两个动作**,
  默认那个原样保留。
- **原话**：触发「都要」/(D5)「Copilot 对话式建技能, 需要一个类似brainstorming的skill,
  加入graph_skill背景知识+skill spec(渐进式暴露)+各种template few shot模版」
  ——原话说的是「一个类似 brainstorming 的 skill」,没有指定它必须是 graph skill;
  「graph skill」是上一轮设计写下的实现选择,本轮按上述两条证据改判。
- **status**：live(2026-08-22)。
- **测试点**：两入口都进向导;产出合 FROZEN 骨架(GRAPH.md+logic/agent)可直接编译;
  默认新建那条路不受影响(不开 copilot、直接铺模板)。
- **归属**：copilot-assist 拥有向导资产与两个入口;产出落盘 [[skill-workspace]] + [[native-fs]]。

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

> **编号更正(2026-08-21)**:`COPILOT_ASSIST-8` 一度同时指两条决议——CP1 的「一次提名的
> 身份是 `(kind, ref)`」与 CP7 的「挂起自己过期要落到那张卡上」,两条都在 2026-08-20 由
> 并行的两个任务各自认领了同一个号。一个 ID 指着两样东西就不成其为 ID,所以重编:
> **8 留给提名身份**(它被 `app/models/copilot.py`、`services/copilot_context.py`、
> `types/copilot.ts` 等处按名引用),**挂起过期改为 9**,本轮新立的提名呈现改为 **10**。
> 编号是标识符不是时间轴,所以 9 早于 10 成立并不矛盾——各条自己写着成立日期。

| ID | 决策 | 动机 |
|---|---|---|
| COPILOT_ASSIST-1 | ThinkingBlock | 单元 `copilot-session-persistence`；**为什么**：全流式消息(含 ThinkingBlock)要完整翻译渲染、不省略 |
| COPILOT_ASSIST-2 | Copilot Write/Edit 自写例外 | 单元 `copilot-session-persistence`；**为什么**：MVP1 允许 SDK Write/Edit 直接读写 workspace，保留 diff/summary 审阅体验；D12 继续约束 Studio 自有写入，Bash 仍逐条审批 |
| COPILOT_ASSIST-3 | session | 单元 `copilot-session-persistence`；**为什么**：退出再进对话一模一样、session 必须落盘不丢(D8 MUST) |
| COPILOT_ASSIST-4 | SDK 测试 | 单元 `copilot-sdk-test-parity`；**为什么**：copilot test 必须走真实 `ClaudeSDKClient`，不能用 AsyncAnthropic 假路径 |
| COPILOT_ASSIST-6 | 决议归消息记录所有 | 单元 `copilot-session-persistence`；**为什么**：决议存在卡片 `useState` 里,会话落盘存的却是「刚到时的样子」,重挂载即复活成未决议 |
| COPILOT_ASSIST-7 | 挂起消失要分三种结局 | 单元 `copilot-session-persistence`；**为什么**：一个 `approval_not_found` 同时指「已决议」「超时」「会话没了」,前端还断言成 expired |
| COPILOT_ASSIST-9 | 挂起自己过期要落到那张卡上 | 单元 `copilot-session-persistence`；**为什么**：超时只发一条泛型 `error`,说不出是哪一张卡,于是每张卡都继续停在「Waiting for approval.」、按钮照样可点,而背后的任务早已停了 |
| COPILOT_ASSIST-8 | 一次提名的身份是 `(kind, ref)`,由前端给出 | 单元 `copilot-assist` F4；**为什么**：让后端拿显示名反查,等于把「用户挑了哪一个」变成一次模糊匹配,正是 F4 ③ 禁的 |
| COPILOT_ASSIST-10 | 提名在屏幕上/正文里/菜单里各长什么样 | 单元 `copilot-assist` F4；**为什么**：8 只定死了它在线上的形状,没说 pill 在 `user_message` 里留下什么、同一个对象提两次算几次、菜单装不下时怎么说 |
| COPILOT_ASSIST-11 | 一张图怎么进来、多大算太大 | 单元 `copilot-assist` F4；**为什么**：整条消息装在一个 WebSocket 帧里,超过 uvicorn 默认的 16 MiB 不是报错而是连接被掉、消息无声消失 |
| COPILOT_ASSIST-5 | 会话身份契约（2026-08-15 用户裁决） | 单元 `copilot-session-persistence`；**为什么**：每个前端会话标签对应一条**独立的后端 SDK 对话**，会话身份必须显式进契约——此前 New chat 只换前端视图，报文无 session 标识，后端按 skill 只存一条 SDK 对话，生成中新建标签发的消息被注入正在跑的对话（2026-08-15 实测缺陷）。目标契约：① ws 报文必带 `session_id`（前端标签的 session id，缺失即边界拒绝）；② 后端 SDK client 缓存键 = (skill, **session**, model, provider, credential, workspace)，不同标签绝不共享对话；③ 流式事件按**发起查询的会话**归属渲染，与"当前激活标签"无关，切标签不串流；④ 关闭标签经 `POST /api/skills/{skill_id}/copilot/session-close` 结束对应后端 client（每 client 一个 CLI 子进程，不关则漏资源）；⑤ ws 断连仍重置该 skill 全部会话、一条连接内查询仍串行（单活跃查询不变式不变，审批/中断继续按 skill 键） |

## 6. 测试关键点
1. ThinkingBlock: baseline 现状为 `_translate_sdk_message` 丢 ThinkingBlock ⚠️；目标为 thinking/tool call 全量流式，折叠但不省略。
2. Copilot Write/Edit 自写例外: baseline 现状为 SDK `acceptEdits` 直写；目标为 允许直写 workspace，同时回显工具事件与 diff/summary，Bash 仍 human-in-the-loop。
3. session: 现状为 一 skill 多 session 历史持久化，并用 `_window.json` 恢复上次打开的 tab 集合与活跃 tab；空窗口状态合法,首条消息才把临时草稿物化为真实 session。
3a. 会话身份契约: 不同 `session_id` 的两次查询得到两个不同的 SDK client、同 `session_id` 复用同一个；ws 报文缺 `session_id` 被拒；`session-close` 只关掉指定会话的 client；事件落在发起查询的标签，切换激活标签不改变归属。
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
