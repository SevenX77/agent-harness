# graph-agent-gateway

> **领域无关的、可复用的大模型「编排 + 调用」网关。**
> 任何需要调用大模型的应用装上它，就获得一整套"把模型管起来、测起来、调起来、编排起来"的公共能力——而不必自己从零实现凭证管理、连通性测试、能力探测、fallback 编排、熔断重试。

---

## 1. 它是什么

graph-agent-gateway 是一个 **富能力的可复用模型网关**，不是一个瘦的"调用代理"。

一句话职责：

> **gateway 拥有并增值处理「模型调用相关的数据与机制」（模型清单 / 路线 / 能力 / 运行状态 / 凭证 / 探测知识），把它们标准化、组织、编排、总结、沉淀成任何调模型的应用都能直接用的公共能力。** 凡不依赖某个具体应用的**「应用加工四件事」（UI 交互 / 产品策略 / 实际调用方式 / 存储介质）**，都是 gateway 公共能力。

它**不关心**调用方是什么应用、给谁用、长什么样。它只认识五类东西：

| 概念 | 含义 |
|---|---|
| `endpoint` | 一个模型服务端点 = 一套 base_url + 协议 + 凭证 |
| `route` | 一条具体可调用的「端点 × 模型」路线 |
| `credential` | 凭证引用（`credential_ref`，不落明文） |
| `capability` | 模型能力（是否支持 thinking、最大输出 token、模态…） |
| `protocol` | 协议 SDK（anthropic / openai / gemini / ark …，内置） |

---

## 2. 边界判据（本包最重要的设计约束）

它决定什么进 gateway、什么留给应用。

### 公共能力（gateway 做）
> 对模型数据与机制的一切**标准化 / 组织 / 重组 / 编排 / 状态总结 / 知识沉淀**，只要**不依赖某个具体应用的「应用加工四件事」（UI 交互 / 产品策略 / 实际调用方式 / 存储介质）**，都是公共能力——因为它是 gateway 机制本身衍生出的最佳方案，任何调模型的应用都能直接复用（用全部 / 用部分 / 不用）。

### 应用加工（应用做，gateway 感知不到的四件事）
1. **UI 交互 / 录入 / 展示**：用户怎么录入凭证、拖拽编辑角色、渲染状态颜色与分组折叠。
2. **产品策略**：默认推荐哪个模型、浮出哪个新版本、哪些算"弃用"。
3. **实际调用方式**：拿到 route 后用什么去真正跑模型（如 Claude Agent SDK / 自己的 agent loop）。
4. **存储介质**：把 gateway 定义的数据（凭证 / 知识库）存到哪个文件 / 路径（只是"插座插哪"）。

### 一条贯穿的缝
> **gateway 产出结构化的数据与能力；应用负责把它「喂进来 + 渲染出去 + 用出去」。**

判定一个逻辑归谁，只问一句：**换一个完全不同的应用装上 gateway，这个能力还原样能用吗？**
能 → 公共（gateway）；不能（因为它绑死了上面四件事之一）→ 应用。

---

## 3. 公共能力清单

> ✅ = 已在本包内；🔻 = 按判据属公共、当前实现还散在 `apps/studio/backend`，待下沉进本包。

### A. 凭证 & 端点
- **凭证 / 端点 schema + 读写规范**（✅ `registry/schema.py`、`registry/credentials.py`、`registry/contracts.py`）：gateway 定义 `ProviderEndpoint` / `ProviderRoute` / 凭证引用 `credential_ref` 的数据结构与读写契约；应用只提供一个存储介质（文件）插上。
- **base_url 按协议归一化**（✅ 通用部分 `registry/fingerprint.py:_normalize_base_url`；每协议规则待补全）：把同一端点的等价 URL 收敛成确定的 canonical 形式，保证测试 / 缓存 / 调用一致。
- **凭证指纹**（✅ `registry/fingerprint.py:compute_credential_fingerprint`）：算一个不可逆缓存键，凭证一变就让相关验证证据失效。
- **原始端点信息 → 标准 endpoint list**（🔻）：应用收集到的零散 / 混合凭证（多 key、多 URL、多协议混在一起）交给 gateway，由它用内置协议 SDK **自动匹配协议 + 测试连通 + 拆成多条标准 endpoint**。应用只负责"怎么收集原始输入"。

### B. 模型知识（available models）
- **单路线探测契约**（✅ `registry/schema.py:ProbeResult`）：1-token 真实探测的结果契约。
- **list-models 解析（每协议）+ 批量探测编排**（🔻）：把端点支持的模型列出来 / 探出来。
- **按同类分组（model group）**（✅ `registry/model_naming.py:project_model_group_identity`）：把同一模型的多个变体 / 快照 / 渠道折叠成一个用户可见的"模型组"，让应用查找 / 选择更方便。**这是给人看的粗分组，不是执行身份**——`registry/identity.py` 的 `canonical_id` 必须和 route_id 后缀逐字节一致，所以带日期快照的 `claude-opus-4-1-20250805` 在那边自成一组；这里刻意把快照折掉，让选择器只显示一行。两者不可互相顶替。
- **品牌 / 家族识别（identity）**（✅ `registry/model_naming.py:project_model_identity`）：把原始 model id 客观归类到厂商 / 家族（Anthropic·Claude、OpenAI·GPT…）。宿主给端点起的**用户可见标签**由 `provider_label` 参数显式传入，不从 endpoint 上读——网关的 `ProviderEndpoint` 没有展示字段，假设它有就只服务于长得像 Studio 的宿主。
- **Probe Knowledge Catalog（探测知识库）**（✅ `registry/catalog.py`；数据结构 `EvidenceRecord` / `ProviderImportDraft` 在 `registry/schema.py`）：记住"哪些 endpoint 连通过 / 哪些模型存在 / 哪些能力被探测证实 / 哪些模型值得优先试"、每条路线历次探测的证据，可**远端共享**。这是 gateway 背后可沉淀、可共享的知识资产；Import Draft（待导入草稿 → apply）不属于 MVP1 主线。
- **notable models（值得优先试的模型）**（🔻 现 `services/llm_notable_models.py`）：读一份人工维护的清单，告诉应用先试哪些模型。

### C. 能力
- **能力归一化**（✅ `registry/capabilities.py:normalize_route_capabilities`）：把各厂商参差的能力字段（模态、最大 token、thinking…）归一成统一表示。
- **能力描述符**（✅ `registry/capabilities.py:build_runtime_setting_descriptors`）：把能力翻译成"机器可读的可配置项"（哪个是布尔开关、哪个是数值上限），驱动应用的设置控件——应用只需选"我关心哪几种能力"。
- **能力合并**（✅ `registry/capabilities.py:route_effective_capabilities`）：把路由静态声明的能力
  与探测真正验证出的能力合并成一份有效能力，**实测压过声称**——路由清单上写着不支持 thinking、
  而一次 thinking 探测回了 `ready`，以探测为准。哪些属于"验证出的"由
  `registry/capabilities.py:verified_profile_capabilities` 单独作答：只有 `ready` 的档案算数，
  且是否算"会思考"看候选**声明的 capability**，不看名字里有没有 thinking 字样——这个结论要盖
  `probed_verified` 章，不能从标签上猜。

### D. 状态
- **客观健康态 + 熔断**（✅ 熔断决策 `call/clients.py:LLMCircuitAndUsageLedger`、探测结果契约 `registry/schema.py:ProbeResult`）：一条路线现在是否验证通过 / 失败 / 熔断冷却中。
- **熔断状态持久化**（🔻 现 `services/llm_health_store.py`）：把冷却事实存起来跨进程复用。
- **标准状态总结（6 态）**（🔻 现 `services/llm_state_projection.py`）：把"配置 + 健康 + 熔断"总结成一套标准状态集（6 态：`ready / 以前联通过(蓝) / untested / failed(带 reason) / cooling_down / off`）——这是 gateway 从自身机制提炼的最佳状态方案，应用选用全套 / 部分 / 不用，**不必自己研究机制重新发明**。

### E. 编排
- **角色 → fallback 链（materialize）**（🔻 编排核心现 `services/llm_role_materializer.py`）：按角色的"意图"（对模型能力的偏好 / 约束，如 thinking 要 / 不要 / 必须、输出 token 上限）过滤路线、降级、排成有序 fallback 链。意图驱动的能力编排是 fallback 机制的内在需求，不是某个应用的发明。
- **角色 → 路线解析**（✅ `resolve/resolver.py:resolve_role` 是编排面的解析；`call/resolver.py:ModelResolver` 是执行面按 fallback 链取下一条的那层）：接收已编排好的角色定义，解析出有序 `ResolvedRoute` + 跳过诊断。
- **lint 校验**（✅ `resolve/lint.py:lint_role_routes`）：检查路线配置是否满足能力要求，只 warn / block，不替应用选型。

### F. 调用
- **两级对外接口**：
  - **role 级**（✅ `ModelResolver`）——应用给一个 role name，gateway 解析 → 自动按 fallback 链调用，失败按错误码熔断 / 重试 / 切下一条。
  - **route 级**（🔻 待提升为一等公共 API）——应用给一条 route，gateway 直接调用（不需要编排的应用用这个）。
- **原生 ChatX 调用**（✅ `call/chat_model.py`、`call/clients.py`）：每条路线用原生 langchain ChatX 调通，外层保留 fallback / 熔断 / 前置探问 / usage / 路线归属编排。
- **错误分类**（✅ `resolve/error_classification.py`）：把 HTTP 状态码 / 异常映射成"该 fallback / 该 fail-fast / 该重试"——应用也可以只要这个错误码语义，自己决定怎么处理。
- **前置探问 + 瞬时重试 + 截断升级重试**：三件事今天各有各的家——前置探问 `call/pre_call_probe.py`（问的是「这条路收不收这些设置」，**不是**探活，见 `docs/graph-agent-gateway/mvp1/07-orch-fallback-circuit-probe/mvp1-alignment.md` F3）、瞬时重试由 ChatX 自己做（有界，只对 429/5xx/连接）、截断升级重试 `call/chat_model.py` 的 `_Attempt`。

### G. 可观测
- **usage / metadata、路由决策事件、调用设置事件、结构化异常**（✅ `events.py` / `call/tracing.py` / `errors.py`）：网关每次跳过、探问失败、丢设置重试、同路由重试、加预算重来、换路由、终止、答出、全灭，都发**同一种**事件（`LLMRouteDecisionEvent`，判别字段是封闭枚举）；答案收口时另发一条 `LLMCallSettingsEvent` 说这次要求的每项设置落到什么下场。设计见 `docs/graph-agent-gateway/mvp1/13-x-tracing-events-exceptions/mvp1-alignment.md`。

---

## 4. 内部架构：六个域，域的公共契约就是包入口

包按**领域**成树。划分依据是一组共同的不变量，不是文件名相似；域外只从包入口导入
（`from graph_agent_gateway.<域> import X`），不深入别人的文件——由
`tests/test_gateway_package_boundary.py` 的 AST 门禁强制。

| 域 | 负责什么 |
|---|---|
| `registry/` | **真相**：凭据 / 端点 / 路由 / 能力的定义、身份、边界、存储 port、状态投影 |
| `resolve/` | **解析**：从角色推出一条具体路由链（lint / profile / 交接 / fallback / 错误分类） |
| `role/` | **角色物化**：角色 → 已贴合这条路由的调用设置 |
| `dialect/` | **方言**：每家 provider 的请求 / 响应形状（生产与探测唯一共用实现） |
| `call/` | **调用**：客户端、chat model、本次调用的设置与下场 |
| `probing/` | **探测**：问一个小到值得问的问题（端点通不通 / 路由认不认 / 这档 effort 收不收） |

贯穿的那条线仍然是**编排 → [route] → 调用**：

- **编排（准备期）**：`resolve` + `role` 推出该用哪条 `route`（含 fallback 顺序与跳过原因），**不调模型**。
- **交接**：`ResolvedRoute` / `ResolvedRole` = 编排 ↔ 调用的唯一接口。
- **调用（执行期）**：`call` 拿 `route` 真正调。

调用方可以只取"编排"（要 route 自己调，如独立 SDK 运行时），也可以让 gateway 一路调到底。

**怎么用**：见 [`docs/graph-agent-gateway/USAGE.md`](../../docs/graph-agent-gateway/USAGE.md)。

---

## 5. 它不是什么（边界澄清）

- ❌ 不含任何 **UI / 前端**——它只产出结构化数据，怎么渲染是应用的事。
- ❌ 不含**产品策略**——不决定默认推荐谁、不知道"弃用区 / family 折叠"这类产品形态。
- ❌ 不知道 **copilot 是什么**——它只解析一个叫 `copilot_chat` 的 role 的 route，谁拿去、用什么 SDK 怎么调，与它无关。
- ❌ 不绑定**存储位置**——数据结构与读写由它定义，存到哪个介质由应用注入。

**它依赖引擎的哪一点，只有这一点**：本包异常继承引擎的公开错误家族 `ModelProviderError`
（`errors.py:GatewayError` 及其三个叶子），这是引擎公开 API 契约写死的后置条件——
见 `docs/engine/public-api-contract.md`「ModelProviderError」一节，宿主因此只需要 catch
五个家族而不是一串叶子异常。所以 `pyproject.toml` 显式声明了 `graph-agent` 依赖，
`errors.py` 的导入是无条件的。**反过来不成立**：引擎不依赖本包，它自己的
`test_engine_source_has_no_gateway_concrete_imports` 禁止引擎源码 import 本包；
宿主用自己的适配器把两者接起来（Studio 是 `app/core/adapters/engine.py` 与
`app/core/adapters/gateway.py`）。本包只走引擎的**公开门面** `graph_agent`，
不 import 它的任何子模块，`packages/graph-agent-gateway/tests/test_gateway_package_boundary.py`
逐文件扫描这一条。

---

## 6. 消费方示例：Studio 设置页（与本包配套，不脱钩）

Studio 是 gateway 的一个消费应用。它的「设置页」站在 gateway 的公共能力之上，只加那四件应用层的事：

| gateway 公共能力 | Studio 设置页加的应用层（应用特有） |
|---|---|
| 标准 endpoint list（自动拆分 / 匹配 / 测试） | provider 卡片 UI、用户在一个卡里填多 URL 的录入交互 |
| available models（分组 / 识别 / 知识库） | 侧栏渲染、family 折叠展示、弃用区、可搜索选组 |
| 能力描述符 | thinking 三态控件、输出 token 控件的具体形态 |
| 6 态 | 状态颜色（绿 / 蓝 / 灰 / 红 / 熔断 / 关）渲染 |
| 角色 → fallback 链（materialize） | 拖拽编辑角色、model group 拖拽、materialize 报告的渲染 |
| route（编排结果） | copilot 用 Claude Agent SDK 拿 route 自己调 |
| —（产品策略不归 gateway） | 默认推荐、动态浮出 opus4.8 → 4.7 |

> 完整的应用层规格见 `docs/studio/mvp1/01_workflows/00_settings-ux-spec.md`（§6 四层模型）。
> **改动本包能力时，该文档对应部分须同步精修，避免边界 drift。**

---

## 7. 现状与下沉路线

- **对外 API**：六个域各有自己的包入口并各自维护 `__all__`，顶层 `__init__` 只是极薄的
  re-export。域入口就是契约：`registry` / `resolve` / `role` / `call` / `dialect` / `probing`。
- **下沉进度**（按 §2 判据属公共能力的十六项，2026-08-13 逐条对代码核实）。这张表是**当前
  事实**，不是计划：每一行都点名它今天真正住在哪个文件，所以谁把一项挪下去、删掉 studio
  那侧的文件，`tests/test_gateway_docs_name_real_files.py` 立刻变红，逼着这张表跟着改——
  上一版清单把已经下沉的四项还写成"待下沉"，正是因为没有任何东西会读一份文档。

  **表的覆盖范围是盘出来的，不是回忆出来的。** 两条判据同时成立即入表：①**属网关域**
  （模块被 `apps/studio/backend/app/routers/llm.py` 使用，或自身 import 网关）；②**无宿主
  依赖**（不碰 fastapi / sqlite / 文件路径 / studio 配置——碰了就说明它绑死了 §2「应用加工
  四件事」之一，得先把规则与介质拆开才谈得上下沉）。按这两条机械扫 studio 的 service 目录，
  2026-08-13 扫出九个模块，其中**五个是此前任何一版清单都没点过名的**。**已知弱点**：门禁
  只保证表里点名的文件存在，不保证该入表的都入了表——覆盖完整性今天仍靠人按上面两条判据
  重扫，这是这张表现在最薄的一环。

  | 能力 | 今天住在哪 | 状态 |
  | --- | --- | --- |
  | endpoint 标准化拆分 | `registry/endpoints.py:standardize_endpoint_candidates` | ✅ 已下沉 |
  | list-models 解析 | `probing/judge.py:model_ids` | ✅ 已下沉 |
  | 6 态投影 | `registry/projection.py:project_route_state` | ✅ 已下沉 |
  | materialize 编排核心 | `role/materialization.py:materialize_role` | ✅ 已下沉 |
  | Probe Knowledge Catalog | `registry/catalog.py`（见 §3.B） | ✅ 已下沉 |
  | 能力合并 | `registry/capabilities.py:route_effective_capabilities` · `registry/capabilities.py:verified_profile_capabilities` | ✅ 已下沉 |
  | model group 分组 | `registry/model_naming.py:project_model_group_identity` | ✅ 已下沉 |
  | identity（模型名） | `registry/model_naming.py:project_model_identity` | ✅ 已下沉 |
  | 单模型探测结果类型 | 探测本体在 `probing/`；`apps/studio/backend/app/services/model_probe.py` 只剩宿主侧 DTO | ✅ 已下沉（29 行：router 把网关 `RouteProbeResult` 适配成这个形状交给自己的调用方，属宿主自用，不再搬） |
  | identity（provider 名 / 配置） | `apps/studio/backend/app/services/llm_provider_identity.py` · `apps/studio/backend/app/services/provider_config.py` | 🔻 待下沉（后者的**匹配规则**属公共，但它读 studio 自己的 `app/data/*.json`，按"存储由宿主注入"要先把规则与介质拆开） |
  | 厂商官方能力文档源 | `apps/studio/backend/app/services/official_capability_sources.py` | 🔻 待下沉（291 行纯知识：按 provider × 能力主题存官方文档 URL 与取值规则，四件事一条都不绑，任何应用装上都能直接用） |
  | 证据外发脱敏红线 | `apps/studio/backend/app/services/community_catalog.py` | 🔻 待下沉（网关 owns 探测知识库，却不 owns「什么可以离开这台机器」：白名单构造上传体、私有 / 内网主机整段丢弃端点身份。这条规则和它守护的知识库不该分居两地） |
  | 证据读取 + 探测排序 | `apps/studio/backend/app/services/llm_credentials_evidence.py` | 🔻 待下沉（其中 `endpoint_probe_priority` 与网关 `registry/catalog.py:probe_priority` 吃同一份输入、目标相反：一个要最快见绿所以领头放已验证的，一个要发现新能力所以跳过已验证的。并排放进网关，这个差别才看得见） |
  | evidence id 铸造 | `apps/studio/backend/app/services/llm_evidence_ids.py` | 🔻 待下沉（19 行，给网关 `EvidenceRecord` 铸 ID） |
  | notable | `apps/studio/backend/app/services/llm_notable_models.py` | 🔻 待下沉 |
  | 熔断持久化 | `apps/studio/backend/app/services/llm_health_store.py` | 🔻 待下沉（判据属公共的是**熔断策略**；sqlite 存储本身按"存储由宿主注入"留在 studio） |

  判"已下沉"的证据是同一条：studio 那侧只剩薄委托或已无实现。例如 6 态投影在
  `app/services/llm_state_projection.py` 只剩 28 行且直接调网关适配器，endpoint 标准化在
  studio 侧 grep 不到实现。
- **模块级现状 vs 目标**详见 `docs/graph-agent-gateway/mvp1/`；域树是怎么定下来的、
  每一期改了什么，见
  [`docs/design/2026-08-10-gateway-module-tree-and-probing-decision.md`](../../docs/design/2026-08-10-gateway-module-tree-and-probing-decision.md)。

---

## 8. 包信息

- **包名**：`graph-agent-gateway`（version 1.0.0）
- **源码**：`src/graph_agent_gateway/`
- **测试**：`tests/`
- **设计判据权威源**：本 README §2 + `docs/studio/mvp1/01_workflows/00_settings-ux-spec.md` §6
