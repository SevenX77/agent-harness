---
status: Living
target_goal: "规范大模型提供商的统一接入方式、Role 定义机制与灾备路由"
linked_code_paths:
  - apps/studio/backend/app/services/llm_roles.py
  - apps/studio/backend/app/routers/llm.py
linked_specs:
  - .kiro/specs/studio-api-keys-redesign/
last_updated: 2026-05-19
---

# LLM 路由与降级配置 (LLM Routing & Fallback)

## 1. `llm_roles.yaml` 定义标准
Engine 不在代码里硬编码大模型配置，而是通过根目录的 `config/llm_roles.yaml` 定义整个模型舰队。
系统抽象了 `Role` 的概念，PM 在 `SKILL.md` 里只写使用哪个 Role（如 `fast`, `creative`, `balanced`），由底层决定它映射到哪个具体的 Provider + Model。

## 2. 动态模型路由策略
```yaml
roles:
  fast:
    primary: "gemini-2.5-flash"
    fallback: ["claude-3-haiku", "gpt-4o-mini"]
```
通过上述配置，Engine 运行时解耦了业务逻辑与具体模型。

## 3. 异常熔断规则与 Fallback 触发链
当向 `primary` 模型发起请求出现如下情况时，触发自动降级（Fallback）：
- **HTTP 429 (Too Many Requests)** 且重试 3 次后仍失败。
- **HTTP 5xx (Server Error)** 大于 5 秒未恢复。
- **Context Length Exceeded** (内容过长截断错误，尝试降级到提供更大窗口的模型)。
降级机制会在 Trace 日志中打上明显标记，但对用户态透明，保证流程完备。

## 4. 特殊参数 (Thinking / Temperature) 支持
不同 Provider 对参数支持存在差异。Engine 的 Wrapper 层统一拦截：
- **Thinking**: 如果 Provider (如 Anthropic 较新版本) 支持 thinking 特性，在 Role 级别进行配置后，Engine 自动装配相关扩展头。
- 若降级的 Fallback 模型不支持 Thinking，Engine 将平滑擦除该参数再发起请求，避免报 400 Bad Request。

## 相关 Spec
- [studio-api-keys-redesign](../../.kiro/specs/studio-api-keys-redesign/design-backend.md)
