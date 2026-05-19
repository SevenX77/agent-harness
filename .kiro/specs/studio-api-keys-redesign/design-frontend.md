---
spec: studio-api-keys-redesign
side: frontend
implementer: apps master
status: Drafting
date: 2026-05-18
scope:
  - apps/studio/frontend/src/components/studio/SettingsPage.tsx
  - apps/studio/frontend/src/api/llm.ts
  - apps/studio/frontend/src/hooks/  (新增 hook)
linked_specs:
  - ./requirements.md
  - ./design-backend.md
  - ./research.md
  - ./tasks.md
linked_docs:
  - docs/llm-providers/
---

# Design — Frontend Side (apps master 实施范围)

## 0. 边界声明

本设计 doc 描述 `apps/studio/frontend/` 内的改动. 后端 schema / endpoint 改动见 [`design-backend.md`](./design-backend.md).

实施期: 等 backend schema ship 后 frontend Step 3/5/6 才能联调; Step 1/2/4 立刻能做.

---

## 1. 信息架构 — Flat Provider List

### 1.1 ApiKeysTab 顶层结构

```
ApiKeysTab
├── Header
│   ├── 标题 "API Keys"
│   └── 副标题 "Configure providers for LLM access. Add as many as needed."
├── ProviderList (flat map, no grouping)
│   ├── ProviderRow #1 (key=provider_code UUID)
│   ├── ProviderRow #2
│   └── ...
└── AddProviderButton (永远可点, 砍 DISABLED_PROVIDER_EDITING tooltip)
```

砍掉:
- `VENDORS` 数组 (apps/studio/frontend/src/components/studio/SettingsPage.tsx:51-57)
- `VendorGroup` 组件 (L592-664)
- `VendorEntry` interface (L34-39)
- `VendorId` type (L27)
- `DISABLED_PROVIDER_EDITING` / `DISABLED_ROLE_EDITING` 常量 (L60-61)

### 1.2 ProviderRow 数据模型 (frontend)

**B1 修正**: `TestStatus` **不含 `'testing'`** — Test 进行中是 UI 临时态, 跟持久化的 `last_test_status` 概念分离, 用独立 `isTesting: boolean` 标记. 这跟 backend `ProviderCredential.last_test_status` Literal 严格对齐 (后端不存 testing 这种瞬态值, race scenario 跟 B4 一致).

```typescript
// 对应 backend ProviderCredential (扩展 8 字段后), 类型名跟 backend 保持一致
interface ProviderEntry {
  provider_code: string             // UUID v4 (新 add) 或 legacy hardcoded. immutable from UI.
  title: string                     // 用户自定义 human-readable label, 默认 "Untitled Provider"
  provider_type: ProviderType       // dropdown: anthropic_compatible | openai_compatible | gemini_official
  vendor_hint?: string              // 可选, 仅 UI 用 (e.g., "Anthropic" / "DeepSeek" / "OpenRouter")
  base_url: string                  // 跟 provider_type 关联默认值, 用户可改
  api_key: string                   // 后端返明文 (round 2 反转)

  // Test 持久化字段 (backend 扩 schema 后填; 全部 readonly from frontend — 仅 GET, PUT 不写)
  last_test_status: TestStatus      // 'untested' | 'ok' | 'invalid_key' | 'rate_limited' | 'quota_exceeded' | 'network_error' | 'timeout'
  last_test_at?: string             // ISO 8601 timestamp
  last_test_message?: string        // 错误信息 / 成功摘要
  last_error_code?: string          // vendor 原始 error code (e.g., 'invalid_x_api_key')
  available_models?: ModelInfo[]    // Test 成功后填
}

type ProviderType = 'anthropic_compatible' | 'openai_compatible' | 'gemini_official'

// 持久化状态 (跟 backend Literal 严格一致, 7 个值, **不含 testing**)
type TestStatus = 'untested' | 'ok' | 'invalid_key' | 'rate_limited'
                | 'quota_exceeded' | 'network_error' | 'timeout'

interface ModelInfo {
  model_id: string
  display_name?: string
  capabilities: {
    thinking: boolean
    tool_calling: boolean
    vision: boolean
    max_context_tokens: number
  }
}

// 前端本地 draft (含 server 返回的 api_key 真值 + UI 临时态)
interface ProviderDraft extends ProviderEntry {
  api_key: string                   // plain text 真实值, 直接来自 backend GET response (round 2)
  // UI 临时态 (B1 — 单独跟持久化 last_test_status 分离, 不进 PUT body)
  isTesting: boolean                // Test 进行中? badge 显示 spinner, Test 按钮 disabled
}
```

### 1.3 默认值表 (按 provider_type 推荐)

```typescript
const DEFAULTS_BY_TYPE: Record<ProviderType, { base_url: string; vendor_hint: string }> = {
  openai_compatible: { base_url: 'https://api.openai.com/v1', vendor_hint: 'OpenAI' },
  anthropic_compatible: { base_url: 'https://api.anthropic.com', vendor_hint: 'Anthropic' },
  gemini_official: { base_url: 'https://generativelanguage.googleapis.com/v1beta', vendor_hint: 'Google Gemini' },
}
```

跟 `docs/llm-providers/README.md` 速查表保持同步.

---

## 2. 交互流程

### 2.1 Add Provider

```
用户点 "+ Add Provider"
  ↓
本地 React state 追加 ProviderDraft:
  {
    provider_code: crypto.randomUUID(),
    title: "Untitled Provider",
    provider_type: "openai_compatible",
    vendor_hint: "OpenAI",
    base_url: "https://api.openai.com/v1",
    api_key: provider.api_key,
    last_test_status: "untested",
    isTesting: false,          // B1 — UI 临时态, 跟 last_test_status 分离
  }
  ↓
该 row 自动 focus 到 title input (UX 提示)
  ↓
用户填字段, 每次 onChange:
  本地 state 更新 → debounce 300ms → PUT /api/llm/credentials (全量替换语义, 见 design-backend.md §3.2)
```

### 2.2 Edit Provider

跟 Add 一致, 全部行内编辑 + debounce save. **没有 Save 按钮**.

provider_type dropdown 改变时:
- 把 `base_url` 自动更新到 DEFAULTS_BY_TYPE 对应值 (**仅当 base_url 当前等于上一个默认值或为空**, 不覆盖用户已改)
- 把 `vendor_hint` 自动更新到 DEFAULTS_BY_TYPE 对应值

### 2.3 Test Provider (B1 + B4 — isTesting UI 临时态)

```
用户点 Test 按钮
  ↓
本地 setState: isTesting = true (badge 显示 spinner; Test 按钮 disabled 防双击)
toast.loading("Testing <title>...") (id = `test-${provider_code}` 防多 toast 堆叠)
  ↓
POST /api/llm/providers/test  { provider_code, provider_type, base_url, api_key, vendor_hint }
  ↓
后端响应 (backend 已经原子回写了 last_test_* 字段, 见 design-backend.md §4.6):
  ├── 成功:
  │     response.body = {
  │       status: 'ok',
  │       latency_ms: 1234,
  │       available_models: [...],
  │       model_seen: 'claude-...',  // 向后兼容字段
  │       message: 'Connected. 12 models available.'
  │     }
  │     toast.success("✓ <title>: N models available", { id: ... })
  │     本地 setState: isTesting=false, 同时把 last_test_status='ok' / last_test_at / available_models 等
  │     **从响应里 copy 到本地 state** (用于立刻显示, 不等下一次 GET refresh)
  │     注意: 本地 state 更新不触发 debounce save (Test 字段单向写, 见 design-backend.md §3.2)
  │     badge 显示绿点 "OK · 2026-05-18 14:23"
  │
  └── 失败:
        response.body = {
          status: 'invalid_key' | 'rate_limited' | ...,
          latency_ms: 456,
          error_code: 'invalid_x_api_key',  // vendor 原始 (或 'missing_api_key' 当 api_key 为空)
          message: 'Vendor returned: ...'
        }
        toast.error("✗ <title>: <translateErrorCode(error_code)>", { id: ... })
        本地 setState: isTesting=false, last_test_status=<status>, last_error_code, last_test_message
        badge 显示红点 "<error_code> · 时间戳", hover tooltip 显示完整 message
```

`translateErrorCode()` 按 `docs/llm-providers/<vendor>.md §8 Error Code Reference` 翻译成中文用户文案. 实现见 [§4.3 错误代码翻译表](#43-错误代码翻译表).

**B4 race 配合**: `isTesting=true` 时, debounce save 仍可触发 (用户改 title 不被锁), 但 **PUT body 不含 Test 字段** (Test 字段单向写规则, 由后端保护 — 见 `design-backend.md §3.2`). 所以 Test + debounce save 并发不会互相覆盖.

**Test 无视熔断** — 任何时候都能 Test, 不受 `last_test_status` 影响. UI 拦截: `isTesting=true` 时 Test 按钮 disabled, 用户点不到第二次.

### 2.4 Delete Provider

```
用户点 Trash icon
  ↓
Confirm dialog: "Remove <title>? This will mark any LLM Roles using it as Unavailable."
  ↓
确认 → 本地 state 移除该 provider → PUT /api/llm/credentials (全量替换, 不发该 provider → backend 自然删, 见 design-backend.md §3.2)
  ↓
LlmRolesTab 重新渲染时:
  - 该 provider 不在 providers 列表
  - 引用该 provider_code 的 RoleModelEntry.providers[i] 仍保留字符串值, UI 标 "Unavailable provider"
  - 不级联删 RoleEntry (用户可以手动改)
```

### 2.5 LlmRoles 下游 — 最小改动让 Unavailable filter 工作

`apps/studio/frontend/src/components/studio/SettingsPage.tsx:768-963` LlmRolesTab.

当前 LlmRolesTab 渲染 model dropdown 时, 改动:

```typescript
// 比对用户选的 model 是否在 provider 的 available_models 列表里
function getModelAvailability(
  modelId: string,
  providerCode: string,
  credentials: CredentialsState
): { available: boolean; reason?: string } {
  const provider = credentials.providers.find(p => p.provider_code === providerCode)
  if (!provider) {
    return { available: false, reason: 'Provider not found' }
  }
  if (provider.last_test_status === 'untested') {
    return { available: true, reason: undefined }  // 没测过, 不主动标 unavailable
  }
  if (provider.last_test_status !== 'ok') {
    return { available: false, reason: `Provider test failed (${provider.last_test_status})` }
  }
  if (!provider.available_models || provider.available_models.length === 0) {
    return { available: true, reason: undefined }  // 空列表 fallback, 不误杀
  }
  const found = provider.available_models.some(m => m.model_id === modelId)
  return { available: found, reason: found ? undefined : 'Model not in provider available_models' }
}
```

dropdown 显示:
- `available: true` → 正常显示 model_id
- `available: false` → 前缀 "⚠️ Unavailable", `disabled` 状态, hover 显示 reason

fallback 链 (`RoleModelEntry.providers` 数组) 渲染时同样 filter — 不可用 model 跳过 (不显示在链里), 或显示但标 "skipped".

**v2.1 不做**: rename RoleEntry 字段 / 改 fallback chain 数据模型 / 重画 LlmRolesTab UI. 延到 v2.5.

---

## 3. Debounce Save Hook

新增 `apps/studio/frontend/src/hooks/useDebouncedCredentialsSave.ts`:

```typescript
import { useEffect, useRef } from 'react'
import { toast } from 'sonner'
import { putCredentials } from '../api/llm'
import type { CredentialsState, ProviderDraft } from '../api/types'

const DEBOUNCE_MS = 300

// B3 + B4 配合: PUT body 仅含 ProviderCredentialWrite 字段 (provider_code / api_key / base_url
// / title / provider_type / vendor_hint), 不含 Test 持久化 5 字段 (后端 §3.2 单向写).
function buildPutPayload(credentials: CredentialsState): { providers: Array<Pick<ProviderDraft,
  'provider_code' | 'api_key' | 'base_url' | 'title' | 'provider_type' | 'vendor_hint'
>> } {
  return {
    providers: credentials.providers.map(p => ({
      provider_code: p.provider_code,
      api_key: p.api_key,                  // 空字符串时后端保留 server 端旧值 (C4 §3.2)
      base_url: p.base_url,
      title: p.title,
      provider_type: p.provider_type,
      vendor_hint: p.vendor_hint,
    })),
  }
}

export function useDebouncedCredentialsSave(
  credentials: CredentialsState,
  enabled: boolean = true
) {
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const lastSavedRef = useRef<string>('')

  useEffect(() => {
    if (!enabled) return
    const payload = buildPutPayload(credentials)
    const currentKey = JSON.stringify(payload)
    if (currentKey === lastSavedRef.current) return

    if (timerRef.current) clearTimeout(timerRef.current)
    timerRef.current = setTimeout(async () => {
      try {
        await putCredentials(payload)
        lastSavedRef.current = currentKey
      } catch (error) {
        console.error('Failed to auto-save credentials', error)
        toast.error('Failed to save provider config. Please retry.')
      }
    }, DEBOUNCE_MS)

    return () => {
      if (timerRef.current) clearTimeout(timerRef.current)
    }
  }, [credentials, enabled])
}
```

参考 video_analysis 的 auto-save pattern, 但简化 — 不每次 toast.success (避免每个 keystroke 都弹), 失败才 toast.error. **B4 解决方案 option a (后端原子写, 见 design-backend.md §4.6)** — 这个 hook 不需要监听 isTesting 暂停 debounce; 因为 PUT body 不带 Test 字段, 跟 POST `/api/llm/providers/test` 的回写完全不交叉.

---

## 4. 明文 API Key Input (round 2)

### 4.1 决策回顾

不用 `<input type="password">` (避免浏览器密码管理器弹窗).
不用字符级 mask / focus-aware mask / CSS blur / hover unblur.
round 2 明确反转 round 1 脱敏占位: input value 始终等于 backend GET/PUT response 返回的 `api_key` 明文。

### 4.2 React 实现 (round 2 — 无 show/hide 状态)

`showKey` / `isVisible` / `isFocused` state 全部删除。input 永远 `type="text"`, 并用 password-manager ignore 属性避免 Chrome / 1Password / LastPass 把它当密码字段。

```tsx
function ApiKeyInput({ value, onChange, providerCode }: ApiKeyInputProps) {
  return (
    <div className="relative">
      <Input
        type="text"
        value={value}
        onChange={(event) => onChange(event.target.value)}
        name={`provider-secret-${providerCode}`}
        autoComplete="off"
        data-1p-ignore
        data-lpignore="true"
        data-form-type="other"
        spellCheck={false}
        placeholder={`Paste API key for ${providerCode}`}
      />
    </div>
  )
}
```

**UX 备注**: 本地单用户场景下, 凭据文件权限已限制为 0600; 前端脱敏没有实际安全收益, 反而造成 "填完 key 自动消失" 的误解。

**Vitest unit 测试覆盖** (F1 落实施):
- backend response `api_key` 明文 → draft `api_key` 等于该值
- render 出来的 input `type="text"` 且 value 等于 draft `api_key`
- input 带 `autoComplete="off"` / `data-1p-ignore` / `data-lpignore="true"` / `data-form-type="other"` / `name="provider-secret-{id}"`

### 4.3 错误代码翻译表 (C3 — v2.1 限定中文 UI, i18n 延后)

**C3 i18n 范围明示**: v2.1 Studio 整体 UI 默认中文, error code 翻译表也用中文 hardcode. 完整 i18n (含语言切换 / 字符串外提到 locale files / vendor 原始英文 message 跟翻译版并存) **延到 v2.6+ 完整 i18n 提案统一处理**, 不在本 spec scope. v2.6 之前出现的新 vendor / 新 error_code 在这里继续中文 hardcode.

`apps/studio/frontend/src/lib/llm-error-messages.ts` (新增):

```typescript
// 跟 docs/llm-providers/<vendor>.md §8 同步; v2.1 中文 hardcode, i18n 延到 v2.6+
export function translateErrorCode(
  errorCode: string,
  vendorHint?: string
): string {
  const messages: Record<string, string> = {
    // missing_api_key (C4 — backend 前置校验返这个 code)
    'missing_api_key': 'API key 为空, 请先粘贴有效的 key',

    // Anthropic
    'invalid_x_api_key': 'API key 无效, 请检查粘贴是否完整 (Anthropic key 通常以 sk-ant- 开头)',
    'authentication_error': '鉴权失败, 请确认 x-api-key 和 anthropic-version header 都有',
    'rate_limit_error': '请求过快, 稍后再试',
    'overloaded_error': '服务暂时过载, 稍后再试',

    // OpenAI
    'invalid_api_key': 'API key 无效, 请检查粘贴 (OpenAI key 通常以 sk- 开头)',
    'insufficient_quota': '账户额度耗尽, 请充值或升级 plan',
    'rate_limit_exceeded': '请求过快, 稍后再试',
    'model_not_found': 'Model 不存在或账户无权限',

    // Gemini
    'UNAUTHENTICATED': 'API key 无效, 请重新生成 (Gemini key 通常以 AIza 开头)',
    'PERMISSION_DENIED': '当前 key 无此 model 权限, 或 region 不可用',
    'RESOURCE_EXHAUSTED': '请求过快或额度耗尽',

    // Network
    'network_error': '网络错误, 检查 base URL 是否可达',
    'timeout': '请求超时, 检查网络或 vendor 服务状态',
  }
  return messages[errorCode] ?? `未知错误: ${errorCode}`
}
```

---

## 5. 实施分步 (6 step)

| Step | 工作 | 状态 | 依赖 |
|---|---|---|---|
| **Step 1** | 砍 VENDORS / VendorGroup 树, ProviderRow 拍平; 实现明文 ApiKeyInput + password-manager ignore 属性 (round 2) | ✅ frontend-can-do-now | 无 |
| **Step 2** | Add Provider 流程 + UUID provider_code 生成 + useDebouncedCredentialsSave hook | ✅ frontend-can-do-now | Step 1 完成 |
| **Step 3** | Provider CRUD 联调 (验证 PUT 全量替换语义 + 任意 UUID provider_code + api_key 空保留); ProviderType Literal 从 4 收敛到 3 (跟 backend B1 同步) | 🚧 blocked-by-backend B1/B2/B3 ship | backend B1+B2+B3 |
| **Step 4** | Test UI 改 toast + persistent badge (移除 inline Alert); 错误代码翻译表 (C3 v2.1 中文 hardcode); isTesting 临时态接入 | ✅ frontend-can-do-now (用 baseline 4-field response 跑出 toast + badge 切换, 等 B4 后 step 5 接 available_models) | Step 1 完成 |
| **Step 5** | 消费扩展后的 ProviderTestResponse 字段 (available_models / error_code / model_seen); 本地 state 同步显示 + GET refresh 后从 backend 持久化字段恢复 | 🚧 blocked-by-backend B4 ship | backend B4 |
| **Step 6** | LlmRolesTab 用 available_models filter "Unavailable" model (最小改动) | ✅ Step 5 完后做 | Step 5 完成 |

### 5.1 我能立刻做 (不等 backend)

Step 1 + Step 2 + Step 4 三件. Step 4 即使 backend `ProviderTestResponse` 不扩, baseline 现有字段 (status / latency_ms / model_seen / message) 也够前端切换到 toast + isTesting badge UI; backend ship 后 Step 5 把扩展字段 (available_models / error_code) 接通.

**重要 (B3 cutover 协调)**: Step 1 + 2 + 4 落实施时**保留 4-enum `ProviderType`** (wavespeed_any_llm 不砍), 因为 backend B1 跟 frontend F1 并行起 PR. 等 backend B1+B2+B3 ship 后, frontend F3 联调 PR 同步把 4-enum 砍到 3-enum, 并把 LlmRoles 引用 wavespeed_any_llm 的 model 自动 migrate 显示提示.

### 5.2 卡 backend 的事

Step 3 (PUT 全量替换 + api_key 空保留 + ProviderType 收敛) / Step 5 (Test response 扩 schema) / Step 6 (依赖 Step 5).

具体 backend 任务清单见 [`design-backend.md`](./design-backend.md) + [`tasks.md`](./tasks.md#backend-tasks-parent-master-实施).

---

## 6. 文件改动清单 (frontend)

### 改动 (baseline 已存在的文件, worktree `/home/sevenx/coding/baseline-v21/`)

- `apps/studio/frontend/src/components/studio/SettingsPage.tsx`
  - 删除: `VendorId` / `VendorEntry` / `VENDORS` / `VendorGroup` / `DISABLED_PROVIDER_EDITING` / `DISABLED_ROLE_EDITING`
  - 重画: `ApiKeysTab` (flat list) / `ProviderRow` (用 `ApiKeyInput` 替换原 Input + 接 Test toast + badge)
  - 改动: `LlmRolesTab` model dropdown 加 availability filter (Step 6)
- `apps/studio/frontend/src/api/llm.ts`
  - 扩 `ProviderType` 类型 (从 4 砍到 3) — F1 暂保留 4-enum, F3 联调时跟 backend B1 同步收敛 (见 §5.1 + tasks.md §实施顺序)
  - 扩 `ProviderEntry` (对应 backend `ProviderCredential`) 加新 8 字段: title / provider_type / vendor_hint / last_test_* / available_models
  - 新增 `ModelInfo` / `ModelCapabilities` / `TestStatus` (不含 testing) 类型
  - `putCredentials` 函数: PUT body 仅含 `ProviderCredentialWrite` 字段 (B3 single-write 规则)

### 新增

- `apps/studio/frontend/src/hooks/useDebouncedCredentialsSave.ts`
- `apps/studio/frontend/src/components/studio/ApiKeyInput.tsx`
- `apps/studio/frontend/src/components/studio/ProviderRow.tsx` (从 SettingsPage 拆出)
- `apps/studio/frontend/src/lib/llm-error-messages.ts`
- `apps/studio/frontend/tests/e2e/api-keys.spec.ts` (Playwright, 等 backend ship 后做)

### 不动

- `LlmRolesTab` 的 `RoleEntry` / `RoleModelEntry` / `circuit_breaker` 数据模型 (v2.5 重画)
- `video_analysis` 项目 (read-only 参考)

---

## 7. 视觉细节 (照 baseline UI 规范)

按 `.kiro/specs/studio-uikit-redesign/tokens.md` + `design.md` 视觉规范:

- ProviderRow 间距: `space-y-3` (12px)
- Badge 颜色: 绿点 `text-emerald-600`, 红点 `text-rose-600`, 灰点 (untested) `text-slate-400`
- 按钮: Test 用 `variant="outline"` size sm, Trash 用 `variant="ghost"` size icon
- ApiKeyInput 无 Eye button, input 占满剩余宽度, 右侧为 Test 按钮
- dropdown 选 provider_type 用 shadcn `<Select>` 组件

具体颜色 / 字号 / 圆角值: 严格按 `tokens.md` semantic token, 不写裸 hex.

---

## 8. 测试计划

### 8.1 Step 1+2+4 (frontend-do-now) 自测 (a3 实施时跑)

- TypeScript 编译过
- ESLint 过
- Vitest unit: useDebouncedCredentialsSave hook (mock putCredentials, fake timers 验证 debounce)
- Playwright smoke: 我能加 / 改 / 测 / 删 1 个 provider (backend 用 baseline)

### 8.2 Step 3+5+6 (backend ship 后) e2e

`apps/studio/frontend/tests/e2e/api-keys.spec.ts`:

| 测试用例 | 期望 |
|---|---|
| 空状态 → 点 Add → 一行 row + 默认 OpenAI | ✓ |
| 改 title → 300ms 后 PUT 触发 | ✓ |
| 粘贴 key → input 保持显示真实值, refresh 后仍显示 server 真值 | ✓ |
| 无 Eye / mask 状态, input 永远 type="text" | ✓ |
| 浏览器密码管理器不弹 | ✓ (`autocomplete=off` + data 属性) |
| Test 成功 → 绿 badge + N models toast | ✓ |
| Test 失败 (invalid key) → 红 badge + error_code toast | ✓ |
| Refresh → badge / available_models 持久化重显 | ✓ |
| Delete 后 LlmRolesTab 标 "Unavailable provider" | ✓ |

### 8.3 视觉验证 (强制, 按宪法 3)

按 memory `feedback_self_verify_before_report_done`: a3 实施完后, **主控亲眼用 Playwright 跑一遍**, screenshot 对比 baseline 截图 (`pre-v21-loaded.png` / `pre-v21-welcome.png`), 验证视觉对齐 baseline 规范, 再跟 user 说 done.

---

## 9. 已知 risk (frontend 侧)

1. **多 provider 性能**: 如果用户开 10+ provider, 每行 input 都持有明文值. v2.1 不优化 (实测 < 20 行的列表性能 OK), v2.5 重画 LlmRolesTab 时虚拟化.

2. **明文可见性**: round 2 接受本地 UI 直接显示 `api_key`; 不再以 placeholder/mask 隐藏已保存值, 避免用户误判 key 已丢失.

3. **UUID 兼容旧 baseline provider_code**: 现有 baseline 已有的 provider_code 是 hardcode 字符串 (e.g., `"OC_CL_ANT"`, `"DS"`). 迁移时:
   - 新 add 的用 UUID
   - 已有的保留旧 code (不强制迁移, 避免 LlmRoles 引用断)
   - **backend 必须支持** "任意字符串 provider_code", 不只是 UUID

4. **provider_type dropdown 改值后 base_url 处理**: 当前规则 "仅当 base_url 等于上一个默认或为空才覆盖". 如果用户改了 type 又改回, base_url 不会自动 reset 回新 type 的默认. 这是 acceptable trade-off (避免覆盖用户意图).

---

## 10. 后续 v2.5 联动

- LlmRolesTab 重画 (rename / fallback chain UI / 真业务调用熔断不做但 UI 提示链)
- 拖拽排序 / favorite 标记
- Provider 模板 import (用户分享 JSON 配置)

这些 v2.1 范围外, 仅作未来视野记录.

## Round 2 翻转记录 (2026-05-19)

`has_key: boolean` 字段全文废弃。frontend 直接显示 `provider.api_key` 真值。

`showKey` useState + Eye/EyeOff toggle 全部删除 — input 一律 `type="text"` plain text 显示, 配 `data-1p-ignore` / `data-lpignore="true"` / `data-form-type="other"` / `name="provider-secret-{id}"` 堵浏览器密码管理器。
