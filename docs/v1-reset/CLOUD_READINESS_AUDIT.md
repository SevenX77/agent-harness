# Skill Studio 云端就绪度审计与重构指南 (Cloud Readiness Audit)

**日期**: 2026-04-30
**目标规模**: 10,000+ C端用户，高峰期 1k-3k 并发 Run
**分析者**: 资深云原生架构师 (a2 Gemini)

---

## 1. Executive Summary (核心结论)

目前的单机架构（内存 Pub/Sub、本地文件系统、本地 SQLite Checkpoint、无 Auth、同步子进程）如果直接上云，将在**并发超载、状态丢失和严重安全漏洞**的三重打击下瞬间崩溃。
要支撑万级并发，必须实施**计算与状态分离**（引入 Redis Pub/Sub + S3 + RDS）、**异步任务下放**（引入 Celery/K8s Jobs 剥离长时 Run），以及**严格的沙箱隔离**（废除物理 PTY，采用 Firecracker/gVisor 级隔离或剥离危险权限）。

## 2. 当前架构必死项清单 (P0 / P1)

### P0 (一上线就崩 / 数据丢失 / 严重安全漏洞)
- **本地文件系统强依赖 (State Loss)**: `workspaces/`、`runs/` 和 SQLite checkpoints 全在本地盘。多实例（Horizontal Pod Autoscaling）下，请求路由到不同 Pod 会直接 404，且 Pod 漂移会导致数据永久丢失。
- **内存 Event Bus 孤岛 (WS 断联)**: `event_bus` 是单机内存 Pub/Sub。负载均衡器将 WS 连到实例 A，而跑任务的进程在实例 B 时，用户完全收不到 `CallbackEvent` 和 `skill_changed`。
- **PTY 终端裸奔 (RCE 漏洞)**: 给 C 端用户分配直接挂载本地文件系统的 Bash/PTY 进程，且 `SKILL.md` 中 `tools: [module.func]` 允许反射调用任意代码，相当于提供开箱即用的 Remote Code Execution (RCE)。
- **0 鉴权与单租户 (数据越权)**: 全部写入 `workspaces/default`，用户不仅能看到别人的代码，还能覆盖和篡改。
- **同步 Spawn Subprocess (OOM 崩溃)**: 在 FastAPI 进程内直接 `subprocess.Popen` 拉起 Agent。3000 并发将瞬间耗尽节点内存和文件句柄。

### P1 (成本爆炸 / 外部依赖限流)
- **无 LLM 速率限制与 Quota**: 没有 per-user token 统计，一小撮恶意/疯狂用户可在一小时内刷爆 Anthropic 账单，同时触发 Provider 的 Global Rate Limit 导致全站瘫痪。
- **缺乏分布式锁与竞态控制**: `PUT /api/skills/{id}` 并发写入同一个文件会导致不可预期的冲突与 AST 损坏。

## 3. 改造分档矩阵

| 维度 | 必须改 (Must Have - Blocker) | 应该改 (Should Have) | 锦上添花 (Nice to Have) |
|---|---|---|---|
| **数据** | S3 (存 SKILL/Trace) + RDS (存元数据) + Redis (存 Checkpoint/锁) | 静态资源 CDN 加速 | 分层存储归档极老 Run |
| **计算** | 分布式任务队列 (Celery/Temporal) 跑 Agent | K8s/Knative 容器化 Agent 实例 | Serverless GPU 算力池 |
| **通信** | Redis Pub/Sub 支撑 WebSocket 集群广播 | WebSocket 断线重连补偿 | 压缩二进制/Protobuf 传输 |
| **安全** | OIDC/OAuth 接入 + RLS(行级权限) 控制 | Python 工具沙箱 (gVisor) | DLP 敏感数据防泄漏扫描 |
| **成本** | API Gateway Rate Limit + Per-user 额度 | Prompt Caching (针对公共模板) | 按 Token 阶梯计费与充值系统 |

## 4. 数据层重构 Plan (Storage Evolution)

**演进方向**: `Filesystem` -> `Cloud Object Storage + RDBMS + Redis`

- **关系型数据库 (PostgreSQL)**:
  - 存储用户元信息、SKILL 元数据 (`SkillSummary` 字段)、Run 的结构化 Metrics 和关联关系。
  - **迁移**: 将基于目录扫描的 `GET /api/skills` 改为 `SELECT * FROM skills WHERE user_id = ?`。
- **对象存储 (S3/OSS)**:
  - 存储大文本和不可变产物：`SKILL.md` 源码、`tracing.jsonl`、`artifacts/`、`test_inputs` 以及 Golden Baseline。
- **分布式缓存与 Checkpoint (Redis)**:
  - **LangGraph Checkpointer**: 从 `langgraph-checkpoint-sqlite` 切换到 `langgraph-checkpoint-redis`，解决实例漂移时的断点续跑问题。
  - **状态同步**: 作为 Event Bus 的 Broker。

## 5. 计算层 Plan (Compute & Scaling)

FastAPI (API Server) 必须只做请求响应与状态下发，不再承载任何重计算。

- **异步任务编排 (Worker Queue)**:
  - 引入 **Temporal** 或 **Celery**。当用户 POST `/runs` 时，FastAPI 将 `RunRequest` 推入队列，并返回 `run_id`。
  - 独立的 Worker 集群拉取任务、下载 S3 的 SKILL、执行 LangChain Agent Loop。
- **横向扩缩容 (HPA)**:
  - Worker 节点基于队列长度 (Queue Depth) 配置 KEDA 或 K8s HPA 自动弹缩，扛住 3k 级别突发脉冲并发。
- **长连接保活**:
  - Worker 将 `CallbackEvent` 写入 Redis Pub/Sub channel (`run_events:{run_id}`)，任意一台保持着客户端 WS 连接的 API Server 订阅该 Channel 并透传给前端。

## 6. 安全与隔离 Plan (Auth & Sandbox)

- **多租户隔离 (Tenant Isolation)**:
  - 接入 Auth0 / Clerk / AWS Cognito，在网关层将 JWT 解析为 `user_id`。
  - S3 路径规范化：`s3://my-bucket/workspaces/{user_id}/skills/{skill_id}/`。代码级强制校验所有请求必须包含合法的 owner id。
- **PTY 终端上云方案**:
  - **废弃**本地 ptyprocess。
  - 方案A（激进）：废除 C 端真实终端，改用前端 Chat UI，后端通过专用 Copilot Endpoint 直接生成 AST 并 Patch S3 文件。
  - 方案B（容器沙箱）：若必须提供 CLI，必须通过 Kubernetes API 动态创建一个极低权限、挂载只读系统盘+临时读写工作区的 Ephemeral Pod（基于 Firecracker MicroVM）。
- **工具滥用防御 (Tool Sandboxing)**:
  - C 端用户自编的 Python script 工具如果直接在 Worker 里 `eval`/`import` 会直接击穿后端。
  - 方案：引入 WebAssembly (Wasmtime) 或安全容器沙箱执行用户自定义工具，禁绝 `os`、`sys` 和高危网络调用。

## 7. 成本控制与可观测性 Plan

- **LLM Cost & Rate Limit**:
  - **Token 记账**: Worker 执行完成后，解析 `TokensMetrics` 写入 DB，扣减用户当日/当月 Quota。
  - **速率限制**: API 网关 (如 APISIX / Kong) 按照用户 ID 设置 TPS/RPM (Requests Per Minute) 限制，防恶意 DDoD。
  - **Prompt Caching**: 针对 `skills/` 下的公共只读模板，开启 Anthropic Prompt Caching 机制，极大降低首轮思考成本。
- **可观测性 (Observability)**:
  - **Trace**: 接入 OpenTelemetry (OTEL)，将 FastAPI、Worker、LLM Call 串联为分布式 Trace，发往 Jaeger/Datadog。
  - **Metrics**: 暴露 Prometheus `/metrics`，监控 Worker Queue 延迟、LLM 失败率、WS 连接数。
  - **Logging**: 用 JSON Structured Logging 替代现有明文 Log，集中收集到 ELK / Loki 栈。

## 8. 估算与参考架构

**标杆对比**: 我们目前的转型，相当于把一个本地的 `VSCode` 变成 `Replit` 或 `Vercel`。
**最相似的成熟架构**: **Modal** (用于 Serverless Worker) + **Supabase** (用于全栈状态) + **Replit** (其容器沙箱模型)。

**演进时间线预估**（1 资深全职 + 2 兼职）：
- **Phase 1 (基础云化, 2-3周)**: 剥离本地盘引入 PostgreSQL + S3，替换 InMemory Checkpointer 为 Redis。接通 OAuth。
- **Phase 2 (计算分离, 3-4周)**: 引入 Celery/Temporal，将 Subprocess 改为 Worker Queue，打通 Redis Pub/Sub WebSocket。
- **Phase 3 (安全隔离, 4-6周)**: 解决 Wasm / 容器级沙箱，重构 PTY 的云端生命周期，接入计费与限流。
*总计约需 2-3 个月即可支持万级用户安全上线。*

## 9. 风险与未知 (Open Questions)

1. **自定义工具执行深度**: 允许 C 端用户写多深的代码？如果只允许 YAML 编排现有框架工具，安全性极高；如果允许用户自己写 `script/my_tool.py`，沙箱隔离的工程成本将直接翻倍。
2. **实时性的 SLA 要求**: 从 Redis Pub/Sub 到 WebSocket 的端到端延迟要求是多少？如果是强实时的“打字机”流式效果，Worker 的网络质量和队列的开销是否会造成明显卡顿感？
3. **法律与合规 (GDPR/Data Privacy)**: 用户让 Agent 处理的数据如果涉及敏感信息（PII），我们将其持久化到 S3 (`final_state.json`) 会有极高的合规风险，是否需要设计“阅后即焚”的无痕 Run 模式？