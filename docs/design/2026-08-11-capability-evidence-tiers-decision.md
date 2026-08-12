# 能力事实的来源分层，与探测词表缺的那一格（决议）

> **日期**：2026-08-11
> **裁决人**：用户（本文第 0 节逐条列出原话与它批准的范围）
> **状态**：已裁决，待实施。实施拆成四个 PR，见 §5。
> **上游决议**：`2026-08-10-preferences-fit-the-route-decision.md`（设置即偏好；effort 能力记的是「这个名字它收不收」）· `2026-08-10-runtime-settings-are-preferences-decision.md`（每项设置的下场怎么判）· `2026-08-10-gateway-module-tree-and-probing-decision.md`（probing 域的边界）

---

## 0. 这份决议在裁什么

三件互不相干的事，追到底是同一个问题：**一条能力记录说的是「谁说的」，而系统今天只认得清其中一种说法。**

1. **台账 P9 / P12**：多模态探测两个方向都推不动能力位。探出「认图」时结论只进证据层、进不了能力位；探出「不认图」时——模型原话 `Model only support text input`——被记成 `probe_status: invalid_model`，证据层随即写 `trust_state: probe-failed`。一句关于能力的明确回答，被记成「这个模型是无效的」。
2. **用户 2026-08-11 裁决**：「加」——同意为 `ProviderProbeStatus` 这个封闭词表增加成员。
3. **用户 2026-08-11 提出**：「能不能让 copilot 去 research 官网然后给他配好填 capability 的工具？作为和远程 draft 一样的证据，再进行实测。」——批准范围见 §0.1。

### 0.1 用户批准的原话与范围

> 「1. DeepSeek官网怎么说呢？能不能让copilot去research官网然后给他配好填capability的工具？作为和远程draft一样的证据，再进行实测.
> 2. 加
> 3. anthropic先不测」

随后对本文 §2 提出的方案回复「按你建议的推进」。因此本决议的授权范围是：**§1（探测词表加成员）+ §2（文档来源的能力由 copilot 现场读文档写入，作为不如实测的证据层）+ 两者共同要求的 §3 清障**。Anthropic 路由暂不做真机验证（账户余额不足，五次 effort 探测全部返回 `Your credit balance is too low`）。

---

## 1. 事实基座（本决议据以推导的证据）

### 1.1 厂商文档自己就不一致，托管方之间更不一致

DeepSeek 官方文档对同一件事有三套取值：

| 面 | 字段 | 官方取值 | 出处 |
|---|---|---|---|
| OpenAI 格式 `/chat/completions` | `reasoning_effort` | `low` / `high` / `max`；`medium` 与 `xhigh` 折叠成 `high` | <https://api-docs.deepseek.com/api/create-chat-completion> |
| Anthropic 格式 | `reasoning.effort` | `none` / `low` / `high` / `max` | <https://api-docs.deepseek.com/guides/thinking_mode/> |
| Responses 格式 | `output_config.effort` | `low` / `high` / `max` | 同上 |

原文（OpenAI 面）：「Controls the reasoning effort of the model. The default effort is `high`. For compatibility, `medium` and `xhigh` are mapped to `high`.」

同一批模型经转售方提供时，规则互相矛盾：OpenRouter 的 v4-flash 页写 `xhigh` 映射到 max reasoning，与 DeepSeek 自己的 `xhigh→high` 相反；SiliconFlow 写 `low` 与 `medium` 都映射到 `high`，与 DeepSeek 的 flash `low→low` 相反。

**推论**：文档来源的能力**只能按路由（端点 × 模型）记，并且必须带上出处 URL**。按模型名记会把互相矛盾的说法混成一条。

### 1.2 文档没说的那一格，实测答了，而且答案与「宽松处理」的读法相反

没有任何厂商文档说明「送一个集合外的 effort 值会怎样」。DeepSeek 唯一沾边的一句「Unsupported parameters are silently ignored」印在 **Responses API** 指南的顶层参数一节，作用域不覆盖 `/chat/completions`。

仓内有第一手实测（`docs/design/2026-08-10-preferences-fit-the-route-decision.md:90-107`）：

```
asked effort='banana' -> invalid_model
  HTTP 400 (invalid_request_error): Failed to deserialize the JSON body into the target
  type: reasoning_effort: unknown variant `banana`, expected one of `none`, `minimal`,
  `low`, `medium`, `high`, `xhigh`, `max`
```

三个后果：provider **确实校验**这个字段；它真实认的枚举有七个名字，与文档写的三值集合冲突（该决议因此写下「所以这一行文档过时，以实测为准」）；**而这句明确回答被记成了 `invalid_model`**。

### 1.3 同一个误分类族有两个成员，不是一个

| 线上原话 | 讲的是什么 | 今天记成 |
|---|---|---|
| Ark：`Model only support text input`（2026-08-11T19:00:42Z 真机） | 这个模型不吃图 | `invalid_model` → `trust_state: probe-failed` |
| DeepSeek：`unknown variant \`banana\`` | 这个参数值不存在 | `invalid_model` |

**所以新成员必须按族定义，不能只为图片开一个口子**——否则 effort 那半边继续错着。

### 1.4 多模态探测的判据早就写在设计里，是代码把它丢了

`packages/graph-agent-gateway/src/graph_agent_gateway/probing/wire.py:217-219` 的 docstring 原文：

> 「``multimodal=True`` 在探测消息里加一张测试图(#11):provider 接受(2xx)=该模型接受图像输入(input_modalities 含 image),4xx 拒绝=不支持。」

设计意图明写着 4xx = 不支持；实现把它落进 `probe_status(answer, model_not_found_status="invalid_model")`，结论丢失。

### 1.5 `agent_draft` 这个槽位早就留好，且零个生产写者

`packages/graph-agent-gateway/src/graph_agent_gateway/registry/schema.py:33`：

```python
CapabilitySource = Literal["api_list", "provider_doc", "agent_draft", "manual", "probed_verified"]
```

全仓**代码**里 `agent_draft` 只出现在三处：这行定义、前端 TS 镜像（`apps/studio/frontend/src/api/llm.ts:16`）、一条网关测试（`packages/graph-agent-gateway/tests/test_registry_catalog.py:131`）。此外它出现在三份 git 已跟踪的规格文档里（`.kiro/specs/llm-provider-intelligence-v2/design.md`、`requirements.md`、`.kiro/specs/studio-llm-roles-model-groups/design.md`，共 8 处描述性文字，不是可执行代码）。**没有任何生产代码写它。**

### 1.6 前端只有一处按 source 判定「实测」，而 effort 那处完全不看 source

- 唯一的实测门：`apps/studio/frontend/src/api/llm.ts:1671-1675` `routeAcceptsImageVerified`，要求 `cap.source === 'probed_verified'`。
- 无门的地方：`apps/studio/frontend/src/components/studio/llm-effort.ts:44` `routeEffortLevels()` 只读 `capabilities?.reasoning_effort?.value.values`，**不看 source**。于是读时注入的 `provider_doc` 档位和真测出来的 `probed_verified` 档位在角色 effort 下拉里长得一模一样。

### 1.7 社区证据可以让路由出蓝，而且这份不对称是它自己写下来的

`apps/studio/backend/app/services/llm_credentials_evidence.py:100-105` 的 `route_is_probe_verified` 只看 `evidence_type` 与 `trust_state`，**没有 provenance 判断**；同文件第 121 行的 docstring 自陈（该 docstring 属于 `probe_evidence_counts`，跨 114-122 行）：「Community evidence still projects blue via `route_is_probe_verified`.」

### 1.8 `PUT /llm/routes/{id}` 会抹掉该路由所有实测能力

- `RouteEditableUpdate.capabilities` 与 `.metadata` 默认 `{}`（`apps/studio/backend/app/routers/llm.py:387-394`）；
- `put_route_metadata` 用 `model_copy(update={... "capabilities": request.capabilities, "metadata": request.metadata})` **整体替换**（`:1470-1478`，函数体 `:1463-1486`）；
- 全仓**生产**调用方只有一个：copilot 工具 `update_llm_route`（`apps/studio/backend/app/services/copilot_tools.py:1837-1842`），它**只传 display_name / canonical_id / status**；
- 前端一次都没调过这个端点（`apps/studio/frontend/src` 全域无 PUT `/llm/routes/`）；
- 另有一处测试经 HTTP 调它并**恰恰传了** `capabilities`/`metadata`（`apps/studio/backend/tests/routers/test_llm_registry_api.py:5589-5598`）——它断言的是 profile-apply 冲突，从没看过这两个字段，所以 D7 删字段时同批改掉它即可。

即：一次被用户点了「同意」的路由改名，会清空该路由的全部测量。

---

## 2. 决策

### D1 · 能力事实分三层，排序按「谁说的」，不按「什么时候写的」

| 层 | source | 谁写 | 含义 |
|---|---|---|---|
| 实测 | `probed_verified` | 探测 | 我们自己发过请求、读过回答 |
| 文档 | `provider_doc` / `agent_draft` | 代码内快照 / copilot 现场读文档 | 厂商说的 |
| 清单 | `api_list` | 端点自报 | 端点列出来的 |

**实测层永远压过文档层**，与写入先后无关。文档层只做两件事：**给人看**，和**给探测出题**。

### D2 · 文档来源的能力落在 `agent_draft`，不新增 source 成员

闭集里这个成员本来就是为「agent 起草、待验证的声称」留的（§1.5）。用户要的「和远程 draft 一样的证据」正是这个层级。

### D3 · 文档来源的能力必须带出处 URL，并按路由记

依据 §1.1：厂商文档自相矛盾、托管方互相矛盾。一条 `agent_draft` 能力必须能回答「这是谁家哪一页说的」，否则它不是证据，只是一句转述。

### D4 · `agent_draft` 不满足任何实测判据

它**不出蓝**、不满足 `routeAcceptsImageVerified`、在 `resolve/lint.py:74` 不与 `manual` 同列、不做 `resolve/resolver.py:498` 的运行时默认值。§1.7 那条社区证据出蓝的不对称是**已知缺陷**，不是可援引的先例。

### D5 · 探测词表增加一个成员：模型明确回答了，答案是「不」

**判据不靠词表，靠差分。** 一个与已知可用请求**只差一样东西**的请求被 request-scope 4xx 拒绝，就是关于那一样东西的裁决，而不是关于模型是否存在的裁决。这与 `call/chat_model.py:458-470` 已经在用的 `dropped_rejected_settings` 是同一个手法（判据注释在 `:458-467`，决策名在 `:470`；另一处入口在 `:353`），它的注释写得很清楚：

> 「The provider read this request and refused it — the one failure a parameter can cause. ... No table of provider wordings can do it, and the wordings are what providers keep changing.」

**「只差一样东西」今天只成立一半，另一半要本决议去建。** 探针确实知道自己这次**带了什么**——`multimodal` 是 `probing/wire.py:213` 的显式布尔参数，effort 值在 `runtime_settings` 里（构造见 `probing/questions.py:95-97`），两个判决点（`wire.py:190`、`wire.py:252`）都拿得到。它今天**拿不到的是基线**：`POST /routes/{id}/probe-multimodal`（`apps/studio/backend/app/routers/llm.py:1418-1455`）发图之前既不跑同候选的纯文本探测，也不检查 `route.status == "verified"`，前端按钮同样不设门（`CopilotModelGroupCard.tsx:244`）。所以：

- **多模态探测**：PR-3 必须**显式建立基线**（同候选先纯文本答一次，或要求该路由已 `verified`），再把「带图被 request-scope 4xx 拒」判成「不吃图」。没有基线就下这个判断，等于把「这条路由整个不通」误判成「它不吃图」。#731 引入的 `_rejects_our_payload`（图**形状**被拒：尺寸/格式/过大）保留，作为「我们自己的 payload 坏了」的出口，优先于本判据。
- **effort 逐档探测**：基线已经有了——整批只差 effort 这一个值，且批内自带 `EFFORT_CONTROL_LEVEL` 对照档（`probing/questions.py:71-80`）。某一档被 request-scope 4xx 拒 ⇒ 这条路由不收这个名字。

**新成员不进 `INCONCLUSIVE_PROBE_STATUSES`**：它是一个确定的回答，不是「没问出答案」。

**新成员不写 `trust_state: probe-failed`**：探测成功了，答案是负的。台账 P12 原文：「裁之前不许随手把它映射成 `error`——那是把「一个明确的回答」谎报成「没问出答案」」——同理也不许记成失败。

**那它写什么？`EvidenceTrustState` 是第二个封闭词表，本决议一并裁。** 它今天 7 个成员（`registry/schema.py:34-42`，含 `stale`），而 `probe_evidence_counts`（`llm_credentials_evidence.py:113-142`）只往 verified / failed 两个桶里数——第三种取值会让「总数 = 两桶之和」当场不成立，Settings 的证据计数（`routers/llm.py:2607`）、tooltip（`core/adapters/gateway.py:660-679`）、社区上传门（`services/community_catalog.py:157`、`community_catalog_runtime.py:46`）都读它。**裁决：复用既有成员 `probe-verified`**——这次探测确实问到了答案，答案是「不支持」，能力位记 `supported: false`。它是一次成功的测量，不是第三种信任度；证据计数照旧两桶相加，无新成员、无新分支。

### D6 · 多模态实测结论必须落到能力位（P9 的正面那一半）

探通了就建一条 ready `VerifiedProfile`，让既有通道（`llm_route_capabilities.py:21-53` 的 `verified_profile_route_capabilities`）把 `input_modalities` 写成 `source="probed_verified"`。**不发明新机制**：同一个仓里 `routers/llm.py:4022` 早就有「探通了就建 ready profile」的现成写法，多模态探测只是没接上。

### D7 · `PUT /routes/{id}` 不再接受 capabilities 与 metadata

依 §1.8 与 AGENTS.md「No backward compatibility」：**删字段，不加兼容**。这个端点的名字是「可编辑元数据」，能力是证据不是可编辑元数据；它唯一的生产调用方从不传这两项，前端根本不调它。删掉之后，「一次**改名**抹掉所有测量」这个状态**在类型上不可能存在**。

**这条只封住改名那一条路，抹测量的第二条路还开着。** `apps/studio/backend/app/routers/llm.py:5504-5551` 的 `_upsert_third_party_model_probe_routes` 对**已存在**的路由只回填 `display_name` 与 `metadata`，capabilities 由 `_provider_route(...)`（`:5593-5644`）从 catalog / 文档重新推导后**整体覆盖**，`probed_verified` 的测量被丢弃；这条路径经 `POST /llm/endpoints/{id}/models/test` 由前端 API Keys 的手动测模型按钮实际可达。同一文件里的对照组 `_upsert_discovered_routes`（`:5414-5501`）以 `**existing.capabilities` 打底、不抹——所以这是**单个函数的缺口**，不是全局设计。**它正是 PR-3 要写入的 `input_modalities: probed_verified` 会被抹掉的地方，因此 PR-3 必须连它一起修**（见 §5）。「在类型上不可能存在」只对 PUT 改名成立，不得读成「测量再也不会被抹」。

### D8 · copilot 读文档的能力

**copilot 今天已经能读网页，只是每读一次弹一张审批卡。** `build_options`（`apps/studio/backend/app/services/copilot.py:808-841`）既不传 `tools` 也不传 `disallowed_tools`——按 SDK 契约 `allowed_tools` 只做免提示放行、`tools` 才圈定工具面，所以 CLI 自带的 WebFetch / WebSearch 一直在模型的工具面里；它们不在 `_DECLARATIVE_ALLOWED_TOOLS`（`:104-130`）里，于是每次调用都落到 `can_use_tool`（`:621-670`）挂起成审批卡。

因此：

- **读网页不需要新造工具**，只需把 `WebFetch` 加进免审批名单——它只读、无文件系统副作用，与名单里已有的 Read/Glob/Grep 同类。判据 D1 要断言的是**不弹卡**，不是**能读**（能读今天就成立）。
- **写能力**（`draft_route_capability`）属于写配置真相：**只要它不进 `_DECLARATIVE_ALLOWED_TOOLS`，默认档就会把它挂起成阻塞式审批卡**（`:621-670` → `_hold_for_tool_approval` `:467-512`）。`_MCP_APPROVAL_WRITE_TOOLS`（`:137-161`）是**显式登记 + 测试锁，不是执行机制**（该 frozenset 零个生产读者，注释自陈）；按既有纪律仍要登记，并补 `_WRITE_TOOL_ACTION_LABELS`（`:163-182`，缺了审批卡只显示原始工具名）。与 `update_llm_role`（`:153`）同级。
- 新工具的登记面共 7 处，PR-4 逐个走到：`copilot_tools.py` 的 `@tool` 定义 + `_copilot_mcp_tools()` 注册表（`:1935-1982`，有漂移测试锁，漏了就是死工具）· `_MCP_APPROVAL_WRITE_TOOLS` · `_WRITE_TOOL_ACTION_LABELS` · 确保**不进** `_DECLARATIVE_ALLOWED_TOOLS` · 对 CLI 表面显式裁决 `cli_mcp_surface.py:21` 的 `CLI_EXCLUDED_TOOL_NAMES`（默认自动暴露）· 核对 `apps/studio/tauri/src/lib.rs:1056-1076` 的 CLI allowlist · 写进 `app/agents/knowledge/KB-13-studio-gates-tools.md`。前端无需登记（审批卡按 `mcp__studio__` 前缀通用渲染）。
- 该工具**不经 `PUT /routes/{id}`**（见 D7），只做 capabilities 的定点合并。

---

## 3. 关键设计决定（实施时不得偏离）

1. **新成员的判据参数化在调用点，不在词表里。** `probe_status(...)` 由调用方告诉它「这次请求变的是什么」；判决器不猜。多模态探测传「变的是图」，effort 探测传「变的是 effort 值」，端点列模型探测什么都不传（它没有差分）。
2. **`_rejects_our_payload` 优先。** 先排除「我们自己的请求坏了」，再谈「模型不支持」。顺序反了会把 #731 修好的东西重新弄坏。
3. **`agent_draft` 与 `probed_verified` 在 UI 上必须看得出区别。** §1.6 那处不看 source 的 effort 下拉是现役缺口：文档档位与实测档位今天长得一模一样。补文档层之前必须先让这两者可区分，否则是把一个已有的混淆放大。
4. **能力合并只有一处权威。** `llm_route_capabilities.py` 与 `role/materialization.py:494-525` 今天是两份近乎相同的实现且判据不同（前者读显式字段，后者搜子串），可能对 `thinking_protocol` 得出不同结论。本决议不在此处修它，但**新写入路径只走前者**，并把这条差异记进台账。
5. **不为 Anthropic 做真机验证**（用户裁决 3）。离线测试照常覆盖。

---

## 4. 验收判据（因果验证：动作之后的可观察结果）

**A. 探测词表加成员**

- A1. 构造一次多模态探测，provider 返回 400 且原文为 `Model only support text input` ⇒ 结果状态是新成员，**不是** `invalid_model`；该路由的证据 `trust_state` **不是** `probe-failed`。以断言这两点的测试为证。
- A2. 同一条路由的图**形状**被拒（`_rejects_our_payload` 词表命中）⇒ 仍落 `error`，#731 的行为不变。以断言的测试为证。
- A3. effort 逐档探测中某一档被 400 拒 ⇒ 该档的状态是新成员；整批仍可判读（新成员不在 `INCONCLUSIVE_PROBE_STATUSES` 内），`accepted_effort_levels` 的结果与改动前逐字相同。以断言的测试为证。
- A4. 这个词表在仓里被**手抄了六份、散在四个文件**：后端 `app/services/model_probe.py:20-30`（类定义 `:18`）、`app/routers/llm.py:426-436`、`app/models/llm_config.py:53-65`；前端 `api/llm.ts:261`/`:339`/`:372`。逐份处置，不是一律增员——
  - `app/models/llm_config.py:53-65`（`TestStatus`）已 export 但**全仓零 importer**，按「删旧路径」**直接删除**，不给它补成员；
  - `api/llm.ts:372`（`ProviderModelTestResult.status`，后端 `EndpointModelTestResult` 的线上镜像）**必须增员**，并顺带补齐它今天就缺的成员；
  - `api/llm.ts:261`/`:339` 是端点级投影（各自刻意多一个非网关成员 `untested` / `missing_api_key`），**不逐一对齐**，只复核新成员到不了那里。
  - 注意 `npm run typecheck` 对不对齐**都绿**，作不了这条的证；判据是逐份处置的记录 + 下面 A7。
- A5. 三个 `frozenset` 状态集合（`INCONCLUSIVE_PROBE_STATUSES`、`_STRUCTURAL_PROBE_STATUSES` `llm.py:4968-4970`、`llm.py:3272` 那个匿名熔断集合）**逐个复核并留下判断记录**——mypy 拦不住它们（都标注为 `frozenset[str]`）。
- A6. i18n 键表补齐新成员，共三张：`locales/{en,zh-CN}/errors.json` 的 status 表、同两份的 `settings.json`、以及 **`errors.json` 的 `codes.*` 表**（`metadata.reason_code` 走 `llm.py:3293` 写入、`lib/llm-error-messages.ts:21-25` 渲染，今天连 `invalid_model` 都缺、已落兜底文案）。补齐前 `translateTestStatus` 会回落成原始字符串，以缺键时的渲染为反证。
- A6b. `apps/studio/backend/tests/routers/test_inconclusive_probe_is_not_a_verdict.py:17-19/:29` 把词表二分硬编码，新成员必须加进 `:29`——否则测试仍绿，但已停止覆盖全词表。
- A7. **新成员不得在到达界面之前被悄悄降级。** 它要穿过三层默认分支，每层都要有断言：① `api/llm.ts:1446-1469` `endpointTestStatus` 默认 `return 'error'`、`:1376-1397` `routeFailureScope` 默认 `'unknown'`；② `ManualModelTestPanel.tsx:49-70`（default → 「测试失败」）、`:77-79`（`status === "ok" ? "ready" : "failed"` → 红徽章）、`:81-93`（default → null，tooltip 丢原因）；③ `ProviderCard.tsx:825`（未知状态涂 destructive 红）、`:910`、`:1079`、`settings/llm-roles/provider-state-badge.tsx:108`。这些分支**编译期全绿**，只有断言测试能拦住。
- A8. `EvidenceTrustState` 不新增成员（D5 已裁复用 `probe-verified`），以 `probe_evidence_counts`（`llm_credentials_evidence.py:113-142`）「总数 = verified + failed」仍然成立为证。

**B. 多模态实测进能力位**

- B1. 多模态探测成功 ⇒ 该路由 `capabilities.input_modalities.source == "probed_verified"` 且值含 `image`。以断言的测试为证。
- B2. `routeAcceptsImageVerified` 对该路由返回 `true`——这条判据在改动前**不可能为真**（P9 记录）。

**C. `PUT /routes/{id}` 不再抹能力**

- C1. `RouteEditableUpdate` 上**不存在** `capabilities` / `metadata` 字段（`extra="forbid"`，传了就 422）。
- C2. 一条带实测能力的路由经 `update_llm_route` 改名后，能力**逐字不变**。以断言的测试为证——这条测试在改动前必须是红的。

**D. 文档来源的能力**

- D1. 读网页**不弹**审批卡（能读今天就成立，见 D8），写能力**必弹**审批卡。
- D2. 写入的能力 `source == "agent_draft"`，`observed_at` 记观察时间，出处 URL 落在**为此新增的 `CapabilityValue` 字段**上——该模型（`registry/schema.py:78-86`）今天是 `extra="forbid"` 且只有 value/source/observed_at/message，**没有 URL 位**，所以 PR-4 必须含网关 schema 改动 + 前端 TS 镜像（`api/llm.ts:20-25`）同步，**不许把 URL 塞进自由文本 `message`**。
- D3. 该能力**不出蓝**、`routeAcceptsImageVerified` 对它返回 `false`、lint 不把它当 `manual`。以断言的测试为证。
- D4. UI 上 `agent_draft` 与 `probed_verified` 可区分（设计决定 3）。
- D5. 一次真机：让 copilot 读 DeepSeek 官方文档写下 effort 档位，再跑实测，两者在界面上分得清、且实测压过文档。

---

## 5. 实施拆分（一任务一 PR）

| # | 内容 | 依赖 |
|---|---|---|
| PR-1 | D7：`PUT /routes/{id}` 删掉 capabilities/metadata 字段（判据 C） | 无。**先做**：它是现役 bug，且后面两个 PR 都不能踩它 |
| PR-2 | D5：探测词表加成员 + 差分判据 + 全部消费点（判据 A1–A8） | 无 |
| PR-3 | D6：先建基线（同候选纯文本先答一次），再让多模态实测进能力位；**同批修 `_upsert_third_party_model_probe_routes` 的抹能力缺口**（判据 B） | PR-2（负面那一半要先能表达） |
| PR-4 | D2/D3/D4/D8：`CapabilityValue` 加出处 URL 字段 + `WebFetch` 进免审批名单 + `draft_route_capability`（7 处登记面）+ UI 可区分（判据 D） | PR-1 |

---

## 6. 本决议不裁的（明确留白）

- **社区证据出蓝的不对称**（§1.7）：已知缺陷，与本决议同轴但不同题，另立台账条目，不夹带。
- **两份能力合并实现的分歧**（设计决定 4）：记档，不在本决议修。
- **`official_capability_sources.py` 里写死的 DeepSeek 快照已过时**：它的条件仍含 `deepseek-chat` / `deepseek-reasoner`，而官网写明这两个名字已于 2026-07-24 停用。属于「代码里的文档快照会过期」——正是 D2 要解决的病，但存量那张表的清理另开。
- **Anthropic 路由的真机验证**：用户裁决暂不做。

---

## 7. 本文的引用被对抗性核过一遍

初稿写完后，五席独立核验被要求**去证伪**本文每一条坐标与引文（打开该行核对，而不是确认符号存在；对「全仓只有一处 / 零个 / 从不」这类绝对断言主动找反例）。48 条里 **23 条被判错或不精确**，已逐条改进正文。改动最大的三处记在这里，因为它们改的是方案而不是行号：

1. **D8 原来写「copilot 今天没有任何 web 工具」——错。** WebFetch / WebSearch 本来就在工具面里，只是每次弹审批卡。于是「让 copilot 读文档」从「造一个工具」缩成「把 WebFetch 加进免审批名单」。
2. **D5 的差分判据原来当成现状引用——不成立。** 探针知道自己带了什么，但**没有已知可用的基线**：多模态探测发图前不跑纯文本、也不看 `route.status`。基线成了 PR-3 要建的前置条件，而不是可以直接用的事实。
3. **D7 原来宣称删完字段「测量再也抹不掉」——过头了。** 还有第二条抹能力的路（`_upsert_third_party_model_probe_routes`），而且正好落在 PR-3 要写入的位置上，已并入 PR-3 的范围。

另外核验席自己也错了一处（把 `EvidenceTrustState` 说成 6 个成员，实际 7 个，含 `stale`），已按实际写。**这一节留着，是因为「结论被人试过推翻」本身是这份决议的一部分证据。**
