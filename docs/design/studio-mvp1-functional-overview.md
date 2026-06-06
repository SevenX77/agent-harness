# Studio MVP1 功能总览(派生快照 · 供查漂移)

> **性质**:派生自各模块 `mvp1-alignment.md` 的定义/机制/接口/决策 + `01_workflows/` 走查 + `DESIGN_UNITS_INDEX.md`(2026-06-06 快照)。**SSOT 仍在各模块文档**;本档只作一次性"查漂移"视图,**不作权威、不进锁**。
> **怎么查漂移**:每条概括 = 设计意图的逻辑(做什么+怎么工作+关键规则),核它对不对;⚠️ 代码债见 §6(那是实现 backlog,非设计漂移)。

## 0. 架构框
- **四层**:① 前端 UI(只投影后端)| ② Rust 后端(本地写 D12 / sidecar 拉起)| **③a Studio 应用加工(主战场)** | **③b gateway 公共内核(只引用)**。判据:换个 app 装上 gateway 还原样能用 = ③b 内核。
- **三轴**:① workflow(旅程 7 节点)| ② 能力(14)+ 区域(12)+ 平台(5+i18n)| ③ 设计单元(22,带机器锁)。

## 1. PM 旅程(轴① · 7 节点)
- **00 设置** — 配主旅程的运行前提(凭证 / model group→角色物化 / copilot / 路径)。独立成节点因为 predict 要它把角色解析成真实 route、run 要它的 provider。中心 overlay 不卸载工作区。灵魂="测了就别丢":测试是真实状态唯一写入点、回写后端持久化,前端只消费统一 6 态、绝不自建真值源。
- **01 发现初始化** — IDE/工作区模型(D11):一个 skill = 一个文件夹,Home = 打开文件夹 + MRU,无中心注册表,子图按 path。打开任意文件夹不在门口卡导入校验(D2:有 compile+copilot 能把"屎"修成标准 skill)。返回 Home 卸载工作区,但 copilot 对话要能恢复(D8)。
- **02 编辑** — 把业务逻辑装配成可编译的 graph_skill,三粒度:GRAPH.md 全局契约 / 拓扑连断+子图 / 节点白名单字段+步骤。硬约束:节点类型由文件名决定(SKILL/LOGIC/SUBGRAPH.md)非可变字段。子图按 path 随便放、删了父子图 io 1:1 强绑。
- **03 Compile** — 编译校验、绿灯才解锁 Predict。检查内容(结构/字段/拓扑/IO/@提及)+错误码沿用 engine FROZEN 契约,Studio 只触发+呈现。实时 lint 只就地标红(节点徽标/字段 tooltip/Monaco 行内)不弹全局,详细错误进可复制的 drawer。
- **04 运行验收** — 试飞→真跑→去黑盒→验收四段。**predict**(logic 真跑确定性、agent 按 golden 态选 mock、零真 token、run 硬前提)→**run**(真烧 token、节点灯随真实事件、成功 autocommit)→**trace**(dot=两节点间黑板转移点,点开看那刻黑板+节点间操作)→**golden**(逐节点期望值三态、只改 output schema 缺字段才失效、run 后字段级 diff)。守卫:predict 假数据不能固化成 golden(409)。
- **05 Debug** — run 失败/暂停后**就地节点级续跑**(不重跑上游)。三场景:节点 [Resume](复用上游 checkpoint)、HitL(agent 要人输入→暂停→节点上方悬浮输入框→注入续跑)、篡改 context(改边 dot 黑板 JSON→续跑下游)。脏状态失效:改上游/拓扑/schema 让受影响下游 Resume 自动置灰。前提:先有一次真实 Run 产出 trace+checkpoint。
- **06 保存发布** — 成功 run 自动本地 git autocommit(MVP1 主力安全网,失败不提交);Release(藏 Header/Team 下拉)打 zip 传 Artifact Registry——**明确≠git push**。PM 定"发布占坑低优先";旧的 commit-msg 输入/push/撒花是虚需求已删;前置缺失(身份/registry)一键跳 Settings、不静默失败。

## 2. 能力(轴② · 14 · 跨区域数据流/行为)
- **compile-lint** — 边写边查(800ms 防抖、只就地轻标记不打断书写)+ 手动 Compile(全量错误集中到底部 drawer、只盖画布、一键复制喂 copilot)+ **stage gate**(compile→predict→run 逐级解锁;warning 不挡 predict、只 error 挡)。检查规则+错误码归 engine,Studio 不自创一套。
- **conflict-overwrite** — 统一两类冲突呈现:文件保存冲突(存盘带 expected hash,不一致弹 use-remote/keep-local/diff,**绝不静默覆盖**)+ 数据流顺序覆盖(下游要覆盖上游同 output key 时标红、要用户显式确认)。"允许覆盖"开关挂在消费侧;前端只 opt-in 提醒,数据流合法性的持久权威是引擎 compile。
- **copilot-assist** — 右侧既懂搭 skill 又懂业务的端到端 agent(本身是 Claude SDK 客户端)。全程流式分类折叠(不丢步、不用摘要替代)、一 skill 多 session 且**落盘持久化退出再进一模一样(D8)**、@mention 精确取上下文+发送后回显注入了哪些(反 hidden prompt)、改文件**Cursor 式即时应用 + 内联 diff + checkpoint、Reject 精确还原**(run 用 pending 代码;写盘仍唯一走 Rust/D12)、Bash 逐条审批。
- **debug-resume** — 真实运行失败/暂停的人工干预,核心是节点级续跑(锚在坏节点、复用上游 checkpoint 不重跑)。管脏 checkpoint 失效、HitL 就地悬浮输入、从边 dot 篡改上下文续跑。失败/dot 这些"状态"消费 trace 的"事件→节点态"投影,自己不算。
- **file-editing** — 打开文件→Monaco 编辑→带冲突保护保存(expected hash),并把编辑器壳借给 trace 只读视图 / debug 篡改。本地读写收口到 Rust 唯一写者(D12),HTTP 不再直写本地文件(防双写者并发)。
- **golden-eval** — 每个 **agent 节点**的期望输出(粒度=单节点,非整次 run 快照,这是和现状最大区别)。三态(untested→logic-ok→has-golden)、predict 按状态自动选 mock、**只在改 output schema 致缺字段时失效**(改 prompt/逻辑不失效)、run 后实际输出 vs golden 字段级 diff。golden 是 run 后验收非前置;落 `.workspace/golden/` 不进源码树。
- **graph-authoring** — 宏观/中观图编排(从 GRAPH.md 渲染节点边、建 phase、连断依赖、展开子图)。画布是 GRAPH.md 的可视化编辑器(非第二套 schema),连边建依赖、有环挡且文件不变。子图写死**绝对 path 无注册表(D7)**、默认落 `subgraph/<name>/` 递归自包含、inline 内联展开+下钻并存。父子图不做 io 1:1 校验。
- **phase-editing** — 选中 phase 节点改被允许的字段+正文。节点类型由文件种类定(agent/logic/subgraph)非可变 mode 字段;Properties 按类型只渲染+只保存白名单字段(权威归 engine skill-syntax)。agent 正文 steps/actions(XML)不在 Properties 改、在画布内联子节点拖拽增删改重排。
- **predict** — 编译后/运行前试飞,**run 硬前置**。按节点 i/o 跑图、验 input/output schema、确定性跑 logic、agent 不调真模型按 golden 态选 mock(零真 token)。成功置 predict-pass 解锁 Run。predict 假数据不可提升成 golden(409),但 Run 真实输出可作 golden 默认种子。
- **publish** — 成功 run/golden 后收尾。本地 autocommit(成功才提交,主力安全网)+ 低优先 Artifact Registry(Release 打 zip+元数据上传,对外分发钩子)。**发布≠git push**;砍掉 commit-msg/push/撒花虚需求;打包写盘收口 D12 Rust。
- **run-execution** — predict-pass 后真跑(烧真 token)。POST `/runs` 起进程、WS 事件派生节点灯/边动画/焦点、持久化 final_state/指标/trace、timeline 看历史、批量多输入轮询且单条失败不静默。Run 需 compile+predict 双过解锁;节点态来自 state-engine 投影非画布假态;成功触发的 autocommit 归属 publish。
- **skill-workspace** — 本地工作区进出(像 IDE 非注册表浏览器)。Home"打开文件夹"+MRU,导入不在门口拦校验(进去 repair 态)、新建建脚手架、delete 只"Remove from Studio"**不删磁盘**。子图按绝对 path 随便放,copilot 工作目录必须纳入被引用的子图 path。
- **studio-settings** — 让 predict/run/publish/copilot 能用起来的运行时配置(凭证/model group/抽象角色/copilot 路由)。overlay 基座、非线性旅程一环。统一 **6 态**(ready/historical_ready 曾连通/untested/failed带因/cooling_down/off,取消旧 needs_setup);**6 态投影+materialize+endpoint 标准化归 ③b gateway**,Studio 只渲染消费、只传角色意图。copilot role 测试走真实 SDK smoke。
- **trace-observability** — 让一次图运行可观测(实时 trace 流、跑完 timeline、人类可读 trace 文档、聚焦节点 trace、边 dot 黑板、prompt 检视)。**焦点决定粒度**:空白画布看整次摘要,聚焦节点看该节点所有执行(loop/retry/batch 多次尝试全分组、不塌缩到最新)。"事件→节点态"派生归它语义、实现落共享 state-engine(run/debug 复用同一套)。

## 3. UI 区域(轴② · 12 · 组件结构/状态)
- **assets** — 左侧文件树(真实文件夹、点开即编辑、不重存元数据)+ 管子图成员归属(路径解析不到标红、弹窗选本地文件夹加进工作区,不走注册表)。golden 文件也能从这里打开。
- **canvas** — 中央 React Flow 图工作区(拖拽建删节点连线、落盘触发编译)。三个互不抢位的视觉通道叠在节点:编译警告标志 / 运行圆点灯(数据来自真实 run 经 state-engine 投影,画布只画)/ 节点上方 debug bar(仅 agent 内联子节点可聊天)。agent 内联展开正文 XML 子节点、子图 inline 展开+下钻(**面包屑放左上角不放顶栏**,防本地 app 用户"跳出项目"恐慌)、边 dot 点开看该次真实黑板切片。
- **center-action-bar** — 底部中央 Compile/Predict/Run 三主按钮,**分级门控、每次只突出下一步该点的安全动作**。Compile 失败自动弹可复制错误抽屉(不遮侧栏)。只拥有按钮触发+门控状态,呈现/试飞/运行归各能力。
- **copilot** — 右侧 AI 对话面板(侧边非全屏弹窗):消息/工具 diff 可展开渲染、模型路由选择、WS 状态(断开禁发)。把当前屏幕(选中节点/边/lint)压缩同步给对话(看得懂屏幕又不塞巨 payload)、退出再进一模一样、下钻子图上下文跟着 skillId 走。模型路由消费 Settings;输入框支持拖/粘贴图片(vision 模型);是 golden 分析 bar 入口。
- **editor** — Monaco 文件+虚拟文档编辑(自动保存+expected hash 防冲突覆盖),旁留紧凑图视图+可拖拽分隔条。承载编译行内标记 / 只读格式化 trace 文档(具名 tab 与在编文件并列、不顶替)/ debug 篡改 JSON / golden 分屏 diff(实际输出 vs golden)。这些能力它都不是 owner、只借壳。
- **input** — 可见名"I/O"面板,管节点/run 的输入输出两侧配置(导入选输入、推断/编辑 schema、predict/run 前按 schema 校验、配 artifact 路径)。选中输入=predict/run 真正发出的 payload、多选做批量。是 golden 主入口之一(output 区+Assets);golden 摘要/diff 归 I/O 不归 Properties。
- **local-history** — 左侧本地历史面板,MVP 安全网只做 git 快照(成功 run 自动 auto_run 快照+手动快照、选中 revert 回 sha)。负向边界:RunDetailDrawer/BatchSummary 属"运行/时间"语义、归 timeline/I/O 不归这。
- **properties** — 右侧属性面板,选中节点按字段白名单显示可编辑 phase 配置,role 那行带 Test 键直接测该角色 + trace inspector 落点。明确决策:**golden 完全不在 Properties**。
- **settings** — 设置区四 tab(General 身份/路径 · API Keys provider 凭证+测端点+拉模型 · LLM Roles 角色→model group+fallback 链 · Copilot 路由+真实 SDK 测试)。关键="单一权威状态投影":统一规范 6 态(界面不本地猜真相、去掉 needs_setup)。是配置中心:predict/run/copilot 复用这里物化的路由、不各存一份。
- **shell-layout** — 常驻 IDE 外壳(Header/Toolbar/可调面板槽/中央路由/copilot 槽/Settings overlay)。**Studio 是常驻 app 非落地页**:中央区切换时外壳稳定,sidecar 没就绪外壳先渲染、错误局部不全屏阻塞。Header 极简(Home/Team/Copilot 开关)、子图面包屑在画布左上角、Settings 做中央 overlay——都为防"跳出项目没保存"恐慌。Toolbar 只切左侧面板且保留选中。
- **timeline** — 时间轴运行检查面板(列每次 predict/run 的状态/耗时/token,predict 行只用 icon 区分)。点 Run 自动开 trace 流式追加(重连不重复)、可开完整时间轴+编辑器里格式化只读 trace 文档+Prompt Inspector(模板/变量/渲染三视图)、顶部 tab 切模型对比。批量 golden 入口不在这(在 copilot bar)。
- **welcome** — 首页(开始/切换本地工作区,对齐 IDE"打开文件夹"非营销页)。最近用过的 skill 卡片网格(只靠 MRU、**不依赖后端 /skills 注册表**)、Open folder 不硬拒非标准文件夹(进去引导修复)、选父目录新建 skill、卡片可 reveal 或"Remove from Studio"(只摘列表不删盘)。

## 4. 平台基础设施(轴② · 5 + i18n)
- **native-fs**(Rust/Tauri) — 本地工作区所有者:目录选择/读写/MRU/reveal/watch + runs/golden/artifacts 布局 + Python 边车生命周期(启动拉起 engine/gateway、传 token、等健康、退出关掉)。铁律 **D12**:所有本地写(skill 源/`.workspace`/golden/产物/copilot 改盘/编辑器保存)唯一经 Rust,前端和 Python 都不直接写盘——杜绝双写者并发冲突。D10:边车失败只局部报错+骨架屏,不全屏 bootstrap 阻塞。
- **engine**(Python 边车) — 图引擎计算后端:编译校验 / predict 试飞 / run 真跑(落 final_state/指标/trace/checkpoint/产物)/ 发细粒度运行事件。是**格式、错误码、机制的唯一权威**(SSOT 在 engine 自己文档),Studio 只触发+呈现、绝不自建并行编译器或重定义格式。predict 是 run 硬前提、golden 只影响 mock 源;逐节点 golden 对比 + 节点级 resume 难点归 engine。
- **gateway**(Python 边车) — 让模型能被调起来的路由基础设施:provider/route 描述符、能力匹配、抽象角色→真实 route 解析、fallback 链、运行期健康/熔断、引擎要的模型适配器。**核心边界**:provider 注册表 / 6 态健康投影 / materialize(角色意图→可执行平铺兜底链)/ endpoint 标准化 / fallback/探测 = 公共内核归 gateway,Studio 只消费算好的投影、把颜色文案拖拽排序留自己(判据=换个 app 能否复用)。copilot 只把 `copilot_chat` 当角色解析出 route、不感知 SDK 会话。
- **llm-copilot-http-api**(Python ③a) — Studio 后端暴露给前端的 LLM/Copilot HTTP/WS 接口面(③a 适配壳):把 HTTP 翻译成对 gateway/凭证/探测/角色/copilot 的调用再投影成前端 DTO(api_key 一律脱敏)。端点家族:registry CRUD / endpoint·model·role test / import draft / model profile / copilot ws+test。边界:底下能力内核(base_url 归一化/capability/探测/materialize/6 态/draft/endpoint 拆分)属 ③b、应下沉 gateway,本层只链接不复制第二份真理。例外:copilot ws/test-sdk 绑死 SDK 调用归 Studio,且测试必须走真实 `ClaudeSDKClient`。
- **state-engine**(前端) — 前端状态协调:工作区 UI 状态(面板/选中/打开文件/导航栈)+ WS/事件桥 + 阶段门控 + **事件→节点态投影**(run/debug 共用一份派生器把流式事件转成节点灯)+ settings 刷新 + copilot store。WS 桥按 run_id/skill_id 分作用域防切工作区串台;切 skill 清旧状态。克制:MVP1 状态量不够大、不上 Redux,只 hooks+文档化契约(YAGNI)。
- **i18n**(前端主导) — 全栈多语言**单一架构权威**(定架构非文案):后端只产机器 error_code + 结构化 details,前端一套 react-i18next 把 UI 文案+错误码翻成当前语言(Strategy C 前端单权威);引擎/网关保持语言无关零改。例外:copilot 系统提示后端构造、前端看不到→后端维护中英两版按 locale 选。默认 en + 首发 zh-CN;后端中文残留(尤其 copilot.py 整个系统提示+约 8 条用户可见错误)改回英文源。

## 5. 横切设计单元(轴③ · 22 · 机器锁态)
> `owned-lock` 全 22=locked(studio 自有切面已审+冻结);`integration-lock` 只 12 个 locked,10 个踩在 engine/gateway 还在 drafted 的契约上 = `unverified`(诚实,不假信心)。

**12 端到端 locked(纯 studio)**:compile-stage-gate · compile-lint-structured-error(compile-lint)· conflict-overwrite-resolution · io-panel-artifacts-test-inputs(input)· node-properties-role-test(studio-settings)· publish-artifact-autocommit(publish)· local-history-snapshot · native-rust-writer(native-fs)· workspace-open-folder-mru(skill-workspace)· shell-runtime-gate(shell-layout)· copilot-session-persistence(copilot/copilot-assist)· i18n-error-code-ui-copy(i18n)。

**10 unverified(自有锁了、外部契约还在动)**:

| 单元 | studio owner | 外部依赖(引,floating-draft) |
|---|---|---|
| subgraph-path-inline-drilldown | canvas/graph-authoring/assets | engine resolver/skill-syntax/physical-layout |
| predict-execution | predict | engine seam/models |
| run-execution-node-status | run-execution/state-engine | engine iterate/observability |
| golden-per-agent-node | golden-eval | engine physical-layout/golden-eval |
| phase-field-whitelist | phase-editing | engine skill-syntax |
| debug-resume-checkpoint | debug-resume | engine checkpoint |
| trace-dot-blackboard | trace-observability | engine observability |
| settings-six-state-provider-health | gateway/llm-copilot-http-api | graph-agent-gateway 6 态投影 |
| model-group-role-materialization | gateway/llm-copilot-http-api | graph-agent-gateway materialize |
| copilot-sdk-test-parity | copilot-assist/gateway/llm-copilot-http-api | graph-agent-gateway copilot route |

## 6. 全局已知漂移(⚠️ = 实现 backlog,非设计漂移)
D12 Rust 写者未收口(file-editing/publish/editor/native-fs 仍走 FastAPI/Python)· 6 态仍旧 5 态/needs_setup(gateway/settings/studio-settings)· predict/run 前端是桩(center-action-bar handler console.info)· trace 未挂主流(TracePanel/useRunStream/RunDetailDrawer 建了未挂、edge dot 假黑板)· canvas node status/inline subgraph mock · debug resume 501 · golden per-node 未落(仍复制整次 final_state)· 巨型 routers/llm.py(materialize/draft/6态该下沉 ③b)· copilot session 内存态/ThinkingBlock 未翻译/SDK test 假路径 · skill-workspace IDE-folder 未落(仍读 /skills 注册表)· state 分散无单一 bridge · i18n 仅英文 catalog。

## 7. 拍死的设计决策(锁,改动须 owner+exemption)
- **3 节点拆分**(03 compile / 04 predict+run+trace+golden / 05 debug),golden 跟 run 走(04)。(PM 2026-06-03)
- **native-fs Rust 唯一写者(D12)**;sidecar Rust eager-spawn,**RuntimeGate 退役(D10)**。(2026-06-01)
- **gateway ③b 公共内核**(6态/materialize/endpoint 标准化/canonical id/draft/探测/熔断),studio 只引不复制。
- **settings 6 态标准投影**锁。(2026-06-05)
- **publish = 占坑低优先**(autocommit + 最小 Artifact Registry;commit-msg/confetti/独立按钮删;团队协作/鉴权占坑未来)。(PM 2026-06-04)
- **i18n 前端单权威**(react-i18next;后端只产 error_code)。(2026-06-03)
- **skill-workspace IDE-folder 模型**(无注册表,子图按 path,owner=engine)。(D11/D2)
- **engine 契约引 `docs/engine/mvp1/` SSOT**(子图 path/golden 落点/skill 语法/错误码/resolver/checkpoint),不在 studio 复制。

---
**SSOT 索引**:旅程 `01_workflows/`;能力/区域/平台 各 `*/mvp1-alignment.md`;横切单元锁 `DESIGN_UNITS_INDEX.md` + `_design-unit-lock-snapshot.json`;决策 `docs/design/studio-mvp1-lock-semantics-decision.md`。
