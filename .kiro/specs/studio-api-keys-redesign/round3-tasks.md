# API Keys Round 3 Implementation Plan

> **For agentic workers (ccb agents a1=Codex / a2=Gemini)**: 派任务前 master Claude 必读 spec `round3-design.md`。每个 task 是一个 self-contained deliverable, 含 files / scope / acceptance / commit message。TDD discipline 内置 (test 先于 impl, 跑测后再 commit)。

**Goal**: API Keys round 3 final design 落地 — Official Providers 预渲染 + Third-party 极简表单 + API Keys Test 收敛为鉴权和模型列表获取 + Manual Model Probing fallback + 元数据 SSoT 迁移 + capabilities dict 化。

**Architecture**: 4 PR 顺序执行 — PR-D1 元数据底座重塑 → PR-D2 Backend schema/test 探测升级 → PR-D3 Frontend 类型重构 + UI 拆分 → PR-D4 ManualModelTestPanel + 累加闭环。按 sop-05 cutover discipline, 每个 cutover PR 内完整清理, 不留双轨。

**Tech Stack**:
- Frontend: TypeScript + React + shadcn/ui + Tailwind CSS (Vite build)
- Backend: Python 3.12 + FastAPI + Pydantic (uv + pytest)
- Metadata: Markdown under `apps/studio/backend/app/data/llm_providers/`

**Spec**: `.kiro/specs/studio-api-keys-redesign/round3-design.md` + `.kiro/specs/llm-roles-setting/round1-design.md`

**Code Workspace**: `/home/sevenx/coding/baseline-v21`

---

## Tasks Scope 说明

本 tasks 仅含 **round 3 新发现的待实施改动**。round 2/3 早期已实施完成的功能 (如 ProviderCard AlertDialog 删除流程 / mask + eye toggle / Skeleton / Badge variant 颜色) **见 round3-design.md 现状描述, 不进 tasks**。

---

## File Structure (Locked, see spec §9)

### 新增 / 移动 (metadata)
- Move: `docs/llm-providers/*.md` → `apps/studio/backend/app/data/llm_providers/*.md`
- Delete: `docs/llm-providers/`
- Delete: `apps/studio/backend/app/services/llm_capability_table.py`
- Delete: `apps/studio/backend/tests/services/test_llm_capability_table.py`

### 修改 (backend)
- `apps/studio/backend/app/models/llm_config.py`
- `apps/studio/backend/app/routers/llm.py`
- `apps/studio/backend/app/services/llm_provider_test.py`
- `apps/studio/backend/services/llm_provider_meta.py`
- `apps/studio/backend/app/services/migrations.py`
- `apps/studio/backend/tests/services/test_llm_provider_meta.py`
- `apps/studio/backend/tests/services/test_llm_provider_test.py`
- `apps/studio/backend/tests/services/test_migrations.py`
- `apps/studio/backend/tests/integration/test_llm_e2e.py`
- `apps/studio/backend/tests/routers/test_llm_credentials_api.py`

### 新增 / 修改 (frontend)
- `apps/studio/frontend/src/api/llm.ts`
- `apps/studio/frontend/src/components/studio/SettingsPage.tsx`
- `apps/studio/frontend/src/components/studio/api-keys/AddProviderForm.tsx`
- `apps/studio/frontend/src/components/studio/api-keys/ProviderCard.tsx`
- `apps/studio/frontend/src/components/studio/api-keys/ManualModelTestPanel.tsx`
- `apps/studio/frontend/src/components/studio/SettingsPage.test.tsx`
- `apps/studio/frontend/src/components/studio/api-keys/*.test.tsx`

### 跨包 cutover
- `packages/graph-agent/src/graph_agent/config/llm_config.py`
- `packages/graph-agent/tests/models/test_llm_client_manager.py`
- `config/llm_roles.yaml`
- `.kiro/specs/studio-api-keys-redesign/*.md`
- `docs/engine/LLM_ROUTING_AND_FALLBACK.md`

---

# PR-D1: 元数据底座重塑 (纯数据/架构清洗, 不可拆分)

**Blocking**: 无
**Scope**: metadata SSoT 迁移 + SDK enum 命名 cutover + 废弃硬编码 capability table。
**Why one PR**: 文件移动、enum rename、wavespeed enum 删除、能力表删除彼此强耦合；拆开会产生半迁移状态, 违反 sop-05 cutover discipline。

## Task D1.1: 移动 provider metadata 到 app/data

**Files**:
- Move: `docs/llm-providers/*.md` → `apps/studio/backend/app/data/llm_providers/*.md`
- Delete: `docs/llm-providers/`
- Modify: `apps/studio/backend/services/llm_provider_meta.py`
- Modify: `apps/studio/backend/tests/services/test_llm_provider_meta.py`

**Scope**:
- 移动 10 个文件: `anthropic.md` / `ark.md` / `deepseek.md` / `gemini.md` / `openai.md` / `openrouter.md` / `qiniu.md` / `wavespeed.md` / `_template.md` / `README.md`
- provider_meta 寻址改为 `pathlib.Path(__file__).parents[1] / "data" / "llm_providers"` 或等价 app/data 路径
- 测试不再引用 `docs/llm-providers/`

**Acceptance**:
- `rg "docs/llm-providers" apps/studio/backend apps/studio/frontend packages config .kiro docs` 只允许历史说明或已明确过期文本
- `uv run pytest studio/backend/tests/services/test_llm_provider_meta.py -q` 通过

## Task D1.2: 删除硬编码 capability table

**Files**:
- Delete: `apps/studio/backend/app/services/llm_capability_table.py`
- Delete: `apps/studio/backend/tests/services/test_llm_capability_table.py`
- Modify callers/tests that import it

**Scope**:
- 所有 `lookup_capabilities` / `llm_capability_table` 引用清零
- capability SSoT 转为 provider metadata §5 + API Keys Test 网络返回缓存

**Acceptance**:
- `rg "llm_capability_table|lookup_capabilities" apps/studio/backend` 无生产引用
- backend targeted tests 通过

## Task D1.3: Cutover `google_genai` → `google_genai`

**Files**:
- Backend enum/mapping/tests
- Frontend type/tests
- Graph-Agent LLM config/tests
- `config/llm_roles.yaml`
- `.kiro/specs/studio-api-keys-redesign/*.md`
- provider metadata docs and engine docs

**Scope**:
- 全仓库替换 SDK enum 值 `google_genai` 为 `google_genai`
- 保持用户数据迁移兼容, 必要时在 migrations 加 alias

**Acceptance**:
- `rg "google_genai"` 只允许 migration 注释或历史 changelog, 生产配置无旧值
- backend tests + frontend typecheck + graph-agent relevant tests 通过

## Task D1.4: 删除 `openai_compatible`

**Files**:
- `apps/studio/backend/app/models/llm_config.py`
- `apps/studio/backend/app/services/llm_provider_test.py`
- `apps/studio/backend/app/routers/llm.py`
- `apps/studio/backend/app/services/migrations.py`
- `apps/studio/frontend/src/api/llm.ts`
- `apps/studio/frontend/src/components/studio/SettingsPage.test.tsx`
- `apps/studio/backend/app/data/llm_providers/wavespeed.md`

**Scope**:
- 删除 `openai_compatible` enum 和 probe 代码
- 迁移已有 mapping `openai_compatible → openai_compatible`
- `wavespeed.md` 改 `compatible_sdks: [openai_compatible]`, 删除 "Native SDK: WaveSpeed SDK" 相关表述

**Acceptance**:
- `rg "openai_compatible"` 只允许 migration 兼容注释
- 全 backend test 套通过

**Commit**:
```text
refactor(studio): migrate llm provider metadata to apps/studio/backend/app/data + cutover gemini/wavespeed naming
```

---

# PR-D2: Backend Schema 解放 + Test 探测升级 (打包不可拆)

**Blocking**: PR-D1 merged
**Scope**: `ModelCapabilities` dict 化、GET /models 双 parser、Manual Model Probing endpoint。
**Why one PR**: schema、parser、router response、tests 是一次 API contract cutover, 必须同步完成。

## Task D2.1: `ModelInfo.capabilities` 改万能字典

**Files**:
- `apps/studio/backend/app/models/llm_config.py`
- backend tests under `studio/backend/tests/`

**Scope**:
- 删除 `class ModelCapabilities(BaseModel)`
- `ModelInfo.capabilities` 改为 `dict[str, Any] = Field(default_factory=dict)`
- 保持现有 4-bool capabilities dict 持久化兼容

**Acceptance**:
- 新增/更新模型解析单测覆盖旧 4-bool dict 和任意新字段
- backend model/schema tests 通过

## Task D2.2: GET /models 双 Parser + capabilities 顺手收集

**Files**:
- `apps/studio/backend/app/services/llm_provider_test.py`
- `apps/studio/backend/tests/services/test_llm_provider_test.py`

**Scope**:
- OpenAI-style Parser: `data[].id`
- Gemini-style Parser: `models[].name`, 去 `models/` 前缀
- 解析 API 返回的 `max_input_tokens` / `max_tokens` / `context_length` / `inputTokenLimit` / `outputTokenLimit` / `capabilities.*` 等字段进 `ModelInfo.capabilities`

**Acceptance**:
- 单测覆盖 OpenAI-style、Gemini-style、unknown/empty response
- parser 输出 `list[ModelInfo]`

## Task D2.3: 拓展 `POST /providers/test`

**Files**:
- `apps/studio/backend/app/routers/llm.py`
- `apps/studio/backend/tests/routers/test_llm_credentials_api.py`

**Scope**:
- Test 按钮只负责联通性鉴权 + available_models 获取
- 读 provider metadata 的 `models_endpoint_path` + `auth_header_format`
- HTTP 200 提取 models; 401/403 抛鉴权错误; 5xx 标 unknown
- `_infer_vendor` 改为 base_url hostname 推断 provider_key

**Acceptance**:
- Router tests 覆盖 200/401/403/404/405/5xx
- Response schema 仍返回 `available_models: ModelInfo[]`

## Task D2.4: 新增 `POST /providers/test-models`

**Files**:
- `apps/studio/backend/app/routers/llm.py`
- `apps/studio/backend/app/services/llm_provider_test.py`
- `apps/studio/backend/tests/routers/test_llm_credentials_api.py`

**Scope**:
- Body: `provider_id` + `model_ids: string[]`
- 对每个 model id 并发发 1-token chat 请求
- HTTP 200/400/422 视为鉴权层放行, 加入 result
- HTTP 401/403 标 reject
- 通过的 model extend + dedupe 到 `state.available_models`, 不覆盖已有列表

**Acceptance**:
- 单测覆盖累加、去重、partial reject、鉴权失败
- 持久化 `~/.studio/llm_credentials.json` 兼容旧数据

**Commit**:
```text
feat(studio-backend): ModelCapabilities → dict schema + GET /models dual parser + POST /providers/test-models
```

---

# PR-D3: Frontend 类型重构 + UI 拆分

**Blocking**: PR-D2 merged
**Scope**: Frontend contract 对齐 + API Keys 两区 UI + 删除 SDK Protocol RadioGroup。
**Why one PR**: UI 拆区和类型 contract 同时变更, caller/tests 必须同步。

## Task D3.1: Frontend `ModelInfo.capabilities` dict 化

**Files**:
- `apps/studio/frontend/src/api/llm.ts`
- frontend tests/fixtures

**Scope**:
- 删除 `ModelCapabilities` interface
- `ModelInfo.capabilities?: Record<string, any>`
- 确认 `available_models` 仍是 `ModelInfo[]`
- `available_sdks` 保持 `string[]`

**Acceptance**:
- `npm --prefix apps/studio/frontend run typecheck` 通过
- 所有 fixtures 不再依赖 4-bool 固定 schema

## Task D3.2: SettingsPage 拆 Official / Third-party 两区

**Files**:
- `apps/studio/frontend/src/components/studio/SettingsPage.tsx`
- `apps/studio/frontend/src/components/studio/SettingsPage.test.tsx`

**Scope**:
- Official Providers 上半区预渲染 Anthropic / OpenAI / Gemini / DeepSeek / Ark 5 张 `ProviderCard`
- Official card 不展示 Provider Name / Base URL 输入
- 未配 API Key 状态显示 "Not configured", Test disabled
- Third-party Providers 下半区保持原行为, 默认折叠

**Acceptance**:
- RTL tests 覆盖 official 未配置、已配置、third-party populated/empty
- 不改 General tab / LLM Roles tab

## Task D3.3: AddProviderForm 极简化

**Files**:
- `apps/studio/frontend/src/components/studio/api-keys/AddProviderForm.tsx`
- related tests

**Scope**:
- 删除 Official / Third-party RadioGroup
- 删除 SDK Protocol RadioGroup
- Form 只保留 Provider Name / Base URL / API Key
- 默认折叠, `+ Add Provider` 展开, Submit 后收起并恢复 button 可点
- 添加 Cancel button

**Acceptance**:
- 交互测试覆盖展开、取消、提交成功收起、字段校验

## Task D3.4: ProviderCard 删除 SDK Protocol RadioGroup

**Files**:
- `apps/studio/frontend/src/components/studio/api-keys/ProviderCard.tsx`
- `apps/studio/frontend/src/components/studio/api-keys/ProviderCard.test.tsx`

**Scope**:
- 删除 SDK Protocol RadioGroup UI
- 保留 API Key input、Test button、status badge、available_models chip 区
- 不改变 mask/eye/delete/test button 已有契约

**Acceptance**:
- Existing ProviderCard tests 通过
- `rg "SDK Protocol|OpenAI Compatible|Anthropic" apps/studio/frontend/src/components/studio` 不再命中 API Keys tab 的可选 UI

**Commit**:
```text
refactor(studio-frontend): Official/Third-party two-zone API Keys UI + dict capabilities type
```

---

# PR-D4: Frontend ManualModelTestPanel + 累加闭环

**Blocking**: PR-D3 merged
**Scope**: GET /models fallback UI + notable models 候选 API + `POST /providers/test-models` 联调 + cumulative chips。
**Why one PR**: notable models 候选、fallback trigger、manual probing、chip 累加刷新是同一用户闭环。

## Task D4.0: 后端透传 Notable Models 候选

**Files**:
- `apps/studio/backend/app/routers/llm.py`
- `apps/studio/backend/services/llm_provider_meta.py`
- `apps/studio/backend/tests/routers/test_llm_credentials_api.py`
- `apps/studio/backend/tests/services/test_llm_provider_meta.py`

**Scope**:
- 新增 `GET /providers/notable-models?provider_key=<key>`
- 后端读取 `apps/studio/backend/app/data/llm_providers/<provider_key>.md` §4 Notable Models
- Response: `{"notable_models": ["claude-opus-4-1", ...]}`
- provider_key 不存在时返回 404 或空列表 (实施时按现有 router 错误风格统一)

**Acceptance**:
- Router/service tests 覆盖 known provider、unknown provider、空 §4
- 前端不直接读取 backend markdown 文件

## Task D4.1: 新增 ManualModelTestPanel

**Files**:
- New: `apps/studio/frontend/src/components/studio/api-keys/ManualModelTestPanel.tsx`
- Tests under `apps/studio/frontend/src/components/studio/api-keys/`

**Scope**:
- 受控 `testModelIds: string[]`
- `+ Add Model` 动态增行
- mount 时调用 `GET /providers/notable-models?provider_key=<key>`, 将返回候选用于 input placeholder / dropdown 默认值
- `[Test Models]` 调用后端验证

**Acceptance**:
- RTL tests 覆盖候选加载、add/remove/edit rows、button disabled/loading/error states

## Task D4.2: ProviderCard 条件渲染 fallback panel

**Files**:
- `apps/studio/frontend/src/components/studio/api-keys/ProviderCard.tsx`
- `ProviderCard.test.tsx`

**Scope**:
- GET /models 404/405 或 metadata `models_endpoint_path: null` / 缺失时显示 panel
- Panel 位于 Available Models chip 区下方
- Panel 常驻可见, 允许继续追加更多 model

**Acceptance**:
- Tests 覆盖 fallback visible / hidden / persistent

## Task D4.3: 累加逻辑与 API client

**Files**:
- `apps/studio/frontend/src/api/llm.ts`
- `ManualModelTestPanel.tsx`
- related tests

**Scope**:
- 新增 API client for `POST /providers/test-models`
- 通过 model extend + dedupe 到当前 `available_models`, 不是覆盖
- 前端刷新 Available Models chips

**Acceptance**:
- Tests 覆盖已有 `gpt-5` + 新增 `claude-opus-4-7` 后同时显示
- Tests 覆盖重复 model 不重复 chip

## Task D4.4: E2E smoke

**Files**:
- Frontend integration/e2e tests where existing pattern fits

**Scope**:
- Mock API Keys fallback flow
- Verify manual model submit 后 chip 区更新

**Acceptance**:
- Frontend typecheck + test 全过
- Backend full tests 保持通过

**Commit**:
```text
feat(studio-frontend): ManualModelTestPanel + cumulative model probing
```

---

## Self-Review (master Claude PM 跑完前自检)

### 1. Spec coverage scan
- `round3-design.md` §2/§3/§8/§9 与本 plan 一致
- `llm-roles-setting/round1-design.md` 已接走 SDK per-model 探测和 capabilities display
- API Keys Test 不再做 SDK 探测, 只做鉴权 + models

### 2. Cutover scan
- `google_genai` rename 与 `openai_compatible` 删除均在 PR-D1 一次完成
- `ModelCapabilities` 删除与 `ModelInfo.capabilities` dict 化在 PR-D2/D3 同步完成
- `available_models` 保持 `ModelInfo[]`, 不回到 `string[]`

### 3. Boundary scan
- 不动 Settings General tab / LLM Roles tab UI
- 不动 Canvas / 其他 frontend 业务代码
- 不动 `~/.studio/llm_credentials.json` / `~/.studio/copilot.json` 等用户数据

## Execution Plan (master Claude PM 推进路径)

1. Review 本 spec 和 tasks 草案
2. 派 PR-D1: metadata/cutover 底座
3. 派 PR-D2: backend schema + endpoints
4. 派 PR-D3: frontend type + two-zone UI
5. 派 PR-D4: ManualModelTestPanel fallback 闭环
