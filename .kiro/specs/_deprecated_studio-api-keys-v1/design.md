# Design Doc: Studio API Keys (v2)

**Status**: v0.2 — v2 推翻重做 by sevenx 反馈 + video_analysis pattern 对齐, 2026-05-14
**Author**: PM + a2 Gemini
**Related Requirements**: `requirements.md`

## 1. 架构概览

Studio API Keys (v2) 旨在为开发者提供一个类似于 VS Code / Cursor / video_analysis 的"开箱即用 + 本地安全存储"的 LLM 凭据管理体验。
核心原则：**零停机热加载**、**File-based Truth**、**明文回读所见即所得**、**去显式提交防密码探测**。

## 2. Storage Schema

v0.1 的硬编码 `backends` dict 已被推翻。v2 采用动态 `ProviderConfig` 列表，支持任意数量和类型的模型供应商。

### 2.1 JSON Schema v2 (`~/.studio/copilot.json`)

```json
{
  "active_provider_id": "default-claude",
  "providers": [
    {
      "id": "default-claude",
      "name": "Claude",
      "kind": "anthropic",
      "api_key": "sk-ant-...",
      "base_url": ""
    },
    {
      "id": "custom-1715690000",
      "name": "Ollama Local",
      "kind": "openai-compat",
      "api_key": "ollama",
      "base_url": "http://127.0.0.1:11434/v1"
    }
  ]
}
```

### 2.2 Pydantic Models

```python
from typing import Literal, List
from pydantic import BaseModel, Field

ProviderKind = Literal["anthropic", "openai-compat", "google"]

class ProviderConfig(BaseModel):
    id: str = Field(..., description="唯一标识，预设项使用 default-xxx")
    name: str = Field(..., description="UI 显示名称")
    kind: ProviderKind = Field(..., description="决定后端使用哪种 Client")
    api_key: str = Field(default="", description="明文存储，可为空")
    base_url: str = Field(default="", description="自定义反代/私有化部署地址")

class CopilotCredentials(BaseModel):
    active_provider_id: str = Field(default="default-claude")
    providers: List[ProviderConfig] = Field(default_factory=list)
```

### 2.3 Migration 策略
原型期铁律：“做错就推翻”。后端 `read_credentials` 在遇到解析/验证错误（如旧的 dict 格式）时，直接记录 Warning，并无脑用包含 4 个 default preset (`default-claude`, `default-openai`, `default-deepseek`, `default-gemini`) 的初始模板覆盖写入，**不包含向后兼容代码**。

## 3. 后端 API 契约

API 全面重构为 RESTful 风格，且支持前端 UI 的 Debounce 无感保存机制。

### 3.1 GET `/api/copilot/credentials`
- **Request**: 无参。
- **Response**: 返回完整的 `CopilotCredentials` 对象。
- **重大改动**: `api_key` **不再脱敏**，直接下发明文。这是为了与 `video_analysis` 保持一致，支持前端 Input 直接双向绑定，并配合 Eye Toggle。

### 3.2 PUT `/api/copilot/credentials`
- **用途**: 响应前端 debounce，全量覆盖。
- **Request Body**: 完整的 `CopilotCredentials` 对象。
- **Response**: `200 OK`
- **行为**: 接收到后立刻原子写入 `copilot.json`，下一次 `POST /api/copilot/query` 时将自然从文件中 fresh read 读到新配置，实现零停机热加载。

### 3.3 POST `/api/copilot/providers/test`
- **用途**: 测通连通性并拉取该 Provider 支持的可用模型。
- **Request Body**: `ProviderConfig` (仅测通该 Request 携带的临时 Key，不读磁盘)。
- **Response**:
  ```json
  {
    "status": "ok",
    "message": "Connected",
    "models": [
      {
        "id": "claude-3-7-sonnet-20250219",
        "supports_thinking": true,
        "supports_vision": true
      }
    ]
  }
  ```

### 3.4 API 鉴权
此模块所有 API 必须受到 `STUDIO_API_TOKEN` 或 `STUDIO_DEV_TUNNEL_TOKEN` 的强制保护（具体见 `studio-tunnel-safety` spec），防止 Tunnel 暴露时的未授权密钥注入。

### 3.5 增删 Provider 设计
无专用 POST/DELETE 接口。由于 PUT 具有全量覆盖语义，前端在本地 Array 增加或删除元素后，等待 650ms debounce 触发一次 `PUT` 即可完成同步。极简、RESTful。

## 4. 前端集成

### 4.1 SettingsPage UI v2

完全废除原生 `<form>` 提交，对齐 `video_analysis` 的 `ConfigView.tsx`。

**1. Mockup:**
```text
================================================================================
                               Settings > AI & Copilot
================================================================================

Active Provider
[ Select Active: Claude (default-claude)   v ]     [ + Add Custom Provider ]

--------------------------------------------------------------------------------
[ Claude ]  (Badge: anthropic)                                          [ Trash ]
                                                                       (Disabled)
API Key
[••••••••••••••••••••••••••••••••] [Eye]                         [ Test Connection ]

[ > Advanced Options ] (Ghost Button)
  | 
  | Base URL (Optional)
  | [ https://api.anthropic.com/v1               ]

Status: ✓ Connected 
Default Model: [ claude-3-7-sonnet-20250219  v ]
Available Models:
[ claude-3-7-sonnet-20250219  🧠 ] [ claude-3-5-sonnet-20241022 ] [ claude-3-opus-20240229 ]
--------------------------------------------------------------------------------
[ Ollama Local ] (Badge: openai-compat)                                 [ Trash ]

API Key
[ollama                          ] [Eye]                         [ Test Connection ]

Status: ⚠ Not configured
--------------------------------------------------------------------------------
```

**2. 核心交互 Spec:**
- **无感保存**: 监听 State 变更，使用 `lodash.debounce` 设置 650ms 延迟，自动发起 PUT 覆盖后端。**绝不使用 `name="password"` 或包含明确 Submit 的按钮**，彻底杜绝浏览器弹“是否保存密码”弹窗，且添加 `autoComplete="new-password"`。
- **Plaintext + Eye Toggle**: Input type 默认 `password`，点击右侧 Eye Icon 切换为 `text`。这要求 GET 必须下发明文。
- **Models 平铺与 🧠 标记**: Test 成功后，`testResults` 持久化，展开该 Provider 支持的所有 Model 的 Badge。如果是 Thinking 模型，Badge 内增加 `🧠` Icon 提示。
- **Per-Provider Default Model**: Test 成功返回 Models 后，允许用户使用 `<Select>` 从中挑一个设为该 Provider 的默认通信模型（该状态同样随 `ProviderConfig` 存入）。
- **Add / Delete**: 预设的 4 个 (`default-*`) 不允许删除（Trash Icon disable）。自定义 Provider 点击 Delete 本地移除并触发 650ms debounce；点击 Add 弹出 Dialog 填入 Name/Kind 生成临时 ID 并 push 到列表触发保存。

### 4.2 API 客户端定义

需要导出以下核心 Types / Functions：
- Types: `ProviderKind`, `ProviderConfig`, `CopilotCredentials`, `ModelInfo`, `TestProviderRequest`, `TestProviderResponse`
- API Functions: `getCopilotCredentials()`, `putCopilotCredentials(data)`, `testCopilotProvider(config)`

### 4.3 状态管理

采用受控状态模式：
- `credentials`: 全量拉取的配置树 `CopilotCredentials`。
- `testResults`: `Record<provider_id, TestProviderResponse | null>` 持久记录每个卡片的连通性。
- `addDialogOpen`: 控制新建窗口。

## 5. 安全细节与 UX 权衡

### 5.1 Test Endpoint 防 SSRF / Reflection
`POST /api/copilot/providers/test` 必须做异常截断。即便测试报错，也不应该将完整的 Provider 返回体（特别是携带完整 trace 和其他敏感内部 IP 探测信息的报错栈）暴漏给前端，应当 catch 后包装为友好的 `"Invalid API Key or connection timeout"`。

### 5.2 输入框明文回读 (Plaintext over Mask)
采用明文传输 + 内存驻留方案，而不是传统的"下发 Mask (e.g. `••••1234`)，提交仅填变更"方案。
**理由**：对齐 VS Code / Cursor UX。用户有权利随时查看自己配置的确切密钥。既然凭据已在本地安全存储 (`0600` 权限) 并在 Tunnel 后加了强鉴权保护，前端索要明文属于合理权限。这也极大地简化了前端逻辑（不用再处理 "输入框为空代表不修改" 的三态同步判断）。

### 5.3 Debounce 即时保存
650ms 保存生效机制使得系统不存在“保存未应用”这种中间态。后端每次 Query 都会 fresh read 磁盘。所以前端不需要显示任何“配置需重启生效”或“保存成功”的阻断式弹窗。

## 6. 与其他系统集成

- **依赖**: Backend HTTP 服务。
- **影响**: Copilot 后端 `/api/copilot/query` 路由。必须通过读取 `active_provider_id` 找到对应的 config 发起请求。

## 7. 命名规范与词汇表

为消除历史债务并与新代码层对齐，使用以下词汇：
- **Provider**: 模型供应商/渠道 (不再使用 backend 称呼)。
- **ProviderConfig**: 单个渠道的完整配置实体。
- **ProviderKind**: 具体的底层连接协议类 (anthropic, openai-compat, google)。
- **Active Provider**: 当前系统聊天默认激活使用的通道 (`active_provider_id`)。

## 8. 不引入的复杂度 (YAGNI)

- **不引入 OAuth / Cloud Sync**: 纯本地工具定位，不接云端账号系统。
- **不引入 Multi-Tenant**: 假设运行环境是单用户单机使用。
- **不引入 Audit Log**: 本地配置的变更记录不在监控范畴。
- **不引入 V1.5 Placeholder**: 砍掉所有的占位符判断，Provider 不填 key 就是失效状态。
- **暂不引入过重的 SDK 抽象层**: 虽然理论上可以引入 LiteLLM 或封装极为完备的 Protocol 基类，但当前 v2 保持仅手写 3 个直连 Client (Anthropic / OpenAICompat / GoogleGenAI) 最为直接高效，避免工程膨胀。