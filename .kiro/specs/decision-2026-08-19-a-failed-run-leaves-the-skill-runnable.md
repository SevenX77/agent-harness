# 决议：跑失败的 run 也是跑完了的 run，技能仍然可以再跑

- 日期：2026-08-19
- 状态：已裁决，随本 PR 落地
- 模块：studio frontend（`apps/studio/frontend`）

## 决策

一次 run **结束**之后——无论成功、失败还是被停止——工具条回到 `predict-pass`：
技能没有任何改变，所以"再按一次 Run"就是它的下一步，不需要重新 Compile + Predict。
失败本身通过失败抽屉呈现（`open-drawer` 效果按 outcome 触发），不由阶段承载。

`run-fail` 这个阶段**删除**。它不再有任何消费者，留着只会让"能不能跑"这件事有两个答案。

## 事实与证据

**设计意图，写在被改的那一行正上方**——
`apps/studio/frontend/src/components/studio/gate-state.ts:73-76`（修改前）：

> A finished run leaves the toolbar on predict-pass: the skill is still
> predict-clean and immediately runnable again, which is the state a human sees
> after their own run completes.

同一张表却把 `fail` 映到 `run-fail`。**测试也已经把这处矛盾钉在里面**：
`gate-state.test.ts` 那条用例的标题是 *"leaves a finished run on predict-pass so it
stays immediately runnable"*，而它的第二条断言期望 `run-fail`——标题和断言互相打架。

**两条规则各说各话（代码，非印象）**：

- `center-action-bar.tsx` 的 `deriveButtons`：只有 `idle`/`compiling`/`compile-fail`
  和 `compile-pass`/`predicting`/`predict-fail` 两组会锁住 Run，其余一律
  `runDisabled: false`。`run-fail` 落在"其余"，于是 **Run 画成可点**。
- `Workspace.tsx:2376` 的 `handleRun`：
  ```ts
  const stage = deriveBuildStage(currentSkillId)
  if (stage !== "predict-pass") {
    return
  }
  ```
  **只接受 `predict-pass`，其它一律静默 return**——没有 toast，没有日志，没有任何反馈。

于是 `run-fail` 是唯一一个"看起来能跑、其实按了没反应"的状态。

**现场（真机，不是推断）**：2026-08-19 在主 app 上跑
`story-deconstruction-v3-lab`，run `2026-08-19T01-56-15_d0733362` 以 failed 收尾。
随后按 Run：CDP 实测 `document.elementFromPoint` 命中的就是那个 Run 按钮本身
（`disabled: false`、`pointerEvents: auto`、`isTheButton: true`），真鼠标事件落在
按钮中心，而 `skill_gate` 事件流里**没有**新的 `run started`，磁盘上也没有新的 run
目录。连点两次，行为一致。

## 关键设计决定

1. **改的是阶段映射，不是给 `handleRun` 放宽条件。** 两处都能让按钮生效，但只有一处
   能消灭"两个答案"。改完之后，**画出可点 Run 的阶段集合与 `handleRun` 接受的阶段集合
   由构造相等**：`running` 渲染 Pause、`paused` 渲染 Resume/Stop，剩下能画出可点 Run 的
   只有 `predict-pass`。放宽 `handleRun` 只会让两份判据继续各自维护，下一个阶段加进来
   时照样漂移。
2. **`run-fail` 直接删掉，不留别名。** 仓规「不向后兼容」：换掉旧设计就在同一个改动里
   删干净旧路径。它此前只出现在三处——类型联合、这张映射表、一条测试断言，没有任何
   分支读它。
3. **失败不会因此被藏起来。** `projectGateEvent` 的 `open-drawer` 效果按
   `outcome === "fail"` 推入，与阶段无关；本 PR 为此新增一条断言把它钉住。

## 验收判据

- RED：`gate-state.test.ts` 修复前给出 `run-fail`，修复后给出 `predict-pass`。
- 不变式：`center-action-bar.test.tsx` 新增用例枚举**全部**阶段（用
  `Record<SkillBuildStage, true>` 做全覆盖，将来加阶段不分类就编译不过），断言画出
  可点 Run 的阶段集合恰好是 `['predict-pass']`。
- 门禁：前端 lint / typecheck / vitest 全套 / build / npm audit 双阈值全绿。
- 真机点验：主 app 上跑一次会失败的 run，失败后再按 Run，必须真的开出新 run。
