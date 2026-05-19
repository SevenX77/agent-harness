# 分离架构 (Split Architecture) 完整可行性及落地计划

**日期**: 2026-04-30
**分析者**: 资深云原生架构师 & DevOps 专家 (a2 Gemini)

---

## 1. Executive Summary

**Verdict: 完美自洽，强烈推荐推进落地**。

将架构分为 **本地研发端 (内部 PM)** 与 **云生产端 (C 端消费者)** 是解决此前 "Python 工具免鉴权 RCE" 这一 P0 级 Deal-breaker 的唯一解。由于确认了 Studio 是内部百人工具且 C 端不修改逻辑，该方案大幅缓解了人审瓶颈与供应链攻击的风险。
当前架构消除了 Deal-breaker，总周期约需 12 周（3 个 Milestone），最大剩余风险是从本地到云端的“环境漂移”及“隐形 Git 冲突合并”的用户体验。

---

## 2. 架构方案设计

### 2.1 架构总览图

```text
┌─────────────────────────────────┐                 ┌───────────────────────────────────────┐
│        研发端 (内部 PM 本地)    │                 │          中间层 (CI/CD Pipeline)      │
│                                 │                 │                                       │
│ 1. 安装 `studio dev` CLI        │    [Publish]    │ ┌────────────────┐  ┌───────────────┐ │
│ 2. Monaco 编辑 SKILL.md         │ ───────────────▶│ │ 自动化 CI      │  │ 人工审核网关  │ │
│ 3. 隐形 Git Auto-Commit         │                 │ │ - pip-audit    │─▶│ - Prompt 改动 │ │
│ 4. 本地 Docker Simulate         │ ◀───────────────│ │ - compile_skill│  │   -> Auto Merge │
└─────────────────────────────────┘  [Pull/Revert]  │ │ - Sandbox test │  │ - Script 改动 │ │
                                                    │ └────────────────┘  │   -> Engineer │ │
                                                    │                     └──────┬────────┘ │
                                                    └────────────────────────────│──────────┘
                                                                                 │ [Merge]
                                                                                 ▼
┌─────────────────────────────────┐                 ┌───────────────────────────────────────┐
│        C 端 (Web / App)         │                 │           生产端 (K8s 云环境)         │
│                                 │                 │                                       │
│ 1. OIDC 登录                    │   POST /runs    │ ┌────────────────┐  ┌───────────────┐ │
│ 2. 浏览已发布 Skill 列表        │ ───────────────▶│ │ API Gateway    │─▶│ PostgreSQL    │ │
│ 3. 填入 Input 触发执行          │                 │ │ (Rate Limit)   │  │ (Metadata)    │ │
│ 4. 消费执行进度与输出           │ ◀───────────────│ └──────┬─────────┘  └───────────────┘ │
└─────────────────────────────────┘    WS Events    │        │ [Task Queue]                 │
                                                    │        ▼                              │
                                                    │ ┌────────────────┐  ┌───────────────┐ │
                                                    │ │ Celery Worker  │─▶│ S3 Object     │ │
                                                    │ │ - LangGraph    │  │ (Trace/Artifact)│ │
                                                    │ │ - Checkpoint   │  └───────────────┘ │
                                                    │ └──────┬─────────┘                    │
                                                    │        │ [PubSub]                     │
                                                    │        ▼                              │
                                                    │ ┌────────────────┐                    │
                                                    │ │ Redis Cluster  │                    │
                                                    │ └────────────────┘                    │
                                                    └───────────────────────────────────────┘
```

### 2.2 关键组件清单

- **Studio Local CLI (`studio dev`)**: PM 本地的统一入口，拉起 FastAPI 后端、Vite 前端并提供基于 Docker 的生产模拟环境，完全跨平台 (Mac/Win)。
- **隐形 Git 抽象层**: 本地守护进程拦截 Monaco 的 Ctrl+S 事件，转化为 `git add & commit`，PM 在 UI 上只感知“版本历史”和“回滚”，不需掌握 Git 命令。
- **Skill Registry (PG + S3)**: 中央化的技能账本。PostgreSQL 存关系映射、使用量、版本状态；S3 存不可变的 SKILL.md 源码和工具脚本。
- **CI/CD 审核 Pipeline**: 运行在 GitHub Actions 上，拦截来自 Studio 的 Publish PR。执行代码安全扫描 (pip-audit)、编译校验和沙箱跑测。
- **人审分流网关**: 智能区分代码变动。Prompt 和 YAML 参数微调触发 Auto-merge；Python Script 变动强制 Assign 给后端工程师审阅。
- **graph_agent Cloud Runtime**: 基于 Temporal 或 Celery 的异步 Worker 集群。从 S3 拉取审核过的 Skill 执行 LangGraph Agent Loop，并将实时 Trace 写入 Redis，断点写入 Redis/Postgres Checkpointer。
- **C 端 API Gateway**: 负责 OIDC 鉴权、基于 Redis 的 per-user rate limit 以及将 Redis PubSub 桥接至外部 WebSocket。

### 2.3 三条核心数据流 (端到端)

**Flow A: PM 开发 + 提审 + 上线**
1. PM 运行 `studio dev`，打开本地浏览器，通过 Monaco 编辑 `SKILL.md`。
2. 每次 Ctrl+S，隐形 Git 执行 `git commit -m "Auto save"`。
3. 满意后，PM 在 UI 点击 [Publish]，后台调用 GitHub API 将当前分支 Push 并创建 PR。
4. GitHub Actions (CI) 拉起，执行 `compile_skill`、`pip-audit` 及基于 Test Inputs 的 Dry-run。
5. 人审网关判定：发现 `script/my_tool.py` 有改动，拦截并通知 Engineer；若仅 `SKILL.md` 文本改动则直接 Auto-merge。
6. Merge 后 CD 触发，将源码包打包推至 Prod S3，更新 DB `SkillSummary.version`，使之对 C 端可用。

**Flow B: C 端用户消费 skill**
1. 用户登录 (OIDC JWT)，App 请求 `GET /api/skills` 获取可用技能。
2. 用户填入 Input，发送 `POST /api/skills/{id}/runs`。
3. FastAPI 鉴权、限流后，将 `RunRequest` 推入 Temporal/Celery Queue，立刻返回 `run_id`。
4. 云端 Worker 接单，从 S3 下载对应版本的 Skill 文件，启动 LangGraph + LangChain 循环。
5. Worker 运行中将 `CallbackEvent` 发布至 Redis Channel `runs:{run_id}:events`。
6. API 节点的 `/ws/runs/{run_id}` 路由订阅 Redis，将流式事件透传给 C 端用户前端。
7. 运行结束，Worker 将 `final_state.json` 与产物写回 S3 (带有用户隔离前缀)，并更新 DB 状态。

**Flow C: 引擎版本一致性保证**
1. PM 本地 `studio dev` 内嵌固定版本的 `graph_agent` (uv.lock 锁定)。
2. `SKILL.md` 的 frontmatter 强制带有 `engine_version: ">=0.1.0"`。
3. Publish PR 时，CI 验证 `engine_version` 与云端 Active Worker 镜像版本匹配。
4. 云端 Worker 拉取包含精确一致依赖的 Docker 镜像执行，消除运行时差异。

### 2.4 组件部署拓扑

建议采用云原生 K8s / Serverless 容器架构：
- **API Nodes**: 3-5 个轻量级 Pod，运行 FastAPI，承接 HTTP 与 WebSocket，无状态。
- **Worker Nodes**: 根据 Queue 深度自动弹缩 (HPA) 的高配 Pod，执行 LangGraph 核心循环，受限权限运行。
- **DB Cluster**: Serverless PostgreSQL (如 Neon/Aurora)。
- **Cache/KV**: Redis 集群 (ElastiCache/Memorystore)，兼作 PubSub、RateLimit 与 Checkpoint 存储。

---

## 3. 修正后的产品前提

1. **Studio 不向 C 端开放**: 仅供内部 10-100 人规模的 PM 团队使用。C 端用户是“消费者”，只填 Input 跑结果，不能 Fork，也不能看/改源码。
2. **Git 心智隐藏**: PM 不需要打开终端敲命令，所有分支、合并、回滚在 Studio UI 内体现为可视化的产品级操作。

这两个修正彻底改变了风险画像：将一个存在无限 RCE 敞口的外部黑客游乐场，收束为了一个**有限信任边界内部的规范发布流程**。

---

## 4. 可行性分析

### 4.1 是否消除 Deal-breaker
上一轮最致命的 "C端万级用户通过 Python Script 发起无门槛 RCE" 的 **Deal-breaker 被完全消除**。
因为 C 端不再提交代码。内部 PM 提交的代码将受到 GitHub PR 和 Engineer Review 的控制。即便存在部分危险代码，隔离 Worker + 不出公网的 Egress 控制也将其爆炸半径缩到了最小。

### 4.2 核心优势
1. **安全可控**: 代码执行权收归可信的 CI/CD 流水线与受限的云端 Worker。
2. **极简开发体验**: 本地开发享受 0 网络延迟的编辑器与系统资源，DX 拉满。
3. **架构成熟经济**: “本地开发 -> 云端构建分发”是现代 SaaS (如 Vercel) 验证过最具伸缩性的低成本形态，云端可随意销毁和弹缩节点。
4. **无需造轮子**: 免去开发重型 WebIDE 与 Web-based Wasm 沙箱这等深坑。

### 4.3 类似产品对照

| 产品 | 开发模式 | 提交机制 | 借鉴价值 |
|---|---|---|---|
| **Vercel** | 本地 `Next.js` 热重载 | Git Push 触发云端 Build | ⭐⭐⭐⭐⭐ (最佳范本，特别是 `vercel dev` 本地拉起能力) |
| **Cloudflare Workers** | 本地 `wrangler dev` | CLI Publish | ⭐⭐⭐⭐ (部署管道的轻量级参考) |
| **Modal** | 本地代码即时上云 | Remote execution | ⭐⭐⭐ (我们只在最终 Publish 环节上云) |

### 4.4 Killer Traps 状态 (修正后)
- **Trap 1 环境漂移**: 严重度 P0 → **P1**。Mac 写的包 Linux 跑不起来仍是隐患。**解药**: 引入 `studio dev --simulate` 本地拉生产镜像跑测，并在 CI 加沙箱 Dry-run。
- **Trap 2 人审瓶颈**: 严重度 P0 → **消解**。几十人的团队，利用分流网关自动合并 Prompt 改动，人工仅审 Python Script，几名研发完全可 Cover。
- **Trap 3 Supply Chain Attack**: 严重度 P0 → **消解**。内部管控源 + 锁定 uv.lock 消除大半。
- **新增 Trap 隐形 Git 抽象层的工程难度**: 要在 UI 默默处理 Pull 拉平远程分支与合并冲突，若处理不当，会导致 PM 本地代码紊乱。这是当前最大的前端工程挑战。

### 4.5 不可还原的能力损失
- **C 端不能 Fork/改 Skill**: 符合“作为产品而非平台”的定位，非问题。
- **C 端无 Web 实时 Debug (详细 trace)**: C 端仅需脱敏进度条，敏感 Prompt 不应外泄，合理。
- **C 端无 Open CLI**: 原本就不该有。

---

## 5. 实施 Phase Plan

### 5.1 Phase Overview

| Phase | 名称 | 周期 | 关键产出 |
|-------|------|------|---------|
| 1 | 基础云化与解耦 | 2-3 周 | PG 库 + S3 Client + Redis Checkpoint + OIDC 认证 |
| 2 | 计算分离 | 3-4 周 | Celery/Temporal Queue + Worker 集群 |
| 3 | 容器限权 | 1-2 周 | Worker Docker 降权 + 网络出栈审计 |
| 4 | 本地 CLI + 隐形 git | 2-3 周 | `studio dev` CLI + Auto-commit/Rollback UI + 生产模拟环境 |
| 5 | 提交-审核-部署 pipeline | 2-3 周 | UI Publish 按钮 + GitHub Actions + 自动人审分流网关 + CD 逻辑 |

### 5.2 Phase 1 Task Breakdown: 基础云化与解耦

| Task ID | 描述 | 输入 (依赖) | 输出 (产出) | 工时估算 | 阻塞 | 优先级 |
|---|---|---|---|---|---|---|
| **1.1** | PostgreSQL Schema 搭建 | 无 | `schema.sql`，DB 迁移脚本 | 2d | 无 | P0 |
| **1.2** | ORM 实体与 Repository 映射 | 1.1 | CRUD 接口替换完成 | 3d | 1.1 | P0 |
| **1.3** | S3 Client 与 IOManager 解耦 | AWS/GCP 账号 | 支持 `SKILL.md` 和 `artifacts` 存入 S3 | 3d | 无 | P0 |
| **1.4** | Redis 配置与连接池 | Redis 实例 | Redis Client 初始化模块 | 1d | 无 | P0 |
| **1.5** | LangGraph Checkpointer 迁移 Redis | 1.4, `checkpointer.py` | 分布式无状态断点恢复能力就绪 | 2d | 1.4 | P0 |
| **1.6** | OIDC/OAuth 中间件接入 | 内部 IdP | FastAPI Auth Middleware | 2d | 无 | P0 |
| **1.7** | 本地运行路径清理 | 1.3 | 无本地文件系统硬编码的干净代码库 | 2d | 1.3 | P1 |

### 5.3 Phase 2 & 3 简短 Task 列表

**Phase 2: 计算分离**
- 2.1 引入 Temporal/Celery Queue。
- 2.2 拆分 FastAPI Server 与 Worker Node 部署形态。
- 2.3 桥接 Redis PubSub 与 API WebSocket 推流。

**Phase 3: 容器限权**
- 3.1 去除 Worker Docker 镜像 Root 权限。
- 3.2 限制或监控不受信域名的网络 Egress。

### 5.4 Phase 4 Task Breakdown: 本地 CLI 与隐形 Git

| Task ID | 描述 | 输入 (依赖) | 输出 (产出) | 工时估算 | 阻塞 | 优先级 |
|---|---|---|---|---|---|---|
| **4.1** | 一体化 `studio dev` CLI | `pyproject.toml` | 跨平台一键启停本地微服务的可执行包 | 3d | 无 | P0 |
| **4.2** | 隐形 Git 控制层: 拦截与自动 Commit | 本地 Git 进程 | 拦截 Monaco 保存，生成格式化记录 | 2d | 无 | P0 |
| **4.3** | Studio UI 版本历史树状图面板 | 4.2 | 解析 `git log` 展示视觉修订节点 | 3d | 4.2 | P1 |
| **4.4** | 隐形 Git 控制层: 一键拉取/回滚 API | 4.3 | UI 触发的 checkout/revert 指令 | 2d | 4.3 | P1 |
| **4.5** | 生产模拟器 (`--simulate`) 指令 | Prod Docker | 本地拉起一致容器跑 Run 防止漂移 | 4d | 无 | P0 |
| **4.6** | Local API Proxy Key 下发 | API Gateway | PM 免配 Key 直接调用公司限速中转池 | 2d | 无 | P1 |

### 5.5 Phase 5 Task Breakdown: 提交-审核-部署 Pipeline

| Task ID | 描述 | 输入 (依赖) | 输出 (产出) | 工时估算 | 阻塞 | 优先级 |
|---|---|---|---|---|---|---|
| **5.1** | UI `[Publish]` 与 GitHub API 对接 | 内部 Git Server | 触发创建 PR / 自动推代码的接口 | 3d | 4.2 | P0 |
| **5.2** | CI: 依赖安全与版本抽取 | 5.1 | 自动跑 pip-audit 提取 lockfile | 1d | 5.1 | P0 |
| **5.3** | CI: 编译验证与 Sandbox Dry-run | 5.2 | 自动执行 `compile_skill` 跑用例 | 2d | 5.2 | P0 |
| **5.4** | 人审分流网关 (Diff 解析) | 5.3 | 识别 Prompt 改动并 Auto-merge | 2d | 5.3 | P0 |
| **5.5** | CD: 制品提升与 DB 元数据同步 | 5.4 | Merge 后推 Prod S3 并更新可用版本 | 3d | 5.4 | P0 |
| **5.6** | Canary 灰度与流量分发引擎 | 5.5 | 支持向新版本 Skill 分流 10% 请求 | 4d | 5.5 | P2 |

---

## 6. Milestones 与落地节奏

总工期估算：**12 周** (基于 1 资深全职后端 + 2 兼职开发配置)。

- **M1 (Week 1-4) - 内部工具成型**: 
  - **关键路径**: 并行推进 Phase 1 (DB/S3 迁移) 与 Phase 4 (CLI + 隐形 Git)。
  - **达成标志**: 公司 PM 能够通过 `studio dev` 开发并在本地获得无缝保存、回放历史体验。
- **M2 (Week 5-8) - 云端基础设施与 CI 闭环**:
  - **关键路径**: 串行推进 Phase 2 (Worker 切分) 与 Phase 5 (Github CI/CD)。
  - **达成标志**: PM 点击 Publish，触发 GitHub 检查通过。C端能在环境里调通 1 个受审核发布的 Skill。
- **M3 (Week 9-12) - 万级压测与发布体系就绪**:
  - **关键路径**: 集中打磨 Phase 3 (限权) 与 Phase 5 后期的 Canary 灰度路由。
  - **达成标志**: 10000+ C 端并发就绪，内部 PM 高频发布提示词且免人审直接上线，系统进入自动化驾驶。

## 7. 推荐技术栈选型

| 维度 | 推荐 | 备选 | 理由 |
|------|------|------|------|
| DB | **Neon / Supabase** | 自建 PG | Serverless 架构，低谷极省成本，脉冲并发横向伸缩快 |
| Queue | **Temporal** | Celery / SQS | 原生持久化状态机，完美契合 LangGraph 的长时间睡眠恢复与编排需求 |
| Deps | **uv** | pip | 极速装包，解决 CLI 初始化慢以及 CI 镜像构建耗时痛点 |
| OIDC | **Auth0 / Clerk** | 内部自研 SSO | 现成多租户管控，减少安全代码债 |
| Cloud | **AWS / GCP** | 阿里云 | 取决于已有组件及合规考虑 |
| 镜像 | **Docker** | Podman | 业界标准，对 CI 集成与 K8s 兼容性最佳 |

## 8. 风险与 Open Questions

### 8.1 修正后剩余的真 Risks
- **环境漂移 (P1)**: 解药是严格推行 `studio dev --simulate` 和 CI Dry-run，但依赖 PM 自觉性的策略常被绕过。
- **隐形 Git Merge Conflict UX**: 若多个 PM 修改同一 Skill 引发冲突，在剥离 Terminal 的 Web 界面优雅解决合并极其困难，容易造成挫败感。

### 8.2 真需要用户决策的 Open Questions
1. **Cloud Provider 选定**: AWS、GCP 还是内部既有云，将决定 IAM/S3/SQS 替代库的基底封装选型。
2. **OIDC IdP 选型**: 我们使用外部现成 SaaS (Auth0) 还是接入公司自身的 User Center？
3. **Queue Engine 定夺**: 切换至功能强大但学习成本高的 Temporal 还是坚守团队更熟悉的 Celery？
4. **启动资源确认**: “1 FT + 2 PT” 的算力是否随时就位？

### 8.3 测试数据隐私墙 (Nice-to-have)
PM 在本地想借用 C 端的失败案例复现 Bug。但强行把带 PII (个人隐私) 的线上真实 `test_inputs` Pull 到开发者笔记本再传 GitHub，涉嫌重大合规违章。需要规划一个阻断外传或自动脱敏的数据代理机制。

## 9. 上线 Ready Checklist (M3 终审)

- [ ] `GET /api/skills` 数据源已切至 DB，响应时间 < 200ms。
- [ ] Worker 从队列消费 `RunRequest` 且执行期间宿主 API 节点 CPU/内存无异常飙升。
- [ ] Pydantic Input Validation 正常拦截格式错误的 C 端提交。
- [ ] 针对纯 Prompt 的修改，CI/CD Pipeline 能在无人干预下自动触发 Merge 和推产线动作。
- [ ] AWS/GCP Metadata 路由不可被 Worker 容器访问 (Egress 屏蔽校验通过)。
- [ ] Redis Checkpoint 在模拟 Pod 被随机 Kill 后可成功被另一个 Worker 接管 (Resume)。

---

## 附录

- **A1**: 旧有审核资料 (`CLOUD_READINESS_AUDIT.md`, `CLOUD_INCOMPATIBLE_FEATURES.md`, `SPLIT_ARCHITECTURE_FEASIBILITY.md` 与 `SPLIT_ARCHITECTURE_PHASE_PLAN.md`) 均已被本综合分析吸收归档，旧文件可删。
- **A2**: 关联源码契约参考：`core/loader.py`、`core/runner.py`。