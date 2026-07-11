# Task 8 + 9 RED 证据(2026-07-10)

执笔:g2-claude(泳道2 gatekeeper),test-first。本批只写红测试,不写生产代码;
g2-m1-antigravity 接手对着这些测试实现变绿,**不得改动这些测试文件**。

- 任务 8:重做前端事件 payload 为 per-assistant 状态枚举(Rust,`apps/studio/tauri/src/lib.rs`)。
- 任务 9:只读 Detach 控件语义两条(前端,`copilot-panel.test.ts`)。
  其余 starting/degraded 前端投影测试不在本批,留后续。

一句话结论:两条 Rust 测试通过**编译期红**(E0425,同 task2/3/4 手法)、两条前端测试通过
**运行期红**(vitest 真跑断言失败)证成。命令与原样输出见下。

---

## A. 任务 8 — Rust payload(编译期 RED)

新增两条命名测试(函数名照抄 tasks.md:105):

- `test_payload_reports_claude_codex_independently`
- `test_payload_carries_readonly_flag`

位置:`apps/studio/tauri/src/lib.rs` 的 `#[cfg(test)] mod tests`,紧挨既有 payload 投影测试
(`ah_events_status_aggregation_is_display_only` / `opened_config_status_spec_...`)。

### 断言锚点(契约边界,非自指)

两条都断言**序列化后的 wire payload**(`serde_json::to_value(...)`)——即前端经
`app.emit("code-assistant-status-changed", ...)` 实际收到的形状(design.md:290-297):

```
{ claude: { status, reason?, readOnly }, codex: { status, reason?, readOnly } }
```

断言 wire token(`"active"`/`"inactive"`/`readOnly:true|false`),不断言 Rust 内部字段名,
所以 g2-m1 给内部类型改名也躲不掉契约。

- `test_payload_reports_claude_codex_independently`:双活跃 → `claude.status` 与
  `codex.status` 各自 `"active"`,无 claude-wins 抑制(Req 6.2);控制用例(claude 活、codex
  无活跃栈)→ `codex.status` 必须 `"inactive"`,反制"恒 active"作弊,并证明两键恒在。
- `test_payload_carries_readonly_flag`:workspace-owned config → `claude.readOnly:true`;
  Studio-managed temp config → `codex.readOnly:false`。readOnly 由单一所有权权威
  `classify_config_ownership`(task5 的活)供给——测试**引用它**既坐实 payload 走真分类器
  (非本地臆测),又是本批的编译期红缝。消费已冻结 fixture `CONFIG_WORKSPACE_OWNED` /
  `CONFIG_STUDIO_MANAGED`(`ah_contract_fixtures.rs:257-272`,未改动)。

### RED 机器验证(真跑)

```
$ cd apps/studio/tauri
$ RUSTUP_HOME=/root/.rustup CARGO_HOME=/root/.cargo cargo test --lib --no-run
```

原样输出(关键片段):

```
error[E0425]: cannot find function `classify_config_ownership` in this scope
    --> src/lib.rs:4618:13
     |
4618 |             classify_config_ownership(Path::new(CONFIG_WORKSPACE_OWNED.config_path)).read_only,
     |             ^^^^^^^^^^^^^^^^^^^^^^^^^ not found in this scope

error[E0425]: cannot find function `classify_config_ownership` in this scope
    --> src/lib.rs:4623:13
     |
4623 |             classify_config_ownership(Path::new(CONFIG_STUDIO_MANAGED.config_path)).read_only,
     |             ^^^^^^^^^^^^^^^^^^^^^^^^^ not found in this scope

For more information about this error, try `rustc --explain E0425`.
error: could not compile `skill-studio-tauri` (lib test) due to 2 previous errors
```

`classify_config_ownership` 尚不存在 → 整个 lib-test target 无法编译 → 两条测试均不能运行(红)。
这是与 task2(`ah_version_gate`)/task3(`verify_snapshot_identity`)/task4 同一套编译期 RED 手法。

### g2-m1 必须补的生产缝(测试内注释块已声明完整签名)

- `enum AssistantStatus { Inactive, Starting, Active, Degraded, Error }`,
  `#[serde(rename_all="lowercase")]`(序列化成前端 union 的小写 token)。
- `struct AssistantState { status: AssistantStatus, reason: Option<String>, read_only: bool }`,
  camelCase 序列化 → `{status, reason?, readOnly}`,`reason` 用 `skip_serializing_if`。
- `struct CodeAssistantStatus { claude: AssistantState, codex: AssistantState }` —— 直接替换
  旧的 `{claude:bool, codex:bool}`(lib.rs:157-160),不做双格式;两键恒在;保持 `Serialize`。
- 删除 claude-wins 抑制 `if status.claude { status.codex = false; }`(lib.rs:1342-1344)。
- `fn classify_config_ownership(config_path: &Path) -> ConfigOwnership`(task5),
  `struct ConfigOwnership { read_only: bool, .. }`。
- `code_assistant_status_from_snapshots(specs, snapshots)` 保持入参,返回新 payload:逐
  (config, spec) 把 snapshot 映射成 `AssistantState.status`,并带
  `read_only = classify_config_ownership(config).read_only`。

---

## B. 任务 9 — 前端只读 Detach 语义(运行期 RED)

新增两条命名测试(名称照抄 tasks.md:112),追加进既有
`apps/studio/frontend/src/components/copilot/copilot-panel.test.ts`(vitest,不新起框架),
用既有 `subscribeCodeAssistantStatus` mock 按真事件形状投喂 task8 的新 payload:

- `test_readonly_active_close_is_detach`
- `test_readonly_inactive_open_disabled`

### 断言锚点(契约边界,非自指)

断言用户可见的**渲染控件** + **生命周期命令面**:

- `closeCodeAssistant` 就是 `ah stop`/`ah kill` 的下发边界;`openClaudeCode`/`openCodexCli` 就是
  `ah start` 的下发边界。"不发生命周期命令"由这些 mock **从未被调用**证成,不看内部 flag。
- Test A:readOnly + active → 控件呈现 `Detach`(非 Close),点选 Detach 只关本地 tab,
  `closeCodeAssistant` 不被调用(Req 6.4)。
- Test B:readOnly + inactive → `button[aria-label="Open code assistant"]` 存在且 `disabled`,
  DOM 里带只读引导文案(`/read.?only/i`),`openClaudeCode`/`openCodexCli` 均不被调用(Req 6.4)。
  引导文案须落在可及 DOM(按钮 title / 菜单文本),不是 portal-only tooltip。

### RED 机器验证(真跑)

先装依赖(本 worktree 无 node_modules):`npm ci`(added 769 packages)。

```
$ cd apps/studio/frontend
$ npx vitest run src/components/copilot/copilot-panel.test.ts
```

原样输出(关键片段):

```
 FAIL  src/components/copilot/copilot-panel.test.ts > buildCopilotJudgeDraft > test_readonly_active_close_is_detach
AssertionError: expected 'MoirAIMoirAICLI runningAttach Claude …' to contain 'Detach'

Expected: "Detach"
Received: "MoirAIMoirAICLI runningAttach Claude codeAttach CodexClose assistantsAsk about this skill, ...

 FAIL  src/components/copilot/copilot-panel.test.ts > buildCopilotJudgeDraft > test_readonly_inactive_open_disabled
AssertionError: expected null to be truthy
- Expected: true
+ Received: null

 Test Files  1 failed (1)
      Tests  2 failed | 20 passed (22)
```

两条红因证明当前漂移:现前端把 per-assistant 对象当 truthy 布尔用,双只读态被误判为双活跃 →
显示 `Close assistants`(无 Detach 路径)、且 inactive 态也没有可禁用的 Open 控件。既有 20 条测试
照常绿,只有本批 2 条红。`npm run typecheck` 退出码 0(本批红纯属行为红,未引入类型破坏)。

### g2-m1 必须补的生产缝(前端)

- `apps/studio/frontend/src/lib/tauri.ts` 的 `CodeAssistantStatus`(143-146)改成新 per-assistant
  形状(与 task8 wire 一致),直接替换旧 `{claude:boolean, codex:boolean}`,不做双格式。
- `copilot-panel.tsx` 投影/控件:readOnly+active 的 Close 渲染为 Detach 且走本地断开(不发
  `closeCodeAssistant`);readOnly+inactive 的 Open 置灰带引导文案(不发 open 命令)。

---

## C. 交给 master 决策的耦合发现(不在本批擅自扩范围)

task8 是**破坏性 payload 重塑**,会连带失效两处既有旧形状测试与一处生产类型定义。为守住"只做
被指派的两×两条"、不擅自扩范围,本批**未改动**下列既有测试;但 g2-m1 实现 task8 时要把它们迁到
新形状才能整体变绿——这属于"改测试文件",请 master 裁定由我(执笔)迁,还是显式授权 g2-m1 迁:

1. Rust 既有测试 `ah_events_status_aggregation_is_display_only`
   (`apps/studio/tauri/src/lib.rs`,断言旧 `CodeAssistantStatus { claude, codex }` 字面量)—
   payload 重塑后该字面量无法编译,必须迁到新形状断言(其"事件聚合仅供显示、启动窗读作未活跃"
   的语义在新形状下依旧成立,只改断言形状)。
2. 前端既有测试 `copilot-panel.test.ts:272-278`(`derives the close button state...`)与
   `329-334`(`derives attach menu entries...`)——断言旧布尔形状
   (`codeAssistantCloseButtonLabel({ claude: true, codex: false })` 等),类型改后 tsc 会红。
3. `tauri.ts:143-146` `CodeAssistantStatus` 接口本体(生产代码,由 g2-m1 在 task8 直接改,
   不算改测试)。

以上是发现即报,不阻塞本批红测试交付。

**master 裁定(2026-07-10)**:既有测试迁移由 g2-claude(执笔/gatekeeper)做,不下放 g2-m1
(铁律「实施者不得增删改测试文件」无"机械迁移"例外)。迁移已在紧跟 871c3546 的追加 commit 落地,
见下 §D。第 3 项 `tauri.ts` 接口本体仍留给 g2-m1(生产代码,不算改测试)。

---

## D. 既有测试迁移到新 payload 形状(master 裁定后追加,同批)

把 task8 破坏性重塑会连带失效的既有旧形状测试,迁到新 per-assistant 形状,**语义断言不变**,
只改被断言的数据形状。**不动** `tauri.ts:143-146` 接口本体(生产代码,g2-m1 在 task8 改)。

### 迁移清单

1. Rust `ah_events_status_aggregation_is_display_only`(`apps/studio/tauri/src/lib.rs`):
   旧 `assert_eq!(..., CodeAssistantStatus { claude: true, codex: false })` →
   序列化 wire 断言 `v["claude"]["status"]=="active"` / `v["codex"]["status"]=="inactive"`;
   启动窗一段同理断言两者 `"inactive"`。"事件聚合仅供显示、启动窗读作未活跃"语义原样保留。
2. 前端 `copilot-panel.test.ts`「derives the close button state...」与「derives attach menu
   entries...」:旧布尔字面量 `{claude:true,codex:false}` →
   `{claude:{status:'active',readOnly:false},codex:{status:'inactive',readOnly:false}}`
   (readOnly:false=Studio-managed,故 active 控件仍是 'Close …',与只读 Detach 场景解耦)。
   Close-label / attach-label 期望值原样不变。

### 红仍在,且红因是"新生产缝还不存在"(非旧字面量残留、非意外变绿)

- **Rust(提交态,编译期红)**:`cargo test --lib --no-run` 仍只报
  `error[E0425]: cannot find function classify_config_ownership`(2 处)——迁移后的
  `ah_events_...` 已能编译(不再有旧 `{claude,codex}` 字面量类型错误),整个 target 之所以仍
  编译不过,是因为 task8/5 新生产缝 `classify_config_ownership` 还不存在。
- **Rust(临时桩实证,确认不会意外变绿)**:临时给 mod tests 塞一个
  `classify_config_ownership` 桩让 target 能编译后真跑三条(桩用完即撤,提交态无桩):

  ```
  test tests::test_payload_reports_claude_codex_independently ... FAILED
    left: Null   right: "active"     (旧扁平 bool payload 无嵌套 .status)
  test tests::test_payload_carries_readonly_flag ... FAILED
    left: false  right: true         (桩分类器 false，与冻结 workspace-owned=true 不符)
  test tests::ah_events_status_aggregation_is_display_only ... FAILED
    left: Null   right: "active"     (同上，迁移后仍红,未意外变绿)
  test result: FAILED. 0 passed; 3 failed; 160 filtered out
  ```

  证明迁移后的 `ah_events_...` 对**旧未重塑生产代码**仍是真红(序列化后拿不到嵌套
  `.status`),红因确是"新 payload 形状还没实现",不是断言被削弱成恒真。

- **前端(运行期红 + 类型红)**:`npx vitest run …copilot-panel.test.ts` →
  **4 failed | 18 passed**(2 条迁移 + 2 条 task9 新测,均红;其余 18 条既有绿):

  ```
  × derives the close button state from live ahd status
      AssertionError: expected [ 'claude', 'codex' ] to deeply equal []
  × derives attach menu entries from live ahd status
  × test_readonly_active_close_is_detach
  × test_readonly_inactive_open_disabled
  ```

  迁移后 `activeCodeAssistantIds({claude:inactive,codex:inactive})` 在**旧 helper**下把两个
  per-assistant 对象当 truthy → 返回 `['claude','codex']`(期望 `[]`)→ 真红,未意外变绿。
  `npm run typecheck` 现为红(退出码 2),报 `TS2322: Type '{ status; readOnly }' is not
  assignable to type 'boolean'`——即新形状字面量还不匹配旧 `CodeAssistantStatus` 接口,红因同为
  "新生产缝(重塑后的 `tauri.ts` 接口 + helper)还不存在"。g2-m1 在 task8 把接口与 helper 重塑后,
  运行期与类型双绿。

---

## 验证命令汇总(可复跑)

```
# Rust 编译期红
cd apps/studio/tauri
RUSTUP_HOME=/root/.rustup CARGO_HOME=/root/.cargo cargo test --lib --no-run

# 前端运行期红
cd apps/studio/frontend
npm ci    # 若无 node_modules
npx vitest run src/components/copilot/copilot-panel.test.ts
npm run typecheck   # 退出码 0:本批未引入类型破坏
```
