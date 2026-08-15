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

## 9222 生命周期(启动 → 验证 → 必须关闭)

WebView2 只对**由设置了环境变量的进程启动的**实例生效,所以开/关调试口都要重启 app。
重启 Studio 桌面 app 已获用户长期授权,不必每次问。

```bash
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
```

「我重启了」不等于「它关了」——最后那条 curl 是验证的一部分,9222 开着等于本机任意
进程都能完全控制 app。

## 五件套脚本(`scripts/`,一律用绝对路径调用——cwd 会在后台任务边界漂回仓根)

| 脚本 | 用法 | 干什么 |
|---|---|---|
| `cdp.mjs` | `node cdp.mjs "<js 表达式>"` | 在真页面里跑任意 JS(读 DOM/状态、毫秒级采样瞬态);`awaitPromise` 已开,可传 async IIFE |
| `click.mjs` | `node click.mjs "<element 表达式>" [dblclick]` | CDP Input 域真鼠标点击。合成 `.click()` 对 Radix/pointerdown 组件和 ReactFlow 节点**无效**,必须用它 |
| `shot.mjs` | `node shot.mjs out.png` | 截真窗口页面(窗口最小化也能截) |
| `emulate.mjs` | `node emulate.mjs 1400 1200` / `clear` | 视口仿真。**坑**:`clear` 并不还原,验完要显式 set 回真实尺寸(如 1400 900);点击坐标超出真实窗口高度不落地 |
| `console.mjs` | `node console.mjs "<js 表达式>" [等待 ms]` | 执行表达式并收 4s(可调)内 console/异常——点了没反应时用它抓静默失败 |

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
6. 背景原理与非 Windows 场景见 `docs/development/RUN_AND_SCREENSHOT.md` §4;本 skill
   是它在本仓 Windows 主力机上的可执行实例。
