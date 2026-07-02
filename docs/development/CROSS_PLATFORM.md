# 跨平台兼容规范（Windows / macOS / Linux）

本项目在三个平台上开发、编译、运行。本文是三平台兼容的**唯一规范文档**：
写文件、起子进程、加脚本、动 CI 之前先读这一页。

## 铁律

**仓库内部一切文本交换统一 UTF-8 + LF，与操作系统 locale 彻底解耦。**
平台差异只允许出现在显式声明的边界层（例：Rust 侧 `cfg!(windows)` 选
`python.exe`、pywin32 路径注入），并且必须能回答"为什么这里必须分平台"。

任何"跟着系统走"的隐式行为（默认编码、默认行尾、大小写不敏感文件名）都是
bug 的温床：同一份代码在中文 Windows、英文 macOS、Linux CI 上会表现不同。

## 分层设计（谁来保证）

| 层 | 机制 | 状态 |
| --- | --- | --- |
| 1. git 地基 | `.gitattributes`（`* text=auto eol=lf`，`.ps1/.bat/.cmd` 例外 CRLF，二进制显式标注）+ `.editorconfig`（charset=utf-8）。本地 `core.autocrlf` 是什么都不再影响仓库。 | ✅ 已落地（本文所在 PR） |
| 2. 代码显式声明 | 所有 `open()` / `Path.read_text()` / `Path.write_text()` / `subprocess(text=True)` 必须显式 `encoding="utf-8"`；读子进程输出加 `errors="replace"`。 | ✅ #280 |
| 3. 运行时兜底 | 所有进程入口设 `PYTHONUTF8=1`（Python UTF-8 模式，3.15 起为官方默认）：根 `conftest.py`、CI env、`studio-dev.ps1` / `wt-*.sh`、Tauri sidecar spawn（`sidecar.rs`）。第 2 层若有遗漏，行为仍统一。 | ✅ #280 |
| 4. 闸门防复发 | ruff 启用 `PLW1514`（unspecified-encoding），未指定编码的文本 I/O 直接 CI 红。 | ✅ #280（`PLW1514` 走 explicit-preview-rules，稳定规则行为不变） |
| 5. CI 真机验证 | `windows-latest` + `macos-latest` 的 cross-platform smoke job（pytest 三包 + 前端 build），**非必需检查**，只做观察信号。 | ✅ 本 PR |

## 写代码时的具体规则

### Python

- 文本 I/O 一律 `encoding="utf-8"`；这不是风格偏好，Windows 上默认是本地
  代码页（中文机是 GBK/cp936），不写就等着乱码。
- `subprocess.run(..., text=True)` 必须加 `encoding="utf-8", errors="replace"`。
  全仓范本：`apps/studio/backend/app/services/git_local.py` 的 `_run_git`。
- 子进程是 Python 时，父进程环境里的 `PYTHONUTF8=1` 会让子进程也用 UTF-8 写
  stdout/stderr——两端编码才对得上。不要单边指定。
- 平台分支用 `os.name == "nt"` / `sys.platform`，且必须显式、集中、带注释；
  `signal.SIGKILL`、`os.killpg` 等 Unix-only API 只允许出现在明确标注
  跳过 Windows 的代码里。

### 路径与文件名

- 用 `pathlib`，不手拼分隔符（安全校验里显式拒绝 `"\\"` 属于合理例外）。
- **禁止新增仅大小写不同的路径。** Windows/macOS 文件系统不区分大小写，
  两个只差大小写的目录在磁盘上会合并成一个，git 索引却认为是两个——本仓
  曾真实踩坑（`docs/PR-reports/` 与 `docs/pr-reports/` 并存，已在本 PR 统一
  为小写）。新目录一律小写-连字符。

### 脚本

- 开发工作流脚本以 bash 为准（Windows 走 Git Bash），行尾由
  `.gitattributes` 钉死 LF——CRLF 的 bash 脚本会直接报错。
- Windows 专用入口用 `.ps1`（如 `studio-dev.ps1`），检出为 CRLF。
- Git Bash 下给原生 Windows 程序传"像 POSIX 路径"的环境变量会被改写，
  用 `MSYS2_ENV_CONV_EXCL` 排除（范本：`scripts/wt-dev.sh`）。

### Rust（Tauri 壳）

- 读外部进程输出用 `from_utf8_lossy`（容错），已是现状；配合第 3 层
  sidecar 的 `PYTHONUTF8=1`，中文日志不再被替换成乱码符。
- 平台差异集中在 `cfg!(windows)` / target triple 分支（`sidecar.rs`），
  新增平台分支照此模式。

## 豁免

确需按系统本地编码交互的场景（目前全仓为零），必须：内联注释说明原因 +
`# noqa: PLW1514`（PR-B 落地后）。没有注释的豁免按 bug 处理。

## 三平台支持矩阵（现状）

| 环节 | Windows | macOS | Linux |
| --- | --- | --- | --- |
| 开发（worktree 工作流） | ✅ Git Bash | ✅ | ✅ |
| CI 必需检查 | —（ubuntu 上跑） | — | ✅ |
| CI smoke（非必需） | ✅ | ✅ | ✅ |
| Studio 启动器 | ✅ `studio-dev.ps1` | ⚠️ `studio-dev.sh` 已就位（与 .ps1 同为 `dev_studio.js` 的薄壳，runtime 下载本就分 triple；真机启动验证待 macOS 硬件） | ✅ `studio-dev.sh`（2026-07-02 于 Ubuntu 22.04.5 x86_64 真机验证：Xvfb 无头启动，窗口无红 banner、Vite 5173/​sidecar 8787 双 200、技能画布可用、sidecar 环境含 `PYTHONUTF8=1` 且中文经 sidecar 往返无乱码、关窗无孤儿 uvicorn） |
