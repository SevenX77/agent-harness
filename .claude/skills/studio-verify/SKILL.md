---
name: studio-verify
description: Studio 桌面 app 真机验证唯一方法:CDP(9222)驱动真 Tauri 窗口做逐项点验+截图。禁止用浏览器直开 Vite 的 web 模式充当验证。含启停 launcher 与 cdp/click/shot/emulate/console 五件套脚本。
---

# Studio 真机验证(CDP 驱动真窗口)

## 铁律:验证 = 真窗口,web 模式的结论一律不算数

**禁止**用 Playwright / 无头浏览器 / 手开浏览器访问 Vite(5173 或 worktree 517x)来做
验证(2026-08-14 用户裁决)。原因不是偏好,是 web 模式下被验对象根本不完整:

- Tauri 原生桥是假的:`invoke`、Rust native-fs(skill 文件唯一写入方)、原生对话框
  (`select_file`/`select_directory`)全部不可达或行为不同;
- Recent workspaces 存在 Rust native store(`recent_workspaces.json`),web 会话恒空,
  连"打开一个 skill"都要另找旁门;
- 鉴权要从 sidecar 进程环境里扒 token,本身就是绕路信号。

web 模式**唯一**允许的用途:自己开发途中肉眼扫一眼样式;它产出的任何结论都不得写进
验证报告。逐项点验(每条改动:操作 + 预期 + 实测 + 截图)只能在真窗口做。

## 流程位置(与功能 SOP 的关系)

1. **worktree 阶段**:本地 CI 门禁 + 单测(vitest/pytest)是这一阶段的验证物,不做真机点验。
2. **合并后**:主仓 `git pull` →(改了 engine/gateway 源码则重建 vendor,配方见
   `AGENTS.md` Workflow Pipeline 第 7 条)→ 用本 skill 的 CDP launcher 重启 app →
   逐项点验 + 截图 → 五列验证报告(格式见 `apps/studio/frontend/CLAUDE.md` Phase 7)。

## 9222 生命周期(占黑板 → 启动 → 验证 → 必须关闭 → 释放)

WebView2 只对**由设置了环境变量的进程启动的**实例生效,所以开/关调试口都要重启 app。
重启 Studio 桌面 app 已获用户长期授权,不必每次问。

**9222 是全局独占资源,动它之前先在运行时资源黑板上占位。** 一台机器只有一个带调试口
的窗口、一个 9222;两个 agent 同时驱动它,双方的 `Runtime.evaluate` 和
`Input.dispatchMouseEvent` 打进的是同一个页面——点击落在别人正在验的界面上,采样读到
别人刚改的状态,两边的结论同时失真而且都察觉不到。并行 worktree 是常态(见 `AGENTS.md`
「并行任务的运行时资源黑板」),所以这一步不是可选的礼貌。

**它也不再只是约定:会驱动窗口的工具自己会查。** `click.mjs`、`emulate.mjs` 和两个
launcher 在动手前都问一次 `wt-board.sh holds cdp-9222`,答不出"这块板是我的"就退出 4,
一个字都不点。查不动黑板(缺 bash、板没了)同样算答不出——**失败一律关向安全侧**,因为
"问不出来"不是往别人窗口里打字的许可。2026-08-15 两个 agent 在同一个窗口上互相打了几个
小时的点击,当时黑板已经合并、文档也写着要占位:只靠文档约束的纪律,实证不成立。

**读永远不需要占位**:`cdp.mjs` / `shot.mjs` / `console.mjs` 是观察工具,不设卡。
这条线是故意画的——你必须能先看一眼才知道别人是不是正在用,占位前无法观察等于逼人盲抢。

```bash
# -1) 报上身份并占住 9222。身份是本会话的稳定 id:黑板要靠它区分同一棵树里的两个 agent
#     (仓根就是最常见的那棵树,worktree 路径分不开我们)。没有它,holds 一律答"证明不了"。
export WT_BOARD_AGENT=<本会话 id>
# 已被占用时退出码非 0 并打印当前持有者与剩余时间——等对方验完,不要抢。
scripts/wt-board.sh claim cdp-9222 --ttl 3600 --note "点验 PR #NNN"
# 点验超过 1 小时就续期,别让占用先过期被别人接管:
#   scripts/wt-board.sh renew cdp-9222 --ttl 3600

# 0) 认路:现在谁占着 8787(认 PID 父链,不要按进程名过滤——会静默空结果)
powershell -Command "Get-NetTCPConnection -LocalPort 8787 -State Listen | Select-Object -ExpandProperty OwningProcess -Unique"

# 1) 关旧实例(杀 8787 属主的进程树;Windows 锁 vendor 的 .pyd 也靠这步释放)
# 2) 分离启动带 9222 的 app(必须 Start-Process 分离——后台任务壳回收会连带杀掉控制台子进程)
powershell -Command "Start-Process powershell -ArgumentList '-ExecutionPolicy','Bypass','-File','<本目录>/scripts/launch-studio-cdp.ps1' -WindowStyle Hidden"

# 3) 等口子就绪(app 冷启 1-3 分钟,日志在 %TEMP%\studio-dev-cdp.log,注意是 UTF-16-LE)
until curl -s -o /dev/null http://127.0.0.1:9222/json/version; do sleep 5; done

# 4) …… 用下面的五件套做点验 ……

# 5) 验完必关:关 app → 用 launch-studio-clean.ps1 重启无调试口的实例 → 验证真关了
curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:9222/json/version --max-time 3   # 必须 000

# 6) 关干净之后再还黑板——顺序不能反,否则下一个 agent 会对着还开着的旧窗口开工
scripts/wt-board.sh release cdp-9222
```

「我重启了」不等于「它关了」——第 5 步那条 curl 是验证的一部分,9222 开着等于本机任意
进程都能完全控制 app。第 6 步同理:占位没还等于别人只能干等。

## 五件套脚本(`scripts/`,一律用绝对路径调用——cwd 会在后台任务边界漂回仓根)

| 脚本 | 用法 | 干什么 |
|---|---|---|
| `cdp.mjs` | `node cdp.mjs "<js 表达式>"` | 在真页面里跑任意 JS(读 DOM/状态、毫秒级采样瞬态);`awaitPromise` 已开,可传 async IIFE |
| `click.mjs` | `node click.mjs "<element 表达式>" [dblclick]` | CDP Input 域真鼠标点击。合成 `.click()` 对 Radix/pointerdown 组件和 ReactFlow 节点**无效**,必须用它 |
| `shot.mjs` | `node shot.mjs out.png` | 截真窗口页面(窗口最小化也能截) |
| `emulate.mjs` | `node emulate.mjs 1400 1200` / `clear` | 视口仿真。**坑**:`clear` 并不还原,验完要显式 set 回真实尺寸(如 1400 900);点击坐标超出真实窗口高度不落地 |
| `console.mjs` | `node console.mjs "<js 表达式>" [等待 ms]` | 执行表达式并收 4s(可调)内 console/异常——点了没反应时用它抓静默失败 |

`click.mjs` / `emulate.mjs` 会先过 `lease-guard.mjs`(两个 launcher 过 `assert-claim.ps1`),
没占位就退出 4 并告诉你怎么占。**改这两个守卫之后要真跑一遍**:无占位必须被拒、占位后
必须放行、换个 `WT_BOARD_AGENT` 必须再次被拒——恒真的判断在纯文本断言下能活很久。
跑的时候把 `WT_BOARD_DIR` 指到临时目录,别污染真板;**也别拿活着的 app 当靶子**,
放行那一档是真的会点下去(2026-08-15 我自己就这么误点了一次)。

## 纪律与已知坑

1. **动手前先认路**:`node cdp.mjs "document.body.innerText.slice(0,120)"`。app 会恢复
   上次工作区而不是首页;盲点会点到别人正在跑的东西(实证:误点 Predict 触发过一次
   predict run)。别碰其他 copilot 会话的待审批项。
2. **target 按端口匹配**:`/:5173/`,不匹配主机名(localhost vs 127.0.0.1 不稳定)。
3. **底部 action bar 会遮住画布下缘节点**(Output/Predict/Run 一带):先
   `emulate.mjs 1400 1200` 把节点露出来再点,验完 set 回去。
4. **一次采样,不要轮询截图**:瞬态(loading 相位、流式增量)用 cdp.mjs 里的 async
   循环 100ms 读状态返回时间线,截图轮询追不上。
5. **报告纪律**:没实测的行不许标 ✅;每行附截图文件名;跨多 PR 的会话报告要汇总全部交付项。
   **给用户看的截图/报告必须发布成 claude.ai Artifact 页**(图片压 JPEG 内嵌 data URI,
   同一文件路径复发布保持同一 URL)——用户常在远端看会话,发本地盘文件路径等于没交付
   (用户裁决 2026-08-14:「给我的截图不要用本地盘,看不见」)。
6. 背景原理与非 Windows 场景见 `docs/development/RUN_AND_SCREENSHOT.md` §4;本 skill
   是它在本仓 Windows 主力机上的可执行实例。
