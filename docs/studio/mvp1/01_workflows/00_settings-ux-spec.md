# Settings Page — 用户 UX Workflow 详细规格（API Keys / LLM Roles / Copilot）

> **来源**：PM 口述需求（2026-06-02）。PM 强调此前"写过好几次"但未落进 mvp1，本次正式记载。
> **地位**：设置页三个子页面的**权威 UX 规格**。[`00_settings.md`](./00_settings.md) 写四条旅程的结构与范式（高层）；本文写**每步操作 / 反馈 / 动机的细粒度行为**，尤其三条横切机制：draft 赋能/写回、model/endpoint 标签表现、测试落点。
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

**页面职责一句话**：确认每个 endpoint 可连通，并用 draft（历史探测知识库）回填模型清单的已知信息。真正"保证某模型能用"的测试在 role 页面做（见 §4.3）。

### 1.1 Official provider（官方，比较可控）
**动机**：官方 endpoint 可控，只要 API key 能连通就够，不必逐模型 probe。
**步骤**：
1. 用户填入 **API key**。
2. 直接点 **Test**。
3. 系统调 `GET /models`（获取模型列表）—— **只要这一步能连通，endpoint 即验证通过，不做逐模型 probe**。
4. **拉取 draft**（该 provider 的历史探测草稿 / 证据库），把拉回的 model list 与 draft **做 diff**。
   - **边界（PM 补充 2026-06-02）**：若 `GET /models` 返回 **200 但 `models=[]`（空清单）**，仍与拉取的 draft 做 diff，**用 draft 里的已知模型填充 model list** —— 空响应不代表没有模型（有的 provider 不返回清单），以 draft 历史为准。
5. **把 draft 中已证实的资料回填给 model list**（历史已验证的能力/元数据填进当前清单）。
6. model list 的标签变 **蓝色 =「以前联通过」**（历史连通标记）。
7. diff 出的**新模型 / 新 capability**（anthropic 在 get-model 时就会返回 capability）**写回 draft**（更新草稿）。
- **official 只需要 get models**，到此 endpoint 验证完成。

### 1.2 Third-party provider（第三方）
与 official **唯一的区别**：
1. 用户**必须填入 URL**（base_url）。`protocol`（协议）**以前要用户自己选，现在系统自动测**（自动探测协议）。
   - **探测方式（PM 2026-06-02，#C 答案）**：**把各 protocol 排列组合各测一遍**（用每种协议的连通方式去试），哪个能连通就判定为哪个 protocol —— "排列组合测一遍就知道"，不需要单独的聪明探测逻辑。
   - **(Claude live 验证 2026-06-02 修正)探测要打「推理端点」，不是 `/models`**：实测 `GET /v1/models` 在 openai 与 anthropic 两种网关上**都返回 200**（各自返回自己 shape 的清单），所以 `/models` **不能**判协议。真正判据 = 推理端点：openai 试 `POST /v1/chat/completions`、anthropic 试 `POST /v1/messages`，看哪个被接受、哪个被拒（如 `anthropic.qnaigc.com` 对 chat/completions 明确回 "Use /v1/messages instead"）。
   - **(Claude live 验证)每协议要带对的 auth header**：anthropic 兼容的第三方网关（qiniu-anthropic / openrouter）用 `x-api-key` 裸探得 401，但它们在 config 里是 verified → app 实际走 `Authorization: Bearer`。探测时 header 带错会把"能用"误判成"不通"。
2. **endpoint 真连通验证 = 批量模型探测**（不是只点一个模型；PM 2026-06-03 改）：
   - **为什么必须探模型（不能只 get-models）**：`get-models` 只证明 **apikey + URL 可达**，**不证明 protocol↔URL 匹配 / 能真生成**。实证：qiniu 的 openai URL 能 `GET /models`(200) 但 `POST /v1/messages`→404 —— get-models 过了不代表该协议能用。所以第三方必须**用模型打推理端点**才算验通。
   - **为什么批量、不靠单个**：单模型探测**不可靠** —— 实测同一个 `deepseek-r1` 一次 401、再测 200（瞬时抖动）；`minimax/glm` 间歇超时。原来让用户手选一个模型，就是怕系统自动只挑一个、它恰好抖动/超时 → **误判整个 endpoint 不通**。现在改全自动，必须用批量消除这个误判。
   - **机制**：系统**自动分批**探测（每批 ~3 个，优先挑常见可靠模型抬命中率；不一个一个、避免一长串失败浪费时间）；**一批一批打**，直到**某批中任一模型成功 → 判 endpoint 可用（停）**；或**模型探尽全失败 → endpoint 不可用**。
   - **错误码短路（省去试完所有模型）**：遇**结构性错配**码可直接判"协议/配置错"不必试完 —— openai 打 anthropic URL→`500 "Use /v1/messages instead"`；anthropic 打 openai URL→`404 not found`；未知模型→`400 invalid_request`。**但瞬时类（401 / 429 / timeout）不可短路**（与真失败靠码区分不了、且会抖动）→ 继续下一个/下一批。
3. draft 行为、标签行为等等**与 official 一致**。
4. **（PM 2026-06-02/03 拍板：直接设计实现，非可选）一个 provider = 一把 key + 多个 URL**：
   - **模型（PM 校正）**：**一个 provider = 一把 key**，其下挂**多个 URL**；每个 `(URL × 探通的协议)` = 一个 **endpoint**。一个 URL 同时通两协议（openrouter）→ **两个 endpoint 都建**（确认①）。
   - **gateway/registry 无「卡」概念（确认②）**：只存**平铺的标准 endpoints**，**不感知它们来自一张卡还是两张卡**（card 是前端录入便利；多 URL → 标准 endpoint list 的拆分由 ③b 做，见 #3.1）；「同一 provider」靠 endpoint 共享的 `credential_ref` + `rate_limit_bucket` 表达，不是一个 card 实体。
   - **共享（确认③）**：同一把 key 的所有 endpoint 共享 `credential_ref`，且 **一把 key 对应一个 `rate_limit_bucket`**（一处限流、全部冷却）。
   - **展示**：endpoint **平铺，不做协议分组子区**；在 LLM Roles 里同一模型跨 endpoint 合并成 model group，其下 endpoint **平铺展示在 model group 的「endpoints」标签**里。
   - **探测**：每个 URL 跑协议探测（打推理端点 + 对应 auth header，见上方 item 1 两条 live 修正）。
   - **拆分 + endpoint_id 生成 = ③b gateway（#3.1 反转，PM 第四轮判据校准）**：「多 URL × 多协议 → 多 endpoint」的**拆分 + 协议匹配 + 测试 + 生成 canonical `endpoint_id`** 由 **③b gateway** 做（它内置协议 SDK，最适合把混合原始信息理成标准 endpoint list）；**前端只录入**（card / 多 URL 行），把用户填的原始信息交给 gateway、拿回标准 endpoint list 展示；**③a 只 `upsert(endpoints[])` + 存储**。`endpoint_id` = ③b 生成的 canonical id（确定性规则 `{slug}-{protocol}[-{n}]`，见 #3.2）。⚠️ 原"前端拆分 / 前端生成 id / 后端不感知 card / `_stable_endpoint_id` 退役"已被本轮反转作废——endpoint 标准化是 ③b 公共能力。
   - **命名防撞（#3.2，PM 2026-06-03；统一格式 `{slug}-{protocol}[-{n}]`，序号永远在最后）**：默认 `{slug}-{protocol}`（最短）—— `qiniu-openai` / `qiniu-anthropic`、`openrouter-openai` / `openrouter-anthropic`。**只有 `(slug,protocol)` 撞了**才在**末尾**补短序号（首个不带、后续 `-2 / -3`；**不用整段 host，避免过长**）：2 URL 都 openai → `myco-openai` / `myco-openai-2`；2 URL × 2 协议都通（4 个）→ `myco-openai` / `myco-openai-2` / `myco-anthropic` / `myco-anthropic-2`（序号一律在 protocol **之后**，且同一 `-2` 恒指同一个 URL）。
   - **各 endpoint 独立**：canonical base_url（按协议归一）、protocol、status、routes、capabilities。

### 1.3 页面定位（重要边界）
- API Keys 页面**必须验证 endpoint**（official：API key 连通 / get-models；third-party：再加一次模型探测）。
- **但它不是"测试模型连通性"的主战场** —— 逐模型"保证能用"的 probe 在 role 页面做。
- 不过这里**留了入口，可以批量对单个模型做 probe**（escape hatch：需要时在 API key 页也能批量探单模型）。

### 1.4 测试结果的展示与落地（UX，PM 2026-06-03 实测反馈）
- **#2.1 结果常驻原地、不只 toast**：endpoint 测试耗时久时，结果一出 toast（sonner）就闪没、看不到（要再测一次、把鼠标悬在 toast 上才看得到）。→ 测试结果（成功 / 失败原因）除 toast 外，**必须固定写在 API Key / Base URL 旁的状态勾（✓）位置**（常驻 inline），鼠标无需追 toast。
- **#2.3 单模型测试结果换样式**：Manual probing 的单模型结果（`xx: Available` 绿 / `xx: Test failed` 红 badge）**还在用旧 model-badge 样式** → 改成与新状态体系一致的呈现（对齐 §4.2 的 route 级状态色 + inline）。
- **#2.4 测试结果全进 draft**：这几次的 endpoint / 模型探测结果（**含失败**）都要写进 draft / 证据库，**不浪费**（失败也是历史：哪些模型抖动 / 超时 / 不可用；下次免重探、喂蓝态）。见 §4.1。
- **#2.5 错误码→用户文案 = 英文（回填 A7，PM 2026-06-03 定 UI 语言 = 英文）**：测试失败的可读诊断用**英文**，权威源 = 现网 `apps/studio/frontend/src/lib/llm-error-messages.ts`（已在 ProviderCard / Settings 用，含 HTTP 状态映射 + `composeTestErrorMessage`）；旧 `studio-api-keys-redesign/design-frontend.md §4.3` 的**中文整表作废**。**产品 UI 语言 = 英文**（非 A7 独有：Connected / Not configured 等全英文）。§1.4 的 inline 常驻诊断 + toast 都用这套英文文案。

---

## 2. LLM Roles 页面 — 把抽象角色映射到模型，并真实测通

> 本节 = §0 原话 + **2026-06-03 第二轮原子动作走查**（PM 逐条裁定，原话见 §2.0）的细化定稿。走查工作流水见 [`_reorg/alignment-notes.md`](../../_reorg/alignment-notes.md)。本节整合三股改动：① ux-spec 状态体系（6 态 / failed-disabled 两分类 / draft，见 §4）；② 上一 part 底层改动（P8 run 模型对比测试复用 model-group/bundle；D10/D12 settings 数据走 gateway sidecar 永不 Rust）；③ gateway mvp1 契约（role→route 一等 API、base_url 保存时归一化、`build_runtime_setting_descriptors` 驱动 intent 控件，见 §6.2）。

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

### 2.3 Role Intent（角色意图）
> 控件应由后端 `build_runtime_setting_descriptors`（把 route capability 投影成前端控件描述符的函数，`registry/capabilities.py:205`）驱动，前端不硬编码各 provider 规则。
- **Thinking**〔#2〕：off / preferred / required **三档互斥**——**必须用单一三态控件**（segmented / radio / select），**不可用两个开关表达**。现码只有 off/preferred 两态，需换组件 + 补 required 档。
- **Output token**：target 值 + `Use max` 开关。**downgrade 默认策略不需要 UI**〔#3〕——保持默认（allow），不暴露 block/warn 选择控件。
- **Route max token 摘要**：投影 route capability，只读。
- **布局**〔#4〕：现 intent 配置布局偏丑，**只调内部布局、不改逻辑**（轻量 UI 优化）。
- **Token Intent 完整 schema（回填 B1+，2026-06-03）**：`target_output_tokens` 与 `target_context_tokens` 都是 `TokenIntent{mode, value?, downgrade?}`，`mode` 五档：`inherit`（**仅** Model-Group / provider 级可用，Role 级不可）/ `default` / `maximum_available`（=`Use max`）/ `target`（配 value）/ **`required_minimum`**（达不到 → role-fit 转 Not Fit）。**继承**：Model-Group 级 intent 默认继承 Role 级、可对该组覆盖；Role 级 mode 必须是具体档（不能 `inherit`）。§2.3 现有"target 值 + Use max 开关"只覆盖 `target`/`maximum_available` → UI 至少还要能表达 `required_minimum`（驱动 Not Fit）和 `default`，并补 `target_context_tokens`（现只有 output token）。
- **downgrade**：是 `TokenIntent` 上的字段（allow / allow_with_warning / block），**schema 保留、默认 allow、不做 UI**（#3）。
- **`cost_priority`：mvp1 砍掉（PM 2026-06-03 拍板）** —— 不做 UI，**schema 也不留**；等真有成本优化需求再加。

### 2.4 状态展示与 tooltip（清理）
- **role-fit 状态灯**：role card 内每 provider 行显 role-fit（Using / Downgraded / Needs Test / Not Fit，role-local 派生，从不改全局 health；来自后端 materialize report）。
- **单一顶层 tooltip**〔#5〕：fail / downgrade 信息**只在 tooltip 展示**，不另起面板。**`RoleTestResultPanel`（角色测试结果面板）已被 PM 删除、不要**（避免加重 UI 复杂度）——不挂载、应清理。
- **清嵌套 tooltip**〔#5〕：provider row 现有**嵌套 tooltip 冲突**→清理为**一个顶层 tooltip**。

### 2.5 Role 测试
- 点 **Test** → 对 **role 里所有模型批量真 probe**（不停在第一条成功）→ 实时回填状态灯 + downgrades（进 tooltip，§2.4）→ **结果（含失败）回写 draft / 证据库**（§4.1）。
- BE：`POST /api/llm/roles/{name}/test` + `/test-jobs`（异步轮询，`llm.py:996/1009`）；evidence 回写部分已在（`_append_model_probe_evidence`，`:771`）。
- **后端 SSOT**：删前端易失 `roleTestStates`，测试态全以后端 job / 投影为准（切 tab / 刷新不丢）。
- 未保存先拒测：draft 测试 = 先 `PUT` 保存再 test。

### 2.6 Model Bundle（与 Role 高度统一）
- **定义**：Model Bundle = 自建的"已排好 fallback 的 model group"；与 model group 区别：可放**不同模型**、**预配 provider**；可像 model group 一样拖进 role card 解析成 route list。
- **Pinned 置顶槽〔回填 B4，PM 2026-06-03 要〕**：已配好/已测的 Model Bundle 在 Available Models **顶部单独成槽、视觉区分**显示（置于 model-group 列表之上），强调可复用，与普通 model group 视觉区分开。
- **统一原则**〔#6/#7/#9〕：bundle 的录入/测试/改名删除 UI **与 role 统一**——
  - `Add Model Bundle` 按钮放到**与 `Add Role` 同位置**〔#6〕。
  - 束 **Test 前端复用 role 的测试**（同组件 / 同路径，束也能独立测）〔#7〕。
  - 束 **Rename / Delete 与 role 统一**〔#9〕。
- **拖进角色 = 引用（同步）**〔#8/#12〕：把束拖进角色后是**引用**，不是快照——**改束 → 所有引用它的角色同步跟着变**（像共享组件实例）。**此条覆盖 765 设计的"快照复制"方案**。落地含义：角色存的是 bundle 引用（bundle_id），materializer 在物化时**按引用拉取当前束内容**展开成 fallback_chain（不在拖入时复制）。

### 2.7 跨页：role 状态 + 快捷 Test 进 Properties 面板〔#11〕
- **节点 Properties 面板**（作者 / 运行期给节点指定 `llm_role` 的地方）**每个 role 旁加 Test 键** + **展示 role 状态**——快捷验"能不能用"，**不必切到 Settings 再测**。
- 复用 §2.5 role 测试 + §2.4 role-fit 状态投影；**跨 region**：Roles 能力的测试/状态投影进 `phase-editing` / properties region 协同（非本页独占）。

### 2.8 P8 跨页：run 模型对比测试复用 model-group/bundle → 临时 role〔#11 认可〕
- run 的"模型对比测试"可选 role / model-group / bundle → endpoint/fallback，**解析成临时（未保存）包装的 role**。
- **复用同一套 materializer**（`llm_role_materializer.py`）+ 新增一条"临时 role"解析路径；run 页**引用 settings 里建好的 bundle/group**，不在 run 页另存。详细归 run/predict region，本页只登记"model-group/bundle 多了 run 这个消费方"。

### 2.9 测试关键点（§5 硬栏，写测试时必须验证）
- **failed 仍在可用**：构造一条 route probe 失败（非弃用类）→ 断言它**仍出现在可用模型、标红、可拖**（防回归成"失败即消失"）。
- **disabled 才灰且不可拖**：provider 明确返回"无此模型 / 已下线" → 归 disabled → 进弃用区、不可拖、可复制名 + 可 re-probe → 再通**捞回**可用模型。
- **蓝态**：endpoint 验通 + draft 有历史连通 → 该模型显 🔵 蓝；role 页真 probe 通 → 升 🟢 绿。
- **配置缺口红显引导**：缺 key / 无效 key / base_url / protocol / model → `failed`（reason=配置缺口，红）→ 组内**标红 + 「去配置」+ 引导去 API Keys 修**（不隐藏、不默认选）。
- **role 测试批量**：role Test 探**所有**模型（非停首条成功），失败也回写 draft，切 tab / 刷新**不丢**。
- **bundle 引用同步**：改 bundle 内容 → 所有引用该 bundle 的 role materialize 出的 fallback_chain **跟着变**（验引用非快照）。
- **thinking 三档**：off/preferred/required 用单控件互斥，required 且模型不支持 → role-fit 转 Needs Test / Not Fit，不静默。
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
- **eligible 判据 = 后端 capability**（route 的 protocol / call_method 支持 anthropic-messages：anthropic 原生 / deepseek-anthropic / ark-anthropic / openrouter-anthropic），**取代前端 `isClaudeAgentSdkCompatibleRoute`（按名字猜兼容性的函数，`CopilotTab.tsx:228`）名字启发式**。
- **未测试也显示、不预过滤**〔#3〕：PM 原话"你没测试的时候不知道，所以还是会显示在 available models 里面（just keep them in there）"。即 SDK 工具调用能力**未测时未知**，不能据此把 route 滤掉 —— 与 §2「untested/failed 不滤」同一原则；真 SDK 测试（§3.4）才确证。
- **内置角色 = 动态浮出**〔#2〕：**不写死 2 个**，而是**默认只浮出 Claude 和 DeepSeek 在 available models 里最新最好的模型**，按 family 偏好阶梯择优：
  - Claude：优先 **opus 4.8**，没有则退 **opus 4.7**（再往后退更旧）。
  - DeepSeek：优先 **V4 Pro**，没有则退 **V3.2 Pro**。
  - 都没有 → 不浮出默认，用户自建。现码硬编码映射 `copilot_opus_4_7`↔`claude-opus-4.7`（`CopilotTab.tsx:132-133`）需改为此动态择优。

### 3.3 配 copilot 角色
- 新建第三方 copilot 角色草稿（`Add model`），id = `copilot_custom_N`（`CopilotTab.tsx:202`，带前缀✓）。
- **选 Model group = 可搜索的选项卡**〔#1〕：C10 的选组器要**可搜索**（同 §2.1 可用模型搜索体验），不是裸下拉。
- route 兜底序拖排 / Add / 删 route（eligible 判据见 §3.2）。
- 单 model group 约束（§3.1）。

### 3.4 测试 = 真 SDK 调用（修假测试，核心）
- **现状假测试**：`_probe_copilot_sdk_tool_call`（copilot SDK 测试探针，`llm.py:2150`）用 `AsyncAnthropic`（裸 Anthropic HTTP 客户端，`:2156`），而真实 copilot 跑 `ClaudeSDKClient`（`copilot.py:242`）→ **测的 SDK ≠ 跑的 SDK**，测过不证明 spawn/env 注入/tool loop 能跑。
- **目标**：测试改走**真 `ClaudeSDKClient` 路径**（gateway `12-inv-copilot-invocation` 目标），发真工具调用、验 spawn/env/tool loop；成功**写高阶证据**（SDK 工具调用验证通过）回 credentials + draft。
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
- **默认浮出阶梯**：available 里有 opus 4.8 → 浮出 4.8；只有 4.7 → 浮出 4.7；deepseek 同理 V4 Pro→V3.2 Pro。
- **fallback**：多 route 按顺序尝试（非只首条）。
- **保存反馈**：改完显保存中/已保存；失败显式告警不静默。
- **去 mock**：无真数据时空态/骨架屏（非 mock 种子）。

---

## 4. 三条横切机制（贯穿三页）

### 4.1 Draft 赋能 / 写回
draft = 该 provider 的**历史探测草稿 / 证据库**，双向：
- **赋能（读）**：拉取 draft，把**已证实的资料**回填给当前 model list（历史已验证的能力/元数据，不用重探）。
- **写回（写）**：本次发现的**新模型 / 新 capability（diff 部分）写回 draft**，沉淀为下次的历史知识。
- **（PM 2026-06-03）每次探测结果——成功 + 失败——都写回 draft / 证据库，不浪费**：失败也是历史信息（哪些模型抖动 / 超时 / 不可用），下次批量探测可优先跳过历史失败的、优先试历史成功的，抬命中率、省时间。

### 4.2 Model / Endpoint 标签的表现 —— route 级状态体系（PM 2026-06-02 拍板，#A 答案）
标签颜色 = 该 **route** 的状态，**三页一致**（同一 endpoint/route 从 API key 页拖到 role 页，颜色不变）。**canonical 状态枚举（6 态）= `ready` / `historical_ready`(🔵 蓝) / `untested` / `failed`(带 reason) / `cooling_down` / `off`**；下表的 `verified` = `ready` 旧称、`disable` = `off`，是现码字段 / 展示映射，不另立态：

| 颜色 / 样式 | 状态 | 含义 |
|---|---|---|
| 🟢 绿色 | **verified** | 真测试连通了（真实 probe 过） |
| 🔵 蓝色 | **以前联通过** | 历史连通过（来自 draft 回填），但当前未真测 verified —— 介于"没测"与"verified"之间的历史态 |
| ⚪ 灰色 | **untested** | 没测试 |
| 🔴 红色 | **failed** | 出错了要你修：① 配置缺口（缺 key/base_url/protocol/model id，原 needs_setup）② 测试失败（route 真探挂）—— `reason` 区分。**红、不挡进可用** |
| ⚪ 灰色 + 倒计时 | **熔断 / cooling_down** | 临时失败（网络/限流/超时），倒计时后重试，不当永久失败 |
| ⚪ 灰色 + 无法选 | **disable / off** | 被禁用，不可选 |

> **单模型 probe 失败的两类（PM 2026-06-03）**：① **模型已弃用 / 不再提供**（provider 明确返回"无此模型 / 已下线"）→ 归 **`disabled`（灰、不可选）**，**不是红 failed**（不是"连不上"，是"没这模型了"）；② **其他失败**（该 model + endpoint 这条 **route** 连不上 / 生成失败）→ **`failed`（红）**，且 **failed 不阻塞它进 available models**（仍列出、标红、仍可选 —— 可能换 role 配置 / 重试就好；真正永久不可用才在运行期被 admission 拦）。瞬时类（网络 / 限流 / 超时）仍走 `cooling_down`（见上表）。
>
> **`disabled`（弃用）不是死刑（PM 2026-06-03）**：弃用模型进（可折叠的）「弃用区」、灰显、hover 显**禁用图标**、**不可拖进 role**；但**点击仍可复制模型名 + 仍可对它单独 re-probe**；**re-probe 再次连通 → 从弃用区捞回 available models**（弃用可逆，模型可能又上线了）。

> **与 gateway 现状投影的关系**：`project_provider_model_state`（投影函数，`services/llm_state_projection.py`）现产 **5 态**（ready / untested / cooling_down / needs_setup / off），其中 `needs_setup` 把"配置缺口"和"真测试失败"揉成一个灰态。**本体系两处改**：① **取消 `needs_setup`**——"配置缺口"与"测试失败"统一成 `failed`（红）+ reason；② **新增「🔵 蓝=以前联通过」**。目标 6 态映射：verified=ready🟢、以前联通过=蓝🔵、untested=untested⚪、**（配置缺口 ∪ 测试失败）=failed🔴（reason 区分）**、熔断=cooling_down、disable=off。→ **gateway 投影需：取消 needs_setup、补蓝态、failed 带 reason**。

#### 状态分层（蓝态归属 + 投影逻辑，Claude 2026-06-02 核实，PM 已确认 Q2）
- **三源域（事实从哪来）**：`Identity`（存在/启用/配置硬有效）· `Capability`（支持什么 + 测过没 + **draft 历史证据**）· `Health`（此刻能否跑/熔断）。铁律：单 status 不当统一真相。
- **🔵 蓝态归 `Capability` 域的 draft/证据子源**（历史连通），是 `ui_state` 投影层的**第 6 态**，**不是新源域**。
- **投影优先级（route 级，6 态）**：`off > failed🔴 > cooling_down > ready🟢 > 蓝🔵 > untested⚪`。`ready / 蓝 / untested` 同属"证据 tier"，按证据新鲜度排：刚测通 > 历史通（draft）> 无证据。
- **蓝↔绿 = 测试落点（§4.3）的直接产物**：API key 页验 endpoint + draft 回填 → 模型显 🔵 蓝；role 页对模型真 probe → 升 🟢 绿。即"endpoint 验证（蓝）→ model 保证（绿）"。
- **与其他状态轴正交**：`ui_state`（能不能用，6 态）≠ `capability_state`（了解多少能力：unknown/callable_only/partial/known）≠ `role_fit`（适不适合本角色，4 态）≠ `admission`（运行期 3 态）。
- **实现 gap**：`ProviderUiState` Literal **去掉 `needs_setup`、加 `failed`（带 reason）+ 蓝态**（`services/llm_state_projection.py:12`）；`_setup_reason`（`:49-56`）改产 `failed` + reason（`missing_config` / `endpoint_unreachable` / `model_failed`）而非 `needs_setup`；`project_provider_model_state` 现只读 endpoint+route+circuits、**不读 draft**，要加"draft 是否有该 route 历史连通"输入；依赖 draft probe-worker（现为桩 `routers/llm.py:872` 只改状态不真探）。

### 4.3 测试落点：role card 里的 model 才做真实测试
- **API key 页**：只验证 **endpoint**（轻量：连通 / get-models / 第三方加一次模型探测）。
- **role / copilot 页**：对 **role card 里的所有 model 做真实 probe**，**保证能用** —— 这才是"模型能不能用"的主战场。
- 一句话：**endpoint 验证在 API key 页，model 保证在 role 页**。

---

## 5. 与现状代码 / 其他决策的对接（cross-ref，不改 §0–§4 的需求）

> 本节是工程对接线索，帮实现时定位；**不修改上面的需求**。

- **draft 机制现状**：已有 `ProviderImportDraft`（草稿数据结构，`registry/schema.py:369`）、`llm_import_drafts.py`（草稿 + 证据库读写）、evidence library。**但 `probe_import_draft`（`routers/llm.py:872`，本该真去探测草稿的端点）现在是占位桩**（只把状态改成 probed、不真探）—— 本规格的"draft 赋能/写回"要真正工作，依赖把它做成真实 probe worker（= PM 已拍板"必须做"的 D2）。
- **统一 UI state 投影**：§4.2 的标签 = `project_provider_model_state`（投影函数，`services/llm_state_projection.py`）现产 5 个 state；本规格目标 6 态：**① 去掉 `needs_setup`（并入 `failed` + reason）② 新增「🔵 蓝=以前联通过」**（#A 已答，见 §4.2）→ gateway 投影需取消 needs_setup、补蓝态、failed 带 reason。
- **capability on get-model**：anthropic 在 get-model 时返回 capability —— 对接 gateway `03-credentials-endpoints` / `05-capabilities`；**#B 由 Claude 核实**各 protocol 的 list-models 是否带 capability（见下"Claude 待核实"）。
- **protocol 自动探测**（第三方）：**#C 已答** —— 各 protocol 排列组合各测一遍、哪个连通判哪个（见 §1.2）。
- **model bundle**：对接 `materialize_model_bundle`（把 bundle 物化成兜底链的函数，`services/llm_role_materializer.py:99`）+ `ModelBundle`（数据结构）—— bundle→route list 的解析已有雏形，实现时确认与本规格一致。
- **测试落点**：§4.3「endpoint 验证 vs model 保证」的分工，需在 gateway `03`(endpoint) / `07`(probe) / `08`(test-SSOT) 模块对齐。

### 已 PM 拍板（2026-06-02 第二轮）
- **#A 已答** → §4.2：route 级 6 态体系（🔵 蓝=以前联通过 是独立第 6 态）。gateway `project_provider_model_state` 需从 5 态补到 6 态。
- **#C 已答** → §1.2：第三方 protocol 自动探测 = 各 protocol 排列组合各测一遍，哪个连通判哪个。

### 新增需求（PM 2026-06-02 第三轮）
- **#D 多 URL per provider card**（PM 原话："一张 provider card 填两个 URL ,你就当我新加的,如果太难不懂也行"）：第三方 card 填多个 base_url → 各成独立 endpoint（各自探协议 + 验证），模型合并到该 card。
  - **Claude 可行性评估**：**不难** —— 是第三方流程的自然延伸；§1.2 已要求"每 URL 自动探协议"，多 URL 即把该步循环 N 次（每 URL → 一 endpoint → 探协议 + 验证）；主要新工作在 UI（卡片多 URL 输入 + 合并展示）。
  - **重叠提示（重要）**：LLM Roles 的"model group 把相同模型跨 endpoint 合并"**本已提供多 URL 兜底** —— 加两张卡（两 endpoint），role 里自动合并成一个带两 provider 的兜底组。故"同模型多 URL 兜底"核心需求现有机制已覆盖；一张卡多 URL 的额外价值 = provider 管理便利（两镜像归一个 provider 名下）。
  - **PM 拍板：不是可选 / 低优先，直接设计实现**。全量设计见 §1.2 item 4；Claude 早前的「可选」建议作废。**3 点已确认**：①一 URL 两协议都建；②平铺建 endpoint、后端无卡概念、roles 里进 model group 的「endpoints」标签（不分组子区）；③一把 key 一个 bucket。
  - **live 验证结果（2026-06-02，用 app 配置 key 真测，key 未外泄）**：
    - **Qiniu = 两 URL 各一协议（PM #2 确认成立）**：`api.qnaigc.com/v1` 只 openai（`GET /v1/models`→200；`POST /v1/messages`→generic 400）；`anthropic.qnaigc.com` 只 anthropic（`POST /v1/messages`→anthropic-shaped 401；`POST /v1/chat/completions`→500 明确 "Use /v1/messages instead"）。**每个 URL 只能一个协议**。
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

> **(Claude live 测 2026-06-02，用 app key 真测 list-models 首条字段)**：① 上表 anthropic / gemini / openai / openrouter 已坐实；② **第三方聚合网关可能阉割 capability**：qiniu 的 /models（openai 口 + anthropic 口）只回 `id`/`display_name`，**不透传** capability（即便底层是 anthropic）→ 「带不带 capability」**看具体网关，不只看协议**；③ 设计结论：**list-models 富字段优先 + 缺则 probe 兜底**，对应 `capability_source`（api_list vs probed_verified）+ draft 赋能。故 official 不一定「只 get-models」就够（openai-official / ark 仍需 probe 补 per-model 能力）。

> **⚠️ 代码缺口（接 #B，2026-06-03）**：anthropic 的 list-models 虽带 `capabilities` 富字段，但**现状代码还没消费** —— `registry/capabilities.py:137-198` 未读该块，anthropic 的 tool/thinking 仍按 `provider_doc` 硬编码注入（`services/official_capability_sources.py:208-223`）。所以"official 靠 list-models 免 probe"**目前未真正成立**，需把 anthropic capability 摄取接到新 `capabilities` 对象才行。

---

## 6. 层次分离：① 前端(ts) / ② 后端(rust) / ③a Studio 适配层 / ③b gateway 库（公共能力内核）

> PM 2026-06-03 第三轮：这两页**重度依赖 gateway**，必须把每个原子操作**精确分层 + 守好各自边界**；尤其 **③b gateway 库是领域无关的「编排 + 模型调用」库，绝不接收特定业务领域需求**。修正前版 §6 的错：把「Studio 后端 Python」与「gateway 库」混成一层「③ 后端 gateway」——本版拆为 ③a（Studio 适配）/ ③b（gateway 库）。§1–§4 写 UX，本节做四层归属 + 握手契约。
>
> ⚠️ **2026-06-03 第四轮判据校准（本节最新依据，反转部分 ③a/③b 划分）**：把"领域 vs 领域无关"精确成"**公共能力内核 vs 应用加工**"。gateway = **富能力可复用网关**（权威定义见 gateway 包 `packages/graph-agent-gateway/README.md` §2）：它对模型数据与机制的**标准化 / 组织 / 编排 / 状态总结 / 知识沉淀**，凡**不依赖「应用加工四件事」（UI / 产品策略 / 调用方式 / 存储介质）**，都是 ③b 公共能力——**含 model group 分组 / 6 态标准总结 / draft 知识库 / materialize 编排内核**（这几项**反转**了旧版"归 ③a"的判断）。③a 只拥有 gateway 感知不到的**应用加工四件事**：① UI 交互/展示 ② 产品策略 ③ 实际调用方式 ④ 存储介质。判定一句话：**换个 app 还原样能用吗？能=③b，不能=③a**。**下方 §6.0–§6.5 全部按此校准；个别仍按旧表述（把 model group/6态/draft 归 ③a）的 ✓ 注与格子，一律以本校准为准**，逐模块处置见 `docs/graph-agent-gateway/mvp1/module-disposition-revised.md`。

### 6.0 四层模型 + 领域无关铁律 + 三处握手
| 层 | 是谁（代码位置） | 管什么 |
|---|---|---|
| **① 前端 (ts)** | `apps/studio/frontend` | UI + 前端业务逻辑（拖拽 / 投影渲染 / 默认选择算法 / family 折叠 / 弃用区 / 可搜索选组 / draft 态展示）。**只投影、不持第二份真相** |
| **② 后端 (rust)** | native-fs | 对 Roles/Copilot **几乎不碰数据**（凭证/角色数据永不 Rust）。只：General 选目录 / sidecar 生命周期 + IPC 桥 / copilot **聊天 session** 落盘（D8，属 skill 工作台 region，**非设置页**） |
| **③a Studio 适配层（应用加工）** | `apps/studio/backend` | **应用加工四件事**：① UI 交互/展示（拖拽编辑、family 折叠、状态颜色渲染、可搜索选组）② 产品策略（默认推荐、动态浮出 opus4.8、弃用区）③ 实际调用方式（copilot 用 Claude SDK 拿 route 自己调）④ 存储介质（凭证/知识库存哪个文件）+ HTTP `/api/llm`·`/api/copilot` 适配壳。**只做 gateway 感知不到的加工** |
| **③b gateway 库（公共能力内核）** | `packages/graph-agent-gateway` | **富能力公共内核**：凭证&端点 schema+读写+base_url 归一化+原始→标准 endpoint list / available models（分组 model_group·识别 identity·知识库 draft+notable）/ capability 归一化+对比+lint / 客观状态+熔断+**6 态标准总结** / 角色→fallback 链（**materialize 编排内核**）/ 两级调用（role+route）+错误分类+原生 ChatX。**凡不依赖应用加工四件事（UI / 产品策略 / 调用方式 / 存储介质）的模型数据/机制处理皆公共**（详 README §3） |

**判据铁律（本节核心，2026-06-03 第四轮反转旧表述）**：③b **不是**"不能碰 model group / 6 态 / draft"——恰恰相反，**model group 分组 / 6 态标准总结 / draft 知识库 / materialize 编排的能力内核都属 ③b 公共**（gateway 机制衍生的最佳方案，任何 app 可复用）。**真正绝不上浮 ③b 的是应用加工四件事**：UI 交互/展示、产品策略（推荐/浮出/弃用/family 折叠）、实际调用方式（copilot SDK + session）、存储介质绑定。判定一句话：**换个 app 还原样能用吗？能=③b 公共，不能（绑死那四件事之一）=③a**。⚠️ 现码这些能力内核多数还**散在 ③a** `apps/studio/backend`（materialize / model_groups / 6 态 / draft / identity / notable / 熔断持久化）——按判据**应下沉 ③b**（下沉清单见修订版归属表）。

**三处握手**：
- **① ↔ ③a** = HTTP `/api/llm/*`（registry / roles / model-groups / model-bundles / endpoints / routes / test-jobs）+ `/api/copilot/*`（REST 配置 + WS 聊天流）。契约 = DTO（`ModelGroup` / `ProviderModelOption.ui_state`(6 态) / `RoleTestResponse`）。FE 只投影 DTO、不持第二份。
- **③a ↔ ③b**（进程内 Python）= ③a 把用户编辑出的**角色编排结构（候选 + 意图）**交给 ③b 的编排内核 `materialize` → fallback 链，再 `resolve_routes(role)` → `ResolvedRole`（有序 `ResolvedRoute` + skipped 诊断）。③b **看得到**"角色编排结构 + 意图"（通用概念，编排内核需要）；③b **看不到的**是"用户怎么拖拽/UI 编辑出它"（③a 应用加工）。注：materialize 编排内核按判据属 ③b，现仍在 ③a 待下沉。
- **③b ↔ provider** = 真实模型调用（graph-agent 走原生 ChatX；**copilot 例外**：库只给 route，调用交回 ③a `copilot.py` 用 `ClaudeSDKClient` 跑）。

**保留原则**：前端只投影后端 SSOT（不持第二份）；数据层走 gateway sidecar **永不 Rust**（唯一 native = General 选目录）；接口前缀 `/api/llm` + `/api/copilot`，v4 契约源 = `llm-provider-intelligence-v2` + `studio-api-keys-regression-hardening`，**不恢复 v3**。

### 6.1 API Keys 页（四层重做，与 §6.2/§6.3 一致）
> 前版"③后端gateway"三列已并入四层。**② Rust = N/A**（凭证/endpoint 数据永不 Rust）。核心分线（第四轮判据校准）：**协议探测 / list-models 解析 / capability 归一化 / route probe / base_url 归一化 / 错误分类 / endpoint 标准化拆分 + 生成 canonical id / 批量探测策略(短路·汇总) / draft 知识库内核 / 6 态标准总结** = **③b 公共能力**；**endpoint upsert + 存储 / 批量探测的 job-进度-HTTP 包装 / draft 的 import-apply 工作流 + 远端源 / 6 态颜色转 DTO** = **③a 应用加工**；**多 URL 录入** = 前端。

**四层职责：**
| 层 | 内容 |
|---|---|
| **① 前端 (ts)** | UI：official 固定 5 卡（隐藏 name/base_url，只填 key）；third-party 自增卡（**多 URL 行 `+ URL`**）；Test 按钮；6 态状态标签（常驻 inline，§1.4）；Manual model probing 面板（加删 model id）；API key 输入（**type=text + CSS mask** + 显隐 + 复制 + **密码管理器抑制属性**，本地 InputGroup）；删除二次确认；骨架屏；**窄视口不溢出**。前端逻辑：输入草稿态（debounce 300ms）；**多 URL 录入**（card / 多 URL 行）→ 把原始信息交给 gateway，由 **③b 拆分 + 协议匹配 + 生成 canonical `endpoint_id`**（前端不再自己拆 / 不生成 id）；**Test 触发 + 展示进度**（批量探测策略归 ③b，前端只触发 + 显示）；**只投影 registry**（provider 卡 + 6 态 + Available Models 按 `route.endpoint_id`），**不持第二份** |
| **② 后端 (rust)** | **N/A**（凭证/endpoint 数据永不 Rust） |
| **③a Studio 适配（应用加工）** | HTTP `/api/llm/*`（见握手）；把前端录入的原始信息转交 ③b、`upsert` ③b 拆好的 endpoint 列表 + 存储；**批量探测的 job/进度/HTTP 包装**（策略归 ③b）；**draft 的 import-apply 工作流 + 远端源选择**（`probe_import_draft` 去桩做真 worker，知识库内核归 ③b）；**6 态颜色/文案转 DTO**（投影内核归 ③b）；endpoint test / route probe 任务编排 |
| **③b gateway 库（公共能力内核）** | **协议探测**（对 URL 打各协议推理端点 + 对应 auth header：native anthropic=`x-api-key`、anthropic 兼容第三方=`Authorization: Bearer`）；**list-models 解析 per protocol**（OpenAI `data[].id` / Gemini `models[].name` 去 `models/` / 去重保序）；**capability 从 list-models 富字段归一化**（anthropic/gemini/openrouter 带；openai/阉割网关缺则 probe 兜底）；**base_url 按 protocol 保存时归一化**；route probe（1-token 真请求）；错误分类（结构错 404/500/400-invalid ↔ 瞬时 401/429/timeout）；**endpoint 标准化拆分 + 生成 canonical id；批量探测策略（短路·汇总）；draft 知识库内核（记录/复用/共享证据）；6 态标准总结**。不碰应用加工四件事，不知 card 录入交互 |

**三处握手（API 契约）：**
- **① ↔ ③a**：`GET /api/llm/registry`（RegistrySnapshot，api_key **redacted**）· `GET …/endpoints/{id}/secret`（单条明文，scoped reveal）· `PUT …/registry/endpoints`（upsert ③b 拆好的 endpoint 列表）· `POST …/endpoints/{id}/test`（批量模型探测）· `POST …/routes/{id}/probe[?force=true]`（单 route 真探 / Manual / Test Now）。DTO：endpoint/route + 6 态 `ui_state`，api_key 一律 redact。
- **③a ↔ ③b**（进程内）：③a 调库做 endpoint 拆分 / 协议探测 / list-models 解析 / capability 归一化 / route probe / base_url 归一化 / 批量探测策略 / draft 知识库读写 / 6 态总结；**③b 返回标准结果（标准 endpoint list、批量探测结果、draft/state 投影结果）**，③a 只包装 job/HTTP + 落存储。
- **③b ↔ provider**：协议探测 + route probe 的真实 HTTP（打推理端点）。

**逐操作归属（A1–A12，② Rust 全 N/A）：**
| # 动作 | ① FE-ts | ③a Studio 适配 | ③b gateway 库 |
|---|---|---|---|
| A1 进 tab 加载 | 渲染 official 5 卡 + 第三方卡 + 6 态 | `GET registry`（redacted） | — |
| A2 official 填 key + Test | 填 key、点 Test | get-models job 包装 + import/apply 工作流 + 转 DTO | list-models 解析 + capability 归一化 + **draft 写语义** + 6 态总结 |
| A3 第三方填 URL + 协议自动探测 | 填 URL、点 Test | 编排探测 + 判定可达 | **协议探测**（打推理端点 + auth header） |
| A4 多 URL × 协议 → 拆 endpoint | 多 URL 录入、触发 | `PUT endpoints` upsert + 存储 | **拆分 + 协议匹配 + 测试 + 生成 canonical endpoint_id** |
| A5 endpoint Test = 批量模型探测 | 触发 + 显示 inline | job/进度/HTTP 包装 + 写 draft（工作流） | **批量探测策略（批批打/命中停/结构错短路/瞬时不短路）+ route probe + 错误分类 + 汇总** |
| A6 单模型 Manual probe | 加删 model id、触发 | job 包装 + import/apply 工作流 | route probe + **draft 写语义** |
| A7 capability 回填 | 显示能力 | 投影 | **list-models 富字段归一化** + 缺则 probe |
| A8 draft 赋能/写回 | 蓝标签渲染 | 调 ③b 读写 + import/apply 工作流 + 远端源 | **draft 知识库读写语义 + probe 结果合并** |
| A9 6 态标签 | 渲染色 | 6 态结果转 DTO | **6 态标准总结（含读 draft 出蓝）+ RouteStatus + 熔断** |
| A10 secret reveal | 进 tab 逐个换真值 | `GET endpoints/{id}/secret`（scoped、单条明文） | — |
| A11 删 endpoint | 二次确认 | `PUT endpoints`（整表 upsert） | — |
| A12 save-status badge | 统一 badge ← saveStatus | save 端点返回状态 | — |

> **守边界检查（第四轮校准）**：③b 列是公共能力内核（协议探测/list 解析/capability 归一化/route probe/错误分类/base_url 归一化/**endpoint 拆分 + canonical id / 批量探测策略 / draft 知识库 / 6 态总结**）；③a 列是应用加工（upsert + 存储 / job-进度-HTTP / import-apply 工作流 / 颜色转 DTO）；① 只录入 + 渲染。⚠️ 原"前端拆分 / 前端生成 id / `_stable_endpoint_id` 退役"已反转——endpoint 标准化拆分 + canonical id 归 ③b。

### 6.2 LLM Roles 页
> **② 后端 (rust) = N/A**（角色/凭证数据永不 Rust，本页 Rust 不参与）。

**四层职责：**
| 层 | 内容 |
|---|---|
| **① 前端 (ts)** | UI + 前端业务逻辑：角色卡 + Available Models 侧栏（model group 卡、**family 可折叠**〔#1〕、**弃用区**可折叠、6 态色含 🔵 蓝、endpoint 平铺在「endpoints」标签）；拖 model group + **默认 provider 选择算法**（Ready+Untested+🔵 优先、排除 failed/off、cooling 有替代不默认选）；provider 链拖序/加删；intent 控件（thinking **三态互斥单控件**〔#2〕、输出 token，downgrade 无 UI〔#3〕，**布局轻优化**〔#4〕，控件由 ③b 描述符驱动）；Test 触发 + role-fit 状态灯 + **单一顶层 tooltip**（fail/downgrade 进 tooltip、**不要 RoleTestResultPanel**、清嵌套 tooltip〔#5〕）；Model Bundle 区（**Add 与 Add Role 同位**〔#6〕、复用 role 编辑/测试/改名删除、**拖进角色=引用**〔#7/#8/#9/#12〕）；family/弃用区折叠（localStorage 视图态）；**只投影、不持第二份**（删 `roleTestStates`） |
| **③a Studio 适配（应用加工）** | `GET /api/llm/registry`（model_groups DTO + 6 态 `ui_state`）· `GET /api/llm/model-groups` · `GET/PUT/DELETE /api/llm/roles[/{name}]` · `POST /api/llm/roles/{name}/test(-jobs)` · `GET/PUT/DELETE /api/llm/model-bundles[/{id}]`+`/test`。**应用加工**：拖拽编辑角色/绑定的 UI；**default 选择/推荐策略**（产品策略）；6 态颜色转 DTO；materialize 报告 + role 测试结果的渲染；draft 的 import-apply 工作流。（model_group 分组 / materialize 编排 / 6 态总结 / draft 知识库的**内核归 ③b**，见右列）|
| **③b gateway 库（公共能力内核）** | **model group 分组 / identity 识别**；**materialize 编排内核**（按意图过滤路线 + 降级 + 排 fallback 链 + role-fit/downgrade 诊断）；`resolve_routes(role)`→`ResolvedRole`；capability 归一化 + 对比 + `build_runtime_setting_descriptors`（驱动 ① intent 控件）；`lint_role_routes`（只 warn/block 不选型）；route probe；ChatX 调用；熔断 + 错误分类 + **6 态标准总结**（供 ③a 转 DTO）。③b 看到"角色编排结构 + 意图"（通用），看不到"用户怎么拖拽编辑出它" |

**逐操作归属（R1–R25，② Rust 全 N/A）：**
| # 动作 | ① FE-ts | ③a Studio 适配 | ③b gateway 库 |
|---|---|---|---|
| R1 进 tab 加载 | 渲染角色卡+侧栏 | `GET registry`(model_groups) | — |
| R2 可用模型过滤 | 过滤渲染(family/弃用/6态) | 调 ③b + 转 DTO | **model group 分组 + 6 态总结(读 draft) + route modality capability** |
| R3 搜模型 | 纯前端 | — | — |
| R4 看 6 态 | 渲染色 | 6 态结果转 DTO | **6 态标准总结 + RouteStatus + 熔断** |
| R5 弃用区 | 渲染/复制名/re-probe 触发 | disabled 分类 + 投影 | route probe(re-probe) |
| R6 新建 role | 弹框 | `PUT roles` | — |
| R7 拖组+默认选 | 拖拽 + 默认算法 | 接收存 model_groups | — |
| R8–R10 调序/增删/删组 | reorder/增删 | `PUT roles` | — |
| R11 fallback 开关 | 开关 | 传 fallback 开关给 ③b | **materialize 尊重 fallback 开关** |
| R12 thinking 三态 | 三态控件←描述符 | 描述符投影 | thinking capability + descriptor |
| R13 output token | 控件←描述符 | 同上 | max_output capability + descriptor |
| R14 route max 摘要 | 显示 | role_effective_runtime_settings 投影 | `_effective_runtime_settings` |
| R15 role-fit 灯 | 显示 | 渲染 fit 灯(读 ③b report) | **materialize 算 role_fit + capability + lint** |
| R16 role Test 批量 | 触发 + 轮询喂灯 | `POST roles/{}/test-jobs` job 包装 + 落存储 | `resolve_routes` + 批量 route probe + **draft 写语义** |
| R17 Test 失败条 | 显示(未保存先拒) | 同 R16 | — |
| R18 fail/downgrade | 单顶层 tooltip(无 panel) | 渲染 downgrade tooltip(读 ③b report) | **materialize 产 downgrade 诊断** |
| R19 role 改名删 | 菜单 | `PUT/DELETE roles` | — |
| R20–R21 Add/编辑 bundle | 同 role(同位/复用编辑器) | `PUT model-bundles` | — |
| R22 束 Test | 复用 role test | `POST bundles/{}/test` 编排 | resolve(临时) + probe |
| R23 束拖进角色=引用 | 引用(非快照) | 传 bundle 引用给 ③b | **materialize 按引用展开 bundle** |
| R24 束改名删 | 同 role | `PUT/DELETE bundles` | — |
| R25 被动刷新 | 重投影 | WS `roles_changed` | — |

> **守边界检查（按 §6.0 第四轮判据校准）**：③b 列是公共能力内核（resolve/capability/lint/probe/ChatX）；**model group 分组 / materialize 编排 / 6 态标准总结 / draft 知识库的内核也属 ③b 公共**（现散 ③a 待下沉）。③a 真正独占的是**应用加工**：拖拽编辑交互、默认选择/推荐策略、状态颜色渲染。

### 6.3 Copilot 页
> **② 后端 (rust)**：copilot **配置**(本页)= N/A；但 copilot **聊天 session 落盘**(D8)= Rust native-fs（skill 工作台 region，非本页）。
> **关键边界**：copilot 的 **SDK 调用 / 测试 / session 都属 ③a Studio 领域**（`copilot.py` 用 `ClaudeSDKClient`）；③b gateway 库**只做 route 解析 + capability**，不碰 SDK 调用、不知 copilot 语义。

**四层职责：**
| 层 | 内容 |
|---|---|
| **① 前端 (ts)** | copilot 角色卡(**单 model group**)；**可搜索选组器**〔#1〕；Test 触发；route 排序/加删；新建第三方角色(`copilot_` 前缀)；**「Backend Integration」slot 换统一 save-status badge**〔#4〕(四页共用、idle 静默)；**去 mock**；**内置动态浮出**〔#2〕(Claude opus4.8→4.7、DeepSeek V4Pro→V3.2Pro)；**eligible 不预过滤未测 route**〔#3〕；**copilot_ 前缀必修**(选组后保前缀)；UI 尽量复用 role |
| **③a Studio 适配（应用加工）** | 复用 roles 端点(`role_kind=copilot`，`_is_copilot_role` 认 `copilot_` 前缀) + `POST /api/copilot/roles/{name}/test-sdk` + WS 聊天流。**领域逻辑**：**copilot SDK 调用**(`copilot.py` `ClaudeSDKClient`、base_url→env)；**真 SDK 测试**(修假测试 `AsyncAnthropic`→`ClaudeSDKClient`，`llm.py:2150`)；走**全 fallback 链**(非 `_resolve_copilot_route` 只取首条)；eligible 判据(调 ③b capability)；内置动态浮出策略；session 持久化(D8)+失败显式告警；测试证据回写 draft |
| **③b gateway 库（公共能力内核）** | **仅** `resolve_routes("copilot_chat")`→`ResolvedRoute[]`(③a 拿去自己用 SDK 调；**库不调 SDK、不知 copilot 是什么**)；route 是否 **anthropic-messages 兼容**的 capability(供 ③a 判 eligible) |

**逐操作归属（C1–C12，② Rust 全 N/A；session 除外属 chat region）：**
| # 动作 | ① FE-ts | ③a Studio 适配 | ③b gateway 库 |
|---|---|---|---|
| C1 进 tab | 渲染卡 + save-status badge | `GET registry` | — |
| C2 角色卡动态渲染 | 渲染 | 从真 model_groups 投影 copilot 角色 | — |
| C3 种子卡(去 mock) | 无 mock | 同 C2 | — |
| C4 route SDK 状态灯 | 显示 | 来自真 SDK 测试结果(③a 存) | — |
| C5 Test 真 SDK | 触发 | **`ClaudeSDKClient` 真跑** + 写证据/draft | **仅** `resolve_routes` 给 route |
| C6 route 兜底序 | 拖序 | `PUT roles` + 走全链 | `resolve_routes` 返回有序 |
| C7 Add/删 route(eligible) | 增删 | eligible 判据(调 ③b capability) | anthropic-messages 兼容 capability |
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
| **draft 赋能/写回** | 蓝标签 + "以前联通过"提示(渲染) | import/apply 工作流 + 存储介质/远端源选择(应用加工) | **draft 知识库内核(记录/复用/共享探测证据)属 ③b 公共**(现 `llm_import_drafts.py` 在 ③a 待下沉)；产出 probe 结果写入知识库 |
| **6 态投影** | 渲染状态色(绿/蓝/灰/红/熔断/关) | 状态颜色/文案的呈现选择(应用加工) | **6 态标准总结(ready🟢/蓝🔵/untested⚪/failed🔴/cooling/off,failed 带 reason)属 ③b 公共**(现 `project_provider_model_state` 在 ③a 待下沉,需取消 needs_setup)；产出 RouteStatus + 熔断 |
| **测试落点** | Test / Test Now 按钮(触发) | endpoint test / role test 编排 + 回写 SSOT | route probe(1-token 真请求) + 熔断写 health store |
| **多 URL / 协议探测** | 多 URL 行(录入) | endpoint upsert + 存储、批量探测的 job/进度/HTTP 包装 | **endpoint 拆分 + 生成 canonical id + 协议探测 + base_url 归一化 + 批量探测策略 + 错误分类** |
| **save-status badge** | 四页共用统一 badge(idle 静默) | save 端点返回状态 | — |

### 6.5 两处守边界检查（实现 / code review 必过的两条架构不变量）
四层之间有**两条内部边界**必须守住——它们是这套握手的不变量，散落在 §6.1–§6.4 的 ✓ 注在此收拢成两条正式检查，逐条验：

**检查 1 @ ③a ↔ ③b 边界：③b = 公共能力内核，不含应用加工（2026-06-03 第四轮反转旧不变量）**
- **不变量**：③b **不是**"不能含 model group / 6 态 / draft"——它们的**能力内核（分组 / 状态标准总结 / 知识库 / materialize 编排）恰属 ③b 公共**。③b **绝不出现的是应用加工四件事**：UI 交互/展示（颜色、布局、折叠、渲染）、产品策略（默认推荐、浮出 opus4.8、弃用区、family 折叠）、实际调用方式（`ClaudeSDKClient` / copilot session）、存储介质绑定（硬编码文件路径 / 远端源）。
- **怎么查**：① grep ③b 公共 API 有无**应用加工**痕迹——渲染/颜色/布局、"默认推荐"策略、`ClaudeSDKClient`、硬编码存储路径；② 对每个 ③b 能力问"**换个 app 还原样能用吗**"——不能（绑死 UI/产品策略/调用方式/存储）= 错放 ③b。
- **违反信号**：③b 里冒出渲染/颜色/默认推荐策略/copilot SDK 调用/硬编码存储位置。
- **现状**：⚠️ **能力内核待归位**——materialize / model_groups / 6 态 / draft / identity / notable / 熔断持久化的内核现仍散在 ③a `apps/studio/backend`，按判据**应下沉 ③b**；copilot SDK 调用、HTTP 壳、UI 渲染、产品策略**正确留 ③a**。下沉清单见 `docs/graph-agent-gateway/mvp1/module-disposition-revised.md`。

**检查 2 @ ① ↔ ③a 边界：前端只投影、不持第二份真相**
- **不变量**：前端（①）的"测试态 / 状态 / 模型清单"**只能从后端 registry 投影**，**不得**在前端组件态 / store 里另存一份真值（切 tab / 刷新就丢的并行态）。
- **怎么查**：① grep 前端有无本地"测试结果 / 状态"的 source-of-truth（而非 `GET registry` 投影）；② 切 tab / 刷新后状态是否仍在（在 = 从后端读 = 对；丢 = 前端自持 = 错）。
- **违反信号**：前端组件态里有 `roleTestStates` / `routeStatusOverrides` / mock 种子数据当真值。
- **现状**：✗ **未守住** —— 仍残留 `roleTestStates`（Roles 易失测试态）、`routeStatusOverrides`、`mock-copilot-data`（copilot mock 种子）→ **本次接线工程要删，改为纯投影后端 SSOT**（切 tab / 刷新不丢）。这是本设计交付的主接线工作之一（对应检查 2 从 ✗ 转 ✓）。

---

> **scope 边界一句话**：本次设计交付 = **① 前端 (ts) + ③a Studio 适配层**（含"不持第二份、只投影"接线改造）；**③b gateway 库** = 写给它的**领域无关能力需求 + 握手契约**（标「新增能力」待补，但**绝不接收领域需求**）；**② Rust** 对这两页近乎不参与。