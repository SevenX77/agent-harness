# Phase T2 Python Sidecar 集成 — Research (Round 1)

## 主题 1: Astral python-build-standalone artifact 选择策略

### 1. 现状调研
目前 Skill Studio 依赖系统 Python 环境运行，这在分发给最终用户时会导致极大的不确定性。业界主流方案（如 Cursor, Cursor IDE 早期）通常打包预编译的 Python 环境。Astral `python-build-standalone` 提供了 `cpython-{ver}+{tag}-{triple}-{variant}.tar.gz` 格式的包。我们需要决定下载哪个变体以及如何管理版本。

### 2. 候选对比
*   **Variant 对比**:
    *   `install_only`: 完整包含 debug symbol 和额外库（如 tcl/tk），体积较大（Linux x86_64 约 43MB）。
    *   `install_only_stripped`: 移除了 debug symbol，体积显著减小（Linux x86_64 约 29MB），但不影响常规业务运行。
*   **Version Pinning 对比**:
    *   *Float (Latest)*: 始终抓取最新的 `+<tag>`。优点是能及时获取安全更新，缺点是破坏了构建的确定性，容易引入环境漂移 bug。
    *   *Pinned (Fixed Hash)*: 在 `lock` 文件中写死 `<tag>` 和对应的 `SHA256`。优点是绝对确定，缺点是更新麻烦。

### 3. 推荐 + 理由
*   **Variant 推荐**: 使用 `install_only_stripped`。
    *   *理由*: Tauri 桌面应用对最终打包体积高度敏感。29MB vs 43MB 是显著差异。我们不需要在最终用户的机器上用 gdb 调试 CPython。对于 Windows，对应的后缀通常是 `install_only`（有时没有 stripped 版），需动态 fallback。
*   **Version 推荐**: 使用 Pinned (Fixed Hash)。
    *   *理由*: 基础设施的稳定性高于一切。任何编译器或运行时的升级都必须是显式的，带测试覆盖的 PR，严禁隐式漂移。
*   **Target Triple 映射**:
    *   macOS (Intel): `x86_64-apple-darwin`
    *   macOS (Apple Silicon): `aarch64-apple-darwin`
    *   Linux (x86_64): `x86_64-unknown-linux-gnu`
    *   Linux (ARM64): `aarch64-unknown-linux-gnu`
    *   Windows (x64): `x86_64-pc-windows-msvc`

### 4. 未知 + 风险
*   Astral 每个平台的 artifact 后缀可能不完全一致（例如 Windows 可能只有 `install_only`）。需要在下载脚本中硬编码这些特例。

---

## 主题 2: Tauri Sidecar 启动机制选型

### 1. 现状调研
在 Tauri 中运行外部程序主要有两种方式：一是使用 Tauri 官方的 Sidecar 机制（配置 `externalBin`，使用 `Command::new_sidecar`），二是将其作为普通资源打包，然后使用标准的 Rust `std::process::Command` 通过绝对路径启动。

### 2. 候选对比
*   **Tauri Sidecar (`externalBin`)**:
    *   *优*: Tauri 自动处理跨平台打包（通过 `-<triple>` 后缀识别）、集成 Capability 安全沙箱、自动清理子进程（一定程度上）。
    *   *缺*: 强制要求目标是一个“单文件二进制”（如 PyInstaller 产物）。对于 `python-build-standalone` 这样一个包含整个目录结构（bin, lib 等）的分发包，极难适配。
*   **`std::process::Command` + Tauri Resource**:
    *   *优*: 可以自由启动目录结构下的任意执行档（`app.resource_dir()/vendor/python/bin/python`）。完全控制生命周期、管道和环境变量。
    *   *缺*: 失去 Tauri 的自动安全限制；必须手动在打包脚本中将整个 Python 目录作为 resource 拷入；需要在 Rust 代码中根据 OS 动态拼接路径。

### 3. 推荐 + 理由
*   **推荐**: 使用 `std::process::Command` + Tauri Resource。
    *   *理由*: 我们分发的是一个完整的 Python 目录（包含 uvicorn 和 fastapi 等依赖），而不是单一的 executable。强行将整个环境塞入 Sidecar 机制会导致路径解析灾难。通过 Tauri 的资源路径解析找到 Python 解释器，并使用 `std::process::Command` (或 `tauri_plugin_shell`) 启动是唯一可靠的路径。

### 4. 未知 + 风险
*   安全审核（如 macOS Notarization）可能对 resource 目录下可执行文件的签名有更严格的要求，特别是当我们不是用 Tauri 官方 Sidecar 机制包装它时。

---

## 主题 3: 跨平台进程优雅关闭

### 1. 现状调研
僵尸进程是桌面端体验的大敌。如果在关闭应用时，跑在后台的 FastAPI 进程（Uvicorn）没有被结束，就会占用端口，导致下一次启动失败。

### 2. 候选对比
*   **Unix (`SIGTERM` -> `SIGKILL`)**: Rust 发送 `SIGTERM` 给 Python。Uvicorn 捕获信号并触发 shutdown lifespan 钩子，清理连接后退出。如果超时（如 3s 未退），再发送 `SIGKILL` 强杀。
*   **Windows (`TerminateProcess`)**: Rust 的 `child.kill()` 在 Windows 默认调用 `TerminateProcess`，这相当于 `SIGKILL`，会导致 Uvicorn 直接猝死，无法触发清理逻辑。
*   **Process Group/Job Object**:
    *   如果 Python 脚本自己又拉起了别的子进程，杀 Python 进程可能只杀了一层。在 Unix 需使用 Process Group (PGID)，在 Windows 需使用 Job Objects，以确保整颗进程树都被杀死。

### 3. 推荐 + 理由
*   **推荐**:
    1.  **事件拦截**: 在 Tauri `RunEvent::ExitRequested` 拦截退出流程。
    2.  **生命周期钩子**: 优先通过内建的 HTTP API（如发一个 `POST /shutdown` 探针到 FastAPI）触发应用的“优雅关闭”。
    3.  **进程树强杀 (Fallback)**: 如果超时或心跳检测失败，Unix 环境使用 `command-group` crate 发送信号给 PGID；Windows 使用 `winapi` 的 Job Objects (或依赖 `tauri-plugin-shell` 底层的树杀逻辑) 进行兜底。

### 4. 未知 + 风险
*   Tauri Rust 进程本身如果 Panic 或者被系统强制 OOM Kill，`ExitRequested` 钩子不会执行，可能导致 Orphaned Sidecar。需要 Python 端实现“心跳保活”（定期轮询父进程 PID），如果发现父进程死了就自杀。

---

## 主题 4: 动态端口分配与传递

### 1. 现状调研
为防止 `8787` 默认端口冲突，我们需要让 FastAPI 在系统分配的随机端口上运行。难点在于避免 Rust 找到端口并传给 Python 的窗口期发生 Race Condition。

### 2. 候选对比
*   **方案 A: 端口预选 (Best Effort)**
    *   Rust 绑定 `127.0.0.1:0` 获取系统端口，立即 close socket，然后通过 `--port <port>` 启动 Python。
    *   *缺点*: 存在极小的 TOCTOU 窗口期被别的程序抢占。
*   **方案 B: 子进程自选 (Child-First Binding)**
    *   Python 使用 `port=0` 启动，由 Uvicorn 绑定端口后，打印到 stdout (如 `PORT=54321`)。
    *   Rust 读取子进程 stdout 获取端口。
    *   *缺点*: 需要修改现有的后端启动脚本来打印此信息，增加启动耗时（Rust 必须等读取到流再向前端暴露配置）。
*   **方案 C: 文件描述符传递 (FD Passing)**
    *   Rust 绑定 socket，并将 fd 通过环境变量传给 Python，Python 接管绑定。
    *   *缺点*: 仅限 Unix 系统，Windows 支持困难，破坏跨平台代码统一性。

### 3. 推荐 + 理由
*   **推荐**: 方案 A 端口预选 (Best Effort)。
    *   *理由*: 尽管存在理论上的 TOCTOU 竞争，但在单机环境下的成功率接近 100%。它实现最简单，能跨平台，无需修改后端 Uvicorn 默认架构。为了兜底，如果启动失败，可以在 Rust 侧加入重试逻辑（换个端口再试）。
*   **端口传递前端**: 在 Tauri 启动前将其存入 managed State，前端通过 `invoke('get_sidecar_config')` 获取，动态设置 `axios.defaults.baseURL`。

### 4. 未知 + 风险
*   开发环境下（`cargo tauri dev`），每次热更可能拉起新的后端实例。需要确保旧的监听器及时释放。

---

## 主题 5: Backend 依赖的 vendor 化方案

### 1. 现状调研
目前 Skill Studio 的后端是 Python 原生项目，依赖写在 `pyproject.toml` 中。在打包为 Tauri 应用时，目标机器没有网络或 `pip` 环境，所有依赖必须前置打包。

### 2. 候选对比
*   **方案 A: Virtualenv (venv)**
    *   在构建阶段，于 `apps/studio/tauri/vendor/` 目录下创建一个 venv，并执行 `pip install`。将整个 venv 打包。
    *   *优*: 是最标准的 Python 依赖隔离方法。
    *   *缺*: Venv 中的 `bin` 脚本会硬编码绝对路径（shebang），跨机器拷贝会失效（尽管我们只执行主模块可能不受影响）。
*   **方案 B: `--target` 安装**
    *   执行 `pip install -r requirements.txt --target apps/studio/tauri/vendor/site-packages`。
    *   通过设置环境变量 `PYTHONPATH=vendor/site-packages` 运行 Python。
    *   *优*: 没有硬编码路径问题，纯净的依赖存放地。
    *   *缺*: 如果遇到带 native C 扩展的包（预编译 wheels），在不同操作系统构建机上拉取的包不能通用。

### 3. 推荐 + 理由
*   **推荐**: 方案 B (`pip install --target`) 配合构建矩阵。
    *   *理由*: Tauri 打包本来就是在 GitHub Actions 对应操作系统的 Runner 上运行的。在 mac Runner 上跑 pip 就会拉取 mac wheels，随后打包成 `.dmg`。因此，Native Binary 跨平台问题由“专机专建”解决。使用 `PYTHONPATH` 隔离，避免引入 venv 导致的绝对路径污染，最适合可移植的绿色软件。

### 4. 未知 + 风险
*   部分依赖（如特定的机器学习小库或图形库如果引入）可能不支持所选目标平台的预编译 wheel（特别是 aarch64 Linux），这会导致构建回退到源码编译，拖慢 CI 或失败。

---

## 主题 6: Resource 路径解析 (dev vs packaged)

### 1. 现状调研
Tauri 应用中有开发和生产打包两种形态。对于后端需要访问的数据目录（如 `skills/`），在源码下是相对路径，而在打包后（如 macOS的 `.app/Contents/Resources/`）结构完全改变。

### 2. 候选对比
*   **由 Python 猜测**: Python 启动时检查当前工作目录，判断是否在 `.app` 或 AppImage 内，自己修正路径。
    *   *缺*: 容易出错，耦合了打包方式，不够优雅。
*   **由 Rust 注入路径环境变量**:
    *   Rust 侧利用 Tauri 的 `app_handle.path_resolver().resource_dir()` API 拿到运行时的确切基地址。
    *   将该地址设为环境变量（如 `STUDIO_RESOURCE_DIR=/path/to/app`），Python 后端启动时优先读取该变量。

### 3. 推荐 + 理由
*   **推荐**: 由 Rust 注入路径环境变量。
    *   *理由*: Tauri 框架才是唯一权威知道打包后资源存放在哪里的实体。Rust 负责解析，Python 仅需消费环境变量，做到了职责分离。不管是 `cargo tauri dev` 还是 `cargo tauri build`，Tauri 的 Path Resolver 都会自动返回正确地址。

### 4. 未知 + 风险
*   某些操作系统可能对打包内资源的访问设置了严格权限（只读）。如果我们需要在资源目录下写入（例如写入 `SKILL.md` 或者缓存），需要确保路径指向系统的 User Data 目录（如 `app_data_dir()`）而不是资源目录。

## 总结

### 跨主题关键 Trade-off
*   **体积控制 (主题1) vs Native 依赖构建复杂度 (主题5)**：选择 `install_only_stripped` (主题1) 有效控制了基础体积，但这意味着遇到带有 Native C/Rust 扩展依赖时 (如特定加解密或机器学习库)，不能依赖分发版内置的工具链现场编译。因此，必须在主题5中采用 `pip install --target` 配合矩阵打包机 (Runner) 提前下发平台专属 Wheel。
*   **启动封装机制 (主题2) vs 动态端口探测 (主题4)**：放弃官方 Sidecar 采用 `std::process::Command` (主题2) 极大简化了 portable 目录打包，但也失去了 Tauri 对于单文件子进程的精细管控；因此，主题4的“Best Effort”端口分配必须更加健壮，并需要搭配严谨的重试逻辑以弥补底层进程管理透明度的缺失。

### Research-driven Outline 修订建议 (针对 design.md)
1.  **细化 Tauri API 与环境透传策略**：在设计文档的“Resource Path”和“端口分配”章节，明确必须利用 Rust 的 `path_resolver().resource_dir()` 作为唯一基准点，并且通过环境变量向 Python 解释器注入这些基准地址和探测到的 `--port`，而非依赖 Python 端自身盲猜。
2.  **确立优雅关闭的三层防线**：在“生命周期管理”部分，设计必须明确划分为：① `RunEvent::ExitRequested` 拦截 -> ② 优先通过 HTTP `/shutdown` 通知 -> ③ 后备使用 `command-group` / Windows Job Objects 进程树强杀。
3.  **明确 Python Artifact 锁定机制**：在“分发与校验”设计章节中，加入具体的 `lock` 文件数据结构草案（包含 tag，platform triple 和 SHA256），并强制规定在下载环节 Fail Closed（校验失败即报错阻断）。
