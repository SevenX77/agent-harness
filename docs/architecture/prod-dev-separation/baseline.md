# prod-dev-separation (architecture) — Baseline (当下代码实现逻辑)

> **Status**: Filled by a1 (Codex), 2026-05-20
> **Scope**: baseline: Harness/Callbacks/Schema 缠绕现状; MVP0: Engine 降为纯节点合集 + Studio 降为外部唤起壳
> **配套**: 见 [INDEX.md](../../INDEX.md) 5 维模板 + cross-link 规则 + writing conventions。

## UI/UX

当前 prod/dev separation 不是“已经完全拆成生产 SDK 和开发壳”的状态，而是一个本地优先 Studio + Python engine 包 + Tauri sidecar 的组合。用户看到的是桌面应用或 Vite Web UI；真正执行 skill 的是 Studio backend 调 graph-agent。Tauri 只负责桌面壳、文件/终端类系统能力和启动 sidecar，不直接执行 graph。

Tauri 打包配置显示产物包含前端 dist、vendor、python_runtime、skills、config，见 `apps/studio/tauri/tauri.conf.json:6` 到 `apps/studio/tauri/tauri.conf.json:33`。这说明当前桌面 prod 包不是纯前端，它把 Python runtime 和 backend 资源一起带上。Python runtime lock 指向 Python 3.12.13 多平台包，见 `apps/studio/tauri/python-runtime.lock.json:3` 到 `apps/studio/tauri/python-runtime.lock.json:36`。

UI 层通过 runtime config 找到 backend。浏览器/dev 模式默认走 `VITE_STUDIO_API_BASE_URL` 或 localhost，见 `apps/studio/frontend/src/config/runtime.ts:27` 到 `apps/studio/frontend/src/config/runtime.ts:40`；Tauri 模式则调用 `get_sidecar_config`，见 `apps/studio/frontend/src/config/runtime.ts:43` 到 `apps/studio/frontend/src/config/runtime.ts:58`。所以“prod/dev 分离”在 UI 层表现为：同一 React app，根据运行环境选择 sidecar config 或 web fallback config。

当前 UI 没有一套单独的“prod UI”和“dev UI”。React app 是同一份，差异来自运行环境、API base URL、token 来源和 Tauri IPC 是否可用。`isTauriRuntime()` 检查 `window.__TAURI_INTERNALS__`，见 `apps/studio/frontend/src/config/runtime.ts:23` 到 `apps/studio/frontend/src/config/runtime.ts:25`；非 Tauri fallback config 在 `apps/studio/frontend/src/config/runtime.ts:27` 到 `apps/studio/frontend/src/config/runtime.ts:40`。

桌面用户体验中，sidecar 是隐式启动的。Rust app 在 setup 中启动 sidecar manager，见 `apps/studio/tauri/src/lib.rs:166` 到 `apps/studio/tauri/src/lib.rs:188`；前端再通过 sidecar config 得到 port 和 token，见 `apps/studio/frontend/src/config/runtime.ts:43` 到 `apps/studio/frontend/src/config/runtime.ts:58`。用户看到的是一个 app，但进程上至少有 Tauri shell、frontend webview、Python backend。

浏览器/dev 用户体验中，Vite proxy 是关键连接层。前端同源请求 `/api` 和 `/ws`，Vite 转到 local backend，见 `apps/studio/frontend/vite.config.ts:47` 到 `apps/studio/frontend/vite.config.ts:68`。因此 dev tunnel 看起来像一个远端 web app，但执行仍在本机 backend/engine。

当前 architecture baseline 不能把 Studio 描述为“纯生产 runtime 外壳”。Tauri bundle 明确包含 vendor/backend、vendor/site-packages、python_runtime、skills、config，见 `apps/studio/tauri/tauri.conf.json:25` 到 `apps/studio/tauri/tauri.conf.json:33`。这是一种一体化桌面分发形态，而不是 production engine 与 development Studio 的硬隔离。

UI 层的 prod/dev 差异也不改变 graph-agent 运行路径。无论是 Tauri 还是浏览器 dev，skill compile/run 最终都到 Studio backend，再由 backend 调 Python package。compile 服务见 `apps/studio/backend/app/services/skills.py:294` 到 `apps/studio/backend/app/services/skills.py:311`；run worker 调 `run_skill()`，见 `apps/studio/backend/app/services/run_manager.py:81` 到 `apps/studio/backend/app/services/run_manager.py:105`。

所以 UI/UX 维度的当下结论是：用户有桌面与 web/dev 两种入口，但它们共享前端和 backend contract；Tauri 提供桌面能力与 sidecar lifecycle，Vite 提供开发代理，二者都不是独立 engine runtime。

## 前端逻辑

前端与 backend 的主要通信是 HTTP + WebSocket。Axios client 默认 base URL 是 `VITE_STUDIO_API_BASE_URL` 或 `http://localhost:8787/api`，见 `apps/studio/frontend/src/api/client.ts:20` 到 `apps/studio/frontend/src/api/client.ts:27`；WebSocket URL 根据 API base URL 转成 ws/wss，并追加 token，见 `apps/studio/frontend/src/api/client.ts:101` 到 `apps/studio/frontend/src/api/client.ts:108`。

Dev tunnel 模式下，Vite 以 `0.0.0.0:5173` 服务前端，并把 `/api` 转发到 `127.0.0.1:8787`、`/ws` 转发到 backend WebSocket，见 `apps/studio/frontend/vite.config.ts:47` 到 `apps/studio/frontend/vite.config.ts:68`。`.env.local` 当前把 `VITE_STUDIO_API_BASE_URL=/api`，见 `apps/studio/frontend/.env.local:1`，这让浏览器同源访问 Vite，再由 Vite proxy 转 backend。

Dev tunnel token 走 URL hash。前端启动时调用 `bootstrapTunnelToken()`，见 `apps/studio/frontend/src/main.tsx:6` 到 `apps/studio/frontend/src/main.tsx:12`；token bootstrap 从 `#tkn=...` 取值并放入 sessionStorage，见 `apps/studio/frontend/src/config/tunnel-token.ts:1` 到 `apps/studio/frontend/src/config/tunnel-token.ts:13`。这和生产 Tauri 的 sidecar token 不同，但两者最终都进入 Authorization Bearer header，header 注入见 `apps/studio/frontend/src/api/client.ts:46` 到 `apps/studio/frontend/src/api/client.ts:54`。

Tauri IPC 只负责桌面能力，不承载业务 API。前端 `openInCursor/openInTerminal/openInCodex/revealInFileManager/selectSkillDirectory` 通过 Tauri command 或 dialog plugin 实现，见 `apps/studio/frontend/src/lib/tauri.ts:4` 到 `apps/studio/frontend/src/lib/tauri.ts:79`。业务数据仍走 HTTP/WS。

前端 token 模型体现了当前 prod/dev 的混合形态。API header 注入 Bearer token，见 `apps/studio/frontend/src/api/client.ts:46` 到 `apps/studio/frontend/src/api/client.ts:54`；dev tunnel token 从 URL hash 进入 sessionStorage，见 `apps/studio/frontend/src/config/tunnel-token.ts:1` 到 `apps/studio/frontend/src/config/tunnel-token.ts:13`；Tauri token 则来自 sidecar config，见 `apps/studio/frontend/src/config/runtime.ts:43` 到 `apps/studio/frontend/src/config/runtime.ts:58`。前端最终把这些来源统一成 HTTP/WS token。

WebSocket URL 也被统一处理。`wsUrl()` 会基于 API base URL 转换协议并附带 token，见 `apps/studio/frontend/src/api/client.ts:101` 到 `apps/studio/frontend/src/api/client.ts:108`。这让 run events、terminal、studio events 和 Copilot 可以复用同一 backend host 形态，但它不是 prod/dev 边界的强类型抽象。

前端业务 API 不区分“生产运行”和“开发运行”。`compileSkill()`、`startRun()`、`getSkillDetail()`、`writeSkillFile()` 都在同一个 API client 中，见 `apps/studio/frontend/src/api/client.ts:81` 到 `apps/studio/frontend/src/api/client.ts:90`、`apps/studio/frontend/src/api/client.ts:140` 到 `apps/studio/frontend/src/api/client.ts:144`、`apps/studio/frontend/src/api/client.ts:157` 到 `apps/studio/frontend/src/api/client.ts:173`。这说明 Studio 前端是开发工作台式客户端。

Tauri desktop-only functions 有 runtime guard。`ensureTauri()` 会在非 Tauri 环境抛错，见 `apps/studio/frontend/src/lib/tauri.ts:4` 到 `apps/studio/frontend/src/lib/tauri.ts:12`。因此 web/dev 模式不会获得本地 shell command 能力，除非通过 backend 其他 API；这是一条现有能力边界。

当前 frontend separation 的实质是“transport/config separation”，不是 feature separation。HTTP、WS、IPC 三条 transport 各自负责不同能力：业务数据用 HTTP/WS，桌面系统动作用 IPC，dev tunnel 用 Vite proxy 和 token hash。这个分层在代码中清晰存在，但业务 feature 本身没有拆成 prod-only/dev-only 两套。

从 architecture 角度看，前端没有直接 import graph-agent，也没有在浏览器里执行 Python skill。所有 engine 行为都通过 backend API 间接发生，见 `apps/studio/frontend/src/api/client.ts:81` 到 `apps/studio/frontend/src/api/client.ts:144` 和 `apps/studio/backend/app/services/run_manager.py:81` 到 `apps/studio/backend/app/services/run_manager.py:105`。这是当前最稳定的一条 prod/dev 边界。

## 后端功能

Studio backend 是 FastAPI sidecar。应用创建时注册 auth、CORS、exception handlers 和所有 routers，见 `apps/studio/backend/app/main.py:112` 到 `apps/studio/backend/app/main.py:140`。启动参数默认 host `127.0.0.1`、port `8787`，见 `apps/studio/backend/app/main.py:160` 到 `apps/studio/backend/app/main.py:164`。

鉴权没有 dev bypass。`configure_api_auth()` 要求 `STUDIO_API_TOKEN` 或 `STUDIO_DEV_TUNNEL_TOKEN`，否则拒绝启动，见 `apps/studio/backend/app/main.py:66` 到 `apps/studio/backend/app/main.py:78`。除 `/health` 外，HTTP 请求必须有 Bearer token，见 `apps/studio/backend/app/main.py:80` 到 `apps/studio/backend/app/main.py:99`。CORS 默认允许本地 Vite/localhost，并可通过 `STUDIO_CORS_EXTRA_ORIGINS` 扩展，见 `apps/studio/backend/app/core/config.py:19` 到 `apps/studio/backend/app/core/config.py:29`、`apps/studio/backend/app/core/middleware.py:11` 到 `apps/studio/backend/app/core/middleware.py:19`。

Tauri sidecar 会在桌面启动时拉起 Python backend。Rust app 如果未设置 `STUDIO_TAURI_DISABLE_SIDECAR=1`，会解析 resource root，创建 SidecarLaunchConfig，然后启动 SidecarManager，见 `apps/studio/tauri/src/lib.rs:166` 到 `apps/studio/tauri/src/lib.rs:188`。退出时会 shutdown sidecar，见 `apps/studio/tauri/src/lib.rs:200` 到 `apps/studio/tauri/src/lib.rs:217`。

SidecarLaunchConfig 指向 bundled python、vendor/backend、vendor/site-packages、vendor/resources，见 `apps/studio/tauri/src/sidecar.rs:53` 到 `apps/studio/tauri/src/sidecar.rs:74`。spawn sidecar 时设置 `PYTHONPATH`、`STUDIO_RESOURCE_DIR`、`STUDIO_API_TOKEN`、`STUDIO_EXIT_ON_ORPHAN`，见 `apps/studio/tauri/src/sidecar.rs:241` 到 `apps/studio/tauri/src/sidecar.rs:260`。健康检查通过后 runtime config 暴露 port、resourceDir 和 token，见 `apps/studio/tauri/src/sidecar.rs:123` 到 `apps/studio/tauri/src/sidecar.rs:134`。

Engine 与 Studio backend 的耦合点很明确：backend import graph-agent package，而不是通过外部 process 或 RPC 调 engine。compile 用 `compile_skill()`，见 `apps/studio/backend/app/services/skills.py:294` 到 `apps/studio/backend/app/services/skills.py:311`；run subprocess 中调用 `run_skill()`，见 `apps/studio/backend/app/services/run_manager.py:81` 到 `apps/studio/backend/app/services/run_manager.py:105`；predict service 也 import `run_skill`、`SkillLoader`、`PredictTracingCallback`，见 `apps/studio/backend/app/services/predictor.py:12` 到 `apps/studio/backend/app/services/predictor.py:29`。

Tracing/schema 缠绕已由 T3 收敛一层：engine public run API 使用 `event_subscriber`，默认落盘由内部 `_TraceJsonlSink` 负责；Studio run manager 通过 `_queue_event_subscriber` 接队列事件，见 `apps/studio/backend/app/services/run_manager.py:74` 到 `apps/studio/backend/app/services/run_manager.py:104`。仍需区分的是：实时 UI subscriber、run artifact、schema validation 分属不同边界。

Sidecar 的 Python runtime 选择也属于后端/桌面边界。Rust sidecar code 根据 bundled runtime 找 python executable，见 `apps/studio/tauri/src/sidecar.rs:199` 到 `apps/studio/tauri/src/sidecar.rs:228`；host target triple 解析在 `apps/studio/tauri/src/sidecar.rs:230` 到 `apps/studio/tauri/src/sidecar.rs:238`。这说明桌面包依赖本地 bundled Python，而不是用户系统 Python。

Sidecar spawn 时把 backend module 作为 Python 进程启动，并注入 `PYTHONPATH`、`STUDIO_RESOURCE_DIR`、`STUDIO_API_TOKEN`、`STUDIO_EXIT_ON_ORPHAN`，见 `apps/studio/tauri/src/sidecar.rs:241` 到 `apps/studio/tauri/src/sidecar.rs:260`。这是当前“production desktop”实际运行后端的机制。

后端 auth 在开发和桌面都强制存在。`configure_api_auth()` 没有本地开发免鉴权分支，见 `apps/studio/backend/app/main.py:66` 到 `apps/studio/backend/app/main.py:99`。这让 dev tunnel 和 Tauri sidecar 都使用 Bearer token，避免把“开发模式”变成无认证 backend。

CORS 是 backend 层的 web/dev 适配，不是 engine 适配。配置允许本地 Vite/localhost，见 `apps/studio/backend/app/core/config.py:19` 到 `apps/studio/backend/app/core/config.py:29`；middleware 挂载在 `apps/studio/backend/app/core/middleware.py:11` 到 `apps/studio/backend/app/core/middleware.py:19`。Tauri webview 不需要以同样方式依赖 Vite proxy，但 backend 仍提供同一 HTTP API。

Backend router 注册是单一 app。`create_app()` 注册 skills、runs、compare、golden、llm、copilot、websockets 等，见 `apps/studio/backend/app/main.py:112` 到 `apps/studio/backend/app/main.py:140`。没有单独的 production-only router set 或 development-only router set。

run manager 的 artifact model 进一步证明 Studio backend 是开发工作台层。`get_run_detail()` 从 run directory 读取 input、trace、final_state、artifacts，见 `apps/studio/backend/app/services/run_manager.py:304` 到 `apps/studio/backend/app/services/run_manager.py:317`。这不是纯 engine SDK return path，而是 Studio 运行记录。

compile service 也承担 Studio 格式转换。`compile_skill_for_studio()` 调 graph-agent compile 后把结果转成 Studio compile contract，见 `apps/studio/backend/app/services/skills.py:294` 到 `apps/studio/backend/app/services/skills.py:311`。因此 backend 是 engine 与 UI 之间的 adapter，不是透明代理。

Predict service 同样 import engine runtime surface，见 `apps/studio/backend/app/services/predictor.py:12` 到 `apps/studio/backend/app/services/predictor.py:29`。这说明 engine 能力不仅被 run manager 使用，也被其他 Studio feature 直接作为 package API 调用。

后端功能维度的结论是：当前 separation 是“Studio backend 作为本地服务承载 engine package”，不是“engine 作为独立生产服务，Studio 只是外部开发客户端”。Callbacks、schemas、artifacts、predict、compile 都在 backend/engine 包边界处交织。

## API

前端到 Studio backend 的业务 API 包括 skills、compile、runs、predict、golden、compare、copilot、llm。核心入口：skill detail `GET /api/skills/{skill_id}`，见 `apps/studio/backend/app/routers/skills.py:98` 到 `apps/studio/backend/app/routers/skills.py:105`；compile `POST /api/skills/{skill_id}/compile`，见 `apps/studio/backend/app/routers/skills.py:108` 到 `apps/studio/backend/app/routers/skills.py:118`；run `POST /api/skills/{skill_id}/runs`，见 `apps/studio/backend/app/routers/runs.py:27` 到 `apps/studio/backend/app/routers/runs.py:29`；run events WebSocket `/ws/runs/{run_id}`，见 `apps/studio/backend/app/routers/websockets.py:27` 到 `apps/studio/backend/app/routers/websockets.py:39`。

Tauri IPC API 包括 `get_sidecar_config`、`get_sidecar_stderr`、`open_in_cursor`、`open_in_codex`、`open_in_terminal`、`reveal_in_file_manager`，注册在 `apps/studio/tauri/src/lib.rs:147` 到 `apps/studio/tauri/src/lib.rs:157`。这些命令不是业务 API，它们是桌面壳能力和 sidecar 生命周期能力。

Engine public API 仍是 Python package API：`run_skill()`，见 `packages/graph-agent/src/graph_agent/core/runner.py:65` 到 `packages/graph-agent/src/graph_agent/core/runner.py:79`；V2.1 graph assembly `assemble_graph()`，见 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:90` 到 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:100`；manifest/state 模型见 `packages/graph-agent/src/graph_agent/core/manifest.py:45` 到 `packages/graph-agent/src/graph_agent/core/manifest.py:90`、`packages/graph-agent/src/graph_agent/runtime/state.py:35` 到 `packages/graph-agent/src/graph_agent/runtime/state.py:41`。

HTTP API 和 Tauri IPC 的边界当前基本清晰。业务资源通过 FastAPI routers 暴露，见 `apps/studio/backend/app/main.py:112` 到 `apps/studio/backend/app/main.py:140`；本地系统动作通过 Tauri commands 暴露，见 `apps/studio/tauri/src/lib.rs:147` 到 `apps/studio/tauri/src/lib.rs:157`。这是一条现有 separation 线。

WebSocket API 归 backend，不归 Tauri。run events、terminal、studio events 在 `apps/studio/backend/app/routers/websockets.py:27` 到 `apps/studio/backend/app/routers/websockets.py:55`。Tauri 只负责 sidecar 的本地启动与命令，不负责业务 event 协议。

Dev tunnel API 形态没有新增 backend endpoint。前端通过 `/api` 和 `/ws` proxy，见 `apps/studio/frontend/vite.config.ts:47` 到 `apps/studio/frontend/vite.config.ts:68`；token 通过 hash bootstrap，见 `apps/studio/frontend/src/config/tunnel-token.ts:1` 到 `apps/studio/frontend/src/config/tunnel-token.ts:13`。backend 仍只看到 Bearer token HTTP/WS 请求。

Sidecar config API 不是 HTTP API，而是 Tauri command。`get_sidecar_config` 注册在 `apps/studio/tauri/src/lib.rs:147` 到 `apps/studio/tauri/src/lib.rs:157`，前端调用点在 `apps/studio/frontend/src/config/runtime.ts:43` 到 `apps/studio/frontend/src/config/runtime.ts:58`。这条路径只存在于桌面运行环境。

Engine API 没有被包装成稳定 external RPC。Studio backend import Python module 并调用 `run_skill()`、`compile_skill()`，见 `apps/studio/backend/app/services/run_manager.py:81` 到 `apps/studio/backend/app/services/run_manager.py:105`、`apps/studio/backend/app/services/skills.py:294` 到 `apps/studio/backend/app/services/skills.py:311`。这保留了 package-level coupling。

API 层因此有三种 contract：frontend-backend HTTP/WS contract、frontend-Tauri IPC contract、backend-engine Python function contract。当前架构没有把它们收敛成一个统一 schema registry。

这也解释了 observability/schema 缠绕为什么属于 architecture 问题：run events 需要 `event_subscriber`，trace artifacts 需要 engine sink，API 表面能启动 run，但 event 语义是否完整取决于 engine 分支内部行为。

## Data Model / State

prod/dev separation 的核心状态分四层。

第一层是 frontend runtime config。`SidecarConfig` 包含 `port/baseURL/wsURL/resourceDir/api_token`，定义在 `apps/studio/frontend/src/config/runtime.ts:3` 到 `apps/studio/frontend/src/config/runtime.ts:9`。Tauri 模式来自 `get_sidecar_config`，web/dev 模式来自 fallback base URL。

第二层是 Studio backend 的资源路径和用户目录。backend config 定义 `RESOURCE_DIR`、`APP_SETTINGS_DIR`、`SKILLS_DIR`、`DEFAULT_SKILLS_ROOT`、`WORKSPACES_DIR`，见 `apps/studio/backend/app/core/config.py:52` 到 `apps/studio/backend/app/core/config.py:63`。这说明开发态/桌面态资源位置由 env/resource dir 决定，不是硬编码到 engine。

第三层是 engine 的 graph state。V2.1 `BlackboardState` 是 `data/flow/messages/run_id`，见 `packages/graph-agent/src/graph_agent/runtime/state.py:35` 到 `packages/graph-agent/src/graph_agent/runtime/state.py:41`。当前缺 input funnel 和 phase-level IO contract，具体审计 A1/A2/A3/A6 见 [state-and-io-contract baseline](../../engine/state-and-io-contract/baseline.md)。

第四层是 run artifact state。Studio `RunDetail` 从 run directory 读取 `input_data.json`、`trace.jsonl`、`final_state.json` 和 artifacts。这层是 Studio 的开发态记录，不是 engine package 的纯模型。

第五层是 Tauri sidecar state。Rust `SidecarManager` 保存 child process、config 和 health 状态，启动健康检查见 `apps/studio/tauri/src/sidecar.rs:123` 到 `apps/studio/tauri/src/sidecar.rs:134`。这层状态只在桌面壳存在，web/dev 浏览器没有它。

第六层是 auth/token state。backend 从 env 读取 `STUDIO_API_TOKEN` 或 `STUDIO_DEV_TUNNEL_TOKEN`，见 `apps/studio/backend/app/main.py:66` 到 `apps/studio/backend/app/main.py:78`；前端从 sidecar config 或 tunnel hash 设置 token，见 `apps/studio/frontend/src/config/runtime.ts:43` 到 `apps/studio/frontend/src/config/runtime.ts:58`、`apps/studio/frontend/src/config/tunnel-token.ts:1` 到 `apps/studio/frontend/src/config/tunnel-token.ts:13`。这层连接 prod desktop 和 dev tunnel。

第七层是 packaged resource state。Tauri config 把 resources 列进 bundle，见 `apps/studio/tauri/tauri.conf.json:25` 到 `apps/studio/tauri/tauri.conf.json:33`；backend config 再通过 `RESOURCE_DIR` 和相关目录定位资源，见 `apps/studio/backend/app/core/config.py:52` 到 `apps/studio/backend/app/core/config.py:63`。这说明资源位置由 packaging/env 和 backend config 共同决定。

第八层是 frontend local/session state。dev tunnel token 存 sessionStorage，见 `apps/studio/frontend/src/config/tunnel-token.ts:1` 到 `apps/studio/frontend/src/config/tunnel-token.ts:13`；runtime config 缓存在 module-level `runtimeConfigPromise`，见 `apps/studio/frontend/src/config/runtime.ts:43` 到 `apps/studio/frontend/src/config/runtime.ts:58`。这类状态只影响连接 backend 的方式，不影响 engine graph state。

Engine state 与 Studio state 的最大分界是：engine V2.1 `BlackboardState` 是运行时数据黑板，Studio `RunDetail` 是运行后观察/记录外壳。二者通过 run worker 和 artifacts 连接，见 `packages/graph-agent/src/graph_agent/runtime/state.py:35` 到 `packages/graph-agent/src/graph_agent/runtime/state.py:41`、`apps/studio/backend/app/services/run_manager.py:304` 到 `apps/studio/backend/app/services/run_manager.py:317`。

旧 Harness 还有自己的 checkpointer/runtime storage 概念，见 `packages/graph-agent/src/graph_agent/core/harness.py:391` 到 `packages/graph-agent/src/graph_agent/core/harness.py:430`、`packages/graph-agent/src/graph_agent/core/harness.py:568` 到 `packages/graph-agent/src/graph_agent/core/harness.py:629`。这进一步说明 current state model 不是单层。

Data Model / State 维度的结论：当前 prod/dev separation 不是通过一个统一 runtime state 达成，而是通过 frontend runtime config、backend resources、Tauri sidecar state、engine blackboard、run artifacts、token state 多层拼接达成。

## Cross-feature interaction

与 agent cognitive architecture：本文件描述物理/进程边界，认知模型和 Harness/V2.1 并存状态见 [agent-cognitive-architecture baseline](../agent-cognitive-architecture/baseline.md)。

与 workspace file system：Tauri 负责桌面打开目录、系统 reveal、终端等能力；backend 负责 skill directory/index/workspace；前端通过 HTTP/IPC 分别调用。文件系统细节见 [workspace-file-system baseline](../../studio/system-level/workspace-file-system/baseline.md)。

与 tracing：Studio 层通过 `event_subscriber` 把 engine typed events 转成 WebSocket run events，默认落盘由 engine 写 `trace.jsonl`。当前 trace 主线见 [tracing-and-observability baseline](../../engine/tracing-and-observability/baseline.md)。

与 schema：compile 阶段由 Studio backend 调 graph-agent compile，run 阶段由 run manager subprocess 调 run_skill；但 runtime input funnel、phase-level IO、subgraph isolation 仍是 engine 内部缺口，不是 Studio 可以单独修好的问题。相关缺口见 [state-and-io-contract baseline](../../engine/state-and-io-contract/baseline.md)。

与 dev tunnel：Vite proxy + tunnel token 让远程浏览器访问本机 Studio，backend 通过 `STUDIO_DEV_TUNNEL_TOKEN` 接受同一套 Bearer auth。它是开发访问形态，不改变 engine 执行路径。

与 engine execution runtime：P0-1/P1-2/P1-3/P1-4/A4/A5 的 runtime 缺口见 [execution-runtime baseline](../../engine/execution-runtime/baseline.md)。这意味着 prod/dev separation 不能只看 Tauri/Vite，还要看 engine branch 是否提供同等 runtime contract。

与 engine state/io：缺 input funnel、phase-level IO、subgraph isolation 的问题见 [state-and-io-contract baseline](../../engine/state-and-io-contract/baseline.md)。Studio backend 即使包装 API，也不能弥补 engine 内部 IO contract 不完整。

与 Studio Canvas：Canvas 消费 compile/manifest/DAG，运行在同一个 React app 中；桌面和 web/dev 入口不会改变 Canvas 的 graph model。Canvas feature 细节见 [canvas-topology baseline](../../studio/feature-folders/canvas-topology/baseline.md)。

与 Copilot：Copilot 走 backend Claude Agent SDK session 和 view context cache，不走 Tauri IPC。其缺 mentions payload 的 audit 映射在 [agent-cognitive-architecture baseline](../agent-cognitive-architecture/baseline.md) 和 [copilot-assistance baseline](../../studio/feature-folders/copilot-assistance/baseline.md) 中体现。

与 workspace file system：Tauri IPC 提供本地打开/终端/reveal，backend 管理 skill dirs 和 workspaces。两者共同构成开发工作台，不是单一生产 runtime。相关 feature 见 [workspace-file-system baseline](../../studio/system-level/workspace-file-system/baseline.md)。

与 trace visualization：Studio trace 依赖 `event_subscriber` / event sink / artifact pipeline。Tauri/Vite 只是入口差异，trace 完整性取决于 backend run manager 和 engine event 接入，见 `apps/studio/backend/app/services/run_manager.py:74` 到 `apps/studio/backend/app/services/run_manager.py:105`。

与 packaging：Tauri bundle 包含 Python runtime 和 backend resources，见 `apps/studio/tauri/tauri.conf.json:25` 到 `apps/studio/tauri/tauri.conf.json:33`、`apps/studio/tauri/python-runtime.lock.json:3` 到 `apps/studio/tauri/python-runtime.lock.json:36`。这让桌面分发能独立运行本地 backend，但也意味着当前 prod 包携带开发工作台依赖。

与 auth/security：dev tunnel 与 Tauri 都使用 Bearer token，backend 没有 dev bypass，见 `apps/studio/backend/app/main.py:66` 到 `apps/studio/backend/app/main.py:99`。这是当前 separation 中少数比较一致的横切 contract。

最终边界：本 baseline 不提出拆分方案，不声称 MVP0 已达成，不移动任何代码。它只记录当前真实分层：同一前端，多 transport；FastAPI sidecar 承载 Studio API；Tauri 负责桌面壳和 Python sidecar；engine 仍以 Python package 嵌入 backend；callbacks/schema/state 在 backend-engine 边界处仍缠绕。

Audit 映射补充：Harness/Callbacks/Schema 缠绕曾经表现为 legacy runner 与 Studio worker 创建 callback 列表。PR-1 后当前事实是：engine runner 创建 `_CompositeEventSink`，见 `packages/graph-agent/src/graph_agent/core/runner.py:237` 到 `packages/graph-agent/src/graph_agent/core/runner.py:248`；Studio run worker 创建 `_queue_event_subscriber` 并传给 `run_skill(event_subscriber=...)`，见 `apps/studio/backend/app/services/run_manager.py:74` 到 `apps/studio/backend/app/services/run_manager.py:105`。

Audit 映射补充：Engine 不是纯节点合集。旧 Harness 仍然集中 phases、callbacks、IO config、context mapping、checkpointer、resolver、retry router、graph builder，见 `packages/graph-agent/src/graph_agent/core/harness.py:356` 到 `packages/graph-agent/src/graph_agent/core/harness.py:390`。这就是 prod/dev separation baseline 必须记录的现状。

Audit 映射补充：Studio 也不只是外部唤起壳。它有 run manager、artifact reader、compile adapter、predict service、Copilot service 和 workspace/file APIs。run detail artifact reader 见 `apps/studio/backend/app/services/run_manager.py:304` 到 `apps/studio/backend/app/services/run_manager.py:317`；compile adapter 见 `apps/studio/backend/app/services/skills.py:294` 到 `apps/studio/backend/app/services/skills.py:311`。

Desktop 映射补充：Tauri sidecar lifecycle 是桌面生产形态的核心。启动逻辑见 `apps/studio/tauri/src/lib.rs:166` 到 `apps/studio/tauri/src/lib.rs:188`；退出 shutdown 见 `apps/studio/tauri/src/lib.rs:200` 到 `apps/studio/tauri/src/lib.rs:217`。这条路径在浏览器 dev 模式不存在。

Desktop 映射补充：sidecar 运行依赖 bundled resources。config 指向 `vendor/python_runtime`、`vendor/backend`、`vendor/site-packages`、`vendor/resources`，见 `apps/studio/tauri/src/sidecar.rs:53` 到 `apps/studio/tauri/src/sidecar.rs:74`。Tauri bundle 资源列表也写在 `apps/studio/tauri/tauri.conf.json:25` 到 `apps/studio/tauri/tauri.conf.json:33`。

Dev 映射补充：Vite proxy 和 tunnel token 是开发访问层，不是 engine 运行层。proxy 配置见 `apps/studio/frontend/vite.config.ts:47` 到 `apps/studio/frontend/vite.config.ts:68`；token hash bootstrap 见 `apps/studio/frontend/src/config/tunnel-token.ts:1` 到 `apps/studio/frontend/src/config/tunnel-token.ts:13`。run path 仍进 backend。

Security 映射补充：backend auth contract 同时覆盖 Tauri 和 dev tunnel。token env 读取见 `apps/studio/backend/app/main.py:66` 到 `apps/studio/backend/app/main.py:78`；HTTP auth enforcement 见 `apps/studio/backend/app/main.py:80` 到 `apps/studio/backend/app/main.py:99`。这不是 feature 分离，但提供了统一访问边界。

Transport 映射补充：业务 HTTP API、业务 WebSocket、桌面 IPC 三条通道并存。HTTP routers 注册见 `apps/studio/backend/app/main.py:112` 到 `apps/studio/backend/app/main.py:140`；WebSocket routes 见 `apps/studio/backend/app/routers/websockets.py:27` 到 `apps/studio/backend/app/routers/websockets.py:55`；Tauri command 注册见 `apps/studio/tauri/src/lib.rs:147` 到 `apps/studio/tauri/src/lib.rs:157`。

State 映射补充：frontend runtime config 是连接状态，不是业务状态。`SidecarConfig` 字段见 `apps/studio/frontend/src/config/runtime.ts:3` 到 `apps/studio/frontend/src/config/runtime.ts:9`；fallback 和 Tauri config resolution 见 `apps/studio/frontend/src/config/runtime.ts:27` 到 `apps/studio/frontend/src/config/runtime.ts:58`。

State 映射补充：backend resource dirs 是 Studio 状态基础。`RESOURCE_DIR`、`APP_SETTINGS_DIR`、`SKILLS_DIR`、`DEFAULT_SKILLS_ROOT`、`WORKSPACES_DIR` 见 `apps/studio/backend/app/core/config.py:52` 到 `apps/studio/backend/app/core/config.py:63`。这解释了桌面资源和开发资源如何进入同一 backend。

State 映射补充：engine graph state 仍在 graph-agent 包内。`BlackboardState` 定义见 `packages/graph-agent/src/graph_agent/runtime/state.py:35` 到 `packages/graph-agent/src/graph_agent/runtime/state.py:41`；`shallow_dict_merge` 冲突语义见 `packages/graph-agent/src/graph_agent/runtime/state.py:13` 到 `packages/graph-agent/src/graph_agent/runtime/state.py:32`。Studio 不能通过 packaging 边界改变这件事。

API 映射补充：frontend API client 的 base URL 和 token header 说明前端只知道 Studio backend，不知道 engine internals，见 `apps/studio/frontend/src/api/client.ts:20` 到 `apps/studio/frontend/src/api/client.ts:54`。这是一条现有隔离线。

API 映射补充：backend-engine 之间没有同样强的隔离。backend 直接 import `run_skill`、`SkillLoader`、`PredictTracingCallback`，见 `apps/studio/backend/app/services/predictor.py:12` 到 `apps/studio/backend/app/services/predictor.py:29`；run manager 也直接调用 `run_skill()`，见 `apps/studio/backend/app/services/run_manager.py:81` 到 `apps/studio/backend/app/services/run_manager.py:105`。

Packaging 映射补充：Python runtime lock 固定多平台 Python 3.12.13 包，见 `apps/studio/tauri/python-runtime.lock.json:3` 到 `apps/studio/tauri/python-runtime.lock.json:36`。这使桌面包更自包含，但也说明当前 prod 包携带 runtime 依赖，而非调用外部 production engine。

Packaging 映射补充：Tauri build 配置使用 frontend dist 和 devUrl，见 `apps/studio/tauri/tauri.conf.json:6` 到 `apps/studio/tauri/tauri.conf.json:10`。同一 app 在 build/dev 两种 Tauri 模式下切换 frontend 来源，但 backend sidecar 模型仍在。

Feature 映射补充：Copilot 没有通过 Tauri IPC 获得特别生产能力。它的 frontend chat payload 见 `apps/studio/frontend/src/hooks/useCopilot.ts:143` 到 `apps/studio/frontend/src/hooks/useCopilot.ts:157`，backend request model 见 `apps/studio/backend/app/models/copilot.py:21` 到 `apps/studio/backend/app/models/copilot.py:27`。这属于 Studio backend feature，而非 desktop shell feature。

Feature 映射补充：Workspace file operations 横跨 frontend IPC 和 backend workspace state。Tauri helper 见 `apps/studio/frontend/src/lib/tauri.ts:4` 到 `apps/studio/frontend/src/lib/tauri.ts:79`；backend resource/workspace dirs 见 `apps/studio/backend/app/core/config.py:52` 到 `apps/studio/backend/app/core/config.py:63`。这正是 Studio 作为开发壳的表现。

Boundary 补充：本文不把 dev tunnel 当生产部署。`.env.local` 指向 `/api`，见 `apps/studio/frontend/.env.local:1`；Vite proxy 转本机 backend，见 `apps/studio/frontend/vite.config.ts:47` 到 `apps/studio/frontend/vite.config.ts:68`。它只是让浏览器入口访问本地服务。

Boundary 补充：本文不把 Tauri IPC 当业务 API。业务 skill/run/compile API 在 FastAPI routers，见 `apps/studio/backend/app/routers/skills.py:98` 到 `apps/studio/backend/app/routers/skills.py:118`、`apps/studio/backend/app/routers/runs.py:27` 到 `apps/studio/backend/app/routers/runs.py:55`。IPC 只覆盖 sidecar config 和本地系统动作。

Boundary 补充：本文不写拆分目标，只写当前代码。MVP0 “Engine 降为纯节点合集 + Studio 降为外部唤起壳”属于 scope 对照；当前事实仍是 graph-agent package 嵌入 Studio backend，Tauri bundle 携带 Python/backend/resources，callbacks/schema/state 跨层交织。

Lineage 补充：sidecar health 后才向前端提供 runtime config，见 `apps/studio/tauri/src/sidecar.rs:123` 到 `apps/studio/tauri/src/sidecar.rs:134`。这使桌面入口依赖 backend 可启动性。

Lineage 补充：backend CLI 默认 host/port 在 `apps/studio/backend/app/main.py:160` 到 `apps/studio/backend/app/main.py:164`。Vite 和 Tauri 都围绕这个本地服务形态工作。

Lineage 补充：前端初始化时先 bootstrap tunnel token 再渲染 App，见 `apps/studio/frontend/src/main.tsx:6` 到 `apps/studio/frontend/src/main.tsx:12`。这说明 dev tunnel token 是应用启动链路的一部分。
