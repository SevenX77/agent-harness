# Task 11 · 手工 Smoke 逐项点验清单(交给 operator/PM 在真机上点)

> **为什么这份清单存在(不是偷懒跳过)**:task 11 的手工 smoke 需要在**真机图形桌面**上把
> Tauri 桌面 app 跑起来,用真实 ah v1.4.0+ 编队逐个走 Open/Attach/starting/degraded/Close/quit
> 等交互场景。本轮验证沙箱的实测状态:
> - **系统库已就绪**(2026-07-11 实测:`dbus-1 / gtk+-3.0 / glib-2.0 / gdk-3.0 / gio-2.0 /
>   webkit2gtk-4.1 / javascriptcoregtk-4.1 / libsoup-3.0 / cairo / pango / atk / gdk-pixbuf-2.0`
>   全部 `pkg-config --exists` = OK)——所以 **Rust crate `cargo test --lib` 本轮真机跑通了**
>   (166 passed,唯一失败是 root 沙箱假象 `publish_package_writer_maps_permission_error`,
>   与本 spec 无关,详见验证报告)。
> - **但没有图形显示服务**:`DISPLAY` 为空、无 Wayland、`Xvfb` 未安装。桌面 GUI 无处渲染,
>   9 个交互场景无法在此环境真机点验。
> - 且这 9 个场景是**多步交互 + 真实 ah 编队生命周期**(启动 master、attach 进 tmux、让 master
>   `/exit`、制造 degraded 死栈……),本质上属于真机 GUI 人工点验,不是自动化能替代的。
>
> 结论:自动化门禁(Rust crate 测试 + 前端投影测试 + 后端全量回归)本轮已全绿(见
> `task11-verification-report-2026-07-11.md`);下面 9 条**交互 smoke 移交 operator/PM 在有图形
> 桌面 + 真实 ah 的机器上逐条点验**。每条写清「如何触发 / 预期看到什么」,照着点即可。

## 前置

- 机器有图形桌面(Windows 原生,或 Linux 带 X/Wayland)。
- 已装 **ah v1.4.0+**(本轮验证机实测 `ah version` = `1.5.0`,满足版本门)。
- 按 `AGENTS.md`「Studio Tauri Dev」标准启动:仓根跑
  `powershell -ExecutionPolicy Bypass -File .\scripts\studio-dev.ps1`(Windows)或
  `scripts/studio-dev.sh`(macOS/Linux)。**不要**裸跑 `cargo tauri dev`。
- 打开 Copilot 面板(右侧 Copilot 泳道),观察其 header 的 Open/Attach/Close 控件。
- 术语对照(代码锚点,方便判断"看到的对不对"):
  - 面板按钮投影逻辑:`apps/studio/frontend/src/components/copilot/copilot-panel.tsx`
    (`isAssistantActive` / `codeAssistantCloseButtonLabel` / `isClaudeOpenDisabled` 等,285-360 行)。
  - Rust 决策面:`apps/studio/tauri/src/lib.rs` 的 events-primary 快照仲裁 +
    ownership 分类 + env clamp;设计真相 `docs/studio/mvp1/03_regions/copilot/ah-orchestration-design.md`。
  - 5 态契约:`inactive | starting | active | degraded | error`(per-assistant,claude/codex 独立)。

---

## 逐项点验(9 条,对应 task 11 枚举的全部场景)

> 勾选格式:每条一行,`[ ]` 待验 / `[x]` 已验;不通过的在「实测」栏写下现象并回报。

### 1. Open(inactive → start)
- [ ] **如何触发**:选一个 **Studio 自己注册的 temp config**(Studio-managed,非仓根 `ah.toml`)对应的
  workspace,此时该 assistant 快照为 `inactive`(ahd 未起或 `active=false` 且所有 session 终态)。
  点击 header 的 **Open**(如 "Open Claude code" / "Open Codex")。
- [ ] **预期看到**:发出 `ah start`(仅对 Studio-managed config 允许),弹出/切到 assistant 终端,
  编队开始启动;按钮不再是 Open。**不得**对 workspace-owned config 触发 start。
- **实测**:________
- _Req 3.1/3.2/3.3, 5.2_

### 2. Attach(active → attach,不重启)
- [ ] **如何触发**:在已有 active 编队(`runtime_state=active`)时,点击 **Attach**(从 Attach 菜单选
  "Attach Claude code" / "Attach Codex")。
- [ ] **预期看到**:直接 attach 进已存在的终端会话(复用,不跑 launcher、不重新 `ah start`);
  能看到 master 的实时输出。
- **实测**:________
- _Req 3.1/3.2/3.3_

### 3. master `/exit` 后回到 Open
- [ ] **如何触发**:在 attach 的 master 终端里输入 `/exit`(或让 master 正常退出),编队收敛为
  `inactive`(ahd alive 但 `active=false`,或 daemon 退出)。
- [ ] **预期看到**:面板通过 events-primary 快照感知状态变化,按钮**恢复为 Open**(不卡在 Attach、
  不误报 error)。
- **实测**:________
- _Req 3.1/3.2/3.3, 5.11_

### 4. `starting` 期间 hands-off
- [ ] **如何触发**:在编队刚 `ah start`、尚未 ready 的窗口内观察(`runtime_state=starting`)。
- [ ] **预期看到**:Open 控件**禁用/hands-off**(`isAssistantStarting` → 触发器不可点),
  UI 显示 starting 态,**不报错、不重复启动、不清理**。
- **实测**:________
- _Req 3.6, 5.6_

### 5. `degraded` 期间 Open 可用(cleanup-then-open)
- [ ] **如何触发**:制造 degraded 快照(`active:false, runtime_state:"degraded"`,某 session
  `cleanup_required:true`、master tmux 已死但 db 仍有 live_agents)。可通过手动 kill 掉 master tmux
  再观察,或用 ah 侧手段造出 degraded。
- [ ] **预期看到**:**Open 按钮可用**(不是三态全灭),点它走 cleanup-then-start:先对
  `cleanup_required`/非 `safe_to_cleanup` 的 session 清理,再 start。
- **实测**:________
- _Req 3.7, 5.7_

### 6. Close(Studio-managed active → ah stop)
- [ ] **如何触发**:对一个 **Studio-managed** 的 active 编队,点击 **Close**(单活跃时按钮文案为
  "Close Claude code" / "Close Codex")。
- [ ] **预期看到**:先确认目标 config 是 Studio-managed,再发 `ah stop`;stop 后重读快照;
  如需强制清理只对 `cleanup_required`/非 `safe_to_cleanup` 的 session 发 `ah kill --session <id> --force`
  (不再"非终态即 kill",不直接 kill tmux)。
- **实测**:________
- _Req 4.1-4.5, 5.5_

### 7. app quit cleanup(只清 Studio-managed)
- [ ] **如何触发**:在有 Studio-managed 活跃编队时,直接退出/关闭桌面 app。
- [ ] **预期看到**:quit 流程只清理 Studio 注册过或 Studio temp namespace 下的 config;
  **不**触碰 workspace-owned config,**不**清理用户在 default state dir 手动起的 ahd。
- **实测**:________
- _Req 4.4/4.5/4.6, 5.9_

### 8. workspace-owned config(仓根 `ah.toml`)在 Close/quit 时不受影响
- [ ] **如何触发**:让当前 selected config 命中**向上发现的 workspace-owned config**(如本仓根
  `ah.toml` 对应的 operator 自己的编队),分别做一次 Close 和一次 app quit。
- [ ] **预期看到**:对 workspace-owned config **绝不发任何生命周期命令**(无 `ah start`/`stop`/`kill`);
  operator 自己的编队在 Close/quit 后**仍然活着、不受影响**。
- **实测**:________
- _Req 5.9_

### 9. 只读 assistant 的 Close = Detach(仅断开观察,编队仍活)
- [ ] **如何触发**:对一个 **workspace-owned(readOnly:true)且 active** 的 assistant,观察其 Close 控件
  并点击。
- [ ] **预期看到**:Close 按钮文案呈现为 **"Detach"**(`codeAssistantCloseButtonLabel` 在全部活跃项皆
  readOnly 时返回 `Detach`);点击**只关闭本地观察 tab / 断开 attach**,**不发** `ah stop`/`ah kill`,
  远端编队**继续存活**。另:readOnly 且 inactive 时 **Open 置灰**并带引导文案(不发任何生命周期命令)。
- **实测**:________
- _Req 5.14, 6.4_

---

## 点验后回报

- 全通过 → 在本文件把对应 `[ ]` 勾成 `[x]`,回报 master「task 11 手工 smoke 全绿」。
- 有不符 → 在该条「实测」栏记录现象(截图更佳),回报 master 裁定(本 spec 的实施者是
  g1-m1-antigravity;修复派单归 master)。
