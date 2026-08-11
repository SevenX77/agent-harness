# 产品化 Gap 分析(2026-06-11)

> **目标(真理)** = 锁定设计 `productization-architecture-2026-06-11.md`;**现状** = 当前代码(被改的对象)。本文是实现任务清单的依据,逐管道带 `file:line`。

## 0. 一句话

**能力内核 / 插座大体就位**(印证"产品化 = 把插座做实,不是重做")。净缺集中在**对外抽象层**:adapter 可拆、存储三线 provider、成品库/发布流水线、凭证来源切换、fallback 浅接口、运行态/resume。另有若干**位置错**(逻辑放错模块,可"待迁"记账)。

## 1. 已就位(不动)

- engine、gateway **纯 SDK 无 API**(全包无 HTTP/uvicorn);
- gateway:角色解析(`resolver.py:140`)、角色→可调用模型(`call/chat_model.py:97`)、加工内核(标准化/归一化/lint/canonical 在包内)、产品策略**未污染** gateway;
- engine:三个注入口在(`model_resolver`/`event_subscriber`/`artifact_saver`,`runner.py:403`)、主运行路径只经一个注入的 `model_resolver.resolve`;
- studio:copilot 跑 Claude SDK + gateway 出路线(`copilot.py:206/436`)、golden 判定+基线在 studio(`golden_diff.py`)、前端无第二份配置真相、无 per-场景大编排器、templates/test_inputs/audit 干净。

## 2. 大净缺(实现工作 · 按建议下手顺序)

| # | Gap | 现状(file:line) | 要改成什么 |
|---|---|---|---|
| **1** | **存储三线 provider 未成形**(地基) | engine 裸 `Path` 写盘(`io/storage.py:166`)、`RunResult` 直接 `mkdir`+写 json(`runner.py:925`)、`artifact_saver` 是 `Any`+`inspect.signature` 嗅探(`io/manager.py:349`);checkpointer 走 env+全局单例(`checkpointer.py:123`)。gateway 裸 `Path.read_text` 读配置(`resolver.py:193-231`),包内无存储口、无 `user_id`。studio 有通用 `StorageBackend` 口(`core/ports/storage.py`)但是 Python 实现、engine 不经它、未拆线、无远程实现 | 定**三条显式接口**:配置真相线(get/put,无缓存,gateway 用)、运行产物线(put/get,写完不改,带 I/O 批处理,engine 用)、运行态线(快照/恢复,单实例独占,engine 用)。engine/gateway 内所有裸 `Path` 收口到接口;本地实现=Rust,远程=DB;预留 `user_id` |
| **2** | **adapter 不可拆、是"一坨"**(底座四核心) | engine/gateway 被当普通库,在 **16+ 处** `import` 进同一进程(engine 9+、gateway 7);无 `EngineClient`/`GatewayClient`,无"进程内/远程"传输开关 | 在 studio↔SDK 之间插**按模块拆的薄 adapter**(engine-adapter / gateway-adapter),原语一对一;adapter 内部传输可切换(本地=进程内直调、远程=HTTP)。gateway 挪远端只换 gateway-adapter,engine 不动 |
| **3** | **成品库/冻结成品/发布流水线净缺**(底座三核心) | engine 吃**源码路径**、每次现编译(`runner.py:403/1075`),无版本身份/内容寻址/成品库;`cache.py` 只是本地 AST 编译缓存(key=路径+mtime)。studio `/publish` **绕过编译直接 zip 源码**(`artifact_registry.py:91`),compile 与 publish 脱节;设计版本(git)与发布版本无命名空间隔离 | 编译产物=不可变快照+内容指纹;建**成品库** put(版本)/get(版本),**只装 publish**;run 入口从"取源码现编译"改成"按版本取成品来跑";发布=源码→编译→冻结→入库;设计期走 git 源码版本、临时产物不进库 |
| **4** | **凭证来源不可切换**(产品目标 §0.3) | `CredentialProviderProtocol` 只有 `describe`/`get(ref)`(`registry/contracts.py:32`),无"来源"维度;唯一实现从内存快照内联密钥取;无远端 vault 实现;凭证路径 grep `vault/remote` 零命中 | `ModelResolver` 已预留 `credential_provider` 注入点(`resolver.py:49`),补:来源维度(本地输入/远端 vault)+ 远端实现 + 脱敏隔离 |
| **5** | **fallback 决策浅接口净缺**(§3.2"共用路由大脑") | 决策内核 `classify_error_context`(`error_classification.py:101`)是纯函数但**未导出**;推进逻辑 `_next_candidate`+down-cache 锁在 `GatewayChatModel` 私有方法。studio-copilot 现在**自己遍历 routes 试下一条**(`copilot.py:224-273`),没复用 gateway 大脑 | 抽一条独立公共管道:输入=路线链+当前路线+调用状态 → 输出=下一步(重试/换/放弃)。导出给"自己执行"的调用方(copilot)复用 |
| **6** | **运行态线 / resume 未接** | studio `resume_run` 是 **501 桩**(`runs.py:69`);checkpoint 裸文件(`run_manager.py:167`)。engine `resume_skill` 已实现但断点存储走 env+全局单例,非注入接口 | resume 走运行态线 provider(注入);studio 薄接 engine `resume_skill` |

## 3. 位置错(逻辑放错模块 · 可"待迁"记账)

| 项 | 现状 | 目标(底座六) |
|---|---|---|
| **golden 判定重复** | engine 有一套完整判定(`evaluate_golden_baseline`→`golden_eval.py:147`,diff+打分+裁决+写报告)**且** studio 也有一套(`golden_diff.py:68`) | 收敛到 studio;engine 那套退役;studio 补"可调 copilot 语义判定"(现只有算法 diff) |
| **画布渲染/编辑(从源码,纠正)** | studio `/graph/serialize` 调 engine `serialize_graph`(`skills.py:1228`)做"图→GRAPH.md"写回;渲染侧 studio 自己建邻接(`skills.py:1246`)。**渲染不经编译产物**(编译产物只给 engine 跑) | 渲染/编辑 = studio 读写**源码**。"图→GRAPH.md"和"GRAPH.md→图"都是 skill 语法格式读写,要**单一来源防漂移**(共享一套轻量 parse/serialize,而非 studio/engine 各写一套) |
| **本地源码 I/O** | Python 写(`skills.py`/`git_local.py` subprocess);Rust 只启 sidecar+系统外壳,不碰源码 | D12:Rust 拥有本地 skill 源码读写 |
| **6 态计算** | studio 一手算+渲染(`llm_state_projection.py:18`)；materialize 也在 studio(`llm_role_materializer.py:27`) | gateway **算**健康态/materialize、studio **渲染** |
| **engine→gateway 直连泄漏** | engine 有 8 处直接 `import graph_agent_gateway`(`runner.py:228/235`、`interception.py:11`、`llm_phase_node.py:135`);predict 默认 mock 路径直连 gateway 造 resolver | 默认 resolver 也由调用方注入,engine 不直连 gateway 具体类型 |

## 4. 建议下手顺序

1. **存储三线 provider 接口**(地基:engine+gateway 都依赖,解锁本地 Rust / 远程 DB)
2. **adapter 可拆层 + 传输维度**(解锁"单独挪 gateway 远端")
3. **成品库 + 冻结成品 + 发布流水线**(engine 最大手术:run-by-version + 干净 publish)
4. **凭证来源 / fallback 浅接口 / resume**(局部,可并行)
5. **位置错迁移**(golden 收敛、图结构导出、Rust 源码、6 态拆分、解 gateway 直连)收尾

> 严重度:1/2/3 是产品化部署拓扑的硬卡点(不做就无法"engine/gateway 上服务器、studio 本地");4/5/6 是功能补全;§3 位置错多数可"待迁"记账、不阻塞主线。
