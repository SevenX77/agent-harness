# Studio LLM Config v2 Tasks
总预估: ~35h。关键 milestone: T6 完成 Tab 1 demo；T9 完成 e2e 全通。
依赖图: T1 -> T2 -> T3 -> T4 -> T5 -> T8；T2 -> T6 -> T7 -> T8；T8 -> T9。
## T1. Backend credentials schema and env patch foundation
**目标**: 建立 `~/.studio/llm_credentials.json` 作为本地密钥池，并把保存的 provider key/base_url patch 到运行时环境。v2 零迁移且忽略旧 `copilot.json`。
**改动 file** (按顺序列):
- `apps/studio/backend/app/models/llm_config.py` (新建)
- `apps/studio/backend/app/services/llm_credentials.py` (新建)
- `apps/studio/backend/app/services/llm_env.py` (新建)
- `apps/studio/backend/tests/services/test_llm_credentials.py` (新建)
**DoD (Definition of Done)**:
- [ ] `providers: [{ provider_code, api_key, base_url }]` 可原子读写，文件权限为 `0600`
- [ ] env patch 支持 `api_key_env`、`api_key_env_fallback`、`base_url`，空 key 不覆盖已有 env
- [ ] 测试覆盖读写、权限、fallback、忽略 `~/.studio/copilot.json`
**依赖**: 无
**预估**: ~4h
**Reviewer**: a2 audit
## T2. LLM credentials and provider test API
**目标**: 提供 v2 credentials 读写和 provider 连通性测试 API，并对写入/测试端点做 token 保护。响应和日志不得泄露 API key。
**改动 file** (按顺序列):
- `apps/studio/backend/app/routers/llm.py` (新建)
- `apps/studio/backend/app/services/llm_provider_test.py` (新建)
- `apps/studio/backend/app/main.py`
- `apps/studio/backend/tests/routers/test_llm_credentials_api.py` (新建)
**DoD (Definition of Done)**:
- [ ] `GET/PUT /api/llm/credentials` 和 `POST /api/llm/providers/test` 可用
- [ ] PUT/test 要求 `STUDIO_DEV_TUNNEL_TOKEN` 或 `STUDIO_API_TOKEN`
- [ ] provider test 支持四类 provider，且测试覆盖 auth、shape、错误映射、无 key 泄露
- [ ] `POST /api/llm/providers/test` 显式接收并处理请求体中的 `provider_type` 字段，以决定实例化哪种 API Client (而非反查 yaml)
**依赖**: T1
**预估**: ~5h
**Reviewer**: a2 audit
## T3. YAML roles service and roles API
**目标**: 用 `config/llm_roles.yaml` 作为 roles/models/providers 的可编辑源，并通过 round-trip YAML 写回保留注释和顺序。
**改动 file** (按顺序列):
- `apps/studio/backend/app/services/llm_roles.py` (新建)
- `apps/studio/backend/app/models/llm_config.py`
- `apps/studio/backend/app/routers/llm.py`
- `apps/studio/backend/tests/services/test_llm_roles.py` (新建)
**DoD (Definition of Done)**:
- [ ] `GET/PUT /api/llm/roles` 和 `GET /api/llm/roles/{role_name}` 可用
- [ ] 写入前校验 role -> model -> provider 引用完整性
- [ ] `ruamel.yaml` 保留未编辑节点注释/顺序，测试覆盖 active_model、fallback/provider order、非法引用
**依赖**: T1, T2
**预估**: ~4h
**Reviewer**: a2 audit
## T4. Add `copilot_chat` role to `llm_roles.yaml`
**目标**: 在共享 role 配置里加入 Copilot 专用角色，使 Copilot 默认走 `CL46T` 并可 fallback 到 `DS32R`。
**改动 file** (按顺序列):
- `config/llm_roles.yaml`
- `packages/graph-agent/tests/config/test_llm_config.py`
**DoD (Definition of Done)**:
- [ ] `roles.copilot_chat` 存在，active model 为 `CL46T`
- [ ] fallback 链包含 `DS32R`，且所有 model/provider code 都已注册
- [ ] `resolve_role("copilot_chat")` 和相关 `resolve_model()` 测试通过
**依赖**: T3
**预估**: ~1h
**Reviewer**: a2 audit
## T5. Copilot backend switches to ModelResolver role override
**目标**: Copilot WebSocket 不再依赖 v1 backend/credential schema，而是用 `ModelResolver(role="copilot_chat", model_override=...)` 解析运行时模型。
**改动 file** (按顺序列):
- `apps/studio/backend/app/services/copilot.py`
- `apps/studio/backend/app/routers/copilot.py`
- `apps/studio/backend/app/models/copilot.py`
- `apps/studio/backend/tests/routers/test_copilot_ws.py`
**DoD (Definition of Done)**:
- [ ] WebSocket 接收 runtime selected model override，未选择时使用 `copilot_chat.active_model`
- [ ] Copilot options 注入 `ANTHROPIC_BASE_URL` 和 `ANTHROPIC_API_KEY`
- [ ] active flow 不读取 `~/.studio/copilot.json`，测试覆盖 override、默认模型、缺 key、事件流兼容
**依赖**: T1, T3, T4
**预估**: ~4h
**Reviewer**: a2 audit
## T6. Settings Tab 1 API Keys credentials pool
**目标**: 将 Settings 第一页改成 API Keys，按 YAML provider 元数据渲染密钥池，完成保存和 provider test 的前后端闭环。
**改动 file** (按顺序列):
- `apps/studio/frontend/src/api/llm.ts` (新建)
- `apps/studio/frontend/src/components/studio/SettingsPage.tsx`
- `apps/studio/frontend/src/components/studio/__tests__/SettingsPage.test.tsx`
**DoD (Definition of Done)**:
- [ ] UI 从 `/api/llm/credentials` 渲染 provider，服务端只回 `has_key`
- [ ] API key 仅在本地输入态，保留 Eye toggle、`new-password`、无 `name`、650ms debounce
- [ ] Test 调 `/api/llm/providers/test`，输入变化不清空测试状态；Milestone: Tab 1 可保存并测试 API key
- [ ] Vendor 分组 (Anthropic/DeepSeek/Gemini/OpenAI/WaveSpeed) 为前端 UI 概念，前端代码内静态 `provider_code → vendor label` 映射；后端 API/yaml schema 不引入 vendor 字段
**依赖**: T2
**预估**: ~4h
**Reviewer**: a2 audit
## T7. Settings Tab 2 LLM Roles and fallback editor
**目标**: 添加 LLM Roles tab，让用户编辑 role active model、fallback 顺序和 provider 顺序，同时隐藏非目标高级配置。
**改动 file** (按顺序列):
- `apps/studio/frontend/src/api/llm.ts`
- `apps/studio/frontend/src/components/studio/SettingsPage.tsx`
- `apps/studio/frontend/src/components/studio/__tests__/SettingsPage.test.tsx`
**DoD (Definition of Done)**:
- [ ] UI 可读写 `/api/llm/roles`，包含 `copilot_chat`
- [ ] 可编辑 active_model、model fallback order、provider order
- [ ] 隐藏 `peer_model_groups`、`circuit_breaker`、`deerflow_*`，测试覆盖保存成功/失败
**依赖**: T3, T4, T6
**预估**: ~4h
**Reviewer**: a2 audit
## T8. Copilot model picker uses `copilot_chat`
**目标**: Copilot 面板模型选择器改为读取 `copilot_chat` role，并把选择作为 runtime override 传给 WebSocket。
**改动 file** (按顺序列):
- `apps/studio/frontend/src/components/copilot/model-picker.tsx`
- `apps/studio/frontend/src/components/copilot/copilot-panel.tsx`
- `apps/studio/frontend/src/api/llm.ts`
- `apps/studio/frontend/src/components/copilot/__tests__/model-picker.test.tsx`
**DoD (Definition of Done)**:
- [ ] picker 从 `GET /api/llm/roles/copilot_chat` 渲染模型
- [ ] 缺少可用 key/env 的 provider/model 被禁用或标记不可用
- [ ] selected model override 随 WebSocket 请求发送，且不再依赖 `active_backend`/v1 credentials shape
**依赖**: T5, T7
**预估**: ~3h
**Reviewer**: a2 audit
## T9. Cleanup, integration tests, and e2e green
**目标**: 清理 v1 残留入口，补齐后端、前端、e2e 集成覆盖，证明 v2 API Keys + Roles + Copilot override 全链路可用。
**改动 file** (按顺序列):
- `apps/studio/backend/app/services/copilot_credentials.py` (删除或从 active flow 移除)
- `apps/studio/frontend/src/api/copilot.ts`
- `apps/studio/e2e/llm-config-v2.spec.ts` (新建)
- `apps/studio/backend/tests/integration/test_llm_config_v2.py` (新建)
**DoD (Definition of Done)**:
- [ ] v1 Copilot credential/backend shim 不在 active code path 中
- [ ] e2e 覆盖保存 key、测试 provider、修改 `copilot_chat`、Copilot 发送 selected model
- [ ] backend/frontend targeted tests、lint/type checks、e2e 全通；Milestone: v2 flow fully green
**依赖**: T6, T7, T8
**预估**: ~6h
**Reviewer**: a3
