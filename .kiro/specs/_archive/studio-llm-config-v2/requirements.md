# Studio LLM Configuration Architecture (v2) - Requirements

**Status**: v0.1 — 按 user 2026-05-13 §2 verbatim 决策重整, 2026-05-14
**Author**: a2 Gemini
**Related Requirements**: (2026-05-13 §2 verbatim quotes)

## 1. 核心业务诉求与纠偏

过去 V1 / V2.5 / V3 系列设计中出现严重漂移，核心原因是没有对齐用户关于“并进同一套后端底层”的约束。本规格书建立在以下不可妥协的真理之上：

- `config/llm_roles.yaml` 是系统全局唯一的 **Single Source of Truth**。
- `~/.studio/copilot.json` 4-backend 体系 (claude/deepseek/gemini/openai) **正式废弃**。
- 不存在 `active_provider_id` 或 `active_model` 作为全局 Settings 维度的“配置”。用户在 Copilot 界面下拉切换的模型，属于**运行时局部状态 (Runtime State)**。

## 2. 验收标准

### R1: SettingsPage 职责完全拆分
Settings 面板必须包含两个清晰独立的 Tab (或视图)：
- **Tab A (API Keys)**：管理所有本地存储的 Provider API Key 和 Base URL。提供测试联通性功能。不提供“设为默认”功能。
- **Tab B (LLM Roles)**：管理 `llm_roles.yaml` 的编排。定义不同的 Role (如 `copilot_chat`, `analyst`, `premium`) 下，Model 的 fallback 优先级和关联 Provider。

### R2: 凭据存储分离
- API Keys 等敏感数据存放在 `~/.studio/llm_credentials.json` (0600 权限) 中，只含 `provider_code` 及其对应的 credential。
- 系统在运行时将这些 credentials **Patch 到环境变量**或传给 `ModelResolver`，供 `llm_roles.yaml` 中配置的 fallback 链条使用。

### R3: Copilot 专属 Role 接入
- `config/llm_roles.yaml` 必须包含专属于 Copilot 的 role 节点 (如 `copilot_chat`)。
- 前端 Copilot 面板的模型下拉列表，需从后端的 `GET /api/llm/roles/copilot_chat` 拉取支持的模型列表。
- 用户在下拉列表中选择后，发起请求须将选中的 Model ID 发往后端，后端以此作强力 Override。

### R4: 旧配置废弃与零迁移 (Migration Strategy)
- 原型期“做错就推翻”，**绝不向后兼容**。旧的 `~/.studio/copilot.json` 及其中的 `V1_5_PLACEHOLDER` 概念直接废弃。
- 系统启动时直接无视旧文件，要求用户在新的 Settings 页面重新为 `llm_credentials.json` 输入 Key。

### R5: 安全与隧道鉴权保护 (Security)
- Test 端点和凭据 PUT 端点是高危接口，**必须**受到 `STUDIO_DEV_TUNNEL_TOKEN` (开发隧道同源) 或 `STUDIO_API_TOKEN` (Tauri 同源) 的 Bearer 鉴权保护。
- Test 失败时的报错回包**绝不能回显 API Key**（防反向 sniff 攻击）。