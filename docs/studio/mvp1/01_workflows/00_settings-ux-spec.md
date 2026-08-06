# Settings Page — 用户 UX Workflow 详细规格（API Keys / LLM Roles / Copilot）

> **来源**：PM 口述需求（2026-06-02）。PM 强调此前"写过好几次"但未落进 mvp1，本次正式记载。
> **地位**：设置页三个子页面的**权威 UX 规格**。[`00_settings.md`](./00_settings.md) 写四条旅程的结构与范式（高层）；本文写**每步操作 / 反馈 / 动机的细粒度行为**，尤其三条横切机制：Probe Knowledge Catalog（探测知识库）赋能/写回、model/endpoint 标签表现、测试落点。§0 保留 PM 原话里的 `draft` 字样；结构化设计中 `draft` 已改名为 Probe Knowledge Catalog,Import Draft 不属于 MVP1 主线。
> **写作铁律**：§0 存 PM 原话 verbatim（不 paraphrase、不修typo）；§1–§4 结构化（忠实，不"顺便优化"）；§5 与现状代码对接（cross-ref，不改需求）。

---

## 0. PM 原话（verbatim，不改一字）

> 1. akikey页面:  a. official, 用户填入api key ,  直接点test ,  get 所有的model list, 不需要probe, 因为比较可控, 只要API key 能连通(/model 获取模型列表)  , 拉取draft API , 对比模型list diff , 把draft中已证实的资料填给 model list , model list标签变成蓝色, 表明以前联通过. 有新的模型, capability(anthropic就能在getmodel的时候返回capability),把diff的部分写回draft; official之需要get models;
>
> b. 第三方唯一的区别是, 用户得填入URL, (protocol以前要自己选, 现在系统自动测); 用户必须在模型列表里面选一个模型进行一次模型测试, 才能验证这个endpoint可用. draft 、 标签行为等等和official一致. API key页面必须验证endpoint, 不是测试模型连通性的主战场, 但是留了地方让你可以批量对单个模型进行probe.
>
> 2. llm role 页面, 根据规则过滤 available models: llm 模型, endpoint测通的; 新建role , 拖动 model group(相同模型合并, endpoint 状态颜色和APIkey页面一样) 到 roles card, 选择provider, 更改role 的 config, 点击test , 对role里面的所有模型测一遍probe , 结果回写draft ; model bundle相当于自建了一个已经安排好fallback的model group. 和model group的区别是, model bundle可以放不同模型, 并把provider配好. 可以和model group一样拖进role card ,  同样能解析成route list
>
> 3. copilot和llm roles类似, 只是copilot的role 只能填一个 model group, 并且测试走 copilot 自己的调用, 测试和真实调用没什么区别,
>
> draft 赋能/ 写回; model/ endpoint标签的表现; role card 中的models才做真实测试, 保证能用;

---

## 1. API Keys 页面 — 验证 endpoint（不是测模型的主战场）

**页面职责一句话**：确认每个 endpoint 可连通，并用 Probe Knowledge Catalog（探测知识库）回填模型清单的已知信息。真正"保证某模型能用"的测试在 role 页面做（见 §4.3）。

### 1.1 Official provider（官方，比较可控）
**动机**：官方 endpoint 可控，协议固定、模型清单可信，**不必逐模型 probe**；但"能连通"不等于"能生成"（PM 拍板修订 2026-07-01，见下）。
**步骤**：
1. 用户填入 **API key**。
2. 直接点 **Test**。
3. 系统调 `GET /models`（获取模型列表），**再打一次最小生成探测**（在语言模型候选里按 probe 优先级挑一个、打推理端点、`max_tokens` 最小）——**生成探测成功才判 verified**；get-models 通、生成探测遇结构性失败（invalid_key / 欠费类 quota）→ endpoint 判 failed 并展示 provider 原文。
   - **修订记录（PM 2026-07-01）**：原设计为"get-models 连通即 verified、不做逐模型 probe"。实证推翻：Anthropic 账户**欠费**时 `GET /models` 照常 200（endpoint 显示 Connected/verified），但**所有**生成调用被 `HTTP 400 "credit balance is too low"` 拒绝 —— role 测试全红、API keys 页却全绿，两页真相矛盾。结论与第三方 §1.2 的论证同源：**get-models 只证明 key+URL 可达，不证明能生成**；官方与第三方在"必须真打一次生成"上对称，差别只剩官方**不需要协议轮换探测**（协议固定）、且候选**过滤为语言模型**（官方清单混着 image/audio/embedding 模型）。欠费类 HTTP 400（provider 报文含 credit/billing 标记）由 gateway 归类为结构性 `quota_exceeded`，短路批量循环，不误判为 `invalid_model`。
   - 逐模型的**能力级** probe（profiles / thinking）仍不在 endpoint Test 里做——那是 role 页与 Manual probing 的职责;endpoint Test 的生成探测只为证明"这个账户当下真能出字"。
4. **读取 Probe Knowledge Catalog**（该 provider 的历史探测知识库），把当前 `GET /models` 结果与 catalog 的 provider/endpoint/model 画像 **做 diff**。
   - **边界（PM 补充 2026-06-02，术语更新）**：若 `GET /models` 返回 **200 但 `models=[]`（空清单）**，仍与 catalog 做 diff，**用 catalog 里的已知模型填充 model list** —— 空响应不代表没有模型（有的 provider 不返回清单），以历史探测知识为候选来源。
5. **把 catalog 中已证实的资料回填给 model list**（历史已验证的能力/元数据填进当前清单，带 provenance/evidence_ref）。
6. model list 的标签变 **蓝色 =「以前联通过」**（历史连通标记）。
7. diff 出的**新模型 / 新 capability**（anthropic 在 get-model 时就会返回 capability）**写回 Probe Knowledge Catalog**（沉淀历史知识）。
- **official = get models + 一次最小生成探测**（修订 2026-07-01，原"只需要 get models"作废），到此 endpoint 验证完成。

### 1.2 Third-party provider（第三方）
与 official **唯一的区别**：
1. 用户**必须填入 URL**（base_url）。`protocol`（协议）**以前要用户自己选，现在系统自动测**（自动探测协议）。
   - **探测方式（PM 2026-06-02，#C 答案）**：**把各 protocol 排列组合各测一遍**（用每种协议的连通方式去试），哪个能连通就判定为哪个 protocol —— "排列组合测一遍就知道"，不需要单独的聪明探测逻辑。
   - **修订记录（PM 2026-07-02，协议探测矩阵）**：#C 的"排列组合各测一遍"落地形态定为**探测矩阵**，并纠正实现 drift（"轮换选出唯一协议并改写 endpoint.protocol"）。原则：**状态不能被设置，只能从观察算出来；观察会老化，但不会被覆盖**。
     1. **矩阵格子 = (canonical base_url, protocol)，身份不可变**。一张卡的每个 URL × 每个候选协议是一个独立格子（= endpoint 记录）；`protocol` 是身份的一部分，**创建后永不改写**。"检测协议"不再是给某个 endpoint 找协议，而是每个格子**用自己的协议**打推理端点、把结果记在**自己**身上。协议轮换机（在一个 endpoint 的 Test 里换协议试、试通改写 `protocol` 字段）**作废删除** —— 它制造过三重事故（实证 2026-07-02）：qiniu `-openai-` endpoint 被改写成 anthropic 与兄弟 endpoint 完全重复；瞬时失败让 google 的 404 赢下检测；同一 Test 连点两次持久真相不同（前端按 id-slug 回写 protocol 与后端检测打乒乓）。
     2. **`protocol_unsupported` 一等分类**（gateway 探测分类新增）：路径级 404/405（如 "not found or method not allowed"、"Use /v1/messages instead"，响应体**不含**模型语义错误）= **该 URL 不支持该协议**，与 `invalid_model`（协议通了、模型 id 不对）**必须区分**。旧实现把协议 404 归进 `invalid_model` 是三个假象的共同根因（"Untested"假状态、google 赢检测、6/6 失败仍 verified）。
        - **补充信号（PM 2026-07-02，误路由与路由拒绝）**：判据不止 404/405。① **路由级拒绝**：`5xx` 明说该协议路径不存在（实证：`anthropic.qnaigc.com × google` 的 `GET /v1beta/models` → HTTP 500 `"Unsupported fixed route: /v1beta/models"`）也是 `protocol_unsupported`（标记扩到 `unsupported fixed route` / `unknown route` / `route not found`）。② **误路由到异协议**：某些网关对不支持的协议**不报错而是静默转发到自己的另一协议上游**，把那个上游的错误原样吐回 —— 探 `google` 却收到 `"OpenAI API error: 401 invalid api key"`（实证：`anthropic.qnaigc.com × gemini` 生成 500 包着七牛内部 OpenAI 上游的 401）。**探 X 协议却收到 Y 协议的 API 错误 = 该 URL 不说 X**，判 `protocol_unsupported`（此判据须早于 401 分支，否则异协议的 401 会被误当成"我这把 key 失效"）。真机验证 2026-07-02：修后该格子稳定判 `protocol_unsupported`、名下 6 条幽灵路由被清空（deepseek-v4-pro 的 qiniu 路由 4→3）。
     3. **格子永不删除、永不手工 disable，状态 = 最近观察的投影**：`verified`（最近生成 ok）/ `untested`（无观察）/ `unsupported`（最近观察 = protocol_unsupported，展示观察时间 + 下次复查时间）/ 瞬时失败（网络/限流/超时 → 下次 Test 即重试）/ 结构失败（invalid_key / quota → 账号级，与格子生死无关）。
     4. **失败分类定半衰期**：`protocol_unsupported` 是提供商架构级事实 → 长半衰期（**30 天**内日常 Test 跳过该格子，到期自动补测；用户可对单格子强制 re-probe）；瞬时类不设门。"哪天 qiniu 支持 gemini 了"由半衰期复测或手动 re-probe 重新发现 —— 能力不会永久丢失，只有"多久发现"。
     5. **protocol 单写真相**：`protocol` 唯一权威 = 后端 credentials 存储的字段。前端**不得**从 endpoint id 的 slug 反推协议，upsert **不得**修改既有 endpoint 的 `protocol`（后端拒绝 422）；(canonical base_url, protocol) 唯一性是存储不变量（历史被改写产生的重复格子视为坏数据清除，数据可丢弃）。
     6. **routes 只挂在活格子上**：格子被观察为 `protocol_unsupported` 时清除其名下 routes（协议都不通的格子上不存在"模型清单"）；瞬时失败不清。
     7. **日志完整性**：每个格子测自己 → `probe_attempts` 天然覆盖全部尝试（旧轮换里中间候选的失败探测不落日志、协议翻转无因无果，随轮换机一并消灭）；runtime activity 时间戳统一 **UTC**（与 credentials 对齐）。
     8. **catalog 只当线索，不当真相**（后续 PR）：探测观察（**含失败**）双向进 Probe Knowledge Catalog（对齐 §1.4 #2.4"失败也是历史"）；catalog 与本地观察冲突（别人通了我这标 unsupported）只**提前本地复测**，永远不直接改本地状态 —— 别人的 key 套餐/区域/网络与我不同，"他通我不通"是常态。
     9. **unsupported 格子必须"指路"到同域名的活协议**（UX，PM 2026-07-02）：格子被判 `protocol_unsupported` 不是死胡同 —— 提供商返回的信号本身就在指路（`anthropic.qnaigc.com` 对 `/v1/chat/completions` 明确回 "Use /v1/messages instead"，实证 2026-07-02：换到 `/v1/messages` 用 `x-api-key` 或 `Bearer` 均 HTTP 200，但**回来的是 Anthropic 信封**`type:message`/`content[]`、**无 `choices`** → OpenAI 客户端解析不了，所以"换后缀能连"= 走回了 Anthropic 协议，不是 OpenAI 协议复活）。tooltip 要把这条指路讲给用户：**"此域名不支持 {当前协议} 协议 —— 请改用同域名下的 {已验证的兄弟协议} 路由"**（同域名 = 同 hostname；兄弟协议 = 同 hostname 下 status=verified 的其它格子协议，可多个）。实证：`anthropic.qnaigc.com × OpenAI` 灰格子指向同域名 `× Anthropic` 绿格子；`api.qnaigc.com × Gemini` 灰格子指向同域名 `× OpenAI / × Anthropic` 两个绿格子；同域名无任何活协议时只说"此域名不支持 {当前协议} 协议"。目的：让用户一眼看懂"能力没丢、在隔壁格子"，而不是把灰色误读成"这把 key / 这个域名废了"（对齐 §4.2 灰 = 非用户可修的架构事实，红才 = 用户要动手）。
   - **(Claude live 验证 2026-06-02 修正)探测要打「推理端点」，不是 `/models`**：实测 `GET /v1/models` 在 openai 与 anthropic 两种网关上**都返回 200**（各自返回自己 shape 的清单），所以 `/models` **不能**判协议。真正判据 = 推理端点：openai 试 `POST /v1/chat/completions`、anthropic 试 `POST /v1/messages`，看哪个被接受、哪个被拒（如 `anthropic.qnaigc.com` 对 chat/completions 明确回 "Use /v1/messages instead"）。
   - **(Claude live 验证)每协议要带对的 auth header**：anthropic 兼容的第三方网关（qiniu-anthropic / openrouter）用 `x-api-key` 裸探得 401，但它们在 config 里是 verified → app 实际走 `Authorization: Bearer`。探测时 header 带错会把"能用"误判成"不通"。
2. **endpoint 真连通验证 = 批量模型探测**（不是只点一个模型；PM 2026-06-03 改）：
   - **为什么必须探模型（不能只 get-models）**：`get-models` 只证明 **apikey + URL 可达**，**不证明 protocol↔URL 匹配 / 能真生成**。实证：qiniu 的 openai URL 能 `GET /models`(200) 但 `POST /v1/messages`→404 —— get-models 过了不代表该协议能用。所以第三方必须**用模型打推理端点**才算验通。
   - **为什么批量、不靠单个**：单模型探测**不可靠** —— 实测同一个 `deepseek-r1` 一次 401、再测 200（瞬时抖动）；`minimax/glm` 间歇超时。原来让用户手选一个模型，就是怕系统自动只挑一个、它恰好抖动/超时 → **误判整个 endpoint 不通**。现在改全自动，必须用批量消除这个误判。
   - **机制**：系统**自动分批**探测（每批 ~3 个，优先挑常见可靠模型抬命中率；不一个一个、避免一长串失败浪费时间）；**一批一批打**，直到**某批中任一模型成功 → 判 endpoint 可用（停）**；或**模型探尽全失败 → endpoint 不可用**。
   - **错误码短路（省去试完所有模型）**：遇**结构性错配**码可直接判"协议/配置错"不必试完 —— openai 打 anthropic URL→`500 "Use /v1/messages instead"`；anthropic 打 openai URL→`404 not found`；未知模型→`400 invalid_request`。**但瞬时类（401 / 429 / timeout）不可短路**（与真失败靠码区分不了、且会抖动）→ 继续下一个/下一批。（修订 2026-07-02：本条的"协议错配"签名即 `protocol_unsupported` 分类的判据，见上方矩阵修订第 2 点 —— 命中即判该格子 `unsupported` 并短路整批。）
3. Probe Knowledge Catalog 行为、标签行为等等**与 official 一致**。
4. **（PM 2026-06-02/03 拍板：直接设计实现，非可选）一个 provider = 一把 key + 多个 URL**：
   - **模型（PM 校正）**：**一个 provider = 一把 key**，其下挂**多个 URL**；每个 `(URL × 探通的协议)` = 一个 **endpoint**。一个 URL 同时通两协议（openrouter）→ **两个 endpoint 都建**（确认①）。（修订 2026-07-02：按上方"协议探测矩阵"细化 —— 每个 `(URL × 候选协议)` 格子都是持久记录，探通与否只改**状态投影**，不决定记录存亡；"探通的协议"= 状态为 verified 的格子。）
   - **gateway/registry 无「卡」概念（确认②）**：只存**平铺的标准 endpoints**，**不感知它们来自一张卡还是两张卡**（card 是前端录入便利；多 URL → 标准 endpoint list 的拆分由 ③b 做，见 #3.1）；「同一 provider」靠 endpoint 共享的 `credential_ref` + `rate_limit_bucket` 表达，不是一个 card 实体。
   - **共享（确认③）**：同一把 key 的所有 endpoint 共享 `credential_ref`，且 **一把 key 对应一个 `rate_limit_bucket`**（一处限流、全部冷却）。
   - **展示**：endpoint **平铺，不做协议分组子区**；在 LLM Roles 里同一模型跨 endpoint 合并成 model group，其下 endpoint **平铺展示在 model group 的「endpoints」标签**里。
   - **探测**：每个 URL 跑协议探测（打推理端点 + 对应 auth header，见上方 item 1 两条 live 修正）。
   - **拆分 + endpoint_id 生成 = ③b gateway（#3.1 反转，PM 第四轮判据校准）**：「多 URL × 多协议 → 多 endpoint」的**拆分 + 协议匹配 + 测试 + 生成 canonical `endpoint_id`** 由 **③b gateway** 做（它内置协议 SDK，最适合把混合原始信息理成标准 endpoint list）；**前端只录入**（card / 多 URL 行），把用户填的原始信息交给 gateway、拿回标准 endpoint list 展示；**③a 只 `upsert(endpoints[])` + 存储**。`endpoint_id` = ③b 生成的 canonical id（确定性规则 `{slug}-{protocol}[-{n}]`，见 #3.2）。⚠️ 原"前端拆分 / 前端生成 id / 后端不感知 card / `_stable_endpoint_id` 退役"已被本轮反转作废——endpoint 标准化是 ③b 公共能力。
   - **命名防撞（#3.2，PM 2026-06-03；统一格式 `{slug}-{protocol}[-{n}]`，序号永远在最后）**：默认 `{slug}-{protocol}`（最短）—— `qiniu-openai` / `qiniu-anthropic`、`openrouter-openai` / `openrouter-anthropic`。**只有 `(slug,protocol)` 撞了**才在**末尾**补短序号（首个不带、后续 `-2 / -3`；**不用整段 host，避免过长**）：2 URL 都 openai → `myco-openai` / `myco-openai-2`；2 URL × 2 协议都通（4 个）→ `myco-openai` / `myco-openai-2` / `myco-anthropic` / `myco-anthropic-2`（序号一律在 protocol **之后**，且同一 `-2` 恒指同一个 URL）。
   - **各 endpoint 独立**：canonical base_url（按协议归一）、protocol、status、routes、capabilities。

### 1.3 页面定位（重要边界）
- API Keys 页面**必须验证 endpoint**（official：get-models + 一次最小生成探测；third-party：协议矩阵逐格子 get-models + 批量模型探测，半衰期未到的 `unsupported` 格子跳过；修订 2026-07-02，原"协议轮换"作废）。
- **但它不是"测试模型连通性"的主战场** —— 逐模型"保证能用"的 probe 在 role 页面做。
- 不过这里**留了入口，可以批量对单个模型做 probe**（escape hatch：需要时在 API key 页也能批量探单模型）。

### 1.4 测试结果的展示与落地（UX，PM 2026-06-03 实测反馈）
- **#2.1 结果常驻原地、不只 toast**：endpoint 测试耗时久时，结果一出 toast（sonner）就闪没、看不到（要再测一次、把鼠标悬在 toast 上才看得到）。→ 测试结果（成功 / 失败原因）除 toast 外，**必须固定写在 API Key / Base URL 旁的状态勾（✓）位置**（常驻 inline），鼠标无需追 toast。
- **#2.3 单模型测试结果换样式**：Manual probing 的单模型结果（`xx: Available` 绿 / `xx: Test failed` 红 badge）**还在用旧 model-badge 样式** → 改成与新状态体系一致的呈现（对齐 §4.2 的 route 级状态色 + inline）。
- **#2.4 测试结果全进 Probe Knowledge Catalog**：这几次的 endpoint / 模型探测结果（**含失败**）都要写进探测知识库，**不浪费**（失败也是历史：哪些模型抖动 / 超时 / 不可用；下次免重探、喂蓝态）。见 §4.1。
- **#2.5 错误码→用户文案 = 英文（回填 A7，PM 2026-06-03 定 UI 语言 = 英文）**：测试失败的可读诊断用**英文**，权威源 = 现网 `apps/studio/frontend/src/lib/llm-error-messages.ts`（已在 ProviderCard / Settings 用，含 HTTP 状态映射 + `composeTestErrorMessage`）；旧 `studio-api-keys-redesign/design-frontend.md §4.3` 的**中文整表作废**。**产品 UI 语言 = 英文**（非 A7 独有：Connected / Not configured 等全英文）。§1.4 的 inline 常驻诊断 + toast 都用这套英文文案。

---

## 2. LLM Roles 页面 — 把抽象角色映射到模型，并真实测通

> 本节 = §0 原话 + **2026-06-03 第二轮原子动作走查**（PM 逐条裁定，原话见 §2.0）的细化定稿。本节整合三股改动：① ux-spec 状态体系（6 态 / failed-disabled 两分类 / Probe Knowledge Catalog，见 §4）；② 上一 part 底层改动（P8 run 模型对比测试复用 model-group/bundle；D10/D12 settings 数据走 gateway sidecar 永不 Rust）；③ gateway mvp1 契约（role→route 一等 API、base_url 保存时归一化、`build_runtime_setting_descriptors` 驱动 intent 控件，见 §6.2）。

### 2.0 PM 原话（2026-06-03 第二轮 Roles 走查，verbatim，不改一字）
> 1. #R3 在model family上做一个折叠功能: anthropic 可以折叠起来, 隐藏里面的所有模型
> 2. #R12 , 如果变成3档, UI组件应该换一下, 这三档是互斥的 , 不能用两个开关表达;
> 3. #R13, 默认策略不需要 UI
> 4. intent配置的UI布局现在有点丑, 要稍微优化一下, 不要大改逻辑, 调整一下里面的布局就行;
> 5. #R18, 这个面板是我删掉不要了的; 加重UI复杂度, fail信息在tooltip里面展示就可以了; 然后provider row 里面的tooltip还有嵌套冲突的, 清清干净, 就一个顶层的tooltip
> 6. #R20, Add model bundle这个按钮放到和Add role统一的位置
> 7. #R22, 前端复用role, 和role统一
> 8. #R23 应该要同步
> 9. #R24 和role 统一
> 10. 现在有一个状态叫做needs_setup, 这是一个什么状态? 要setup什么呢??
> 11. "P8 跨页耦合：run 的模型对比测试" 认可; 还有一点, 在设置的properties面板里面, 每一个role旁边, 增加一个test键, 快捷test能不能用,就不用切到setting里面再去测试了; 在配置role 的时候也要能展示role的状态
> 12. "束拖进角色 = 快照 vs 引用" 引用

### 2.1 可用模型侧栏（Available Models）
**过滤规则**（右侧"可用模型"按规则过滤后才出现）：
- **是 LLM 模型**（text→text 语言推理模型，判据是模态）。模态过滤归后端 `_include_route_in_model_groups`（决定一条 route 是否进 model group 的函数，`llm.py:1506`）；embedding/image route 不进可用模型。
- **endpoint 状态投影**：模型（组）只要在 registry 里就出现；组内各 provider 行显各自 6 态。**配置缺口 → `failed`（红）+ 引导、不隐藏**（PM 裁定取消 needs_setup，见下）：缺/错 key、base_url、protocol、model id 的 provider 行在组内**标红 + 「去配置」+ 点击引导去 API Keys 页修**，**不静默过滤**（修现状 catalog #35「看不到为何缺」），且不默认选中。定义见下「failed vs cooling_down vs disabled」。
- **`failed` 不被过滤掉**（对齐 §4.2 两类失败）：endpoint 测通后，其下单条 route 即便 probe `failed`（红）**仍列在可用模型、仍可拖**（换 role 配置 / 重试可能就好，真正永久不可用在运行期 admission 拦）。
- **`disabled`（弃用）入弃用区**：不在主列表（见弃用区）。
- **singleton / 未知模型卡（回填 B7）**：后端无法把某 provider model 自信归入任何已知组时，**仍渲染成同格的 model-group 卡**（singleton；后端按 `canonical_id` 键，缺则按 `route_slug`，执行仍用精确 `route_id`）。前端只渲染该 DTO、不自己 canonical 化。

**model family 折叠**〔#1〕：侧栏按 model family（anthropic / deepseek / openai / gemini …）分区，**每个 family 可整体折叠**，折叠后隐藏该 family 下所有模型卡（长列表收纳）。现码 `buildAvailableModelGroups`（`AvailableModelsSidebar.tsx:377`）已按 `section`（family）分组渲染，但**无折叠**→需加 per-section 折叠态（纯视图态，localStorage / 组件态即可，不入后端）。

**6 态色 + 弃用区**：模型卡内每个 provider 行显该 route 的 6 态色（🟢 verified / 🔵 以前联通过 / ⚪ untested / 红 failed / 灰+倒计时 cooling_down / 灰+不可选 off；见 §4.2）。现码 `buildAvailableModelGroups`（`:385`）只留 ready/cooling/untested、**滤掉了 failed**——需改为保留 failed（红、可拖）。
- **弃用区**（可折叠）：`disabled`（弃用）模型进此区，灰显、hover 显**禁用图标**、**不可拖进 role**；但**可复制模型名 + 可单独 re-probe**；**re-probe 再次连通 → 从弃用区捞回可用模型**（弃用可逆，模型可能又上线）。现码无此区，是新增 UI。

**provider chip 聚合 = 真聚合，不是丢弃（修订 PM 2026-07-02，随 §1.2 协议探测矩阵）**：同一模型在同一 provider 名下有多条 route（多 URL × 多协议 transport）时：
- **侧栏 chip**：聚合成一个 provider chip 合理，但必须**带成员数量角标**（如 `Qiniu ×4`）+ **tooltip 列出每条 transport**（URL × 协议 × 各自 6 态）。实证反例（2026-07-02）：GLM 5.1 有 4 条 verified Qiniu route，现码 `collapseDuplicateProviderLabels` 只留排序最优 1 条、其余静默丢弃，无数量、无 tooltip —— 用户不知道另外 3 条存在。
- **拖入 role 面板**：落下时把该 provider 的**全部** transport route 写入 role 配置，并在 provider 链里**展开为 provider 内部的 fallback 子序**（同 provider 的多 transport 可拖动排序、可单删），不是只存被折叠选中的那一条。实证反例（同日）：拖 GLM 5.1 进 role，`llm_roles.yaml` 只落 1 条 route（选哪条用户不可见不可控）。
- 此设计与「§1.2 确认②endpoint 平铺进 model group 的 endpoints 标签」一致——聚合只发生在**展示**层，配置与执行永远面向 route 全集。

**failed vs cooling_down vs disabled（PM #10「needs_setup 是什么」的最终裁定，定义留底）**：三个「不能直接用」的状态正交，别混。**取消原 `needs_setup` 灰态——它本质是 `failed` 的一个 reason（配置缺口），并入 failed 显红**：

| 状态 | 含义 + reason | 颜色 | 谁来动 |
|---|---|---|---|
| `failed` | 出错了、要你修。两类 reason：① **配置缺口**（endpoint 级：缺/错 key、base_url、protocol、model id）→ 去 API Keys 页补；② **测试失败**（route 级：endpoint 通了但单模型这条 route 真探挂）→ 换 role 配置/重试 | 🔴 红 | **用户**（补配置 / 排查重试）；红、**不挡**进可用 |
| `cooling_down` | 配是好的，刚才网络/限流/超时，临时熔断 | 灰+倒计时 | **无人**，倒计时后自动重试 |
| `disabled` | 用户主动关 / 模型已下线（route 级） | 灰+不可选 | 进弃用区，可逆（re-probe 捞回） |

> **为什么取消 `needs_setup`**（PM 裁定）：①「配置缺口」本质是一种 failure，和 `failed` 同族；②灰色会和 `untested`（没测、中性）混淆，弱化"这是致命错误"；③现码 `_setup_reason`（`llm_state_projection.py:49-56`）反而把真·测试失败（endpoint/route failed）也揉进 `needs_setup` 显灰——双重混淆。**裁定：取消 `needs_setup`，统一 `failed`（红）+ `reason`（`missing_config` / `endpoint_unreachable` / `model_failed`）**。颜色心智：**红=出错要你修；灰=非错误的不可用（untested 没测 / cooling 熔断中 / off 关了）；绿=好；蓝=以前好。**

### 2.2 配 role 的步骤
1. **新建 role**（弹框命名，允许建无模型空壳）。
2. **拖动 model group 到 role card**：
   - model group = **相同模型合并**（同一个模型跨多个 provider 归一成一张组卡）。
   - endpoint 的**状态颜色与 API key 页面一致**（同一套 UI state 投影；🔵 蓝=以前联通过）。
   - 拖入后**默认选 provider**：含 ready + untested + 🔵 蓝（可用候选），排除 failed / off，cooling_down 有替代则不默认选；official 优先（除非 role 偏好覆盖）。算法见 §6.2 引用的 765 设计 7 步。
   - **provider 排序三模式 + manual_order 锁（回填 B3，2026-06-03）**：`RoleIntent.provider_preference` 三档驱动默认排序——`official_first`（默认）按 `provider_kind`（official 先；用持久化 kind，不靠前端猜名）/ `ready_first` 按 UI 态（Ready 先于 Untested）/ `manual_order` 保留 registry/用户顺序。**锁**：一旦设 `manual_order`，materialize **不得**再为 official/ready 自动重排——用户手排即权威。
   - **重复拖入去重（回填 B7）**：把一个**已在该 role 里**的 model group 再拖进来，**不建副本** —— 聚焦/选中已有那张卡，或按默认选择策略**合并新可用的 provider**。
3. **调兜底序**：model 之间拖序（谁先试，active_model 同步首位）；同一 model group 内 provider 链拖序（只改该模型 provider 顺序）；`Add provider` / 垃圾桶移除单 provider；删整组。
4. **Model Fallback 开关**：关 → 只用首个 model group（provider 兜底永远在）。

### 2.3 Role Intent（角色意图 = 三个生成参数）
> **改动说明（PM 2026-07-01 拍板简化；PR3 落地，替换旧设计、删旧路径）**：旧 §2.3 把 role intent 做成一套复杂机制——thinking 三档（off/preferred/required）、token 用 `TokenIntent{mode 四档}`（default/maximum_available/target/**required_minimum**，其中 required_minimum 还驱动"route 输出上限不够→not_fit 踢出 fallback"）、外加 `downgrade`（allow/warn/block）与 `target_context_tokens`。**这套整体作废**，理由 = PM 原话："thinking 只需要开关就够了""output token 不需要给选项，填一个数字就行""context token 设置没有意义"。**按"不向后兼容、换掉即删干净"**（AGENTS.md 开发原则 1），PR3 把 thinking→开关、token→纯数字 clamp、删 context token + required_minimum/downgrade 机制、补 temperature。gateway 每条 route 的底层 `RuntimeSettings`（`temperature`/`max_output_tokens`/`reasoning.enabled`）**保留**——它是参数真相载体；动的是 studio `RoleIntent` 语义层 + 物化 + 前端 + 对应测试。

角色 intent 现在就是**三个生成参数**，都在 **role 级**设（铁律：只对 role 提要求，不逐 model-group、不逐 provider）：

- **Thinking（开关）**：单一 `Switch`（on/off），不再是三档。**语义 = best-effort**：开关开且模型支持 reasoning → 用；模型不支持 → 就不用（不报错、不静默降级出错）。落到 gateway `reasoning.enabled`（本来就是 bool）。**Test 时开关开但模型不支持 → 警告，不阻塞**（不像旧 required 档那样把 route 判 not_fit）。旧的 off/preferred/required 三态控件 + required 的 not_fit 逻辑删除。
- **Max output token（纯数字）**：一个数字输入框，**不给 mode 选项**。机制固定:**不填 = 用模型/route 的最大可用输出 token**；填的数字 **> route 上限 → 取上限**、**< route 下限 → 取下限**（clamp，不再 not_fit、不再 downgrade）。输入与展示**自动加千位符**（PM 撤回了 k 单位，一律全数字）。placeholder 提示按当前配置**推断出的有效最大 token**。落到 gateway `max_output_tokens`。旧 `TokenIntent{mode}` 四档 + `required_minimum→not_fit` + `downgrade` 删除。
- **Temperature（Slider，默认 70%）**：role 级温度使用 0-100% Slider；存储仍是 provider-neutral authored 0..2 数值，因此默认 70% 对应 `temperature=1.4`。拖动时只更新本地读数，松手/键盘结束/focus 离开等交互结束点才触发保存；若底层 Slider 只发 preview 没发 commit，结束事件也必须提交最后一个 preview，不能出现 UI 变了但没落盘。保存中如果又产生新需求，只保留最新 payload，旧保存完成后立即用最新值覆盖。落到 gateway route `temperature`（route 级本来就有该字段，role 级此前缺，补上）。role intent 不再把空 temperature 当作 model default；缺失或 null 必须在 Studio role authoring 层归一成默认 70%。
- **Context token：不做**（PM：没有意义）——`target_context_tokens` schema + UI **整块删除**。
- **Route max token 摘要**：投影 route capability，只读（保留，用来给 output token 输入框算 placeholder 的推断上限）。
- **`cost_priority`**：早已砍掉（PM 2026-06-03），schema 不留。
- **provider_preference（manual_order）**：不属于这三个生成参数，是 provider 排序意图，**保留不动**。

**节点级覆盖（PR3 同批做）**：节点 Properties 面板对这三个参数**直接覆盖、无开关字段**（PM 原话："节点覆盖 role 不用做开关，直接覆盖就好"）。节点覆盖**不进 SKILL.md**（llm 参数是 gateway 域配置真相，skill 源只放符号引用）；存 studio 后端**按 skill+phase**（和 compare 候选同族存储）。技术支点：engine 的 `model_resolver.resolve` 本来就带 `phase_name` 入参（`_GatewayBackedLLMProvider.invoke` 已把 phase_name 传进 resolve），studio 侧 resolver 按节点应用覆盖，**PR3 完全不改 engine**。phase 改名时同步迁移该存储 key。

### 2.4 状态展示与 tooltip（清理）
- **role-fit 状态灯**：role card 内每 provider 行显 role-fit（Using / Downgraded / Needs Test / Not Fit，role-local 派生，从不改全局 health；来自后端 materialize report）。
- **单一顶层 tooltip**〔#5〕：fail / downgrade 信息**只在 tooltip 展示**，不另起面板。**`RoleTestResultPanel`（角色测试结果面板）已被 PM 删除、不要**（避免加重 UI 复杂度）——不挂载、应清理。
- **清嵌套 tooltip**〔#5〕：provider row 现有**嵌套 tooltip 冲突**→清理为**一个顶层 tooltip**。

### 2.5 Role 测试
- 点 **Test** → 对 **role 里所有模型批量真 probe**（不停在第一条成功）→ 实时回填状态灯 + downgrades（进 tooltip，§2.4）→ **结果（含失败）回写 Probe Knowledge Catalog**（§4.1）。
- BE：`POST /api/llm/roles/{name}/test` + `/test-jobs`（异步轮询，`llm.py:996/1009`）；evidence 回写部分已在（`_append_model_probe_evidence`，`:771`）。
- **后端 SSOT**：删前端易失 `roleTestStates`，测试态全以后端 job / 投影为准（切 tab / 刷新不丢）。
- 未保存先拒测：role 测试 = 先 `PUT` 保存再 test。

### 2.6 Model Bundle（与 Role 高度统一）
- **统一模型（地基，2026-06-18 PM）**：**model-group、model-bundle、role 本质都是「一串 routes 的数组」**，最终都被 materializer **展开铺平成一条 fallback_chain**。所以三者特性应**一致**：bundle 在 role 里和 model-group **同级、可拖、可调序、可逐模型/逐 provider 配（因为它就是 routes）**；copilot role 也是这套（§3）。区别只在"谁拥有这串数组"：model-group=registry 归一出来的、bundle=用户自建可复用的、role=用户为某个用途编排的。**任何 group/bundle/role 的语义，先回到"它是一串 routes"去推。**
- **定义**：Model Bundle = 自建的"已排好 fallback 的 model group"；与 model group 区别：可放**不同模型**、**预配 provider**；可像 model group 一样拖进 role card 解析成 route list。
- **Pinned 置顶槽〔回填 B4，PM 2026-06-03 要〕**：已配好/已测的 Model Bundle 在 Available Models **顶部单独成槽、视觉区分**显示（置于 model-group 列表之上），强调可复用，与普通 model group 视觉区分开。
- **统一原则**〔#6/#7/#9〕：bundle 的录入/测试/改名删除 UI **与 role 统一**——
  - `Add Model Bundle` 按钮放到**与 `Add Role` 同位置**〔#6〕。
  - 束 **Test 前端复用 role 的测试**（同组件 / 同路径，束也能独立测）〔#7〕。
  - 束 **Rename / Delete 与 role 统一**〔#9〕。
- **拖进角色 = 引用（live 同步）**〔#8/#12〕：把束拖进角色后是**引用**，不是快照——**改束 → 所有引用它的角色同步跟着变**（像共享组件实例）。**此条覆盖 765 设计的"快照复制"方案**。落地含义（2026-06-18 PM 补全的边界）：
  - 角色存的是 bundle 引用（`bundle_id`），materializer 物化时**按引用拉取当前束内容**展开成 fallback_chain（**不在拖入时复制**）。「同步」= 物化时永远读束的最新内容，所以束改了，下次物化/测试自然就是新的。
  - **删除级联**：束被删 → 引用它的角色里**那一项引用也随之消失**（不是留个失效快照）；该角色重新物化时少了这串 route（可能转 not-fit，按 §2.5/§6.2 的可执行性判定）。
  - **role 可覆盖**：因为束在 role 里就是一串 routes（与 model-group 同级），role 对它**照常可调序 / Add / 删 route / 配 provider**——这些是 role 自己的编排，不回写束本体（束是共享的；role 的局部调整只活在该 role 的 routes 数组里）。〔存储语义见 §2.6 末尾「已定」〕

- **✅ 已定（PM 2026-06-18 拍板）：引用 + 局部覆盖的存储语义 = 方案①（引用 + delta），束为源头、删除同步优先。** role 对一个**被引用的束**做局部改动后：仍存 `bundle_id` 引用 + 一份"该 role 的覆盖 delta"（调序 / 删某条 / 加 route / 配 provider 都记成 delta）；物化时**先按引用拉取束的当前内容、再叠加该 role 的 delta**。
  - **冲突解析铁律——束是源头**：束删掉某条 route，就从该 role 的链里移除，**哪怕 role 对它做过本地覆盖**；role 的局部覆盖只对"仍存在于束里的 route"生效，束里已不存在的 route 上的 delta 自动失效丢弃。
  - 这样**不需要**"一改就脱离引用、固化成快照"的第二套机制；行为与上面「拖进角色 = 引用（live 同步）」「删除级联」完全一致——束永远是单一真相源，role 的 delta 只是叠加在它之上的局部编排。

### 2.7 跨页：role 状态 + 快捷 Test 进 Properties 面板〔#11〕
- **节点 Properties 面板**（作者 / 运行期给节点指定 `llm_role` 的地方）**每个 role 旁加 Test 键** + **展示 role 状态**——快捷验"能不能用"，**不必切到 Settings 再测**。
- 复用 §2.5 role 测试 + §2.4 role-fit 状态投影；**跨 region**：Roles 能力的测试/状态投影进 `phase-editing` / properties region 协同（非本页独占）。

### 2.8 P8 跨页：节点级 Compare LLMs — 候选只选模型 + 旁路单节点多跑〔#11 认可；2026-07-02 重定〕
> **改动说明（2026-07-02，PM 拍板）**：旧文案是"run 模型对比测试可选 role / model-group / bundle → 解析成临时 role、整图按角色扇出多跑"。**这条已作废**，原因有二：① 候选**只选模型**（model group + endpoint route），**不做 role / bundle**——有意简化，对比的语义就是"同一个节点、同样输入配置、只换底层模型"，牵进 role/bundle 会把"换模型"和"换角色定义"混成一件事；② 对比**不再整图按角色扇出**，改成节点级旁路单节点多跑（见下）。旧的整图扇出链（`CompareRunDialog` + `POST /runs/compare` 按角色 fan-out + `run_compare.py` 整图 roles 物化）**同批删除**。

- **候选 = 模型**：在**节点 Properties 面板**的 `Compare LLMs` 区块配置，每个候选 = 一个 model group + 一条 endpoint route（"auto" 或具体 route）。候选**持久化在 Studio 后端**，按 `skill + node` 归属（不写进 SKILL.md——对比是运行期实验配置，不是 skill 源文件的一部分）。节点改名时后端存储的 key 要同步迁移。
- **运行机制 = 旁路单节点多跑（不改 engine，不写主黑板）**：对比在真 run 时发生，但**不往图里注入并联节点**——实证坐实当前 V0.3.0 引擎跑不了任意"两节点同超步并联"（`WorkflowState.data` 是无 reducer 的 LastValue 通道，同步写就 `InvalidUpdateError`；连死胡同影子节点都炸）。改为:
  1. 主图照常用**基准模型**跑一次，完全不动；
  2. Studio 从主 run 的 `InputDispatchEvent`（引擎在每个节点入口发的事件，携带喂给该节点的确切黑板输入切片）抓到对比节点的真实输入；
  3. 对每个候选，把**这一个 phase** 物化成一个单节点临时 skill 变体（`depends_on=input`，把切片当输入）+ 一份候选临时 roles，走**现成的 `run_artifact`** 跑一遍。
- **天然满足三条边界**：单节点独立 run ⇒ 没有并联通道冲突（不改 engine 执行逻辑）；物理上是独立 run、碰不到主运行的状态机（**永不写主黑板**）；每个候选自带独立 run 目录（**per-candidate artifacts 各自落盘、分目录**，白送）。仅底层 llm 不同，输入/其他配置与基准一致。
- **结果展示**：进 Trace **顶部 tab**（[D13](../04_run-and-verify.md)）——focus 对比节点时，基准输出 + 各候选输出并排切换。详细归 `timeline` / properties region，本页只登记"model group + route 多了'节点级对比候选'这个消费方，且对比运行机制 = 旁路单节点"。

### 2.9 测试关键点（§5 硬栏，写测试时必须验证）
- **failed 仍在可用**：构造一条 route probe 失败（非弃用类）→ 断言它**仍出现在可用模型、标红、可拖**（防回归成"失败即消失"）。
- **disabled 才灰且不可拖**：provider 明确返回"无此模型 / 已下线" → 归 disabled → 进弃用区、不可拖、可复制名 + 可 re-probe → 再通**捞回**可用模型。
- **蓝态**：endpoint 验通 + Probe Knowledge Catalog 有历史连通 → 该模型显 🔵 蓝；role 页真 probe 通 → 升 🟢 绿。
- **配置缺口红显引导**：缺 key / 无效 key / base_url / protocol / model → `failed`（reason=配置缺口，红）→ 组内**标红 + 「去配置」+ 引导去 API Keys 修**（不隐藏、不默认选）。
- **role 测试批量**：role Test 探**所有**模型（非停首条成功），失败也回写 Probe Knowledge Catalog，切 tab / 刷新**不丢**。
- **bundle 引用同步**：改 bundle 内容 → 所有引用该 bundle 的 role materialize 出的 fallback_chain **跟着变**（验引用非快照）。
- **thinking 开关（PR3 简化）**：单一 Switch（on/off）；开关开且模型不支持 reasoning → **警告不阻塞**（不再 Needs Test / Not Fit）。旧 off/preferred/required 三档 + required→not_fit 已删。
- **max output token 纯数字（PR3 简化）**：无 mode 下拉；不填=route 最大、超上限取上限、低下限取下限（clamp），不再 not_fit/downgrade；输入即时千位符。
- **temperature（PR3 新增）**：role 级数字输入落到 route temperature。context token 已整块删除。
- **model family 折叠**：折叠态是视图态，刷新后保持（localStorage），不污染后端。

---

## 3. Copilot 页面 — 与 LLM Roles 类似，两点不同

> 本节 = §0 原话 + **2026-06-03 第二轮原子动作走查**（PM 逐条裁定，原话见 §3.0）的细化定稿。现状定性（亲验 file:line）：**这页桩/mock/假测试最多**，但 PM 早前已拍「copilot 必须全功能、不延后」→ 现状的桩/mock/假测试/bug 一律标「现状 gap → 接线工程」，非可接受限制。

### 3.0 PM 原话（2026-06-03 第二轮 Copilot 走查，verbatim，不改一字）
> 1. C10, 要有可搜索的选项卡 ;
> 2. 动态, 但是默认只浮出 Claude和deepseek 在available models最新最好的模型, claude 优先opus4.8, deepseek 优先V4 pro. 没有的话再往后退, opus4.7, deepseek V3.2 Pro;
> 3. copilot-eligible 判据:对 , 但是有个问题是,你没测试的时候不知道, 所以还是会显示在available models里面(just keep them in there),
> 4. "Backend Integration" 徽章 这是什么

### 3.1 与 LLM Roles 的同与不同
- **同**：同构的角色配置 + 拖 model group + 测试回写；UI 尽量复用 role（与 §2.6 bundle-role 统一同一精神）。
- **不同点一**：copilot 的 role **只能填一个 model group**（不像 graph role 可多组 / bundle）。现码 `modelGroupOptions`（可选组列表，`CopilotTab.tsx:171`）已滤掉已选组，单组约束已在。
- **不同点二**：测试**走 copilot 自己的调用**（`claude_agent_sdk` 的 `ClaudeSDKClient`，spawn claude CLI、base_url 经 `ANTHROPIC_BASE_URL` env 注入；`copilot.py:242`）—— 所以 copilot 的"测试"和"真实调用"**本应没区别、不存在假测试**。**但现状有假测试**（见 §3.4）。

### 3.2 可用模型 + 内置角色动态浮出
- **eligible 判据 = 后端投影的 `copilot_sdk_compatible`**。前端不看 protocol、不维护 method 白名单；Studio 后端从 gateway 的 `call_methods.json` 读取 method 对 `anthropic_messages_client` 的兼容性：已知支持(anthropic / deepseek / ark / openrouter 的 Anthropic Messages method)放行，已知 OpenAI/Gemini/普通 chat method 不兼容则过滤，未知 method 保留可测，再叠加 tool loop capability 的显式不支持证据。它**取代前端 `isClaudeAgentSdkCompatibleRoute` 名字启发式**。
- **未测试也显示、不预过滤**〔#3〕：PM 原话"你没测试的时候不知道，所以还是会显示在 available models 里面（just keep them in there）"。即 SDK 工具调用能力**未测时未知**，不能据此把 route 滤掉 —— 与 §2「untested/failed 不滤」同一原则；真 SDK 测试（§3.4）才确证。
- **内置角色 = 动态浮出**〔#2〕：**不写死 2 个**，而是**默认只浮出 Claude 和 DeepSeek 在 available models 里最新最好的模型**，按 family 偏好阶梯择优：
  - **copilot 默认模型 = DeepSeek V4 Flash（PM 裁决 2026-08-06）**：available 里有 `deepseek-v4-flash` → 它浮出且**排位第一**（composer role picker 的初始角色 = 排位第一的浮出组），取代 2026-07-02 的「默认 opus4.8」。
  - Claude：优先 **opus 4.8**，没有则退 **opus 4.7**（再往后退更旧）。
  - DeepSeek 不再有 pro 候选梯队（PM 裁决 2026-08-06「去掉 deepseek v4 pro」：V4 Flash 是唯一的 DeepSeek 内置）。
  - **固定 copilot 角色 = 固定模型（PM 裁决 2026-08-06）**：内置 copilot 固定角色为 `copilot_claude_opus_4_8` + `copilot_deepseek_v4_flash`（v4 pro 退出）。固定角色的模型组绑定**不可移除、不可换组**——UI 不提供入口（无移除按钮，拖拽换组被拒），写路径（bulk 与单角色 PUT）在边界拒绝（422）；唯一例外是把冷态空绑定修复为推荐模型组（reconcile 负责冷态）。
  - 都没有 → 不浮出默认，用户自建。现码硬编码映射 `copilot_opus_4_7`↔`claude-opus-4.7`（`CopilotTab.tsx:132-133`）需改为此动态择优。
- **本质（2026-06-18 PM 澄清）：copilot 的"内置角色"= 自动选了一个 canonical model-group**（如名为 `opus4.7` 的组），**复用 model-group 现成的 canonical_id 归一化**（各 provider 五花八门的 opus4.7 model name 归一成同一个标准 name —— 这套 §2.1「相同模型合并 / singleton 按 canonical_id 键」已经有）。所以**「内置 vs 第三方」不需要新的后端 role 元数据契约**：内置 = 自动选了 canonical 组、third-party = 用户自建组；前端**不要靠硬编码 model-id 白名单 + `includes('Claude')` 套模板判定**（现码 #55 的脆做法），而是看这个 copilot role 选的是不是系统按阶梯自动浮出的 canonical 组。

### 3.3 配 copilot 角色
- 新建第三方 copilot 角色草稿（`Add model`），id = `copilot_custom_N`（`CopilotTab.tsx:202`，带前缀✓）。
- **选 Model group = 可搜索的选项卡**〔#1〕：C10 的选组器要**可搜索**（同 §2.1 可用模型搜索体验），不是裸下拉。
- route 兜底序拖排 / Add / 删 route（eligible 判据见 §3.2）。
- 单 model group 约束（§3.1）。

### 3.4 测试 = 真 SDK 调用（修假测试，核心）
- **现状假测试**：`_probe_copilot_sdk_tool_call`（copilot SDK 测试探针，`llm.py:2150`）用 `AsyncAnthropic`（裸 Anthropic HTTP 客户端，`:2156`），而真实 copilot 跑 `ClaudeSDKClient`（`copilot.py:242`）→ **测的 SDK ≠ 跑的 SDK**，测过不证明 spawn/env 注入/tool loop 能跑。
- **目标**：测试改走**真 `ClaudeSDKClient` 路径**（见本页 §3.8 Copilot SDK 调用机制），发真工具调用、验 spawn/env/tool loop；成功**写高阶证据**（SDK 工具调用验证通过）回 credentials + Probe Knowledge Catalog。
- copilot 应走 **role→routes 一等 API**（`resolve_routes`，gateway 02 目标），不再自己手装 registry snapshot（现 `_resolve_copilot_runtime` 手装，`copilot.py:419`）。

### 3.5 现状 gap → 接线工程清单（亲验 file:line）
- **去 mock**：`mock-copilot-data.ts` 全套 + `mockCopilotRoles` 死代码（仅 test 引用）清理；默认 props `defaultCopilotModelGroups`（`CopilotTab.tsx:58`）→ 接真 registry（`buildCopilotRolesFromRealData`，`:117` 主导）。
- **🐛 copilot_ 前缀分流 bug（必修）**：`selectModelGroup`（`:219`）选组后把 role 键改成**裸 `modelGroupId`**（`:232/242`，如 `claude-opus-4.7`，丢 `copilot_` 前缀）；后端 `_is_copilot_role`（`llm.py:905`，`startswith("copilot_")`）→ **误判成 graph-agent 角色错存**。修：选组后 role key 保 `copilot_` 前缀。
- **「Backend Integration」假徽章 → 统一 save-status badge**〔#4，PM 校正：不是删，是换成和前两页一样的保存状态标签〕：现 `<Badge>Backend Integration</Badge>`（`CopilotTab.tsx:79` & `:302`）是写死装饰、不反映真实状态。改成**统一 save-status badge**（依据 `FRONTEND_UI_SPEC.md:76`「Settings 表单字段变更实时保存并显示保存状态、不放独立 Save 按钮」），放同一 header trailing slot，**接 Copilot 真 `saveStatus`**（修 `void saveStatus; void error`，`:70` 丢弃）。状态集同 `RoleSaveStatusBadge`（`RoleBadges.tsx:5`）：idle→静默不显 / pending→Pending / saving→Saving / saved→Saved / 失败→错误（**失败显式告警不静默**，D8 铁律）。
- **统一组件（横切）**：现状是**三份近重复** badge —— `SaveStatusBadge`（API Keys，`ApiKeysTab.tsx:19`）/ `RoleSaveStatusBadge`（`RoleBadges.tsx:5`）/ `AppSettingsSaveStatusBadge`（`GeneralTab.tsx:12`），都吃同一 `SaveStatus` 类型。按"统一组件"要求应**合并成一个共享 save-status badge**，四页（General / API Keys / LLM Roles / Copilot）共用。（API Keys 已闭环，consolidation 作横切登记、不重开该页。）
- **fallback 只取首条**：`_resolve_copilot_route`（`copilot.py:445`）只取首条 route → 走完整 fallback 链。
- **占位按钮**：model-group 行 Remove 现 disabled 写死无 handler → 接 handler。
- **SDK 状态灯**：现按 `ui_state==ready` 粗映射 → 来自真 SDK 测试结果。

### 3.6 session 持久化边界（D8，不在本页）
- copilot **对话 session 持久化**（落盘、退出恢复一模一样）+ **写盘/读回失败显式告警不静默**属 **copilot 聊天（skill 工作台 region）**，归 D8；**settings §3 只配「用哪个模型」**，session 持久化在 [`00_settings.md`](./00_settings.md) §5 失败退路登记，不在本页实现。
- copilot 脑子（领域知识）= 一个 graph skill（D5），别处配；settings §3 配的是它跑用的 model。

### 3.7 测试关键点（§5 硬栏）
- **真 SDK 测试**：Test 走 `ClaudeSDKClient`（非 `AsyncAnthropic`）—— 验 spawn/env 注入/tool loop 真跑通（测试通 ⟺ 运行通，消灭假测试）。
- **copilot_ 前缀**：新建 + 选组后 role key **仍带 `copilot_`** → 后端 `_is_copilot_role` 归 copilot、不错存 graph-agent。
- **未测也显示**：未测 route（SDK 能力未知）**仍在** copilot 可用模型（不预过滤）；测试才确证。
- **默认浮出阶梯**：`deepseek-v4-flash` 在 available 里 → 浮出且排第一（copilot 默认模型，PM 裁决 2026-08-06）；Claude 有 opus 4.8 → 浮出 4.8，只有 4.7 → 浮出 4.7。DeepSeek pro 梯队已退出（2026-08-06）。
- **fallback**：多 route 按顺序尝试（非只首条）。
- **保存反馈**：改完显保存中/已保存；失败显式告警不静默。
- **去 mock**：无真数据时空态/骨架屏（非 mock 种子）。

### 3.8 Copilot SDK 调用机制（③a Studio 领域；原 gateway 模块 12 移除后内容留此，不丢）

> **来源迁移**：以下是 Copilot 拿到 route 后**怎么用 `claude_agent_sdk` 真正调**的现状机制。按第四轮判据，**gateway 库不感知 copilot**（只给 `copilot_chat` route），SDK 调用 / session / 事件翻译 / 假测试全属 **③a Studio 领域**——故 **2026-06-03 移除 gateway 模块 12「copilot-invocation」**（copilot=③a 应用、不构成 gateway 模块），其全部内容完整留在本页 + 能力 [[copilot-assist]]，gateway 侧只保留「把 `copilot_chat` 当普通 role 解析成 route」（gateway 模块 01 的 route 级 API）。代码均在 `apps/studio/backend/app/services/copilot.py`（行号以当前源码为准）。

**A. session 缓存键**：`make_session_key`（用 skill、模型、endpoint 和 API key 哈希生成 SDK session cache key，`copilot.py:93`）保证换 key 后不会复用旧进程。`get_or_create_session`（复用同一 skill/model/provider/key 组合的 `ClaudeSDKClient`，`copilot.py:276`）减少重复 spawn SDK 会话。

**B. env 注入（base_url 不走构造器）**：`build_options`（把 API key、base_url 和 provider 特殊 env 写入 `ClaudeAgentOptions.env`，避免改全局 `os.environ`，`copilot.py:112`）固定写 `ANTHROPIC_API_KEY`（`:121`），route 有 base_url 时写 `ANTHROPIC_BASE_URL`（`:122-123`）。注释说明 Claude SDK `__init__` 不接受 base_url，只能 per-session env 注入（`copilot.py:1-8`）—— 这正是裸 SDK 测试覆盖不到的关键差异。

**C. 一次用户消息主循环**：`stream_query`（Copilot 一次消息的主调用循环，`copilot.py:201`）先调 `_resolve_copilot_runtime`（读 credentials + roles 构造 registry snapshot，调 `resolve_role(snapshot,"copilot_chat",route_override=...)` 得有序 `ResolvedRoute` 列表，`copilot.py:419`）；遍历 routes（`:218-220`），每条先由 `_resolve_route_runtime`（把一条 `ResolvedRoute` 转成 SDK 需要的 `api_key/base_url/env_overrides`，`copilot.py:449`）取 secret/base_url/特殊 env；缺 credential 或解析失败时多 route 记录失败继续下一条、单 route 直接 yield `CopilotEventError`（`:225-238`，这是 Copilot 本地 fallback，不走 `GatewayChatModel._generate`）；成功后 `get_or_create_session` 建/复用 `ClaudeSDKClient` 再 `connect/query/receive_response`（`:242-256`）。全 route 失败才 yield `CopilotEventError("all configured Copilot providers failed")`（`:264-273`）。

**D. SDK 消息翻译**：`_translate_sdk_message`（把 SDK message 翻译成 websocket event，`copilot.py:364`）把 `AssistantMessage`/`ResultMessage` 的 TextBlock→`CopilotEventText`、ToolUseBlock→`CopilotEventToolUseStart`、ToolResultBlock→`CopilotEventToolUseResult`、结束→`CopilotEventDone`（`:364-409`）。输出是 websocket event，不是 LangChain `ChatResult`——这是 Copilot 不归 `GatewayChatModel` 调的根本原因。

**E. 假测试现状（要修）**：`test_copilot_role_sdk`（角色 SDK 测试端点，`routers/copilot.py:89`）调 `_probe_copilot_sdk_tool_call`（`routers/llm.py:2150`），后者实际用 `anthropic.AsyncAnthropic` 走 messages API（`:2150-2172`），而真实运行用 `ClaudeSDKClient` + per-session env（`copilot.py:242-252`）。→ **测的 SDK ≠ 跑的 SDK**，测过不证明 spawn/env 注入/tool loop 能跑（§3.4 的核心修正项）。

**F. call method catalog = ③b 调用方式真相源（不属 copilot 领域）**：`packages/graph-agent-gateway/src/graph_agent_gateway/registry/call_methods.json` 是 provider call method 的运行时配置真相源，声明 method 的 provider backend、wire family、对 `anthropic_messages_client` 的兼容性、base_url transform 和特殊认证 env。`copilot.py` 不再硬编码 `_ark_anthropic_base_url` / `_deepseek_anthropic_base_url`；它只经 GatewayAdapter 调 `apply_call_method_base_url` / `call_method_auth_token_env`，把 gateway catalog 的结果写进 Claude SDK 的 per-session env。

**G. session 持久化边界**：copilot **对话 session 落盘 / 退出恢复**属 copilot 聊天工作台 region（D8），**不在设置页**；见 [`00_settings.md`](./00_settings.md) §5 与 mvp0 `02_features/copilot-chat/`。本页 §3 只配"用哪个模型"。

---

## 4. 三条横切机制（贯穿三页）

### 4.1 Probe Knowledge Catalog 赋能 / 写回
Probe Knowledge Catalog（探测知识库）= 按 provider 组织的 endpoint/model/route/capability 历史探测知识，双向：
- **赋能（读）**：读取 catalog，把**已证实的资料**回填给当前 model list（历史已验证的能力/元数据，不用重探）。
- **列表兜底**：`GET /models` 失败或返回空时，从 catalog 按 `provider_id + endpoint_fingerprint` 精确查候选；没有精确命中时降级到 `provider_id + protocol`。兜底生成的 route 只能是 `unverified_manual / untested`，不能直接 verified。
- **能力回填**：当前 probe/list-models 拿不到 capability 时，可从 catalog 回填 capability；每个值必须带 provenance/evidence_ref，用于 UI/role-fit/probe 参数选择，但不能单独让 route 变绿。
- **probe 优先级**：测试 endpoint 但不知道哪个 model 更可能连通时，从 catalog 的历史成功/失败/弃用数据排序，优先试近期成功、成功率高、能力匹配的模型，历史失败/弃用降权。
- **写回（写）**：本次发现的**新模型 / 新 capability / endpoint 连通 / route probe 成功失败**写回 catalog，沉淀为下次的历史知识。
- **（PM 2026-06-03，术语更新）每次探测结果——成功 + 失败——都写回探测知识库，不浪费**：失败也是历史信息（哪些模型抖动 / 超时 / 不可用），下次批量探测可优先跳过历史失败的、优先试历史成功的，抬命中率、省时间。
- **MVP1 分享边界**：本地 evidence 只写本机 Probe Knowledge Catalog；远端 catalog 在 MVP1 是只读同步来源。`/catalog/share` 只做本地脱敏导出/摘要，不自动上传到全网，也不代表已有社区写入通道。未来若要多用户贡献，必须单独设计 ingestion service、审核/限流/反滥用、聚合与发布链路。脱敏红线包括 API key、credential_ref、私有 base_url、本地路径、原始 prompt/input/output、账号/组织信息。公共 catalog evidence 只能作为建议来源，不能直接把 active route 写绿。
- **Import Draft 不属于 MVP1 主线**：MVP1 不做"待导入草稿 → apply 到 credentials"。`draft` 只作为旧文/旧代码 legacy 名称保留，不再代表本功能。

### 4.2 Model / Endpoint 标签的表现 —— route 级状态体系（PM 2026-06-02 拍板，#A 答案）
标签颜色 = 该 **route** 的状态，**三页一致**（同一 endpoint/route 从 API key 页拖到 role 页，颜色不变）。**canonical 状态枚举（6 态）= `ready` / `historical_ready`(🔵 蓝) / `untested` / `failed`(带 reason) / `cooling_down` / `off`**；下表的 `verified` = `ready` 旧称、`disable` = `off`，是现码字段 / 展示映射，不另立态：

| 颜色 / 样式 | 状态 | 含义 |
|---|---|---|
| 🟢 绿色 | **verified** | 真测试连通了（真实 probe 过） |
| 🔵 蓝色 | **以前联通过** | 历史连通过（来自 Probe Knowledge Catalog 回填），但当前未真测 verified —— 介于"没测"与"verified"之间的历史态 |
| ⚪ 灰色 | **untested** | 没测试 |
| 🔴 红色 | **failed** | 出错了要你修：① 配置缺口（缺 key/base_url/protocol/model id，原 needs_setup）② 测试失败（route 真探挂）—— `reason` 区分。**红、不挡进可用** |
| ⚪ 灰色 + 倒计时 | **熔断 / cooling_down** | 临时失败（网络/限流/超时），倒计时后重试，不当永久失败 |
| ⚪ 灰色 + 无法选 | **disable / off** | 被禁用，不可选 |

> **单模型 probe 失败的两类（PM 2026-06-03）**：① **模型已弃用 / 不再提供**（provider 明确返回"无此模型 / 已下线"）→ 归 **`disabled`（灰、不可选）**，**不是红 failed**（不是"连不上"，是"没这模型了"）；② **其他失败**（该 model + endpoint 这条 **route** 连不上 / 生成失败）→ **`failed`（红）**，且 **failed 不阻塞它进 available models**（仍列出、标红、仍可选 —— 可能换 role 配置 / 重试就好；真正永久不可用才在运行期被 admission 拦）。瞬时类（网络 / 限流 / 超时）仍走 `cooling_down`（见上表）。
>
> **`disabled`（弃用）不是死刑（PM 2026-06-03）**：弃用模型进（可折叠的）「弃用区」、灰显、hover 显**禁用图标**、**不可拖进 role**；但**点击仍可复制模型名 + 仍可对它单独 re-probe**；**re-probe 再次连通 → 从弃用区捞回 available models**（弃用可逆，模型可能又上线了）。

> **与 gateway 现状投影的关系**：`project_provider_model_state`（投影函数，`services/llm_state_projection.py`）现产 **5 态**（ready / untested / cooling_down / needs_setup / off），其中 `needs_setup` 把"配置缺口"和"真测试失败"揉成一个灰态。**本体系两处改**：① **取消 `needs_setup`**——"配置缺口"与"测试失败"统一成 `failed`（红）+ reason；② **新增「🔵 蓝=以前联通过」**。目标 6 态映射：verified=ready🟢、以前联通过=蓝🔵、untested=untested⚪、**（配置缺口 ∪ 测试失败）=failed🔴（reason 区分）**、熔断=cooling_down、disable=off。→ **gateway 投影需：取消 needs_setup、补蓝态、failed 带 reason**。

#### 状态分层（蓝态归属 + 投影逻辑，Claude 2026-06-02 核实，PM 已确认 Q2）
- **三源域（事实从哪来）**：`Identity`（存在/启用/配置硬有效）· `Capability`（支持什么 + 测过没 + **catalog 历史证据**）· `Health`（此刻能否跑/熔断）。铁律：单 status 不当统一真相。
- **🔵 蓝态归 `Capability` 域的 catalog/probe-history 子源**（历史连通），是 `ui_state` 投影层的**第 6 态**，**不是新源域**。
- **投影优先级（route 级，6 态）**：`off > failed🔴 > cooling_down > ready🟢 > 蓝🔵 > untested⚪`。`ready / 蓝 / untested` 同属"证据 tier"，按证据新鲜度排：刚测通 > 历史通（catalog）> 无证据。
- **蓝↔绿 = 测试落点（§4.3）的直接产物**：API key 页验 endpoint + catalog 回填 → 模型显 🔵 蓝；role 页对模型真 probe → 升 🟢 绿。即"endpoint 验证（蓝）→ model 保证（绿）"。
- **与其他状态轴正交**：`ui_state`（能不能用，6 态）≠ `capability_state`（了解多少能力：unknown/callable_only/partial/known）≠ `role_fit`（适不适合本角色，4 态）≠ `admission`（运行期 3 态）。
- **实现 gap**：`ProviderUiState` Literal **去掉 `needs_setup`、加 `failed`（带 reason）+ 蓝态**；`_setup_reason` 改产 `failed` + reason（`missing_config` / `endpoint_unreachable` / `model_failed`）而非 `needs_setup`；`project_route_state` 输入为 `catalog_history`（`draft_history` 仅为旧 metadata fallback），读 Probe Knowledge Catalog 中该 route 是否有历史连通证据。

#### endpoint 标签 = 单端点测试入口 + 灰态两义区分（item 1/2，PM 2026-07-02 拍板）
`Available Endpoints` 里每个 (canonical base_url, protocol) 格子的**视觉 + 交互**跟着它的状态走，而且必须把「未测但可测」与「架构性不可用」这两种灰**一眼分开**（此前实现把二者都置灰，用户无法区分「还没测」和「这把 key / 域名废了」）：

- **untested（未测但已配置）= 中性但明确可交互态。** §4.2 表里 untested 是「灰、可选」（无「无法选」限定）→ 用**亮色边框 + 亮色文字**（都是 `border-foreground` + `text-foreground`，中性色但明确是亮的、说明"可点我"；PM 2026-07-03「边框要和字体颜色一样是亮色」），底色 `bg-muted/10`——**不做成 muted 灰边框**（那看着像死格子）。它是**点击即测**的活入口：点它 → 跑**和整卡 Test 同一套** get-models 流程、只 scoped 到这一条 endpoint（复用 `runProviderGetModels({onlyEndpointId})`，**同一套 per-step toast**，不另起简版；**不是整卡全测**）。
- **可点性:除 `protocol_unsupported` 外全部状态都直接点击即测**（PM 2026-07-03）。verified（绿）/ untested / failed（红）/ not_configured 都可点复测。**唯一不可直接点的是 `protocol_unsupported`**（"disabled"）:格子本体 `cursor-not-allowed`，只能走尾部显式 Re-probe 按钮（force、绕半衰期门）;`testing`（正在测）瞬态也不可点。即 `endpointTagIsTestable` = 除 `testing` / `protocol_unsupported` 外全 true。
- **protocol_unsupported = 架构事实，格子本体不可点（`cursor-not-allowed`）。** 它是「同域名不服务此协议」的死格子（§1.2 矩阵第 9 点：tooltip 指路同域名的活协议），日常不重测（30 天半衰期门）；唯一动手入口是格子尾巴那个**显式 Re-probe 按钮**（force 复测、绕过半衰期门，§1.2 矩阵第 4 点），不是点格子本体。→ 灰 = 非用户可修的架构事实，与 untested 的「还没测」灰在**可点性**上必须分得开。
- **not_configured（缺 key / base_url）** 仍是 muted 死态（没东西可测）；**testing** 中的格子走边框流动动画、不可点（正在测）。

### 4.3 测试落点：role card 里的 model 才做真实测试
- **API key 页**：只验证 **endpoint**（轻量：连通 / get-models / 第三方加一次模型探测）。
- **role / copilot 页**：对 **role card 里的所有 model 做真实 probe**，**保证能用** —— 这才是"模型能不能用"的主战场。
- 一句话：**endpoint 验证在 API key 页，model 保证在 role 页**。

---

## 5. 与现状代码 / 其他决策的对接（cross-ref，不改 §0–§4 的需求）

> 本节是工程对接线索，帮实现时定位；**不修改上面的需求**。

- **Probe Knowledge Catalog 现状 / legacy 命名**：canonical 入口已收敛到 `graph_agent_gateway.probe_catalog` / `app.services.llm_probe_catalog` / `llm_probe_catalog.json`；底层仍复用 `ProviderImportDraft` / `llm_import_drafts.py` 作为历史存储兼容层。这是历史命名，不是 MVP1 功能名。目标正式 schema 为 `ProbeKnowledgeCatalog`：保留 append-only evidence、remote read-only sync、probe history、candidate/capability fallback；MVP1 分享端点只做 local export，不自动上传；**不保留 Import Draft（待导入草稿 → apply）主线**。
- **统一 UI state 投影**：§4.2 的标签 = gateway `project_route_state` / Studio adapter 投影，当前已产 6 态：**① 去掉 `needs_setup`（并入 `failed` + reason）② 新增「🔵 蓝=以前联通过」**（#A 已答，见 §4.2）；`catalog_history` 驱动历史蓝态，`draft_history` 仅为旧 metadata fallback。
- **capability on get-model**：anthropic 在 get-model 时返回 capability —— 对接 gateway `03-credentials-endpoints` / `05-capabilities`；**#B 由 Claude 核实**各 protocol 的 list-models 是否带 capability（见下"Claude 待核实"）。
- **protocol 自动探测**（第三方）：**#C 已答** —— 各 protocol 排列组合各测一遍、哪个连通判哪个（见 §1.2；修订 2026-07-02：落地形态 = 协议探测矩阵，逐格子观察、不选边不改写，见 §1.2 修订记录）。
- **model bundle**：对接 `materialize_model_bundle`（把 bundle 物化成兜底链的函数，`services/llm_role_materializer.py:99`）+ `ModelBundle`（数据结构）—— bundle→route list 的解析已有雏形，实现时确认与本规格一致。
- **测试落点**：§4.3「endpoint 验证 vs model 保证」的分工，需在 gateway `03`(endpoint) / `07`(probe) / `08`(test-SSOT) 模块对齐。

### 已 PM 拍板（2026-06-02 第二轮）
- **#A 已答** → §4.2：route 级 6 态体系（🔵 蓝=以前联通过 是独立第 6 态）。gateway `project_provider_model_state` 需从 5 态补到 6 态。
- **#C 已答** → §1.2：第三方 protocol 自动探测 = 各 protocol 排列组合各测一遍，哪个连通判哪个（2026-07-02 细化为协议探测矩阵，见 §1.2 修订记录）。

### 新增需求（PM 2026-06-02 第三轮）
- **#D 多 URL per provider card**（PM 原话："一张 provider card 填两个 URL ,你就当我新加的,如果太难不懂也行"）：第三方 card 填多个 base_url → 各成独立 endpoint（各自探协议 + 验证），模型合并到该 card。
  - **Claude 可行性评估**：**不难** —— 是第三方流程的自然延伸；§1.2 已要求"每 URL 自动探协议"，多 URL 即把该步循环 N 次（每 URL → 一 endpoint → 探协议 + 验证）；主要新工作在 UI（卡片多 URL 输入 + 合并展示）。
  - **重叠提示（重要）**：LLM Roles 的"model group 把相同模型跨 endpoint 合并"**本已提供多 URL 兜底** —— 加两张卡（两 endpoint），role 里自动合并成一个带两 provider 的兜底组。故"同模型多 URL 兜底"核心需求现有机制已覆盖；一张卡多 URL 的额外价值 = provider 管理便利（两镜像归一个 provider 名下）。
  - **PM 拍板：不是可选 / 低优先，直接设计实现**。全量设计见 §1.2 item 4；Claude 早前的「可选」建议作废。**3 点已确认**：①一 URL 两协议都建；②平铺建 endpoint、后端无卡概念、roles 里进 model group 的「endpoints」标签（不分组子区）；③一把 key 一个 bucket。
  - **live 验证结果（2026-06-02，用 app 配置 key 真测，key 未外泄）**：
    - **Qiniu = 两 URL 各一协议（PM #2 确认成立）**：`api.qnaigc.com/v1` 只 openai（`GET /v1/models`→200；`POST /v1/messages`→generic 400）；`anthropic.qnaigc.com` 只 anthropic（`POST /v1/messages`→anthropic-shaped 401；`POST /v1/chat/completions`→500 明确 "Use /v1/messages instead"）。**每个 URL 只能一个协议**。（观察更新 2026-07-02：`api.qnaigc.com` 现已同时通 anthropic 协议生成——生成探测 verified；且两 host 模型目录不同，`anthropic.qnaigc.com` 多 13 个 free/alpha 模型。**提供商行为会变，正是"观察会老化、按半衰期复测"的实证**，见 §1.2 修订记录。）
    - **OpenRouter = 一 URL 两协议（live 完全成立）**：`openrouter.ai/api` 同时通 `/v1/chat/completions`（Bearer→200）与 `/v1/messages`（**Bearer→200，返回真 anthropic message**；先前 401 是我 `x-api-key` 用错 header）。**走通配置 = `Authorization: Bearer`**（anthropic 兼容第三方通用）。
    - **endpoint 映射规则（确认）**：endpoint 身份 =（canonical base_url, protocol）；一张卡 →（每个 URL × 探通的协议）各成一个 endpoint，命名 `{slug}-{protocol}`（qiniu-openai / qiniu-anthropic / openrouter-openai / openrouter-anthropic）；同卡 endpoint **共享 api_key + rate_limit_bucket**，各自 canonical base_url（按协议）/ routes / capabilities。
    - **现状代码 gap**：`_stable_endpoint_id`（`llm_credentials.py:369`）是 host 白名单硬编码，openrouter 现塌成单 `openrouter-prod` 单协议 → 要改成通用 `(slug, protocol)` 派生 + 迁移现有 id。
    - **#1 答案（最终，live 复测 2026-06-03）：qiniu-anthropic 没问题，我之前是「单探瞎判」**：照 gateway 配方 + 你截图同款模型实测 —— `deepseek-v3-0324`→**200**、`deepseek-r1`→**200**（就是我上次报 401 的那个模型，同一请求现在 200）。**那次 401 是瞬时抖动**（非 key / endpoint 坏）；`minimax/glm` 间歇超时；`zzz-假模型`→`400 invalid_request`。**教训 = §1.2 批量探测的直接依据**：单模型探测不可靠，瞬时失败不可凭一个定 endpoint 生死。

### #B 已核实（Claude，2026-06-02）
get-model / list-models 是否带 capability（决定哪些 provider 可免 probe 直接拿能力）：

| Protocol | list-models 带 capability? | 仍需 probe 拿 capability? |
|---|---|---|
| **anthropic** | **是**（`capabilities` 对象 + `max_input_tokens`/`max_tokens`） | 否 |
| **google/gemini** | **是**（`inputTokenLimit`/`outputTokenLimit`/`supportedGenerationMethods`/`thinking`） | 否 |
| **openai** | **否**（仅 id/created/owned_by） | 是（doc 表或 probe） |
| **openrouter**（聚合） | **是（最全）**（`context_length`/`architecture`/`supported_parameters`/`pricing`） | 否 |
| **ark**（openai 兼容 `/api/v3`） | **否**（同 openai） | 是（doc 表或 probe） |

> **(Claude live 测 2026-06-02，用 app key 真测 list-models 首条字段)**：① 上表 anthropic / gemini / openai / openrouter 已坐实；② **第三方聚合网关可能阉割 capability**：qiniu 的 /models（openai 口 + anthropic 口）只回 `id`/`display_name`，**不透传** capability（即便底层是 anthropic）→ 「带不带 capability」**看具体网关，不只看协议**；③ 设计结论：**list-models 富字段优先 + 缺则 probe 兜底**，对应 `capability_source`（api_list vs probed_verified）+ Probe Knowledge Catalog 赋能。故 official 不一定「只 get-models」就够（openai-official / ark 仍需 probe 补 per-model 能力）。

> **⚠️ 代码缺口（接 #B，2026-06-03）**：anthropic 的 list-models 虽带 `capabilities` 富字段，但**现状代码还没消费** —— `registry/capabilities.py:137-198` 未读该块，anthropic 的 tool/thinking 仍按 `provider_doc` 硬编码注入（`services/official_capability_sources.py:208-223`）。所以"official 靠 list-models 免 probe"**目前未真正成立**，需把 anthropic capability 摄取接到新 `capabilities` 对象才行。

---

## 6. 层次分离：① 前端(ts) / ② 后端(rust) / ③a Studio 适配层 / ③b gateway 库（公共能力内核）

> PM 2026-06-03 第三轮：这两页**重度依赖 gateway**，必须把每个原子操作**精确分层 + 守好各自边界**；尤其 **③b gateway 库是领域无关的「编排 + 模型调用」库，绝不接收特定业务领域需求**。修正前版 §6 的错：把「Studio 后端 Python」与「gateway 库」混成一层「③ 后端 gateway」——本版拆为 ③a（Studio 适配）/ ③b（gateway 库）。§1–§4 写 UX，本节做四层归属 + 握手契约。
>
> ⚠️ **2026-06-03 第四轮判据校准 + 2026-06-23 术语收敛**：把"领域 vs 领域无关"精确成"**公共能力内核 vs 应用加工**"。gateway = **富能力可复用网关**（权威定义见 gateway 包 `packages/graph-agent-gateway/README.md` §2）：它对模型数据与机制的**标准化 / 组织 / 编排 / 状态总结 / 知识沉淀**，凡**不依赖「应用加工四件事」（UI / 产品策略 / 调用方式 / 存储介质）**，都是 ③b 公共能力——**含 model group 分组 / 6 态标准总结 / Probe Knowledge Catalog / materialize 编排内核**。③a 只拥有 gateway 感知不到的**应用加工四件事**：① UI 交互/展示 ② 产品策略 ③ 实际调用方式 ④ 存储介质/远端源/上传审批。判定一句话：**换个 app 还原样能用吗？能=③b，不能=③a**。`draft` 只保留为旧代码/旧原话里的 legacy 术语,不再作为 MVP1 功能名。

### 6.0 四层模型 + 领域无关铁律 + 三处握手
| 层 | 是谁（代码位置） | 管什么 |
|---|---|---|
| **① 前端 (ts)** | `apps/studio/frontend` | UI + 前端业务逻辑（拖拽 / 投影渲染 / 默认选择算法 / family 折叠 / 弃用区 / 可搜索选组 / catalog 历史态展示）。**只投影、不持第二份真相** |
| **② 后端 (rust)** | native-fs | 对 Roles/Copilot **几乎不碰数据**（凭证/角色数据永不 Rust）。只：General 选目录 / sidecar 生命周期 + IPC 桥 / copilot **聊天 session** 落盘（D8，属 skill 工作台 region，**非设置页**） |
| **③a Studio 适配层（应用加工）** | `apps/studio/backend` | **应用加工四件事**：① UI 交互/展示（拖拽编辑、family 折叠、状态颜色渲染、可搜索选组）② 产品策略（默认推荐、动态浮出 opus4.8、弃用区）③ 实际调用方式（copilot 用 Claude SDK 拿 route 自己调）④ 存储介质（凭证/知识库存哪个文件）+ HTTP `/api/llm`·`/api/copilot` 适配壳。**只做 gateway 感知不到的加工** |
| **③b gateway 库（公共能力内核）** | `packages/graph-agent-gateway` | **富能力公共内核**：凭证&端点 schema+读写+base_url 归一化+原始→标准 endpoint list / available models（分组 model_group·识别 identity·Probe Knowledge Catalog + notable）/ capability 归一化+对比+lint / 客观状态+熔断+**6 态标准总结** / 角色→fallback 链（**materialize 编排内核**）/ 两级调用（role+route）+错误分类+原生 ChatX。**凡不依赖应用加工四件事（UI / 产品策略 / 调用方式 / 存储介质）的模型数据/机制处理皆公共**（详 README §3） |

**判据铁律（本节核心，2026-06-03 第四轮反转旧表述）**：③b **不是**"不能碰 model group / 6 态 / catalog"——恰恰相反，**model group 分组 / 6 态标准总结 / Probe Knowledge Catalog / materialize 编排的能力内核都属 ③b 公共**（gateway 机制衍生的最佳方案，任何 app 可复用）。**真正绝不上浮 ③b 的是应用加工四件事**：UI 交互/展示、产品策略（推荐/浮出/弃用/family 折叠）、实际调用方式（copilot SDK + session）、存储介质绑定/远端源/上传审批。判定一句话：**换个 app 还原样能用吗？能=③b 公共，不能（绑死那四件事之一）=③a**。⚠️ 现码这些能力内核多数还**散在 ③a** `apps/studio/backend`（materialize / model_groups / 6 态 / catalog legacy draft / identity / notable / 熔断持久化）——按判据**应下沉 ③b**。

**三处握手**：
- **① ↔ ③a** = HTTP `/api/llm/*`（registry / roles / model-groups / model-bundles / endpoints / routes / test-jobs）+ `/api/copilot/*`（REST 配置 + WS 聊天流）。契约 = DTO（`ModelGroup` / `ProviderModelOption.ui_state`(6 态) / `RoleTestResponse`）。FE 只投影 DTO、不持第二份。
- **③a ↔ ③b**（进程内 Python）= ③a 把用户编辑出的**角色编排结构（候选 + 意图）**交给 ③b 的编排内核 `materialize` → fallback 链，再 `resolve_routes(role)` → `ResolvedRole`（有序 `ResolvedRoute` + skipped 诊断）。③b **看得到**"角色编排结构 + 意图"（通用概念，编排内核需要）；③b **看不到的**是"用户怎么拖拽/UI 编辑出它"（③a 应用加工）。注：materialize 编排内核按判据属 ③b，现仍在 ③a 待下沉。
- **③b ↔ provider** = 真实模型调用（graph-agent 走原生 ChatX；**copilot 例外**：库只给 route，调用交回 ③a `copilot.py` 用 `ClaudeSDKClient` 跑）。

**保留原则**：前端只投影后端 SSOT（不持第二份）；数据层走 gateway sidecar **永不 Rust**（唯一 native = General 选目录）；接口前缀 `/api/llm` + `/api/copilot`，v4 契约源 = `llm-provider-intelligence-v2` + `studio-api-keys-regression-hardening`，**不恢复 v3**。

### 6.1 API Keys 页（四层重做，与 §6.2/§6.3 一致）
> 前版"③后端gateway"三列已并入四层。**② Rust = N/A**（凭证/endpoint 数据永不 Rust）。核心分线：**协议探测 / list-models 解析 / capability 归一化 / route probe / base_url 归一化 / 错误分类 / endpoint 标准化拆分 + 生成 canonical id / 批量探测策略(短路·汇总) / Probe Knowledge Catalog 内核 / 6 态标准总结** = **③b 公共能力**；**endpoint upsert + 存储 / 批量探测的 job-进度-HTTP 包装 / 远端源选择 / 上传审批脱敏 / 6 态颜色转 DTO** = **③a 应用加工**；**多 URL 录入** = 前端。

**四层职责：**
| 层 | 内容 |
|---|---|
| **① 前端 (ts)** | UI：official 固定 5 卡（隐藏 name/base_url，只填 key）；third-party 自增卡（**多 URL 行 `+ URL`**）；Test 按钮；6 态状态标签（常驻 inline，§1.4）；Manual model probing 面板（加删 model id）；API key 输入（**type=text + CSS mask** + 显隐 + 复制 + **密码管理器抑制属性**，本地 InputGroup）；删除二次确认；骨架屏；**窄视口不溢出**。前端逻辑：输入草稿态（debounce 300ms）；**多 URL 录入**（card / 多 URL 行）→ 把原始信息交给 gateway，由 **③b 拆分 + 协议匹配 + 生成 canonical `endpoint_id`**（前端不再自己拆 / 不生成 id）；**Test 触发 + 展示进度**（批量探测策略归 ③b，前端只触发 + 显示）；**只投影 registry**（provider 卡 + 6 态 + Available Models 按 `route.endpoint_id`），**不持第二份** |
| **② 后端 (rust)** | **N/A**（凭证/endpoint 数据永不 Rust） |
| **③a Studio 适配（应用加工）** | HTTP `/api/llm/*`（见握手）；把前端录入的原始信息转交 ③b、`upsert` ③b 拆好的 endpoint 列表 + 存储；**批量探测的 job/进度/HTTP 包装**（策略归 ③b）；**Probe Knowledge Catalog 的远端源选择、存储介质、上传审批/脱敏**（知识库内核归 ③b）；**6 态颜色/文案转 DTO**（投影内核归 ③b）；endpoint test / route probe 任务编排 |
| **③b gateway 库（公共能力内核）** | **协议探测**（对 URL 打各协议推理端点 + 对应 auth header：native anthropic=`x-api-key`、anthropic 兼容第三方=`Authorization: Bearer`）；**list-models 解析 per protocol**（OpenAI `data[].id` / Gemini `models[].name` 去 `models/` / 去重保序）；**capability 从 list-models 富字段归一化**（anthropic/gemini/openrouter 带；openai/阉割网关缺则 probe 兜底）；**base_url 按 protocol 保存时归一化**；route probe（1-token 真请求）；错误分类（结构错 404/500/400-invalid ↔ 瞬时 401/429/timeout）；**endpoint 标准化拆分 + 生成 canonical id；批量探测策略（短路·汇总）；Probe Knowledge Catalog 内核（记录/复用/共享证据、provider 分区、probe priority）；6 态标准总结**。不碰应用加工四件事，不知 card 录入交互 |

**三处握手（API 契约）：**
- **① ↔ ③a**：`GET /api/llm/registry`（RegistrySnapshot，api_key **redacted**）· `GET …/endpoints/{id}/secret`（单条明文，scoped reveal）· `PUT …/registry/endpoints`（upsert ③b 拆好的 endpoint 列表）· `POST …/endpoints/{id}/test`（批量模型探测）· `POST …/routes/{id}/probe[?force=true]`（单 route 真探 / Manual / Test Now）。DTO：endpoint/route + 6 态 `ui_state`，api_key 一律 redact。
- **③a ↔ ③b**（进程内）：③a 调库做 endpoint 拆分 / 协议探测 / list-models 解析 / capability 归一化 / route probe / base_url 归一化 / 批量探测策略 / Probe Knowledge Catalog 读写 / 6 态总结；**③b 返回标准结果（标准 endpoint list、批量探测结果、catalog/state 投影结果）**，③a 只包装 job/HTTP + 落存储。
- **③b ↔ provider**：协议探测 + route probe 的真实 HTTP（打推理端点）。

**逐操作归属（A1–A12，② Rust 全 N/A）：**
| # 动作 | ① FE-ts | ③a Studio 适配 | ③b gateway 库 |
|---|---|---|---|
| A1 进 tab 加载 | 渲染 official 5 卡 + 第三方卡 + 6 态 | `GET registry`（redacted） | — |
| A2 official 填 key + Test | 填 key、点 Test | get-models job 包装 + 转 DTO + catalog 存储/远端源 | list-models 解析 + capability 归一化 + **catalog 写语义** + 6 态总结 |
| A3 第三方填 URL + 协议自动探测 | 填 URL、点 Test | 编排探测 + 判定可达 | **协议探测**（打推理端点 + auth header） |
| A4 多 URL × 协议 → 拆 endpoint | 多 URL 录入、触发 | `PUT endpoints` upsert + 存储 | **拆分 + 协议匹配 + 测试 + 生成 canonical endpoint_id** |
| A5 endpoint Test = 批量模型探测 | 触发 + 显示 inline | job/进度/HTTP 包装 + 写 catalog | **批量探测策略（批批打/命中停/结构错短路/瞬时不短路）+ route probe + 错误分类 + 汇总** |
| A6 单模型 Manual probe | 加删 model id、触发 | job 包装 + 写 catalog | route probe + **catalog 写语义** |
| A7 capability 回填 | 显示能力 | 投影 | **list-models 富字段归一化** + 缺则 probe |
| A8 Probe Knowledge Catalog 赋能/写回 | 蓝标签渲染 | 调 ③b 读写 + 远端源 + 上传审批/脱敏 | **catalog 读写语义 + probe 结果合并 + provider 分区 + probe priority** |
| A9 6 态标签 | 渲染色 | 6 态结果转 DTO | **6 态标准总结（含读 catalog 出蓝）+ RouteStatus + 熔断** |
| A10 secret reveal | Eye/Copy 等显式用户动作才换单条真值；进 tab 只投影 redacted registry | `GET endpoints/{id}/secret`（scoped、单条明文） | — |
| A11 删 endpoint | 二次确认 | `PUT endpoints`（整表 upsert） | — |
| A12 save-status badge | 统一 badge ← saveStatus | save 端点返回状态 | — |

> **守边界检查**：③b 列是公共能力内核（协议探测/list 解析/capability 归一化/route probe/错误分类/base_url 归一化/**endpoint 拆分 + canonical id / 批量探测策略 / Probe Knowledge Catalog / 6 态总结**）；③a 列是应用加工（upsert + 存储 / job-进度-HTTP / 远端源 + 上传审批 / 颜色转 DTO）；① 只录入 + 渲染。⚠️ 原"前端拆分 / 前端生成 id / `_stable_endpoint_id` 退役"已反转——endpoint 标准化拆分 + canonical id 归 ③b。

### 6.2 LLM Roles 页
> **② 后端 (rust) = N/A**（角色/凭证数据永不 Rust，本页 Rust 不参与）。

**四层职责：**
| 层 | 内容 |
|---|---|
| **① 前端 (ts)** | UI + 前端业务逻辑：角色卡 + Available Models 侧栏（model group 卡、**family 可折叠**〔#1〕、**弃用区**可折叠、6 态色含 🔵 蓝、endpoint 平铺在「endpoints」标签）；拖 model group + **默认 provider 选择算法**（Ready+Untested+🔵 优先、排除 failed/off、cooling 有替代不默认选）；provider 链拖序/加删；intent 控件（PR3 简化：thinking **单 Switch**、max output token **纯数字**、temperature 数字；去 context/mode/downgrade；**布局轻优化**〔#4〕）；节点 Properties 面板同三参数直接覆盖；Test 触发 + role-fit 状态灯 + **单一顶层 tooltip**（fail/downgrade 进 tooltip、**不要 RoleTestResultPanel**、清嵌套 tooltip〔#5〕）；Model Bundle 区（**Add 与 Add Role 同位**〔#6〕、复用 role 编辑/测试/改名删除、**拖进角色=引用**〔#7/#8/#9/#12〕）；family/弃用区折叠（localStorage 视图态）；**只投影、不持第二份**（删 `roleTestStates`） |
| **③a Studio 适配（应用加工）** | `GET /api/llm/registry`（model_groups DTO + 6 态 `ui_state`）· `GET /api/llm/model-groups` · `GET/PUT/DELETE /api/llm/roles[/{name}]` · `POST /api/llm/roles/{name}/test(-jobs)` · `GET/PUT/DELETE /api/llm/model-bundles[/{id}]`+`/test`。**应用加工**：拖拽编辑角色/绑定的 UI；**default 选择/推荐策略**（产品策略）；6 态颜色转 DTO；materialize 报告 + role 测试结果的渲染；Probe Knowledge Catalog 的远端源配置 / 存储介质 / 上传审批与脱敏。（model_group 分组 / materialize 编排 / 6 态总结 / Probe Knowledge Catalog 的**内核归 ③b**，见右列）|
| **③b gateway 库（公共能力内核）** | **model group 分组 / identity 识别**；**materialize 编排内核**（按意图过滤路线 + 降级 + 排 fallback 链 + role-fit/downgrade 诊断）；`resolve_routes(role)`→`ResolvedRole`；capability 归一化 + 对比 + `build_runtime_setting_descriptors`（驱动 ① intent 控件）；`lint_role_routes`（只 warn/block 不选型）；route probe；ChatX 调用；熔断 + 错误分类 + **6 态标准总结**（供 ③a 转 DTO）。③b 看到"角色编排结构 + 意图"（通用），看不到"用户怎么拖拽编辑出它" |

**逐操作归属（R1–R25，② Rust 全 N/A）：**
| # 动作 | ① FE-ts | ③a Studio 适配 | ③b gateway 库 |
|---|---|---|---|
| R1 进 tab 加载 | 渲染角色卡+侧栏 | `GET registry`(model_groups) | — |
| R2 可用模型过滤 | 过滤渲染(family/弃用/6态) | 调 ③b + 转 DTO | **model group 分组 + 6 态总结(读 catalog) + route modality capability** |
| R3 搜模型 | 纯前端 | — | — |
| R4 看 6 态 | 渲染色 | 6 态结果转 DTO | **6 态标准总结 + RouteStatus + 熔断** |
| R5 弃用区 | 渲染/复制名/re-probe 触发 | disabled 分类 + 投影 | route probe(re-probe) |
| R6 新建 role | 弹框 | `PUT roles` | — |
| R7 拖组+默认选 | 拖拽 + 默认算法 | 接收存 model_groups | — |
| R8–R10 调序/增删/删组 | reorder/增删 | `PUT roles` | — |
| R11 fallback 开关 | 开关 | 传 fallback 开关给 ③b | **materialize 尊重 fallback 开关** |
| R12 thinking 开关（PR3 简化） | 单一 Switch（on/off） | role_intent.thinking:bool → route reasoning.enabled | thinking capability（不支持则 Test 警告不阻塞） |
| R13 max output token（PR3 简化） | 纯数字输入（无 mode）+ temperature 数字 | role_intent.max_output_tokens clamp 到 route min/max；temperature 落 route | max_output capability（算 placeholder 推断上限） |
| R14 route max 摘要 | 显示 | role_effective_runtime_settings 投影 | `_effective_runtime_settings` |
| R15 role-fit 灯 | 显示 | 渲染 fit 灯(读 ③b report) | **materialize 算 role_fit + capability + lint** |
| R16 role Test 批量 | 触发 + 轮询喂灯 | `POST roles/{}/test-jobs` job 包装 + 落存储 | `resolve_routes` + 批量 route probe + **catalog 写语义** |
| R17 Test 失败条 | 显示(未保存先拒) | 同 R16 | — |
| R18 fail/downgrade | 单顶层 tooltip(无 panel) | 渲染 downgrade tooltip(读 ③b report) | **materialize 产 downgrade 诊断** |
| R19 role 改名删 | 菜单 | `PUT/DELETE roles` | — |
| R20–R21 Add/编辑 bundle | 同 role(同位/复用编辑器) | `PUT model-bundles` | — |
| R22 束 Test | 复用 role test | `POST bundles/{}/test` 编排 | resolve(临时) + probe |
| R23 束拖进角色=引用 | 引用(非快照) | 传 bundle 引用给 ③b | **materialize 按引用展开 bundle** |
| R24 束改名删 | 同 role | `PUT/DELETE bundles` | — |
| R25 被动刷新 | 重投影 | WS `roles_changed` | — |

> **守边界检查（按 §6.0 第四轮判据校准）**：③b 列是公共能力内核（resolve/capability/lint/probe/ChatX）；**model group 分组 / materialize 编排 / 6 态标准总结 / Probe Knowledge Catalog 内核也属 ③b 公共**（现散 ③a 待下沉）。③a 真正独占的是**应用加工**：拖拽编辑交互、默认选择/推荐策略、状态颜色渲染、远端源配置/上传审批/脱敏。

### 6.3 Copilot 页
> **② 后端 (rust)**：copilot **配置**(本页)= N/A；但 copilot **聊天 session 落盘**(D8)= Rust native-fs（skill 工作台 region，非本页）。
> **关键边界**：copilot 的 **SDK 调用 / 测试 / session 都属 ③a Studio 领域**（`copilot.py` 用 `ClaudeSDKClient`）；③b gateway 库**只做 route 解析 + 通用 call method/capability 真相**，不碰 SDK 调用、不知 copilot 语义。gateway 只知道“这个 method 是否能被一个 Anthropic Messages client 驱动”，不知道“Copilot 页面要怎么显示”。

**四层职责：**
| 层 | 内容 |
|---|---|
| **① 前端 (ts)** | copilot 角色卡(**单 model group**)；**可搜索选组器**〔#1〕；Test 触发；route 排序/加删；新建第三方角色(`copilot_` 前缀)；**「Backend Integration」slot 换统一 save-status badge**〔#4〕(四页共用、idle 静默)；**去 mock**；**内置动态浮出**〔#2〕(Claude opus4.8→4.7、DeepSeek V4Pro→V3.2Pro)；**eligible 不预过滤未测 route**〔#3〕；**只消费 `copilot_sdk_compatible`**，不维护 method/protocol 名单；**copilot_ 前缀必修**(选组后保前缀)；UI 尽量复用 role |
| **③a Studio 适配（应用加工）** | 复用 roles 端点(`role_kind=copilot`，`_is_copilot_role` 认 `copilot_` 前缀) + `POST /api/copilot/roles/{name}/test-sdk` + WS 聊天流。**领域逻辑**：**copilot SDK 调用**(`copilot.py` `ClaudeSDKClient`、base_url→env)；**真 SDK 测试**(修假测试 `AsyncAnthropic`→`ClaudeSDKClient`)；走**全 fallback 链**；把 ③b call-method compatibility 投影为 `provider_models[].copilot_sdk_compatible`；内置动态浮出策略；session 持久化(D8)+失败显式告警；测试证据回写 Probe Knowledge Catalog |
| **③b gateway 库（公共能力内核）** | **仅** `resolve_routes("copilot_chat")`→`ResolvedRoute[]`(③a 拿去自己用 SDK 调；**库不调 SDK、不知 copilot 是什么**)；`call_methods.json` 声明 method 的 wire family、client compatibility、official probe backend、base_url transform 和特殊 env |

**逐操作归属（C1–C12，② Rust 全 N/A；session 除外属 chat region）：**
| # 动作 | ① FE-ts | ③a Studio 适配 | ③b gateway 库 |
|---|---|---|---|
| C1 进 tab | 渲染卡 + save-status badge | `GET registry` | — |
| C2 角色卡动态渲染 | 渲染 | 从真 model_groups 投影 copilot 角色 | — |
| C3 种子卡(去 mock) | 无 mock | 同 C2 | — |
| C4 route SDK 状态灯 | 显示 | 来自真 SDK 测试结果(③a 存) | — |
| C5 Test 真 SDK | 触发 | **`ClaudeSDKClient` 真跑** + 写证据/catalog | **仅** `resolve_routes` 给 route |
| C6 route 兜底序 | 拖序 | `PUT roles` + 走全链 | `resolve_routes` 返回有序 |
| C7 Add/删 route(eligible) | 增删 | 读 `copilot_sdk_compatible`，由后端调 ③b call-method catalog 投影 | call method client compatibility |
| C8 model-group remove | 接 handler | `PUT roles` | — |
| C9 Add custom 角色 | 弹框(`copilot_custom_N`) | `PUT roles` | — |
| C10 选 group(可搜索) | 可搜索选组 + **保 copilot_ 前缀** | `PUT roles`(`_is_copilot_role` 认前缀) | — |
| C11 删第三方角色 | 确认 | `PUT roles` 整表 | — |
| C12 save-status badge | 统一 badge ← saveStatus | save 端点返回状态 | — |

> **守边界检查**：copilot 的 SDK 调用/测试/session 全在 ③a；③b **只** resolve_routes + capability。**库完全不知道 copilot 是什么**——它只解析一个叫 `copilot_chat` 的 role 的 route,谁拿去怎么用与它无关。✓

### 6.4 横切机制的四层归属
> ② Rust 对这些机制全 N/A。**核心（第四轮校准）：应用加工（UI/产品策略/调用/存储）归 ③a，公共能力内核归 ③b。**

| 机制 | ① 前端 (ts) | ③a Studio 适配（应用加工） | ③b gateway 库（公共能力内核） |
|---|---|---|---|
| **Probe Knowledge Catalog 赋能/写回** | 蓝标签 + "以前联通过"提示(渲染) | 存储介质/远端源选择/上传审批与脱敏(应用加工) | **Probe Knowledge Catalog 内核(记录/复用/共享探测证据、provider 分区、probe priority)属 ③b 公共**(现码 legacy `llm_import_drafts.py` 在 ③a 待下沉并改名)；产出 probe 结果写入知识库 |
| **6 态投影** | 渲染状态色(绿/蓝/灰/红/熔断/关) | 状态颜色/文案的呈现选择(应用加工) | **6 态标准总结(ready🟢/蓝🔵/untested⚪/failed🔴/cooling/off,failed 带 reason)属 ③b 公共**(现 `project_provider_model_state` 在 ③a 待下沉,需取消 needs_setup)；产出 RouteStatus + 熔断 |
| **测试落点** | Test / Test Now 按钮(触发) | endpoint test / role test 编排 + 回写 SSOT | route probe(1-token 真请求) + 熔断写 health store |
| **多 URL / 协议探测** | 多 URL 行(录入) | endpoint upsert + 存储、批量探测的 job/进度/HTTP 包装 | **endpoint 拆分 + 生成 canonical id + 协议探测 + base_url 归一化 + 批量探测策略 + 错误分类** |
| **save-status badge** | 四页共用统一 badge(idle 静默) | save 端点返回状态 | — |

### 6.5 两处守边界检查（实现 / code review 必过的两条架构不变量）
四层之间有**两条内部边界**必须守住——它们是这套握手的不变量，散落在 §6.1–§6.4 的 ✓ 注在此收拢成两条正式检查，逐条验：

**检查 1 @ ③a ↔ ③b 边界：③b = 公共能力内核，不含应用加工（2026-06-03 第四轮反转旧不变量）**
- **不变量**：③b **不是**"不能含 model group / 6 态 / catalog"——它们的**能力内核（分组 / 状态标准总结 / Probe Knowledge Catalog / materialize 编排）恰属 ③b 公共**。③b **绝不出现的是应用加工四件事**：UI 交互/展示（颜色、布局、折叠、渲染）、产品策略（默认推荐、浮出 opus4.8、弃用区、family 折叠）、实际调用方式（`ClaudeSDKClient` / copilot session）、存储介质绑定（硬编码文件路径 / 远端源 / 上传审批）。
- **怎么查**：① grep ③b 公共 API 有无**应用加工**痕迹——渲染/颜色/布局、"默认推荐"策略、`ClaudeSDKClient`、硬编码存储路径；② 对每个 ③b 能力问"**换个 app 还原样能用吗**"——不能（绑死 UI/产品策略/调用方式/存储）= 错放 ③b。
- **违反信号**：③b 里冒出渲染/颜色/默认推荐策略/copilot SDK 调用/硬编码存储位置。
- **现状**：⚠️ **能力内核待归位**——materialize / model_groups / 6 态 / Probe Knowledge Catalog(现码 legacy draft) / identity / notable / 熔断持久化的内核现仍散在 ③a `apps/studio/backend`，按判据**应下沉 ③b**；copilot SDK 调用、HTTP 壳、UI 渲染、产品策略**正确留 ③a**。下沉清单见 `docs/graph-agent-gateway/mvp1/module-disposition-revised.md`。

**检查 2 @ ① ↔ ③a 边界：前端只投影、不持第二份真相**
- **不变量**：前端（①）的"测试态 / 状态 / 模型清单"**只能从后端 registry 投影**，**不得**在前端组件态 / store 里另存一份真值（切 tab / 刷新就丢的并行态）。
- **怎么查**：① grep 前端有无本地"测试结果 / 状态"的 source-of-truth（而非 `GET registry` 投影）；② 切 tab / 刷新后状态是否仍在（在 = 从后端读 = 对；丢 = 前端自持 = 错）。
- **违反信号**：前端组件态里有 `roleTestStates` / `routeStatusOverrides` / mock 种子数据当真值。
- **现状**：✗ **未守住** —— 仍残留 `roleTestStates`（Roles 易失测试态）、`routeStatusOverrides`、`mock-copilot-data`（copilot mock 种子）→ **本次接线工程要删，改为纯投影后端 SSOT**（切 tab / 刷新不丢）。这是本设计交付的主接线工作之一（对应检查 2 从 ✗ 转 ✓）。

---

> **scope 边界一句话**：本次设计交付 = **① 前端 (ts) + ③a Studio 适配层**（含"不持第二份、只投影"接线改造）；**③b gateway 库** = 写给它的**领域无关能力需求 + 握手契约**（标「新增能力」待补，但**绝不接收领域需求**）；**② Rust** 对这两页近乎不参与。

---

## 7. atom action 全清单（现状审计 × 能力·区域映射）

> **用途**：§1–§4 是**目标设计叙事**（按三页深入）；本节是**按 UX 心智顺序的最细 atom action 现状审计**——每个动作映射到 能力(细 slug) / 区域 / 现状 status / file:line 证据，是 §1–§6 设计的**原料与依据**。两块只在本节、§1–§3 叙事未覆盖：**Stage 0 壳层** + **Stage 1 General**。
> **现状 vs 目标(铁律)**：status 列描述**当前代码行为**(✅=现接线可用)，**不等于目标设计**。凡现状与 §1–§4 冲突，以叙事为准。**最关键的一处 drift**：Stage 2 的 official(#24 异步批量 job)/third-party(#25 同步单次)**测试机制不对称是 current-code drift,不是设计**——目标是**统一 `POST /endpoints/{id}/test` + 批量探测**(§1.2)；官/三在目标设计里的真区别只剩**身份与 canonical 默认**(§1.1 vs §1.2),测试路径同一套。
> **状态图例**：✅ live(接线可用) · 🟡 placeholder(桩/占位) · 🔌 orphan(组件已建·未挂载) · 🛠 backend-only(后端有·前端无 UI) · 🎯 target-design(仅设计) · ⚠️ 冲突/问题(stale-code / 契约违反 / 潜伏 bug)
> **UX 主流程一句话**：工作区点 Toolbar Settings → 面板盖画布(左文件树/右 Copilot 仍在,工作区不卸载)→ General 配「我是谁/产物发哪」→ API Keys 配 provider 凭证 → LLM Roles 把角色映射到模型兜底链 → Copilot 配助手 → 一切即填即存 → 点 X 关闭回工作区。

### 7.0 Stage 0 — 进入 Settings（壳层）〔区域 `settings:shell`，叙事未覆盖，仅此〕

| # | 动作 | 能力 | 现状 |
|---|---|---|---|
| 1 | 点 Toolbar Settings 图标 → 打开面板(center overlay 盖画布,**不卸载工作区**) | open-settings-overlay | ✅ 非真 modal,左右栏仍挂载可交互,无 backdrop/focus-trap |
| 2 | 数据未到显示骨架屏(available models 巨长列表是 NFR 首要) | settings-skeleton | ✅ 壳层按 tab 就绪门控骨架:General=GeneralTabSkeleton、Roles/Copilot=RolesTabSkeleton(shell 级),API Keys=ProviderListSkeleton(tab 内),均 shadcn Skeleton;General 不再 disable 整表单 |
| 3 | 四 tab(General/API Keys/Roles/Copilot)间切换(切到才懒加载) | settings-tab-switch | ✅ |
| 4 | 改动后看右上保存徽章(Pending/Saving/Saved/Failed) | settings-save-badge | ✅ ⚠️ 三 tab 各画各的,顶栏无全局保存态 |
| 5 | 外部改 credentials → WS `registry_changed` 自动刷新 | ws-registry-refresh | ✅ ⚠️ 空 catch 静默,无重连(违 logging 铁律) |
| 6 | 外部改 roles → WS `roles_changed` 自动刷新 | ws-roles-refresh | ✅ ⚠️ 没开过 Roles tab 则事件被吞 |
| 7 | 点 X 关闭回工作区画布 | close-settings-overlay | ✅ 无未保存确认,in-flight PUT 仍落地 |
| 8 | (Settings 打开时)点 Header Home → 连带关 Settings + 退首页 | home-closes-settings | ✅ 与 X 两条语义(Home 还卸载工作区) |
| 9 | 某 tab 渲染崩溃 → 错误兜底卡 + Retry(不白屏) | settings-error-boundary | ✅ ⚠️ 只包 Roles/Copilot,General/API Keys 没包 |
| 10 | **后端不可达时禁止写操作(就绪门)** | settings-backend-readiness-gate | ✅(PM 2026-07-03)后端**实时可达** = API 配置就绪(`apiReady`)**且** `/ws/events` 连着(`!connectionLost`)。凡是会写后端的动作(删 provider / 删 URL / Test 取模型 / 单格 Re-probe / 新增 provider)在发请求**前先过这道门**:不可达则**拒绝执行 + 明确提示「后端正在重连,请稍候再试」**(不再让请求打进空气、拿不到响应弹裸 "Backend unavailable",也不再乐观删除后又回滚);同时按钮**禁用**(如 Add Provider `disabled`)。app 外壳仍立即渲染、不整屏隐藏(尊重「壳层立即挂载」),门控只作用在**会写后端的交互**上。 |

> Stage 0 行为 PM 已拍板(批次 settings-shell):窗口小自动收侧栏;再点 toolbar Settings 图标=关 settings;网络拉不到显示「连接不上」警告标志(否则不必让用户感知);**写操作在后端不可达时禁用 + 提示重连(#10 就绪门,PM 2026-07-03),而不是让动作打进空气再弹裸报错**。详见 [01_init §4](./01_init.md)(Settings overlay 不卸载工作区的流转)。

### 7.1 Stage 1 — General（身份与产物路径）〔区域 `settings:general`,叙事未覆盖,仅此〕

| # | 动作 | 能力 | 现状 |
|---|---|---|---|
| 10 | 改 Studio User ID | studio-user-id | ✅ |
| 11 | 填 Gitea Host(**publish 硬依赖**,缺则 sync 报错) | gitea-host | ✅ |
| 12 | 手填默认 skills 目录路径 | skills-dir-manual | ✅ |
| 13 | Choose 弹 OS 文件夹选择器(**settings 唯一走 native/Rust 的本地操作**) | skills-dir-native-picker | ✅ web 模式仅 toast "Desktop only" |
| 14 | Reset 还原默认目录(回 runtime 默认 `configDir/Skills`) | skills-dir-reset | ✅ runtime config 不可用时 disabled |
| 15 | 任意字段即填即存(300ms debounce `PUT /api/settings`)+ 徽章 | appsettings-save | ✅ |
| 15.1 | 切界面语言(English / 简体中文 下拉, `i18n.changeLanguage`) | settings-language | ⚠️ 新增原子(2026-06-18 PM:语言**算 Settings**、之前漏写)。现仅切界面、**不持久化**;目标=和其它字段一样存进 `app_settings`(重开恢复上次语言),走同一条 `PUT /api/settings` + 即填即存 |
| 15.2 | 展开 Runtime truth source files → 每个运行时真相文件一张卡(路径 + Open + 存在性/大小/更新时间)+ 每卡 Runtime log 折叠列表 | runtime-truth-sources | ✅ 补写设计(2026-07-01 PM:此前设计漏写此区) |

> **Runtime log 设计原则(PM 拍板 2026-07-01)**:runtime activity log(`logs/studio_runtime_activity.jsonl`,append-only,按 `source_id` 归到各真相文件卡)是**审计明细账,不是一句话流水**。每条 entry = `recorded_at / action / message / changes`,其中 **`changes` 必须承载与真相 json 文件一致的事实明细**——用户在 Runtime log 里展开 Details 看到的内容,要与打开对应 json 文件看到的关键事实一致,不许只记 "analyst / failed" 这类概要:`endpoint_test` 带 status/message/discovered_model_ids/**probe_attempts**(每次生成探测的 protocol×model×status);`role_test_result_saved` 带**逐路由 `route_results`**(canonical_id / route_id / provider / status / **message 失败原文**)。前端 GeneralTab 的 RuntimeLogItem 通用渲染 `changes` 全部字段(数组逐行、对象 JSON 行),不挑字段白名单——写入侧记全,展示侧全展。

> **机制**：三字段整体 PUT(无字段级 PATCH),`GET/PUT /api/settings`→`app_settings.json`。Gitea host 只是 publish 鉴权链的一半(token/凭据走另一套 credentials,且为 env-only `STUDIO_*`,见 [00_settings §git](./00_settings.md))。选目录是 settings 里唯一的 Rust 本地操作。**写入归属铁律**:credentials/roles/settings 走 gateway Python(`~/.studio/` + `routers/llm.py`),**settings 不适用 D12「写全量 Rust」**(那是 skill 源文件)——唯一 native 操作就是这条选目录。

### 7.2 Stage 2 — API Keys（Provider 凭证）〔区域 `settings:api-keys`;轨 官/三/共〕
> 设计叙事见 §1。下表 = 现状 atom 审计。**注意上方 drift 铁律**:#24/#25/#27 的官/三测试不对称是现状,非目标。

| # | 动作 | 轨 | 能力 | 现状 |
|---|---|---|---|---|
| 16 | 进 tab → 只加载 redacted registry 凭证；Eye/Copy 显式动作才 scoped GET 单条 secret | 共 | secret-reveal | ✅ |
| 17 | 渲染拆 official 区(固定 5 厂商预渲染)+ third-party 区(用户自增) | 共 | provider-partition | ✅ |
| 18 | official 只填 Key;Base URL/Protocol canonical 默认+隐藏,不可增删改名 | 官 | official-key-only | ✅ |
| 19 | `+ Add Provider` → 弹框填名 → 建 `custom-{uuid}` 草稿 | 三 | tp-add-provider | ✅ ⚠️ 现两步,目标 inline 一次填全(§1.2) |
| 20 | 填 name / base_url / protocol / api_key | 三 | tp-credential-edit | ✅ |
| 21 | 改 API Key(两类共用;改后旧测试失效→badge 回 untested) | 共 | credential-key-edit | ✅ |
| 22 | Eye/EyeOff 切明文/掩码（redacted 时先 scoped reveal 单条 secret） | 共 | secret-mask-toggle | ✅ |
| 23 | Copy 复制 key 到剪贴板 | 共 | secret-copy | ✅ |
| 24 | `Test` → 异步批量 job(750ms 轮询)拉全厂商模型目录,endpoint 提 verified | 官 | official-test-job | ✅ ⚠️**DRIFT**:后端硬门禁 `provider_kind!='official'` 拒;目标=统一 `POST /endpoints/{id}/test`+批量探测(§1.2) |
| 25 | `Get Models` → 同步单次 models-list 发现;路由停 unverified_manual | 三 | tp-getmodels | ✅ ⚠️ DRIFT(同上) |
| 26 | 'Endpoint test' 填单 model id → Test 探测该 model | 三 | tp-model-probe | ✅ |
| 27 | 'Manual model probing' 加多 model id 批量探测(后端按 kind 分叉) | 共 | manual-model-probe | ✅ ⚠️ 官→多候选 VerifiedProfile / 三→单次 `_probe_model` 写死 text-only(目标:统一批量探测+能力探测)；探测证据写本地 Probe Knowledge Catalog，MVP1 不自动上传 |
| 28 | (自动)Manual panel 拉 `notable-models` 候选作输入建议 | 共 | notable-models | ✅ 有 note 文件即返,不分官/三 |
| 29 | `⋮` → Rename / Delete(official 不可改名/删) | 三 | tp-rename-delete | ✅ 删除二次确认 toast |
| 30 | 状态投影:tp 顶层徽章(参数指纹) / official 每 route 彩色 Tag(后端权威) | 共 | test-status-projection | ✅ → 目标 6 态(§4.2) |
| 31 | 刷新后从 registry 恢复 key/状态/Available Models | 共 | registry-restore | ✅ |

> **官/三 目标区别(去掉 drift 后)**：official 不是用户选的,后端按 `endpoint_id` 白名单(anthropic/openai/gemini/deepseek/ark-official/ark-openai-official)钉死 `provider_kind`,前端镜像成固定 5 厂商 + canonical base_url/protocol 默认且隐藏;Ark official 同一 host 有两颗协议身份：`ark-official`=`ark_runtime`, `ark-openai-official`=`openai_compatible`,不能只按 host 合并。third-party 用户自填 name/url/protocol/key。**测试路径同一套**(统一 endpoint test + 批量探测)。多 URL/协议探测/命名见 §1.2。
> **🔌 孤儿/🛠 backend-only**：`OfficialVendorSelect`、`AddProviderForm` createBlank/derive、`ProviderDeleteButton`(定义未渲染)、`probeRoute`→`POST /routes/{id}/probe`(此 tab 未接线)。处置(接线 vs 清死代码)逐组判定。

### 7.3 Stage 3 — LLM Roles（角色 → 模型兜底链）〔区域 `settings:llm-roles`〕
> 设计叙事见 §2。

| # | 动作 | 能力 | 现状 |
|---|---|---|---|
| 32 | 进 tab → 加载 Graph Agent 角色卡(滤掉 copilot_)+ 右侧 Available Models 侧栏 | role-list-load | ✅ |
| 33 | `Add Graph Agent Role` → 弹框命名 → 新建空角色 | role-create | ✅ 允许建无模型空壳角色 |
| 34 | 侧栏搜模型(按 model/provider/id 多词匹配) | available-models-search | ✅ |
| 35 | 展开模型卡看各 provider 状态(Ready/Untested/Cooling Down) | available-model-provider-states | ✅ ⚠️ needs_setup/off 的 provider 被静默过滤,看不到为何缺失 |
| 36 | 拖模型进角色 → 自动挂 model group + 默认选 Ready+Untested 在前 | role-model-map-drag | ✅ |
| 37 | 拖动调多个 model 兜底序 | role-model-reorder | ✅ active_model 永远同步第一个 |
| 38 | 拖 provider tag 调该模型的 provider 兜底序 | role-provider-reorder | ✅ |
| 39 | `Add provider` 补加 / 垃圾桶移除某 provider | role-provider-add/remove | ✅ |
| 40 | 删整个 model group | role-model-remove | ✅ |
| 41 | 切 `Model Fallback` 开关(关则只用第一个 model) | role-model-fallback-toggle | ✅ |
| 42 | 开/关 `Thinking` 开关(PR3 简化,不再三档) | role-thinking-intent | thinking:bool;开关开+模型不支持→Test 警告不阻塞 |
| 43 | 填 `Max output tokens` 纯数字 + `Temperature`(PR3 简化,无 mode/无 context/无 downgrade) | role-output-token-intent | max_output_tokens clamp 到 route min/max;temperature 落 route |
| 44 | 看 `Route max token` 摘要 | role-output-limit-summary | ✅ |
| 45 | 悬停状态灯看 role-match(Can Run/Limited/Blocked)+ 诊断 | role-route-status-light | ✅ role_fit 来自后端 materialize report |
| 46 | 点 `Test` → 后端 job 逐 route 探测兜底链,实时回填灯 + downgrades | role-test | ✅ ⚠️ 结果易失(切 tab 丢);`RoleTestResultPanel` 已写未挂载 |
| 47 | Test 失败红色错误条(未保存先拒测) | role-test-error-banner | ✅ |
| 48 | `⋮` → Rename / Delete 角色 | role-rename/delete | ✅ |
| 49 | `Add Model Bundle`(可复用模型束,跨角色) | model-bundle-create | ✅ |
| 50 | 拖模型进束 / 束内编辑(复用角色卡编辑器,束不可嵌套束) | model-bundle-edit | ✅ ⚠️ 束卡不显状态灯、无 Test 按钮 |
| 51 | 把已建束整体拖进角色作一组兜底 | bundle-as-role-source | ✅ ⚠️ 快照复制,束后续改动不同步到已拖入的角色 |
| 52 | 束 `⋮` → Edit 改名 / Delete 删束 | model-bundle-rename-delete | ✅ |
| 53 | (被动)其它窗口改 roles / 窗口聚焦 → 自动重投影刷新 | role-projection-refresh | ✅ |

> **机制**：角色存**结构化** `model_groups[]`(canonical_id + 各 provider 的 route),后端 `materialize_role` 物化成 gateway 消费的**平铺** `fallback_chain`;前端看 Group,引擎跑链。物化时跳过 needs_setup/off、cooling_down 记 warning、只把 fit 的 route 入链——UI 测试态与引擎编排同一套判断。
> **测试 SSOT 落差(头号)**：role 测试结果后端 job 内存字典(`_role_test_jobs`)是 SSOT,但前端 `roleTestStates` 是组件易失 state,**切 tab 即丢**;只有静态 `role_fit` 持久。**本次接线工程要删前端易失层、纯投影后端 SSOT**(对应 §6.5 检查 2)。
> **🔌 孤儿/🛠 backend-only**：`useRoleTestChainRunner`、`RoleTestResultPanel`、`RoleFitBadge`、`ProviderStateBadge`、`CoolingDownCountdown` 仅测试引用未挂载;`PUT /llm/roles/{name}`(单角色带 materialize)前端不调(只用 bulk PUT)。

### 7.4 Stage 4 — Copilot（助手配置）〔区域 `settings:copilot`〕
> 设计叙事见 §3。⚠️ 现状定性:**配置外壳真接线,内里大量 mock/桩/假测试**。

| # | 动作 | 能力 | 现状 |
|---|---|---|---|
| 54 | 进 tab → 标题 + "Backend Integration" 徽章 + 角色卡(无数据先骨架屏) | copilot-tab-shell | ✅ ⚠️ 徽章是写死装饰,不反映真实连接 |
| 55 | 看 copilot 角色卡(Opus 4.8 / DeepSeek V4 Pro,Built-in/Third-party 徽章) | copilot-role-list | ✅ 已接真 registry；eligible 读后端 `copilot_sdk_compatible`，不再前端猜 method/protocol |
| 56 | (首次无角色)自动填 3 张种子卡 | role-seed-fallback | 🟡 ⚠️ 前端现造,默认 props 还是 mock |
| 57 | 看每 route SDK 状态灯(N/M SDK Ready) | route-sdk-status-badge | 🟡 ⚠️ 只按 ui_state==ready 粗映射,非真测过 SDK |
| 58 | 点 `Test` → 逐 route 验 SDK 工具调用(testing→ready/unsupported) | copilot-role-test | ✅ ⚠️**假测试**:探针走 `AsyncAnthropic`(发 weather 工具调用),真实 copilot 跑 `ClaudeSDKClient` —— 测的 SDK ≠ 跑的 SDK(§3.4 要修) |
| 59 | 拖动调 route 回退优先级 | route-fallback-reorder | ✅ ⚠️ 运行侧 `_resolve_copilot_route` 只取首条,重排未必生效 |
| 60 | `Add route` 追加兼容 route / 垃圾桶删 | route-fallback-add/remove | ✅ 可选 route 读后端 `copilot_sdk_compatible`；未知 method 保留可测，明确不兼容 method 过滤 |
| 61 | model-group 行的 Remove 按钮 | model-group-remove | 🟡 ⚠️ disabled 写死且无 handler,纯占位 |
| 62 | 点 `Add model` 新建第三方 copilot 角色草稿卡 | copilot-role-add | ✅ ⚠️ key 命名触发后端分流误判风险(见下 bug) |
| 63 | 空卡下拉选 Model group → 变可配置角色 | copilot-config-model-group | ✅ ⚠️ 选 group 后 key 变 modelGroupId(无 `copilot_` 前缀) |
| 64 | 删第三方 copilot 角色(确认 toast) | copilot-role-delete | ✅ built-in 卡无删除;走整表 PUT 覆盖 |
| 65 | (期望)改完看保存中/已保存反馈 | copilot-save-status | ⚠️ stale-code:`void saveStatus; void error;` 直接丢弃,改完无任何反馈 |

> **🐛 潜伏 bug(接线必修)**：新建 copilot 角色 id 用 `copilot_custom_N`,但选 model group 后 `selectModelGroup` 把 role key 改成 `modelGroupId`(如 `claude-sonnet-4.7`,**无 `copilot_` 前缀**);后端 `put_llm_roles` 的 copilot/graph-agent 分流只认 `copilot_` 前缀 → 会**误判为 graph-agent 角色错存**。
> **🛠 后端有·前端无**：`POST /api/copilot/roles/{role}/test-sdk` 前端从未调(且最终仍落同一 AsyncAnthropic 假探针);真实对话 `ws`→`ClaudeSDKClient` 属 skill 工作台不在设置页;`dispatch_copilot` 仍 501 占位。
> **mock 来源**：`mock-copilot-data.ts`(默认 props)、`copilot-role-state.ts` 全套 + `mockCopilotRoles`(死代码,仅 test 引用)。

### 7.5 贯穿性问题（cross-cutting，现状审计结论）

1. **测试 → SSOT 落差(头号工程)**：provider 测试(API Keys)与 role 测试(Roles/Copilot)后端都有持久化/job,但前端仍有易失副本、切 tab/刷新即丢。目标 = 删前端易失层、完全以后端投影为准(§6.5 检查 2)。settings 接线的主工程。
2. **写入归属 = gateway Python,永不 Rust 化数据层**：见 §7.1 机制。settings **不适用** D12「写全量 Rust」,唯一 native 操作是选默认 skills 目录。
3. **孤儿组件群**：API Keys 4 个 + Roles 5 个 + Copilot `copilot-role-state` 全套 + 多个 backend-only 端点。逐组判定:计划待接线(保留) vs 历史死代码(清理)。
4. **Copilot 整体桩程度最高**：mock 数据 + 假测试(SDK 不一致) + save 无反馈 + 分流误判 bug + 占位按钮。

### 7.6 当初的 open questions → 已拍板对照（闭环,无遗留待答）

| 早期 open question | 结论落点 |
|---|---|
| 测试态 SSOT 落盘/回填、删前端易失层 | ✅ §6.5 检查 2 + §4.1 Probe Knowledge Catalog 写回 |
| Copilot 整 tab 做到哪档 | ✅ 配置 + 真测试(修假测试)全做,§3.4 |
| Copilot 分流 bug(#62/63 丢前缀) | ✅ 确认是 bug、接线必修,§7.4 |
| role intent(#42/43) | ✅ **PR3 简化定稿**:thinking 开关 + max output token 纯数字 + temperature;删 required/block/context/mode/downgrade,§2.3 Role Intent |
| Available Models 静默过滤(#35) | ✅ 显式展示「为何缺失」,§2.1 + §4.2 6 态 |
| Model Bundle 语义(#50/51 快照/无 Test) | ✅ §2.6 Model Bundle 与 Role 高度统一 |
| API Keys 现状差(probe/mask/两步/protocol/孤儿/base_url/状态术语) | ✅ §1.2 + §4.2 + §7.2 |
| 壳层 NFR(骨架/WS 重连/全局保存徽章) | ✅ §7.0 + Stage 0 PM 拍板 |
| 孤儿组件群处置 | ⏳ 接线工程逐组判定(保留 vs 清),非设计待答 |
