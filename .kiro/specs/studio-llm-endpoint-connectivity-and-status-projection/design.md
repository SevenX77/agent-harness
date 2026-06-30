# Design — 已确认决策(+ 待定项清单)

> 只收录**已与用户确认无问题**的设计;尚需对齐的列在末尾「待定项」,确认后再补。
> 依据见 `research.md`,需求编号见 `requirements.md`。KEEP-MAIN:gateway/engine 默认冻结,
> studio 层改动走 adapters;凡需动 gateway 的单独标注并先取授权。

## D1 — 状态归一:单一持久化归一状态(已确认 R1)

**决策**:每个 route(及 endpoint)落盘**唯一**归一状态字段,前端只读它投影。

- **状态枚举(扁平,投影侧零计算)**:沿用并收敛到一套 UI 语义 ——
  `ready`(绿/已验证生成) · `historical_ready`(蓝/历史 probe-verified) · `untested`(灰) ·
  `failed`(红/真失败) · `disabled`(灰禁用/off) · `cooling_down`(熔断中)。
- **reason 子码(可选,仅诊断/文案,不参与颜色)**:归一一套
  `invalid_key · quota_exceeded · invalid_model · endpoint_unreachable · missing_config · no_model_available · timeout · upstream_error`。
- **谁写**:后端在**写状态的时机**(test/probe)直接算好归一状态 + reason 落盘;
  `route.evidence` 仍是 append-only 历史,**状态字段从 evidence + 探测结果一次性派生后存下来**,
  不再让前端/投影器各算一遍。
- **前端**:删除 `endpointStateDisplayStatus` / `providerTestResultFailureScope` 的文本匹配二次判定(R1.2),
  改为直接读归一状态 + reason。
- **分两阶段**(已确认):
  - **阶段一(本期)**:把**测试态**归一落盘 + 前端只读。这步即修掉 R1.4(endpoint/route 分叉)与 Qiniu 一红一不红。
  - **阶段二(可后置,R1.5)**:engine 真实调用结果经**事件总线**回流 studio 写归一状态;
    **gateway 保持存储无关,不直接写 credentials**(守 KEEP-MAIN)。
- **不变量**:endpoint 归一状态与其 routes 归一状态**不得语义分叉**(同一失败因子,二者一致)。
- **落点(定稿,T1)**:就**一个**归一状态字段持有上面 6 态 + `reason_code`(+ `cooling_down` 配 `retry_at`)。
  **不再保留并行的 4 值 `route.status`**;迁移期可临时双写,**终态收敛为单字段**,后端现读 `route.status`
  的逻辑(`endpoint_probe_priority` 对 `verified`/probe-verified 的判断等)改读归一态(`ready`/`historical_ready`)。

## D2 — 没有模型可测:不猜、不测、untested + ⚠(已确认 R2)

- get-models 返回空表且无已知 route ⇒ **不回退 `notable_model_ids` 做生成探测**(删/绕过该三级兜底中的"保底猜测"分支)。
- 该 endpoint 归一状态 = **untested**,reason = `no_model_available`;连通性(reachable)如实记证据。
- **不新增**状态枚举(用户明确:没测就是 untested)。
- UI:测试触发 **toast 报错**;endpoint tooltip 加 **⚠**,文案「该 endpoint 未返回可用模型,请手动输入模型名做单模型测试」。
- **不引入**"用远端 catalog 补 model list"(用户明确:没有就别测)。

## D3 — invalid_api_key ⇒ disabled(已确认 R3)

- 结构性认证错误(`invalid_key`/`authentication_error`)⇒ 该 **endpoint + 其全部 route** 归一状态 = `disabled`(投影 `off`),reason=`invalid_key`。
- evidence 仍记 `probe-failed`(诊断),状态走 disabled。
- 改 key 重测通过 ⇒ 自动复活(disabled 非终态锁,下次成功探测覆盖)。

## D4 — endpoint 测试 = 只测连通性(已确认 R4)

- 达标线:get-models 可达 = reachable;对**真实存在的**模型成功生成一次 = verified。
- **不**在 endpoint 测试里逐 method / tool-use 穷举。
- **method / tool-use 真测移到 LLM Role / Copilot Role 测试**(另立 spec/阶段);本 spec 仅声明边界。
- 沿用现有候选上限(6)与早停语义(成功或结构性错误即停)。

## D5 — 补齐 ark 多协议(已确认 R5,部分需 research 收口)

- **已坐实**:gateway 既有 method 证明 ark 同时有 **openai 形**(`ark_chat`)与 **anthropic 形**(`ark_anthropic_messages`)与 `ark_responses`(research §5)。
- 配置 ark 时应能建立 ark 的 **openai_compatible** 形 endpoint(确定补);**anthropic_compatible** 形按上述证据**确认纳入**。
- 以 gateway 既有 method 为准,不臆造。**实现处是否触及 gateway 待定**(见待定项)。

## D6 — 手动单模型探测扇出(已确认 R6)

- 目标集 = 该 provider 下**所有填了 key+base_url 的 endpoint**,含 failed/untested/disabled。
- 实现取向:**前端扇出**(对每个目标 endpoint 各发一次现有 `/endpoints/{id}/models/test`),不改后端契约、最快;
  各 endpoint 结果分别回写。(若后续要"单请求批量",再加后端路由,本期不做。)
- 成功的 endpoint 据结果更新归一状态(D1)。

## D7 — 诊断日志补齐(已确认 R7)

- 在 `llm_credentials` 真相源下补结构化记录:get-models 原始结果(可达/返回 model id 列表/空表/是否触发保底)、
  探测的 protocol×base_url×model 组合及成败、更新的 route evidence/capabilities 计数+id(受体量上限)、测后上传选取与结果。
- 复用 `record_runtime_activity`,`changes` 字段结构化;超大列表截断并标注 omitted 计数(沿用现有 `_MAX_LOGGED_ROUTES` 风格)。

## D8 — provider id 可见 + 索引语义(已确认 R8)

- provider 卡片标题 tooltip 展示 provider id + 其聚合的 endpoint id 列表。
- 注释/文档澄清:provider 列表用**前端派生 provider id** 索引;**catalog evidence 用 `host + model_id` 索引**,
  与本地 endpoint id(带哈希)解耦(research §6)。**不**把 endpoint 哈希 id 当 catalog 键。

## D9 — Community catalog 配置只读展示(已确认 R10)

- Community model catalog 开关下,只读展示 manifest URL + 签名公钥(token,非文件),标注「系统默认/可被环境变量覆盖」,无编辑框。

## D10 — 连通性分层模型(已确认 Part A,本 spec 脊柱)

- 五层 L1 api_key / L2 base_url / L3 endpoint(+protocol) / L4 route(+model) / L5 capability·method。
- L1+L2 由 get_models 判定(**充分非必要**:失败落「未知/待 endpoint 测」,不武断标红)。
- L3/L4 必须用真实 model 探测;L5 移 role/copilot。
- **api_key / base_url 指示器重做**(D10↔R-A2):各自表达本层连通态,删掉「api_key 勾只绿不红、base_url 复用 endpoint 派生态」的现状(research §A)。
- **一 model 多 route 聚合**(R-A4):model 展示态 = 其名下所有 route 归一态的聚合(任一绿则可用);贯穿 model 标签与 role 内 endpoint/route 标签。与 D1 同源实现。

## D11 — evidence 匹配身份统一(已确认 Part B-1)

- 定**唯一**「匹配身份」派生函数,本地存 / wire 传 / 回填三处共用,消除现状三套口径(research §6)。
- 颗粒度:endpoint 级 `(base_url, protocol)`、route 级 `(endpoint, model)`;**不强制洗 URL**,只要全链路规则一致。
- method 是否进匹配键 → **待定 T8**(倾向不进,作 evidence 附加属性)。

## D12 — provider 分类身份 = 注册域派生 + alias(已确认 Part B-2)

- **provider 规范名 = base_url 的 eTLD+1 标签**,系统化派生:`api.qnaigc.com`→`qnaigc`、`*.wavespeed.ai`→`wavespeed`。
  **用注册域、不用完整 host**(否则 `api./llm.wavespeed.ai` 裂成两家)。不同注册域默认两家(qnaigc≠qiniu),不强合。
- 叠加 **provider 级 alias/展示名**(`Qiniu`/`WaveSpeed`/`ARK`),新增 provider 维度(现状只有 endpoint/route 级 display_name)。
- **写进 catalog `provider_id`**(现状仅透传未填,research §B)。
- eTLD+1 需 PSL(`.co.uk`/`.com.cn` 多级后缀)→ **实现选型待定 T6**。
- 动机:api_key / 用量 / 计费挂在 provider 层(R-B8)。

## D13 — 社区贡献开放:allowlist → 安全闸(已确认 Part C)

- **移除** `PUBLIC_PROVIDER_HOST_ALLOWLIST` 准入名单;任何**公网 provider** 脱敏证据可贡献。
- 换**安全闸(黑名单式)**:拦私有 host(RFC1918 / localhost / 裸 IP / `*.local`)+ URL 带密钥/租户身份(长随机段 / token 形参);其余公网放行。
- 永不外传 api_key(沿用脱敏字段集);受 `remote_model_catalog_enabled` 门控。
- 安全闸**判定细则**(私有段清单、"疑似密钥路径"启发式阈值)→ **待定 T7**。

---

## 实施分波(已确认排序)

1. **第一波(无架构争议,先上)**:D9(只读展示)、D6(手动探测扇出)、D2 的 UI 部分(toast+⚠ 骨架)。
2. **第二波(状态归一脊柱,TDD)**:D1 阶段一 + D3 + D2 后端 + D4 语义 + D7 日志(彼此同源,一并做)。
3. **第三波(增量)**:D5(ark 多协议)、D8(tooltip/索引澄清)。
4. **阶段二(后置)**:D1 阶段二(运行期事件回写)+ R9(逐模型探测进度事件 + 标签动画 + 自动展开)。

## 待定项(未确认,确认后再并入正文)

- **T1 归一状态落点 —— 已确认(用户裁决)**:**单一**归一状态字段,枚举 = 6 态
  `ready / historical_ready / untested / failed / disabled / cooling_down` + `reason_code`(+ `cooling_down` 的 `retry_at` 时间戳)。
  **不保留并行的 4 值 `route.status`**;后端现读 `route.status` 的逻辑(`endpoint_probe_priority` 等)迁到读归一态。
  前端只读归一态。(D1 据此修订。)
- **T2 ark 多协议 —— 已确认走配置**:provider 的协议/method/官方 host 映射/别名/notable models **全部入一份结构化 provider 配置文件**(data-driven),代码读配置、不硬编码。
  是否仍需动 gateway(若 studio 无法仅靠配置 + 现有 per-method probe 完成)→ 实现时核,触及 gateway 再取授权。(D5/D12 据此修订。)
- **T8 匹配键含 method —— 已确认:不含**。method 与 capabilities 同级,均为 route/evidence 附加属性,不进匹配身份。(D11 据此定稿。)
- **T3 R9/阶段二事件**:逐模型探测进度事件的事件名/载荷、与现有 `useStudioEventStream` 的接法。
- **T4 读同步开关 drift**:`remote_model_catalog_enabled` 是否也应门控读同步(对齐注释/上游设计),还是只门控写?属上游 catalog-ssot 范畴,本 spec 仅记录,不擅自改。
- **T5 provider 分组键**:前端 `credentials.providers[].id` 的确切派生规则(实现 D8/D12 时精确核;应统一到 D12 注册域派生)。
- **T6 eTLD+1 实现选型**:用 PSL 库(`tldextract`/`publicsuffix2`,新增依赖,过 pip-audit)还是内置精简后缀表?多级后缀(`.com.cn`/`.co.uk`)必须正确。
- **T7 安全闸判定细则**:私有段清单(RFC1918/CGNAT/`*.local`/裸 IP)、"疑似密钥/租户身份 URL"的启发式(随机段长度阈值、是否含 query)、是否对边界情形要用户 opt-in 确认。
- **T8 匹配键是否含 method**:evidence 匹配核心键 = endpoint`(base_url,protocol)` / route`(+model)`;**method 倾向只作 evidence 附加属性、不进核心键**(method 属 L5)。需用户确认。
- **T9 api_key/base_url 失败归因**:get_models 失败时如何从错误码把 L1(key)与 L2(url)分开标(401→key、DNS/超时→url、404/空→「不提供 list,待 endpoint 测」),无法区分时落「未知」。细则待定。
