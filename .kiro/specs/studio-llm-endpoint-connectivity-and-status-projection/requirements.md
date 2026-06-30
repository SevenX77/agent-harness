# Requirements — Studio LLM 连通性分层 · 身份/唯一性 · 状态归一 · 社区贡献 · 诊断日志

> Spec 范围:重做「endpoint 连通性测试」语义为**分层连通性模型**;统一 **evidence 匹配身份** 与
> **provider 分类身份**;把分散的状态投影**归一到单一持久化状态**;按设计初衷**开放社区贡献**
> (移除固定 allowlist 改为安全闸);补齐探测全流程诊断日志;修一批真机取证坐实的缺陷(WaveSpeed/Qiniu)。
> 上游 spec:`studio-llm-credentials-catalog-ssot`。取证见 `research.md`;已确认设计见 `design.md`。

## 术语

- **endpoint**:一条 **(base_url × protocol)** 物理入口。
- **route**:endpoint 下一个具体 **model**(endpoint × model)。
- **model(逻辑)**:由 `canonical_id` 聚合的逻辑模型,**可对应多个 route(跨 endpoint/provider)** —— 一对多。
- **provider(分类身份)**:面向用户/计费的归类,= base_url 的**注册域(eTLD+1)**派生(见 Part B)。
- **evidence 匹配身份**:跨用户匹配证据用的机器键(见 Part B),分 endpoint 级 / route 级。
- **归一状态**:每个 route/endpoint 上**唯一**、决定 UI 投影的状态字段(+ 可选 reason 子码)。
- **连通性**:某一层「能到达并被接受」,**get_models 成功是充分非必要证明**(失败不等于不连通)。

---

## Part A — 连通性分层模型(本 spec 的概念脊柱)

**User story**:我希望连通性是**逐层**的——每加一个变量验证一层,状态各层独立、互不冒充。

- **R-A1 五层**:
  - **L1 api_key 有效** · **L2 base_url 连通**:二者由 **get_models 这一发**判定(成功=两者都通)。
    **充分非必要**:get_models 失败**不等于**不连通(provider 可能不提供 list 接口)→ 落「未知/待 endpoint 测」,**不得武断标红**;能从错误码区分是 key 还是 url 的问题时再分别标。
  - **L3 endpoint 连通** = L1 + L2 + **protocol**:protocol 是否被该 base_url 真正讲,**必须用一个 model 发一次**才证实(get_models 弱证可达;对真实 model 成功生成=强证 verified)。
  - **L4 route 连通** = endpoint + **model**:同一发探测**兼证 L3(endpoint/协议)与 model 可用**。
  - **L5 route 的某 capability/method 可用**:放到**真实应用环境(LLM Role / Copilot Role)**测,**不在 endpoint 测试里**。
- **R-A2 api_key / base_url 指示器要按 L1/L2 改**:现状 api_key 勾「只绿不红、且条件是模型列表可达」、base_url 图标「复用 endpoint 派生态」——**都不表达本层连通性**(research §A)。改为各自表达 L1/L2 真实连通态。
- **R-A3 endpoint 由 (base_url × protocol) 自动生成多条**,各自用 model 测 L3;UI「Available Endpoints」每个 chip = 「该 URL 讲不讲这套协议」的结论。
- **R-A4 一 model — 多 route 必须贯穿所有语境**:model 标签、LLM Role 中 model 下的 endpoint/route 标签,本质都是 **route 集合**;一个 model 的展示状态 = **对其名下所有 route 的聚合**(任一 route 绿则 model 可用)。任何 UI 不得假设 model 只挂单 route。

## Part B — 身份与唯一性(两个维度,分开治理)

**User story**:多用户场景下,名字随便填、api_key 每人不同(且是秘密),**真正有唯一性的是 base_url**。但「机器匹配证据」和「给用户分类」是两个维度。

### B-1 evidence 匹配身份(机器用,细颗粒,追求确定性+一致)

- **R-B1 颗粒度**:endpoint 级 = **(base_url, protocol)**;route 级 = **(endpoint, model)**。**哪怕不洗 URL 也行**——那就是跑通时的真实配置参数,**只要全链路规则一致**即可匹配。
- **R-B2 三处统一**:本地存储键 / wire 上传键 / 回填匹配键**必须用同一个「匹配身份」派生函数**。现状三套口径不一致(本地 `canonicalize_base_url` 按协议规整 / wire `normalize_base_url` 通用 / 回填只用 `host+model`,research §6)→ 收敛为一。
- **R-B3 待定(见 design 待定项 T1)**:匹配键是否含 **method**?倾向:**method 是 evidence 的附加属性,不进核心匹配键**(method 属 L5);需用户确认。

### B-2 provider 分类身份(用户/计费用,粗颗粒)

- **R-B4 provider 名 = base_url 的注册域(eTLD+1)派生**,**系统化、不硬编码**:
  `https://api.qnaigc.com/v1` → 注册域 `qnaigc.com` → provider 名 **`qnaigc`**;
  `https://llm.wavespeed.ai/v1` 与 `https://api.wavespeed.ai/api/v3` → 同注册域 `wavespeed.ai` → **同一 provider `wavespeed`**。
  **关键:用注册域、不用完整 host**——否则 `api.wavespeed.ai` / `llm.wavespeed.ai` 会被裂成两家(不符逻辑)。
- **R-B5 不同注册域默认即不同 provider**(如 `qnaigc.com` 与 `qiniu.com` 默认为两家,合理,不强合)。
- **R-B6 alias / 展示名**:provider 名(`qnaigc`/`wavespeed`)是**机器规范名**;叠加**人类展示别名**(`Qiniu`/`WaveSpeed`/`ARK`),用于 UI。现状无 provider 级别名概念(只有 endpoint/route 级 `display_name`)→ 新增。
- **R-B7 catalog 数据携带 provider 分类**:把 provider 规范名写进 catalog 的 `provider_id`(现状该 wire 字段只透传、未系统填充,research §B)。
- **R-B8 理由(写入设计动机)**:api_key、token 用量、计费都挂在 **provider** 这一层,故 provider 必须是稳定、用户可辨识的归类。

## Part C — 社区贡献:开放新 provider(移除固定 allowlist,换安全闸)

**User story**:我希望用户能上传**新 provider** 的连通证据,让库越来越厚;现有「只白名单 host 才参与」违背初衷,不是我定的。

- **R-C1 开放贡献**:任何**公网 provider** 的(脱敏)连通证据都可上传/参与社区匹配,**移除 `PUBLIC_PROVIDER_HOST_ALLOWLIST` 这个"准入名单"**(research §3/§9)。
- **R-C2 换成安全闸(黑名单式)**——隐私顾虑真实存在,故不是无脑放开:
  - **拦截**:私有/不可公开 host(RFC1918 内网段、`localhost`、裸 IP、`*.local`);URL 路径/query 里**疑似带密钥/租户身份**的(长随机段 / token 形参)。
  - **放行**:其余正常公网 DNS host。
- **R-C3 永不外传 secret**:api_key 等绝不进 wire(沿用现有脱敏白名单字段集)。
- **R-C4 用户可整体关**:受 `remote_model_catalog_enabled` 开关门控。

## Part D — 状态归一:单一真相,前端只读

- **R-D1** 每个 route(及 endpoint)落盘**唯一**归一状态 + 可选 `reason_code`;前端**只读它**投影。
- **R-D2** **移除前端基于 `last_test_message` 文本子串匹配的二次判定**(`endpointStateDisplayStatus`/`providerTestResultFailureScope`,research §2)。
- **R-D3** 归一状态由后端在**写状态时机**(test/probe)算好落盘;真实运行期调用的回写作**阶段二**(R-D5)。
- **R-D4** endpoint 与其 routes 的归一状态**不得语义分叉**(修 Qiniu「endpoint 红 / route 却 Untested」「同样失败一红一不红」)。
- **R-D5(阶段二)** engine 真实调用成功/失败经**事件回流** studio 写归一状态;**gateway 保持存储无关,不直接写盘**。

## Part E — 行为修复

- **R-E1 没模型可测就不测、不猜**:get_models 空表且无已知 route ⇒ **不回退 `notable_model_ids` 文档保底模型**去探(WaveSpeed 被猜出 `o3-mini` 即此,research §3);状态 = **untested + reason `no_model_available`**,**不判 failed、不加新状态**;UI **toast 报错** + endpoint tooltip 加 **⚠**「无可测模型,建议手动单测」。
- **R-E2 invalid_api_key ⇒ disabled**:结构性认证错误 ⇒ 该 **endpoint + 其全部 route** 归一为 **disabled**(投影 off);evidence 记 `probe-failed`;改 key 重测通过自动复活。
- **R-E3 endpoint 测试 = 只测连通性(L3)**:不在此逐 method/tool-use;method/tool-use 真测移 LLM Role / Copilot Role(另立 spec,本 spec 仅声明边界)。沿用候选上限(6)+ 早停(成功或结构性错误即停)。
- **R-E4 补齐 ark 多协议**:ark 既有 method 证明它同时有 openai 形(`ark_chat`)与 anthropic 形(`ark_anthropic_messages`)与 `ark_responses`(research §5);配置 ark 时按既有证据建立这些协议形 endpoint,不臆造。
- **R-E5 手动单模型探测扇出**:目标 = 该 provider 下**所有填了 key+base_url 的 endpoint**,**含 failed/untested/disabled**(撤销「只测成功 endpoint」);各 endpoint 各发一次、分别回写。

## Part F — 探测全流程诊断日志(归 `llm_credentials` 真相源)

- **R-F1** get_models 原始结果:可达否、返回哪些 model id(或明确「空表」)、是否触发保底(R-E1 应为否)。
- **R-F2** 探测了哪些 **protocol × base_url × model** 组合、各自成败原因。
- **R-F3** 本次更新了哪些 route 的 **evidence / capabilities**(计数 + id,受体量上限)。
- **R-F4** 测后上传:`collect_uploadable` 选了哪些、成功/失败。

## Part G — UI / 配置

- **R-G1 provider 标题 tooltip** 显示 provider 规范名 + 聚合的 endpoint id 列表。
- **R-G2(阶段二)测试中模型标签动画 + 自动展开**:endpoint 测试对某 model 探测时,该标签显示进行中动画(复用 `.api-route-tag-border-flow`),并自动展开完整模型列表;依赖后端发**逐模型探测进度事件**。
- **R-G3 Community catalog 配置只读展示**:开关下只读展示 manifest URL + 签名公钥(64-hex token,非文件),标注「系统默认/可被环境变量覆盖」,无编辑框。

---

## 验收门禁

- 后端 ruff + mypy(strict) + pytest×3 全绿;前端 lint + typecheck + test + build 全绿。
- 行为类改动**先写失败测试再写实现**(TDD)。
- 亲眼在运行的 Studio 里点过受影响界面(含 WaveSpeed/Qiniu 失败态)再报完成。
