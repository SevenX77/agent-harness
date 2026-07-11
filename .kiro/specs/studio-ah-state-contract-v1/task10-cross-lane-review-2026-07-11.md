# 跨泳道审计:26308bd3 task10 设计文档回写(F7)

- **审计人**:g2-claude(泳道2 gatekeeper),跨泳道独立验证 d1-claude 执笔的纯文档回写(不采信 commit message 自报)
- **被审 commit**:`26308bd34d4fc3b7809a5449eb229d84bb7e69d4`
  `docs(design): task10 设计文档回写(F7)`
- **spec 依据**:tasks.md 任务 10(把 `docs/studio/mvp1/03_regions/copilot/ah-orchestration-design.md`
  与本 spec `design.md` 里被 ah 1.3.4+ 证伪的旧措辞,回写成与 task5-9 已验收实现一致的表述);
  4 条验收点见 `.kiro/specs/studio-ah-state-contract-v1/tasks.md`「10. 设计文档回写」
- **交叉核实来源**:`apps/studio/tauri/src/lib.rs` 真实代码 + `requirements.md` + `design.md` 数据模型 +
  task5/6/6.1/7/9 已通过的 cross-lane-review
- **日期**:2026-07-11
- **裁定**:**✅ 通过(ACCEPT)** —— 4 处 markdown + design.md:226 逐处忠实于已验收实现;
  纯文档、零生产代码/测试夹带;design.md:226 的 task7 §2 出处主张经原文核对属实。
  附**一条已诚实标注、不影响裁定的观察**(item 4 moirai skill 文案的 code↔design drift,归 master
  跟踪的独立修复线,不在本审计范围)。

---

## 一、任务背景

本 spec(studio-ah-state-contract-v1)任务 5-9 已全部实施完成并逐单跨泳道审计通过(见同目录
`task5-*`/`task6-*`/`task6.1-*`/`task7-*`/`task9-cross-lane-review-*.md`)。task10 是设计回写单:把
两份文档里被 ah 1.3.4+/1.4.0 证伪的旧措辞,订正为与已落地实现一致的表述——这是「MVP1 design = source
of truth」纪律下**闭合 code→design 漂移**的收口动作(方向:让设计文档追平已验收实现的目标态)。

被审 commit 声明改动 4 处 markdown + 额外 1 处(design.md:226,响应 task7 跨泳道审计遗留跟进项)。

---

## 二、Diff 合规核对:纯文档、零生产代码/测试夹带 —— ✅(验收点 5)

`git show 26308bd3 --stat`:

```
 .kiro/specs/studio-ah-state-contract-v1/design.md  |  2 +-
 .../03_regions/copilot/ah-orchestration-design.md  | 33 +++++++++++++---------
 2 files changed, 21 insertions(+), 14 deletions(-)
```

- **仅 2 个文件,均为 `.md`**;无 `apps/studio/tauri/src/lib.rs`、无任何 `.ts/.tsx/.rs/.py`、无测试文件。
- 工作树里游离的 `M ah.toml`、`.operator-report.phase1`、`vendor/` **均未被本 commit 吸入**(非 `git add -A`)。
- `git show 26308bd3` 全 diff 逐行确认:两个文件的每一个 hunk 都是散文/规则文字的替换,无代码块逻辑改动。

结论:纯 markdown 回写,不碰生产逻辑,合规。

---

## 三、逐处改动忠实度核对(验收点 1、3)

对每处改动,核对「改后文字」是否真实匹配 task5-9 已验收实现;并专查有无「文档写得比实现更宽」或
「文档遗漏实现里的真实约束」的失真/过度美化。

### 改动 1 —— ah-orchestration-design.md §4.6 生命周期规则(四值相位语义) —— ✅ 忠实

改后文字(diff 新增块)称:`runtime_state` 是**四值相位** `active`/`inactive`/`starting`/`degraded`;
`starting`=**hands-off**(不清理、不重复启动、UI 显示 starting 不报错);`degraded` 必须暴露**可用的
cleanup-then-open 路径,三个按钮不得全灭**,清理目标由 ah 自己的 per-session `cleanup_required` 驱动,
`safe_to_cleanup` 是安全闸不是 kill 触发器。逐条对实现/权威设计:

- **四值相位**:权威数据模型 `design.md:19`「`runtime_state` is a **four-value phase**, not a boolean:
  `active`, `inactive`, `starting`, `degraded`」+ `design.md:240` TS 契约
  `runtimeState: 'active' | 'inactive' | 'starting' | 'degraded'`;实现侧 `lib.rs:3044`
  `runtime_state: AhRuntimeState` + `lib.rs:3153 assistant_status_for_runtime_state(...)` 四值 match。✔
- **starting=hands-off**:`design.md:327`「`starting` phase performs no cleanup/no duplicate start」;
  被 ah 1.3.4 证伪的旧句「runtime_state 只有 Active/Degraded/Inactive、没有 Starting」在 diff 中被删除并
  改写为「当时 Studio 读到的快照还没有相位字段、只能靠两个布尔猜——这正是根因」,与 §4.6 冷启动自杀事故
  的诊断一致,消除了段内自相矛盾。✔
- **degraded 露可用 Open、三按钮不得全灭、由 cleanup_required 驱动**:权威 `Requirement 3.7`
  (`requirements.md:82`)「degraded ... expose an Open action that first runs cleanup driven by the
  snapshot's own ... `sessions[].cleanup_required`/`sessions[].safe_to_cleanup` ... degraded shall never
  leave the user with zero available actions」;`design.md:328/337`「degraded ... driven by
  `sessions[].cleanup_required`/`safe_to_cleanup`」「maps to a working Open path, not a fully disabled
  button set」。**已验收实现**:task9(`2a14016b`,g1 审 ACCEPT,`task9-cross-lane-review-2026-07-11.md`
  §2/§3)——starting 控件 disabled/hands-off、degraded 露 `aria-label="Open code assistant"` 且
  `disabled=false` 的可用 Open、断言「不是 Attach/Close,也不是三态全灭」。✔

判定:**忠实,未放宽也未遗漏约束**。文字所述「三按钮不得全灭 / cleanup_required 驱动 / starting hands-off」
恰为 Req 3.7 + task9 已验收行为的散文投影,无「比实现更宽」。

### 改动 2 —— ah-orchestration-design.md §9.9(旧 629,events-primary 主决策面) —— ✅ 忠实

改后文字:状态检测以 `ah events --format json` 为**主决策面**、`ah status --json` 为 bootstrap/fallback,
按 `sequence` 仲裁;活跃/相位判定读结构化 `runtime_state`(四值),不再用 `ahd_has_inventory`/
`master_tmux_alive` 双布尔猜 stale;每帧先按请求 config 做身份校验(权威判据 `state_dir` + 会话身份
`session_id`/`path`/`project_id`,`config_path` 仅诊断),不匹配即丢弃;绝不解析 `ah ps` 文本/探测 tmux。

- **events-primary + status fallback + 身份校验**:`lib.rs:3281-3335 resolve_open_snapshot` doc/实现
  「events-primary; ... bootstraps from `ah status --json` and verifies the snapshot really describes」;
  「never `ah ps` text or tmux probing (design.md:178)」(`lib.rs:3330`)。✔
- **sequence 仲裁**:`lib.rs:3163-3202 SequenceArbiter`(`accept()` 按 `sequence` 判 reset/前进/丢弃)。✔
- **config_path 仅诊断、身份靠 state_dir/session**:权威 NF1(`design.md` Requirement 2.7/4.8,
  `task7-cross-lane-review-2026-07-11.md` 引 NF1);`lib.rs` 快照注释「`config_path` is ADVISORY」。✔

判定:**忠实**。旧「双布尔同时成立」框架被收敛到读结构化相位,与实现主决策面一致。

### 改动 3 —— ah-orchestration-design.md §9.9(旧 637-640,ownership guard + 只清 cleanup_required) —— ✅ 忠实

改后文字:不再解析 `ah ps` 文本提取 `tmux -L <socket>`/`sess_*`、不做 tmux double-check;强清只对身份校验
通过快照里 ah 标记 `cleanup_required` 的 session 发 `ah kill --session <id> --force`(`safe_to_cleanup` 是
安全闸不是 kill 触发器);生命周期命令前先过所有权分类(ownership guard);Close/quit cleanup 改为重读结构化
快照、**不直接 kill tmux**、workspace-owned config 透明跳过。

以上四点**逐条**已被 task7(`5cb62744`,ACCEPT,`task7-cross-lane-review-2026-07-11.md` §2/§3/§4/§5)坐实:

- 只清 `cleanup_required`:`lib.rs:3319-3323 cleanup_target_session_ids` = `.filter(|s| s.cleanup_required)`。✔
- 只走 `ah kill --session --force`、tmux 直杀分支删净:task7 §3 + `force_cleanup_ah_sessions`。✔
- 所有权透明跳过:task7 §4 + `cleanup_code_assistant_config` 首行 `if classify_config_ownership(..).read_only
  { return Ok(false); }`。✔
- 重读结构化快照:`lib.rs:3328-3335 resolve_cleanup_snapshot`(events-primary / status fallback,不碰 ah ps/tmux)。✔

判定:**忠实,与 task7 已验收实现完全对齐**。

### 改动 5 —— design.md:226(kill 目标判据收紧) —— ✅ 忠实(专项核查见 §四)

### 改动 4 —— §9.6(旧 553)/§9.9(旧 644)「ah status 不是可用命令」订正 —— ⚠️ 文档已追平目标态,生产字符串暂缓(见 §五)

改后文字把「`ah status` 不是可用命令,不要调用」订正为「优先用 `ah status --json`(1.4.0 起可用的结构化
bootstrap/fallback 读),必要时辅以 `ah ps`;daemon 不存在时 `status --json` 非零退出且无 JSON(F1)」。

- **`ah status --json` 为 1.4.0 起可用的合法读**:`lib.rs:3284/3335` 直接以 `status --json` 作 bootstrap;
  `requirements.md:82`(F1 daemon-absent)、`lib.rs:4208-4220`(daemon-absent 时 `status --json` 非零退出)
  佐证「非零退出且无 JSON(F1)」的注释真实。✔ **文字所述与实现读面一致**。
- **忠实度注意**:§9.6/§9.9-644 描述的是 `.ah/skills/moirai-intro/SKILL.md` 的**目标文案**,而当前生产
  代码里该 skill 字符串(`lib.rs:599`,常量 `MOIRAI_INTRO_SKILL` 定义于 `lib.rs:586`)**仍为旧句**
  「用 `ah ps` ... `ah status` 不是可用命令,不要调用」。即**文档已先行追平目标、生产字符串尚未跟上**——存在
  一处 code↔design drift。此项即 task10 验收点 4 的**暂缓项**,commit message 已诚实标注,**不在本审计范围**
  (brief 明确:该字符串因与测试断言耦合,走独立修复线);详见 §五。

---

## 四、design.md:226 专项核查(验收点 2:task7 §2 出处主张是否属实)

commit message 声称 design.md:226 的收紧「响应 `task7-cross-lane-review-2026-07-11.md` §2 的要求,且已用
回滚自检坐实」。**不采信转述,去读 review 原文 + 生产代码核对:**

**(a) 「响应 task7 §2 要求」属实。** `task7-cross-lane-review-2026-07-11.md` §2 结尾(该文件 88-90 行)
明列「**必须跟进项(记入 gate)**:... 须在 **task10 设计回写**时把 design.md:226 收紧为『只按
`cleanup_required`;`safe_to_cleanup` 是安全闸不是 kill 触发器』,闭合 code↔design 的 drift」;§五
遗留跟进项(234-237 行)复述同一要求。→ design.md:226 收紧确为 task7 §2 交办的跟进项。✔

**(b) 「已用回滚自检坐实」属实。** task7 §2(62-72 行)+ §四回滚自检(191、195-206 行)记录:把生产谓词
临时改成 design.md:226 字面 OR 读法 `session.cleanup_required || !session.safe_to_cleanup`,重跑 test1
→「**精确变红在『a live ACTIVE session ... must NOT be killed』**」,即字面 OR 会把活栈
(`safe_to_cleanup:false`、6 个 live agent 在跑)选为 `ah kill --force` 目标——对操作者自有编队的误杀。
→ commit message 的「回滚自检坐实字面 OR 会误杀活栈」主张,与 review 原文逐字吻合。✔

**(c) 改后 design.md:226 文字忠实于实现,无过度美化。** 改后原文(`design.md:226`):

> ... only where the snapshot marks that session `cleanup_required`. `safe_to_cleanup` is ah's **safety
> gate** ... NOT a kill trigger, so `!safe_to_cleanup` alone must never escalate a kill — targeting is
> driven solely by `cleanup_required`, per Requirement 4.2 ... The earlier `cleanup_required`/not
> `safe_to_cleanup` OR-reading was falsified by task7's rollback self-check ...; see
> `task7-cross-lane-review-2026-07-11.md` §2.

与生产代码近乎逐字一致:`lib.rs:3315-3317` doc 注释「`safe_to_cleanup` is ah's safety gate against
killing live work, NOT a kill trigger, so `!safe_to_cleanup` alone must never escalate a kill — only ah's
own `cleanup_required` flag selects a target」;`lib.rs:3323` 实现 `.filter(|s| s.cleanup_required)`;
权威 `Requirement 4.2`(`requirements.md:94`)「prefer the snapshot's own `sessions[].safe_to_cleanup`/
`cleanup_required` ... over Studio re-deriving『non-terminal therefore kill』」。文档还反向引用了 review
出处,code↔design 双向对齐。✔

判定:**design.md:226 收紧 = 由 OR 读法(更宽、会误杀活栈)收紧为「只按 cleanup_required」(更 fail-closed)**;
这是 task7 遗留跟进项的正确闭合,**在安全轴上更收紧、非稀释**,commit message 的 §2 出处与回滚自检主张
**经原文核对全部属实**。

---

## 五、观察:item 4 moirai skill 文案的 code↔design drift(诚实标注、不在本审计范围)

brief 已预先告知:验收点 4(`lib.rs:599` moirai-intro skill 字符串「ah status 不是可用命令」)因牵动测试
断言、走独立修复线,**不在本审计范围**。核对全链后如实记录状态,供 master 跟踪:

- 本 commit(26308bd3)把**设计文档** §9.6/§9.9-644 先行订正为 `ah status --json` 目标态;**生产字符串**
  `lib.rs:599`(`MOIRAI_INTRO_SKILL`)仍为旧句——设计已追平、代码未跟上,存在短暂 code↔design drift。
  commit message 文末「暂缓(item 4)」段**已诚实标注**此 drift(「设计 markdown(553/644)已先行订正,存在
  短暂 code↔design drift」),非静默稀释。方向为「设计领先、代码追平」,符合 AGENTS.md「design = source of
  truth」。
- **对 commit message 一处措辞的核实(物理实证,不采信自报)**:commit message 称该字符串被
  「`lib.rs:3515 assert!(MOIRAI_INTRO_SKILL.contains("不是可用命令"))`」钉死。`git show
  26308bd3:apps/studio/tauri/src/lib.rs` 核对——**在 26308bd3 自身快照上,`lib.rs:3515` 确为
  `assert!(MOIRAI_INTRO_SKILL.contains("不是可用命令"));`**,commit message 对自身时点的描述**准确无误**。
- **独立修复线已推进到 RED 阶段(在 26308bd3 之后,非本审计目标)**:当前 worktree HEAD 实为
  `47e6f95b`(`test(studio): task10 收尾 moirai-intro skill 文案 RED 测试`,2026-07-11 03:09,26308bd3 的
  子提交),它把 `lib.rs:3515-3516` 改写为 `assert!(...contains("ah status --json"))` +
  `assert!(!...contains("不是可用命令"))`。由于生产字符串 `lib.rs:599` 尚未订正,该 moirai 测试在当前 HEAD
  为**故意 RED**(item 4 生产修复的 TDD 红灯,源码可判定;`MOIRAI_INTRO_SKILL` 定义域 586-609 内无
  `ah status --json`、含「不是可用命令」)。**此 RED 属 47e6f95b、归 master 跟踪的独立修复线,不计入
  26308bd3 的裁定**;26308bd3 自身时点是绿的(文档改 + 代码/测试旧态自洽)。

此观察为「诚实标注、非静默」的已知 drift,与 task7 §2 当初记录 design.md:226 跟进项的处置同构;本次 task10
正是闭合 task7 那条跟进项。moirai 生产字符串的收口留给 master 已在跟踪的独立线。

---

## 六、裁定

**✅ ACCEPT** —— 逐条达标:

1. **纯文档、零夹带**:仅 2 个 `.md`,无生产代码/测试/ah.toml/vendor(§二)。
2. **4 处 markdown + design.md:226 逐处忠实**:四值相位语义、events-primary 主决策面、ownership guard +
   只清 `cleanup_required`、`status --json` 读面——均为 task5-9 已验收实现 + `requirements.md`/`design.md`
   权威设计的忠实散文投影,**无「文档比实现更宽」、无遗漏真实约束**(§三、§四)。
3. **design.md:226 的 task7 §2 出处与回滚自检主张,经 review 原文 + 生产代码核对全部属实**;收紧方向在安全轴上
   **更 fail-closed**(由会误杀活栈的 OR 读法收紧为「只按 cleanup_required」),正确闭合 task7 遗留跟进项(§四)。
4. **item 4 暂缓项的 code↔design drift 已诚实标注**,归 master 跟踪的独立修复线(已推进到 47e6f95b RED 阶段),
   不在本审计范围,不影响本单裁定(§五)。

**承接闭合**:`task7-cross-lane-review-2026-07-11.md` §2/§五交办的「task10 设计回写把 design.md:226 收紧」
跟进项,本单已闭合。
