# Skill Studio 云端不兼容特性分析报告 (Cloud Incompatible Features)

**日期**: 2026-04-30
**目标规模**: 10,000+ C端用户，高峰期 1k-3k 并发 Run
**分析者**: 资深云原生架构师 (a2 Gemini)

---

## 1. Executive Summary (核心结论)

在详细审查了当前 `graph_agent` 与 `Studio` 的契约假设与运行时表现后，我发现在目前的单机模型中有 **3 个特性必须直接砍掉 (P0 无法实现)**，**3 个 UX 将不可避免地降级**，以及 **4 个深层框架契约在分布式环境下完全破产**。
最大的 **Deal-breaker** 是 **"用户通过自定义 Python script 工具执行业务逻辑"** 这一框架底层假设，它与 C 端云服务的多租户安全存在根本性冲突，若不彻底沙箱化或限制为 YAML 编排，整个 SaaS 模型将无法成立。

## 2. 类别 1: 必砍功能清单 (Cloud 不能做)

### 2.1 任意路径 PTY 与宿主机环境访问 (P0)
- **现状**: `TerminalManager` (`studio-backend/app/services/terminal_manager.py`) 通过 `ptyprocess.spawn` 直接拉起一个享有宿主机进程权限的交互式终端。
- **砍掉的影响**: C 端用户直接拥有了宿主机的 Shell 权限，能轻易越权访问 `/etc/passwd`、内部网络甚至其他租户的凭证文件。必须彻底砍除物理 PTY。
- **替代方案是否等价**: **否 (不可还原度 80%)**。改用前端纯 Chat 面板，或者极其受限的、仅能运行 `claude` 命令的伪终端，这会完全丧失 "Open CLI" 自由敲命令的极客感 UX。

### 2.2 自由编写与反射调用 Python Script 工具 (P0 Deal-breaker)
- **现状**: SKILL.md 支持 `tools: [script.my_module.my_func]`，框架会在 `core/loader.py` 通过 `importlib` 动态加载该 Python 文件并交给 LLM Agent 执行。
- **砍掉的影响**: 恶意用户只需写一段死循环或内网爆破代码，就能瞬间瘫痪服务集群。在缺乏重量级 VM 沙箱 (如 Firecracker) 的前提下，这在多租户集群中绝对无法实施。
- **替代方案是否等价**: **否 (不可还原度 90%)**。如果限制为官方审核白名单工具，将极大削弱 GraphAgent "自由扩展业务能力" 的核心卖点，变成一个残缺的玩具。

### 2.3 基于内存的 Event Bus 全局订阅 (P0)
- **现状**: `studio-backend/app/services/event_bus.py` 使用单机 `asyncio.Queue` 搭配 `watchdog`。
- **砍掉的影响**: 部署在 K8s 后，API Server 有多个 Replica。用户连在 Pod A 上，而修改了 SKILL 的请求路由到了 Pod B，此时内存中的 Pub/Sub 完全无法跨 Pod 通信。
- **替代方案是否等价**: **是 (不可还原度 10%)**。这个功能必须被 Redis Pub/Sub 彻底替代，对用户透明。

## 3. 类别 2: 必降级 UX 清单

### 3.1 PTY 或 WebSocket 流式打字的实时感
- **当前体验**: 本地 `xterm.js` <-> `ptyprocess` 之间几乎零延迟（< 10ms），就像在本地敲终端。
- **云端最佳近似**: 通过 API Gateway、Load Balancer 及跨实例 WebSocket 代理，端到端延迟通常在 100-300ms。高并发下排队打字的粘滞感将极其明显。
- **UX 损失量化**: 交互流畅度严重受损，体验从 100% 降到 60%。

### 3.2 FileWatcher 的实时毫秒级同步
- **当前体验**: `watchdog` 监控本地文件修改并即时推送到前端。
- **云端最佳近似**: 用户的 SKILL 将保存在 S3。要监控对象存储的变更，必须依靠 S3 的 Event Notification 写入 SQS 再被后端消费。链路至少有 1-3 秒延迟。
- **UX 损失量化**: 双轨编辑同步速度从 50ms 级别退化到秒级，可能会诱发竞态保存。

### 3.3 大体积 Artifact 的即时取用
- **当前体验**: `StorageManager` 将产物直接写入本地磁盘，前端可以瞬间拉取数百兆的数据。
- **云端最佳近似**: 必须提供短时有效（Signed URL）让前端去 S3 拉取，或者后端流式代理下载。
- **UX 损失量化**: 大文件的访问增加了网络 I/O 耗时，无法像本地文件系统一样瞬间挂载。

## 4. 类别 3: 框架契约不兼容清单

### 4.1 LangGraph Checkpoint 的 Thread-ID 单机假设
- **当前契约**: `core/checkpointer.py` 使用 `SqliteSaver` 维护断点。
- **为什么不成立**: 在水平扩展 (HPA) 的集群中，运行在 Worker Pod C 上的任务崩溃后，用户请求 Resume，此时请求很可能落入 API Pod D。Pod D 上没有那个本地的 `store.db`，Thread ID 会直接 404。
- **必改契约**: 必须将持久化层替换为 `langgraph-checkpoint-postgres` 或 Redis。

### 4.2 跨实例的 Subprocess Spawn 假设
- **当前契约**: `studio-backend/app/services/run_manager.py` L49 使用 `multiprocessing.Process` 生成子进程并在本地 `asyncio.Queue` 收发事件。
- **为什么不成立**: FastAPI 节点通常配置较小。直接在其内部 Spawn 可能长达几分钟的重量级 LangGraph 运算，会导致 API 节点迅速因 OOM 被杀。
- **必改契约**: Spawn 模式破产，必须改为通过分布式任务队列 (如 Celery/Temporal) 投递到高算力 Worker 集群执行。

### 4.3 模块级全局状态的非隔离性
- **当前契约**: 旧的 Python 脚本经常使用模块级全局变量做缓存。
- **为什么不成立**: 云端复用 Worker 进程中，如果上一个 Run 污染了模块级变量，下一个分发到同 Worker 的 Run（可能是其他租户的）将读到脏数据。
- **必改契约**: 严禁任何带有状态的 Python 工具；但在未对代码强制隔离时，框架无法保证此契约。

### 4.4 `tracing.jsonl` 与日志的并发落盘碰撞
- **当前契约**: 所有 callback 都使用文件系统 IO 进行日志追加（如 `TracingCallback` 写 `.jsonl`）。
- **为什么不成立**: 云端环境下，多个高并发调用落在挂载同一块共享盘（EFS）的不同 Pod 上，POSIX 锁将导致严重的争用或乱序。
- **必改契约**: 必须取消本地落盘，改由 `StudioQueueCallback` 聚合后推流至外部对象存储。

## 5. 类别 4: 法律 / 合规 "不能做" 清单

- **持久化留存包含 PII 的最终状态 (GDPR 风险)**: 若用户上传了真实的财务/医疗数据作为 `test_inputs`，而将 `final_state.json` 长久保留在 S3，直接违反数据最小化原则。技术上需实现定期 TTL。
- **无限制的 LLM 接口调用代理**: 万级 C 端免费用户足以触发上游 Provider 的 Abuse 封号策略。商业 ToS 不允许无限制的 API 倒卖。
- **对外网络扫描与滥用 (AUP 违反)**: 自由的 HTTP Requests 能力会被当作免费的高匿爬虫代理池使用，导致 AWS/GCP 账号因违反 AUP 被封。

## 6. Deal-breaker 评估 (致命缺陷)

**最致命的问题 (Deal-breaker)**：**放弃原生 Python Script 执行将抽空产品的核心灵魂**。
如果要上云，合规与安全性决定了我们**绝不能**让不可信的 C 端代码在环境中自由执行。一旦转为“YAML 限定白名单积木”模式，PM 遇到稍微复杂的预处理逻辑就无计可施。
如果要保留此能力，构建安全无状态 MicroVM 或 WASM 环境，其研发周期和算力成本也与 MVP 背道而驰。这是导致产品形态在单机转云端时发生质变的断腕级妥协。

## 7. 与上一份 Audit 的差异

- `CLOUD_READINESS_AUDIT.md` 侧重于**存储系统如何升级、进程如何编排**（建设改造方案）。
- 本报告 `CLOUD_INCOMPATIBLE_FEATURES.md` 侧重于**业务形态将被迫做出哪些无法等价的断腕级妥协**（破坏方案），揭示了 `importlib` 加载代码和 `multiprocessing` 隔离在 SaaS 语境下的逻辑死穴。

## 8. 风险与未知 (Open Questions)

- **如果只允许 YAML 编排，能保留多少产品吸引力？** 阉割外部工具接入后，"Skill Studio" 是否只是变成了一个大厂 API 的简陋壳子，相比直接使用 Dify 或 Coze 还有什么护城河？
- **多租户合规下，模型缓存数据是否会串门？** Anthropic 的 Prompt Caching 是否会在后台因为相似的 Token 发生租户间的数据泄漏？这是无法通过代码控制的黑盒。
