# Phase T2 Python Sidecar 集成 — Design (Round 2 Expand)

> **Status**: DRAFT - Pending PM Review

## §1 架构总览 (Architecture Overview)

本阶段核心任务是实现 Tauri Rust 主进程对 Python 后端进程（Sidecar）的全生命周期管理，并解决生产环境下的跨平台依赖隔离与资源寻址问题。Rust 作为编排者，不仅要启动和监控 Python 服务，还需将动态分配的网络端口和确定的数据目录安全地传递给前端和后端。

### 系统组件交互图

```mermaid
graph TD
    subgraph OS[OS Environment]
        P[Available TCP Port]
        Dir[Platform Data/Resource Dirs]
    end

    subgraph Tauri[Tauri Rust Main Process]
        A[Lifecycle Manager]
        B[Port Allocator]
        C[Resource Path Resolver]
        D[Tauri IPC / State]
    end

    subgraph Python[Python Sidecar Process]
        E[FastAPI Uvicorn]
        F[Vendor Dependencies]
        G[Health/Shutdown Endpoints]
    end

    subgraph Web[Frontend WebView]
        H[React App]
        I[API Client (Axios/WS)]
    end

    %% Data Flow
    B -->|1. Find Port| P
    C -->|2. Resolve Paths| Dir
    A -->|3. Spawn with --port & ENV| E
    F -.->|4. PYTHONPATH Isolation| E
    A -->|5. Poll /health| G
    A -->|6. Store Config| D
    H -->|7. invoke('get_config')| D
    D -->|8. Return Port & Paths| I
    I -->|9. API Requests| E
    A -->|10. POST /shutdown| G
```

### 核心数据流说明
*   **启动流**: Tauri 启动 → Rust `Port Allocator` 绑定 `127.0.0.1:0` 获取随机端口并释放 → `Resource Path Resolver` 计算基准目录设置环境变量 `STUDIO_RESOURCE_DIR` → `Lifecycle Manager` 使用 `std::process::Command` 带参数拉起 Python → 轮询 `/health` 直至 HTTP 200 → 前端 `invoke` 获取配置开始渲染。
*   **关闭流**: 监听 Tauri `RunEvent::ExitRequested` 挂起退出 → `Lifecycle Manager` 请求 Python `POST /shutdown` → 若 2 秒内未结束，利用 Process Group / Job Objects 执行树状强杀。
*   **阶段边界声明**: 仅覆盖 Phase T2（Sidecar 本地启停管控）。不含基础 Setup、自动跨平台 CI 打包机制 (T3) 及系统托盘/文件关联等系统级体验 (T4)。

---

## §2 组件分解 (Component Breakdown)

*   **Python Runtime Manager**: 负责执行环境预置。根据 Target Triple 下载对应架构的 Astral `python-build-standalone` 包，校验 SHA256，解压到 Tauri 的资源目录中供应用调用。
*   **Backend Sidecar**: 承载核心业务逻辑。作为被动子进程运行，入口为 Uvicorn，加载 `--target` 隔离的 `vendor` 依赖。它必须提供供 Rust 探测和控制的 `/health` 和 `/shutdown` API。
*   **Rust Sidecar Manager**: 核心编排器。包含进程启动（环境变量与命令行组装）、重试机制（针对端口冲突）、日志管道（捕获 Python `stdout`/`stderr`）和优雅关闭逻辑（信号或 HTTP 触发）。
*   **Frontend Runtime Config**: React 端配置中心。在 Splash Screen 阶段通过 Tauri IPC 获取 Rust 传来的 API `baseURL`，并注入到所有的 Axios 实例和 WebSocket 连接中。
*   **Resource Resolver**: 跨平台路径抽象层。封装 Tauri `app_handle.path_resolver().resource_dir()`，生成绝对路径通过环境变量传递，从而消灭后端代码中的任何路径硬编码和运行模式（dev/prod）差异猜测。
*   **E2E Test Harness**: 质量防线。专门负责验证 P0 指标，包含端口争用模拟、异常关闭后的进程残留扫描（利用 ps/tasklist 等 OS 级命令），以及验证“选择 Skill 并编译”的基础业务链路。

---

## §3 数据模型 (Data Models / Config Files)

### `python-runtime.lock.json`
定义跨平台 Python 运行时的强一致性契约。
```json
{
  "version": "1.0",
  "tag": "20260504",
  "python_version": "3.10.20",
  "artifacts": {
    "x86_64-apple-darwin": {
      "filename": "cpython-3.10.20+20260504-x86_64-apple-darwin-install_only_stripped.tar.gz",
      "sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
      "url": "https://github.com/astral-sh/python-build-standalone/..."
    }
  }
}
```

### 配置改动与 Schema
*   **`tauri.conf.json` 改动**:
    ```json
    {
      "build": {
        "beforeBuildCommand": "node scripts/download_runtime.js && pip install -r backend/requirements.txt --target apps/studio/tauri/vendor/site-packages"
      },
      "tauri": {
        "bundle": {
          "resources": ["vendor/**", "python_runtime/**", "skills/**", "config/**"]
        }
      }
    }
    ```
*   **Frontend Runtime Config**:
    ```typescript
    interface SidecarConfig {
      port: number;
      baseURL: string;      // e.g., "http://127.0.0.1:54321/api"
      wsURL: string;        // e.g., "ws://127.0.0.1:54321/ws"
      resourceDir: string;  // e.g., "/Users/xxx/Library/Application Support/..."
    }
    ```

---

## §4 关键 API (Key APIs)

### Rust → Python 进程通信 (单向控制)
不使用复杂的 gRPC。控制面通过标准 OS 机制实现：
*   **CLI Args**: `python -m uvicorn app.main:app --port 54321 --host 127.0.0.1`
*   **Env Vars**: `STUDIO_RESOURCE_DIR=/app/path`, `PYTHONPATH=vendor/site-packages`
*   **Pipes**: Python 的 `stdout` 和 `stderr` 重定向给 Rust，由 Rust 负责格式化和落盘。

### Tauri Command Surface (Rust 暴露给前端)
```rust
#[tauri::command]
fn get_sidecar_config(state: tauri::State<SidecarState>) -> Result<SidecarConfig, String> {
    // Return the port and paths determined at startup
}

#[tauri::command]
fn trigger_shutdown(app_handle: tauri::AppHandle) {
    // Allow frontend to request a clean application exit
    app_handle.exit(0); 
}
```

### Backend 内部 Endpoint (FastAPI)
*   **`GET /health`**: Rust 探针专用。只要服务启动并绑定端口即返回 `200 OK`。
*   **`POST /shutdown`**: 必须验证请求源头（如校验来源 IP 为 127.0.0.1 且附带启动时注入的随机 Token）以防恶意终止。接收后调用 Uvicorn 的优雅关闭钩子。

---

## §5 进程生命周期实现 (Process Lifecycle Implementation)

### 动态端口分配 (Best Effort + 重试)
```rust
fn find_available_port() -> u16 {
    let listener = std::net::TcpListener::bind("127.0.0.1:0").unwrap();
    let port = listener.local_addr().unwrap().port();
    drop(listener); // 存在微小 Race Condition 窗口，需配合下游重试
    port
}
```

### 启动伪代码
```rust
let port = find_available_port();
let mut child = Command::new(&python_bin)
    .env("PYTHONPATH", vendor_dir)
    .env("STUDIO_RESOURCE_DIR", resource_dir)
    .arg("-m").arg("uvicorn")
    .arg("app.main:app")
    .arg("--port").arg(port.to_string())
    .group() // Unix process group 隔离
    .spawn()
    .expect("Failed to spawn sidecar");
// 进入 HTTP 轮询 /health，最大等待 5 秒...
```

### 优雅关闭防线
```rust
tauri::Builder::default()
    .run(|app_handle, event| match event {
        tauri::RunEvent::ExitRequested { api, .. } => {
            api.prevent_exit(); // 1. 阻止立即退出
            tauri::async_runtime::spawn(async move {
                // 2. 发送 HTTP shutdown
                let _ = reqwest::Client::new().post(format!("http://127.0.0.1:{}/shutdown", port)).send().await;
                tokio::time::sleep(Duration::from_secs(2)).await;
                // 3. 进程树强杀兜底
                if child.try_wait().unwrap().is_none() {
                    child.kill().unwrap(); // 依赖 command-group 杀进程树
                }
                app_handle.exit(0);
            });
        }
        _ => {}
    });
```
*   **心跳保活**: Python 侧启动后台线程 `while True: if os.getppid() == 1: os._exit(1); time.sleep(1)`，防止 Rust 主进程意外崩溃（如 Panic/OOM）导致 Sidecar 遗留。

---

## §6 跨平台 + 资源解析 (Cross-Platform & Resource Resolution)

### Target Triple 映射与运行时来源
根据构建环境（`std::env::consts::OS` 和 `ARCH`）动态选用锁定包：
*   macOS (Intel/Apple Silicon): `x86_64-apple-darwin`, `aarch64-apple-darwin`
*   Linux: `x86_64-unknown-linux-gnu`, `aarch64-unknown-linux-gnu`
*   Windows: `x86_64-pc-windows-msvc`

### 资源路径一致性
Tauri 是环境拓扑的唯一真相源。
```rust
// Rust 计算绝对路径
let resolver = app_handle.path_resolver();
let resource_dir = resolver.resource_dir().expect("Not packaged correctly");
let data_dir = resolver.app_data_dir().expect("Missing data dir");

// Python 端仅消费环境变量
import os
from pathlib import Path
BASE_RESOURCE_DIR = Path(os.environ["STUDIO_RESOURCE_DIR"])
SKILLS_DIR = BASE_RESOURCE_DIR / "skills"
```
无论在 `cargo tauri dev`（源码相对路径）还是打包后（macOS 的 `.app/Contents/Resources` 或 Windows MSI 的安装目录），路径逻辑均保持正确。

### Vendor 依赖布局
依赖存放于 `vendor/site-packages/`。不同 OS 构建包含 Native 扩展包（如需要编译 C/Rust 的 Python 库）时，由各个 CI Runner（Mac/Linux/Windows）在执行 `tauri build` 前动态运行 `pip install --target`，确保 Wheel 包符合宿主架构，运行时仅需追加环境变量 `PYTHONPATH` 即可。

---

## §7 验收 + 可观测 (Acceptance & Observability)

### P0 回归测试设计
必须建立自动化（或明确的半自动 Checklist）防线：
1.  **强占测试**: 启动前用 Python 占死 8787 端口，验证 Studio 依然能找到新端口并成功显示 UI。
2.  **僵尸清零测试**: 正常关闭和在终端 `kill -9` Tauri 主进程后，执行系统进程扫描，断言无残留的 Python FastAPI 子进程。
3.  **核心工作流**: 从启动开始，前端无错误连接后端，成功读取本地的 `SKILL.md`，执行预定义的 E2E Compile 流程并验证输出 Schema，确保 IO 通道贯通。

### 诊断 UX 与日志聚合
*   **启动故障屏**: 若 `/health` 轮询 5 秒超时，前端 Splash 状态机转向 `Error` 视图，调用 IPC 从 Rust 获取并渲染最近 50 行的 Python `stderr`，禁止静默失败。
*   **日志归档**: Rust 拦截子进程 `stdout`/`stderr` 后，写入按日滚动的日志文件（存放在 `app_handle.path_resolver().app_log_dir()`），格式包含时间戳和流来源标识 `[SIDE-ERR] 2026-xxx ...`。

### Headless CI 支持
通过环境变量 `DISABLE_GUI=1` 在无显示器的 Linux 构建机上提供降级行为，此模式下仅执行 Rust 的单元测试与 `pip install` 打包流程的验证，不拉起 Tauri 窗口。

---

## §8 实施风险 + Open Issues

*   **Open Q1 (打包体积)**: **决议采用 `install_only_stripped`**。考虑到 Tauri 强调轻量级，优先使用无 debug symbol 的版本可直接削减约 15MB 体积。至于更深度的 Python 标准库裁剪（如剔除 tcl/tk），由于可能影响第三方库隐式调用，延期至 T3+ 阶段专门处理。
*   **Open Q2 (Vendor Git 策略)**: **决议将其加入 `.gitignore`**。我们不在源码库中提交上百兆的 Python 包。依赖在 CI 阶段实时构建或下载，保持代码仓库精简。
*   **Open Q3 (依赖安装策略)**: **决议采用 `--target` (Site-packages) 隔离**。如 Research 结论所述，`venv` 中携带硬编码绝对路径的 `bin` 脚本，在可移植分发时极易失效。纯净的 `--target` 结合 `PYTHONPATH` 是最安全的便携方案。
*   **Open Q4 (Headless CI E2E)**: **决议本阶段降级为 Record-Only 模式**。在缺乏 X11/Wayland 的 CI 机器上强跑 GUI E2E 成本过高且易出 Flaky Test。真实 GUI 交互测试留待 T3 阶段搭建带虚拟 Display 的专用 Runner 处理。

**已知遗留 Risks**:
1.  **Notarization 签名墙**: macOS 对资源目录内的可执行文件（预编译的 Python 二进制档）签名要求严格，可能引发 Gatekeeper 拦截。
2.  **Windows Artifact 特例**: Astral 的 Windows 构建可能不提供 `stripped` 后缀版本，下载脚本必须对特定 Triple 做好 fallback 处理。
