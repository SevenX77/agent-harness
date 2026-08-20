# 删除必须被显式表达（API Keys 保存契约）

> 决议文档。用户 2026-08-20 裁决：「按『删除必须显式表达』开工」。
> 本文定契约与验收判据；`docs/studio/mvp1/01_workflows/00_settings-ux-spec.md`
> 仍是 Settings 的设计真相源，本文只把它已经写下的规则落成一份可实施、可验收的契约。

## 1. 决策

**「当前 payload 里没有某个 endpoint」不再被解释为「用户要删除它」。**

保存契约拆成两个互不重叠的动作：

- **upsert**：提交当前被编辑的 endpoint。它只增改，永不删除。
- **delete**：提交用户操作产生的待删除 endpoint id。**只有它**能触发
  `deleteEndpoint` 及其级联。

伴随修复：**纯 id 规范化不是 endpoint 搬家**。把一条记录从非规范 id 改钉到规范 id
时，它名下的 routes 与一切指向这些 route 的引用必须一并改钉，不得留下悬空引用。

## 2. 现场与根因

### 2.1 机制

`apps/studio/frontend/src/api/llm.ts:1720-1743` 的 `putCredentials` 把入参当作
**整页的完整申报**：

```ts
const existingEndpoints = cachedRegistry?.provider_endpoints ?? {}
const updateIds = new Set(updates.map((update) => update.id))
const removedEndpointIds = Object.keys(existingEndpoints).filter((endpointId) => !updateIds.has(endpointId))
for (const endpointId of removedEndpointIds) {
  latestRegistry = await deleteEndpoint(endpointId)
}
```

`updates` 来自 `buildPutPayload(draftsRef.current)`（`SettingsPage.tsx:777`），
即整页草稿经由 `draftsFromCredentials → buildPutPayload` 这条**派生链**投影出来的结果。
于是：**任何一个后端存在、而这条派生链没能覆盖到的 endpoint，都会在用户改任意一张卡的
任意一个字段时被删掉**——连同它名下的 routes、role/profile/bundle 里指向这些 route 的
引用，以及重建时拿不回来的密钥（`delete_registry_endpoint` 的既有级联）。

### 2.2 已实测的三条漏洞

审计于 2026-08-20 执行，三条都由实跑证实，不是读代码推断：

| # | 派生链在哪里丢了 id | 可达路径（已实测） |
|---|---|---|
| A-1 | `provider-utils.ts:382` 的 `if (!thirdPartyProtocolCandidates.includes(providerType)) continue` 跳过候选表以外的协议，而候选表（同文件 54-58 行）只有 openai / anthropic / google，**没有 `ark_runtime`**；`buildPutPayload`（`useDebouncedCredentialsSave.ts:198`）对第三方卡也只按这三个协议出 id | Ark Official 卡的 Base URL 一旦改离厂商默认值 `https://ark.cn-beijing.volces.com/api/v3`，`isOfficialProviderDraft`（`provider-utils.ts:317-333`）的厂商 URL 判据不再成立，整张卡被重分类为第三方，它的 `ark_runtime` 格子就此从 payload 消失 |
| A-2 | `normalizeBaseUrlGroupKey`（`provider-utils.ts:367-369`）分组前剥掉结尾的 `/v1`，而后端 `canonicalize_base_url` **只对 `anthropic_compatible` / `ark_runtime` 改写地址**——对 `openai_compatible` 来说 `https://api.x.com/v1` 与 `https://api.x.com` 是两个合法且不同的格子，在 UI 里却被并成一行；`baseUrlRowsFromCredentialProviders` 的 `endpointIds[providerType] ??= provider.id`（同文件 383 行）每个协议槽只留先到的那个 id | 一张卡上同时存在只差尾部 `/v1` 的两条地址，同协议的第二条必被判为待删 |
| A-4 | `upsert_endpoints`（`apps/studio/backend/app/services/llm_credentials.py:216-218`）在 `persisted_endpoint_id != endpoint_id` 时把旧 id 从 `provider_endpoints` 里 pop 掉，而 `provider_routes` 里的 `route.endpoint_id` 仍指着那个已经不存在的旧 id | 磁盘上一条 id 为 `legacy-hand-written`、地址 `https://api.legacy.example/v1` 的记录，原样存一次就被改钉到 `api-legacy-example-v1-openai-ce3238d3f5`，而它名下的 `legacy-hand-written:m1` 仍写着旧 endpoint_id，成为孤儿 |

### 2.3 根因

A-1 与 A-2 **不是两个缺陷，是同一个缺陷的两次显形**：派生链丢 id 的方式可以有无数种，
而**只要「payload 没提到」等于「删掉」，任何一种丢法都会变成删除**。它们已经是同一形状的
第三、第四次复发（前两次：2026-08-19 的 id-slug 嗅探误判 google 兄弟格子、同日 qiniu 卡被
整卡误删，PR #866）。

因此本次**不补协议表、不调 `/v1` 分组规则**——那是把这一次的丢法堵上，留着下一次。
要修的是那个等号本身。

### 2.4 被证伪的假设（记下来免得重走）

审计时曾怀疑「服务端改了 id 之后，还脏着的草稿仍拿着旧 id，于是下一次 PUT 把新 id 删掉」。
**实测不成立**：`reconcileDraftsWithCredentials`（`SettingsPage.tsx:152-160`）用
`providerDraftIdentityKey` 认出旧草稿与新快照是同一张卡，丢弃旧草稿并采用新快照，
所以下一次 payload 带的是**新** id。（副作用另说：用户当时正在输入的内容会被服务端快照
盖掉——那是 UX 问题，不是误删，不在本次范围。）

## 3. 设计源怎么说：这是 drift，不是设计变更

三条既有规则，代码全都反着来：

1. **`00_settings-ux-spec.md:50`（§1.2 矩阵第 3 点）**：
   「**格子永不删除、永不手工 disable**，状态 = 最近观察的投影」。
   一次普通的字段编辑把格子删掉，与这条正面冲突。
2. **`00_settings-ux-spec.md:724`（原子 10，PM 2026-07-03）**：会写后端的动作被逐个点名，
   删除只有两个——「**删 provider / 删 URL**」，且都要过后端就绪门。
   这两个动作本来就是显式的、有确认弹窗的用户操作，删除的合法入口早就存在。
3. **后端自己的契约**：`apps/studio/backend/app/routers/llm.py:507`
   `"""Upsert endpoints; absent endpoint IDs are retained."""`
   ——后端**从来没有**要求整页申报。差集删除是前端在一个 upsert-only 的接口之上
   自行加的一层语义。

按 `AGENTS.md`「MVP1 design = source of truth」，设计赢，改代码。

## 4. 新契约

### 4.1 保存契约（读写两侧）

**读**：`getCredentials()` → `getRegistry()` 拿到服务端 canonical snapshot，
缓存进 `cachedRegistry`，再由 `registryToCredentials` 投影成前端的 `CredentialsState`。
`cachedRegistry` 是**读通道的只读副本**（呼应 `AGENTS.md`「SSOT 读取原则」），
它的用途只有两个：投影给 UI 看，以及为 upsert 提供「这个 endpoint 已有的非编辑字段」
（`endpointFromCredentialUpdate` 的 `existing` 参数）。
**它不再参与任何删除判定。**

**写（upsert）**：`putCredentials(updates)` 只做一件事——把 `updates` 里的 endpoint
提交给 `PUT /api/llm/registry/endpoints`。payload 里没有的 id 一律**保持不动**，
与后端契约一致。函数不再读 `cachedRegistry` 的键集合，不再计算差集，不再调
`deleteEndpoint`。

**写（delete）**：见 4.2。

### 4.2 删除意图的唯一 owner

**唯一 owner = `SettingsPage.deleteProviderEndpoints(endpointIds)`**
（`apps/studio/frontend/src/components/studio/settings/SettingsPage.tsx:888`）。
改动后它是整个前端**唯一**调用 `deleteEndpoint` 的地方。

到达它的路径只有两条，都是用户的显式操作，且都已经过二次确认与后端就绪门：

| 用户操作 | 入口 | 待删 id 从哪来 |
|---|---|---|
| 删掉整张 provider 卡 | `ProviderDeleteButton` → `confirmDelete` → `deleteProvider` | 该卡当前所有 endpoint 草稿的 id |
| 删掉卡上一条 Base URL 行 | `ProviderCard.deleteBaseUrlRow` → `confirmDelete` → `onDeleteEndpointIds` | 该行 `endpoint_ids` 里的 id（服务端下发） |

**待删 id 必须来自服务端下发的 `endpoint_ids`，不得由前端现拼。** 理由：id 的唯一权威是
后端（`_persisted_endpoint_id`），前端拼出来的 id 只是新建时的占位符；拿占位符去删，
删中的可能是别的记录，或者什么都没删中。

**同步纪律**：`deleteBaseUrlRow` 触发的删除，必须先 `flush` 掉尚未落地的凭据保存，
再解析待删 id。否则一条「刚敲进去、保存还在飞」的 URL 行被删掉时，它的 `endpoint_ids`
还是空的，后端已经建出来的格子就没人删了——差集删除从前会顺手扫掉它们，现在不会。
用既有的 `flushCredentialsSave` 关掉这个窗口，不新造机制。

### 4.3 前端草稿与服务端 canonical snapshot 的交互边界

三样东西，各有唯一权威，互不越界：

| 对象 | 权威在哪 | 谁能改 | 谁不能碰 |
|---|---|---|---|
| **草稿**（`draftsRef.current`）：用户此刻在输入框里的内容 | 前端本地，逐键更新 | 用户输入；`reconcileDraftsWithCredentials` 在保存返回后按卡片身份合并 | 草稿**不是**真相，不得据它推断服务端该有什么、不该有什么 |
| **canonical snapshot**（`cachedRegistry`）：服务端此刻的凭据真相 | 后端 `llm_credentials.json` | 只有服务端响应能写它（`cacheRegistry`） | 前端不得凭本地推理修改它，也不得据它与草稿的**差集**推断用户意图 |
| **删除意图**：用户想删掉哪个 endpoint | 4.2 那两条显式操作 | 只有用户点击（且确认）能产生 | 任何派生投影（`draftsFromCredentials` / `buildPutPayload` / 分组规则 / 协议候选表）**都不产生删除意图** |

一句话判据：**草稿说「我要什么」，snapshot 说「现在有什么」，两者的差不说明任何事。**
「删掉什么」只能由第三样东西——用户的显式删除操作——说出口。

### 4.4 id 规范化不是 endpoint 搬家（A-4）

`upsert_endpoints` 里 `persisted_endpoint_id != endpoint_id` 有两种成因，处置相反：

- **搬家**（`combo_changed` 为真）：`(canonical base_url, protocol)` 变了，这个 endpoint
  换了身份。名下 routes 描述的是它不再指向的地址，随旧 id 一并**清除**，role 引用走
  删除级联。——已由 PR #876 落地，设计源 §1.2 矩阵第 3 / 第 6 点。
- **规范化**（`combo_changed` 为假）：地址那一对没变，只是这条记录此前存在一个非规范的
  id 下（历史手写 id）。它**不是**换了东西，只是换了个称呼。名下 routes 仍然成立，
  必须跟着改钉到新 id，而不是被清除，更不能被留在原地变成悬空引用。

**改钉要动的东西**（route_id 的格式是 `<endpoint_id>:<slug>`，所以 endpoint 换名，
route 的 id 也跟着换名）：

- 凭据侧：`provider_routes` 的键、每条 route 的 `route_id` 与 `endpoint_id`；
- 角色侧（`RolesData` 里引用 route_id 的全部五处）：
  `roles[*].fallback_chain[*].route_id`、
  `roles[*].model_groups[*].provider_models[*].route_id`、
  `model_profiles[*].fallback_chain[*].route_id`、
  `model_bundles[*].fallback_chain[*].route_id`、
  `model_bundles[*].model_groups[*].provider_models[*].route_id`。

**原子性能保证到哪一层，说清楚**：

- **凭据文件内部是原子的**：endpoints 与 routes 的改钉在一次内存变换里完成，
  经由一次 `_save_credentials_unlocked`（`os.replace`）落盘，不存在「endpoint 改了、
  route 没改」的中间态。
- **跨文件（凭据 json + 角色 yaml）没有共享事务**，本仓从来没有。所以要保证的不是
  「不可能有中间态」，而是**中间态必须是可以重做的**：写入顺序定为**先角色、后凭据**。

  理由是不对称的：凭据文件是「旧 route id 曾经存在过」的**唯一**记录。
  若先提交凭据、写角色时崩掉，旧 id 已经被抹掉，重试同一次保存会发现 endpoint
  已在规范 id 上、不再改钉、也不再级联——那批悬空引用**永远修不回来**，而且
  `save_roles_file` 的 `validate_references` 会让此后每一次角色保存都失败。
  反过来先写角色、写凭据时崩掉：角色指向新 id、凭据还在旧 id 上，用户**再存一次**
  就会重新改钉一次（角色侧此时已是新 id，映射匹配不到、原样不动，是幂等的），
  两边收敛。同一个崩溃点，一边是永久损坏，一边是重做一次即可。

  这条规则是 git 的规则：先写 object，最后才移动指向它的 ref——**提交那个「指认者」
  的动作放在最后**，崩在中途只留下一批没人引用、重跑一次就被覆盖的产物。本仓这里
  的「指认者」就是凭据文件。它同时也与既有的删除级联同向（`delete_registry_endpoint`
  也是先写角色、再写凭据），所以两条级联只有一种中间态需要推理，而不是两种。
- **落地形状**：`upsert_endpoints` 接受一个 `cascade` 回调，在**同一把凭据锁内、
  落盘之前**把 `EndpointRouteCascade`（搬家丢下的 route id、改钉的 id 映射、
  本次落盘后凭据将持有的全部 route id）交给它；`app/routers/llm.py` 的
  `_follow_endpoint_rekey_into_roles` 用这三样做**一次**角色写入。
  回调抛出的任何异常都会让凭据**一个字节都不写**——`save_roles_file` 内的
  `validate_references` 因此成为写入前的门禁，而不是写入后的抱怨。

## 5. 关键设计决定（含被放弃的替代项）

1. **删的是差集删除这段代码，不是给它加开关。** 本仓 pre-release、不向后兼容：
   换掉旧设计就在同一个改动里删干净旧路径（`AGENTS.md` Development Principles 第 1 条）。
   *放弃的替代*：留一个 `allowImplicitDelete` 参数——那只是把缺陷改成默认关闭，
   下一个人打开它就复活。
2. **不新建「待删清单」状态机。** 删除的显式入口（`deleteProviderEndpoints`）本来就存在，
   而且已经是 `deleteEndpoint` 的调用者之一；本次只是把另一个非法调用者拿掉，让它变成
   唯一的那个。*放弃的替代*：给 `putCredentials` 加一个 `deletedIds` 入参，
   把删除塞回保存调用里——那会让「保存」这个动作重新拥有删除能力，正是要根除的东西
   （SRP：一个单元只应有一个被改动的理由）。
3. **A-1 / A-2 落成回归测试，不改各自的规则。** 用户裁决原话：「不要靠补协议表或调整
   `/v1` 分组规则掩盖」。这两条现在是**根因的两个见证**：只要保存不再隐式删除，
   派生链丢不丢 id 都不会导致数据丢失。派生链本身的不完整另属显示层问题
   （某些格子在 UI 上看不见），不在本次范围，也不再具备破坏性。
4. **规范化改钉 = 改名，不是删除+新建。** 删除+新建会让 role 引用先断后接，
   中途任何一次读都看到断的状态；改名是一次映射，引用始终指向存在的对象。
5. **待删 id 只认服务端下发的，前端不现拼。** 见 4.2。这条同时呼应设计源 `:553`
   「前端不再自己拆 / 不生成 id」。

## 6. 验收判据

全部为可执行测试，先红后绿：

**端到端保存（前端 API 层，用假 adapter 记录发出的请求）**

1. 快照里有一个 `ark_runtime` 第三方格子（A-1 的形状）→ 保存另一张卡的编辑 →
   **不得**发出任何 `DELETE /llm/registry/endpoints/*`，且该格子在快照里存活。
2. 快照里有两个同协议、只差尾部 `/v1` 的格子（A-2 的形状）→ 保存 →
   同样不得发出任何 DELETE，两个格子都存活。
3. 一次普通编辑保存后，发出的请求**只有** `PUT /llm/registry/endpoints`，
   且 body 里只有被编辑的那些 endpoint。
4. 用户显式删除（删卡 / 删 URL 行）→ **确实**对每个待删 id 发出
   `DELETE /llm/registry/endpoints/<id>`。

**id 规范化改钉（后端 pytest）**

5. 一条存在非规范 id 下、地址不变的记录，原样存一次 → endpoint 改钉到规范 id，
   名下 route 的 `route_id` 与 `endpoint_id` 同步改钉，`provider_routes` 里
   **没有任何** `endpoint_id` 指向已不存在的 endpoint（悬空引用为零）。
6. 同一场景下，role / model_profile / model_bundle 里指向旧 route_id 的五类引用
   全部改钉到新 route_id，一条不漏、一条不丢。
7. 搬家（地址真的变了）仍然是**清除**而不是改钉——PR #876 的行为不被本次改动动摇。
8. 角色写入失败（注入故障）时，凭据文件**一个字节都没变**：endpoint 仍在旧 id 上、
   route 仍是旧 route_id——即上面「中间态必须可重做」的可执行证据。

**真机（合并后）**

9. 在主 app 上编辑任意一张卡的任意字段并保存，`llm_credentials.json` 的
   `provider_endpoints` 键集合不减少。
10. 显式删掉一条 Base URL 行，该行对应的格子确实从盘上消失。

## 7. 不在本次范围

- **派生链的显示层不完整**（`thirdPartyProtocolCandidates` 没有 `ark_runtime`；
  `normalizeBaseUrlGroupKey` 的 `/v1` 分组与后端 `canonicalize_base_url` 不同口径）。
  修掉隐式删除之后，它们的后果从「删数据」降级为「某些格子在卡片上看不见」。
  这是显示层的正确性问题，应当单独立项、单独举证，不塞进本次。
- **前端仍在为新建的 endpoint 现拼占位 id**（`endpointIdForBaseUrlProtocol` 的
  `${baseId}-${suffix}` 回退），与设计源 `:553`「前端不再自己拆 / 不生成 id」有出入。
  它是 A-4 那类历史非规范 id 的来源之一，但改掉它牵动新建流程的整条握手，
  另立。
- **保存返回的服务端快照会盖掉用户正在输入的内容**（2.4 记下的那个副作用）。
