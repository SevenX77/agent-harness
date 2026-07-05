# “Open in Claude Code” 安装 + 启动指南（Studio 侧）

Studio copilot 面板右上角的 **“Open in Claude Code”** 按钮,会把你当前打开的
skill 工作区交给真实的 Claude Code 跑一个交互会话。这份文档讲**怎么装、怎么用、
出问题怎么查**——是 Studio 自己这一套(安装脚本 + 本指南),和 `ah` 自身的职责
分开(边界见文末「谁负责什么」)。

> 一句话:装一次(脚本 + 两步人工确认)→ 以后点按钮就能用。

---

## 0. 它是什么 / 为什么要装这些

点按钮时发生的事:Studio 通过 [`ah`](https://github.com/SevenX77/ah)(agent
hypervisor)在 **WSL2** 里拉起一个真正的 `claude` 交互会话,跑在你打开的那个
skill 工作区里,并把一个终端窗口 attach 上去。所以点按钮之前,机器上得先有:
WSL2 + 一个 Linux 发行版 + systemd + tmux + `claude` CLI + `ah` + 一次订阅登录。

`ah` 自己的安装命令只装 `ah` 一个二进制,**不管** WSL2/tmux/claude/登录这些。
所以这些由 Studio 的安装脚本 `scripts/install-claude-code-wsl.ps1` 统一打包。

---

## 1. 一次性安装

从**仓库根目录**开一个 PowerShell,跑:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\install-claude-code-wsl.ps1
```

脚本**幂等**(随便重跑,已经装好的会跳过),会依次装 WSL2 → 发行版 → systemd +
镜像网络 → 时区/语言/代理(从 Windows 同步)→ tmux → `ah` → `claude` → 处理登录,
最后打印 `ah doctor` 自检。

### 只有两处必须你亲自动手(操作系统安全层面绕不过)

脚本跑到这两处会**打印清楚的下一步、然后干净退出(不是报错)**,你照做完,
**重跑同一条命令**就继续:

1. **装 WSL2 要重启一次电脑。** 首次装 WSL2 功能后 Windows 需要重启;脚本会提示
   你重启,重启后再跑一遍命令。
   - 如果提示需要管理员权限:用「以管理员身份运行」的 PowerShell 再跑一次。
2. **首次登录 Claude 要你在浏览器里过一次 OAuth。** 脚本会在 Windows 上装一份
   `claude` CLI(如果还没有),然后让你:开一个新终端跑 `claude` → 浏览器里用你的
   Claude 订阅登录 → 回来重跑安装脚本,它会把登录凭据复制进 WSL。
   - 用的是你的**订阅登录**,不是 API key。

装完最后看到 `Done. Go back to Studio and click 'Open in Claude Code'.` 就 OK 了。

> `ah doctor` 输出里那条红色 `daemon - ahd daemon is not running` 是**正常的**——
> ahd 是你点按钮那一刻才按需启动的,装机阶段本来就不该起。

---

## 2. 日常使用:点按钮

1. Studio 里打开任意一个 skill(进画布)。
2. 右侧 MoirAI(copilot)面板右上角,点 **“Open in Claude Code”**(终端图标)。
3. 弹出一个终端窗口,先打印 `Starting Claude Code through ah ...`。
4. 约 **15–20 秒**(首次冷启动)后自动 attach,你会看到 Claude Code 交互界面
   (Opus 4.8、当前工作目录路径)。
5. **不用你打字**,Claude 会自己蹦出一段中文状态汇报(我是谁 / 当前是哪个 skill /
   能帮你做什么),然后停下等你。之后就是一个正常的 Claude Code 会话,直接对话即可。

关于这个窗口:
- 底部那条绿色状态栏是 **tmux**——它让 claude 进程独立于窗口存活。关掉窗口,
  claude 不会立刻死;再点一次按钮能重新 attach 回同一个会话。
- 想临时脱离(不关会话):`Ctrl-b` 然后按 `d`。
- 窗口中间大片留白是 Claude Code TUI 自身的渲染方式(输入框钉在底部),不是 bug。

---

## 3. 出问题怎么查

| 现象 | 多半是什么 / 怎么办 |
|---|---|
| 按钮点了没反应 / 灰着 | 按钮在没有工作区时会禁用;先确认进了某个 skill 的画布。 |
| 终端弹出但报 `Could not start WSL` | WSL2 没装好。跑第 1 步的安装脚本。 |
| 终端里 `ah CLI was not found in WSL` | `ah` 没装。跑安装脚本(会装 `ah`)。 |
| 终端一直停在 `Starting...` 不动超过 ~40s | 大概率网络/代理没通。重跑安装脚本(它会把 Windows 代理同步进 WSL);确认 Windows 上代理是开的。 |
| 弹出 “Allow external CLAUDE.md file imports?” 之类的确认框 | 正常情况下已被自动预置跳过(见下)。若仍出现,说明工作区的某个祖先目录有新的 `CLAUDE.md`——点 “Yes” 一次即可,之后不再弹。 |

**为什么通常不弹那些确认框**:launcher 会在拉起 claude 前,往 `~/.claude.json`
预置好这个工作区(以及它每一层含 `CLAUDE.md` 的祖先目录)的三个 onboarding 开关
——主题、文件夹信任、外部 CLAUDE.md 导入批准——所以交互式 claude 不会卡在这些框上。
(实现见 `apps/studio/tauri/src/lib.rs` 的 `CLAUDE_ONBOARDING_PRESEED_PY`。)

---

## 4. 谁负责什么(所有权边界)

安装脚本 `scripts/install-claude-code-wsl.ps1` 刻意分成两部分:

- **PART A — `ah` 的运行环境前置**(WSL2 / 发行版 / systemd / 镜像网络 /
  时区·语言·代理 / tmux)。这些**架构上应该归 `ah` 自己的安装器**,已作为需求提给
  `ah` 仓库(见 [`docs/handoffs/ah-installer-provisioning-and-master-defaults.md`](../handoffs/ah-installer-provisioning-and-master-defaults.md)
  Req 1)。在 `ah` 接管前,脚本作为**临时桥**代劳;一旦 `ah` 自装运行环境,PART A
  整段删掉。
- **PART B — Studio 自己的 Claude Code provider 层**(装 `ah`、装 `claude` CLI、
  订阅登录)。这是 Studio 的**长期职责** —— provider CLI 和用户登录**明确不归 `ah`
  管**。

启动逻辑(点按钮那条链路)在 `apps/studio/tauri/src/lib.rs` 的 `open_claude_code`
命令里:写一个临时 `ah.toml`(master 命令 = `IS_SANDBOX=1 claude
--dangerously-skip-permissions '<汇报提示>'`)+ 一段 WSL bash payload → 通过
`wsl.exe -e bash` 在**同一个会话**里 `ah --config … start --wait` 然后
`exec ah attach master`(attach 顶住发行版,master 才不被 WSL 空闲回收)。

---

## 相关文件

- 安装脚本:`scripts/install-claude-code-wsl.ps1`
- 启动逻辑(Tauri 命令 + WSL payload):`apps/studio/tauri/src/lib.rs`
- 给 `ah` 仓库的需求:`docs/handoffs/ah-installer-provisioning-and-master-defaults.md`
- Tauri 外壳说明里的简版入口:`apps/studio/tauri/README.md` →「Open in Claude Code」
