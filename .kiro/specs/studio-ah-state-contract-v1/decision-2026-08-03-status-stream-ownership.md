# 决议 2026-08-03 — 状态事件流的所有权归属 + "尚未观测"不得冒充"没有在跑"

> 本文件是 PM 于 2026-08-03 批准的实施方案落盘件，记录缺陷 C 的修复决策、关键设计决定
> 与验收判据。它修订 `studio-ah-state-contract-v1` 的**订阅生命周期**与**状态投影**部分
> （`design.md` 的 "Frontend event payload" 与 "Tauri event projection"），不修订该 spec
> 的其余部分。前一份决议见 `decision-2026-08-02-lingering-state-and-cli-autoupdate.md`。

## 一、缺陷 C：CLI 明明在跑，面板却渲染 `Open in CLI`

### 1. 现象

2026-08-03 21:37，用户在 Studio 里开着 Claude Code CLI（终端可见、tmux 会话正常、
MoirAI 面板里刚跑完一轮对话），面板右上角的控件却是 `Open in CLI` 下拉，而不是
`CLI running`（Attach / Close）管理控件。用户原话："状态不统一，cli 还开着呢，
右上角的 button 已经变成这个状态了。"

### 2. 根因（已取证）

**取证 1 — ah 侧的真相是 `active`。** 用 Studio 自己构造的那条命令
（`lib.rs:1053-1066` 的 `build_ah_bash_script` 形状）对同一个 config 跑一次
`ah events --format json`：

```
{"schema_version":2,"event":"snapshot","sequence":1,"reason":"initial",
 "runtime_state":"active","ahd_alive":true,"master_tmux_alive":true,
 "sessions":[{"session_id":"sess_f257e2a9-6b63-44ea-b8e6-0c5d345c1f33",
   "path":"/mnt/d/coding/skills/exp-b-round4","status":"ACTIVE",
   "master_state":"IDLE","master_tmux_session":"master_exp-b-round4","master_pid":938}],
 "agents":[{"agent_id":"atropos","state":"IDLE","pid":982,"tmux_alive":true}, …×3]}
```

**取证 2 — Studio 侧一个状态生产者都不剩。** Tauri 进程（PID 31348，17:18:13 启动）
只有一个 `wsl.exe` 子进程，是 17:20:43 起的 `open-claude-code.sh` 启动脚本；WSL 内
`ps -eo pid,ppid,etime,cmd | grep 'events --format json'` 无任何匹配。也就是说
`code-assistant-status-changed` 这个事件没有任何东西在喂。

**取证 3 — 面板因此停在初始值。** `codeAssistantStatus` 仍是构造时的
`inactive/inactive`，于是 `closableCodeAssistantIds` 为空 →
`codeAssistantCloseButtonLabel` 返回 `null`（`copilot-panel.tsx:392-404`）→ 头部走
else 分支渲染 `Open in CLI` 下拉（`copilot-panel.tsx:817-896`）。

**取证 4 — 排除"流从未起过"与"子进程崩溃"。** `ensure_code_assistant_status_streams_for_workspace`
里先跑 `check_ah_version_cached`（`lib.rs:1489`），Open 流程走的是同一个函数
（`lib.rs:2679`）；CLI 在 17:20 开成功了，说明当时版本门通过、流确实建立过。app 日志
（`%LOCALAPPDATA%\com.sevenx.skill-studio\logs\Skill Studio.log`）中不存在任何
`events-exited-respawning` 警告（该警告在子进程意外退出时必打，`lib.rs:1571-1574`），
排除"子进程崩溃后重生失败"。

**由此定位到四条叠加的机制：**

1. **面板是条件挂载的**：`copilotOpen && !morph ? <CopilotPanel/> : null`
   （`Workspace.tsx:2663`）。折叠 / 展开 MoirAI 面板 = 组件卸载 / 重新挂载。
2. **卸载会向 Rust 发出停流命令**：effect cleanup → dispose
   （`copilot-panel.tsx:657-660`）→ `invoke('unwatch_code_assistant_status')`
   （`tauri.ts:289-292`）。
3. **该命令无条件杀掉共享的生产者**：`unwatch_code_assistant_status_streams_for_workspace`
   （`lib.rs:1675-1703`）杀 `ah events` 子进程、删 `status_specs`、清 `status_snapshots`，
   既不看还有没有别的订阅者，也没有任何引用计数。
4. **`watch` / `unwatch` 都是异步 IPC，没有顺序保证**：上一次卸载（或 `StrictMode`
   开发期双挂载中被丢弃的那一次，`main.tsx:19`）发出的 `unwatch`，只要**落在**新挂载
   发出的 `watch` **之后**，就会把活着的订阅者的生产者杀掉。而 `watch` 只在
   「挂载 / Open / Close / CLI 退出」四个时机下发（`copilot-panel.tsx:626、678、682、721`），
   没有任何兜底重连——于是永久停在这个状态。

**第五条机制放大了后果**：`code_assistant_status_from_snapshots` 把"这个 config 还没有
任何快照帧"投影成 `AssistantStatus::Inactive`（`lib.rs:1384-1387`
`.unwrap_or(AssistantStatus::Inactive)`）。`unwatch` 刚清空缓存，紧接着的 `watch` 立刻
用空缓存 emit 一次（`lib.rs:2786-2787`），面板收到的是一句**断言**"两个助手都没在跑"，
而事实只是"还没观测到"。

### 3. 决策

**PM 裁决（2026-08-03）：这是所有权错误，不是按钮逻辑错误，也不是竞态调参问题。**
`ah events` 事件流是"这个工作区有 Studio 管理的 ah 配置"这件事的属性，它的 owner 必须是
Rust 侧的 `CodeAssistantRuntimeState`；React 组件只能是**纯观察者**，无权决定生产者的生死。
同时，"尚未观测到"必须被如实表达，不得冒充"确定没有在跑"。

### 4. 参考的成熟做法（外部先例）

本决议采用的两条模式在成熟项目里都是既定解法，不是本仓自创：

- **外部 store 拥有订阅，视图只挂载观察者**：React 18 的 `useSyncExternalStore`
  把 store 放在 React 之外，组件只提供 `subscribe`/`getSnapshot`；TanStack Query 的
  query 由 `QueryCache` 拥有，组件挂的是 observer，最后一个 observer 卸载后数据还会
  按 `gcTime` 保留一段时间才回收，正是为了让"卸载→重挂载"不摧毁缓存；SWR 的 per-key
  全局缓存同理。共同点是：**卸载一个视图不等于销毁数据源**。
- **"未知"是一等状态**：gRPC 健康检查协议有 `UNKNOWN`/`SERVICE_UNKNOWN`；Kubernetes
  的 node condition 取值含 `Unknown`；Docker 健康检查在拿到第一次结果前是 `starting`
  而不是 `unhealthy`。共同点是：**没观测到不等于观测到没有**。

### 5. 关键设计决定

#### D-C1：删除 `unwatch_code_assistant_status` 整条路径

**决定**：删除 Tauri command `unwatch_code_assistant_status`
（`lib.rs:2791-2802`）及其实现 `unwatch_code_assistant_status_streams_for_workspace`
（`lib.rs:1675-1703`），并从 `invoke_handler` 注册表中移除。前端 dispose 只做本地
`unlisten()`，不再向 Rust 发任何停流命令。

**理由**：订阅者的 teardown 只应撤销它自己建立的东西——它建立的只有一个前端监听器。
生产者是它到达之前就该存在、它离开之后仍该存在的共享资源。让 teardown 去杀生产者，
就是把「谁拥有这个状态」这个问题回答错了（AGENTS.md「显式状态与唯一 owner」）。

**被否决的替代项 1 — 引用计数**：`refreshCodeAssistantStatus`
（`copilot-panel.tsx:621-627`）在 Open / Close / CLI 退出后单方面调 `watch` 而**没有**
配对的 `unwatch`，计数天生不平；更根本的是，引用计数只是把竞态窗口变窄，并没有纠正
"view 决定 producer 生死"这个错误的所有权。

**被否决的替代项 2 — 前端给 dispose 加延迟 / 防抖**：症状级补丁，违反
AGENTS.md「First-principles fixes, not patches」。

#### D-C2：`watch` 是幂等的"确保存在"，并顺带收敛到单工作区

**决定**：`watch_code_assistant_status(workspace_root)` 的语义改为
「确保该 workspace 的生产者存在」+「停掉**其它** workspace 的生产者」。

**理由**：Studio 同一时刻只显示一个工作区（`Workspace.tsx` 的 `currentWorkspaceRoot`
是单值），所以"当前工作区"这个不变量本来就成立。用它来界定生产者集合，既让生产者数量
有界（不会随用户切 skill 无限累积），又保证**永远不会杀掉正在被观察的那一个**——这正是
删掉 `unwatch` 之后仍然需要的资源上界。

**边界**：被停掉的只有 `status_specs` / `status_streams` / `status_snapshots` 这三张
**观察**用的表；`state.configs`（退出时 cleanup 用的**生命周期**注册表）不受影响，
所以切换工作区不会让别的工作区的 ah 运行时逃过退出清理。

#### D-C3：新增相位 `unknown`，表示"尚未观测"

**决定**：`AssistantStatus` 增加取值 `unknown`，wire 值 `"unknown"`。其定义为：
**Studio 知道这个助手有一份 ah 配置，但还没有拿到任何一帧描述它的运行时快照。**

产生它的唯一位置是投影层：spec 存在但 `status_snapshots` 里没有对应帧。**完全没有
ah 配置**的助手仍然投影为 `inactive`——那是一次真实的观测（磁盘上没有配置 ⇒ 没有
Studio 管理的运行时），不是未知。

**前端语义**：`unknown` 与既有的 `starting` 同属"hands-off"一类——头部渲染 Open 控件
但**禁用**，不得渲染可点击的 Open，也不得渲染 Attach/Close。

**理由**：`inactive` 在本契约里是一句断言（"这套运行时确实被回收过"，见 2026-08-02
决议 D-A1 与 D-A4 决策表末行）。把"没观测到"塞进这句断言，会让 UI 在缺乏依据时给出
一个可点击的、语义错误的入口——这正是缺陷 C 的可见形态。用一个独立取值把它区分开，
是「让非法状态不可表示」的直接落地。

**被否决的替代项**：把 payload 里的每个助手改成可空（`AssistantState | null`）。
会让所有投影函数都要处理 null，而 null 在 TS 里最容易被 `??` 系列默认值悄悄吃掉，
反而更容易复发同一个缺陷。

#### D-C4：流启动时用 `ah status --json` 播种，把未知窗口压到最短

**决定**：`start_code_assistant_status_stream` 在进入 `ah events` 监督循环之前，
若该 config 在 `status_snapshots` 里没有任何帧，先做一次 `ah status --json` bootstrap
读取（复用既有的 `resolve_bootstrap_snapshot` + `verify_snapshot_identity`），把结果
按与 events 帧完全相同的路径写进缓存并 emit。已有缓存帧时跳过（子进程重生不重复播种）。

**理由**：`design.md:29` 定的就是"events 为主、`status --json` 作为 bootstrap/fallback"。
这条 bootstrap 目前只接在**生命周期判定**那条道上（`resolve_open_snapshot`，
`lib.rs:3577-3595`），**UI 状态投影**这条道没接——`unwrap_or(Inactive)` 就是这个缺口的
现场。本决议把同一条规则补到 UI 投影这条道，属于修复实现对设计的 drift，不是新增设计。

**放在流线程里而不是 emit 路径里**：`ah status --json` 要跨 WSL，耗时以秒计。放进
`watch` 命令会阻塞 IPC；放进流线程则不影响任何前台路径，代价只是首帧晚 1~2 秒——
而那段时间里 UI 呈现的是诚实的 `unknown`。

#### D-C5：给订阅生命周期补结构化日志

**决定**：`watch` 到达、生产者启动 / 停止、bootstrap 结果，各打一行 `log::info!`，
沿用既有 `phase=… action=…` 格式。

**理由**：本次排查全靠翻进程表反推，因为这条链一行日志都没有。可观测性缺失本身就是
缺陷的一部分（rules/logging.md）。

#### D-C6：删除前端投影器里的 boolean / null 兼容形状

**决定**：`AssistantStateInput`（`copilot-panel.tsx:320`）收窄为 `AssistantState`，
删掉 `boolean` 与 `null | undefined` 分支及其"未知即 inactive"的强制转换
（`copilot-panel.tsx:322-327`）。对应的两处 boolean 形状测试
（`copilot-panel.test.ts:339、359`）改用真实 payload 形状。

**理由**：该 boolean 形状注释自称是"legacy per-assistant flag"，但 Rust 侧自 task 8
起只发 `AssistantState` 结构（`lib.rs:171-185`），这条兼容分支已经是死路径——按
AGENTS.md「No backward compatibility」必须在同一改动里删干净。更重要的是，
`state?.status ?? 'inactive'` 与 `unwrap_or(Inactive)` 是同一个缺陷在前端的复制品：
只修 Rust 侧而留着它，等于给复发留了后门。

## 二、验收判据

| # | 判据 | 验证方式 |
|---|---|---|
| C-1 | 同一 workspace 连续两次 `watch` 之后，生产者只有一个且仍在运行 | Rust 单测（注入可观测的启动/停止记录） |
| C-2 | 一个订阅者 teardown 之后，另一个订阅者的生产者与缓存都还在 | Rust 单测；由"不存在 unwatch 命令"这一事实保证，附注册表断言 |
| C-3 | `unwatch_code_assistant_status` 不再存在于 `invoke_handler` 注册表 | Rust 单测（源文本断言，沿用既有 registry 断言的写法） |
| C-4 | `watch(B)` 之后，A 工作区的生产者被停掉、B 的仍在 | Rust 单测 |
| C-5 | spec 存在但无快照帧 → 投影为 `unknown`，不是 `inactive` | Rust 单测 |
| C-6 | 完全没有 ah 配置的助手 → 仍投影为 `inactive`（对照组，证明不是常量） | Rust 单测 |
| C-7 | 有快照帧时投影仍按 2026-08-02 决策表走（active/lingering/degraded/starting/inactive） | Rust 单测（既有 fixture 回归） |
| C-8 | `unknown` 渲染**禁用**的 Open 控件，既不可点 Open，也不出现 Attach/Close | 前端单测 |
| C-9 | 面板卸载→重挂载后，面板不会因为收不到事件而停在"可以 Open"的错误呈现 | 前端单测（挂载态初值为 `unknown`） |
| C-10 | 投影器不再接受 boolean / null 形状（类型层面），既有语义测试全绿 | `npm run typecheck` + 前端单测 |
| C-11 | 真机：CLI 开着时反复折叠/展开 MoirAI 面板，`ah events` 进程始终存在，控件始终是 `CLI running` | 操作者实测（进程表 + 界面）— ✅ 2026-08-03 通过：三轮折叠/展开，同一 PID 全程存活，日志 `stream-start=1 / stream-stop=0` |
| C-12 | 代码里不存在"只清快照缓存、不重开观察流"的入口（D-C7） | Rust 源码断言测试 |
| C-13 | 真机：Close 之后控件在数秒内回到**可点**的 `Open in CLI`，不停在禁用态 | 操作者实测（采样按钮 disabled 状态） |

### 6. D-C7：Close 确认消失之后必须**重开观察流**，而不是只清缓存

> 本节由 2026-08-04 的真机点验推翻并重写。原文曾把"Close 之后的 `unknown` 窗口"记为一处
> 被接受的取舍，其依据是"`ah events` 子进程会随 ahd 一起退出、监督循环 3 秒后重生"。
> **这个依据经实测为假**，原结论随之作废。

**实测事实（2026-08-04）**：`ah stop` 杀掉 ahd 之后，该 config 的 `ah events` 子进程
**不会退出**——它只是从此永远不再发帧。现场：ahd 停止后子进程仍存活 3 分 08 秒，app 日志
里 `events-exited-respawning` 计数为 **0**，面板停在 `unknown` 超过 30 秒无任何变化。
（对照实验证明 ah 侧行为正常：`ah stop` 后 socket 确实消失、`status --json` 退 1、
新起一个 `ah events` 立刻发出 `reason:"daemon_absent"` / `ahd_alive:false` 的首帧，
并且它不会把 ahd 重新拉起来。）

**后果**：`clear_status_snapshots_for_workspace` 清空缓存之后，**再没有任何东西能把它
填回来**——投影按 D-C3 给出 `unknown`，面板把 Open 控件**永久禁用**，使用者连重新打开
CLI 的入口都没有了。这比修复前更糟：修复前"未知冒充 inactive"至少让按钮可点。

**决定**：删除"只清缓存"这个动作本身，`close_code_assistant` 的两条分支都改走
`restart_status_streams_for_workspace`——停掉该 workspace 的观察流并立即重建。重建后的
`ah events` 立刻发一帧 `daemon_absent`，投影成 `inactive`，Open 恢复可点；未知窗口是
新流从启动到首帧的一两秒，有界且诚实。

**一般规则**：**一条 `ah events` 流绑定的是某一个 daemon 实例，不是那份 config。**
Studio 自己改变了 daemon 的存亡，就必须把观察者一起重开——否则观察者会安静地对着一个
已经不存在的 daemon 继续"运行"，而这种沉默与"什么都没发生"不可区分。

**被否决的替代项**：给快照缓存加一个 `Absent` 变体来记录"确认消失"这次观测。它能表达得
更准，但没有触及真正的病灶——那条流已经死了却还占着位置；下一次 daemon 起来时它同样
不会有任何反应。修观察者的生命周期才是那一层。

## 三、范围边界

本决议**不包含**：改 ah 仓任何代码；改 `ah events` / `ah status` 的调用形状（除 D-C4
新增的 bootstrap 时机外）；改 2026-08-02 决议定下的 phase→UI 投影表（`unknown` 是新增
取值，不改既有取值的映射）；改嵌入式终端（`cli_terminal`）的生命周期；把非 Tauri 运行时
（浏览器预览）下的 `inactive` 改成 `unknown`——那里"没有原生能力 ⇒ 没有运行时"是一次
真实观测，不是未知。
