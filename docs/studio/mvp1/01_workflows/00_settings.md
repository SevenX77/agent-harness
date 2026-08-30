---
role: summary
authority: ./00_settings-ux-spec.md
---

# Node 0: 设置与配置 (Settings & Configuration)

> Tier: workflow · 能力 `studio-settings` · 区域 `settings` · 平台 `gateway`(Python sidecar)
> 设计源(最新权威): 本页 workflow 走查 + [`00_settings-ux-spec.md`](./00_settings-ux-spec.md)(PM 口述权威) + gateway 模块设计 [`docs/graph-agent-gateway/mvp1/`](../../../graph-agent-gateway/mvp1/) + 锁定决策 D8 / D10 / §11 / G3。(`.kiro/specs/studio-*` 仅历史参考,**不作 SSOT**。)
> 角色: **运行底座** —— 被 predict / run / publish / copilot 硬依赖的前置配置节点,不串在主旅程里,而是托住主旅程。

## 1. 业务目标

01–06 是"做一个 skill"的主旅程,但它们集体悬在一个隐含前提上:**LLM 得能跑**。Predict 要把抽象角色解析成真实 route 才能试飞,Run 要真实消耗 provider,Publish 要知道 Gitea 主机与产物落盘路径,Copilot 要有自己的模型与密钥。这些"跑起来的前提"既不属于画布、也不属于编辑器,而是一处独立的配置面 —— 这就是 00_settings。

它承载 PM 的五条常驻配置旅程:**Provider 凭证(API Keys)/ 抽象角色到模型的映射(LLM Roles)/ 助手配置(Copilot)/ 身份与产物路径(General)/ 媒体生成(Media Generation)**。第五条的设计单独立在 [`02_capabilities/media-generation/design-decision.md`](../02_capabilities/media-generation/design-decision.md)(2026-08-13 立项),本节点只登记它是 Settings 的一页,细则不在此重述。这五条之外还有一条**一次性的前置征询**——首次打开 Studio 时的社区共享征询对话框(§3.0),它只在从未回答过时出现一次,答案由 General 页(§3.1)里的常驻开关承接后续变更。这个节点的产物不是某个 skill,而是让其余所有节点"能调模型、能上线"的运行底座。因此它在逻辑上先于 01–06 的任何 LLM 动作,是被 predict / run / publish / copilot 硬依赖的前置节点。

## 2. 核心范式

### 2.1 配置面,而非退出工作区
打开 Settings 是中心覆盖层(center overlay)盖住中心视图,**不卸载当前 skill workspace** —— skill 态、copilot、面板、分屏全部保留,关掉覆盖层即回到原工作区。这区别于 Header 的 `[ ← Back to Home ]`(那会卸载工作区)。PM 可以在装配 / 试飞途中随手进设置改个 key,回来继续,不丢上下文。

### 2.2 后端是唯一真相源,前端只投影
Settings 看起来是"前端表单",但它的真相全在后端:一个 provider 能不能用,不是一个布尔字段,而是 **endpoint 状态 + route 状态 + 密钥是否存在 + 运行期熔断**四者的组合,这些事实都在 gateway 后端(凭证文件 + SQLite health store)。因此 Settings 的铁律是:**前端不自建并行真值源,只消费后端投影**。测试一个 provider / model 的结果必须回写后端,UI 从后端读回 —— 切 tab、重启 app 都不丢。(现状落差见 §4。)

### 2.3 启动期就绪,但不全屏 gate
因为 settings 的 API key / LLM role 配置需要服务端解析(未来还要承载登录),gateway sidecar 在 app 启动期就由 Rust 即刻拉起,而非等到第一次打开 Settings 才懒加载。但这**不是全屏 bootstrap gate**:外壳、文件树、编辑器(Rust 本地)立即可用;Settings 这种依赖 sidecar 的面用骨架屏(skeleton)+ 懒加载 + 全局"后端就绪"指示来兜 —— available models 那条巨长列表是骨架屏的头号场景。

### 2.4 数据层永不 Rust 化
横切铁律 D12 是"本地写全量走 Rust",但它管的是 **skill 源文件**(GRAPH.md / SKILL.md / `.workspace`)。Settings 的凭证与角色数据(`~/.studio/` 下的 credentials / roles)是 **gateway 拥有的服务端数据,永不 Rust 化** —— 读写一律走 gateway Python(经 storage seam 抽象、预留 `user_id`,为未来远端服务化对齐形状)。本节点唯一的本地 OS 操作,是"选默认 skills 目录"的文件夹选择器(native / Rust)。

## 3. 首次征询与五条配置旅程

> 📋 **每步操作 / 反馈 / 动机的细粒度 UX 规格**（含 draft 赋能写回、model/endpoint 标签表现、测试落点：endpoint 验证在 API key 页、model 保证在 role 页）见 [`00_settings-ux-spec.md`](./00_settings-ux-spec.md)（PM 2026-06-02 口述，权威）。

### 3.0 首次征询 — 社区共享(前置一次性 gate)

Studio 每验证一次 provider,就沉淀一条"哪个公开服务的哪个模型答得通、支持哪些能力"的探测证据。这份证据可以和社区互换:分享出去就能换回别人已经验通的参数,免去自己逐个探测。是否参与这次交换,交给用户在**首次打开 Studio**、进入首屏(Welcome/Home,尚未选中任何 skill,`apps/studio/frontend/src/components/welcome/WelcomePage.tsx`)时回答一次;答完之后 General 页(§3.1)里的常驻开关承接后续变更,对话框不会再弹出。

**真相字段是三态,不是布尔**:`AppSettings.community_sharing_choice ∈ {"unset", "shared", "declined"}`(后端 `apps/studio/backend/app/models/settings.py`;前端镜像同名 `CommunitySharingChoice`,`apps/studio/frontend/src/api/types.ts`)。旧字段是布尔 `remote_model_catalog_enabled`,表达不出"从没问过"与"问过而用户主动拒绝"这两种状态的区别——而首屏要不要弹窗、上传要不要放行,恰恰只取决于这一区分。这是"让非法状态不可表示"原则(仓规 Coding Standards)在这个字段上的直接应用:三态把"未决"设成第三个显式值,而不是让调用方拿一个布尔的默认值去猜测"没改过"到底是"同意"还是"还没问"。

**门控规则(同一条规则,统一适用于自动回传与手动读取)**:
- **回传(contribute,含探测后自动回传)要求 `"shared"`**——`"unset"`(没问过)与 `"declined"`(问过拒绝)一律不许上传。默认上传等于替用户做了同意声明,这正是 2026-08-23 坐实的缺陷:旧字段 `remote_model_catalog_enabled` 默认 `True` 且从未征询用户,运行时活动日志里已有 101 条 `autoshare_uploaded` 记录为证。唯一实现在 `apps/studio/backend/app/routers/llm.py` 的 `_autoshare_after_probe_best_effort`。
- **读取(read)只在 `"declined"` 时停**——`"unset"` 仍允许读取。理由:读取不带走这台机器上的任何东西,而"能直接用上社区已验通的参数"正是对话框承诺的好处,首屏就把它关掉只会让第一次体验更差,却换不来任何隐私收益。唯一实现在 `apps/studio/backend/app/services/community_catalog_runtime.py` 的 `sync_verified_community_catalog_into_credentials`(应用面覆盖启动期自动同步与 `POST /api/llm/catalog/sync-verified` 手动同步——两处调用点共用同一个函数,门控只需改一处)。

**对话框交互**:复用 `@/components/ui/dialog`(本仓 shadcn 封装,组件 `apps/studio/frontend/src/components/welcome/CommunitySharingConsentDialog.tsx`)。两个按钮——"开启共享"写 `"shared"`,"暂不开启"写 `"declined"`——都是合法的最终答案,因此**没有第三种关闭方式**:不给右上角 X(`showCloseButton={false}`)、不允许点遮罩或按 Escape 关闭。写法沿用本仓已有的必答弹窗惯例(`ConflictDialog`):`<Dialog open={...}>` 不传 `onOpenChange`,Radix Dialog 在这种受控模式下内部的 Escape/outside-dismiss 处理器没有回调可调,因此不生效。答完之后 `community_sharing_choice` 离开 `"unset"`,对话框的开启条件(`choice === "unset" && !isLoading`)恒为假,永不再弹;`isLoading` 那一半防止设置仍在加载时,乐观的默认快照(也读作 `"unset"`)让对话框对一个早已回答过的用户一闪而现。

**答后确认(2026-08-29 补,J-01.J)**:两个按钮都立即冲刷防抖保存(`useAppSettings.save()`),并在**保存真正落盘之后**弹一条 `toast.success` 确认——"开启共享"确认已开启,"暂不开启"确认保持关闭并指路 General 页开关。确认以保存结果为准,不以点击为准:`save()` 失败时解析为 `null`,此时**不弹成功确认**(失败提示由 autosave 自己的错误 toast 负责,成功与失败不许同屏各说各话)。理由:这是全应用唯一一个"回答即落盘的持久选择",探测/编译/保存全都有结果反馈,唯独它没有,用户答完无从知道选择是否生效(J-01.J,PROBLEM_LEDGER.md)。

**界面陈述必须与实际行为一致**:API Keys 页曾经用 `ProbeCatalogSharingSummary`(旧 `apps/studio/backend/app/models/llm_config.py`)硬编码"Local only"徽章与"MVP1 does not auto-upload"文案——`mode`/`auto_upload_enabled`/`message` 都是常量默认值,router 里没有任何覆盖点会去改写它们,却与同一进程里 `_autoshare_after_probe_best_effort` 的真实上传行为直接矛盾。修复时这个模型被整体删除而不是修补(仓规"不留一份并行真值"):唯一真相收敛回 `community_sharing_choice`,前端 API Keys 页与 General 页的开关对同一个状态给出一致陈述,后端不再维护第二份需要手动保持同步的投影。

### 3.1 General — 身份与产物路径
最朴素的一条:User ID、Gitea 主机、**默认 skills 目录**。前两者是身份 / 可选远端坐标(**注意:publish 走 Artifact Registry zip 上传、非 git push**,见 [`06_eval`](./06_eval.md);Gitea 主机不是 publish 机制),后者决定 Home"新建 skill"时的默认落点。交互是即填即存(debounce auto-save,无 Save 按钮);"选目录"唤起 OS 文件夹选择器,"重置"回落到计算出的默认值。

除了这三个字段,General 页还持有**社区共享开关**:读写同一个 `community_sharing_choice`,开=写入 `"shared"`、关=写入 `"declined"`——它**永远不会**把值改回 `"unset"`(那个值只有"从未回答过首次征询"这一个含义,一个已经回答过的用户不能靠拨动这个开关"退回未回答"这个假状态)。它是 §3.0 首次征询对话框答案的常驻承接点,门控规则、三态理由的完整说明见 §3.0。

### 3.2 API Keys — Provider 凭证
配 provider 让模型能连通,分两区:**official**(固定 5 厂商 anthropic/openai/gemini/deepseek/ark,只填 key)与 **third-party**(用户自增:填 URL + key,protocol 系统自动探)。
- **一个 provider = 一把 key + 多个 URL**:每个 `(URL × 探通协议)` 拆成一个**平铺 endpoint**(前端拆好告诉后端、后端不感知"卡";同 key 共享 credential + 一个限流 bucket;一 URL 通两协议则两个都建)。
- **验 endpoint = 批量模型探测**:official 与 third-party **在「必须真打一次生成」上对称**——`get-models` 只证 URL+key 可达,不证能生成、也不证协议匹配,所以两类都要生成探测过了才判 verified;差别只剩 official **不做协议轮换**(协议固定)且候选**过滤为语言模型**。(**修订 2026-07-01**,原「official 只 `get-models` 即验通」作废。推翻它的实证:Anthropic 账户欠费时 `GET /models` 照常 200,而所有生成调用被 `HTTP 400 "credit balance is too low"` 拒绝,于是 role 页全红、API keys 页全绿,两页真相矛盾。权威原文与完整修订记录见 [`00_settings-ux-spec.md`](./00_settings-ux-spec.md) §1.1;实现 `apps/studio/backend/app/routers/llm.py` 的 `_verify_endpoint_by_generation_probe`。)**分批探(每批 ~3)、命中即停 / 全失败判死、结构错短路**——单模型会瞬时抖动,不能凭一个定生死。
- **状态 6 态 + draft 赋能**:测试结果(含失败)落 draft 沉淀历史;模型 / endpoint 标签用统一 route 级 6 态(🔵 蓝=以前联通过)。
- **锁定约束**:`base_url` 按 protocol 归一化;`api_key` 服务端明文存(0600)、`GET registry` redact、专用 secret 端点取明文;数据走 gateway(永不 Rust)。
> 细粒度 UX(official/third-party 分步、协议探测的错误码短路、批量探测、draft 赋能/写回、命名防撞、前端 UI / 前端业务逻辑 / 后端 gateway 接口的层次分离)见权威 [`00_settings-ux-spec.md`](./00_settings-ux-spec.md)。

### 3.3 LLM Roles — 抽象角色到模型的映射
这是 settings 最重的一条,也是 predict / run 的命脉:把抽象角色(analyst 等 graph-agent 角色)映射到"用哪些模型、按什么顺序兜底"。

> 📋 **细粒度 UX(原子动作 + 测试关键点)见权威 [`00_settings-ux-spec.md` §2](./00_settings-ux-spec.md)。** 以下为高层要点。

- **以 Model Group 为单位,而非裸 route**:左侧角色卡展示该角色的 Model Group 兜底链;右侧可用模型按 Model Group 卡片(扁平,不暴露 `route_id` / `canonical_id` / `endpoint_id`,只给 `display_name`;**model family 可整体折叠**)。拖一个 Model Group 进角色,自动挑 Ready + Untested + 🔵 蓝(以前联通过)的 provider、排除 `failed` / Off(**旧 Needs Setup 已并入 `failed`**)。
- **存储结构化、执行平铺**:角色存 `model_groups[]`,后端物化(materialize)成 gateway 平铺 `fallback_chain`。前端作者看 Group,引擎跑链。
- **role → route 是一等编排 API**:gateway 把"角色名 → route[]"作为一等输出(`ResolvedRoute` 是编排 ↔ 调用唯一交接物)。provider 可用性标签 = 这条链上每个 route 的 UI state 投影。
- **状态体系 6 态 + 弃用区**:provider 行用统一 6 态色(`ready`/`historical_ready`🔵/`untested`/`failed`/`cooling_down`/`off`;🔵 蓝=以前联通过/draft 回填)。单模型失败**两分类**——`failed`(红、**不挡**进可用、仍可选)vs `disabled`(弃用→灰、入可折叠弃用区、re-probe 再通可**捞回**);**配置缺口**(缺 key/base_url/protocol/model)并入 `failed`(`reason=missing_config`)、引导去 API Keys 修(**旧 `needs_setup` 已取消**)。
- **角色测试 = 批量探 + 回写 draft**:对 role 内**所有模型批量真 probe**,结果(含失败)回写 draft;后端 SSOT,删前端易失态。
- **Model Bundle 与 Role 统一**:bundle 复用 role 的录入/测试/改名删除(Add 按钮同位);**拖进角色 = 引用同步**(改束→引用角色跟着变,非快照)。
- **lint 只警示、不选型**:gateway 异常分类(401/402/403/404 + 400-capability → fallback)是运行期流量安全过滤,**不驱动**编排期选型;测试失败不挡拖拽,真正拦截在运行期 admission。
- **跨页**:role 状态 + 快捷 Test 投影进**节点 Properties 面板**(不必切 settings);run 的**模型对比测试**复用 model-group/bundle → 临时 role(见 run region)。

### 3.4 Copilot — 助手配置
Copilot 用与 LLM Roles 同构的角色模型(`role_kind=copilot`),但运行时独立:copilot 拿到解析好的 route 后,自己用 `claude_agent_sdk`(spawn claude CLI、base_url 写进 `ANTHROPIC_BASE_URL` env)调用,而非 graph-agent 的原生 ChatX。密钥经 CredentialProvider 运行期取。

> 📋 **细粒度见权威 [`00_settings-ux-spec.md` §3](./00_settings-ux-spec.md)。** PM 已拍「copilot 必须全功能、不延后」→ 现状桩/mock/假测试一律是**接线工程**,非可接受限制。

- **限单 model group**(不像 graph role 多组/bundle);选组器**可搜索**。
- **测试 = 真实 SDK 调用**(`ClaudeSDKClient`),与运行同路 → **本不该有假测试**。
- **内置角色动态浮出**:默认浮出 Claude(优先 opus4.8→退 4.7)+ DeepSeek(优先 V4Pro→退 V3.2Pro)在 available 里最新最好的;eligible 判据 = 后端 anthropic-messages 兼容,**未测不预过滤**(keep them in there)。
- **「Backend Integration」slot → 统一 save-status badge**(四页共用、接真 `saveStatus`)。

> **接线已完成(核验 2026-08-23,逐条对着 `main` 的代码)**:曾经记在这里的四项缺口都不再成立——① 测试走真实 SDK,`apps/studio/backend/app/routers/llm.py:1727` 写着「copilot 的 test 走 copilot 自己的真实 `ClaudeSDKClient` 调用」,`:2052` 是逐 route 的真工具调用测试,`AsyncAnthropic` 在 studio 后端已无任何引用;② mock 驱动已删,`mock-copilot-data` 在前端非测试代码里搜不到;③ `saveStatus` 已接,`CopilotTab.tsx:522` 与 `:752` 渲染 `SaveStatusBadge`;④ `copilot_` 前缀分流已修,`copilot-role-derivation.ts:377` 由 `copilotRoleNameForGroup` 统一产出 `copilot_<slug>`。**留作复核**:当年同段提到的「占位按钮」这一项本轮未逐个复核。
> **session 持久化(D8)** 属 copilot 聊天(skill 工作台 region),settings §3 只配模型,失败退路见 §5。

## 4. 测试 → 持久化 → 投影(贯穿四旅程的核心机制)

四条旅程共享同一套"测了就别再丢"的机制,这是 settings 的灵魂:

1. **探测**:endpoint 测试 / route probe / role 测试 是真实测试状态的唯一写入点。
2. **持久化**:endpoint 成功 / 失败 / 空 key 写 endpoint 状态 + 时间戳 + 消息;route 确定成功写 `verified` + capabilities,确定失败写 `failed` + 原因码,**临时**网络 / 限流 / 超时写运行期熔断(cooling_down)而**不**永久打 failed —— 临时问题会过期,用 `retry_at` 表达"暂时别用"。熔断事实落 SQLite。
3. **投影**:前端 registry 行与角色物化都调同一个后端投影函数,把"endpoint 状态 + route 状态 + 密钥存在性 + 熔断 + draft 历史证据"合成 **6 个 UI state 之一**(canonical 见 [`00_settings-ux-spec §4.2`](./00_settings-ux-spec.md);**已取消旧 `needs_setup`**):
   - **`ready`**(🟢) — endpoint 与 route 都 verified,唯一绿灯。
   - **`historical_ready`**(🔵 蓝) — 历史连通过(draft 回填),当前未真测 verified —— 介于"没测"与 verified 之间。
   - **`untested`**(⚪) — 没测。
   - **`failed`**(🔴,带 `reason`) — **统一**「配置缺口(缺 key/base_url/protocol/model,`reason=missing_config`)」与「真测试失败(`reason=endpoint_unreachable`/`model_failed`)」;**红、不挡进可用**(仍可选)。
   - **`cooling_down`**(⚪+倒计时) — 有未过期熔断(网络/限流/超时),展示 `retry_at`,不当永久失败。
   - **`off`** — 被用户 / 配置主动禁用,优先级最高。
   > 投影优先级:`off > failed > cooling_down > ready > historical_ready > untested`。**这套六态已在代码里落地(核验 2026-08-23)**:权威定义在 gateway `packages/graph-agent-gateway/src/graph_agent_gateway/registry/schema.py:32` —— `ProviderUiState = Literal["ready","historical_ready","untested","failed","cooling_down","off"]`,旧 `needs_setup` 已不存在;`registry/projection.py:30-36` 把「`reason_code` 当且仅当 `ui_state == "failed"` 时存在」编成校验,让非法组合不可表示。studio 侧的 `app/services/llm_state_projection.py` 已收缩为对 gateway adapter 的薄委托,不再自带一份态定义。
4. **复用**:角色物化时跳过 `failed` / `off`、对 `cooling_down` 记警告、只把 fit 的 route 放进兜底链 —— UI 看到的测试态,与引擎实际编排用的是同一套判断。

> **现状落差(头号 gap)**:后端持久化(endpoint / route 状态 + SQLite 熔断 + 投影函数)已具雏形,但前端仍残留**易失副本**(provider 测试结果、role 测试态存内存,刷新即丢)。目标是删掉前端这层易失覆盖,完全以后端 SSOT 投影为准。这是 settings 接线的主工程。

## 5. 失败退路

- **sidecar 未就绪(启动期)**:Settings 面用骨架屏 + 全局"后端就绪"指示;gateway 起不来在该面内报错,而非全屏失败(壳 / FS 仍可用)。
- **sidecar 运行中掉线(运行期,2026-08-24 补,dead-sidecar-says-so)**:上一条只覆盖"启动就没起来";sidecar 在 app 已经就绪之后自己死掉(进程崩溃 / 被杀)是另一半失败退路,过去没有任何代码路径覆盖它——探测只在挂载那一刻和用户按 Retry 时跑一次(`RuntimeGate.tsx` 的探测 `useEffect` 依赖数组是 `[attempt]`),运行中死掉不会触发重新探测,界面停在最后一次"就绪"的画面,没有任何提示,`error` 态才渲染的 Retry 按钮也因此不出现(实测:杀掉进程后 9 秒界面零提示)。修复分四层:
  - **活性可观测**:复用两个已有的推送信号,不新增定时轮询器——呼应 §2 的 SSOT 精神(AGENTS.md 的「事件驱动 revalidation」条约束的是重取**真相数据**;活性不是真相数据,但两个信号本来就会触发,没有理由再加一条心跳)。信号一是共享 WebSocket 事件流的 `connectionLost`(`useStudioEventStream`,已有阈值:连续 3 次重连失败或累计 10 秒无连接);信号二是任一 HTTP 调用拿不到响应(`BACKEND_UNAVAILABLE_HTTP_EVENT`,`apps/studio/frontend/src/api/client.ts` 的 axios 响应拦截器在归类为"后端不可达"时派发)。两者在 `apps/studio/frontend/src/hooks/useBackendDownSignal.ts` 汇合成一次性的"掉线"边沿触发,直到显式重新启用才会再次触发。
  - **有界自动重启**:最多 3 次,退避 1s / 4s / 16s,总窗口 2 分钟;到限即停,不再自动重试,直到人工 Retry 重新打开一轮预算。前端按此时序调度(`apps/studio/frontend/src/components/runtime-gate-auto-restart.ts`),Rust 侧 `SidecarSupervisor::restart_automatic`(`apps/studio/tauri/src/sidecar.rs`)独立地对次数与窗口做第二次强制约束——两层都拦是因为"限流"这件事该长在被监督对象自己身上、不该只靠调用者自觉,这一点借鉴 systemd 的 `StartLimitBurst`/`StartLimitIntervalSec` 与 Erlang/OTP 的 `max_restarts`/`max_seconds`。这不是该文件旧注释里明确拒绝过的 `Restart=always`:旧注释反对的是"自动重试会埋掉永久性失败",而有界策略到限就停在一个可见终态、错误原文原样保留——`Restart=always` 才是那个会把错误埋掉的东西。
  - **人工 Retry 永远优先、永不被自动预算挡住**:人工按下的 Retry 调用 `restartSidecar`(Rust 命令 `restart_sidecar`),自动重试调用另一条独立的 `restartSidecarAutomatic`(Rust 命令 `restart_sidecar_automatic`)。两条命令分离,是为了让"自动重启预算耗尽"只挡自动重试、绝不挡人工重试——按钮既然显示在屏幕上就必须真的做点什么,一次人工点击被静默拒绝,比修复前"零提示"的原始缺陷更糟。人工 Retry 同时重置自动预算,让下一轮自动重启重新拥有满额度。
  - **到限之后的常驻失败态,外壳绝不因此关闭**:横幅(`RuntimeShell`)不自动消失,带最后一次尝试的错误原文和一个可用的 Retry 按钮;依赖 sidecar 的功能面带原因置灰而非无声的灰按钮——画布的 Compile / Predict / Run / Pause / Resume / Stop(`center-action-bar.tsx` 的 `backendReachable` 属性)与本节点 §3.2 的 API Keys 测试按钮(既有的 `backendReachable` 投影,`SettingsPage.tsx`)共享同一条"后端可达"信号。呼应 §2.3:壳、文件树、Rust 本地编辑器全程可用,这与 AGENTS.md「Rust native-fs 层是 skill 文件在磁盘上的唯一写入方」互相印证——关掉 app 会连带毁掉与 sidecar 无关的工作(包括未保存的编辑器缓冲),没有必要为一个可恢复的子系统故障支付这个代价。
- **测试失败**:返回结构化原因码(invalid_key / rate_limited / quota_exceeded / network_error / timeout / missing_key),UI 据此给可读诊断 + 对应 state,而非笼统报错;临时类失败走 cooling_down 等待重试。
- **密钥泄漏防护**:redact + secret 端点 + 前端不 log / 不 toast / 不持久化明文。
- **Copilot session 持久化失败(D8 MUST 配套)**:copilot 对话与 session 必须落盘且重进恢复一模一样;**写盘 / 读回失败必须显式告警,绝不静默吞** —— 静默吞 = 对话丢失,违"零容忍静默失败"铁律。此失败退路是 D8 的配套待建动作。
- **首次征询对话框的答案保存失败(§3.0)**:两个按钮点击后走的是与 General 页开关相同的 `useAppSettings` debounced autosave 路径,PUT 失败时沿用该路径既有的 `toast.error` 提示。刻意**不**在本地乐观地假装"已经问过"——对话框是否再次出现只看服务端持久化的 `community_sharing_choice`,如果这次保存最终没有落盘,该字段仍读作 `"unset"`,下次打开 Studio 会再弹一次,而不是悄悄记成"已答复"。宁可多问一次,也不在没拿到真实、已落盘的同意时假装拿到了。

## 6. 平台依赖与下游流转

- **平台**:本节点的数据面全部由 `gateway`(Python sidecar)提供 —— provider / role / credential / model 解析 + copilot chat facade;经 storage seam 抽象、预留 `user_id`。OS 文件夹选择器走 native(Rust)。
- **下游硬依赖**:
  - **[04 运行与验收(predict/run)](./04_run-and-verify.md)**:role 必须先在此配好并解析成 route,predict / run 才能调模型。
  - **[06_eval](./06_eval.md)(publish)**:Publish 推 Gitea 要 General 的 Gitea 主机;产物落盘路径(artifacts 默认落 `.workspace/artifacts`,见 G3 / FROZEN-2 改动)与 General 的目录配置相关。
  - **Copilot(贯穿全程)**:右侧 copilot 自始至终依赖 copilot 角色 + 密钥配置。
- **上游**:无强制上游 —— settings 可在任意时刻经 Toolbar 进入(center overlay);逻辑上它是被其余节点依赖的前置底座,而非串在主旅程里的一步。

---

> **三维链路**:本节点(workflow)→ 能力 [`studio-settings`](../02_capabilities/README.md) → 区域 [`settings`](../03_regions/README.md);平台依赖 [`gateway`](../04_platform/README.md)。能力 / 区域文档按 INDEX §7 模板在 task C 阶段补全;本节点只写旅程,不重述组件实现(§2 所有权不变量)。
