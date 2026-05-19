# Round 3 Design — API Keys 多 SDK 自动探测 + Mask 切回 + 官方/第三方分类

> **Status**: Draft (a2 review round 2 PASS, awaiting user spec review)
> **Date**: 2026-05-19
> **Brief 来源**: User 9 项 feedback (2026-05-19) + 3 轮澄清
> **Reviewer**: a2 (Gemini), 2 rounds, 最终评级 PASS
> **关联文档**: `requirements.md` (round 1+2 反转), `design-frontend.md` / `design-backend.md` (round 2 plaintext display), `research.md` (video_analysis pattern), `tasks.md`

---

## §0 反转日志 (Round 1 → Round 2 → Round 3)

| Round | 核心改动 | Trigger |
|---|---|---|
| Round 1 | Backend GET 返 `has_key:bool` (不返 key) + frontend draft.api_key="" + "Saved key retained" placeholder + input `type="password"` (mask) | 初始设计, 防 key 泄露屏显 |
| Round 2 (PR #74) | Backend 返 plaintext + frontend init draft from server + input 永远 `type="text"` + 删 showKey/Eye toggle + 加 password-manager 抑制属性 | (1) Round 1 save 后 draft reset 成 placeholder → Test 报 "API key empty"; (2) `type="password"` 触发 Chrome "Save password?" 弹框 |
| **Round 3 (本文)** | 多 SDK 自动探测 + 官方/第三方单入口分类 + skeleton + AlertDialog + mask 切回 (CSS, 非 type=password) + Badge utility 颜色 + Doc 元数据扩展 + max_tokens 跳 runtime 测试 | User 9 项 feedback, 见 §1 |

### Round 3 必守契约 (来自 round 2 反转教训, 防 round 4)

**契约 A1**: input 永远 `type="text"`, 绝不许 `type="password"`。Mask 走 CSS, 不走 native input type。
**契约 A2**: `draft.api_key` 永远是 backend 返的真值, 绝不许 mask 实现污染 draft state (mask 只是 display layer)。
**契约 A3**: PR #74 加的浏览器密码管理器抑制属性 (`data-1p-ignore` / `data-lpignore` / `data-form-type="other"` / `name="provider-secret-{id}"`) 保留, round 3 不动。

---

## §1 9 项 user feedback 总览 + cover 段映射

| # | User 原话 (节选) | Cover 段 |
|---|---|---|
| 1 | "加一下 skeleton" | §5 |
| 2 | "API key 要用 **** 隐藏, input 后面加一个 eye button 开关, button 去掉默认动画" | §4 |
| 3 | "多 SDK 兼容? ... test 时在多个 sdk 上测试, 得到 available sdk, 和模型一样, 这个 API 可以用哪些模型, 哪些 sdk; Gemini / Ark 官方 sdk 加入, 去抓官方文档存到 docs" | §3 + §8 |
| 4 | "sdk protocol form 不需要, 在最下方展示可用的 sdk, 可用的模型" | §3 (chip 区) |
| 5 | "tested 状态 badge 颜色改一下, 哪几种状态对应那几种模版颜色, 去 shadcn 官网确认" | §7 |
| 6 | "删除功能要加 alert 确认" | §6 |
| 7 | "test 按钮可以稍微再宽一点点, 稍微有点丑" | §7 (px-6) |
| 8 | "需要选择是官方 provider 还是第三方, 官方 provider 只需要下拉菜单选择: anthropic / Gemini / ark / deepseek 等等, 把市面上常用大模型文档扒一遍, base URL 就不用填了, 官方的用默认就好, provider name 也不用填, 就用模型厂商+Official, 例如 Deepseek-Official" | §2 |
| 9 | "测试能否测试出 max_token? 包括输入和输出" | §9 (跳 runtime, 抄 doc) |

---

## §2 总架构: 单入口 + 类型 Radio + Official Select 下拉

> 修自 round 1 review 反馈 (a2 1.1): User #8 原话 "需要选择" + "官方下拉菜单" 指单入口 form flow, 不是 layout 分区双轨

### 2.1 入口

- 顶部一个 `+ Add Provider` 按钮 (shadcn `Button`)
- 点击 → **inline form 展开** (在按钮下方, 带描边/背景独立区块, 跟 shadcn admin console 主流一致; **不是 Dialog**, 避免遮盖已有列表 — 来自 a2 round 2 §4 推荐)

### 2.2 Form 内容

- **类型选择** (shadcn `RadioGroup`, 2 选 1):
  - "Official Provider"
  - "Third-party Provider"
- **选 Official 时**:
  - shadcn `Select` 下拉, 5 项: Anthropic, OpenAI, Gemini, DeepSeek, Ark
  - 选完后:
    - Provider name 字段自动填 `<Vendor>-Official` (e.g., `DeepSeek-Official`), **readOnly**
    - Base URL 字段自动填 doc 元数据里的 official endpoint, **readOnly**
    - API Key 字段 user 填
- **选 Third-party 时**:
  - 跟现有 OpenRouter 表单一致 (user 自由填 name / base URL / api key)

### 2.3 现有 provider 列表

- 展示在 `+ Add Provider` 按钮**上方**, 一个 flat 列表 (不分官方/第三方)
- 每个 row 用 shadcn `<Badge variant="outline">` 显示类型: "Official" or "Third-party"

### 2.4 文件影响

- `apps/studio/frontend/src/components/studio/SettingsPage.tsx` 当前的 `VendorGroup` (硬编码 5 vendor) 拆掉, 改成 flat ProviderList
- 新增子组件:
  - `apps/studio/frontend/src/components/studio/api-keys/AddProviderForm.tsx` (form 主体, 含 RadioGroup + 条件渲染)
  - `apps/studio/frontend/src/components/studio/api-keys/OfficialVendorSelect.tsx` (5 vendor Select)
  - `apps/studio/frontend/src/components/studio/api-keys/ProviderRow.tsx` (现有 ProviderRow 拆出来, 单独文件, 避免 SettingsPage.tsx 越 300 行)

---

## §3 Test 行为 + 多 SDK 探测 + 可用模型 chip 展示

> 修自 round 1 review 反馈 (a2 2.1): doc 元数据要补 `models_endpoint_path` + `auth_header_format`

### 3.1 删除 SDK Protocol form

- 当前 SettingsPage.tsx 的 OpenAI Compatible / Anthropic 单选 RadioGroup **整组删除**
- backend 的 `ProviderType` enum 字段保留 (用于 backend 内部判断), 但前端 user 不再选

### 3.2 Test 流程

Test 按钮 click 后, backend handler 干 2 件:

#### A. SDK 探测 (`available_sdks`)

1. 读 vendor 的 doc 元数据 `compatible_sdks`, 得到 "理论可用 SDK 集合"
2. 对集合内每个 SDK:
   - 按 doc 的 `auth_header_format` 模板组装 header
   - 发 1-token request (`max_tokens=1, messages=[{role:"user", content:"."}]` 或 SDK 等价 minimal call)
   - 判定:
     - 200 OK → 该 SDK 加入 `available_sdks`
     - 401 / 403 → key 鉴权不通该 SDK, 不加入
     - 400 / 422 (输入太短 / 语义 reject) → 鉴权层通了, **加入 `available_sdks`** (我们只验证鉴权层)
     - 5xx → 网络 / 厂商问题, 标 unknown 不写入

#### B. 模型探测 (`available_models`)

- 读 vendor doc 元数据 `models_endpoint_path`:
  - **非 null** (e.g., OpenAI `/v1/models`, OpenRouter `/api/v1/models`) → backend `GET ${base_url}${models_endpoint_path}` (含 auth header) → parse 返回的 models list → 写入 `available_models`
  - **null** (e.g., Anthropic 无 `/models` endpoint) → 走 doc fallback, 读该 vendor doc 的 "Notable Model IDs" 章节 (现有 `_template.md` §4 已定义) → 写入 `available_models`

### 3.3 UI 展示

- 卡片底部新区: `Available SDKs: [chip × N]` + `Available Models: [chip × N]`
- 测试前 placeholder: "Untested" (灰色 muted text)
- 用 shadcn `<Badge variant="secondary">` 或 inline chip 元素 (按 baseline tokens.md 视觉)

### 3.4 Third-party Provider 走相同流程

- backend 拿 user 填的 base URL + doc 元数据 (`compatible_sdks` / `models_endpoint_path` / `auth_header_format`)
- 元数据来源: `docs/llm-providers/openrouter.md` / `wavespeed.md` / `qiniu.md` (a2 后续扒, 见 §8)

---

## §4 Mask + Eye 实现 (CSS 方案 + Firefox fallback)

> 修自 round 1 review 反馈 (a2 3.1): 采纳 CSS, 废弃"值分离" (后者要劫持 onChange / 维护光标, 脆弱)
> 加 round 2 review 反馈 (a2 §5): Firefox 不支持 `-webkit-text-security`, 加 fallback

### 4.1 input 处理

- input 永远 `type="text"` (契约 A1)
- 加 className `mask-input` (条件渲染, 基于 `visible: boolean` state)
- CSS rule:
  ```css
  .mask-input {
    -webkit-text-security: disc;
    /* Firefox fallback */
    font-family: 'text-security-disc', sans-serif;
  }
  ```
- Firefox fallback webfont (`text-security-disc`): 一次性 import 进 frontend 的 fonts/, 开源 (Apache-2.0 license)

### 4.2 Eye button

- shadcn `Button` (`size="icon-xs" variant="ghost"`)
- 加 `transition-none` className (去掉 hover / active default 动画, 来自 user #2)
- click toggle `visible: boolean` state → render 时 add / remove `mask-input` className

### 4.3 state 不污染

- `draft.api_key` 永远是 backend 返的真值 (契约 A2)
- `visible` 是独立 display state, 不影响 storage

### 4.4 文件影响

- `apps/studio/frontend/src/components/studio/api-keys/ProviderRow.tsx`: 加 eye button + className 切换
- `apps/studio/frontend/src/index.css` (或对应全局 stylesheet): 加 `.mask-input` rule
- `apps/studio/frontend/public/fonts/text-security-disc.woff2`: 引入 Firefox fallback webfont (3KB)

---

## §5 Skeleton (loading)

- `apps/studio/frontend/src/components/studio/api-keys/ProviderListSkeleton.tsx`: 新组件, 用 shadcn `Skeleton` 占位
- 渲染时机: `GET /credentials` 未返回前 (查 SettingsPage 现有 loading state)
- 渲染内容: 3 行 placeholder (vendor 名 + API key 行 + 按钮行), 高度跟实际 ProviderRow 匹配

---

## §6 Delete + AlertDialog

- 当前 ProviderRow.tsx 删除按钮 disabled (注释 v2.5)
- 启用按钮, click → shadcn `AlertDialog` 弹出
- 文案: "确认删除 `<provider name>`? 此操作不可恢复。" 二级按钮 "取消" / "删除"
- 删除走现有 backend `DELETE /credentials/<provider_code>` (查 backend 现有 endpoint)

---

## §7 Test 按钮宽度 + Badge variant 颜色

### 7.1 Test 按钮宽度 (user #7)

- shadcn `Button size="sm"`, 加 `px-6` className
- 不自创 size variant (维持 baseline tokens.md 的 size 矩阵不变)

### 7.2 Badge variant 映射 (user #5)

> 修自 round 1 review 反馈 (a2 3.2): "Connected" 用 default 主色视觉暗示弱, 改 outline + utility class

| 状态 | shadcn Badge variant | className |
|---|---|---|
| "Saved" / "Untested" | `secondary` | (默认) |
| "Connected" / "Tested" | `outline` | `text-emerald-500 border-emerald-500/50` |
| "Error" | `destructive` | (默认) |
| "Testing..." | `outline` | (默认) + 内嵌 spinner icon |

**Rationale**: 不引入 custom `success` variant 漂移 baseline tokens; utility class 在 use site 加成功语义色 (符合 shadcn 组合哲学)。实施时 a1 看 shadcn 官网 Badge doc + mira preset indigo theme 视觉测试, 必要时微调 emerald 透明度。

---

## §8 Docs/llm-providers 扒文档 + 元数据扩展

> 修自 round 1 review 反馈 (a2 2.1): doc 元数据要补探测字段; round 2 补 vendor coverage

### 8.1 `_template.md` 新增章节 §1.5 探测元数据

```yaml
compatible_sdks: [<sdk_enum>, ...]   # 该 vendor 支持的 SDK 集合
                                      # 已有 enum: anthropic_compatible / openai_compatible / gemini_official / wavespeed_any_llm
models_endpoint_path: "<path>" | null # GET <base_url><path> 拉 models list
                                      # null 走 fallback 读 §4 Notable Model IDs
auth_header_format: |
  Header1: <template1>                # 含 ${key} 占位符
  Header2: <template2>
```

### 8.2 新扒 5 份 vendor doc (a2 后续主笔)

| Vendor | Type | URL hint |
|---|---|---|
| DeepSeek | Official | https://api-docs.deepseek.com/ |
| Ark (火山引擎方舟) | Official | https://www.volcengine.com/docs/82379 |
| OpenRouter | Third-party | https://openrouter.ai/docs |
| WaveSpeed | Third-party | (查 backend `wavespeed_any_llm` 现有 reference) |
| 七牛 | Third-party | https://www.qiniu.com/ (具体 LLM 服务子路径待 a2 verify) |

### 8.3 老 3 份 doc 补元数据

- `anthropic.md`: 加 §1.5 (`compatible_sdks: [anthropic_compatible]`, `models_endpoint_path: null`, `auth_header_format: "x-api-key: ${key}\nanthropic-version: 2023-06-01"`)
- `openai.md`: 加 §1.5 (`compatible_sdks: [openai_compatible]`, `models_endpoint_path: "/v1/models"`, `auth_header_format: "Authorization: Bearer ${key}"`)
- `gemini.md`: 加 §1.5 (`compatible_sdks: [gemini_official]`, `models_endpoint_path` + `auth_header_format` 待 a2 confirm)

### 8.4 max_tokens 数据 (跳 runtime)

- 跳过 runtime 验证 (Q3 决议: 跑 5 vendor 旗舰 model verify 一次 ~$10-12, ROI 低)
- a2 扒 doc 时直接抄官方写死的 `max_context_tokens` / `max_output_tokens` 进 `<vendor>.md` 的 §5 能力维度表 (现有 `_template.md` §5 已定义)
- 后续如发现 doc 数字跟实际有偏差, 再补测

---

## §9 修改范围精准 (user 原则: "没提到的地方不要自说自话乱改")

### 只动

| 文件 / 目录 | 改动内容 |
|---|---|
| `apps/studio/frontend/src/components/studio/SettingsPage.tsx` | ApiKeysTab 拆分 (移逻辑出去), TestMessage 改 badge variant |
| `apps/studio/frontend/src/components/studio/api-keys/*.tsx` | **新增**子目录 (AddProviderForm / OfficialVendorSelect / ProviderRow / ProviderListSkeleton) |
| `apps/studio/frontend/src/api/llm.ts` | `CredentialProviderState` 加 `available_sdks: string[]` / `available_models: string[]` 字段 |
| `apps/studio/frontend/src/index.css` (或全局 css) | 加 `.mask-input` rule |
| `apps/studio/frontend/public/fonts/text-security-disc.woff2` | **新增** Firefox fallback webfont |
| `apps/studio/backend/services/llm_credentials.py` | 加 `available_sdks` / `available_models` 字段 |
| `apps/studio/backend/services/llm_provider_test.py` | Test handler 改造 (SDK 探测 + `GET /models` 调用, 按元数据组装) |
| `apps/studio/backend/models/llm_config.py` | response shape 加新字段 |
| `apps/studio/backend/services/llm_provider_meta.py` | **新增** module: 加载 `docs/llm-providers/<vendor>.md` 元数据 (parse YAML frontmatter / §1.5 章节) |
| `docs/llm-providers/_template.md` | 加 §1.5 探测元数据章节 |
| `docs/llm-providers/{anthropic,openai,gemini}.md` | 补 §1.5 元数据 |
| `docs/llm-providers/{deepseek,ark,openrouter,wavespeed,qiniu}.md` | **新增** 5 份 |
| `.kiro/specs/studio-api-keys-redesign/round3-design.md` | **本文档** |

### 不动

- Settings → General tab / LLM Roles tab (不在 round 3 scope)
- Canvas / 其他 frontend / backend 业务代码
- PR #74 加的浏览器密码管理器抑制属性 (`data-1p-ignore` 等), 保留
- backend `ProviderType` enum 4 种值, 复用不扩
- `docs/llm-providers/{anthropic,openai,gemini}.md` 现有 §1-§8 章节, 不动 (只加 §1.5)

---

## §10 PR 拆分 (实施顺序)

| PR | 主笔 | scope | blocking |
|---|---|---|---|
| PR-A | **a2** (Gemini) | `docs/llm-providers/` 5 份新 doc + 老 3 份补 §1.5 元数据 + `_template.md` 加 §1.5 章节 | 无 |
| PR-B | **a1** (Codex) | backend schema + Test handler 改造 (`available_sdks` / `available_models` 字段, SDK 1-token verify, `GET /models` 调用, 元数据加载 module) | PR-A merge 后 |
| PR-C | **a1** (Codex) | frontend 9 项 UI 改造 (拆 ProviderRow 文件 + 单入口 form + skeleton + AlertDialog + mask CSS + Badge utility class + Test 按钮 px-6 + Available SDKs/Models chip 区) | PR-B merge 后 (依赖新字段) |

---

## §11 a2 review 摘要

### Round 1 (NEEDS FIX, 4 findings, 全 fix)

1. **1.1 §1 总架构方向偏** (`[证据 H × 影响 H × 置信度 A]`): User #8 "下拉菜单选择" 是单入口 form flow, 不是 layout 双轨。**已修**: §2 改单入口 + RadioGroup + Select 下拉
2. **2.1 §2 第三方探测元数据漏** (`[证据 M × 影响 H × 置信度 A]`): doc 元数据要补 `models_endpoint_path` + `auth_header_format`, 否则第三方 Test 报 404/401。**已修**: §3 + §8 加元数据字段
3. **3.1 §3 Mask 推 CSS 弃值分离** (`[证据 H × 影响 H × 置信度 A]`): 值分离要劫持 onChange / 维护光标, 脆弱。**已采纳**: §4 走 CSS `-webkit-text-security`
4. **3.2 §6 Badge "Connected" 用 outline + utility** (`[证据 M × 影响 M × 置信度 B]`): default 主色视觉暗示弱, utility class 加 emerald 更准确。**已修**: §7.2 改 outline + emerald className

### Round 2 (PASS, 2 实施推荐)

1. **§1 推 Inline form (非 Dialog)** (`[证据 H × 影响 M × 置信度 A]`): admin console 主流, 不遮盖列表。**已采纳**: §2.1 明示 inline form
2. **§4 CSS mask 加 Firefox fallback** (`[证据 H × 影响 H × 置信度 A]`): Firefox 不支持 `-webkit-text-security`。**已采纳**: §4.1 加 webfont fallback (`font-family: 'text-security-disc'`)

a2 原话: "整体业务链路及方案通过, 请直接开始后续实现"

---

## §12 Spec self-review (PM inline check)

- ✅ 无 TBD / TODO placeholder
- ✅ 9 项 user feedback 全 mapping 到 §2-§9 (§1 总览表)
- ✅ 三条契约 (A1/A2/A3) 在 §0 明示, 防 round 4 反转
- ✅ §10 PR 拆分依赖明确 (PR-A → PR-B → PR-C, 不能并行)
- ✅ §9 修改范围精准, "动什么 / 不动什么" 列清楚
- ✅ Scope 在一个 spec 内 (frontend + backend + docs 一并, 不分裂)
- ✅ 无内部矛盾 (a2 review 收敛点跟 §2-§9 一致)

唯一 ambiguity (实施层面, 可在 PR-C 决定, 不阻设计):
- §7.2 Badge "Connected" emerald 具体透明度 (`text-emerald-500` vs `text-emerald-600`), 看 mira preset indigo theme 视觉测试。

---

## §13 下一步

按 brainstorming skill 流程:

1. ~~Brainstorm clarifying~~ ✅ 3 轮收敛
2. ~~Propose approaches~~ ✅ PM propose + a2 round 1/2 review 2 rounds
3. ~~Write spec~~ ✅ 本文档
4. ~~Spec self-review~~ ✅ §12
5. User review 本文档 → 如有 push back 收敛 → approve
6. Invoke `superpowers:writing-plans` skill 拆 implementation plan (基于 §10 PR 拆分)
