# Research: Open in Codex/Claude — 二进制来源劫持与 ah 沙盒穿透(2026-07-06)

> 事故:Studio「Open in Codex」拉起的 master 读的不是我们注入的 sandbox 配置。
> 本文是完整证据链(全部实测,含时间戳/文件路径/行号),design.md 基于此定稿。

## §1 现象(用户截图,2026-07-06)

Studio 打开的 "Studio Codex master - text-segmentation" 终端里,codex 表现出三处异常:

| # | 异常 | 正常应为 |
|---|---|---|
| 1 | 底部状态显示 `gpt-5.5 xhigh` | sandbox 内 `$HOME/.codex/config.toml` 只有 Studio 写入的 trust 表,无 model 配置 |
| 2 | 自报 cwd 为 Windows 路径 `D:\coding\skills\...` | WSL 进程应看到 `/mnt/d/...` |
| 3 | 执行 PowerShell 命令(`Get-Location`、`Get-Content -TotalCount 80`) | WSL 内 codex 用 bash |
| 4 | 自报「我是 Codex,GPT-5 驱动的本地编码助手」,无 MoirAI master 身份 | 应读到 `$HOME/.codex/AGENTS.md`(软链自 `.ah/rules/master.md`)并自报编队角色 |

`gpt-5.5 xhigh` 与 **Windows 侧** `C:\Users\test\.codex\config.toml` 实测原文逐字吻合
(`model = "gpt-5.5"` + `model_reasoning_effort = "xhigh"`)。四处异常合并只有一个解释:
**这个 codex 是 Windows 进程,不是 WSL 里的 Linux 进程。**

## §2 根因定位:一根被劫持的软链

WSL 实测(2026-07-06):

```
/root/.local/bin/codex -> /mnt/c/Users/test/AppData/Local/OpenAI/Codex/bin/ea1c60319a1dcb19/codex.exe
file: PE32+ executable (console) x86-64, for MS Windows
```

`codex_master_cmd`(`apps/studio/tauri/src/lib.rs:637`)的二进制解析链:
`command -v codex`(PATH 上无原生 codex,落空)→ 退回
`$STUDIO_AH_HOST_HOME/.local/bin/codex` → 命中上面这根软链 → `exec` 一个 Windows PE。
WSL 的 binfmt interop(实测 enabled)把它交给 Windows 侧执行。

对照组:`/root/.local/bin/claude -> /root/.local/share/claude/versions/2.1.199`
是原生 Linux 二进制(7月2日),claude 链路今天没踩坑**纯属运气**——解析逻辑
(`claude_master_cmd`,lib.rs:622)与 codex 完全同构,同样零来源校验。

## §3 时间线(全部实测时间戳,本机 -0700)

| 时间 | 事件 | 证据 |
|---|---|---|
| 7月5日 02:42 | 环境安装脚本装好**原生 Linux codex 0.142.5 (musl)** | `/root/.codex/packages/standalone/releases/0.142.5-x86_64-unknown-linux-musl/` 完整存在;`current/bin/codex --version` 实测输出 `codex-cli 0.142.5`;布局与官方 install.sh 的 `STANDALONE_ROOT` 结构逐字段吻合 |
| 7月5日 22:46 | 原生 codex 还在 sandbox home 内正常运行 | sandbox `.codex/sessions/`、`history.jsonl`、`version.json`(内含 `last_checked_at: 2026-07-06T05:46Z`)写入时间——Windows 进程写不出这些 WSL 路径 |
| 7月6日 00:14:31 | **WSL 发行版重启**(journal 记录脏关机恢复,应为整机重启) | journald:`WSL version 2.7.10.0` 启动序列 + `system.journal corrupted or uncleanly shut down` |
| 7月6日 00:16:15 | `/root/.local/bin/codex` 被改指 Windows `codex.exe`(启动后 ~100 秒) | 软链 ctime 精确到秒;同目录 claude 链仍是 7月2日,只有 codex 被动 |
| 之后 | 用户 Open in Codex → fallback 命中劫持链 → 穿透 | §1 全部现象 |

## §4 排除法:谁翻的软链

逐一排查,全部实证:

1. **官方 Linux install.sh**(`https://chatgpt.com/codex/install.sh`,全文下载检查):
   `BIN_DIR="${CODEX_INSTALL_DIR:-$HOME/.local/bin}"`,目标只会指向
   `$HOME/.codex/packages/standalone/...`;全文 **0 处** `/mnt/`、`LOCALAPPDATA`、
   WSL、Windows 字样。不可能产出指向 `/mnt/c` 的链。→ 排除
2. **官方 Windows install.ps1**(全文 924 行下载检查):0 处 wsl/distro/`/mnt/`/`ln -s`。→ 排除
3. **我们两个仓**(agent-harness + ccbd-rust 含未提交 WIP):
   `OpenAI/Codex|local/bin/codex|codex\.exe` 全仓 grep,除 lib.rs 的合法引用与
   安装脚本的 Windows 路径检查外零命中,无任何建链代码。→ 排除
4. **本机 agent 会话记录**(完整 transcript grep `ln -sfn.*codex`):零命中。→ 排除
5. **WSL 内部进程**(journald 00:14:31–00:17:30 全量):只有 e2e 残留 ahd 自启,
   无任何进程动 `.local/bin`。→ WSL 内部排除
6. **剩下唯一通路:Windows 侧进程跨 `\\wsl.localhost` 写入**(journald 不可见)。
   实证支持:`codex.exe` 二进制本身含 WSL 相关字符串(grep 命中);同目录带
   `codex-command-runner.exe`、`codex-windows-sandbox-setup.exe` 等环境编排组件;
   翻链发生在 WSL/整机重启后 100 秒——与"Windows Codex 随系统自启后执行 WSL
   集成(把 WSL 里的 codex 入口'修复'为指向自己)"的行为完全吻合。

**结论:上游 Windows Codex CLI 的 WSL 集成行为,与本仓任何 PR 无关**——
`codex_master_cmd` 的解析逻辑自 #395 引入起一字未改(git log -S 实证),
payload 历史上也从未有过装原生 codex 之外的动作。

## §5 为什么 ah 沙盒拦不住(穿透机理)

ah 的沙盒隔离是**环境变量级的协作式隔离**,不是内核级。journald 抓到的 worker
spawn 原文(ahd 日志,7月6日 01:13):

```
systemd-run --user --scope ... -- env
  HOME=/root/.cache/ah/sandboxes/2330f128cb60
  CLAUDE_CONFIG_DIR=/root/.cache/ah/sandboxes/2330f128cb60/.claude
  ... claude --dangerously-skip-permissions
```

即:注入 `HOME` 等环境变量,依赖子进程 (a) 继承它们、(b) 尊重 `$HOME` 语义。
无 mount namespace、无 chroot、无容器。

master 侧同理:master cmd 的 bash 脚本部分**在沙盒里正确跑完了**——auth.json
软链、trust 表、AGENTS.md 链全部落进 sandbox home(sandbox 目录内实测可见)。
穿透发生在最后一步 `exec codex.exe`:

```
bash(Linux, HOME=sandbox ✅) → exec codex.exe
  → binfmt_misc 拦截 PE 头 → /init interop 桥 → Windows 进程
```

跨 interop 边界时协作式隔离的两个前提同时被打碎:

- **环境不继承**:WSL→Windows 只传 `WSLENV` 白名单变量,`HOME`/`CLAUDE_CONFIG_DIR`
  直接蒸发;
- **语义不尊重**:Windows 程序定位用户目录用 `%USERPROFILE%`(Windows 会话给定,
  Linux 侧不可注入),根本不看 `HOME`。

于是 codex.exe 读 `C:\Users\test\.codex\`、用 Windows 凭据、起 PowerShell。
**不是隔离被绕过,而是该进程从未生活在 ah 能管辖的操作系统里。**
且全程无一层报错:Windows codex 凭据有效能正常干活,tmux 里的 bash+interop 桥
活着,ah 状态面板全绿——协作式隔离被单方面退出时是静默的。

## §6 现有防线盘点(缺口清单)

| 防线 | 现状 | 缺口 |
|---|---|---|
| `codex_master_cmd` / `claude_master_cmd`(lib.rs:622/637) | `command -v` + host-home fallback,找到即 exec | **零来源校验**:`/mnt/*` PE 照样 exec,静默穿透 |
| 环境安装脚本 `scripts/install-claude-code-wsl.ps1` B1(L323-329) | `command -v codex` 查不到→官方 install.sh 装原生(7月5日已正确干过一次) | 不校验既有入口的**指向**;劫持后若 shell PATH 含 `~/.local/bin`,`codex --version`(Windows exe)也能应答,会误判 present 跳过修复 |
| 设计矩阵 `docs/studio/mvp1/03_regions/copilot/ah-orchestration-design.md` §4.5 | 管"登录态数据从哪来"(auth 搬运矩阵) | 缺"**二进制从哪来**"维度:隐含假设执行侧是本 OS 原生二进制,从未成文 |
| ah(ccbd-rust)provider 层 | spawn 时注入 env,不看二进制 | exec 前无 ELF 校验(次要防线,主修在 Studio 侧) |
| codex auth 同步(payload `codex_auth_sync` + master cmd auth.json 链) | 正确落进 sandbox | 被劫持时整条链**空转**——Windows codex 用 Windows 凭据,歪打正着"能用",掩盖故障 |

## §7 波及面

- **codex @ Windows+WSL**:当前被劫持,sandbox 配置全失效(本事故)。
- **claude @ Windows+WSL**:同构逻辑,今天未踩仅因 claude 链仍指原生;任何第三方
  改写 `~/.local/bin/claude` 会复现同一穿透。
- **macOS / Linux native**:无 interop 边界,不受此机理影响(但来源校验守卫对
  "指向意外二进制"的一般情形仍有价值,设计中按低成本顺带覆盖)。
- **止血可用资产**:原生 codex 0.142.5 完好在
  `/root/.codex/packages/standalone/current/bin/codex`,翻回软链一条命令即恢复——
  但 Windows Codex 每次自启后可能再次翻链,**光止血不够,必须有守卫**。
