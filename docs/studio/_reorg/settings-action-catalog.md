# Skill Studio `00_settings` — 用户 UX 动作目录(全 tab,待 PM 确认)

> **✅ 已迁移(2026-06-03)**:全部 65 atom action 已折入 [`../mvp1/01_workflows/00_settings-ux-spec.md`](../mvp1/01_workflows/00_settings-ux-spec.md) **§7**(现状审计 × 能力·区域映射,含 Stage 0 壳层 + Stage 1 General 两块叙事未覆盖部分)。**本文保留作迁移源 / 可追溯,不再更新,以 ux-spec 为准。**

> 来源: workflow `apikeys-action-catalog`(API Keys)+ `settings-ux-action-catalog`(General/LLM Roles/Copilot/壳层), 各经对抗校验抽检 file:line(分叉/status 判定全部坐实, 仅 3 处 copilot 文案小修已并入), 2026-06-02。
> 用途: 把 settings 旅程**按用户 UX 心智顺序**拆到最细交互动作, 每动作映射 能力(细 slug)/ 区域 / 实现 / 现状问题。确认后并入 [`../mvp1/01_workflows/00_settings.md`](../mvp1/01_workflows/00_settings.md) §3。
> 三维归属: 能力 `studio-settings`(下列细 slug 是**动作级**功能名, 都 roll-up 到这一个注册表能力)· 区域 `settings` · 平台 `gateway`(Python sidecar)。

**状态图例**: ✅ live(接线可用) · 🟡 placeholder(桩/占位) · 🔌 orphan(组件已建·未挂载) · 🛠 backend-only(后端有·前端无 UI) · 🎯 target-design(仅设计) · ⚠️ 冲突/问题(stale-code / 契约违反 / 潜伏 bug)

**用户 UX 主流程(一句话)**: 在工作区点 Toolbar 的 Settings → 面板盖在画布上(左侧文件树/右侧 Copilot 仍在, 工作区不卸载)→ 在 General 配「我是谁/产物发哪」→ API Keys 配 provider 凭证 → LLM Roles 把角色映射到模型兜底链 → Copilot 配助手 → 一切即填即存 → 点 X 关闭回工作区。

---

## Stage 0 — 进入 Settings(壳层)〔区域 `settings:shell`〕

| # | 动作 | 能力 | 区域 | 状态 |
|---|---|---|---|---|
| 1 | 点 Toolbar 的 Settings 图标 → 打开面板(center overlay 盖画布, **不卸载工作区**) | open-settings-overlay | shell | ✅ 注:非真 modal, 左右栏仍挂载可交互, 无 backdrop/focus-trap |
| 2 | 数据未到时显示骨架屏(available models 巨长列表是 §11 NFR 首要场景) | settings-skeleton | shell | ✅ ⚠️ 无壳层级骨架, 完全下放各 tab 自管 |
| 3 | 在 General / API Keys / LLM Roles / Copilot 四 tab 间切换(切到才懒加载该 tab 数据) | settings-tab-switch | shell | ✅ |
| 4 | 改动后看右上保存徽章(Pending/Saving/Saved/Failed) | settings-save-badge | shell | ✅ ⚠️ 三 tab 各画各的, 顶栏无全局保存态 |
| 5 | 外部改 credentials 文件 → WebSocket `registry_changed` 自动刷新 | ws-registry-refresh | shell | ✅ ⚠️ 空 catch `// ignore` 静默, 无重连 |
| 6 | 外部改 roles 文件 → WebSocket `roles_changed` 自动刷新 | ws-roles-refresh | shell | ✅ ⚠️ 没开过 LLM Roles tab 则事件被吞掉 |
| 7 | 点顶栏 X 关闭 Settings 回工作区画布 | close-settings-overlay | shell | ✅ 注:无未保存确认, in-flight PUT 仍落地 |
| 8 | (Settings 打开时)点 Header Home → 连带关 Settings + 退回首页 | home-closes-settings | shell | ✅ 注:与 X 是两条语义(Home 还卸载工作区) |
| 9 | 某 tab 渲染崩溃 → 该 tab 错误兜底卡 + Retry(不白屏) | settings-error-boundary | shell | ✅ ⚠️ 只包了 LLM Roles/Copilot, General/API Keys 没包 |

---

## Stage 1 — General(身份与产物路径)〔区域 `settings:general`〕

| # | 动作 | 能力 | 区域 | 状态 |
|---|---|---|---|---|
| 10 | 改 Studio User ID | studio-user-id | general | ✅ |
| 11 | 填 Gitea Host(**publish 硬依赖**, 缺则 sync 直接报错) | gitea-host | general | ✅ |
| 12 | 手填默认 skills 目录路径 | skills-dir-manual | general | ✅ |
| 13 | 点 Choose 弹 OS 文件夹选择器(**本节点唯一走 native/Rust 的本地操作**) | skills-dir-native-picker | general | ✅ 注:web 模式仅 toast "Desktop only" |
| 14 | 点 Reset 还原默认目录(回退到 runtime 默认 `configDir/Skills`) | skills-dir-reset | general | ✅ 注:runtime config 不可用时按钮 disabled |
| 15 | 任意字段即填即存(300ms debounce `PUT /api/settings`)+ 保存徽章 | appsettings-save | general | ✅ |

> **机制**: 三字段一起整体 PUT(无字段级 PATCH), `GET/PUT /api/settings`→`app_settings.json`。Gitea host 只是 publish 鉴权链的一半(token/凭据走另一套 credentials), 选目录是 settings 里唯一的 Rust 本地操作。

---

## Stage 2 — API Keys(Provider 凭证)〔区域 `settings:api-keys`〕

> 轨: **官**=official 官方厂商 / **三**=third-party 第三方兼容网关 / **共**=两者共有。

| # | 动作 | 轨 | 能力 | 状态 |
|---|---|---|---|---|
| 16 | 进 tab → 加载凭证 + 逐个 `GET secret` 把 `'**********'` 换回真值 | 共 | secret-hydration | ✅ |
| 17 | 渲染拆成 official 区(固定 5 厂商预渲染)+ third-party 区(用户自增) | 共 | provider-partition | ✅ |
| 18 | official 只能填 Key;Base URL/Protocol 被强制 canonical 默认 + 隐藏, 不可增删改名 | 官 | official-key-only | ✅ |
| 19 | 点 `+ Add Provider` → 弹框填名 → 建 `custom-{uuid}` 草稿 | 三 | tp-add-provider | ✅ ⚠️ 现状两步(弹框只收名), 目标是 inline 一次填全 |
| 20 | 填 name / base_url / protocol / api_key | 三 | tp-credential-edit | ✅ |
| 21 | 改 API Key(两类共用输入框;改后旧测试结果失效→badge 回 untested) | 共 | credential-key-edit | ✅ |
| 22 | Eye/EyeOff 切明文/掩码 | 共 | secret-mask-toggle | ✅ ⚠️ 切了 native `password` type, 违 round3 契约(应永 text + CSS mask) |
| 23 | Copy 复制 key 到剪贴板 | 共 | secret-copy | ✅ |
| 24 | 点 `Test` → **异步批量 job**(750ms 轮询进度)拉全厂商模型目录, endpoint 提 verified | 官 | official-test-job | ✅ 后端硬门禁 `provider_kind!='official'` 拒 |
| 25 | 点 `Get Models` → **同步单次** models-list 发现;路由停 unverified_manual | 三 | tp-getmodels | ✅ |
| 26 | 'Endpoint test' 填单 model id → Test 探测该 model | 三 | tp-model-probe | ✅ |
| 27 | 'Manual model probing' 加多个 model id 批量探测(后端按 kind 分叉) | 共 | manual-model-probe | ✅ 官→多候选 VerifiedProfile / 三→单次 `_probe_model` 写死 text-only |
| 28 | (自动)Manual panel 拉 `notable-models` 候选作 input 建议 | 共 | notable-models | ✅ 有 note 文件即返, 不分官/三 |
| 29 | `⋮` → Rename / Delete(official 不可改名/删) | 三 | tp-rename-delete | ✅ 删除二次确认 toast |
| 30 | 状态投影:third-party 顶层徽章(按参数指纹) / official 每 route 彩色 Tag(后端权威) | 共 | test-status-projection | ✅ |
| 31 | 刷新后从 registry 恢复 key/状态/Available Models | 共 | registry-restore | ✅ |

> **官/三 核心区别**:official 不是用户选的, 是后端按 `endpoint_id` 白名单(anthropic/openai/gemini/deepseek/ark-official)钉死的 `provider_kind`;前端镜像成固定 5 厂商。official 独占①异步批量 test job ②多候选 `VerifiedProfile` 真探 ③富能力来源;third-party 只有单 model 一次性探测 + 写死 text-only。两者共享 models-list 自动发现, 唯一分叉:official 发现到模型即把 endpoint 提 `verified`, third-party 停 `unverified_manual`。
> **🔌 孤儿/未接线**: `OfficialVendorSelect`(官方厂商下拉)、`AddProviderForm` 的 createBlank/derive helper、`ProviderDeleteButton`(定义未渲染)、`probeRoute`→`POST /routes/{id}/probe`(此 tab 未接线, 🛠 backend-only)。

---

## Stage 3 — LLM Roles(角色 → 模型兜底链)〔区域 `settings:llm-roles`〕

| # | 动作 | 能力 | 状态 |
|---|---|---|---|
| 32 | 进 tab → 加载 Graph Agent 角色卡(滤掉 copilot_)+ 右侧 Available Models 侧栏 | role-list-load | ✅ |
| 33 | 点 `Add Graph Agent Role` → 弹框命名 → 新建空角色 | role-create | ✅ 注:允许建无模型的空壳角色 |
| 34 | 侧栏搜模型(按 model/provider/id 多词匹配) | available-models-search | ✅ |
| 35 | 展开模型卡看各 provider 状态(Ready/Untested/Cooling Down) | available-model-provider-states | ✅ ⚠️ needs_setup/off 的 provider 被静默过滤, 看不到为何缺失 |
| 36 | 拖模型进角色 → 自动挂 model group + 默认选 Ready+Untested 在前 | role-model-map-drag | ✅ |
| 37 | 拖动调多个 model 之间的兜底序(谁先试) | role-model-reorder | ✅ active_model 永远同步为第一个 |
| 38 | 拖 provider tag 调该模型的 provider 兜底序 | role-provider-reorder | ✅ |
| 39 | `Add provider` 补加 / 垃圾桶移除某 provider | role-provider-add/remove | ✅ |
| 40 | 删整个 model group | role-model-remove | ✅ |
| 41 | 切 `Model Fallback` 开关(关则只用第一个 model) | role-model-fallback-toggle | ✅ |
| 42 | 切 `Thinking Preferred`(偏好推理模型) | role-thinking-intent | ✅ ⚠️ 后端还支持 `required` 档, 前端只 off/preferred 两态无 UI |
| 43 | 填 `Output Token Target` / 开 `Use max` | role-output-token-intent | ✅ ⚠️ 前端固定 downgrade=allow, 后端的 block/warn 策略无 UI |
| 44 | 看 `Route max token` 摘要 | role-output-limit-summary | ✅ |
| 45 | 悬停状态灯看 role-match(Can Run/Limited/Blocked)+ 诊断 | role-route-status-light | ✅ role_fit 来自后端 materialize report |
| 46 | 点 `Test` → 后端 job 逐 route 探测兜底链, 实时回填灯 + downgrades | role-test | ✅ ⚠️ 结果易失(切 tab 丢);`RoleTestResultPanel` 已写未挂载, 看不到 downgrades 全文 |
| 47 | Test 失败红色错误条(未保存先拒测) | role-test-error-banner | ✅ |
| 48 | `⋮` → Rename / Delete 角色 | role-rename/delete | ✅ |
| 49 | `Add Model Bundle`(可复用模型束, 跨角色) | model-bundle-create | ✅ |
| 50 | 拖模型进束 / 束内编辑(复用角色卡编辑器, 束不可嵌套束) | model-bundle-edit | ✅ ⚠️ 束卡不显状态灯、无 Test 按钮, 无法单测束 |
| 51 | 把已建束整体拖进角色作一组兜底 | bundle-as-role-source | ✅ ⚠️ 快照复制, 束后续改动不同步到已拖入的角色 |
| 52 | 束 `⋮` → Edit 改名 / Delete 删束 | model-bundle-rename-delete | ✅ |
| 53 | (被动)其它窗口改 roles / 窗口聚焦 → 自动重投影刷新 | role-projection-refresh | ✅ |

> **机制**: 角色存**结构化** `model_groups[]`(canonical_id + 各 provider 的 route), 后端 `materialize_role` 物化成 gateway 消费的**平铺** `fallback_chain`;前端作者看 Group, 引擎跑链。物化时跳过 needs_setup/off、cooling_down 记 warning、只把 fit 的 route 入链 —— UI 测试态与引擎编排同一套判断。
> **测试 SSOT 落差(头号)**: role 测试结果在后端 job 内存字典(`_role_test_jobs`)是 SSOT, 但前端 `roleTestStates` 是组件易失 state, **切 tab 即丢**;只有静态 `role_fit` 持久。
> **🔌 孤儿/🛠 backend-only**: `useRoleTestChainRunner` hook、`RoleTestResultPanel`、`RoleFitBadge`、`ProviderStateBadge`、`CoolingDownCountdown` 仅测试引用未挂载;`PUT /llm/roles/{name}`(单角色, 带 materialize)前端不调(只用 bulk PUT)。

---

## Stage 4 — Copilot(助手配置)〔区域 `settings:copilot`〕

> ⚠️ 现状定性:**配置外壳真接线, 内里大量是 mock/桩/假测试**。

| # | 动作 | 能力 | 状态 |
|---|---|---|---|
| 54 | 进 tab → 标题 + "Backend Integration" 徽章 + 角色卡(无数据先骨架屏) | copilot-tab-shell | ✅ ⚠️ 徽章是写死装饰, 不反映真实连接 |
| 55 | 看 copilot 角色卡(Opus 4.7 / DeepSeek V4, Built-in/Third-party 徽章) | copilot-role-list | ✅ ⚠️ 卡片元数据由前端硬编码模板/启发式推导, 与后端 role 语义脱节 |
| 56 | (首次无角色)自动填 3 张种子卡 | role-seed-fallback | 🟡 ⚠️ 前端现造, 默认 props 还是 mock 数据 |
| 57 | 看每 route SDK 状态灯(N/M SDK Ready) | route-sdk-status-badge | 🟡 ⚠️ 只按 ui_state==ready 粗映射, 非真测过 SDK |
| 58 | 点 `Test` → 逐 route 验 SDK 工具调用(testing→ready/unsupported) | copilot-role-test | ✅ ⚠️ **假测试**:探针走 `AsyncAnthropic`(发 weather 工具调用), 真实 copilot 跑 `ClaudeSDKClient` —— 测的 SDK ≠ 跑的 SDK |
| 59 | 拖动调 route 回退优先级 | route-fallback-reorder | ✅ ⚠️ 运行侧 `_resolve_copilot_route` 只取首条, 重排未必生效 |
| 60 | `Add route` 追加兼容 route / 垃圾桶删 route | route-fallback-add/remove | ✅ ⚠️ 可选 route 靠前端启发式(provider_type/methodId)过滤 |
| 61 | model-group 行的 Remove 按钮 | model-group-remove | 🟡 ⚠️ disabled 写死且无 handler, 纯占位点不动 |
| 62 | 点 `Add model` 新建第三方 copilot 角色草稿卡 | copilot-role-add | ✅ ⚠️ key 命名触发后端分流误判风险(见下) |
| 63 | 在空卡下拉选 Model group → 变可配置角色 | copilot-config-model-group | ✅ ⚠️ 选 group 后 key 变 modelGroupId(无 `copilot_` 前缀) |
| 64 | 删第三方 copilot 角色(确认 toast) | copilot-role-delete | ✅ 注:built-in 卡无删除按钮;走整表 PUT 覆盖 |
| 65 | (期望)改完看保存中/已保存反馈 | copilot-save-status | ⚠️ stale-code:`void saveStatus; void error;` 直接丢弃, 改完无任何反馈 |

> **🐛 潜伏 bug(接线必修)**: 新建 copilot 角色 id 用 `copilot_custom_N`, 但选了 model group 后 `selectModelGroup` 把 role key 改成 `modelGroupId`(如 `claude-sonnet-4.7`, **无 `copilot_` 前缀**);后端 `put_llm_roles` 的 copilot/graph-agent 分流只认 `copilot_` 前缀 → 会把它**误判为 graph-agent 角色错存**。
> **🛠 后端有·前端无**: 专用 `POST /api/copilot/roles/{role}/test-sdk` 端点前端从未调(且最终仍落同一 AsyncAnthropic 假探针);真实对话 `ws`→`ClaudeSDKClient` 属 skill 工作台不在设置页;`dispatch_copilot` 仍 501 占位。
> **mock 来源**: `mock-copilot-data.ts` 的 `defaultCopilotModelGroups/defaultCopilotCredentials` 是默认 props;`copilot-role-state.ts` 全套 + `mockCopilotRoles` 静态数组已是死代码(仅 test 引用)。

---

## 贯穿性问题(cross-cutting)

1. **测试 → SSOT 落差(头号工程)**: provider 测试(API Keys)与 role 测试(LLM Roles/Copilot)后端都有持久化/job, 但**前端仍有易失副本, 切 tab/刷新即丢**。目标(08-orch-test-status-ssot)是删前端易失层、完全以后端投影为准。这是 settings 接线的主工程。
2. **写入归属 = gateway Python, 永不 Rust 化数据层**: credentials/roles 走 `~/.studio/` + `routers/llm.py`(经 storage seam, 预留 user_id)。settings **不适用** D12「写全量 Rust」(那是 skill 源文件), 唯一 native 操作是「选默认 skills 目录」(`select_directory`→Rust `pick_folder`)。
3. **孤儿组件群**: API Keys 4 个 + LLM Roles 5 个 + Copilot 的 `copilot-role-state` 全套 + 多个 backend-only 端点。需逐组判定:计划待接线(保留)vs 历史死代码(清理)。
4. **Copilot 整体桩程度最高**: mock 数据 + 假测试(SDK 不一致)+ save 无反馈 + 分流误判 bug + 占位按钮。

---

## 最需要你拍的点(open questions)

1. **测试态 SSOT**: role test + provider test 结果是否要落盘/回填(删前端易失层)?这是接线主工程, 但量大 —— MVP 范围做到哪?
2. **Copilot 整 tab 做到哪一档**: 现状 = 配置壳真 + 内里多桩。MVP 先做「配置 + 真测试(修假测试)」, 还是先只保配置、测试/状态延后?
3. **Copilot 分流 bug(#62/63)**: 选 group 后 key 丢 `copilot_` 前缀→后端误判存错。确认这是 bug、接线时必修。
4. **role intent 前端缺口(#42/43)**: thinking `required`、token downgrade `block` 后端已实现但无 UI。补 UI 还是先 backend-only?
5. **Available Models 静默过滤(#35)**: needs_setup/off 的 provider 在侧栏看不到。要不要显式展示「为何缺失」?
6. **Model Bundle 语义(#50/51)**: 拖进角色是快照复制(束改不同步)+ 束卡无状态灯无 Test。这是目标设计还是缺口?
7. **API Keys 7 个现状 vs 目标差**(上一轮已列, 仍待拍): Manual probing 端点方案 B / Eye-mask 契约 / 两步添加 vs 一次填全 / Protocol 手选去留 / 4 个孤儿 / base_url 默认值口径 / 状态枚举术语(`ProviderUiState` vs legacy `TestStatus`)。
8. **壳层 NFR(#1/2/4/5)**: Settings 无壳层级骨架/就绪 gate(各 tab 自管)、WS 空 catch 无重连无日志(违 logging 铁律)、无全局保存徽章。维持现状还是补齐?
9. **孤儿组件群处置**: 计划待接线 vs 历史死代码该清 —— 需逐组判定。
