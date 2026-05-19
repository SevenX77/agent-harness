# Design Doc: Studio LLM Configuration Architecture (v2)

**Status**: v0.1 — 按 user 2026-05-13 §2 verbatim 决策重整, 2026-05-14
**Author**: a2 Gemini
**Related Requirements**: `requirements.md` (2026-05-13 §2), `config/llm_roles.yaml`

## 1. 架构目标与职责拓扑

基于 User 明确指示：“LLM 调用走 graph agent 的 role>model>provider 的 fallback 链条” 且 “应该有两个页面, 一个只管 APIkey 通不通, 一个管 fallback 编排”，以及废除全部 `active_model` 与 `active_provider` 配置态的指示，我们重新定义 Studio 的 LLM 配置架构：

### 1.1 职责拓扑 (两页 / 两 Tab 设计)
在 Studio 的 Settings 界面中，将采用两个完全隔离的 Tab（或页面）来管理 LLM 设置：

- **Tab 1: API Keys & Providers (凭据池)**
  - **职责**：仅负责配置底层大模型厂商（Vendor）和接入端点（Provider）的认证信息（API Key）及反代地址（Base URL）。
  - **核心能力**：热加载原子保存、测试连通性（Test Connection）。
  - **状态**：**不包含**任何 "Active / Default" 概念。它只是一个凭据池。

- **Tab 2: LLM Roles & Fallback (编排引擎)**
  - **职责**：可视化编辑 `config/llm_roles.yaml`，管理 Role -> Model -> Provider 的 Fallback 优先级链条。
  - **核心能力**：配置 `balanced`, `premium`, `copilot_chat` 等功能角色在遇到限流时该如何向下兼容。

### 1.2 Copilot Panel 与 Settings 的关系
- **SettingsPage** 提供底座：定义好了有哪些 Provider 通道 (Tab 1)，以及有哪些 Role 链条 (Tab 2)。
- **Copilot Panel (运行时)**：Cursor 风格的顶部下拉 ModelPicker，它的数据源应该是读取自 `config/llm_roles.yaml` 里的某个预定义的角色（例如 `copilot_chat`）。用户在下拉框中选择的是**具体的 Model**（例如切换为 `DS32R`），Copilot 运行时会在内存 / LocalStorage 保存用户的这一**运行时状态**，并在下一次 WebSocket query 时携带此信息，交由后端的 `ModelResolver` 处理。

## 2. Storage Schema 拓扑

### 2.1 凭据存储: `~/.studio/llm_credentials.json`
- **定位**：纯本地 `0600` 权限的明文文件，只存敏感信息和私有化网络配置。
- **与 YAML 的衔接机制**：生产环境的 `llm_roles.yaml` 定义了 `api_key_env` 及其 fallback。Studio Sidecar 在启动和每次凭据更新后，遍历 YAML 中的 providers 列表，获取每个 provider 的 `api_key_env`，然后将 `llm_credentials.json` 里对应的 key 直接**Patch 到 `os.environ` 中**。这样底层 Client 和 `ModelResolver` 依然通过环境变量获取凭据，逻辑无缝闭环。Yaml 文件绝对不写明文密钥。

```json
// ~/.studio/llm_credentials.json 示例
{
  "providers": [
    {
      "provider_code": "OC_CL_ANT",
      "api_key": "sk-ant-...",
      "base_url": ""
    },
    {
      "provider_code": "DS",
      "api_key": "sk-deepseek-...",
      "base_url": "https://api.deepseek.com"
    }
  ]
}
```

### 2.2 编排存储: `config/llm_roles.yaml`
- **定位**：代码库级别提交的配置文件，Single Source of Truth。
- **新增 Copilot 角色**：在 `roles` 下增加 `copilot_chat` (名称供讨论)，使得 Copilot 也能享受 graph_agent 原生的模型回退保护。

```yaml
  copilot_chat:
    temperature: 0.7
    model_fallback: true
    active_model: CL46T
    models:
      CL46T: { providers: [OC_CL_ANT, OC_CL, WS_LLM] }
      DS32R: { providers: [DS, OC_DS] }
```

## 3. 后端 API 契约

### 3.1 凭据池 API (给 Tab 1 用)
- **`GET /api/llm/credentials`**: 读取 `llm_credentials.json`，返回包含明文 API Key 的 Provider 列表。
- **`PUT /api/llm/credentials`**: 接收前端 debounce 传来的配置，全量覆盖并原子写入 `llm_credentials.json`。
- **`POST /api/llm/providers/test`**: 接收 `{provider_code, provider_type, api_key, base_url}` 进行单点测试（不写盘）。必须传递 `provider_type` (如 `anthropic_compatible`) 才能让后端知道实例化哪种 client 进行 Ping。返回 Status (OK/Fail) 和延迟。

### 3.2 角色编排 API (给 Tab 2 用)
- **`GET /api/llm/roles`**: 读取并解析 `config/llm_roles.yaml`，返回结构化的 Role / Model / Provider DAG。
- **`PUT /api/llm/roles`**: 接收前端可视化的拖拽/修改结果，写回 `config/llm_roles.yaml`。**必须强制使用 `ruamel.yaml` 库**，以确保 Round-trip 时保留原有的大量中文注释和格式。

## 4. 前端 UI 设计 (Mockup)

### 4.1 Tab 1: API Keys & Providers (凭据池)
```text
======================================================================
                     Settings > API Keys (Local)
======================================================================
▼ Anthropic
  • Official API                                         [ Test ]
    API Key:  [••••••••••••••••••••] [Eye]
    Status: ✓ Connected (150ms)
  • [ + Add Custom Provider ]

▼ DeepSeek
  • Official API                                         [ Test ]
    API Key:  [sk-deepseek-12345   ] [Eye]
    Status: ✓ Connected (87ms)
  • Custom: OneChats-DS                                  [ Test ] [ × ]
    API Key:  [sk-oc-12345         ] [Eye]
    Base URL: [ https://chatapi.onechats.ai/v1 ]
    Status: ⚠ Untested
  • [ + Add Custom Provider ]

▼ ...
======================================================================
```

### 4.2 Tab 2: LLM Roles & Fallback (编排引擎)
```text
======================================================================
                     Settings > LLM Roles (YAML)
======================================================================
Role: [ copilot_chat v ] (Fallback enabled: ON)

Fallback Chain:
1. Model: [ Claude Sonnet 4.6 Thinking (CL46T) ] 
   -> Providers: OC_CL_ANT -> OC_CL -> WS_LLM
2. Model: [ DeepSeek-V4 Pro (DS32R) ]
   -> Providers: DS -> OC_DS

[ + Add Fallback Model ]
======================================================================
```

## 5. Spec 重组建议 (最终树状图)

本次架构梳理后，我们将废弃那些“自建 4-backend 体系”与“状态粘连”的历史 Spec，收敛为以下全新的 Spec：

```text
.kiro/specs/studio-llm-config-v2/
├── requirements.md         # (新建) 确立 2 个 Tab 分治、Yaml 为 Truth 的核心法则
└── design.md               # (当前文件) 具体 Architecture 与 API 设计

已处置的旧 Spec:
.kiro/specs/studio-api-keys-v1/ 
  -> Rename to _deprecated_studio-api-keys-v1/ (历史遗物，与 YAML 冲突)
.kiro/specs/studio-copilot-providers-v3/ 
  -> Rename to _deprecated_studio-copilot-providers-v3/ (被 v2 替代)
.kiro/specs/studio-copilot-v1/ 
  -> Rename to _deprecated_studio-copilot-v1/ (由于内置 4-backend 且不走 fallback，需未来重构)
```

## 6. Copilot 的 "单独 Role" 实施
- **YAML 侧**：新增 `copilot_chat` role，其 `models` 列表包含了所有允许 Copilot 使用的模型。
- **UI 侧 (Copilot Panel)**：前端拉取支持的模型清单，填充到聊天顶部的 ModelPicker 中。用户切换模型时，修改 React 本地 State。
- **后端执行侧 (claude-agent-sdk)**：Copilot 依然使用现有的 `claude-agent-sdk` 子进程驱动，以保留原生的 Read/Write/Edit/Bash Tool Use 能力。但是，网络调用的参数将完全由 `ModelResolver(role="copilot_chat", active_model=user_override)` 解析出具体的 Provider 后，再通过 `ClaudeAgentOptions(env={"ANTHROPIC_BASE_URL": base_url, "ANTHROPIC_API_KEY": api_key})` 的形式，精准注入给 SDK 子进程。

## 7. YAGNI (不在 V1 实现)
- 不在 Tab 2 UI 中实现复杂的 `peer_model_groups` 和 `circuit_breaker` (熔断配置) 可视化编辑器。
- 不在 Tab 2 UI 的下拉框中暴露 DeerFlow 系统级角色 (`deerflow_default` 等)，仅暴露基础业务 Role (`premium`, `balanced`, `copilot_chat` 等)。复杂的高级配置请直接去代码库编辑 YAML。