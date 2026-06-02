# llm-provider-config (studio feature) — Baseline (当下代码实现逻辑)

> **Status**: Filled by a1 (Codex), 2026-05-20
> **Scope**: Provider credential 配置、模型测试、LLM Roles、per-role / per-phase 模型选择
> **配套**: 见 [INDEX.md](../../../INDEX.md) 5 维模板 + cross-link 规则 + writing conventions。
>
> 📍 **当前状态补注**：本正文为 **2026-05-20 代码快照**（a1/Codex，5 维模板）。2026-05-25 registry hard
> cutover 后的当前真实行为与已知回归见文末「## 当前真实状态与回归」——**涉及当前行为以该节为准**。

## UI/UX

Settings 页面有 General、API Keys、LLM Roles 三个 tab，导航和内容挂载在 `SettingsPageContent`，见 `apps/studio/frontend/src/components/studio/settings/SettingsPageContent.tsx:41` 到 `apps/studio/frontend/src/components/studio/settings/SettingsPageContent.tsx:80`。本 feature 主要覆盖 API Keys 和 LLM Roles。

API Keys tab 由 `ApiKeysTab` 渲染，顶部说明这是 local LLM provider credentials 且 auto-save，见 `apps/studio/frontend/src/components/studio/settings/api-keys/ApiKeysTab.tsx:46` 到 `apps/studio/frontend/src/components/studio/settings/api-keys/ApiKeysTab.tsx:81`。官方 providers 包括 Anthropic、OpenAI、Gemini、DeepSeek、Ark，定义在 `apps/studio/frontend/src/components/studio/settings/provider-utils.ts:5` 到 `apps/studio/frontend/src/components/studio/settings/provider-utils.ts:11`。

API Keys UI 分为 official providers 与 third-party providers。官方 provider card 列表见 `apps/studio/frontend/src/components/studio/settings/api-keys/ApiKeysTab.tsx:88` 到 `apps/studio/frontend/src/components/studio/settings/api-keys/ApiKeysTab.tsx:107`；第三方 provider 支持 Add Provider 表单、删除、测试和手动模型列表，见 `apps/studio/frontend/src/components/studio/settings/api-keys/ApiKeysTab.tsx:109` 到 `apps/studio/frontend/src/components/studio/settings/api-keys/ApiKeysTab.tsx:151`。

LLM Roles tab 允许选择 role、设置 active model、打开或关闭 fallback，并查看 role 下模型与 provider chain，见 `apps/studio/frontend/src/components/studio/settings/LlmRolesTab.tsx:65` 到 `apps/studio/frontend/src/components/studio/settings/LlmRolesTab.tsx:151`。新增模型和新增 provider 当前 disabled，见 `apps/studio/frontend/src/components/studio/settings/LlmRolesTab.tsx:143` 到 `apps/studio/frontend/src/components/studio/settings/LlmRolesTab.tsx:151`、`apps/studio/frontend/src/components/studio/settings/LlmRolesTab.tsx:239` 到 `apps/studio/frontend/src/components/studio/settings/LlmRolesTab.tsx:247`。

## 前端逻辑

SettingsPage 负责加载 credentials、roles 和保存状态。credentials 在页面打开时通过 `getCredentials` 拉取，见 `apps/studio/frontend/src/components/studio/settings/SettingsPage.tsx:48` 到 `apps/studio/frontend/src/components/studio/settings/SettingsPage.tsx:66`；roles 在进入 llm_roles tab 时通过 `getRoles` 拉取，见 `apps/studio/frontend/src/components/studio/settings/SettingsPage.tsx:68` 到 `apps/studio/frontend/src/components/studio/settings/SettingsPage.tsx:83`。

provider 字段更新会先更新本地 draft，再调度保存，见 `apps/studio/frontend/src/components/studio/settings/SettingsPage.tsx:85` 到 `apps/studio/frontend/src/components/studio/settings/SettingsPage.tsx:110`。添加 provider 和删除 provider 分别在 `apps/studio/frontend/src/components/studio/settings/SettingsPage.tsx:118` 到 `apps/studio/frontend/src/components/studio/settings/SettingsPage.tsx:130`。

Provider 测试由 `runProviderTest` 触发，调用 `testProvider`，并把测试结果写回本地 credentials state；成功/失败都会 toast，见 `apps/studio/frontend/src/components/studio/settings/SettingsPage.tsx:140` 到 `apps/studio/frontend/src/components/studio/settings/SettingsPage.tsx:186`。手动模型测试和 notable models API 在 `apps/studio/frontend/src/api/llm.ts:185` 到 `apps/studio/frontend/src/api/llm.ts:197`。

Roles 编辑通过纯函数更新 draft。`updateActiveModel`、`toggleModelFallback`、移动/删除 provider 和 model、校验 role draft 等逻辑在 `apps/studio/frontend/src/components/studio/settings/role-utils.ts:7` 到 `apps/studio/frontend/src/components/studio/settings/role-utils.ts:82`。保存 roles 前会验证引用完整性，见 `apps/studio/frontend/src/components/studio/settings/SettingsPage.tsx:194` 到 `apps/studio/frontend/src/components/studio/settings/SettingsPage.tsx:213`。

per-phase override 当前不属于 Settings 的直接编辑面。phase 节点会读取 `llm_role` 并显示在节点数据里，见 `apps/studio/frontend/src/components/GraphCanvas/build-nodes.ts:162` 到 `apps/studio/frontend/src/components/GraphCanvas/build-nodes.ts:184`；创建向导生成 graph phase 时会写 `llm_role`，见 `apps/studio/frontend/src/templates/skillMdGenerator.ts:89` 到 `apps/studio/frontend/src/templates/skillMdGenerator.ts:94`。Settings 只编辑 role registry 和 provider credentials。

## 后端功能

credentials 服务把配置保存到 `~/.studio/llm_credentials.json`，路径定义在 `apps/studio/backend/app/services/llm_credentials.py:26` 到 `apps/studio/backend/app/services/llm_credentials.py:30`。加载、保存和响应序列化见 `apps/studio/backend/app/services/llm_credentials.py:32` 到 `apps/studio/backend/app/services/llm_credentials.py:68`。

credential 文件写入使用 atomic replace，并把目录权限设为 0700、文件权限设为 0600，见 `apps/studio/backend/app/services/llm_credentials.py:121` 到 `apps/studio/backend/app/services/llm_credentials.py:147`。测试结果会被持久化回 provider state，见 `apps/studio/backend/app/services/llm_credentials.py:71` 到 `apps/studio/backend/app/services/llm_credentials.py:118`。

Roles 服务用 ruamel yaml round-trip 读取和保存 LLM roles 文件，见 `apps/studio/backend/app/services/llm_roles.py:24` 到 `apps/studio/backend/app/services/llm_roles.py:48`。保存前会验证 provider/model 引用，见 `apps/studio/backend/app/services/llm_roles.py:56` 到 `apps/studio/backend/app/services/llm_roles.py:80`，写入同样走临时文件替换，见 `apps/studio/backend/app/services/llm_roles.py:103` 到 `apps/studio/backend/app/services/llm_roles.py:118`。

Provider test endpoint 会检查缺失 key、按 provider/model 调用测试服务、保存测试结果并返回响应，见 `apps/studio/backend/app/routers/llm.py:213` 到 `apps/studio/backend/app/routers/llm.py:265`。notable models 和 batch model test endpoint 见 `apps/studio/backend/app/routers/llm.py:268` 到 `apps/studio/backend/app/routers/llm.py:335`。

## API

前端 API 类型定义在 `apps/studio/frontend/src/api/llm.ts:3` 到 `apps/studio/frontend/src/api/llm.ts:160`。credentials API 包括 `getCredentials`、`putCredentials`、`testProvider`，见 `apps/studio/frontend/src/api/llm.ts:163` 到 `apps/studio/frontend/src/api/llm.ts:183`；roles API 包括 `getRoles`、`getRole`、`putRoles`，见 `apps/studio/frontend/src/api/llm.ts:199` 到 `apps/studio/frontend/src/api/llm.ts:212`。

后端 credentials endpoint：GET 在 `apps/studio/backend/app/routers/llm.py:148` 到 `apps/studio/backend/app/routers/llm.py:153`，PUT 在 `apps/studio/backend/app/routers/llm.py:156` 到 `apps/studio/backend/app/routers/llm.py:210`。PUT 会保留已有 api_key：如果 incoming 为空但已有 provider 有 key，则沿用旧 key，见 `apps/studio/backend/app/routers/llm.py:156` 到 `apps/studio/backend/app/routers/llm.py:210`。

后端 roles endpoint：GET roles 在 `apps/studio/backend/app/routers/llm.py:338` 到 `apps/studio/backend/app/routers/llm.py:342`，GET role 在 `apps/studio/backend/app/routers/llm.py:345` 到 `apps/studio/backend/app/routers/llm.py:353`，PUT roles 在 `apps/studio/backend/app/routers/llm.py:356` 到 `apps/studio/backend/app/routers/llm.py:368`。

## Data Model / State

credential 前端模型包含 provider code/name/type/base_url/api_key、models、test status/message/tested_at，见 `apps/studio/frontend/src/api/llm.ts:35` 到 `apps/studio/frontend/src/api/llm.ts:65`。后端存储模型 `LLMCredentialsFile` 在 `apps/studio/backend/app/models/llm_config.py:127` 到 `apps/studio/backend/app/models/llm_config.py:133`。

roles 模型包含 provider entries、model entries、role entries 和 active_model/allow_fallback，前端类型见 `apps/studio/frontend/src/api/llm.ts:118` 到 `apps/studio/frontend/src/api/llm.ts:160`，后端 Pydantic 模型见 `apps/studio/backend/app/models/llm_config.py:136` 到 `apps/studio/backend/app/models/llm_config.py:224`。

SettingsPage state 包括 credentials、rolesData、selectedRole、rolesLoading、testingProviderCode、saveState 等，见 `apps/studio/frontend/src/components/studio/settings/SettingsPage.tsx:15` 到 `apps/studio/frontend/src/components/studio/settings/SettingsPage.tsx:24`。provider drafts 会补齐官方 provider placeholder，并把自定义 provider 分到 third-party，见 `apps/studio/frontend/src/components/studio/settings/provider-utils.ts:55` 到 `apps/studio/frontend/src/components/studio/settings/provider-utils.ts:72`。

## Cross-feature interaction

与 Copilot：Copilot 默认解析 `copilot_chat` role，或使用用户选择的 `model_override`，见 `apps/studio/backend/app/services/copilot.py:372` 到 `apps/studio/backend/app/services/copilot.py:381`。Copilot 面板如何读取 roles/credentials 见 [copilot-assistance baseline](../copilot-assistance/baseline.md)。

与 skill 创建/编辑：skill generator 会把 graph phase 的 `llm_role` 写入 frontmatter，见 `apps/studio/frontend/src/templates/skillMdGenerator.ts:89` 到 `apps/studio/frontend/src/templates/skillMdGenerator.ts:94`；多文件编辑器可直接编辑这些文件，见 [multi-file-editor baseline](../multi-file-editor/baseline.md)。

与运行：后端 run/coplanar 服务最终依赖 graph_agent 的 provider resolution；Studio Settings 只维护本地 provider credential 和 roles 文件，不直接触发 run。运行 trace 与 provider 错误呈现见 [trace-visualization baseline](../trace-visualization/baseline.md)。

---

## 当前真实状态与回归（2026-06-01 审计补注）

> 上文正文为 **2026-05-20 代码快照**。以下为 2026-05-25 registry hard cutover 后的当前真实状态，
> **涉及当前行为以本节为准**。修复方向见 `.kiro/specs/studio-llm-gateway-redesign/`。

- **桌面架构**：Studio 是 Tauri 2 应用，Python FastAPI 后端由 `tauri/src/sidecar.rs` 以
  `uvicorn app.main:app`（loopback + 随机 Bearer token）作为 sidecar 拉起；后端同进程 import
  `graph-agent-gateway`。后端按"可移植服务"设计（可插拔 AuthProvider/Storage、多 token、env 注入、
  skills 模块已 `user_id` 隔离），但 **LLM 配置模块是其中唯一的"桌面单用户孤岛"**（无 `user_id`、
  全局单文件、明文密钥）。
- **持久化路径已变更**：credentials/roles 实际存用户 AppData（macOS
  `~/Library/Application Support/AgentStudio/llm/`，可经 `STUDIO_LLM_CREDENTIALS_PATH` /
  `STUDIO_LLM_ROLES_PATH` 覆盖），**非**上文 §后端功能 写的 `~/.studio/`。
- **回归 1（保存死锁）**：`_save_roles_with_active_routes`（`routers/llm.py:4726`）以
  `known_route_ids=active_route_ids` 硬校验整份 YAML，任一角色引用未配置路由 → 整体 400，锁死增删改。
  （2026-05-25 `c8bfb93f` 引入；旧版 `validate_references(data)` 不耦合凭证。）
- **回归 2（resolver 硬崩）**：`graph-agent-gateway` 的 `registry/resolver.py:57` 对 fallback_chain
  第一个未配置路由直接 `raise`，无优雅跳过、无 WARNING。（2026-05-25 `ecab5fe1` cutover 替换了旧
  `resolve_role` 的 `continue`+WARNING。）
- **测试状态易失**：route 最终 status 已落 `provider_routes[].status`（后端 SSOT），但前端
  `routeStatusOverrides`/`roleTestStates` 自建并行内存态，切 Tab/重启即丢；test job 仅在内存（`llm.py:232`）。

修复方向见 `.kiro/specs/studio-llm-gateway-redesign/{requirements,design,tasks}.md`。
