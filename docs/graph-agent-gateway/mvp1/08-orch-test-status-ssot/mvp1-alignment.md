---
module: 08-orch-test-status-ssot
doc: mvp1-alignment
status: drafted
---

# 08 — Test Status SSOT（测试状态唯一事实源:6 态投影 + draft/证据库）· MVP1 设计

> **Tier**：③b gateway 公共能力内核（6 态标准总结 `state_projection` + draft/证据库知识库内核 `import_drafts` **本轮反转判 ③b 公共,现散 ③a 待下沉**；UI 颜色渲染 / import-apply 工作流 / 远端源选择 / 存储介质留 ③a）
> **Owns**：把"配置 + 健康 + 熔断 + 历史证据"总结成一套**标准 6 态**(`ready/historical_ready蓝/untested/failed带reason/cooling_down/off`)的投影内核 + 探测证据知识库(draft + append-only evidence + 远端共享)内核；**不渲染颜色、不做 import/apply 工作流 UI、不绑定存储介质**(归 ③a)
> **Status**：设计定稿（2026-06 判据第四轮反转 + ux-spec §4.2 六态对齐）；代码 = `state_projection`/`import_drafts` 待下沉 ③b，`ProviderUiState` Literal 待从 5 态(含 `needs_setup`)改 6 态(取消 `needs_setup`、补蓝 `historical_ready`、`failed` 带 reason)，`probe_import_draft` 待去桩
> **Related**：[[02-orch-role-resolution]]（materialize 消费 6 态投影排 fallback_chain，已取消 needs_setup）· [[05-orch-capabilities-and-models]]（`capability_state` 第二轴 + identity/notable/model_groups 同属下沉知识库）· [[07-orch-fallback-circuit-probe]]（probe 产证据 + 熔断写 health store）· [[04-orch-registry-schema]]（`ProviderImportDraft`/`EvidenceRecord`/`ProviderRoute` 字段权威源）· [[03-orch-credentials-endpoints]]（endpoint test 回写 active credentials）· [[14-api-router]]（HTTP 探测/draft 端点 = ③a 薄壳）
> **决策日志**：`docs/studio/mvp1/01_workflows/00_settings-ux-spec.md` §4.1(draft)/§4.2(6 态体系)/§4.3(测试落点)/§6.0(判据)/§6.4(横切四层) + `docs/graph-agent-gateway/mvp1/module-disposition-revised.md`（08 行两处反转 + 下沉清单）+ gateway 包 `README.md` §3 D/B（6 态总结 + draft 知识库属公共）
> **现状**：见同目录 `baseline.md`

## 1. 定义

MVP1 目标:测试状态以**后端 SSOT(单一事实源)**为准。探测结果回写 active backend store 或 runtime health store,UI **只读投影**,import draft 与 evidence library 只提供候选和证据、不能绕过 SSOT。

⚠️ **本模块反转最大**。原文档隐含把 `project_provider_model_state`(6 态投影)+ `llm_import_drafts`(draft + 证据库)当作"**studio 后端 SSOT / 后端投影**"——即隐性 ③a。按 2026-06 第四轮判据,这两者的**能力内核恰是 ③b 公共**:

- **6 态标准总结** = **③b 公共内核**:把"配置 + 健康 + 熔断 + 历史证据"总结成一套标准状态集,是 gateway 从自身机制提炼的最佳状态方案,任何调模型 app 装上就能用;`module-disposition-revised.md:40` 08 行新判定 = "**③b 公共(标准总结),下沉 gateway;颜色渲染留前端**"。gateway 包 `README.md:74` D 节明确"标准状态总结(6 态)"属公共。
- **draft + 证据库知识库内核** = **③b 公共内核**:记住"哪些模型存在 / 可用 / 值得试"、每条路线历次探测的证据、可远端共享——这是 gateway 背后可沉淀、可共享的知识资产;`module-disposition-revised.md:41` 08 行新判定 = "**③b 公共(知识库),知识库下沉 gateway;import UI 留 studio;远端源改可配置**"。gateway 包 `README.md:64` B 节明确"探测知识库(draft + 证据库 + notable)"属公共。

**留在 ③a 的应用加工(四件事)**:① import / apply 工作流 + 录入 UI(交互)② 状态颜色 / 文案渲染(展示)③ 远端源选择(现硬编码 GitHub repo,**应改可配置**——存储/源介质,四件事之④)④ 存储介质(draft / 证据 / 健康库存哪个文件 / SQLite 路径)。

不调真实模型;本模块定义"探测→持久化→投影→复用"的唯一写回路径与状态语义。本文只写文档目标,不改代码。

## 2. 数据流 / 机制（目标;现状逐步见 `baseline.md`）

**上下游**:① 探测入口(endpoint test / route probe,③a HTTP 壳触发,内核 ③b)→ 写回 **active backend store(endpoint/route status)+ health store(熔断 circuit)+ 证据库(probe 结果含失败)**(③b 内核,③a 注存储介质)→ **6 态投影 `project_provider_model_state`(③b 内核)** 把 status + key + circuit + draft 历史证据合成 UI state → 两个消费方:前端 registry row(③a 渲染颜色)+ [[02-orch-role-resolution]] materialize(③b 编排,跳过 `failed/off`、`cooling_down` 写 warning、只把 fit route 进 fallback_chain)。

**6 态投影优先级（route 级,目标语义,ux-spec §4.2 状态分层 `00_settings-ux-spec.md:264`）**:`off > failed🔴 > cooling_down > ready🟢 > historical_ready蓝🔵 > untested⚪`。其中 `ready / 蓝 / untested` 同属"证据 tier",按证据新鲜度排:刚测通(ready) > 历史通(蓝,来自 draft) > 无证据(untested)。蓝插在 ready 检查之后、untested 兜底之前。

**SSOT 写回路径(四类结果,目标语义)**:① endpoint models-list 成功 → 写 `endpoint.status=verified` + last_test 字段;② route generation/tool/probe 成功 → 写 `route.status=verified` + capabilities + verified_profiles + 清 circuit + **写"成功 probe 证据"进知识库**;③ 临时失败(网络/限流/超时/配额)→ 写 health store circuit(`cooling_down`),**不**把 route 永久 failed + **写"失败证据"进知识库**;④ 确定失败 → 写 `route.status=failed` + reason metadata + 写失败证据。投影再把 ④ 变成 `failed🔴`(带 reason,**不再是** `needs_setup`)。

**目标设计与流程**（逐步;保留 baseline 全部小节,补 6 态对齐 + 判据归属）:

### 2.1 探测 → 持久化 → 投影 → 复用

1. 探测入口:Endpoint 探测由 `test_endpoint`(endpoint 探测 API,调 provider models-list 最小请求)发起,route 探测由 `probe_route` / `_force_probe_route`(route 探测 API + 真实探测 helper)发起;这些入口必须是真实测试状态的唯一写入点之一(`apps/studio/backend/app/routers/llm.py:460-567`,`:782-818`,`:1818-1886`)。**判据:HTTP 端点 = ③a 薄壳;探测/拆分/匹配的内核 = ③b 公共。**

2. 持久化 endpoint:Endpoint 成功/失败/空 key/并发变更结果写入 `ProviderEndpoint.status`、`last_test_at`、`last_test_message`,并通过 `save_credentials` 落盘(`apps/studio/backend/app/routers/llm.py:509-567`)。**判据:status 字段 schema + 写回规则 = ③b;落盘到哪个文件(存储介质)= ③a 注入。**

3. 持久化 route:Route 成功写 `status="verified"` 并写 capabilities;确定失败写 `status="failed"` 和 reason metadata;临时网络/限流/超时写 runtime circuit,不把 route 永久打 failed(`apps/studio/backend/app/routers/llm.py:815-818`,`:1843-1886`)。

4. 持久化 circuit:`SqliteLlmHealthStore.open_circuit`(熔断持久化入口,upsert circuit 到 SQLite)把 cooling_down 事实写进 SQLite;`get_active_circuits` 只返回仍未到 retry_at 的 circuit(`apps/studio/backend/app/services/llm_health_store.py:34-62`,`:70-101`)。**判据:熔断持久化内核 = ③b(与 07 同一反转);SQLite 路径 = ③a 注入。**

5. 投影:前端 registry row 和 role materializer 都调用 `project_provider_model_state`(6 态投影函数),由后端把 status + key + circuit(+ MVP1 新增 draft 历史证据)合成 UI state(`apps/studio/backend/app/routers/llm.py:1708-1723`;`apps/studio/backend/app/services/llm_role_materializer.py:131-154`)。**判据:6 态投影内核 = ③b(本轮反转);前端把 state 渲染成颜色 = ③a。**

6. 复用:role 物化时跳过 `failed`(含原 needs_setup 配置缺口)/ `off`,对 `cooling_down` 写 warning,只把 fit 的 route 放进 fallback_chain;这使 UI test state 与实际编排共享同一判断(`apps/studio/backend/app/services/llm_role_materializer.py:48-90`)。**注**:此处旧文写"跳过 needs_setup",**6 态对齐后改为跳过 `failed`**(needs_setup 已并入 failed),与 [[02-orch-role-resolution]] §2 同步。

### 2.2 UI state 的唯一语义（6 态;取消 needs_setup,补蓝态)

> **本节为 6 态对齐重写**。原文是旧 5 态(ready/untested/cooling_down/**needs_setup**/off),与文末 MVP1 回填段(蓝态 + 取消 needs_setup)自相矛盾。现按 ux-spec §4.2 canonical 6 态统一,**取消 `needs_setup`(并入 `failed` + reason)、新增 `historical_ready`(🔵 蓝=以前联通过)**。颜色心智(ux-spec §2.1 `00_settings-ux-spec.md:114`):**红=出错要你修;灰=非错误的不可用(untested 没测 / cooling 熔断中 / off 关了);绿=好;蓝=以前好。**

1. `ready`(🟢 绿):endpoint.status 和 route.status 都是 `verified`(真 probe 过);这是唯一绿色可用状态(`apps/studio/backend/app/services/llm_state_projection.py:44-45`)。

2. `historical_ready`(🔵 蓝=以前联通过,**新增第 6 态**):endpoint verified + draft/证据库显示该 route **历史连通过**(来自 `EvidenceRecord.trust_state`,`schema.py:339`),但当前无 live `route.status=verified`;介于 untested 与 ready 之间的历史态。**蓝判据(Claude 定,PM 可推翻)**:只 `probe-verified` 历史(真连通过)算蓝,贴合"以前联通过";doc-discovered / 没连过的不算(control-plane R9.11 更宽,从窄)。**蓝不替代 ready**:真 route-probe 通 → 升 🟢;依赖 draft probe-worker(现为桩,见 §8 待办)真写历史连通证据。投影插点 = 现 `:45`(ready 检查)与 `:46`(untested 兜底)之间。

3. `untested`(⚪ 灰):没有 disabled、没有配置缺口、没有 active circuit、也没有历史连通证据、但也不是双 verified;通常对应 `unverified_manual` 或待验证 route(`apps/studio/backend/app/services/llm_state_projection.py:46`)。

4. `failed`(🔴 红,带 reason,**取代 needs_setup**):出错了要你修,两类经 `reason` 区分——① **配置缺口**(缺 key / base_url / protocol / model id,**原 `needs_setup`**)reason=`missing_config`;② **测试失败**(route 真探挂)reason=`endpoint_unreachable` / `model_failed`。**红、不挡进可用**(failed route 仍列出、仍可拖,换 role 配置 / 重试可能就好,真正永久不可用在运行期 admission 拦)。现 `_setup_reason`(配置缺口判断 helper)产 `needs_setup`(`:33-56`),MVP1 改产 `failed` + reason。

5. `cooling_down`(⚪ 灰+倒计时):存在匹配 route/endpoint/rate_limit_bucket 且 retry_at 未过的 circuit(临时网络/限流/超时);UI 展示 retry_at 和 message,不当永久失败(`apps/studio/backend/app/services/llm_state_projection.py:36-43`,`:81-91`)。

6. `off`(⚪ 灰+不可选):endpoint 或 route disabled(用户/配置主动关闭),优先级最高(`apps/studio/backend/app/services/llm_state_projection.py:31-32`)。**注**(ux-spec §4.2 单模型 probe 失败两类 `00_settings-ux-spec.md:255`):模型已弃用 / 不再提供(provider 明确返回"无此模型")归 `off`(灰、不可选),**不是** `failed`(不是"连不上",是"没这模型了");弃用可逆——点击仍可复制名 + 单独 re-probe,再次连通 → 从弃用区捞回。

### 2.3 draft + evidence library 的目标边界

1. Draft 输入:Agent/import 抓到的 endpoint_candidates 和 route_candidates 先进入 `ProviderImportDraft`(非可信导入草稿),不直接进入 active credentials(`packages/graph-agent-gateway/src/graph_agent_gateway/registry/schema.py:369-386`)。**判据:draft 数据结构 + 知识库内核 = ③b 公共;import/apply 工作流 UI = ③a。**

2. Evidence 输入:probe/docs/catalog 证据进入 `EvidenceRecord`(append-only 证据记录),保留 trust_state、scope、probe_attempts、successful_probe/failed_probe 等字段,供人工或后端决策复用(`packages/graph-agent-gateway/src/graph_agent_gateway/registry/schema.py:332-366`)。**PM 原话(ux-spec §1.4 #2.4)要求"探测结果含失败都写进 draft / 证据库,不浪费"**——失败也是历史(哪些模型抖动 / 超时 / 不可用),下次批量探测可优先跳过历史失败、优先试历史成功。

3. Evidence 追加:`append_evidence_record`(证据追加入口)继续 append-only,给 evidence 补 observed_at/attempted_at、合并 route_candidates、把新 record 追加到尾部,避免新的单条证据覆盖旧观察;但它不能直接代表 UI ready 状态(`apps/studio/backend/app/services/llm_import_drafts.py:94-128`)。

4. Draft 应用:`apply_draft`(draft 应用入口)继续要求显式应用和冲突处理;应用后的 route 默认 `unverified_manual`,必须再经过 route probe 或可信回写流程变成 active verified(`apps/studio/backend/app/services/llm_import_drafts.py:136-202`)。**判据:apply 的冲突处理工作流 = ③a;route 默认态 schema = ③b。**

5. Remote library:`sync_remote_evidence_library`(远端证据同步入口)可以合并远端 evidence(拉远端 JSON、合并 route_candidates/capabilities/metadata、按 evidence_id 去重追加),但远端证据仍应作为 advisory library,不能越过 active credentials/status SSOT(`apps/studio/backend/app/services/llm_import_drafts.py:297-376`)。**判据:同步/合并/去重的知识库内核 = ③b;远端源是哪个(现硬编码 GitHub repo)= ③a 应改可配置(`module-disposition-revised.md:61`)。**

### 2.4 后端 SSOT 回写规则

1. 成功的 endpoint models-list 测试回写 endpoint.status 与 last_test 字段;若发现官方 endpoint 的模型列表,可 upsert route,但 route 仍需按 probe 语义决定 verified(`apps/studio/backend/app/routers/llm.py:533-567`)。

2. 成功的 route generation/tool/probe 回写 route.status、capabilities、verified_profiles 和 probe metadata;当前 `_force_probe_route` 的 success path 已具备 route verified + clear circuit 的基本形状(`apps/studio/backend/app/routers/llm.py:1843-1857`)。**MVP1 补:成功 probe 同时写"成功证据"进知识库(喂蓝态历史 + 下次免重探)。**

3. 临时失败回写 health store,不写 route failed;当前 `_force_probe_route` 对 timeout/rate_limited/quota/network_error 打开 circuit,这应是 MVP1 cooling_down SSOT(`apps/studio/backend/app/routers/llm.py:1858-1873`)。

4. 确定失败回写 route.status failed 和 metadata reason;projection 再把它变成 `failed🔴`(带 reason)——**6 态对齐:不再是 `needs_setup`**(`apps/studio/backend/app/routers/llm.py:1874-1886`;`apps/studio/backend/app/services/llm_state_projection.py:52-56`)。

### 2.5 capability 就绪投影（D2 第二轴,与 availability 正交)

除 `ui_state`(能不能用,6 态),投影**第二条轴 `capability_state`(四态:unknown/callable_only/partial/known,见 [[05-orch-capabilities-and-models]] 回填)**,与 availability 分开;`_capability_state`(`routers/llm.py:1767`)从二值升四态,`tools`/`structured_output` 改派生(`llm.py:1778-1779`)。**正交轴(ux-spec §4.2 `00_settings-ux-spec.md:266`)**:`ui_state`(能不能用,6 态)≠ `capability_state`(了解多少能力)≠ `role_fit`(适不适合本角色,4 态,归 02)≠ `admission`(运行期 3 态)。

### 2.6 版本-stale 与历史证据两轴合成（D1 交叉)

版本-stale(见 [[04-orch-registry-schema]] 回填)的"曾 verified"route 投影时**不算 ready**——正是蓝(以前 verified、现未重验)。两轴(版本失效 D1 + draft 历史 E1)在 `project_provider_model_state` 合成一致投影:任何"历史 verified 但当前无 live verified"的 route 都收敛到 `historical_ready🔵`,真重验通才升 ready🟢。

## 3. 接口契约

> 跨边界签名 / schema / 错误 / 归属。前端只投影、不持第二份真相(ux-spec §6.5 检查 2);③a↔③b 边界 = ③a 注存储介质 + 渲染颜色 + 跑 import 工作流,③b 出标准 6 态 + 知识库内核。

| 边界 | 契约 |
|---|---|
| **6 态投影输出（③b 内核 → ③a/前端）** | `project_provider_model_state(endpoint, route, runtime_circuits, now, draft_history) → ProviderModelStateProjection`{ `ui_state`: 6 态 Literal `ready/historical_ready/untested/failed/cooling_down/off`, `reason_code`(failed 时 `missing_config`/`endpoint_unreachable`/`model_failed`), `retry_at`(cooling_down 时), `ui_detail` }。**MVP1 入参新增** `draft_history`(该 route_id 有无历史连通证据,来自 `EvidenceRecord.trust_state`)——现函数只读 endpoint+route+circuits、不读 draft(`llm_state_projection.py:23-46`)。**前端只渲染 `ui_state`→颜色,不在组件态另存真值**(ux-spec §6.5 检查 2)。 |
| **`ProviderUiState` Literal 改动（③b schema）** | 现 5 态 `["ready","untested","cooling_down","needs_setup","off"]`(`llm_state_projection.py:12`)→ 改 6 态 `["ready","historical_ready","untested","failed","cooling_down","off"]`：**删 `needs_setup`、加 `historical_ready`+`failed`**;`_setup_reason`(`:49-56`)改产 `failed`+reason 而非 `needs_setup`。 |
| **draft / 证据知识库（③b 内核 API）** | `create_draft`/`load_draft`(找不到抛 `DraftNotFound`)/`load_evidence_library`(找不到默认 `studio-evidence-library` 返空 library)/`append_evidence_record`(append-only)/`apply_draft`(route→`unverified_manual`)/`sync_remote_evidence_library`(远端合并去重)。`ProviderImportDraft`{ endpoint_candidates / route_candidates / probe_results / evidence_records / agent_notes / diff } + `EvidenceRecord`{ evidence_type / trust_state / scope / endpoint_id / route_id / model_id / probe_status / probe_attempts } 字段权威源 `registry/schema.py:332-386`(归 04)。**远端源 URL(现硬编码 GitHub repo)由 ③a 配置注入**,不硬编码进 ③b。 |
| **熔断持久化（③b 内核,与 07 同源）** | `SqliteLlmHealthStore.open_circuit(...)` / `get_active_circuits(route_id, endpoint_id, rate_limit_bucket) → RuntimeCircuit[]`(只返回 retry_at 未过);`RuntimeCircuit` 字段 `scope/scope_id/opened_at/retry_at/ttl_seconds/reason_code/failure_count/message`(`llm_health_store.py:14-101`)。SQLite 路径 ③a 注入。 |
| **SSOT 写回入口（③a 壳触发,③b 内核回写）** | endpoint test `test_endpoint` → 写 `ProviderEndpoint.status`+last_test;route probe `_force_probe_route` → success 写 `route.status=verified`+capabilities+clear circuit、temp-fail 开 circuit(不 failed)、hard-fail 写 `route.status=failed`+reason。**四类结果都写证据库(成功+失败,PM #2.4)。** |
| **存储介质（③a 注入,不归 ③b）** | draft / 证据库 / 健康库存哪个文件 / SQLite 路径 = ③a 提供(gateway 定 schema + 读写,studio 给位置)。`_save_all`(draft/evidence 原子写,目录 `0700`/文件 `0600`,`import_drafts.py:220-244`)的"写哪个目录"由 ③a 决定。 |
| **错误** | `load_draft` 找不到 → `DraftNotFound`;投影对缺失输入有兜底(disabled→off 优先,无证据→untested 兜底)。 |
| **归属 / 稳定性** | `ProviderImportDraft`/`EvidenceRecord`/`ProviderRoute`/`ProviderEndpoint` 字段权威源 = [[04-orch-registry-schema]];`RuntimeCircuit` 与 [[07-orch-fallback-circuit-probe]] 同源;`capability_state` 第二轴归 [[05-orch-capabilities-and-models]];本模块**只链接不复制**,防 drift。 |

## 4. 设计决策基础（用户原话）

> **判据(本轮反转 6 态投影 + draft 知识库归属)**："换个 app 还原样能用吗?能=③b,不能=③a。"(ux-spec §6.0 判据铁律 `00_settings-ux-spec.md:334`) → 6 态标准总结 + draft/证据知识库是 gateway 机制衍生的最佳方案、任何调模型 app 可复用 → **③b 公共**(原隐性 ③a 后端 SSOT);UI 颜色 / import 工作流 / 远端源 / 存储介质绑死那四件事 → **③a**。

> **PM #A 6 态体系**(ux-spec §4.2 `00_settings-ux-spec.md:243-244`)：标签颜色 = 该 **route** 的状态,**三页一致**;canonical 6 态 = `ready` / `historical_ready`(🔵 蓝) / `untested` / `failed`(带 reason) / `cooling_down` / `off`。

> **PM 取消 needs_setup**(ux-spec §2.1 #10 PM 裁定 `00_settings-ux-spec.md:114`)：原话 PM 问"现在有一个状态叫做needs_setup, 这是一个什么状态? 要setup什么呢??";裁定"取消原 `needs_setup` 灰态——它本质是 `failed` 的一个 reason(配置缺口),并入 failed 显红"——理由:①「配置缺口」本质是 failure、和 failed 同族;②灰色会和 untested(没测、中性)混淆、弱化"这是致命错误";③现码 `_setup_reason` 把真测试失败也揉进 needs_setup 显灰、双重混淆。

> **PM draft 赋能/写回 + 失败也是历史**(ux-spec §0.1 + §1.4 #2.4 `00_settings-ux-spec.md:11,:70`)：原话"拉取draft API, 对比模型list diff, 把draft中已证实的资料填给 model list, model list标签变成蓝色, 表明以前联通过. 有新的模型, capability...把diff的部分写回draft";"这几次的 endpoint / 模型探测结果(含失败)都要写进 draft / 证据库,不浪费(失败也是历史:哪些模型抖动 / 超时 / 不可用;下次免重探、喂蓝态)"。

> **PM 蓝↔绿 = endpoint 验证 vs model 保证**(ux-spec §4.3 + §4.2 状态分层 `00_settings-ux-spec.md:265`)：API key 页验 endpoint + draft 回填 → 模型显 🔵 蓝;role 页对模型真 probe → 升 🟢 绿。即"endpoint 验证(蓝)→ model 保证(绿)"。

## 5. 决策 + 动机

- **6 态标准总结 `state_projection` = ③b 公共内核(本轮反转)**:把"配置 + 健康 + 熔断 + 历史证据"总结成标准状态集,是 gateway 从自身机制提炼的最佳方案、任何 app 可复用;**判据**:"换个 app 还原样能用吗?能=③b"。**被反转**:原 baseline `Baseline/Alignment 差异` 与 `决策原因` 隐含"UI state 必须**后端**投影"——把它当 studio 后端职责(隐性 ③a);现按判据,投影**内核** = ③b 公共,**只有把 state 渲染成颜色 = ③a**(`module-disposition-revised.md:40`、ux-spec §6.4 横切表 `00_settings-ux-spec.md:450`)。
- **draft + 证据库知识库内核 = ③b 公共内核(本轮反转)**:记住"哪些模型存在/可用/值得试"+ 每条路线探测证据 + 可远端共享,是 gateway 背后可沉淀可共享的知识资产;**被反转**:原 baseline 把它当"studio 隔离草稿 / advisory store"(隐性 ③a 后端);现知识库**内核** = ③b 下沉,**import/apply 工作流 + 远端源选择(GitHub repo 改可配置)+ 存储介质 = ③a**(`module-disposition-revised.md:41,:61`、gateway 包 `README.md:64`)。
- **取消 `needs_setup`,统一 `failed`(红)+ reason(6 态对齐)**:消除文档自相矛盾(原正文旧 5 态 vs 文末回填段 6 态)+ 对齐 PM 裁定。心智:红=出错要你修、灰=非错误的不可用、绿=好、蓝=以前好;`needs_setup`(配置缺口)本质是 failure → 并入 `failed` + reason=`missing_config`,真测试失败 = reason=`endpoint_unreachable`/`model_failed`;权威 ux-spec §2.1 + §4.2 + 状态分层实现 gap(`00_settings-ux-spec.md:267`)。
- **新增 `historical_ready`(🔵 蓝=以前联通过)第 6 态**:蓝态归 `Capability` 域的 draft/证据子源(历史连通),是 `ui_state` 投影层的第 6 态、**不是新源域**(ux-spec §4.2 状态分层 `00_settings-ux-spec.md:263`);蓝判据从窄(只 probe-verified 历史算蓝)。
- **后端 SSOT 能避免前端易失态**:ready 不是单一字段,而是 endpoint status、route status、secret 存在性、runtime circuit(+ 历史证据)的组合;这些事实都在后端 SSOT,前端只投影、不持第二份(ux-spec §6.5 检查 2;`apps/studio/backend/app/services/llm_state_projection.py:23-56`)。**注**:SSOT 在"后端"是相对前端而言;后端里**投影内核**属 ③b(可下沉 gateway 包),与"前端不持第二份"不矛盾。
- **cooling_down 不应写成 failed**:临时网络/限流问题会过期,health store 的 retry_at 能表达"暂时不要用",而 route.status failed 会表达"配置或模型不可用"(`apps/studio/backend/app/routers/llm.py:1858-1873`;`apps/studio/backend/app/services/llm_health_store.py:70-101`)。
- **evidence library 不能直接驱动执行**:它可以来自远端 catalog 或历史观察、可信度不同;active route.status 必须由本地显式 probe/apply 写回决定(`apps/studio/backend/app/services/llm_import_drafts.py:94-128`,`:297-376`)。蓝态是历史/建议态,真 route-probe 通才升绿。
- **draft 隔离能保护 active runtime**:import draft 来自非可信 Agent/onboarding 输入,`apply_draft` 已要求冲突处理、route 默认置 `unverified_manual`,这是防止未经验证候选直接进 ready 的关键(`apps/studio/backend/app/services/llm_import_drafts.py:136-202`)。

## 6. 测试关键点

- **6 态投影**:① 双 verified → `ready🟢`;② endpoint verified + draft 有历史连通证据 + 无 live verified → `historical_ready🔵`;③ 无任何证据 → `untested⚪`;④ 缺 key/base_url/protocol/model id → `failed🔴` reason=`missing_config`;⑤ route 真探挂 → `failed🔴` reason=`endpoint_unreachable`/`model_failed`;⑥ active circuit 未过期 → `cooling_down`(带 retry_at);⑦ disabled / 模型弃用 → `off`。
- **取消 needs_setup(回归)**:任何旧产 `needs_setup` 的输入(配置缺口)现产 `failed` + reason;`ProviderUiState` Literal 不再含 `needs_setup`。
- **蓝↔绿升级**:`historical_ready🔵` 的 route 真 route-probe 通 → 升 `ready🟢`(蓝是历史态,不替代 ready)。
- **蓝判据从窄**:只 `probe-verified` 历史(真连通过)算蓝;doc-discovered / 没连过的 → 仍 `untested`(不冒充蓝)。
- **投影优先级**:同时满足多态时按 `off > failed > cooling_down > ready > 蓝 > untested` 取最高优先。
- **draft 喂投影**:`project_provider_model_state` 入参含 `draft_history`(读 `EvidenceRecord.trust_state`);现函数不读 draft → 回归点 = 必须读到历史证据才出蓝。
- **失败也写证据(PM #2.4)**:route 探测失败(含临时/确定)→ 失败证据写进知识库(下次批量探测可跳过历史失败)。
- **前端不持第二份(ux-spec §6.5 检查 2)**:切 tab / 刷新后状态仍在(从后端投影读)= 对;丢 = 前端自持 = 错。
- **draft apply 保守默认**:`apply_draft` 后 route = `unverified_manual`(非直接 verified),必须再 probe 才升 active verified。
- **probe worker 去桩(解待办)**:`probe_import_draft` 从"只改 status=probed"做成真 probe worker,真探测 + 真写历史连通证据(蓝态依赖它)。
- **capability_state 第二轴(D2)**:`_capability_state` 从二值升四态(unknown/callable_only/partial/known),与 `ui_state` 正交。

## 7. 涉及 region / platform

- **③b** `packages/graph-agent-gateway`(**待下沉**):6 态投影内核(现 `services/llm_state_projection.py`)、draft+证据库知识库内核(现 `services/llm_import_drafts.py`)、熔断持久化内核(现 `services/llm_health_store.py`,与 07 同)、`ProviderImportDraft`/`EvidenceRecord`/`ProbeResult` 数据结构(已在 `registry/schema.py` + `registry/probe_contracts.py`,归 04);list-models 解析 + 批量探测编排内核(现 `routers/llm.py` 探测段)。
- **③a** `apps/studio/backend` + 前端:import/apply 工作流(`apply_draft` 冲突处理 + 录入 UI)、状态颜色/文案渲染、远端源选择(现硬编码 GitHub repo → **应改可配置**)、存储介质(draft/证据/健康库存哪个文件 / SQLite 路径)、HTTP `/api/llm/*` 探测/draft 端点薄壳(归 14)、批量探测进度 UI。
- **② Rust**:N/A(凭证/角色/证据/健康数据永不 Rust)。

## 8. gaps / 待设计

- **代码下沉**(后续工程,非本轮):6 态投影内核 + draft/证据知识库内核 + 熔断持久化内核 → gateway 包;颜色渲染 / import-apply 工作流 / 存储介质 / 远端源配置留 ③a。
- **待办(去桩,PM 已拍板必做 D2)**:把 import draft probe 从"标记 probed"升级为真实 worker;当前 `probe_import_draft`(只把 draft.status 改成 probed,注释说真 agent probing 由后续 worker 处理)没有实际探测逻辑(`apps/studio/backend/app/routers/llm.py:871-876`)。**蓝态 + 真探测结果回写都依赖它去桩**(`routers/llm.py:872`)——做成真 probe worker。
- **待办(6 态 Literal 改造)**:`ProviderUiState` Literal 去 `needs_setup`、加 `failed`(带 reason)+ `historical_ready`(`services/llm_state_projection.py:12`);`_setup_reason`(`:49-56`)改产 `failed` + reason(`missing_config`/`endpoint_unreachable`/`model_failed`)而非 `needs_setup`;`project_provider_model_state`(`:23-46`,现只读 endpoint+route+circuits、**不读 draft**)加"draft 是否有该 route 历史连通"输入。
- **待办(蓝态 contract)**:把 `historical_ready🔵` 与 `ready🟢` 的关系写成稳定 contract(蓝是历史/建议、绿是 live verified、蓝真探通升绿);当前 compact model status 还能从 evidence library 推导 `probe-verified` 展示标签、但 projection state 没有该枚举(`apps/studio/backend/app/routers/llm.py:4076-4106`)——收口为蓝态。
- **待办(evidence 回写规则)**:为 evidence 回写 active route status 制定规则,例如仅本地成功 probe 才能写 `verified`、远端 evidence 只能作为建议(`apps/studio/backend/app/services/llm_import_drafts.py:297-376`)。
- **待办(远端源可配置)**:`sync_remote_evidence_library` 的远端源现硬编码 GitHub repo,应改可配置(③a 注入)(`apps/studio/backend/app/services/llm_import_drafts.py:297-376`;`module-disposition-revised.md:61`)。
- **疑点(circuit 排序)**:`_select_active_circuit`(active circuit 选择 helper)当前用 `-retry_at.timestamp()` 排序、倾向选更晚 retry_at 的 circuit;如果 UI 想展示"最具体 scope 优先"或"最快可重试",需要调整排序规则(`apps/studio/backend/app/services/llm_state_projection.py:72-78`)。

## 已实现 / 与 baseline 差异

1. 已实现:后端已有 `project_provider_model_state`,并且 router 与 materializer 都在调用它,说明 UI 与编排已经开始共享同一投影口径(`apps/studio/backend/app/services/llm_state_projection.py:23-46`;`apps/studio/backend/app/services/llm_role_materializer.py:131-154`)。**归属:投影内核 = ③b(待下沉)。**
2. 已实现:route force probe 对 success、temporary failure、hard failure 三类结果有不同持久化路径,这是 SSOT 回写的基础(`apps/studio/backend/app/routers/llm.py:1818-1886`)。
3. 已实现:runtime circuit 是 SQLite 持久化,不是前端内存态(`apps/studio/backend/app/services/llm_health_store.py:26-101`)。**归属:熔断持久化内核 = ③b(待下沉,与 07 同);SQLite 路径 = ③a 注入。**
4. 差异(**6 态对齐**):baseline 投影是旧 5 态(含 `needs_setup`);MVP1 取消 `needs_setup`(并入 `failed` + reason)、新增 `historical_ready🔵`——共 6 态。`ProviderUiState` Literal(`:12`)与 `_setup_reason`(`:49-56`)需改造。
5. 差异(**判据反转**):baseline 隐含把投影 + draft 当 studio 后端 SSOT(隐性 ③a);MVP1 明确投影内核 + 知识库内核 = ③b 公共(待下沉),仅 UI 颜色 / import 工作流 / 远端源 / 存储介质留 ③a。
6. 差异:baseline 仍存在从 evidence library 推导 compact model `probe-verified` 的展示路径;MVP1 应明确它**收口为蓝态 `historical_ready`**(advisory 历史态),不能替代 `project_provider_model_state` 的 6 态(`apps/studio/backend/app/routers/llm.py:4076-4106`)。
7. 差异:baseline 的 import draft probe 只是标记 draft.status=`probed`;MVP1 若要宣称 probe status SSOT,需要真实 probe worker(去桩,蓝态依赖)或移除"probed"歧义(`apps/studio/backend/app/routers/llm.py:871-876`)。
8. 差异:baseline `apply_draft` 把 route 写成 `unverified_manual`;MVP1 应保持这个保守默认,并要求后续真实探测回写 active route status(`apps/studio/backend/app/services/llm_import_drafts.py:182-194`)。

## 决策原因（保留 baseline 原文,补反转 + 6 态对齐)

1. UI state 投影内核必须存在,原因是 ready/failed/cooling_down 需要同时看 endpoint、route、secret、runtime circuit(+ 历史证据);这些数据前端不应自己拼(`apps/studio/backend/app/services/llm_state_projection.py:23-56`)。**反转补:此"投影"的内核 = ③b 公共(可下沉 gateway),原 baseline 隐含的"必须 studio 后端"只是相对前端的 SSOT 表述,不与下沉冲突;前端只渲染颜色。**
2. runtime circuit 单独持久化,原因是限流/网络冷却不等于 route 永久 failed;`_force_probe_route` 对 timeout/rate_limited/network_error 打开 circuit,但返回原 route,就是这个语义(`apps/studio/backend/app/routers/llm.py:1858-1873`)。**反转补:熔断持久化内核 = ③b(与 07 同),SQLite 路径 ③a 注入。**
3. draft 必须隔离,原因是 import draft 来自非可信 Agent/onboarding 输入;`apply_draft` 需要显式处理 endpoint collisions,且 route 应用后仍是 `unverified_manual`(`apps/studio/backend/app/services/llm_import_drafts.py:136-202`)。**反转补:隔离/冲突处理工作流 = ③a;draft 数据结构 + 知识库内核 = ③b 公共。**
4. evidence library 适合作为建议材料,原因是它是 append-only 并可远端同步,但不应替代 active credentials 的可执行状态(`apps/studio/backend/app/services/llm_import_drafts.py:94-128`,`:297-376`)。**反转补:append-only 知识库内核 + 远端合并去重 = ③b 公共;远端源选择(GitHub repo 改可配置)= ③a。**

**判据反转 + 6 态对齐(2026-06 第四轮)**:6 态标准总结 `state_projection` + draft/证据库 `import_drafts` 从"隐性 ③a 后端 SSOT/投影"反转为"③b 公共能力内核(待下沉)";`needs_setup` 取消并入 `failed`+reason、新增蓝态 `historical_ready`,正文从旧 5 态对齐到 canonical 6 态(消除与文末回填段的自相矛盾);权威源 ux-spec §4.2 + §6.0 + §6.4 + 归属表 `module-disposition-revised.md:40-41` + gateway 包 `README.md:64,74`。

## 代码索引 clues

- `apps/studio/backend/app/services/llm_state_projection.py:12`:`ProviderUiState` Literal——**6 态对齐**:去 `needs_setup`、加 `failed`+`historical_ready`。
- `apps/studio/backend/app/services/llm_state_projection.py:23-46`:6 态投影流程——**= ③b 公共内核(本轮反转,待下沉)**;MVP1 加 `draft_history` 入参。
- `apps/studio/backend/app/services/llm_state_projection.py:49-99`:`_setup_reason`/circuit 匹配/scope priority——`_setup_reason` 改产 `failed`+reason。
- `apps/studio/backend/app/routers/llm.py:460-567`:endpoint test 回写 active credentials(③a 壳 + ③b 写回内核)。
- `apps/studio/backend/app/routers/llm.py:782-818`:route probe 回写 verified/capabilities。
- `apps/studio/backend/app/routers/llm.py:1818-1886`:force route probe 回写 missing_key/success/circuit/failed(success path 补写成功证据)。
- `apps/studio/backend/app/routers/llm.py:871-876`:`probe_import_draft` 桩——**待去桩做真 probe worker(蓝态依赖,PM 拍板 D2)**。
- `apps/studio/backend/app/routers/llm.py:4076-4106`:evidence-derived `probe-verified` 展示路径——**收口为蓝态 `historical_ready`**。
- `apps/studio/backend/app/services/llm_health_store.py:34-101`:runtime circuit 写入和读取——**熔断持久化内核 = ③b(待下沉);SQLite 路径 ③a 注入**。
- `apps/studio/backend/app/services/llm_role_materializer.py:48-90`:projection 影响 fallback_chain 物化(跳过 `failed`/`off`、`cooling_down` warning)——6 态对齐后跳过 `failed`(原 needs_setup 已并入)。
- `apps/studio/backend/app/services/llm_import_drafts.py:55-128`:draft/evidence 创建、读取、追加——**知识库内核 = ③b 公共(待下沉)**。
- `apps/studio/backend/app/services/llm_import_drafts.py:136-202`:draft apply 到 active credentials——apply 工作流 ③a;route 默认态 schema ③b。
- `apps/studio/backend/app/services/llm_import_drafts.py:297-376`:remote evidence library merge——合并去重内核 ③b;**远端源(GitHub repo)改可配置 ③a**。

## 覆盖率

本 alignment 覆盖 08 brief 的全部要求:`services/llm_state_projection.py:project_provider_model_state`(6 态投影)+ `services/llm_import_drafts.py`(draft + 证据库)两个核心对象已落到真实 `file:line`,并补齐两处判据反转(6 态投影内核 = ③b、draft 知识库内核 = ③b)+ 6 态对齐(取消 needs_setup、补蓝态)。为说明"探测→持久化→投影→复用",额外引用 router、health store、role materializer 作为证据线索,均标注 ③a/③b 归属。

## 交叉引用（链接,不复制）

- [[02-orch-role-resolution]]:materialize 消费 6 态投影排 fallback_chain（已取消 needs_setup,跳过 `failed`/`off`）
- [[05-orch-capabilities-and-models]]:`capability_state` 第二轴 + identity/notable/model_groups 同属下沉知识库
- [[07-orch-fallback-circuit-probe]]:probe 产证据 + 熔断写 health store（`SqliteLlmHealthStore` 同源反转 ③b）
- [[04-orch-registry-schema]]:`ProviderImportDraft`/`EvidenceRecord`/`ProviderRoute`/`ProviderEndpoint` 字段权威源（本模块只链接）
- [[03-orch-credentials-endpoints]]:endpoint test 回写 active credentials + base_url 归一化
- [[14-api-router]]:HTTP `/api/llm/*` 探测/draft 端点 = ③a 薄壳
- ux-spec §4.1(draft)/§4.2(6 态体系)/§4.3(测试落点)/§6.0(判据)/§6.4(横切四层) · 归属表 `module-disposition-revised.md`（08 行两处反转 + 远端源可配置）· gateway 包 `README.md` §3 B/D
