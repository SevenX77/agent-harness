# Node 0: 设置与配置 (Settings & Configuration)

> Tier: workflow · 能力 `studio-settings` · 区域 `settings` · 平台 `gateway`(Python sidecar)
> 设计源: `.kiro/specs/studio-{api-keys-redesign, api-keys-regression-hardening, llm-roles-model-groups, llm-roles-frontend-cutover, llm-gateway-redesign, llm-platform-control-plane-runtime}` + gateway 模块设计 [`docs/graph-agent-gateway/mvp1/`](../../../graph-agent-gateway/mvp1/) + 锁定决策 D8 / D10 / §11 / G3。
> 角色: **运行底座** —— 被 predict / run / publish / copilot 硬依赖的前置配置节点,不串在主旅程里,而是托住主旅程。

## 1. 业务目标

01–06 是"做一个 skill"的主旅程,但它们集体悬在一个隐含前提上:**LLM 得能跑**。Predict 要把抽象角色解析成真实 route 才能试飞,Run 要真实消耗 provider,Publish 要知道 Gitea 主机与产物落盘路径,Copilot 要有自己的模型与密钥。这些"跑起来的前提"既不属于画布、也不属于编辑器,而是一处独立的配置面 —— 这就是 00_settings。

它承载 PM 的四条配置旅程:**Provider 凭证(API Keys)/ 抽象角色到模型的映射(LLM Roles)/ 助手配置(Copilot)/ 身份与产物路径(General)**。这个节点的产物不是某个 skill,而是让其余所有节点"能调模型、能上线"的运行底座。因此它在逻辑上先于 01–06 的任何 LLM 动作,是被 predict / run / publish / copilot 硬依赖的前置节点。

## 2. 核心范式

### 2.1 配置面,而非退出工作区
打开 Settings 是中心覆盖层(center overlay)盖住中心视图,**不卸载当前 skill workspace** —— skill 态、copilot、面板、分屏全部保留,关掉覆盖层即回到原工作区。这区别于 Header 的 `[ ← Back to Home ]`(那会卸载工作区)。PM 可以在装配 / 试飞途中随手进设置改个 key,回来继续,不丢上下文。

### 2.2 后端是唯一真相源,前端只投影
Settings 看起来是"前端表单",但它的真相全在后端:一个 provider 能不能用,不是一个布尔字段,而是 **endpoint 状态 + route 状态 + 密钥是否存在 + 运行期熔断**四者的组合,这些事实都在 gateway 后端(凭证文件 + SQLite health store)。因此 Settings 的铁律是:**前端不自建并行真值源,只消费后端投影**。测试一个 provider / model 的结果必须回写后端,UI 从后端读回 —— 切 tab、重启 app 都不丢。(现状落差见 §4。)

### 2.3 启动期就绪,但不全屏 gate
因为 settings 的 API key / LLM role 配置需要服务端解析(未来还要承载登录),gateway sidecar 在 app 启动期就由 Rust 即刻拉起,而非等到第一次打开 Settings 才懒加载。但这**不是全屏 bootstrap gate**:外壳、文件树、编辑器(Rust 本地)立即可用;Settings 这种依赖 sidecar 的面用骨架屏(skeleton)+ 懒加载 + 全局"后端就绪"指示来兜 —— available models 那条巨长列表是骨架屏的头号场景。

### 2.4 数据层永不 Rust 化
横切铁律 D12 是"本地写全量走 Rust",但它管的是 **skill 源文件**(GRAPH.md / SKILL.md / `.workspace`)。Settings 的凭证与角色数据(`~/.studio/` 下的 credentials / roles)是 **gateway 拥有的服务端数据,永不 Rust 化** —— 读写一律走 gateway Python(经 storage seam 抽象、预留 `user_id`,为未来远端服务化对齐形状)。本节点唯一的本地 OS 操作,是"选默认 skills 目录"的文件夹选择器(native / Rust)。

## 3. 四条配置旅程

> 📋 **每步操作 / 反馈 / 动机的细粒度 UX 规格**（含 draft 赋能写回、model/endpoint 标签表现、测试落点：endpoint 验证在 API key 页、model 保证在 role 页）见 [`00_settings-ux-spec.md`](./00_settings-ux-spec.md)（PM 2026-06-02 口述，权威）。

### 3.1 General — 身份与产物路径
最朴素的一条:User ID、Gitea 主机、**默认 skills 目录**。前两者是身份 / 上线坐标(Publish 推送到 Gitea 时要用),后者决定 Home"新建 skill"时的默认落点。交互是即填即存(debounce auto-save,无 Save 按钮);"选目录"唤起 OS 文件夹选择器,"重置"回落到计算出的默认值。

### 3.2 API Keys — Provider 凭证
配 provider 让模型能连通,分两区:**official**(固定 5 厂商 anthropic/openai/gemini/deepseek/ark,只填 key)与 **third-party**(用户自增:填 URL + key,protocol 系统自动探)。
- **一个 provider = 一把 key + 多个 URL**:每个 `(URL × 探通协议)` 拆成一个**平铺 endpoint**(前端拆好告诉后端、后端不感知"卡";同 key 共享 credential + 一个限流 bucket;一 URL 通两协议则两个都建)。
- **验 endpoint = 批量模型探测**:official 只 `get-models` 即验通;third-party 须用模型打推理端点(`get-models` 只证 URL+key 可达、不证协议匹配)。**分批探(每批 ~3)、命中即停 / 全失败判死、结构错短路**——单模型会瞬时抖动,不能凭一个定生死。
- **状态 6 态 + draft 赋能**:测试结果(含失败)落 draft 沉淀历史;模型 / endpoint 标签用统一 route 级 6 态(🔵 蓝=以前联通过)。
- **锁定约束**:`base_url` 按 protocol 归一化;`api_key` 服务端明文存(0600)、`GET registry` redact、专用 secret 端点取明文;数据走 gateway(永不 Rust)。
> 细粒度 UX(official/third-party 分步、协议探测的错误码短路、批量探测、draft 赋能/写回、命名防撞、前端 UI / 前端业务逻辑 / 后端 gateway 接口的层次分离)见权威 [`00_settings-ux-spec.md`](./00_settings-ux-spec.md)。

### 3.3 LLM Roles — 抽象角色到模型的映射
这是 settings 最重的一条,也是 predict / run 的命脉:把抽象角色(analyst 等 graph-agent 角色)映射到"用哪些模型、按什么顺序兜底"。

> 📋 **细粒度 UX(原子动作 + 测试关键点)见权威 [`00_settings-ux-spec.md` §2](./00_settings-ux-spec.md)。** 以下为高层要点。

- **以 Model Group 为单位,而非裸 route**:左侧角色卡展示该角色的 Model Group 兜底链;右侧可用模型按 Model Group 卡片(扁平,不暴露 `route_id` / `canonical_id` / `endpoint_id`,只给 `display_name`;**model family 可整体折叠**)。拖一个 Model Group 进角色,自动挑 Ready + Untested + 🔵 蓝(以前联通过)的 provider、排除 Needs Setup / Off。
- **存储结构化、执行平铺**:角色存 `model_groups[]`,后端物化(materialize)成 gateway 平铺 `fallback_chain`。前端作者看 Group,引擎跑链。
- **role → route 是一等编排 API**:gateway 把"角色名 → route[]"作为一等输出(`ResolvedRoute` 是编排 ↔ 调用唯一交接物)。provider 可用性标签 = 这条链上每个 route 的 UI state 投影。
- **状态体系 6 态 + 弃用区**:provider 行用统一 6 态色(新增 🔵 蓝=以前联通过/draft 回填)。单模型失败**两分类**——`failed`(红、**不挡**进可用、仍可选)vs `disabled`(弃用→灰、入可折叠弃用区、re-probe 再通可**捞回**);`needs_setup`(provider 没配通:缺 key/base_url/protocol/model)灰显引导去 API Keys 修。
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

> **现状 → 接线工程(亲验 file:line,见 ux-spec §3.5)**:mock 驱动(`mock-copilot-data`)+ **假测试**(测试探针 `AsyncAnthropic` ≠ 运行 `ClaudeSDKClient`,`llm.py:2150` vs `copilot.py:242`,[[copilot-assist]] + ux-spec §3.8 待修)+ `saveStatus` 丢弃 + **copilot_ 前缀分流 bug**(选组后丢前缀→后端 `_is_copilot_role` 误判存到 graph-agent 侧)+ 占位按钮。
> **session 持久化(D8)** 属 copilot 聊天(skill 工作台 region),settings §3 只配模型,失败退路见 §5。

## 4. 测试 → 持久化 → 投影(贯穿四旅程的核心机制)

四条旅程共享同一套"测了就别再丢"的机制,这是 settings 的灵魂:

1. **探测**:endpoint 测试 / route probe / role 测试 是真实测试状态的唯一写入点。
2. **持久化**:endpoint 成功 / 失败 / 空 key 写 endpoint 状态 + 时间戳 + 消息;route 确定成功写 `verified` + capabilities,确定失败写 `failed` + 原因码,**临时**网络 / 限流 / 超时写运行期熔断(cooling_down)而**不**永久打 failed —— 临时问题会过期,用 `retry_at` 表达"暂时别用"。熔断事实落 SQLite。
3. **投影**:前端 registry 行与角色物化都调同一个后端投影函数,把"endpoint 状态 + route 状态 + 密钥存在性 + 熔断"合成五个 UI state 之一:
   - **`ready`** — endpoint 与 route 都 verified,唯一绿灯。
   - **`untested`** — 无禁用、无缺配、无熔断,但也未双 verified。
   - **`cooling_down`** — 有未过期熔断,展示 `retry_at` + 消息,不当永久失败。
   - **`needs_setup`** — 缺 key / endpoint failed / route failed。
   - **`off`** — 被用户 / 配置主动禁用,优先级最高。
4. **复用**:角色物化时跳过 `needs_setup` / `off`、对 `cooling_down` 记警告、只把 fit 的 route 放进兜底链 —— UI 看到的测试态,与引擎实际编排用的是同一套判断。

> **现状落差(头号 gap)**:后端持久化(endpoint / route 状态 + SQLite 熔断 + 投影函数)已具雏形,但前端仍残留**易失副本**(provider 测试结果、role 测试态存内存,刷新即丢)。目标是删掉前端这层易失覆盖,完全以后端 SSOT 投影为准。这是 settings 接线的主工程。

## 5. 失败退路

- **sidecar 未就绪**:Settings 面用骨架屏 + 全局"后端就绪"指示;gateway 起不来在该面内报错,而非全屏失败(壳 / FS 仍可用)。
- **测试失败**:返回结构化原因码(invalid_key / rate_limited / quota_exceeded / network_error / timeout / missing_key),UI 据此给可读诊断 + 对应 state,而非笼统报错;临时类失败走 cooling_down 等待重试。
- **密钥泄漏防护**:redact + secret 端点 + 前端不 log / 不 toast / 不持久化明文。
- **Copilot session 持久化失败(D8 MUST 配套)**:copilot 对话与 session 必须落盘且重进恢复一模一样;**写盘 / 读回失败必须显式告警,绝不静默吞** —— 静默吞 = 对话丢失,违"零容忍静默失败"铁律。此失败退路是 D8 的配套待建动作。

## 6. 平台依赖与下游流转

- **平台**:本节点的数据面全部由 `gateway`(Python sidecar)提供 —— provider / role / credential / model 解析 + copilot chat facade;经 storage seam 抽象、预留 `user_id`。OS 文件夹选择器走 native(Rust)。
- **下游硬依赖**:
  - **[03_prediction](./03_prediction.md) / [04_execution](./04_execution.md)**:role 必须先在此配好并解析成 route,predict / run 才能调模型。
  - **[06_eval](./06_eval.md)(publish)**:Publish 推 Gitea 要 General 的 Gitea 主机;产物落盘路径(artifacts 默认落 `.workspace/artifacts`,见 G3 / FROZEN-2 改动)与 General 的目录配置相关。
  - **Copilot(贯穿全程)**:右侧 copilot 自始至终依赖 copilot 角色 + 密钥配置。
- **上游**:无强制上游 —— settings 可在任意时刻经 Toolbar 进入(center overlay);逻辑上它是被其余节点依赖的前置底座,而非串在主旅程里的一步。

---

> **三维链路**:本节点(workflow)→ 能力 [`studio-settings`](../02_capabilities/README.md) → 区域 [`settings`](../03_regions/README.md);平台依赖 [`gateway`](../04_platform/README.md)。能力 / 区域文档按 INDEX §7 模板在 task C 阶段补全;本节点只写旅程,不重述组件实现(§2 所有权不变量)。
