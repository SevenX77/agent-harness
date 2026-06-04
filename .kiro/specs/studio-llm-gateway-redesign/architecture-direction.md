---
status: Decided
created: 2026-06-01
owner: Studio + Engine
supersedes_ambiguity_between:
  - .kiro/specs/studio-llm-platform-control-plane-runtime/
  - .kiro/specs/studio-llm-gateway-redesign/
---

# LLM 平台架构方向决策（远端服务化分层）

> 本文件是上位方向决策（ADR）。审计 `studio-llm-gateway-redesign` 方案时，追溯到 2026-05-25
> 的一次 hard cutover 回归，并经用户确认目标形态后形成。它统一了上面两份重叠 spec 的方向，
> 后续 requirements/design/tasks 以本文件为准。

## 1. 目标形态（用户确认，2026-06-01）

> 用户原话：「gateway 和 llm调用相关模块未来都要远端服务化, studio功能设计编译这些放在桌面端」

- **远端服务化**：gateway + resolver + LLM 执行 + roles/credentials 配置 + Test 真机探测
  （凡"llm 调用相关"）。目标：多用户 + 认证 + 远端存储。
- **桌面端**：studio 的 skill 设计 / 编译 / 画布（authoring）。
- 桌面前端对 API Keys / Roles / Copilot 的操作 = 远端 LLM 服务的管理界面；**SSOT 在远端**。

## 2. 架构现状（勘察实据，2026-06-01）

- 桌面壳 = **Tauri 2**：`tauri/src/sidecar.rs` 用 `Command` spawn `uvicorn app.main:app`
  （loopback + 随机 Bearer token + 健康检查）。Rust 层目前只管 sidecar 生命周期，无数据 command。
- 后端 = **标准 FastAPI 服务，本就为可移植设计**：可插拔 `AuthProvider`/`Storage`/`Metadata`
  backend（`app/core/backends.py:114`、`:122`）、多 token Bearer 中间件（`app/main.py:80`）、
  CORS 可配、全 env 注入、`sqlalchemy>=2.0`。**skills 模块已 user_id 多用户隔离**
  （`app/routers/skills.py:74`）。
- **LLM 配置模块是后端唯一的"桌面单用户孤岛"**：`llm.py`/`copilot.py` 路由无 `user_id`；
  roles/credentials 存全局单文件（`services/llm_paths.py`）；credentials 明文 + `chmod 0600`。
- backend ↔ gateway = 同进程 Python import；control→runtime 牵手点 = `RegistrySnapshot`
  （`app/models/llm_config.py:279 to_registry_snapshot()` → gateway `resolve_role()`）。

## 3. 回归根因（2026-05-25 hard cutover）

两个提交在 2026-05-25 删了约 7200 行旧 LLM 栈，换成新 registry/gateway，丢失了两个旧行为：

- `ecab5fe1 feat(gateway): hard cutover runtime resolver` — 删旧 resolver
  （`config/llm_config.py:resolve_role`，含 `continue` 跳过 + `logger.warning`）。
- `c8bfb93f feat(studio): hard cutover llm registry backend` — 重写 save 路径，
  把 `validate_references(data)`（仅查 YAML 自洽）改成 `validate_references(data, known_route_ids=active_route_ids)`（焊死凭证）。

| 行为 | 旧版（5-25 前，更好） | 现在（回归） |
|---|---|---|
| 保存校验 | 仅查 YAML 自洽，不碰凭证 → 不死锁 | 耦合凭证 → 死锁 |
| 运行期缺路由 | `continue` 跳过 + WARNING → 优雅可观测 | `raise` 崩在第一个 + 无日志 |

参考实现（已验证可用）：`git show ecab5fe1^:packages/graph-agent/src/graph_agent/config/llm_config.py`

## 4. 决策

1. **LLM 配置数据层不 Rust 化**。理由：要上远端服务，Rust 化会焊死在桌面客户端，与远端化直接冲突。
2. **测试状态写回 SSOT（治本）**，而非前端状态提升（治标）。SSOT 接口按远端 user_id-scoped 形状设计。
3. **近期修复留 Python，按"远端多用户服务"形状写，不引入反远端债**。

## 5. 范围分界

### 近期（本次，bug 修复 + 形状对齐）
- ① resolver：把 `packages/graph-agent-gateway/.../registry/resolver.py:57` 的 `raise` 改为
  `continue + logger.warning`，仅在过滤后整条 chain 为空时报错（移植旧 `resolve_role` 语义）。
- ② save 解耦：`_save_roles_with_active_routes` 传 `known_route_ids=None`
  （`app/routers/llm.py:4726`）。
- ③ 测试结果写回 SSOT 并落盘；前端切 tab/重启都从后端读，删前端并行内存态。
- 约束：①②③ 的接口/存储都按 `user_id`-ready + Storage 抽象的形状写，**实现先维持本地文件**。

### 远期（独立 spec）
- LLM 服务真正远端化：多用户 + DB 存储 + 密钥 KMS/加密 + 认证体系。

### 债登记（远端化时偿还，现在不准加重）
- credentials 明文密钥（仅靠 `chmod 0600`）。
- LLM 模块无 `user_id`、roles/credentials 全局单文件。
- 测试状态 SSOT 为本地单文件。

## 6. 待确认 / 边界

- roles 是否随 credentials 一并归"远端 LLM 服务域"（本文件按"是"处理；桌面只是其编辑前端）。
- 近期范围是否就是 §5 的 ①②③（形状对齐但不接 DB/KMS）。
