# 跨泳道审计:af0833d1 task6 Open/Attach 决策覆盖 starting/degraded 相位

- **审计人**:g1-claude(泳道1 gatekeeper),跨泳道审 g2-claude 实施的生产代码
- **被审 commit**:`af0833d1ad37ffea1e142768553530ca57fe1e31`
  `feat(studio): task6 reconcile_snapshot_lifecycle 覆盖 starting/degraded 相位`
- **红测试 commit(g1 执笔,先行,非本会话实例)**:`36d49b01e83a5c37021a8bd71301f18a19561c74`
  (`test_starting_is_hands_off` + `test_degraded_exposes_working_open`)
- **spec 依据**:tasks.md task 6(重做 Open/Attach 决策,覆盖 starting/degraded);requirements Req 3.6 / 3.7 / 5.6 / 5.7
- **日期**:2026-07-10
- **裁定**:**✅ 通过(ACCEPT)** — 附一项承重 scope 提示(§五),须 master 裁量后续接线任务

---

## 一、任务背景

task 6(tasks.md:120-131)把 Open/Attach 决策从「只看 `active` 布尔」升级到「按
`runtime_state` 全相位集」——重点补齐此前未覆盖的 `starting`(hands-off)与
`degraded`(cleanup-then-start,Open 可用)两相位。g1 先写两个红测试锚定 **typed 决策面**:

- `reconcile_snapshot_lifecycle(&AhRuntimeSnapshot)`(任务 3/4 引入的 typed 缝),
- 新的相位→UI 状态投影缝 `assistant_status_for_runtime_state(AhRuntimeState)`。

g2 对着红测试实现,commit 只动一个文件 `apps/studio/tauri/src/lib.rs`(`+38 / -4`)。

---

## 二、Diff 合规核对(逐条对 brief 五项审计点)

### 1) af0833d1 只改生产代码,未动 36d49b01 的两个测试断言 —— ✅

- `#[cfg(test)] mod tests` 起于 **lib.rs:3413-3414**。af0833d1 的三处 hunk 全部落在其**之上**:
  - lib.rs:466-467(`CodeAssistantLifecycleAction` 新增 `HandsOff` 变体);
  - lib.rs:2648-2653(`attach_code_assistant_terminal` 穷尽 match 补 `HandsOff` 臂);
  - lib.rs:3260-3290(`reconcile_snapshot_lifecycle` 改写 + 新增 `assistant_status_for_runtime_state`)。
- 两个被审测试位于 lib.rs:4346-4428(由 36d49b01 加在测试模块内)。`git show af0833d1`
  的 diff 在该区间**零改动**——测试断言本体原样保留,未被实现悄悄改写迁就。
- `git show af0833d1 --stat`:单文件 `apps/studio/tauri/src/lib.rs`,`38 insertions / 4 deletions`,
  **无 `ah.toml`、无 vendor、无测试文件**;非 `git add -A`(工作树里游离的 `ah.toml`
  改动、`.operator-report.phase1`、`vendor/` 均未被本 commit 吸入)。

### 2) starting 相位是否真正 hands-off(不发 StartFresh/CleanupStale,不重复 ah start)—— ✅(在红测试锚定的 typed 缝层面)

`reconcile_snapshot_lifecycle`(lib.rs:3272-3278)按相位穷尽分派:

```rust
match snapshot.runtime_state {
    AhRuntimeState::Active    => CodeAssistantLifecycleAction::AttachExisting,
    AhRuntimeState::Inactive  => CodeAssistantLifecycleAction::StartFresh,
    AhRuntimeState::Starting  => CodeAssistantLifecycleAction::HandsOff,   // ← Req 3.6
    AhRuntimeState::Degraded  => CodeAssistantLifecycleAction::CleanupStale,
}
```

- `Starting → HandsOff`(lib.rs:3276):`HandsOff` 是**独立的「无动作」出口**(枚举第四变体,
  lib.rs:463-468),既非 `StartFresh`(不重复 `ah start`)、非 `CleanupStale`(不清理)、
  亦非 `AttachExisting`(不附着)。合 Req 3.6「shall not run cleanup / shall not start a
  duplicate / shall not report an error」。
- UI 投影:`assistant_status_for_runtime_state(Starting) => AssistantStatus::Starting`
  (lib.rs:3289),序列化 wire tag 为 `"starting"`——非 `error`、非 `degraded`。合 Req 5.6。
- 对旧规则的对照:原实现只看 `snapshot.active`,把每个非 active 相位**塌成 `StartFresh`**——
  starting 会误发重复 `ah start`(违 Req 3.6)。新分派消除了这一塌陷,方向正确、更保守。

### 3) degraded 相位是否真正走 cleanup-then-start,Open 可用不三态全灭 —— ✅(在 typed 缝层面)

- `Degraded → CleanupStale`(lib.rs:3277)。在 Open 流程里 `CleanupStale` 决策被解析为
  「先清理再 StartFresh」:`prepare_code_assistant_open` 的
  `CodeAssistantOpenDecision::CleanupStale` 臂(lib.rs:2593-2596)
  `cleanup_workspace_code_assistants(...)?` 后返回 `StartFresh`——Open 保持可用,
  不是 Req 3.7 之前措辞导致的「三个按钮全灭」死锁。合 Req 3.7 / 5.7。

### 4) 任务 5 所有权护栏 `ensure_lifecycle_command_allowed` 在 StartFresh 路径原样保留、未被绕过 —— ✅

- `open_code_assistant` 的 `StartFresh` 臂(lib.rs:2614-2622)仍在**发子进程之前**
  第一步调 `ensure_lifecycle_command_allowed(&config_path)?`(lib.rs:2616),`?` 直接短路——
  之后才 `write_code_assistant_launcher_script` + `spawn_terminal_with_launcher`。
- af0833d1 的三处 hunk(466 / 2648 / 3260 区间)**均未触及** lib.rs:2614-2622 这段;
  护栏原样,未被绕过、未被削弱。清理路径的护栏
  (`force_cleanup_ah_runtime` lib.rs:1194)同样未被本 commit 触碰。

### 5) 新增 `HandsOff` 第四变体是否漏接到其它穷尽 match / 被 `_ =>` 悄悄吞掉 —— ✅

- 全仓对 `CodeAssistantLifecycleAction` 的**唯一穷尽 `match`** 在
  `attach_code_assistant_terminal`(lib.rs:2636-2653),四臂**逐一显式列出**,
  `HandsOff` 臂(lib.rs:2648-2653)给出「仍在启动,先等启动完成再 attach」诊断,
  **无 `_ =>` 通配**。
- 全文件唯一的 `_ =>`(lib.rs:439)属 `CodeAssistant` 字符串解析(`unknown code assistant`)——
  **另一个类型**,与本枚举无关,不构成吞并。
- `reconcile_snapshot_lifecycle`(3272)与 `assistant_status_for_runtime_state`(3285)
  是对 `AhRuntimeState`(4 变体)的穷尽 match,亦无通配。
- `decide_code_assistant_open`(lib.rs:534-566)用 `==` 比较而非 `match`,且其 action
  仅来自旧决策面 `reconcile_code_assistant_lifecycle`(该面永不产出 `HandsOff`),
  当前运行期不会有 `HandsOff` 流经此处被静默吞掉(见 §五:此处待 typed 面接线时须补 HandsOff)。
- 佐证:`cargo test --lib` **编译通过(exit 0)**——若任一穷尽 match 漏 `HandsOff`,
  Rust 编译期即会红,不可能出库。

---

## 三、独立重跑验证(brief 第 6 项,g1 自跑不信 commit message 数字)

```
cd apps/studio/tauri
RUSTUP_HOME=/root/.rustup CARGO_HOME=/root/.cargo cargo test --lib
```

结果:**166 passed;1 failed**。

- 唯一失败:`native_fs::tests::publish_package_writer_maps_permission_error`
  (panic 于 `src/native_fs.rs:1947`,"read-only parent maps to permission")——
  本沙箱 **root 环境既有失败**(root 可写只读父目录,权限断言不成立),
  与本改动无关,是 brief 明确允许的例外。
- **失败集合未变**:`failures:` 块只列这一项,无新增红。计数与先例自洽——task5 审计时为
  164 passed;task6 加了 2 个测试(36d49b01)→ 164 + 2 = **166 passed**,failed 恒为 1 项同一 native_fs。
- 两个 task-6 测试单独按名重跑均绿:
  ```
  test tests::test_degraded_exposes_working_open ... ok
  test tests::test_starting_is_hands_off ... ok
  test result: ok. 2 passed; 0 failed; ... 165 filtered out
  ```

---

## 四、回滚自检(锚定硬项实操,证明测试穿过本次 diff)

临时把 `reconcile_snapshot_lifecycle`(lib.rs:3273-3278)的相位分派**退回旧的只看 `active`
规则**(`if snapshot.active { AttachExisting } else { StartFresh }`),重跑两测试:

```
test tests::test_starting_is_hands_off ... FAILED
  assertion `left != right` failed: starting must NOT start a duplicate runtime (Req 3.6: 'shall not start a duplicate')   [lib.rs:4361]
test tests::test_degraded_exposes_working_open ... FAILED
  assertion `left == right` failed: degraded must expose a working cleanup-then-start Open path, not zero actions (Req 3.7/5.7)  [lib.rs:4425]
test result: FAILED. 0 passed; 2 failed
```

两测试**双双变红**,且红在正是 Req 3.6 / 3.7 的断言上——证明它们真穿过本次 diff 的核心改动,
非空转(未锚在别处已修好的代码上)。`git checkout -- lib.rs` 复原后:

- 该文件相对 HEAD **零 diff**(`git diff --stat HEAD` 空);
- 两测试**回绿**(`test result: ok. 2 passed; 0 failed`)。

回滚自检闭合,未污染被审树。

---

## 五、⚠️ 承重 scope 提示(非本 commit 缺陷,须 master 裁量)

**本次改的 typed 决策面尚未接入生产 Open/Attach/Close 活路径——它当前只被测试消费。**
物理实证(按 `mod tests` 起点 3413 区分 PROD/test 引用):

- `reconcile_snapshot_lifecycle`(lib.rs:3272)与 `assistant_status_for_runtime_state`
  (lib.rs:3285)两个函数,**生产侧零调用点**;全部实际调用都在测试模块内(4157 / 4360 / 4380 / 4426)。
- 生产 Open/Attach 活路径(`prepare_code_assistant_open` lib.rs:2543、
  `attach_code_assistant_terminal` lib.rs:2626)仍走**旧决策面**
  `reconcile_code_assistant_lifecycle(AhLifecycleSnapshot)`(lib.rs:501-512),
  而 `AhLifecycleSnapshot` 由 `inspect_ah_runtime`(lib.rs:1157-1191)**解析 `ah ps` 文本 +
  探测 tmux** 派生,**不含 `runtime_state` 相位**——旧面根本感知不到 `starting`/`degraded`。

由此得出两条须如实上报的真相:

1. **端到端未闭合**:在 shipping UI 的活路径上,真实的 `starting`/`degraded` 运行时
   **尚未按 Req 3.6/3.7 生效**——typed 缝已正确,但还没被任何活入口读到。commit message
   「现在 starting 真正 hands-off、degraded 真正走 cleanup-then-start」在**红测试锚定的缝层面**
   属实,但**在活 UI 层面被夸大**;严格说应是「typed 决策面已覆盖两相位,接线到活路径待后续」。
2. **该 gap 是既有条件,非 task6 引入**:整条 typed 面(task 3/4 的 parse + reconcile,task 8
   的 payload 缝)都是「先建缝、测试锚定、后接线」的增量策略;`inspect_ah_runtime` 仍解析
   `ah ps` 文本(Req 2.4 明令禁止用于 normal decision),这一状态在 task6 之前就存在。
   36d49b01 的红测试(前一 g1 实例执笔)**刻意**锚定 typed 缝(测试注释明确引用 task-3/4 的
   `test_decision_plane_consumes_typed_snapshot_not_ps_text` 为先例),故「接线」不在 task6 的
   红测试契约内。tasks 3/4/8 均以同一「seam-first」基准被验收通过,若因此拒收 task6 则与既有
   验收标准自相矛盾。

**给 master 的建议**:确认后续存在一个「切换活路径消费 typed 面、退役 `inspect_ah_runtime`
的 `ah ps` 文本解析(Req 2.4)、并给 `decide_code_assistant_open` 的 `==` 比较补 `HandsOff`
分支」的接线任务(task 9 或专门的 cutover 单)。task6 的实现本身不含该职责——除非 master
判定 task6 的 spec 正文(「Open 前读取 selected config 的当前快照 …」)本就要求本单一并完成
接线,那属红测试 scope 不足(g1 测试执笔侧),按泳道纪律不归被审实施方担责。

---

## 六、裁定

**✅ ACCEPT** —— 按泳道 TDD 契约,被审实施的验收线是「正确变绿红测试,且不改测试 / 不绕护栏 /
不稀释 spec / 不越 scope」。af0833d1 逐条达标:

- 只改生产代码,未碰 36d49b01 两测试断言,未碰 ah.toml/vendor,单文件提交;
- `starting → HandsOff`、`degraded → CleanupStale` 在 typed 缝上正确落地(Req 3.6/3.7/5.6/5.7),
  比旧「非 active 一律 StartFresh」更保守,无 fail-closed 稀释;
- 任务 5 所有权护栏在 StartFresh 路径原样保留、未绕过;
- `HandsOff` 第四变体正确接入唯一穷尽 match(无 `_ =>` 吞并),编译通过即证全穷尽 match 已覆盖;
- 独立重跑 166 passed / 1 failed(唯一失败为既有 root 环境 native_fs 例外,失败集合未变);
- 回滚自检证明两测试各自穿过本次 diff 核心改动、非空转,复原后回绿树净。

**唯一附带项**(§五)是承重 scope 提示而非缺陷:typed 决策面尚未接入活路径,端到端 Req 3.6/3.7
在 shipping UI 未闭合;此为既有 seam-first 条件、不在 task6 红测试契约内,须 master 裁量后续接线单。
