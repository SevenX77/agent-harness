# 发现:任务3/4/6 的"事件驱动决策面"从未接入真实 Open/Attach/Close 命令入口

- **发现人**:master(本会话,复核 g1-claude 对 af0833d1 的跨泳道审计时,g1 在
  裁定 ACCEPT 之余主动报了一条承重提示,master 亲自顺着提示去 lib.rs 物理核实,
  确认属实)。
- **日期**:2026-07-10

## 论据(文件路径 + 行号 + 引文)

**设计权威(design.md,必须遵守)**:
- `design.md:27`:"Remove `ah ps` text parsing and tmux liveness probing from
  normal status decisions."
- `design.md:178`:"Never use `ah ps` text or tmux probing for normal lifecycle
  decisions."
- `design.md:325`:"Open decision uses the events-primary/status-fallback
  plane, not `ah ps`."

**tasks.md 任务3 原文(仓根 `.kiro/specs/studio-ah-state-contract-v1/tasks.md`)**:
- "移除 normal decision path 对 `ah ps` 文本解析和 tmux 探测的依赖。"

**当前代码(`apps/studio/tauri/src/lib.rs`)**:
- `inspect_ah_runtime`(lib.rs:1157-1191)对每次调用都跑
  `run_ah_config_command_output(config_path, &["ps"])`(lib.rs:1161,即 `ah ps`),
  再用 `extract_tmux_socket_label`/`ah_ps_output_has_inventory`/
  `extract_ah_session_ids` 对其文本输出做解析,并用 `list_tmux_sessions` 探测
  tmux——这正是 design.md 明令移除的路径,一行未删。
- 该函数被三个真实用户触发的生命周期入口直接调用:
  - `prepare_code_assistant_open`(lib.rs:2543-2599,Open 按钮走这条)
    在 lib.rs:2549 与 2561 两处调用 `inspect_ah_runtime`。
  - `attach_code_assistant_terminal`(lib.rs:2626-2659,Attach 走这条)
    在 lib.rs:2635 调用 `inspect_ah_runtime`,并把结果喂给旧的
    `reconcile_code_assistant_lifecycle`(lib.rs:501,布尔 `AhLifecycleSnapshot`,
    非 typed `AhRuntimeSnapshot`)。
  - `force_cleanup_ah_runtime`(lib.rs:1193-1237,Close/quit 强制清理走这条)
    同样吃 `inspect_ah_runtime` 的 probe,并直接调 `kill_tmux_session`
    (lib.rs:1224)——design.md:227 "Do not directly kill tmux sessions during
    normal cleanup." 同样被违反。
- 任务3/4/6 新增的 typed 决策面——`AhRuntimeSnapshot`(lib.rs:3228)、
  `parse_ah_runtime_snapshot`(lib.rs:3246)、`reconcile_snapshot_lifecycle`
  (lib.rs:3272)——只在单元测试里被直接构造 fixture 调用(lib.rs:4157-4426),
  没有任何真实调用点。
- 后台 `ah events` 订阅(`start_code_assistant_status_stream`,lib.rs:1513起)
  确实吃 `AhRuntimeSnapshot` 并推事件,但该函数自己的注释(lib.rs:1492-1496)
  明确写死:"Snapshots only drive the status display... Cleanup happens on
  user actions only (open/attach/close/quit)."——即事件流只喂 UI 状态显示,
  三个真实的生命周期动作入口完全不读它,各自另起炉灶跑 `ah ps`。

## 结论

任务3、4 在 `76ef06b8`("check off tasks 3/4 after master physical acceptance"）
的验收依据只是"cargo test --lib 161 passed"——即新增的 typed 解析/仲裁函数
单测通过,但**从未核实这两个任务自己明文写的验收标准**「移除 normal decision
path 对 `ah ps` 的依赖」「events 设为 open/attach/close 决策的主输入」在真实
命令入口上是否成立。这是前一任 master 验收疏漏,不是本次实现故意留的技术债。

任务6(af0833d1)同理:`reconcile_snapshot_lifecycle` 的 starting/degraded 分支
本身实现正确(g1 已用红测试验证），但因为它没有任何真实调用点，**用户点击
Open/Attach 时实际执行的仍是老的、只认 `active` 布尔的 `decide_code_assistant_open`
+ `reconcile_code_assistant_lifecycle`**——也就是说 starting/degraded 相位在
真机上尚未生效，任务6 在"重做 Open/Attach 决策"这条最终目标上还没有闭环。

## 处置

- `tasks.md` 任务3/4 的 checkbox 改回未完成,补一条 "wiring gap" 说明,避免
  再被误当作已收口。任务6 维持未勾选(本来就没勾）。
- 新增一条不在原 tasks.md 编号体系内的收尾任务(见 `.kiro/specs/.../tasks.md`
  新增条目,编号 6.1):把 `prepare_code_assistant_open` /
  `attach_code_assistant_terminal` / `force_cleanup_ah_runtime` 的决策输入
  从 `inspect_ah_runtime`(`ah ps` 文本 + tmux 探测)切到事件驱动的
  `AhRuntimeSnapshot` + `reconcile_snapshot_lifecycle`（events-primary,
  `status --json` fallback,按 design.md:92-158 的 sequence graph 实现)，
  按项目"无向后兼容"铁律删除旧路径（`AhLifecycleSnapshot`/
  `reconcile_code_assistant_lifecycle`/`decide_code_assistant_open`
  /`inspect_ah_runtime` 的 `ah ps` 分支），不得双轨并存。
- 该收尾任务须在任务7(Close/quit,同样依赖此决策面)之前完成，避免任务7
  继续在同一条错误路径上叠加。任务9(前端按钮投影)依赖任务6的真实闭环，
  同样要排在此收尾任务之后。
