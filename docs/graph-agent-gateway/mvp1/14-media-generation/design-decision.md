---
module: 14-media-generation
doc: design-decision
status: drafted（用户批准 2026-08-13；随实现 PR 落盘；未进入 audited-ready 哈希锁）
aligns_with: ../../studio/mvp1/02_capabilities/media-generation/design-decision.md（Studio 消费切面与页面设计）
---

# 14-media-generation — gateway 媒体生成域设计决议

## 1. 边界定义

`graph_agent_gateway.media` 是 gateway 内与 LLM registry **并列且隔离**的新域：持有媒体生成（图像/视频异步任务式生成）服务商的凭据 schema、声明式模型目录与零成本探活逻辑。

- **与 LLM 域的关系**：不共享 `Protocol`/route/role 任何类型；媒体模型不可被 role→route 解析选中。隔离靠类型系统实现（独立 schema 模块，无交叉引用）。
- **存储边界**：gateway 不落盘。`MediaGenerationSnapshot` 由 host（Studio backend）负责持久化与注入——与 registry 的 storage-provider 注入范式一致。
- **调用边界**：本期只有 L1 探活（accountStatus）。任务提交/轮询/文件上传属下一单元 `media-invocation-runtime`，本期不建。

## 2. 模块构成

| 文件 | 职责 |
|---|---|
| `media/schema.py` | Pydantic 模型：`MediaModelSpec`（含判别式参数 spec 联合类型）、`MediaProviderCredential`、`MediaModelSettings`、`MediaProbeResult`、`MediaGenerationSnapshot`。`extra="forbid"`，非法状态不可表示。 |
| `media/catalog.py` | 内置 RunningHub 目录（10 条，证据基线见 studio 侧决议 §3）+ `validate_model_settings()`（默认参数按 spec 校验的唯一出口）。 |
| `media/probing.py` | `probe_runninghub_account()`：`POST {base}/uc/openapi/accountStatus`，返回 `MediaProbeResult`（ok/auth_failed/network_error + 延迟 + 余额）。httpx AsyncClient 由调用方注入 transport 可测（离线可验证原则）。 |

## 3. 关键类型决定

- 参数 spec 用**判别式联合**（`type` 字段判别）：`string` / `enum`（values 枚举）/ `int_range`（min/max）/ `image_list`（max_items/max_size_mb）/ `image_slot`（单图位，首尾帧场景两个具名 slot）。默认值合法性由 `validate_model_settings()` 按 spec 裁决，宿主在边界调用，域内代码得以假设设置合法。
- `MediaChannel = Literal["economy", "official"]`；`MediaEndpointKind = Literal["standard", "ai_app"]`（seedance 走 AI 应用接口，形状不同，本期仅目录展示用）。
- 计价 `MediaPricing(unit=per_image|per_second|per_run, amount, currency="CNY")`；无证据的条目允许 `pricing=None`，禁止编造。
- 探活响应判定：RunningHub 统一信封 `{"code": 0, "msg": ..., "data": ...}`；`code==0` → ok 并从 data 提取余额字段；非 0 → auth_failed（带 msg）；传输层异常/非 JSON → network_error。判定逻辑离线测试用 httpx MockTransport 覆盖三分支。

## 4. 验收判据

1. `mypy --strict` 通过；`ruff` 通过。
2. 目录完整性测试：10 条 id 唯一、端点非空、每条 params 的默认值通过 `validate_model_settings()` 自校验。
3. 探活三分支（ok/auth_failed/network_error）离线测试全绿（MockTransport，不打真网络）。
4. 设置校验测试：非法枚举值/超范围整数被拒，合法值通过。
