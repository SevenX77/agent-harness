---
spec: studio-api-keys-redesign
status: Drafting
date: 2026-05-18
baseline_branch: baseline/v2.1-2026-05-18
baseline_worktree: /home/sevenx/coding/baseline-v21/
---

# Tasks — Studio API Keys Redesign

实施分两条并行流:

- **apps master** 跑 frontend (F1-F6), 在 `/home/sevenx/coding/baseline-v21/apps/studio/frontend/`
- **parent master** 跑 backend (B1-B5), 在 `/home/sevenx/coding/baseline-v21/apps/studio/backend/`

详细设计见 [`design-frontend.md`](./design-frontend.md) / [`design-backend.md`](./design-backend.md).

**Owner phrasing 约定 (C5)**: 本 spec 用 "**apps master 派 a1 主实施 / a3 备援**" 等结构化短语, 跟 master 调度层 (apps / parent) 跟具体 ccb agent (a1 codex / a3 claude) 解耦. master 之间分工边界由 user 拍定 (apps master = frontend, parent master = backend); master 内部派 ccb agent 用 SOP-01 §4 测试分工 (a1 主力编码 / a3 e2e + 备援).

---

## Frontend Tasks (apps master 实施)

### F1 — UI 重构: 砍 VENDORS 分组 + 拍平 ProviderRow + ApiKeyInput

**Scope**: `apps/studio/frontend/src/components/studio/SettingsPage.tsx`, 新增 `components/studio/ApiKeyInput.tsx` / `components/studio/ProviderRow.tsx`

- 删除 `VendorId` / `VendorEntry` / `VENDORS` / `VendorGroup` / `DISABLED_PROVIDER_EDITING` / `DISABLED_ROLE_EDITING`
- ApiKeysTab 改 flat list 渲染
- 新 `ApiKeyInput` 组件: focus-aware mask, onChange 拦截方案 (C2 fix, 见 design-frontend §4.2)
- ProviderRow 拆到独立文件
- 视觉按 `.kiro/specs/studio-uikit-redesign/tokens.md` semantic token
- `ProviderType` Literal **保留 4-enum (含 `openai_compatible`)**, 砍 enum 留到 F3 联调 (跟 backend B1 同步)

**依赖**: 无 (frontend-can-do-now)

**Owner**: apps master 派 a1 主实施, a3 review + 主控亲跑 Playwright 视觉验证

**测试**:
- TypeScript 编译过
- Vitest unit: ApiKeyInput onChange 拦截方案 (mask paste / 退格 / 全选删除 / Eye toggle 5 个 case)
- Vitest unit: useDebouncedCredentialsSave fake timers 验证
- Playwright smoke: 旧 baseline backend 跑通, vendor 分组消失, ProviderRow 显示真实 mask

---

### F2 — Add Provider + UUID + Debounce Save Hook

**Scope**: `apps/studio/frontend/src/hooks/useDebouncedCredentialsSave.ts` (新增), `components/studio/SettingsPage.tsx` Add 按钮 + state 管理

- "+ Add Provider" 激活, 点击追加默认 OpenAI 协议 row, 生成 UUID `provider_code` (`crypto.randomUUID()`)
- 新 hook `useDebouncedCredentialsSave` (300ms debounce, 失败 toast.error)
- 替换现有 Save 按钮触发为自动 debounce save
- PUT body 仅含 `ProviderCredentialWrite` 6 字段 (B3 single-write 规则, 不含 Test 持久化 5 字段)

**依赖**: F1 完成

**Owner**: apps master 派 a1 主实施, a3 review

**测试**:
- Vitest unit: hook fake timers 验证 debounce + payload 字段筛选正确 (不含 Test 字段)
- Playwright smoke: 点 Add 后行出现, 改字段后 300ms PUT 触发 (mock backend)

---

### F3 — CRUD 联调 + ProviderType 4→3 收敛

**Scope**: `apps/studio/frontend/src/api/llm.ts`, `components/studio/SettingsPage.tsx`, e2e 测试

- 跟 backend 联调验证 PUT 全量替换语义 (delete = 不发该 provider, 重新 GET 列表里消失)
- 验证 PUT 接受任意 UUID provider_code (新 add)
- 验证 api_key 空字符串保留旧值 (改 title 不清 key)
- 验证 vendor_hint / title 字段往返一致
- **ProviderType Literal 收敛 4→3** (砍 `openai_compatible`): 跟 backend B1 同步 ship, LlmRoles 引用 wavespeed 的 model 自动 migrate 显示 vendor_hint = "OpenAI compatible"
- 删除 F1 临时保留的 4-enum 兼容代码

**依赖**: backend B1 + B2 + B3 ship

**Owner**: apps master 派 a3 主实施 (e2e), a1 review + 主控亲跑 Playwright e2e 验证

**测试**:
- e2e: Add → 改字段 → refresh → 字段持久化
- e2e: Delete provider → refresh → 真消失
- e2e: 改 title 中 → PUT 时 server 端 api_key 不清
- e2e: PUT body 含 openai_compatible → 后端拒收 (422)

---

### F4 — Test UI 改 Toast + Persistent Badge + isTesting + 错误代码翻译

**Scope**: `components/studio/ProviderRow.tsx` Test 按钮交互, 新增 `lib/llm-error-messages.ts`

- 移除 inline Alert
- toast.loading / success / error 三态, id = `test-${provider_code}` 防多 toast 堆叠
- `isTesting: boolean` UI 临时态 (B1) — Test 进行中 badge 显示 spinner, Test 按钮 disabled
- 持久化 badge 显示 `last_test_status` (绿/红/灰点 + 时间戳)
- `translateErrorCode(error_code)` 翻译人话 (C3 v2.1 中文 hardcode, 含 `missing_api_key`)

**依赖**: F1 完成 (UI 重构基础)

**Owner**: apps master 派 a1 主实施, a3 review

**测试**:
- Vitest unit: translateErrorCode 各 vendor error_code 翻译正确 (含 missing_api_key)
- Playwright smoke: 点 Test → toast.loading → 等响应 → badge 切换状态 + isTesting=false; 第二次 Test 同 provider 不堆叠 toast

---

### F5 — 消费 ProviderTestResponse 新字段

**Scope**: `api/llm.ts` 扩 `ProviderEntry` 类型 (对应 backend `ProviderCredential` 8 新字段), ProviderRow + state 持久化 available_models / last_test_*

- TypeScript 类型加 `ModelInfo` / `ModelCapabilities` / `TestStatus` (不含 testing)
- Test 响应回写到本地 state (跟后端 `ProviderCredential` 同步)
- Refresh 后 badge / available_models 从 `GET /api/llm/credentials` 读取重显

**依赖**: backend B4 ship

**Owner**: apps master 派 a3 主实施 + 主控亲跑 e2e 视觉验证

**测试**:
- e2e: Test 成功 → refresh → badge / available_models 持久化重显
- e2e: Test 失败 (故意错误 key) → badge 显示红点 + error_code; refresh 后红点仍在

---

### F6 — LlmRolesTab availability filter

**Scope**: `components/studio/SettingsPage.tsx` LlmRolesTab model dropdown

- `getModelAvailability()` helper
- dropdown 项前缀 "⚠️ Unavailable" + disabled
- fallback 链跳过不可用 model
- 不动 `RoleEntry` / `RoleModelEntry` 数据模型

**依赖**: F5 完成

**Owner**: apps master 派 a1 主实施, a3 review

**测试**:
- e2e: provider Test 失败 → LlmRoles 该 provider 引用的 model 显示 Unavailable
- e2e: 删 provider → 引用 role 显示 Unavailable

---

## Backend Tasks (parent master 实施)

### B1 — ProviderType Literal 收敛 + DEFAULT_BASE_URLS 含 /v1 后缀 + yaml migration

**Scope**: `apps/studio/backend/app/models/llm_config.py:31-36` + `app/services/llm_provider_test.py:11-30`, 新增 `app/services/migrations.py`

- 两处 `ProviderType = Literal[...]` 同步砍 `openai_compatible` (4 → 3)
- `DEFAULT_BASE_URLS` 改成含 `/v1` 后缀的版本 (跟 frontend 推荐值对齐)
- `_request_provider_models` 拼接逻辑改 `f"{base_url.rstrip('/')}/models"`, 不重复加 `/v1`
- 新增 `migrate_provider_type_value` 给 yaml load 时迁移

**Owner**: parent master 派 a1 主实施, a2 audit + a3 review

**测试**:
- Unit: `ProviderType` 解析 3 个合法 / openai_compatible 报 ValidationError
- Unit: `migrate_provider_type_value("openai_compatible") == "openai_compatible"`
- Unit: 两处 Literal 值完全一致 (assert 一致性 test 避免漂移)

---

### B2 — ProviderCredential 扩 8 字段 + 新增 ModelInfo / Capabilities / TestStatus

**Scope**: `apps/studio/backend/app/models/llm_config.py`

- `ProviderCredential` 加 `title` / `provider_type` / `vendor_hint` 元数据字段
- `ProviderCredential` 加 `last_test_status` / `last_test_at` / `last_test_message` / `last_error_code` / `available_models` 5 Test 字段
- 新增 `ModelInfo` / `ModelCapabilities` Pydantic 模型 (含 `extra="forbid"`)
- 新增 `TestStatus` Literal (7 个值, 不含 testing)

**依赖**: B1

**Owner**: parent master 派 a1 主实施, a3 review

**测试**:
- Unit: schema 接受新字段, 拒收 extra (extra="forbid" 验证)
- Unit: 旧 `~/.studio/llm_credentials.json` 仅 3 字段加载, 新字段填默认值 (last_test_status="untested", available_models=None)

---

### B3 — PUT /api/llm/credentials 改全量替换 + provider_code 不可变 + api_key 空保留 + Test 字段单向写

**Scope**: `apps/studio/backend/app/routers/llm.py` PUT handler (L85-107)

- 改 PUT 为全量替换语义: client 发完整 providers list, server 替换 (delete = 不发)
- `provider_code` 不可变: 由 frontend UI 保证 (input 不暴露), backend 不强制 reject 但不开放修改入口
- api_key 空字符串保留 server 端旧值 (修复 baseline L97 bug)
- Test 持久化 5 字段 PUT body 不接受 (single-write 规则, 由后端 §3.2 保证)
- 扩 `ProviderCredentialWrite` schema 加 title / provider_type / vendor_hint Optional 字段
- response 返 api_key 明文 (round 2 反转, 见 requirements.md round 2 段)

**依赖**: B1, B2

**Owner**: parent master 派 a1 主实施, a3 review + a2 audit 全量替换 cutover 风险

**测试**:
- Integration: PUT 新 UUID provider 200, 响应 **api_key 明文返**
- Integration: PUT 现有 provider 空 api_key → **api_key 仍是旧值** (旧 key 未清空)
- Integration: PUT 不发某 provider → 整个 provider 消失 (delete)
- Integration: PUT body 含 last_test_status="ok" → server 端不写入 (single-write)
- Integration: PUT response 含 api_key 明文字段

---

### B4 — POST /api/llm/providers/test 扩响应 + 3 provider 实现 + 原子回写

**Scope**: `apps/studio/backend/app/routers/llm.py` POST handler + `app/services/llm_provider_test.py` 新增 `ping_provider_extended` + `app/services/copilot_test.py` 异常加 `error_code` + 新增 `app/services/llm_capability_table.py`

- 入口加 missing_api_key 前置校验 (C4) — 空 key 直接返 invalid_key + error_code="missing_api_key"
- 新 `ProviderTestResponse` 含 `available_models` + `error_code`, 保留 `model_seen` 向后兼容
- `_Unauthorized` / `_RateLimited` / `_QuotaExceeded` / `_NetworkError` 4 异常加 `error_code: str | None` 属性
- 增强 `_raise_for_status` 解析 vendor body 提取 error_code (按 §5.1-5.3 表)
- `ping_provider_extended` 替代 `ping_provider`, 返完整 model 列表
- `_extract_model_ids` 区分 Gemini (`models[].name` 剥 "models/" 前缀) vs Anthropic/OpenAI (`data[].id`)
- `CAPABILITY_TABLE` + `STATIC_FALLBACK_MODELS` lookup (新文件 `llm_capability_table.py`)
- Test 完成后 `_persist_test_outcome` 用 `_credentials_lock` 原子 patch 5 字段 (不动其他)

**依赖**: B1, B2

**Owner**: parent master 派 a1 主实施, a3 review

**测试**:
- Unit: 3 个 provider_type happy path (mock httpx 200, 验证 available_models 填充 + capability lookup 正确)
- Unit: 401 invalid_key / 429 rate_limited / 429+insufficient_quota / 5xx network_error / timeout 各 error path
- Unit: missing_api_key (api_key="") 不发 HTTP 直接返
- Unit: static fallback union (Anthropic 返空列表, fallback 加 5 个 model)
- Integration: POST /api/llm/providers/test 成功 → GET /api/llm/credentials 看到回写的 last_test_*
- Integration: Test + PUT 并发 → 两个写不互相覆盖 (B4 race scenario test)

---

### B5 — 集成 + 单元 test 全更新

**Scope**: `apps/studio/backend/tests/services/` + `apps/studio/backend/tests/routers/`

- 删除测旧 `openai_compatible` 的 test (如有)
- 加 migrations / capability_table / provider_test / llm router 新 test 覆盖

**依赖**: B1-B4

**Owner**: parent master 派 a1 主实施 + a2 audit test 覆盖率

**Why**: 按 cutover discipline 铁律 (`~/.claude/rules/05-sop-cutover-discipline.md`), schema 改 + test 同步必须**同一个 PR**, 不可分拆.

---

## 实施顺序 + 协同 (B3 cutover 协调)

```
                    Backend (parent master)              Frontend (apps master)
                    ─────────────────────                ──────────────────────
Phase 1 (并行):     B1 + B2 起草 PR (baseline branch)    F1 + F2 + F4 起 PR (baseline branch)
                    [4-enum → 3-enum 砍, 8 字段扩]       [保留 4-enum 兼容]
                                                          F1 → F2 → F4 顺序接力
Phase 2 (backend ship to baseline):
                    B3 + B4 + B5 ship                    F1-F2-F4 frontend PR merge to baseline
                    ✓ backend PR merged to baseline
Phase 3 (联调 + cutover 收敛):
                                                          F3 + F5 测 backend 联调
                                                          F3 同步把 ProviderType 4→3 收敛
                                                          F6 收尾 (依赖 F5)
                                                          Frontend 第二个 PR ship to baseline
Phase 4 (v2.1 → main cutover, user 拍板时机):
                    整段 v2.1 → main cutover PR (含 backend + frontend 所有合并)
                    user 验证 manual smoke 11 条全过, 单一 PR squash merge to main
```

### B3 ordering 修复说明

跟 parent master review B3 反馈一致 — frontend F1 + F2 + F4 落实施时**不动 `ProviderType` 收敛** (保留 4-enum), 因为 backend B1 同步在改 enum, 如果 frontend 先砍 enum 会跟 baseline backend 跑不通 (PUT 4-enum 报 422). 把 enum 收敛归到 frontend F3 联调 PR — 那时 backend B1+B2+B3 已 ship, frontend 跟 backend 一起切换到 3-enum.

### Branch 策略 (revised)

- **Phase 1-3 各 PR 都打到 `baseline/v2.1-2026-05-18` 分支**, 不直接打 main
- `apps-master/api-keys-frontend-v2.1` — apps master 的 frontend 第一个 PR (F1+F2+F4)
- `parent-master/api-keys-backend-v2.1` — parent master 的 backend PR (B1-B5)
- `apps-master/api-keys-frontend-v2.1-cutover` — apps master 的 frontend 第二个 PR (F3+F5+F6)
- 各自 review + merge **到 baseline branch**
- **Phase 4**: 整段 v2.1 → main cutover PR 由 user 拍板时机统一推 (不在本 spec scope)

---

## 风险跟踪

| 风险 | 缓解 | Owner |
|---|---|---|
| Anthropic /v1/models 返回不全 | static fallback union (design-backend §4.5) | parent master B4 |
| api_key 空字符串误清 (baseline bug) | PUT 改 `if incoming.api_key else existing.api_key` + 显式测试 (B3) | parent master B3 |
| ProviderType 双定义漂移 | B5 加一致性 assert test | parent master B5 |
| PUT 全量替换 client 兼容 | F3 同步 ship, 不允许旧 client + 新 backend 长期共存 | apps master F3 |
| Test + PUT race 互相覆盖 | 后端原子写 (option a, B4) + PUT body 不带 Test 字段 (B3 single-write) | parent master B3+B4 |
| focus 切换 rerender jank | v2.1 不优化 (< 20 行性能 OK) | apps master F1 |
| mask 状态游标位置不直观 (C2 修后) | 用户改 key 流程触发 focus 即可看到真实值; v2.5 视用户反馈优化 | apps master F1 |
| baseline legacy hardcoded provider_code 兼容 | 不强制迁移, 任意 string ≤ 64 chars OK | parent master B3 |
| ProviderType 4→3 cutover 时点 | F3 跟 B1 同步 ship 收敛 | apps F3 + parent B1 |

---

## Done Criteria

按 [`requirements.md §4 验收标准`](./requirements.md#4-验收标准) 11 条 manual smoke + Playwright e2e 全过, 主控亲眼跑 Playwright 验证视觉对齐 baseline 规范, 才能跟 user 报 done.
