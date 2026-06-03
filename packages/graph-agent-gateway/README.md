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
- **base_url 按协议归一化**（✅ 通用部分 `registry/storage.py:_normalize_base_url`；每协议规则待补全）：把同一端点的等价 URL 收敛成确定的 canonical 形式，保证测试 / 缓存 / 调用一致。
- **凭证指纹**（✅ `registry/storage.py:compute_credential_fingerprint`）：算一个不可逆缓存键，凭证一变就让相关验证证据失效。
- **原始端点信息 → 标准 endpoint list**（🔻）：应用收集到的零散 / 混合凭证（多 key、多 URL、多协议混在一起）交给 gateway，由它用内置协议 SDK **自动匹配协议 + 测试连通 + 拆成多条标准 endpoint**。应用只负责"怎么收集原始输入"。

### B. 模型知识（available models）
- **单路线探测契约**（✅ `registry/probe_contracts.py`）：1-token 真实探测的结果契约 `ProbeResult`。
- **list-models 解析（每协议）+ 批量探测编排**（🔻）：把端点支持的模型列出来 / 探出来。
- **按同类分组（model group）**（🔻 现 `llm_model_groups.py`）：把同一模型的多个变体 / 快照 / 渠道折叠成一个用户可见的"模型组"，让应用查找 / 选择更方便。
- **品牌 / 家族识别（identity）**（🔻 现 `llm_model_identity.py`）：把原始 model id 客观归类到厂商 / 家族（Anthropic·Claude、OpenAI·GPT…）。
- **探测知识库（draft + 证据库 + notable）**（🔻 现 `llm_import_drafts.py` / `llm_notable_models.py`；数据结构 `EvidenceRecord` / `ProviderImportDraft` 已在 ✅ `registry/schema.py`）：记住"哪些模型存在 / 可用 / 值得试"、每条路线历次探测的证据，可**远端共享**。这是 gateway 背后可沉淀、可共享的知识资产。

### C. 能力
- **能力归一化**（✅ `registry/capabilities.py:normalize_route_capabilities`）：把各厂商参差的能力字段（模态、最大 token、thinking…）归一成统一表示。
- **能力描述符**（✅ `registry/capabilities.py:build_runtime_setting_descriptors`）：把能力翻译成"机器可读的可配置项"（哪个是布尔开关、哪个是数值上限），驱动应用的设置控件——应用只需选"我关心哪几种能力"。
- **能力对比 / 合并**（🔻 现 `llm_route_capabilities.py`）：把路线静态声明的能力 + 探测验证出的能力合并成一份有效能力。

### D. 状态
- **客观健康态 + 熔断**（✅ `client_manager.py` 熔断决策、`registry/probe_contracts.py`）：一条路线现在是否验证通过 / 失败 / 熔断冷却中。
- **熔断状态持久化**（🔻 现 `llm_health_store.py`）：把冷却事实存起来跨进程复用。
- **标准状态总结（6 态）**（🔻 现 `llm_state_projection.py`）：把"配置 + 健康 + 熔断"总结成一套标准状态集（6 态：`ready / 以前联通过(蓝) / untested / failed(带 reason) / cooling_down / off`）——这是 gateway 从自身机制提炼的最佳状态方案，应用选用全套 / 部分 / 不用，**不必自己研究机制重新发明**。

### E. 编排
- **角色 → fallback 链（materialize）**（🔻 编排核心现 `llm_role_materializer.py`）：按角色的"意图"（对模型能力的偏好 / 约束，如 thinking 要 / 不要 / 必须、输出 token 上限）过滤路线、降级、排成有序 fallback 链。意图驱动的能力编排是 fallback 机制的内在需求，不是某个应用的发明。
- **角色 → 路线解析**（✅ `resolver.py:ModelResolver`、`registry/resolver.py:resolve_role`）：接收已编排好的角色定义，解析出有序 `ResolvedRoute` + 跳过诊断。
- **lint 校验**（✅ `registry/lint.py:lint_role_routes`）：检查路线配置是否满足能力要求，只 warn / block，不替应用选型。

### F. 调用
- **两级对外接口**：
  - **role 级**（✅ `ModelResolver`）——应用给一个 role name，gateway 解析 → 自动按 fallback 链调用，失败按错误码熔断 / 重试 / 切下一条。
  - **route 级**（🔻 待提升为一等公共 API）——应用给一条 route，gateway 直接调用（不需要编排的应用用这个）。
- **原生 ChatX 调用**（✅ `gateway_chat_model.py`、`client_manager.py`）：每条路线用原生 langchain ChatX 调通，外层保留 fallback / 熔断 / probe / usage / 路线归属编排。
- **错误分类**（✅ `registry/error_classification.py`）：把 HTTP 状态码 / 异常映射成"该 fallback / 该 fail-fast / 该重试"——应用也可以只要这个错误码语义，自己决定怎么处理。
- **探活 + 瞬时重试 + 截断升级重试**（✅ `client_manager.py`）。

### G. 可观测
- **usage / metadata、fallback 事件、tracing、结构化异常**（✅ `events.py` / `tracing.py` / `exceptions.py`）。

---

## 4. 内部架构：编排 → [route] → 调用

- **编排（准备期）**：role → 解析出该用哪条 `route`（含 fallback 顺序、熔断 / probe 决策），**不调模型**。
- **交接**：`route`（`ResolvedRoute` / `ResolvedRole`）= 编排 ↔ 调用的唯一接口。
- **调用（执行期）**：拿 `route` 真正调（原生 ChatX）。

调用方可以只取"编排"（要 route 自己调，如独立 SDK 运行时），也可以让 gateway 一路调到底。

---

## 5. 它不是什么（边界澄清）

- ❌ 不含任何 **UI / 前端**——它只产出结构化数据，怎么渲染是应用的事。
- ❌ 不含**产品策略**——不决定默认推荐谁、不知道"弃用区 / family 折叠"这类产品形态。
- ❌ 不知道 **copilot 是什么**——它只解析一个叫 `copilot_chat` 的 role 的 route，谁拿去、用什么 SDK 怎么调，与它无关。
- ❌ 不绑定**存储位置**——数据结构与读写由它定义，存到哪个介质由应用注入。

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

- **已在包内**（`src/graph_agent_gateway/`）：`ModelResolver` / `GatewayChatModel` 调用外壳、`client_manager` 调用与熔断、`registry/`（schema / credentials / capabilities / lint / error_classification / probe / canonical / resolver）、events / exceptions / tracing。
- **对外 API 现状**：顶层 `__init__` 目前只导出 `GatewayChatModel` / `ModelResolver` / 异常——上面 §3 的多数富能力**尚未提升为一等对外 API**（仍埋在 `registry` 子模块，或仍在 studio 侧）。
- **待下沉**（按判据属公共，当前实现散在 `apps/studio/backend`）：endpoint 标准化拆分、list-models 解析、model group 分组、identity、notable / draft 知识库、6 态投影、熔断持久化、materialize 编排核心、能力合并。
- **模块级现状 vs 目标**详见 `docs/graph-agent-gateway/mvp1/`。

---

## 8. 包信息

- **包名**：`graph-agent-gateway`（version 1.0.0）
- **源码**：`src/graph_agent_gateway/`
- **测试**：`tests/`
- **设计判据权威源**：本 README §2 + `docs/studio/mvp1/01_workflows/00_settings-ux-spec.md` §6
