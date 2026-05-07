# Tauri T2 - Python Sidecar 集成任务拆分

> Scope: 只覆盖 Phase T2 (Python Sidecar 集成)。T3 跨平台打包/签名、T4 原生体验、`packages/graph-agent/` SDK 改动不在本 spec 范围。

## 参考输入

- `docs/architecture/TAURI_KICKOFF_PLAN.md` §3 Phase T2 + §4 关键技术决策 + §5 风险
- `docs/architecture/POST_PLAN_C_FINAL_DECISIONS.md` §3 PM 工作流
- `apps/studio/tauri/Cargo.toml`
- `apps/studio/tauri/src/lib.rs`
- `apps/studio/tauri/src/main.rs`
- `apps/studio/tauri/tauri.conf.json`
- `apps/studio/frontend/src/api/client.ts`
- `apps/studio/backend/app/main.py`
- `apps/studio/backend/app/core/config.py`
- Astral `python-build-standalone` release assets: `https://github.com/astral-sh/python-build-standalone/releases`
- `.kiro/specs/tauri-t2/requirements.md` Req 3.1-3.6
- `.kiro/specs/tauri-t2/research.md` 主题 1-6 推荐结论
- `.kiro/specs/tauri-t2/design.md` §1-8 ship 版

## 全局决策约束

- `python-build-standalone` 是 Astral 预编译的 portable Python distribution；T2 只做 download + verify + bundle，不把 Python/Rust/依赖整体编译成统一原生二进制，不采用 PyInstaller/Nuitka 路线。
- 必须支持 macOS x86_64、macOS aarch64、Linux x86_64、Linux aarch64、Windows x86_64；artifact target triple 需要显式映射。
- 端口冲突是 P0：Rust 主进程必须动态找随机可用端口，并通过 `--port` 或等价参数传给 Python/uvicorn；前端不能再依赖固定 `VITE_STUDIO_API_BASE_URL`。
- 僵尸进程是 P0：Tauri 窗口关闭/应用退出时必须终止 Python 子进程；按 design §5 采用 `RunEvent::ExitRequested` 拦截、HTTP `/shutdown`、command-group/Windows Job Objects 强杀三层防线。
- 依赖隔离采用 `pip install --target apps/studio/tauri/vendor/site-packages` + `PYTHONPATH`，不采用 venv，避免可移植分发中的硬编码 shebang。

## Sub-tasks

- [x] T2.1 Python runtime artifact manifest + 下载校验脚本
  - 目标：建立可复现的 Astral portable Python runtime 获取流程，按 OS/arch 下载并校验 `python-build-standalone` artifact。
  - 估时：12h
  - 涉及文件：
    - `apps/studio/tauri/scripts/fetch_python_runtime.py`
    - `apps/studio/tauri/python-runtime.lock.json`
    - `apps/studio/tauri/.gitignore`
    - `apps/studio/tauri/README.md`
  - 关键决策点：
    - 明确选择 portable Python distribution download + bundle；不得描述成应用整体二进制编译。
    - 初始 pin 一个 CPython release tag 与固定 SHA256，采用 design Q1 决议的 Pinned Fixed Hash，不允许 latest 浮动漂移。
    - lock 文件按 design §3 schema 记录 `version`、`tag`、`python_version`、`artifacts.{target_triple}.{filename,sha256,url}`。
    - artifact 命名按 `cpython-{python_version}+{tag}-{target_triple}-install_only_stripped.tar.gz` 优先；Windows `x86_64-pc-windows-msvc` 允许 fallback 到 `install_only.tar.gz`，其他平台 fallback 必须显式记录原因。
    - target triple 映射至少覆盖 `x86_64-apple-darwin`、`aarch64-apple-darwin`、`x86_64-unknown-linux-gnu`、`aarch64-unknown-linux-gnu`、`x86_64-pc-windows-msvc`。
    - sha256 校验使用 GitHub release asset digest 或同 release 的 `SHA256SUMS`，下载后本地重新计算。
  - 验收标准：
    - 在本机运行下载脚本可生成 `apps/studio/tauri/vendor/python/<target>/`，其中包含可执行 Python。
    - `python --version` 输出 lock 文件 pin 的 CPython 版本。
    - sha256 不匹配时脚本 fail closed，不留下半成品 runtime。
    - lock 文件能列出 5 个目标平台的 `filename`、`url`、`sha256`，并包含顶层 `version`、`tag`、`python_version` 字段。
  - 测试要求：
    - 单元：artifact target 映射、URL 生成、sha256 校验函数。
    - 集成：当前 host 平台真实下载一次并执行 `python --version`。
    - e2e：不负责 GUI。
  - 依赖：无。

- [x] T2.2 Backend sidecar 启动入口与依赖安装布局
  - 目标：让 bundled Python 能以 sidecar 方式启动 Studio FastAPI backend，并支持 Rust 注入端口和本地数据目录。
  - 估时：14h
  - 涉及文件：
    - `apps/studio/backend/app/main.py`
    - `apps/studio/backend/app/api/system.py`
    - `apps/studio/backend/app/core/config.py`
    - `apps/studio/backend/pyproject.toml`
    - `apps/studio/tauri/scripts/install_backend_deps.py`
    - `apps/studio/tauri/vendor/backend/`
    - `apps/studio/tauri/README.md`
  - 关键决策点：
    - Python backend 继续是 FastAPI + uvicorn 本地 HTTP sidecar，不改成 Rust IPC/gRPC。
    - 启动命令固定为 `python -m uvicorn app.main:app --host 127.0.0.1 --port <DYNAMIC_PORT>`，端口必须由 Rust 传入，不再只用固定 `STUDIO_PORT = 8787`。
    - Rust 启动 Python 时注入 `STUDIO_RESOURCE_DIR=<resource_dir>` 与 `PYTHONPATH=apps/studio/tauri/vendor/site-packages`。
    - Tauri 桌面端遵循 local-first，同机前后端可传本地路径；不要引入生产 cloud 传输设计。
    - backend 依赖安装采用 design Q3 决议的 `pip install --target`，放弃 venv，不能依赖开发者机器全局 Python。
    - Backend 必须提供 `/shutdown` endpoint，并校验来源 IP 为 `127.0.0.1` 且附带启动时注入的随机 token。
  - 验收标准：
    - 使用 T2.1 runtime 能在 repo 内通过 `python -m uvicorn app.main:app --host 127.0.0.1 --port <dynamic>` 启动。
    - 指定随机端口后 `GET /api/health` 或现有健康/基础 API 返回成功。
    - `POST /shutdown` 仅接受 localhost + token 白名单请求，非法请求 fail closed。
    - `STUDIO_RESOURCE_DIR` 与 `PYTHONPATH` 生效，backend 能从 resource dir 解析 skills/config，并从 vendor/site-packages import 依赖。
    - 未指定端口时 dev fallback 行为清晰，且不会影响 Rust 动态端口路径。
    - backend import 不依赖 `packages/graph-agent/` 改动。
  - 测试要求：
    - 单元：端口参数/env 解析、shutdown token 校验、resource dir 解析。
    - 集成：用 bundled Python + `PYTHONPATH=vendor/site-packages` 启动 backend，访问 health 和 shutdown endpoint。
    - e2e：由 T2.6 覆盖。
  - 依赖：T2.1。

- [x] T2.3 Rust sidecar runtime manager：动态端口、启动、健康检查、生命周期
  - 目标：在 Tauri Rust 主进程中封装 Python sidecar manager，负责找端口、启动 uvicorn、等待 ready、退出清理。
  - 估时：18h
  - 涉及文件：
    - `apps/studio/tauri/src/lib.rs`
    - `apps/studio/tauri/src/python_runtime.rs`
    - `apps/studio/tauri/src/ports.rs`
    - `apps/studio/tauri/src/sidecar.rs`
    - `apps/studio/tauri/src/lifecycle.rs`
    - `apps/studio/tauri/src/heartbeat.rs`
    - `apps/studio/tauri/Cargo.toml`
    - `apps/studio/tauri/tauri.conf.json`
  - 关键决策点：
    - 端口冲突 P0：Rust bind `127.0.0.1:0` 或等价方式拿随机可用端口，再把端口传给 Python；采用 Best Effort + 启动失败重试，重试上限约 3 次，禁止固定 8787。
    - 启动命令优先用 `std::process::Command` 管理 bundled Python interpreter；如改用 Tauri Sidecar，必须证明能定位 portable Python 目录和传动态参数。
    - Rust 保存 child handle 到 Tauri state，ready 前前端不得拿到 API base。
    - 僵尸进程 P0：实现 design §5 三层优雅关闭防线：`RunEvent::ExitRequested` prevent exit，优先 HTTP `POST /shutdown`，2 秒超时后用 command-group/Windows Job Objects 进程树强杀。
    - Python 侧实现心跳保活辅助线程，周期性检查 `os.getppid() == 1` 并自杀，覆盖 Rust panic/OOM 导致的 orphaned sidecar。
    - Rust 捕获 Python stdout/stderr，并保留最近 stderr 行给 T2.6 启动故障屏 IPC 使用。
  - 验收标准：
    - `cargo check` 通过。
    - 连续启动两次 Tauri dev，不因端口冲突失败，且每次端口可不同。
    - Python sidecar 启动失败时窗口/API 给出可诊断错误，不静默白屏。
    - 关闭 Tauri 窗口后 `ps`/Task Manager 看不到残留的 sidecar Python 进程。
    - 人为抢占 Rust 预选端口时，manager 能换端口重试并在重试上限内给出明确错误。
  - 测试要求：
    - 单元：随机端口分配、端口重试上限、命令参数构造、ready timeout、shutdown token header。
    - 集成：spawn 一个测试 HTTP server/假 Python 进程验证 HTTP shutdown、强杀 fallback、stderr capture。
    - e2e：由 T2.6 覆盖真实 Tauri dev 流程。
  - 依赖：T2.1、T2.2。

- [x] T2.4 Frontend runtime API base 注入与 WebSocket 同步
  - 目标：让 React 在 Tauri 桌面环境从 Rust 获取 sidecar API base，并动态更新 HTTP/WebSocket client。
  - 估时：10h
  - 涉及文件：
    - `apps/studio/frontend/src/api/client.ts`
    - `apps/studio/frontend/src/api/runtimeConfig.ts`
    - `apps/studio/frontend/src/main.tsx`
    - `apps/studio/frontend/src/App.tsx`
    - `apps/studio/frontend/src/components/SplashScreen.tsx`
    - `apps/studio/frontend/package.json`
    - `apps/studio/tauri/src/lib.rs`
  - 关键决策点：
    - 前端不能在桌面环境硬编码 `http://localhost:8787/api`，必须通过 design §4 的 `invoke('get_sidecar_config')` Tauri command 获取 Rust 分配的配置。
    - TypeScript 侧定义 design §3 `SidecarConfig` interface，包含 `port`、`baseURL`、`wsURL`、`resourceDir` 四个字段。
    - Web 模式继续保留 `VITE_STUDIO_API_BASE_URL` fallback，避免破坏现有 Vite/e2e 流程。
    - `wsUrl()` 必须和动态 API base 同源更新，不能只修 Axios。
    - sidecar ready 前显示 Splash Screen loading state；配置获取失败或 health timeout 后转 error state，避免请求打到旧 base URL。
  - 验收标准：
    - `npm run build` 通过。
    - Web dev 模式仍可用 env 指定 backend。
    - Tauri dev 模式下 Network 请求命中 Rust 返回的 `baseURL`，形如 `http://127.0.0.1:<dynamic>/api`。
    - WebSocket URL 使用同一个 dynamic host/port，形如 `ws://127.0.0.1:<dynamic>/ws`。
    - Splash Screen 在 sidecar ready 前不初始化 API 请求，失败时展示可诊断 error。
  - 测试要求：
    - 单元：`SidecarConfig` 解析、runtime config fallback、`wsUrl()` 动态 base、Splash loading/error 状态。
    - 集成：mock Tauri `invoke('get_sidecar_config')` 返回配置，验证 Axios baseURL 与 WebSocket URL 同步生效。
    - e2e：由 T2.6 覆盖桌面真实链路。
  - 依赖：T2.3 可先并行接口约定；最终集成依赖 T2.3 command/event。

- [ ] T2.5 Tauri bundle resources 与 dev/build 流程串联
  - 目标：把 portable Python runtime、backend 代码和依赖纳入 Tauri dev/build 可定位的资源布局。
  - 估时：14h
  - 涉及文件：
    - `apps/studio/tauri/tauri.conf.json`
    - `apps/studio/tauri/build.rs`
    - `apps/studio/tauri/Cargo.toml`
    - `apps/studio/tauri/scripts/fetch_python_runtime.py`
    - `apps/studio/tauri/scripts/install_backend_deps.py`
    - `apps/studio/tauri/README.md`
  - 关键决策点：
    - T2 只要求 bundle sidecar runtime 到 app resources；安装包签名、公证、CI matrix 属于 T3。
    - design Q2 决议：`vendor/`、`python_runtime/` 等产物加入 `.gitignore`，不入仓库；CI/build 阶段动态下载 runtime 并 `pip install --target`。
    - `tauri.conf.json` 按 design §3 接入 `beforeBuildCommand`：download runtime + `pip install --target apps/studio/tauri/vendor/site-packages`。
    - `bundle.resources` 至少包含 `vendor/**`、`python_runtime/**`、`skills/**`、`config/**`。
    - resource path 解析由 design §6 Rust `path_resolver().resource_dir()` 自动处理 dev (`cargo tauri dev`) 与 packaged app，不依赖当前工作目录。
    - 跨平台 path/executable 名称必须覆盖 macOS/Linux `python/bin/python*` 与 Windows `python.exe`。
    - 控制 scope creep：不做 Python 标准库裁剪策略以外的大规模体积优化，体积优化记录到 risk/backlog。
  - 验收标准：
    - `cargo tauri dev` 能通过同一 resolver 定位本地 vendor runtime/backend。
    - `cargo tauri build` 至少在当前 host 平台能把 `vendor/**`、`python_runtime/**`、`skills/**`、`config/**` 打进 bundle 或输出明确缺失资源错误。
    - packaged app 通过 `path_resolver().resource_dir()` 找到 Python runtime、vendor site-packages、skills/config，Python 端只消费 Rust 注入的 `STUDIO_RESOURCE_DIR`。
    - README 记录 T2 dev bootstrap 命令：下载 runtime、`pip install --target` 安装 backend deps、启动 Tauri。
    - `.gitignore` 覆盖动态生成的 vendor/runtime 目录，仓库不提交大型依赖产物。
    - 不修改 T3 CI/signing 配置。
  - 测试要求：
    - 单元：resource path resolver。
    - 集成：dev resource lookup + packaged path smoke + bundle resources manifest 检查。
    - e2e：由 T2.6 覆盖当前 host。
  - 依赖：T2.1、T2.2、T2.3。

- [ ] T2.6 端到端验收与 P0 回归测试
  - 目标：建立 T2 完成标准，验证 sidecar 启动、动态端口、API 调通、关闭清理和跨平台 smoke checklist。
  - 估时：12h
  - 涉及文件：
    - `apps/studio/tests-e2e/`
    - `apps/studio/tauri/README.md`
    - `apps/studio/tauri/src/sidecar.rs`
    - `apps/studio/tauri/src/lifecycle.rs`
    - `apps/studio/tauri/scripts/test_zombie_scan.py`
    - `apps/studio/tauri/scripts/test_port_conflict.py`
    - `apps/studio/frontend/src/api/client.ts`
    - `apps/studio/frontend/src/components/SplashScreen.tsx`
    - `.kiro/specs/tauri-t2/tasks.md`
  - 关键决策点：
    - P0 回归必须按 design §7 三件套覆盖强占、僵尸清零、PM workflow smoke；不能只以 `cargo check` 代替。
    - 当前 host 可自动化；macOS x86_64/aarch64、Linux x86_64/aarch64、Windows x86_64 至少需要 smoke checklist，完整 GUI CI matrix 留给 T3。
    - Headless CI 采用 design Q4 决议的 Record-Only 模式；`DISABLE_GUI=1` 时只跑 Rust 单元、pip install 打包验证和脚本化 P0 检查，不拉起 Tauri 窗口。
    - 启动故障屏必须覆盖 `/health` 5 秒 timeout，Frontend Splash Error 通过 IPC 展示 Python stderr 最近 50 行。
    - 使用真实 backend API 做一条 PM 工作流 smoke：打开 Studio、读取/选择 skill、调用 compile 或现有轻量 API。
  - 验收标准：
    - `cargo check`、`npm run build`、backend pytest 相关子集通过。
    - `cargo tauri dev` 启动后 sidecar 端口可验证，前端 API 请求成功。
    - 人工或自动关闭窗口后，`ps`/Task Manager 确认无 Python sidecar 残留。
    - 手动占用 8787 后启动 Tauri 仍成功，证明未依赖固定端口。
    - `/health` 5 秒超时时 UI 不白屏，Splash Error 能显示 Rust 捕获的 Python stderr 最近 50 行。
    - `DISABLE_GUI=1` 的 headless record-only 路径在无 display 环境下能稳定执行并记录未跑 GUI 的原因。
  - 测试要求：
    - 单元：补齐 T2.1-T2.4 的关键函数测试。
    - 集成：真实 sidecar spawn + HTTP health/API + shutdown + stderr capture。
    - e2e：`test_port_conflict.py` 强占测试、`test_zombie_scan.py` 僵尸清零测试、Playwright 或等价 GUI smoke 负责 PM workflow；无 display 环境走 `DISABLE_GUI=1` record-only。
  - 依赖：T2.3、T2.4、T2.5。

## 总估时

80h

## Risk / Blocker Flags

- P0：端口冲突与僵尸进程必须作为 T2.3/T2.6 验收项，不应延后。
- P1：Python runtime + backend deps 体积可能超过原计划 40MB，尤其 Linux `install_only` 非 stripped artifact 可能很大；T2 先确保可运行，深度裁剪可列 backlog。
- P1：Astral release artifact 数量多且命名会随 CPython/release 变化；必须 pin release + lock sha256，避免每次构建隐式漂移。
- P1：macOS Notarization 对 resource 目录内 Python 可执行文件签名要求严格，可能触发 Gatekeeper 拦截；签名/公证深水区留给 T3，但 T2 要记录风险。
- P1：Windows 可能没有 `install_only_stripped` artifact，下载脚本必须对 `x86_64-pc-windows-msvc` fallback 到 `install_only`，并在 lock 文件中固定 hash。
- P2：无桌面/display 的 CI 或 VPS 无法跑 `cargo tauri dev` GUI 验收，需要本地桌面或后续 T3 CI runner 覆盖。

## 建议执行顺序

先做 T2.1，再做 T2.2；T2.3 可在 T2.2 接口确定后启动。T2.4 可与 T2.3 并行做接口约定和 frontend fallback，最终联调依赖 T2.3。T2.5/T2.6 放在最后收敛。
