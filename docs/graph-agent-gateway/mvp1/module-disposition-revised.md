# Gateway MVP1 — 修订版逐模块归属表（按"公共能力内核 vs 应用加工"判据）

> **取代** 2026-06-03 只读 review 的"领域泄漏"结论。
> **判据权威源**：gateway 包 `packages/graph-agent-gateway/README.md` §2 + `docs/studio/mvp1/01_workflows/00_settings-ux-spec.md` §6.0（第四轮校准）。
> **一句话判据**：gateway = 富能力可复用网关；它对模型数据/机制的**标准化 · 组织 · 编排 · 状态总结 · 知识沉淀**，凡**不依赖「应用加工四件事」**，皆 ③b 公共；app 只留**应用加工四件事**——① UI 交互 ② 产品策略 ③ 实际调用方式 ④ 存储介质。

---

## 0. 为什么反转

原 review（2026-06-03）按"③b 绝不含 model group / draft / 6 态 / copilot = 领域"判定，把一大批 gateway 公共能力误判成"③a 领域泄漏、该搬出 gateway"。

PM 第四轮校准后：这些的**能力内核恰是 ③b 公共**（gateway 机制衍生的最佳方案，任何调模型的 app 可复用），只有 UI / 产品策略 / 调用方式 / 存储介质归 ③a。

故原"搬出 gateway"的结论**反转**为"**确认属 ③b 公共 + 规划 studio 实现下沉**"。判定一律走一句话：**换个完全不同的 app 装上 gateway，这个能力还原样能用吗？能 = ③b 公共；不能（绑死 UI/产品策略/调用/存储之一）= ③a 应用。**

---

## 1. 归属表（14 模块 + 相关 service）

> ❌ 标记 = 原 review 误判、本次反转的项。真实位置：③b = `packages/graph-agent-gateway/`，③a = `apps/studio/backend/app/`。

| 模块 / 能力 | 原 review 判定 | 新判定 | 处置 |
|---|---|---|---|
| 01 handoff route 契约 | ③b ✓ | ③b 公共 | 留 gateway；**补 route 级直调 public API** |
| 02 `resolve_role` 路线解析 | ③b | ③b 公共 | 留 gateway |
| 02 materialize（`llm_role_materializer`） | ③a 应搬 studio ❌ | **③b 公共**（编排内核）+ ③a（report 渲染） | 编排内核下沉 gateway；report 渲染留 studio |
| 03 凭证/端点 schema+读写+base_url 归一化 | ③b（seam） | ③b 公共 | 留 gateway；存储介质留 studio 注入 |
| 03 endpoint 标准化拆分 | ① 前端 | **③b 公共**（拆分/匹配/测试）+ ① 录入 | 拆分下沉 gateway；录入 UI 留前端 |
| 04 registry schema | ③b ✓ | ③b 公共 | 留 gateway |
| 05 capabilities / lint / profile_selector | ③b | ③b 公共 | 留 gateway |
| 05 model_groups（分组） | ③a 应搬 ❌ | **③b 公共** | 下沉 gateway |
| 05 identity（品牌/家族） | ③a 应搬 ❌ | **③b 公共** | 下沉 gateway |
| 05 notable（已知可用模型知识） | ③a 应搬 ❌ | **③b 公共**（知识库） | 下沉 gateway |
| 05 route_capabilities（能力合并） | ③a（实现住错） | **③b 公共** | 下沉 gateway |
| 06 错误分类 | ③b ✓ | ③b 公共 | 留 gateway |
| 07 fallback / circuit / probe | ③b ✓ | ③b 公共 | 留 gateway |
| 07 health_store（熔断持久化） | ③a（seam） | **③b 公共** | 下沉 gateway；存储介质留注入 |
| 07 copilot_test（copilot 假测试） | ③a leak | ③a 应用（copilot 专属） | 留 studio |
| 08 6 态投影（`state_projection`） | ③a 全搬 ❌ | **③b 公共**（标准总结） | 下沉 gateway；颜色渲染留前端 |
| 08 draft + 证据库（`import_drafts`） | ③a 全搬 ❌ | **③b 公共**（知识库）+ ③a（import/apply 工作流） | 知识库下沉 gateway；import UI 留 studio；**远端源改可配置** |
| 09 invocation runtime | ③b ✓ | ③b 公共 | 留 gateway |
| 10 route-chat-model 工厂 | ③b（新建） | ③b 公共 | 留 gateway（新建） |
| 11 provider profiles | ③b（新建） | ③b 公共 | 留 gateway（新建） |
| 12 copilot（`copilot.py` SDK 调用） | ③a 全搬/降 stub | ③a 应用（实际调用方式） | 留 studio；gateway 只给 `copilot_chat` route（**模块 12 降为 stub 并入 01**） |
| 13 tracing / events / exceptions | ③b ✓ | ③b 公共 | 留 gateway |
| 14 routers（HTTP `/api/llm`·`/api/copilot`） | ③a | ③a 应用（薄壳/适配） | 留 studio |
| predict-migration | mock → engine | mock=业务逻辑→engine；role→route 公共 | 不变 |
| 推荐 / 默认浮出 / family 折叠展示 | ③a | ③a 应用（产品策略/展示） | 留 studio / 前端 |

---

## 2. 下沉清单（现散在 ③a `apps/studio/backend`，按判据应下沉 ③b）

| 能力内核 | 现位置（③a） | 下沉时留在 ③a 的应用层 |
|---|---|---|
| materialize 编排内核 | `services/llm_role_materializer.py` | materialization_report 的渲染 |
| model_group 分组 | `services/llm_model_groups.py` | family 折叠/弃用区的展示 |
| identity 品牌/家族识别 | `services/llm_model_identity.py` | 展示名样式覆盖（如有） |
| notable 知识 | `services/llm_notable_models.py` | 哪个面板展示（Manual panel） |
| draft + 证据库 | `services/llm_import_drafts.py` | import/apply 工作流 UI + **远端源选择（现硬编码 GitHub repo，应改可配置）** |
| 6 态标准总结 | `services/llm_state_projection.py` | 状态颜色/文案呈现 |
| 熔断持久化 | `services/llm_health_store.py` | 存储介质（SQLite 路径）注入 |
| 能力合并 | `services/llm_route_capabilities.py` | — |
| endpoint 标准化拆分 | 前端 + `services/llm_credentials.py` upsert | provider 卡录入交互、多 URL 行 |
| list-models 解析 + 批量探测编排 | `routers/llm.py` 探测编排 | 批量进度的 UI |

> 下沉是**代码迁移**，属后续工程；本表先固化"判据归属"，不在本轮动代码。

---

## 3. 正确留在 ③a / 前端（应用加工，不下沉）

- **copilot SDK 调用 / session**（`services/copilot.py`）—— gateway 只给 `copilot_chat` route，怎么用是 studio 的事。
- **HTTP routers**（`routers/llm.py`、`routers/copilot.py`）—— 薄壳/适配，底下调的 service 是公共。
- **产品策略**：默认推荐、动态浮出 opus4.8→4.7、弃用区、family 折叠展示。
- **UI 交互**：拖拽编辑角色、provider 卡录入、状态颜色渲染、可搜索选组。
- **存储介质**：凭证/知识库存哪个文件（gateway 定 schema + 读写，studio 提供存储位置）。

---

## 4. 纯 ③b（原 review 已判对，不变）

06 错误分类 · 09 调用运行时 · 10 route-chat 工厂 · 11 provider profiles · 13 tracing/events/exceptions · 01 handoff 契约 · 03 凭证端点 schema · 04 registry schema。

## 5. predict（不变）

mock = 业务逻辑 → 移交 engine；gateway 只留 role→route。

---

## 6. 对原 14 个模块文档的影响

- **不再"把模块搬出 gateway 文档"**——这些模块（含 model_group / 6 态 / draft / materialize）**本就该在 gateway 文档**，因为它们是公共能力。
- 真正要从 gateway 文档**剥离/降级**的只有：**12 copilot**（降为 stub：gateway 只给 `copilot_chat` route，copilot 专属内容移 studio）、**14 routers**（标注为 ③a 适配壳），以及各模块里混入的 **UI / 产品策略**描述。
- 各模块文档需**重写视角**：把"现状 ③a 实现"标为"待下沉 ③b 的公共能力"，把 UI / 产品策略部分明确划给 studio（与 `00_settings-ux-spec.md` §6 配套，不脱钩）。
