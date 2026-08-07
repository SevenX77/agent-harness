# 决议 2026-08-07:run 终态出口共享产出契约触发 + CLI 读档白名单对齐 + run 控制工具补全

状态:已批准(用户 2026-08-07「按你自己的判断实施然后做真实项目验证」授权,本文档为
方案落盘;三项均为北极星实验 exp-B R6 实测坐实的缺口,证据在下)。

## 背景与证据

北极星实验 exp-B round6(transcript 428 events,坐标见
`D:\coding\skills\_copilot-lab\EXPERIMENT.md` §8 R6 行)坐实三个缺口:

1. **产出契约提醒未送达**。#595 把「run 成功但零产物」提醒挂在 `wait_for_run`
   成功返回上,但 R6 会话全程用 `get_run_detail` 轮询终态、从未调用
   `wait_for_run`——提醒一次都没送达。终态是同一个事实,agent 从哪条工具读到它,
   提醒就该在哪条工具上出现。
2. **CLI 免审批名单漂移**。权威规则是
   `apps/studio/backend/app/agents/contexts/cli.md` 第 23 行:
   "Read and probe tools are pre-allowed. Write and execute tools … surface
   this CLI's own approval prompt."。但 `apps/studio/tauri/src/lib.rs` 的
   `CLAUDE_STUDIO_ALLOWED_TOOLS` 是手抄清单,已两波工具上新未跟上:纯读的
   `get_skill_output_contract`(#585)与 KB-13 第 50 行明文归类为
   "Real connectivity probes; never mutate config vocabulary" 的
   `run_role_test` / `test_llm_endpoint` / `test_llm_endpoint_models` /
   `probe_llm_route` 均不在名单内。bypass 模式下不显性,正常审批模式下这些
   只读/探测调用会平白弹审批卡。
3. **run 控制能力不对等**。人类有 Pause/Stop 按钮(#584,
   `apps/studio/backend/app/routers/runs.py` 210-226 行),copilot 没有对应
   MCP 工具。R6 会话原话(A[223]):"No cancel tool is exposed on this CLI
   surface — I'll let the doomed run expire"。

## 决策

### D-1 终态出口共享产出契约提醒(P4-E9)

- 「run success 且零产物 → 附 `output_contract_reminder`」这条业务规则只保留
  一个权威定义(模块级常量),`wait_for_run` 与 `get_run_detail` 共用。
- `get_run_detail` 仅在 `metadata.status == "success"` 且产物清单为空时附加
  提醒字段;failed/paused/cancelled/running 一律不附(失败要谈的是失败本身,
  混谈会把主缺陷埋掉——与 #595 的测试语义一致)。
- 不改 `get_run_detail` 既有字段(`artifacts` 保持原名),只新增提醒键。

### D-2 CLI 免审批名单对齐读/探测档(P4-E10)

- `CLAUDE_STUDIO_ALLOWED_TOOLS` 增补 5 项:`get_skill_output_contract`(读)、
  `run_role_test`、`test_llm_endpoint`、`test_llm_endpoint_models`、
  `probe_llm_route`(探测,KB-13 归类为据)。
- 写/执行类(含新加的 pause/stop)不进名单——cli.md 档位规则不变,本决议只
  消除代码对规则的漂移,不改规则本身。
- 名单仍是手抄清单的问题(SSOT 漂移隐患,本次是第三次漂移)记入台账观察项;
  不在本次引入生成机制(名单语义在 Rust 侧、工具注册在 Python 侧,跨语言生成
  链路的成本当前不划算,先以「新工具 PR 必须核对 cli.md 档位并同步名单」为纪律)。

### D-3 pause_run / stop_run MCP 工具(P4-E11)

- `copilot_tools.py` 新增 `pause_run` / `stop_run` 工具,直调
  `run_manager.pause_run` / `run_manager.stop_run`——与 HTTP 路由同一条服务链,
  gate 事件照常广播,状态对等(UI 工具栏随之走到 paused/终态)免费获得。
- 工具描述写清语义分工:pause=可从断点续(引擎只在自然完成时清 checkpoint),
  stop=终局但保留 run 记录;非法状态(如对已结束 run 调 pause)由
  run_manager 的 409 语义落成 is_error 返回,不在工具层重复防御。
- `cli.md` 第 23 行执行类枚举补 run control;KB-13 工具地图补对应行。

## 不做什么

- **不改实验任务词/会话身份提示词**。往任务词里加「核对产出契约」会把北极星
  实验测的对象从「产品能否触发 MoirAI 思考」偷换成「指令让她思考」;静态知识面
  已由 KB-14(#616)覆盖,主动触发面由 D-1 覆盖。
- **不给 pause/stop 进免审批名单**。与 run/resume 同档(执行类),审批卡是
  设计内摩擦。

## 验收判据

1. 后端测试:`get_run_detail` success+零产物 → 提醒含 `get_skill_output_contract`
   与 `set_output_artifacts` 两个工具名;success+有产物 → 无提醒键;failed →
   无提醒键。`wait_for_run` 既有三测不回归。
2. 后端测试:`pause_run`/`stop_run` 成功路径返回含 status 的 metadata 投影;
   缺参与非法状态落 is_error。
3. Rust 测试:`CLAUDE_STUDIO_ALLOWED_TOOLS` 断言更新为含 5 个新增项。
4. 全部 CI 门禁绿,PR 合并进 main。
5. 真实项目验证:exp-B round7 按 §6 协议全轮跑通,观测「产出问题」在终态出口
   被真实送达(提醒出现在会话实际读取的工具返回里),结果记入 EXPERIMENT.md §8。
