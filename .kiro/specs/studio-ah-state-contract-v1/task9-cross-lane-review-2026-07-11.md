# 跨泳道审计:2a14016b task9 starting/degraded 按钮投影实现

- **审计人**:g1-claude(泳道1 gatekeeper),跨泳道审 g2-claude 实施的生产代码(自审禁忌:本单生产代码由 g2 落地,g1 审)
- **被审 commit**:`2a14016b48e1e251af208378449a4e6d4abdeb7b`
  `feat(studio): task9 starting/degraded 按钮投影实现`
- **红测试 commit(g1 执笔,先行)**:`7ab55ec678292fc2ab231397916106d63c006dd5`
  (`test_starting_disables_buttons` + `test_degraded_exposes_working_open`)
- **契约依据**:tauri.ts `AssistantState` 5 态契约(`inactive | starting | active | degraded | error`,
  `src/lib/tauri.ts:143-147`);task8 per-assistant payload `{ status, reason?, readOnly }`;
  studio-ah-state-contract-v1 task 9(把 header 生命周期控件的投影从「inactive-vs-非inactive 二分」
  收敛到 5 态显式判据,starting 不给可点动作、degraded 露可用 Open)
- **日期**:2026-07-11
- **裁定**:**✅ 通过(ACCEPT)** —— 逐条达标;无遗留跟进项

---

## 一、任务背景

task9 之前,`isAssistantActive` 把 5 态契约压成「`status !== 'inactive'` 即 active」的二分:
`starting` / `degraded` / `error` 全落进 active 分支,header 渲染 Attach/Close(「CLI running」)管理控件。
但按 5 态契约,只有真正 running 的 `active` 才该露出 Attach/Close;`starting`(生成中、尚未就绪,应
hands-off)与 `degraded`(可恢复,应给 cleanup-then-open 的 Open)不该被当作可 attach 的活会话。

g1 先写两个 RED 测试(7ab55ec6)锚定契约边界的**可观测行为**——用户实际看到的那个 header 控件是哪个
(trigger 的 aria-label / disabled)、Attach/Close 动作是不是一个可点击(enabled)的按钮,而非任何内部 flag:
- `test_starting_disables_buttons`:starting 时渲染的控件 disabled,且无任何 enabled 的 Attach/Close;
- `test_degraded_exposes_working_open`:degraded 时露出 `aria-label="Open code assistant"` 且 `disabled=false`
  的可用 Open,并断言 `aria-label="Manage code assistant"` 为 null(不是 Attach/Close,也不是三态全灭)。

g2 对着红测试实现(2a14016b),commit **只动一个文件** `apps/studio/frontend/src/components/copilot/copilot-panel.tsx`
(`+42 / -12`)。

---

## 二、Diff 合规核对(逐条对 brief 七项审计点)

### 1) 2a14016b 只改生产代码,未动 7ab55ec6 两个 RED 测试的断言本体 —— ✅

- `git show 2a14016b --stat`:**单文件** `apps/studio/frontend/src/components/copilot/copilot-panel.tsx`
  (42 insertions / 12 deletions),**无 `.test.ts`、无 `tauri.ts`、无 vendor、无其它文件**;工作树里游离的
  `M ah.toml`、`.operator-report.phase1`、`vendor/` 均未被本 commit 吸入(非 `git add -A`)。
- 因本 commit 未触碰 `copilot-panel.test.ts`,两个 RED 测试(`test_starting_disables_buttons`、
  `test_degraded_exposes_working_open`)的 fixture 与全部 `expect(...)` 断言相对 7ab55ec6 **逐字节未动**,
  未被实现悄改迁就。

### 2) starting 真正 disabled / hands-off(不给任何可点的生命周期动作)—— ✅

- `isAssistantActive`(copilot-panel.tsx:306-318)改成对 `getAssistantStatus` 的显式 switch:`starting` 归
  `return false`。于是 `activeCodeAssistantIds`(:338-343)不含 starting,`codeAssistantCloseButtonLabel`
  (:345-357)返回 `null` → header 落进 **Open 分支**(:796-833),而非 Attach/Close(「CLI running」)分支。
- 新增 `isAssistantStarting`(:322-324)+ `isAnyCodeAssistantStarting`(:548-549),并把它接进 Open trigger 的
  `disabled` 表达式(:803):`disabled={openingCodeAssistant !== null || !codeAssistantWorkspace ||
  allReadOnlyInactive || isAnyCodeAssistantStarting}`。starting 时 `isAnyCodeAssistantStarting=true` →
  Open trigger `disabled=true`,其下拉的生命周期项(Claude code / Codex)因 trigger 禁用而不可达 = hands-off。
- 契合测试:控件 `aria-label="Open code assistant"` 存在且 `disabled=true`;全页无 enabled 且文本含 `Attach|Close`
  的按钮(Open 分支的可见文案是「Open in CLI」/「Claude code」/「Codex」,无 Attach/Close)。

### 3) degraded 真正露出可用 Open(aria-label 含 "Open",disabled=false),不是 Attach/Close、不是三态全灭 —— ✅

- `degraded` 在 switch 里同归 `return false`(:311-314)→ `codeAssistantCloseButtonLabel` 返回 `null` →
  渲染 **Open 分支**,`aria-label="Manage code assistant"` 的 Attach/Close 触发器根本不渲染(测试断言其为 null,成立)。
- degraded 非 `starting` → `isAnyCodeAssistantStarting=false`;degraded 非 `inactive` → `isClaudeOpenDisabled`
  /`isCodexOpenDisabled`(:543-544)为 false → `allReadOnlyInactive=false`。测试的 `workspaceRoot` 非空 →
  `codeAssistantWorkspace` 真,`openingCodeAssistant` 默认 null。故 Open trigger `disabled=false` = 可用(可点),
  一步即可 cleanup-then-open,不是三态全灭的 stub。

### 4) active / inactive 现有行为保持不变(未被本次改动意外破坏)—— ✅

- `active` → switch 命中 `case 'active': return true`;`inactive` → `case 'inactive': return false`。与改动前
  (`status !== 'inactive'`:active→true、inactive→false)**结果完全一致**。
- 逐态对比(改动前 `!== 'inactive'` vs 改动后 switch):active `true→true`、inactive `false→false`、
  **error `true→true`(改动 message 明确保留既有 running-control 映射,task9 范围外不发挥)**;仅
  `starting`(`true→false`)、`degraded`(`true→false`)行为改变——**恰是 task9 目标,零附带破坏**。
- boolean legacy 形状亦不变:`getAssistantStatus(true)='active'`→`isAssistantActive` true;`false`→false,
  与改动前 boolean 直返一致。

### 5) readOnly 驱动的 Detach / 置灰逻辑原样保留,未被本次改动波及 —— ✅

- **Detach 分支**(`codeAssistantCloseButtonLabel`:350-352,`active.every(id => isAssistantReadOnly(...)) →
  'Detach'`)在 diff 中**完全未触碰**,原样保留。
- **置灰三行**(改动前 517-519 → 现 543-545):`isClaudeOpenDisabled` / `isCodexOpenDisabled` /
  `allReadOnlyInactive` 的定义在 diff hunk `@@ -517,6 +543,10 @@` 中作为**上下文行(未加未删)**呈现,
  新增的 `isAnyCodeAssistantStarting`(+4 行)追加在这三行**之后**,不改其一字。
- `isAssistantReadOnly`(:326-331)仅把签名 `state: any` 收敛为 `AssistantStateInput`,函数体
  (`if (state && typeof state === 'object') return !!state.readOnly; return false`)**逐字节不变**。
- Open 下拉项的 readOnly 置灰(`isClaudeOpenDisabled` / `isCodexOpenDisabled` 门控 :815/:824 + read-only 文案
  :821/:830 + title :819/:828)均在 diff 之外,原样保留。

### 6) status 判据 helper 从 `state: any` 收敛成显式联合类型 —— 只是类型收紧,无行为变化 —— ✅

- **坐实「消掉 3 处 no-explicit-any」**:`git show 7ab55ec6:./...copilot-panel.tsx | grep -c 'function
  (isAssistantActive|isAssistantReadOnly|getAssistantStatus)\(state: any\)'` = **3**;当前文件
  `grep 'state: any'` = **0**;新增的 `isAssistantStarting` 也用 `AssistantStateInput`,未新增任何 `any`。
- **新类型**:`type AssistantStateInput = AssistantState | boolean | null | undefined`(:290)——boolean 为
  ahd-events 回归路径仍在用的 legacy 形状,联合类型如实覆盖两种输入,非放宽。
- **行为不变的两处**:`getAssistantStatus`(:292-297)与 `isAssistantReadOnly`(:326-331)函数体相对改动前
  **逐字节一致**,仅换签名类型;boolean 与 object 两条支路的返回值全部保持。**唯一**有行为变化的是
  `isAssistantActive`,且其变化已在第 2/3/4 点确认恰为 task9 目标(starting/degraded 由 true→false),
  active/inactive/error/boolean 全部结果不变。
- **lint 佐证**:`npx eslint src/components/copilot/copilot-panel.tsx` → exit 0(干净,无新 any / 无新告警)。

### 7) 实机重跑(不信 commit message 数字)—— ✅ 24 passed

```
cd apps/studio/frontend
npm test -- src/components/copilot/copilot-panel.test.ts
```

结果:**Test Files 1 passed / Tests 24 passed(24)** —— 既有 22 + 新增 2,与 commit message 数字一致,亲跑坐实。

---

## 三、回滚自检(锚定硬项实操,证明测试穿过本次 diff、非空转)

临时把本次 diff 的**核心改动**回滚——`isAssistantActive` 从 5 态显式 switch 退回改动前的二分
(`return getAssistantStatus(state) !== 'inactive'`)——重跑测试文件:

```
❯ src/components/copilot/copilot-panel.test.ts (24 tests | 2 failed)
  × test_starting_disables_buttons
  × test_degraded_exposes_working_open
 Tests  2 failed | 22 passed (24)
```

- **恰好且仅有**两个新测试变红(其余 22 个既有测试全绿):退回二分后,starting/degraded 重新落进 active 分支
  渲染 Attach/Close(「Manage code assistant」)——`test_starting` 因 Manage 触发器 `disabled=false`(其禁用
  条件不含 starting)而红在「控件应 disabled」;`test_degraded` 因 Open 触发器根本不存在(`querySelector
  ('button[aria-label="Open code assistant"]')` 返回 null)而红在 `expect(openButton).toBeTruthy()`。
- 证明两个新测试真穿过本次 diff 的 `isAssistantActive` 5 态判据核心逻辑,断言锚在契约边界的可观测控件上,
  非空转在别处已改好的代码上。
- `git checkout -- ...copilot-panel.tsx` 复原后:该文件相对 HEAD **零 diff**;重跑 **24 passed**,树净。
  回滚自检闭合,未污染被审树。

---

## 四、裁定

**✅ ACCEPT** —— 按泳道 TDD 契约,被审实施的验收线是「正确变绿红测试,且不改测试 / 不绕护栏 /
不稀释契约 / 不越 scope」。2a14016b 逐条达标:

- 只改生产代码单文件 `copilot-panel.tsx`,两个 RED 测试的 fixture+断言逐字节未动,未碰 tauri.ts/ah.toml/vendor(§1);
- starting 真正 hands-off:落 Open 分支且 trigger 被 `isAnyCodeAssistantStarting` 禁用,无 enabled 的 Attach/Close(§2);
- degraded 露出可用 Open(`aria-label="Open code assistant"`、`disabled=false`),Manage 触发器不渲染,非三态全灭(§3);
- active/inactive/error 与 boolean legacy 形状行为**逐态一致**,唯一行为变化即 starting/degraded 由 true→false 的 task9 目标(§4);
- readOnly 驱动的 Detach 分支与置灰三行原样保留、`isAssistantReadOnly` 函数体逐字节不变,新增 const 追加在其后不改一字(§5);
- 3 处 `state: any` 收敛为 `AssistantStateInput` 联合、零新增 any、eslint exit 0,`getAssistantStatus`/`isAssistantReadOnly`
  函数体逐字节不变,是纯类型收紧无行为漂移(§6);
- 实机重跑 24 passed(既有 22 + 新增 2),与 commit message 一致(§7);
- 回滚自检证明两个新测试穿过本次 diff 的 5 态判据核心逻辑、非空转,复原后回绿树净(§三)。

**承接闭合**:studio-ah-state-contract-v1 task9「starting/degraded 按钮投影」本单已闭合;header 生命周期控件的
投影从「inactive-vs-非inactive 二分」正式收敛到 5 态显式判据,starting hands-off、degraded 给可用 Open。

**遗留跟进项**:无。
