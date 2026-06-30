# Tasks — 实施清单(TDD 顺序)

> 规则:每个行为类任务**先写失败测试(red)再写实现(green)**。门禁(全绿才推):
> 后端 ruff + mypy(strict) + pytest×3;前端 lint + typecheck + test + build。
> 需求/设计编号见 `requirements.md` / `design.md`。`[ ]` 待办 · `[~]` 进行中 · `[x]` 完成。

## 约定:状态归一字段(贯穿全 spec 的核心数据)

- 单一归一态 `ProviderRoute.status`(收编为 6 态)+ `reason_code` + 可选 `retry_at`(D1/T1)。
- 迁移期允许临时双写,终态单字段;后端读旧 4 值处改读归一态。

---

## Wave 1 — 无架构争议,先落地(可并行,独立可推)

### W1-A · Community catalog 配置只读展示(D9 / R-G3)
- [ ] **W1-A.1** 后端 `/api/system/...` 暴露 manifest_url + signing_pubkey(只读;来源 `backends.py` 默认/env)。
- [ ] **W1-A.2 (red→green)** 前端 GeneralTab:Community model catalog 开关下只读展示两项 + 复制按钮 + "系统默认/可env覆盖"说明;vitest 渲染断言。
- [ ] **W1-A.3** 亲眼:General 页看到两项只读展示。

### W1-B · 手动单模型探测扇出到所有 endpoint(含 failed)(D6 / R-E5)
- [ ] **W1-B.1 (red)** 前端测试:`ManualModelTestPanel` 对一个有 N 个已配置 endpoint(含 failed)的 provider,触发 N 次 `/endpoints/{id}/models/test`。
- [ ] **W1-B.2 (green)** 前端:`runModelTests` 改为遍历该 provider 下所有 key+base_url 齐的 endpoint(含 failed/disabled),各发一次、分别回写;聚合结果展示。
- [ ] **W1-B.3** 亲眼:WaveSpeed 这类多 endpoint provider,手动单测覆盖全部 endpoint。

---

## Wave 2 — 状态归一脊柱(TDD,彼此同源,一并做)

### W2-A · 归一状态数据模型(D1/D10)
> **发现订正**:gateway `ProviderRoute` **已有** `ui_state`(6 态,`schema.py:24/221`),studio route 继承——**被持久化但每次响应被重算覆盖**。故无需"加 6 态字段 / v5→v6 迁移";W2-A 实为「把计算从读时挪到写时落盘 + 补齐 reason companion」。按用户认可框架:gateway `route.status`(4 值物理态)保留作路由输入,studio 加**展示态** companion。
- [x] **W2-A.1/.2 (red→green)** studio `ProviderRoute` 加持久 studio-only `reason_code: str|None`(`ui_state` 已继承);`_gateway_route` strip 它(连同 display_name/evidence)不进冻结区 gateway。**无 schema 升级**(可选字段默认优雅兼容旧文件)。门禁:ruff · mypy(strict)· LLM 域 pytest 全绿(干净 main 基线;唯一失败=Windows chmod 预存环境)。
  (`test_registry_stamps_route_reason_code`)
  > **retry_at 推迟阶段二**:它是熔断计时的瞬态值(cooling_down),持久化会触发 datetime/str 序列化告警且语义不对。本刀只落 `reason_code`(稳定可持久,正是干掉前端文本匹配所需);retry_at 随运行期回写(R-D5)一起设计。
- [ ] **W2-A.3** `endpoint_probe_priority` 等读 `route.status` 处——评估是否改读归一态(route.status 仍是 gateway 路由字段,多数读点应保留;逐一甄别)。

### W2-B · 投影坍缩到单字段(D1 R-D1/R-D2)
- [x] **W2-B.1 (red→green,raw routes 面)** `_project_route_ui_states` 写回 route 时**一并 stamp `reason_code`**(原来只 stamp `ui_state`、丢了 reason——正是前端要去文本匹配的根因)。`/api/llm/registry` 的 `provider_routes` 现带 ui_state+reason_code。
- [x] **W2-B.1b(已存在)** model_groups 面 `_provider_model_option`([llm.py] `"reason_code": projection.reason_code`)**早已暴露** reason_code;无需补。两个投影面现都带 reason_code。
- [ ] **W2-B.2(可后置)** 写状态时机预算归一态落盘,响应只读(cooling_down 因依赖熔断计时仍需读时 overlay,属阶段二/运行期)。
- [ ] **W2-B.3 (red→green)** 前端:删 `endpointStateDisplayStatus`/`providerTestResultFailureScope` 文本匹配,直接读 ui_state + reason_code;改既有快照/单测。(需跑 app 亲眼验证)
- [ ] **W2-B.4 (red→green)** 一 model 多 route 聚合(R-A4):model 标签态 = 名下 routes 归一态聚合(任一 ready 则可用);贯穿 model 标签 + role 内 endpoint/route 标签。

### W2-C · L1/L2 指示器按层重做(D10 / R-A2)
- [ ] **W2-C.1 (red)** 前端:api_key / base_url 各自独立连通态(get_models 成功=两者通;失败按 T9 归因或落"未知",**不武断标红**)。
- [ ] **W2-C.2 (green)** 重做两指示器(api_key 支持绿/红/未知,base_url 不再复用 endpoint 派生态)。

### W2-D · 没模型不猜 + invalid_key⇒disabled(D2/D3 · R-E1/R-E2)
- [x] **W2-D.1 (red)** 后端:get_models 空表且无已知 route ⇒ **不调 `notable_model_ids` 探测**;endpoint=untested(**非 failed**)。
  复现 WaveSpeed o3-mini 场景。✓ RED 实证根因:失败信息显示探测了 `[gpt-4o,…,o3-mini]` 6 个 notable 模型。
  (`tests/routers/test_llm_registry_api.py::test_endpoint_test_third_party_no_models_does_not_guess_notable_models`)
- [x] **W2-D.2 (green)** 改 `_third_party_probe_model_ids` 去保底猜测(`return []`)+ `_verify_third_party_endpoint_by_probe`
  无模型→新增 `status="no_model"`(reachable/untested),caller 映射到 `unverified_manual`、`last_test_message` 提示手动单测。
  删除超期旧测 `..._empty_model_list_falls_back_to_notable_probe`(锁旧行为)。门禁:107 passed · ruff · mypy 全绿。
  > 注:本刀用现有 `unverified_manual`(=untested)落地,**未**依赖 W2-A 的 6 态新字段;待 W2-A/B 落地后归一态自然接管。reason=`no_model_available` 与 ⚠/toast 归 W2-D.4。
- [x] **W2-D.3 (red→green)** invalid_key ⇒ endpoint + 其全部 route = `disabled`(非 failed);get-models 成功时先清该 endpoint 的 disabled route(自动复活),再走 upsert/verify。
  改 `test_endpoint`:加 `auth_failed`(get-models `invalid_key`)、status 类型加 `disabled`、disable cascade + revive sweep。
  更新旧测 `test_endpoint_test_rejects_invalid_api_key`(failed→disabled+route cascade)+ 新增 revive 测试。门禁:122 passed · ruff · mypy 全绿(完整后端套件确认中)。
  > 注:本刀只判 get-models 的 `invalid_key`(主路径,Qiniu/WaveSpeed 截图即此);第三方"生成探测返回 invalid_key"的边缘场景留待 W2-A/B 归一时统一。reason 子码同样并入 W2-A/B。
- [ ] **W2-D.4 (red→green)** 前端:untested+`no_model_available` 的 endpoint tooltip 显示 ⚠ + 文案;测试触发 toast。

### W2-E · 诊断日志补齐(D7 / R-F)
- [x] **W2-E.1a (red→green)** `endpoint_test` 记录补 `reachable`(get-models 是否到达)+ `discovered_model_ids`(实际 model id 列表,原来只有 count)。归 `llm_credentials` 源。
  (`test_endpoint_test_logs_discovered_models_and_reachability`)。`model_list_observed` 已记 added/removed/unchanged。
- [x] **W2-E.1b (red→green)** `ThirdPartyEndpointVerification` 加 `probe_attempts`(每个 {protocol, model, status}),在协议探测 + 批量循环里采集、4 个 return 点带回;`endpoint_test` 记录加 `probe_attempts`。
  (`test_endpoint_test_logs_probe_attempts`)。门禁:105 passed · ruff · mypy 全绿。
- [x] **W2-E.1c (red→green)** 测后上传(autoshare)成败记录:`_autoshare_after_probe_best_effort` 成功记 `autoshare_uploaded`(含 `uploaded_count`)、失败记 `autoshare_failed`(含 `attempted_count`+error),都归 `llm_credentials` 源;失败记录自身也不抛(守 best-effort 契约)。门禁:ruff · mypy · 7 autoshare pytest 全绿。
  > 「更新的 route evidence/capabilities 计数+id」那半留作可选小尾巴(`model_list_observed` 的 added/removed/unchanged + W2-E.1a/1b 已覆盖"测了啥/拿到啥"的主要诊断面)。

---

## Wave 3 — 身份与配置 data-driven(D11/D12/D13 + T2/T6/T7)

### W3-A · provider 配置文件(data-driven,替代硬编码)(T2)
- [ ] **W3-A.1** 定结构化 provider 配置(协议/method/官方 host→id/别名/notable models);定位与格式(YAML/JSON,落 `apps/studio/backend/app/data/` 或扩 `docs/development/llm_provider_notes/`)。
- [ ] **W3-A.2 (red→green)** 代码改读配置:移除 `_endpoint_notable_provider_key` 硬编码 qiniu/openrouter、official host 映射、ark 协议硬编码。
- [ ] **W3-A.3** ark 多协议(R-E4)经配置补齐(openai 形 + anthropic 形 + responses);若需 gateway probe 改动→先取授权。

### W3-B · provider 身份 = 注册域派生 + alias(D12)
- [x] **W3-B.1/.2 (red→green)** 新建 `services/llm_provider_identity.py::registrable_provider_name(base_url)` —— eTLD+1 派生(T6 定:**内置精简多级后缀表**,无新依赖、不过 pip-audit 风险):`api.qnaigc.com`→`qnaigc`、`api./llm.wavespeed.ai`→同一 `wavespeed`、`ark.cn-beijing.volces.com`→`volces`、裸 IP/单标签/`foo.com.cn`→`foo`/None。15 参数化单测。
- [x] **W3-B.3a (green)** catalog `provider_id` 系统填充:`_build_model_probe_evidence` + `_build_official_profile_probe_evidence` 两个 probe-evidence 构建点 `provider_id=registrable_provider_name(endpoint.base_url)`(R-B7)。门禁:ruff · mypy · 121+35 pytest 全绿。
- [ ] **W3-B.3b** 前端 provider 分组键统一到注册域(T5)+ alias 展示表(`qnaigc`→Qiniu / `volces`→ARK,data-driven)——**前端 + 配置文件**,归 W3-A/前端批。
- [ ] **W3-B.4** provider 标题 tooltip 显示 provider 名(D8/R-G1)——前端。
  > 注:`_endpoint_notable_provider_key` 的 qiniu/openrouter 硬编码是 **notes-file 查找别名**(qnaigc→qiniu.md),与 provider 分类身份是两回事,留待 W3-A provider 配置文件统一(届时 alias 表 + notes-key 一起入配置)。

### W3-C · evidence 匹配身份统一(D11)
- [ ] **W3-C.1 (red)** 测试:本地存/wire 传/回填三处用同一"匹配身份"派生(endpoint=base_url+protocol、route=+model;不含 method)。
- [ ] **W3-C.2 (green)** 抽一个匹配身份函数,三处共用;回填匹配从 host+model 收敛到统一键。

### W3-D · 社区贡献开放:allowlist→安全闸(D13)
- [x] **W3-D.1/.2 (red→green)** 移除 `PUBLIC_PROVIDER_HOST_ALLOWLIST` 固定准入名单,换 `is_safe_to_publish` 安全闸:公网 DNS host / 公网 IP 可发布(wavespeed.ai 这类新 provider 现可贡献);私有(RFC1918/裸私有IP)/ LAN(`.local/.internal/.lan/.home/.corp/.intranet`)/ loopback / 单标签 host / RFC6761 保留 TLD(`.test/.example/.invalid/.localhost`)/ 带 userinfo 的 URL 一律不发布。api_key 永不外传不变(脱敏字段集没动)。
  (T7 细则定稿如上;`is_public_allowlisted` + 常量 + `build_upload_record` 的 allowlist 参数全删,redaction 测试改成参数化安全闸覆盖)。门禁:84 community/evidence pytest · ruff · mypy 全绿。

---

## 阶段二(后置)— 运行期回写 + 探测动画

- [ ] **S2-A** engine 真实调用结果经事件总线回流 studio 写归一态(R-D5;gateway 不直接写盘,T3 事件设计)。
- [ ] **S2-B** 逐模型探测进度事件 → 模型标签 testing 动画(复用 `.api-route-tag-border-flow`)+ 测试期自动展开模型列表(R-G2)。

---

## 待用户拍板才动的点(已在 design 待定项)
- T6 PSL 选型(W3-B.2 前)· T7 安全闸细则(W3-D 前)· T9 key/url 失败归因(W2-C 前)——均实现时定,遇真分叉再问。
