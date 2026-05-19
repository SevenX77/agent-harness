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

## §概念定义

为对齐架构边界, 锁定 6 个核心概念:

- **provider (接入商)**: 提供大模型 API 服务的平台, 无论官方 (Anthropic 官方 API) 还是第三方 (OpenRouter / Wavespeed). 计费和鉴权主体.
- **provider_key (接入商唯一标识)**: 对应 `apps/studio/backend/app/data/llm_providers/<provider_key>.md` 文件名 (如 `openrouter`), 用于关联元数据.
- **provider.id**: 凭证持久化数据库记录的 UUID, 区分同一个 provider 平台配置的多张 credential 记录 (e.g., 同一个 OpenRouter 可申请 2 个 key 分别给 Gemini 和 Claude 用, id 不同).
- **vendor (模型开发厂商)**: 实际训练并发布模型的主体公司 (Anthropic 开发 Claude / OpenAI 开发 GPT / Google 开发 Gemini). 一个第三方 provider 可提供多个 vendor 的 model.
- **model**: 实际执行推理的模型实例 (`claude-opus-4-7` / `gpt-5` / `gemini-2.5-pro`).
- **SDK (通信协议)**: 调用 API 所使用的客户端协议规范 (`openai_compatible` / `anthropic_compatible` / `google_genai`).
- **role (系统角色)**: Studio 内部智能体角色 (Planner / Executor 等). 绑定到 `(provider.id, model)` 组合上, 详见 `.kiro/specs/llm-roles-setting/round1-design.md`.

**关系链路示例**:
用户在 Provider (OpenRouter) 配置 Key, 选择 vendor=Anthropic 的 model (`claude-opus-4-7`), 后端匹配出 SDK (`openai_compatible`) 发起调用, 最终赋能 Role (Planner).

**层级**:
```
provider (OpenRouter) 卖多个 vendor 的 model:
  ├─ vendor=Anthropic: claude-opus-4-7, claude-haiku-4-5
  ├─ vendor=OpenAI: gpt-5, gpt-4o
  └─ vendor=Google: gemini-2.5-pro

provider (Anthropic 官方) 只卖 vendor=Anthropic 的 model

provider.id (UUID) 区分多张 credential record:
  id: "uuid-1234" → provider_key="openrouter" → name="OpenRouter (Gemini)"
  id: "uuid-5678" → provider_key="openrouter" → name="OpenRouter (Claude)"
  两条共享 provider_key, 通过 id 独立共存.
```

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

## §2 总架构: Official 预渲染 + Third-party 极简表单

页面按 provider 属性物理划分上下两区:

### 2.1 Official Providers (上半区)
- 预先渲染固定的 5 张 `ProviderCard`: Anthropic / OpenAI / Gemini / DeepSeek / Ark
- 用户视角无须填写 Provider Name 和 Base URL (后端隐式绑定官方默认值, readOnly)
- 每张 card 暴露: API Key 输入框 + Test 按钮
- 未配 API Key 状态 = "Not configured" (灰色 badge), Test 按钮 disabled

### 2.2 Third-party Providers (下半区)
- 严格继承 round 1 之前的 Third-party 行为和设计, 仅做最小微调
- 默认折叠
- 点击 `+ Add Provider` 按钮展开 inline form (button 下方独立块, 非 Dialog)
- Form 字段维持现状最小化 (无新增下拉框):
  1. `Provider Name` (Text Input)
  2. `Base URL` (Text Input)
  3. `API Key` (Text Input)
- 提交后 button 重新可点, form 收起

### 2.3 删除项 (相比 round 1 设计)
- ❌ Form 内 "Official / Third-party 类型选择" RadioGroup (因为已物理两区分隔, 不再需要 user 选)
- ❌ SDK Protocol radio (OpenAI Compatible / Anthropic) — 由 LLM Roles 探测得出, user 不再选

### 2.4 文件影响
- `apps/studio/frontend/src/components/studio/SettingsPage.tsx`: ApiKeysTab 拆 Official 区 + Third-party 区
- `apps/studio/frontend/src/components/studio/api-keys/AddProviderForm.tsx`: 删 type RadioGroup, 默认折叠, 加 Cancel button
- `apps/studio/frontend/src/components/studio/api-keys/ProviderCard.tsx`: 删 SDK Protocol RadioGroup
- 新增: `apps/studio/frontend/src/components/studio/api-keys/ManualModelTestPanel.tsx` (§3 Fallback 用)

---

## §3 API Keys Test 流程

API Keys 页面 Test 按钮职责严格收敛于**联通性鉴权 + 可用模型列表获取**, SDK 探测后置到 LLM Roles.

Test 触发后, 后端 `POST /providers/test` 按以下路径执行:

### 3.1 首选路径: GET /models 探测

- 后端读 `provider_key` 对应的 `models_endpoint_path` 元数据 + `auth_header_format` 构造鉴权请求
- 发送 `GET ${base_url}${models_endpoint_path}` (含 auth header)
- **判定**:
  - HTTP 200 → 鉴权成功 + 提取 `available_models`. 双目标一次网络开销完成
  - HTTP 401 / 403 → Key 鉴权失败, 中止抛错, 前端提示
  - HTTP 5xx → 服务异常, 标 unknown

### 3.2 双 Parser 提取

- **OpenAI-style Parser**: 提取 `data[].id` (覆盖 OpenAI / Anthropic / DeepSeek / Ark / OpenRouter)
- **Gemini-style Parser**: 提取 `models[].name` (去 `models/` 前缀)
- **顺手收集 capabilities**: 解析时若 API 返回额外字段, 统一归一化后写入 `ModelInfo.capabilities` (万能字典)

**capabilities 归一化约定**:

| 统一字段 | 含义 | API 原始字段映射 |
|---|---|---|
| `max_context_tokens` | input context window | Anthropic `max_input_tokens` → `max_context_tokens`; Gemini `inputTokenLimit` → `max_context_tokens`; OpenRouter `context_length` → `max_context_tokens` |
| `max_output_tokens` | output max | Anthropic `max_tokens` → `max_output_tokens`; Gemini `outputTokenLimit` → `max_output_tokens`; OpenRouter 不返回则留空 |

其他原始能力字段 (如 `capabilities.*`) 透传保留进 dict, 供未来扩展; 但 LLM Roles 固定读取 `max_context_tokens` / `max_output_tokens` 两个归一化键。

### 3.3 Fallback 路径: Manual Model Probing (手动验证模型)

**触发**: 首选路径 GET /models 返 HTTP 404/405 (endpoint 不存在), 或 doc 元数据 `models_endpoint_path: null` / 缺失.

**前端 UI** (新组件 `ManualModelTestPanel.tsx`):
- 条件渲染在 ProviderCard 的 `Available Models` chip 区下方
- 文本输入框 (受控 state `testModelIds: string[]`) + `+ Add Model` 按钮动态增行
- mount 时调用后端 `GET /providers/notable-models?provider_key=<key>` 获取候选, 作为 input placeholder / dropdown 默认值
- `[Test Models]` 按钮触发后端验证

**后端 endpoints**:

`GET /providers/notable-models?provider_key=<key>`
- 后端读取 `apps/studio/backend/app/data/llm_providers/<provider_key>.md` §4 Notable Models
- 返回 `{"notable_models": ["claude-opus-4-1", ...]}`
- 前端不能直接读取 backend markdown 文件, 必须通过该 API 透传候选

`POST /providers/test-models` (body 含 `provider_id` + `model_ids: string[]`)
- 对每个 model id 并发发 1-token chat 请求 (必须带 model 参数)
- 鉴权通过 (HTTP 200 / 400 / 422 — 鉴权层放行) → 该 model 加入 result
- 鉴权失败 (401 / 403) → 该 model 标记 reject

**累加机制**:
- 通过的 model **追加** (extend + 去重, 不是替换) 进 `state.available_models` 持久化列表
- 前端 Available Models chip 区刷新显示
- ManualModelTestPanel **常驻可见**, user 可以继续添加 / 修改 / 重新测试累加更多 model

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

## §6 Delete + AlertDialog (round 2/3 早期已实施)

- ProviderCard 删除按钮 click → shadcn `AlertDialog` 弹出
- 文案: "确认删除 `<provider name>`? 此操作不可恢复。" 二级按钮 "取消" / "删除"
- 确认后 frontend 从本地 `CredentialsState.providers` 列表移除该 entry, 然后调用现有 `PUT /credentials` 整体覆盖保存
- 不新增 `DELETE /credentials/<provider_code>` endpoint (当前 backend 只有 `GET /credentials` / `PUT /credentials` / `POST /providers/test`)

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

## §8 静态元数据体系 (Single Source of Truth)

**位置变更**: `docs/llm-providers/*.md` → `apps/studio/backend/app/data/llm_providers/*.md`

**理由**:
- `docs/` 容易被误认为是仅供人阅读的说明书
- `app/data/llm_providers/` 明确宣告"驱动系统运行的关键配置 (Machine-Readable Data)"
- 跟现有 `apps/studio/backend/app/{core,models,routers,services,templates}` 同级目录风格一致

**Backend 寻址**: `pathlib.Path(__file__).parents[1] / "data" / "llm_providers"` (调用方在 `app/services/` 下时, parents[1] = `app/`)

**清理**: 彻底删除原 `docs/llm-providers/` 目录, 避免双份真相.

### 8.1 §1.5 探测元数据 (API Keys 用)
- `auth_header_format`: 请求头模板 (支持 `${key}` 插值)
- `models_endpoint_path`: 模型列表 Endpoint 路径 (OpenAI/Anthropic/DeepSeek 统一 `/v1/models`, Gemini 用 `/v1beta/models`, 不支持的 provider 写 `null`)

### 8.2 §1.5 + §5 模型能力维度 (LLM Roles 用)
- `compatible_sdks`: 该 Provider 理论支持的 SDK 协议集合
- §5 模型能力维度 = 万能字典容器 (max_tokens / 各 capabilities 字段)
  - **Minimal API 厂商** (OpenAI / DeepSeek / Ark): doc §5 **必填强制**, 作为 SSoT 唯一数据源
  - **丰富 API 厂商** (Anthropic / Gemini / OpenRouter): doc §5 退化为 fallback. 业务运行时优先用 GET /models 网络 Test 顺手提取的真实数据, 缓存缺失才退回 doc

### 8.3 废弃后端硬编码 ModelCapabilities Schema
- 删 `apps/studio/backend/app/models/llm_config.py` 的 `class ModelCapabilities(BaseModel)` (line 29-37)
- 删 `apps/studio/backend/app/services/llm_capability_table.py` (硬编码静态映射表)
- `ModelInfo.capabilities` 改成 `dict[str, Any] = Field(default_factory=dict)` (万能字典)
- frontend `apps/studio/frontend/src/api/llm.ts` 同步: 删 `ModelCapabilities` interface, `ModelInfo.capabilities?: Record<string, any>`
- 持久化兼容: 现有 `~/.studio/llm_credentials.json` 里 4-bool capabilities dict 无损解析为宽泛 dict, 零 [BREAKING]

---

## §9 修改范围与 Cutover 清理

### 9.1 Frontend
- `apps/studio/frontend/src/components/studio/SettingsPage.tsx` (ApiKeysTab 拆 Official 区 + Third-party 区, 删 type RadioGroup, 删 SDK Protocol RadioGroup)
- `apps/studio/frontend/src/components/studio/api-keys/AddProviderForm.tsx` (删 type RadioGroup, 默认折叠, 加 Cancel)
- `apps/studio/frontend/src/components/studio/api-keys/ProviderCard.tsx` (删 SDK Protocol RadioGroup, available_models chip 区 + 条件渲染 ManualModelTestPanel)
- 新增 `apps/studio/frontend/src/components/studio/api-keys/ManualModelTestPanel.tsx`
- `apps/studio/frontend/src/api/llm.ts` (删 ModelCapabilities interface, ModelInfo.capabilities 改 Record<string, any>)

### 9.2 Backend
- `apps/studio/backend/app/models/llm_config.py`: 删 `class ModelCapabilities`, `ModelInfo.capabilities` 改 `dict[str, Any]`
- `apps/studio/backend/app/routers/llm.py`:
  - 拓展现有 `POST /providers/test` (按 §3.1 + §3.2 GET /models + 双 Parser)
  - 新增 `GET /providers/notable-models?provider_key=<key>` (按 §3.3 从 provider metadata §4 返回候选)
  - 新增 `POST /providers/test-models` (按 §3.3 Manual Model Probing 1-token 鉴权)
  - 更新 `_infer_vendor` (改 base_url hostname 推断 provider_key)
- `apps/studio/backend/app/services/llm_provider_test.py`: 双 Parser 实现 + 顺手收集 capabilities 进 dict
- `apps/studio/backend/services/llm_provider_meta.py`: 更新 doc 文件寻址路径 (从 `docs/llm-providers/` 改 `apps/studio/backend/app/data/llm_providers/`)
- **删除** `apps/studio/backend/app/services/llm_capability_table.py`

### 9.3 File System 迁移
- 移动 `docs/llm-providers/*.md` (10 个文件: `anthropic.md` / `ark.md` / `deepseek.md` / `gemini.md` / `openai.md` / `openrouter.md` / `qiniu.md` / `wavespeed.md` / `_template.md` / `README.md`) → `apps/studio/backend/app/data/llm_providers/`
- 删除原 `docs/llm-providers/` 目录

### 9.4 Test 文件 (sop-05 cutover discipline)
- `apps/studio/backend/tests/services/test_llm_provider_test.py`
- `apps/studio/backend/tests/services/test_llm_provider_meta.py` (更新 doc 路径)
- `apps/studio/backend/tests/services/test_migrations.py`
- `apps/studio/backend/tests/services/test_llm_capability_table.py` (**删除**, 表本身已废弃)
- `apps/studio/backend/tests/integration/test_llm_e2e.py`
- `apps/studio/backend/tests/routers/test_llm_credentials_api.py`
- `apps/studio/frontend/src/components/studio/SettingsPage.test.tsx`
- `apps/studio/frontend/src/components/studio/api-keys/*.test.tsx` (相关组件 test)

### 9.5 Cutover: google_genai → google_genai
全局替换 (约 20+ 个业务/spec/config 文件; 不写死总数, 以实施时 `rg` 结果为准), 覆盖:
- Backend code 6 文件 (含 `models/llm_config.py` enum / `routers/llm.py` mapping / `services/llm_provider_test.py` probe / `services/llm_capability_table.py` 已删 / 测试 4)
- Frontend code 3 文件 (`api/llm.ts` / `SettingsPage.tsx` / `SettingsPage.test.tsx`)
- Graph-Agent 2 文件 (`packages/graph-agent/src/graph_agent/config/llm_config.py` / `tests/models/test_llm_client_manager.py`)
- Spec / config 6+ 文件 (`config/llm_roles.yaml` / `.kiro/specs/studio-api-keys-redesign/*.md`)
- Docs 4 文件 (`docs/llm-providers/gemini.md` / `_template.md` / `README.md` / `docs/engine/LLM_ROUTING_AND_FALLBACK.md`)

### 9.6 Cutover: openai_compatible 删除 (持久化 0 record, 零代价)
- 删 `apps/studio/backend/app/models/llm_config.py` enum
- 删 `apps/studio/backend/app/services/llm_provider_test.py` 中 wavespeed probe 函数 + dict entry + if 分支
- 删 `apps/studio/backend/app/routers/llm.py` 的 `_infer_vendor` wavespeed mapping
- 改 `apps/studio/backend/app/services/migrations.py` (跑 migration, 已有 mapping openai_compatible → openai_compatible)
- 删 `apps/studio/frontend/src/api/llm.ts` ProviderType union 中 'openai_compatible'
- 改 `apps/studio/frontend/src/components/studio/SettingsPage.test.tsx` 改 fixture provider_type
- 改 `apps/studio/backend/app/data/llm_providers/wavespeed.md` (迁移后路径): `compatible_sdks: [openai_compatible]`, 删 "Native SDK: WaveSpeed SDK" 假话

### 9.7 不动 (按宪法 6 "没提到的不要乱改")
- Settings General tab / LLM Roles tab UI (round 3 只动 API Keys tab)
- Canvas / 其他 frontend 业务代码
- `packages/graph-agent/` 其他代码 (除 LLM config 改名)
- `~/.studio/llm_credentials.json` 持久化数据 (改 schema 后用户数据自动兼容)
- `~/.studio/copilot.json` 等其他用户数据

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
