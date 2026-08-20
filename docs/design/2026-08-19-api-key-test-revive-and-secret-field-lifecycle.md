# API Keys:密钥失效后的复活路径 + 密钥字段生命周期(决议,2026-08-19)

> 本文是一次**实现对齐设计**的决议:两个用户点名的缺陷,根因都在「密钥字段的生命周期」这一条
> 链上——上游让一把好密钥被写坏,下游让被写坏的端点再也测不了。设计源(MVP1
> `docs/studio/mvp1/01_workflows/00_settings-ux-spec.md`)对这两件事**早有裁决**,是实现偏离了
> 它;因此本文不新造需求,只做三件事:钉住偏离、给出改法、写清验收判据。新增的部分只有一条设计
> 缺口(见 D3「就地编辑一把未揭示的密钥」),它同步写回设计源。

**状态**:已裁决(用户 2026-08-19 批准「把有问题的地方都修好」),随实施 PR 一并合入。

---

## 1. 事实(先摆证据,再下结论)

### F1. 点 Test 没有任何事情发生,连请求都没发出

用户报「点 test 会失效」。真机盘上与日志的一手证据:

| 证据 | 内容 |
|---|---|
| `%APPDATA%\AgentStudio\llm\llm_credentials.json` | `deepseek-official`:`status: "disabled"`、`last_test_message: "Invalid API key (invalid_request_error)."`、`last_test_at: "2026-08-12T16:34:38"`;名下 2 条 route(`deepseek-v4-flash` / `deepseek-v4-pro`)全部 `disabled` |
| `%APPDATA%\AgentStudio\logs\studio_runtime_activity.jsonl`(连续覆盖至 2026-08-19T19:05) | `deepseek-official` 历史共 12 次 `endpoint_test`,**最后一次即 2026-08-12T16:34:38 那次失败**;此后至今**一次都没有**。2026-08-19 当天全库 9 次 `endpoint_test`,**无一条属于 DeepSeek** |

因果结论:自 2026-08-12 起,任何一次对该卡的 Test 点击都**没有产生任何下游可观察结果**——请求
根本没离开前端。

同样被锁死的还有 3 个端点:`gemini-official`(2026-08-13,官方卡)、
`api-jiekou-ai-anthropic-google-*`(2026-08-19,message 为 "API key is empty",即 #866 差集删除
洗掉密钥的遗留)、`anthropic-qnaigc-com-google-*`(2026-08-19)。

### F2. 四道门把「复活」这条路全部焊死

| # | 位置 | 行为 |
|---|---|---|
| 1 | `SettingsPage.tsx` `routineEndpointTestShouldQueue` | `if (persisted.endpoint_status === "disabled") return false`,端点被剔出测试队列 |
| 2 | `SettingsPage.tsx` `runProviderGetModels` | `if (endpointDrafts.length === 0) return`,这行在 `toast.loading` **之前**,所以队列空时连一句提示都没有 |
| 3 | `routers/llm.py` 端点测试入口 | `_probe_endpoint_model_list_atom(endpoint, allow_disabled=force)`,不带 `force` 时 disabled 端点直接跳过 |
| 4 | `ProviderCard.tsx` | 唯一能带 `force=true` 的 Re-probe 按钮,只在 `protocol_unsupported` 时渲染,`disabled` 没有 |

第 1 道门的 `disabled` 判断写在「参数变了就该重测」判断**之前**,于是**换一把全新的密钥也无法解锁**;
`llm_credentials.py` `upsert_endpoints` 又以 `"status": current.status` 把 `disabled` 原样带过保存。
官方卡没有删除入口(`ProviderCard.tsx` 的 `!isOfficial` 条件),因此 `deepseek-official` /
`gemini-official` 在界面里已**无任何出路**。

### F3. 聚焦密钥输入框会把回读占位符当成内容显示出来

`ProviderCard.tsx` 聚焦即 `setApiKeyEditing(true)`,而 `apiKeyDisplayValue` 的第一行是
`if (visible || editing || !value) return value`——editing 态**直接吐原始值**。未揭示时草稿里
存的原始值就是服务端回读的固定 10 字符占位符 `**********`(`api/llm.ts`
`REDACTED_ENDPOINT_SECRET`),于是用户看到 10 个星号。

**它的危险延伸**:占位符一旦成为可编辑文本,退格一次得到 9 个星号、在末尾粘贴得到
`**********sk-xxx`——两者都**不再全等于**占位符,于是前端 `endpointFromCredentialUpdate`
(只认全等)判定"用户输入了新密钥"原样发出,后端 `_is_new_secret`(也只认全等)照单写盘。
**整条链没有任何一处兜底,一把好密钥就此被垃圾字符串覆盖**;下一次 Test 必然
`invalid_key`,随即掉进 F1/F2 的陷阱,再也测不回来。两个缺陷是一条因果链的上下游。

---

## 2. 设计依据(设计源怎么说的,逐条引用)

**S1 — 格子永不 disable,`invalid_key` 是账号级事实**(`00_settings-ux-spec.md` §1.2 矩阵第 3 点,
PM 2026-07-02):

> **格子永不删除、永不手工 disable,状态 = 最近观察的投影**:`verified`(最近生成 ok)/
> `untested`(无观察)/ `unsupported`(最近观察 = protocol_unsupported,展示观察时间 + 下次
> 复查时间)/ 瞬时失败(网络/限流/超时 → **下次 Test 即重试**)/ **结构失败(invalid_key /
> quota → 账号级,与格子生死无关)**。

**S2 — 除 `protocol_unsupported` 外全部状态点击即测**(同文件 §4.2 端点标签一节,PM 2026-07-03):

> **可点性:除 `protocol_unsupported` 外全部状态都直接点击即测**。verified(绿)/ untested /
> failed(红)/ not_configured 都可点复测。**唯一不可直接点的是 `protocol_unsupported`**……
> 即 `endpointTagIsTestable` = 除 `testing` / `protocol_unsupported` 外全 true。

**S3 — 红 = 用户要动手修**(同文件 §4.2 六态表):

> 🔴 failed:出错了要你修:① 配置缺口(缺 key/base_url/protocol/model id)② 测试失败。

**S4 — 只有 Eye/Copy 这类显式动作才换真值,掩码位数按真实长度**(同文件 A10 / 原子动作 16、22,
2026-08-12 决议):

> Eye/Copy 等显式用户动作才换单条真值;进 tab 只投影 redacted registry(掩码点数 =
> `api_key_length` 真实位数,**非占位符 10 位**)。

**S4b — 换密钥即作废旧测试结论**(同文件原子动作 21):

> 改 API Key(两类共用;**改后旧测试失效→badge 回 untested**)

**S5 — `disabled` 可逆,复活靠再测一次**(`docs/design/2026-08-10-gateway-module-tree-and-probing-decision.md`
D13,2026-08-12):

> `disabled` 是**系统当下的决定**(密钥被拒时整端点连同路由一起停用,**下次测试成功再恢复**)

**偏离认定**:S1 说端点格子不该因 `invalid_key` 被 disable,后端 R-E2 却把端点置为 `disabled`;
S2(2026-07-03)说 failed 红格子点击即测,PR #385(2026-07-04,**次日**)加的队列闸门把它否掉了;
S4 说只有 Eye/Copy 换真值,聚焦却把占位符当内容吐了出来。三处都是**实现偏离设计**,按
`AGENTS.md`「MVP1 design = source of truth」以设计为准。

---

## 3. 决策

### D1. `invalid_key` 把端点判为 `failed`,不判 `disabled`(后端)

R-E2 对**端点**的处理改为对齐 S1/S3:密钥被拒是账号级结构失败,端点格子记录这次观察即可
(`failed` + `last_test_message` + `last_error_code`),**不改变格子的生死**。红色、可点、可复测,
正是 S3 定义的「要你修」。

**路由仍然停用**:R-E2 里「把该端点名下 routes 置 `disabled`」保留不动——那是 D13 依赖的
禁令(死密钥不该继续把 50 条路由摆给 role 选),`routeIsUsable` 的禁令优先规则、
`project_route_state` 的 `off` 投影都建立在它之上;既有的 revive sweep(get-models 成功即把
`disabled` 路由恢复为 `unverified_manual`)负责复活。

**连带删除**:端点状态从此不会再是 `disabled`,于是 `_endpoint_probe_is_disabled` /
`_disabled_endpoint_probe_result` / `_disabled_route_probe_result` / `allow_disabled` 参数链 /
`endpoint_test_skipped` 的 disabled 分支全部成为死路径,**同一改动里删干净**(不向后兼容,
不留兼容分支)。`force` 参数保留它的另一个职责:绕过 `protocol_unsupported` 的 30 天半衰期门。

### D2. 显式 Test 一律进队列,且永远有回应(前端)

`routineEndpointTestShouldQueue` 的 `disabled` 分支删除——它与 S2 直接冲突。保留
`protocol_unsupported` 分支(S2 明确把它排除在点击即测之外,由尾部 Re-probe 按钮走 force)。
函数改名为 `endpointTestShouldQueue`:两个调用方(整卡 Test 按钮、端点格子点击)**都是显式
用户命令**,"routine"这个词从一开始就名不副实,是它让"跳过"看起来理所当然。

「队列为空 → 静默 return」这个哑巴出口同时修掉:一次点击必须有可见回应,否则用户无法把
"系统拒绝执行"与"程序坏了"分开(F1 的用户体验正是如此)。

### D3. 未揭示的密钥不可就地编辑;第一次输入 = 整把替换(前端)【设计缺口,新增】

设计源定了"只有 Eye/Copy 换真值"(S4),但**没定**"用户在一个从未揭示过的密钥字段里打字
会怎样"。本决议补上,并写回设计源:

- **`stored`(回读占位符)态**:一律按 `api_key_length` 渲染掩码点,**聚焦不改变显示**。占位符
  永远不作为内容出现在输入框里。
- **在 `stored` 态输入** = 「我要换一把新密钥」:取输入事件里**非掩码字符**的部分作为新密钥
  (整把替换),而不是在掩码上做增删改。掩码字符是 `•`(U+2022),不可能出现在真实密钥里,
  所以这个判据没有歧义。
- **在 `stored` 态纯删除**(退格 / Delete 只删掉掩码点):**不改变已存密钥**。删掉一个掩码点
  不构成"半把密钥"这种东西;要清空密钥,先 Eye 揭示再删,这条路径显式且可见。
- **要就地编辑真实密钥**,先按 Eye 揭示(S4 的显式动作),揭示后字段进入 `plaintext` 态,
  可正常编辑。

**被否决的替代方案**:聚焦时自动取回真实密钥。它把"点一下输入框"变成泄密动作,与 S4
"显式动作才换真值"直接冲突,还给每次聚焦加一次网络请求。

### D4. 换密钥即作废旧观察(后端)

`upsert_endpoints` 保存时以 `"status": current.status` 把旧结论原样带过。按 S1「状态 = 最近
观察的投影」:那次观察是对**旧密钥**做的,密钥换了就没有任何针对新密钥的观察,状态必须回到
`unverified_manual`,`last_test_at` / `last_test_message` 清空。

**唯一例外 `protocol_unsupported`**:它是关于 (base_url, protocol) 的事实——「这个域名不说这个
协议」与用哪把密钥无关(§1.2 矩阵第 4 点给了它 30 天半衰期)。换密钥不作废它,`last_error_code`
在这一种情况下保留。

### D5. 掩码污染的值在写入边界上被拒(后端一道,且只要一道)

按仓规「Fail fast,在边界校验」:一个**掩码形状**的值不可能是密钥,在写入边界(`upsert_endpoints`)
直接 422 拒绝并给出诊断,而不是写进盘里等下一次 Test 去发现。三种形状被判定为掩码,判据选得
足够窄以免误伤真实密钥:整串只由掩码字符构成;以占位符开头(在掩码尾部打字/粘贴的产物);
含 U+2022(本 UI 的掩码字形,没有任何服务商在密钥里发这个字符)。

**裸占位符是唯一合法的掩码值**,它是"未改动"这个语义的协议 token,由 `_preserved_secret`
照旧保留——回读什么就发回什么,是前端现有的正常往返。

**只在后端设这一道,前端不再设第二道。** D3 之后 UI 已经在结构上产不出污染值,此时前端再
"悄悄丢弃"只会把 422 的诊断吞掉——一个自以为存好了密钥而其实没存的调用方,和它上游那个
缺陷是同一类错误。让它响亮地失败,是唯一能被发现的失败。

---

## 4. 验收判据

行为判据(每条都要有对应自动化测试,失败测试先行):

| # | 判据 | 层 |
|---|---|---|
| V1 | 一张卡的全部端点都处于 `disabled`/`failed` 时点 Test:请求**必须发出**,且界面有可见回应 | 前端 |
| V2 | `invalid_key` 之后,端点状态是 `failed`(不是 `disabled`),名下 routes 是 `disabled` | 后端 |
| V3 | 对一个曾经 `invalid_key` 的端点再测一次并成功:端点回到 verified,routes 由 `disabled` 恢复 | 后端 |
| V4 | 换一把新密钥保存后,端点 `status` 回到 `unverified_manual`、`last_test_*` 清空 | 后端 |
| V5 | 换密钥不清除 `protocol_unsupported` 的 `last_error_code` | 后端 |
| V6 | `stored` 态聚焦输入框:显示的是 `api_key_length` 个掩码点,**绝不出现 `*` 字符** | 前端 |
| V7 | `stored` 态输入/粘贴:草稿密钥变为插入的那段本身(整把替换),不含任何掩码字符 | 前端 |
| V8 | `stored` 态按退格:草稿密钥不变(仍是占位符),不产生写请求 | 前端 |
| V9 | 掩码形状的值到达 `upsert_endpoints` 时以 422 拒绝,已存密钥与观察都不受影响 | 后端 |
| V10 | 已 reveal 的明文密钥仍可正常就地编辑 | 前端 |

真机判据(合并后在主 app 上逐项点验,按 SOP Phase 7 交报告):DeepSeek 卡点 Test 能真正发起
测试并如实反映结果;Ark 卡点击密钥输入框显示掩码点而非 `**********`。

---

## 5. 影响面

- 用户盘上现存的 4 个 `disabled` 端点(F1)**自愈**:两道门拆掉后它们重新可测,一次成功的
  Test 就会用新观察覆盖旧状态。不需要手工改 JSON,也不需要重建数据。
- `PR #385` 钉住旧行为的两个测试:`protocol_unsupported` 那条保留(仍是设计要求),
  `disabled` 那条改写成钉 D2 的新规则。
- 台账:`docs/development/PROBLEM_LEDGER.md` 第 3 节(LLM 配置)新增两条并随本 PR 勾销状态;
  `docs/development/DELIVERY_LEDGER.md` 记本次交付。
