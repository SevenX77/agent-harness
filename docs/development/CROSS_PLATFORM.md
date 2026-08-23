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
| 5. CI 真机验证 | `windows-latest` + `macos-latest` 的 cross-platform smoke job（pytest 三包 + 前端 build + tauri crate 的 `cargo test`），**两条腿都是必需检查**：红了挡合并。它建起来时只是观察信号，2026-08-12 提升为必需——理由与提升过程见 `AGENTS.md`「Workflow Pipeline」第 4 条。 | ✅ #280；2026-08-12 提升为必需 |

## 写代码时的具体规则

### Python

- 文本 I/O 一律 `encoding="utf-8"`；这不是风格偏好，Windows 上默认是本地
  代码页（中文机是 GBK/cp936），不写就等着乱码。
- **读别人写的文件用 `encoding="utf-8-sig"`，读我们自己写的文件用 `"utf-8"`。**
  上一条铁律管的是**我们往外写**什么（UTF-8，不带签名，LF），它管不了外面的
  编辑器往我们手里塞什么：Windows 记事本和 PowerShell 重定向默认在文件开头写
  一个 UTF-8 字节序标记（BOM，字节 `EF BB BF`）。那三个字节属于**编码**，不是
  正文的第一个字符；用 `"utf-8"` 读进来，它会变成一个 `\ufeff` 字符卡在最前面。
  实测踩坑（2026-08-21，问题台账 K7）：一个外部编写的 `GRAPH.md` 因此以
  `\ufeff---` 开头，引擎的 frontmatter 匹配是行首锚定的 `^---`，于是整份
  frontmatter 判定为不存在——Studio 画出一个零相位的空技能，**没有任何报错**。
  所以**每个模块给"人手写、我们读回"的文件留一个解码出口，全模块只此一个**，
  三个模块各自命名同一条规则：

  | 模块 | 解码出口 | 管辖范围 |
  | --- | --- | --- |
  | engine | `graph_agent.core.authored_text.read_authored_text` | 技能 markdown、validator 源码、声明的运行时输入文件 |
  | studio backend | `app.core.authored_text.read_authored_text` | skill 工作区里的一切：相位 markdown、golden case、test input、`.workspace/` 配置 |
  | Rust native-fs | `native_fs.rs::read_workspace_text` | 前端拿到的一切工作区文本（它是前端唯一的文件读取方） |

  三处都只是给标准库的 `utf-8-sig` 起了个模块内的名字（Rust 侧手写等价逻辑，
  因为 `read_to_string` 不剥签名）——**规则只有一条，出口按模块各有一个**。
  我们自己写出的文件（缓存、trace、metrics、`%APPDATA%` 下的设置与索引）没有
  签名可剥，继续用 `"utf-8"` 读；这个区别本身就说明了这份文件是谁写的。

  **Rust 与 Python 必须一起剥，不能只剥一边**：`workspace_text_hash`
  （LF 归一化后的 sha256）是乐观锁的判据，Rust 读一份、Python 读同一份，
  只要有一边把签名算进哈希，同一个文件的两个哈希就对不上——带签名的文件
  从此**永远保存不了**，而且报的是一个根本没发生过的冲突。
  **不要在踩到的地方逐个 `.lstrip("\ufeff")`**：那是调用点补丁，得在每一个
  读取方记得做一遍——K7 就是这么来的（引擎侧 `graph_assembler` 补了、`parser`
  没补，后端侧 `runtime_config` 相隔十二行给出两种答案），同一个文件于是有了
  两种读法；而且它剥的是一**串**标记而不是签名那一个，正文里合法出现的零宽
  不换行空格会被它吃掉。
- `subprocess.run(..., text=True)` 必须加 `encoding="utf-8", errors="replace"`。
  全仓范本：`apps/studio/backend/app/services/git_local.py` 的 `_run_git`。
- 子进程是 Python 时，父进程环境里的 `PYTHONUTF8=1` 会让子进程也用 UTF-8 写
  stdout/stderr——两端编码才对得上。不要单边指定。
- 平台分支用 `os.name == "nt"` / `sys.platform`，且必须显式、集中、带注释；
  `signal.SIGKILL`、`os.killpg` 等 Unix-only API 只允许出现在明确标注
  跳过 Windows 的代码里。
- **平台分支的两条实现必须给出同一个语义，不只是同一个签名。** 名字一样、
  参数一样、返回类型一样，仍可能一边"永远等下去"另一边"等一会儿就报错"——
  调用方按前者写，就只在另一个平台上炸。实测踩坑（2026-08-12）：跨进程文件锁
  `runtime_state_store_local.py` 的 POSIX 分支是 `fcntl.flock(LOCK_EX)`（等到
  属于你为止），Windows 分支是 `msvcrt.locking(LK_LOCK)`——**它重试十次、每次
  隔一秒，然后抛 `OSError [Errno 36]`（Windows 11 实测 9.1 秒放弃）**。持有方
  写得慢一点，Windows 上等待方的正常等待就成了一个裸 OSError，穿透了调用方
  依赖的类型化异常契约。改法是用不重试的原语（`LK_NBLCK`：占用时立刻抛
  `PermissionError`）自己轮询，把"等多久"握在自己手里。
  **写平台分支时，先把语义写成一句话，再确认两边都满足它**；差异只允许存在于
  怎么实现，不允许存在于承诺了什么。这类差异测试要**跨过对方的内部上限**
  才测得出来（那条测试持锁 12 秒，就是因为上限在 9 秒左右）。

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
