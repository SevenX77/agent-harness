# PR492 合并冲突消解报告 — origin/main(#491 studio-moirai-agent-system)→ feat/studio-ah-state-contract-impl

- **日期**:2026-07-11
- **执笔**:泳道1 gatekeeper(g1)
- **裁决来源**:master(3 处冲突逐一裁决;第 4 处经 `.lane-question` Q1 授权)
- **merge commit**:`2d3e20dc730246d24848d1bfa323590adbf7c3bf`
  - 双亲:`c56967ff`(HEAD, feat/studio-ah-state-contract-impl) + `ffeff566`(origin/main）

## 1. 背景

两条 spec 在 `apps/studio/tauri/src/lib.rs` 撞车:

- **本 spec(studio-ah-state-contract-v1)**:把 Studio 的 ah 状态检测从「两布尔猜测」换成「四值 `runtime_state` 结构化合约」(task3-9,已全部验收)。
- **origin/main(#491 studio-moirai-agent-system)**:把 MoirAI 技能/角色文本从「内联 const 字符串」换成「随包资产目录加载」(`studio_agents_dir()`)。

两者互不矛盾,消解 = 各留其一、删掉真正被淘汰的部分。

### 本次合并纳入的 origin/main 提交(`c56967ff..ffeff566`,共 4 个)

```
ffeff566 feat: MoirAI agent system — four-layer packaged assets, native subagents, code-enforced tool boundaries (#491)
624fb9c9 docs(.ah): three stack-revival recipes from 2026-07-11 credential incident (#490)
03e454f5 docs(.ah): ps returns empty table under pinned AH_STATE_DIR — per-subcommand invocation caveat (#489)
be634c02 docs: add studio-moirai-agent-system kiro spec v4 (requirements/design/tasks/research) (#488)
```

git 自动合并 61 处改动(43 新增 + 8 删除 + 10 修改,全为 moirai spec 的 Python/前端/文档/资产文件),仅 `apps/studio/tauri/src/lib.rs` 需人工消解。

## 2. 四处冲突的最终结果

### 冲突 1(旧 lib.rs:484-535)— 取 HEAD 侧(整体删除)

删除无调用点的三布尔旧生命周期模型:`AhRuntimeEventLine` / `lifecycle_snapshot_from_ah_event` / `decide_code_assistant_open`(注意:非 `_v2`)。

**gatekeeper 独立复核**:这三个符号在合并树里**无任何代码调用点**——`grep` 全量仅剩注释提及名字(lib.rs:3327/4711/4736/4739 均为注释文本);活跃决策面是 `decide_code_assistant_open_v2`(2591 调用 + 大量测试)。本 spec task6.1(432bad03)已把真实入口切到 typed 决策面(`resolve_open_snapshot` / `decide_code_assistant_open_v2` / `parse_ah_runtime_snapshot`)。按「无向后兼容」铁律删除死路径。✅

### 冲突 2(旧 lib.rs:566-698)— 取 origin/main 侧

删除全部内联 skill const(`MOIRAI_MASTER_RULES` / `CLOTHO_RULES` / `LACHESIS_RULES` / `ATROPOS_RULES` / `MOIRAI_INTRO_SKILL` / `EVAL_JUDGEMENT_SKILL`)+ `struct StudioAhManagedFile`;保留 `register_studio_resource_root`。

**gatekeeper 独立复核**:
- 内联 const 仅在被删块内定义;老消费者 `STUDIO_AH_MANAGED_FILES` 在合并树里 **零出现**(已被 moirai 改动合掉,`prepare_studio_ah_workspace` 已重写为走 `studio_agents_dir()`)。
- `register_studio_resource_root` 在 lib.rs:3087 有真实调用,必须保留。
- 资产文件 `apps/studio/backend/app/agents/skills/moirai-intro/SKILL.md` 含 `name: moirai-intro`(第2行)+ `ah ps`(第19行),**不含**「不是可用命令」假话。本 spec task10 对 moirai-intro 文案的订正无需迁移——moirai spec 自己的表面中立设计(design.md R5.4)已取代。✅

### 冲突 3(旧 lib.rs:3742-3761)— 取 origin/main 侧

`moirai_launch_prompt_triggers_intro_skill_without_scripted_answer` 测试断言:删除锚定已删常量 `MOIRAI_INTRO_SKILL` 的 HEAD 版本,保留从真实资产文件 `studio_agents_dir()/skills/moirai-intro/SKILL.md` 读取并断言的 origin/main 版本。HEAD 版本锚的常量已被冲突 2 删除,留之则编译不过;origin/main 版本锚在真实产物,是正确验收锚点。✅

### 冲突 4(lib.rs:5072 / 5354)— git 未标记的语义 mis-merge,经 `.lane-question` Q1 授权

**性质**:git 无文本冲突地合并、却产出编译不过的语义冲突,`cargo build --lib` 不报(测试不编译),仅 `cargo test --lib` 暴露:

```
error[E0277]: the trait bound `Result<String, String>: AsRef<[u8]>` is not satisfied
  --> src/lib.rs:5072:13   (test: test_lifecycle_only_on_studio_managed_config)
  --> src/lib.rs:5354:13   (test: test_quit_leaves_workspace_owned_config_untouched)
```

**根因(git 双亲对比查实)**:

| | HEAD(本分支) | origin/main(#491) |
|---|---|---|
| `fn transient_ah_config_content` 返回类型 | `-> String` | `-> Result<String, String>` |
| 上述 2 个测试 | 把返回值原样塞给 `fs::write`(`String: AsRef<[u8]>` 合法) | 不存在这 2 个测试 |

本分支从未改签名行(相对 merge-base 保持 `String`),origin/main 改成 `Result`。git 三方合并因此**无文本冲突地**取了 origin/main 的 `Result` 签名,又**无文本冲突地**保留本分支这 2 个假设 `String` 的测试 → 语义打架。

**修法(唯一解)**:`Result` 签名已在 main(canonical 真相),按「无向后兼容 / main=真相」铁律,本分支这 2 个测试**只能适配**——补 `.expect("transient claude ah config")`,与同文件 5 处兄弟站点(lib.rs:3576/3624/3703/4701/5461)既有写法完全一致。无第二种改法。

gatekeeper 未擅自落地:此为跨泳道(moirai 签名 × 本泳道测试)+ 超出 master 授权的 3 处裁决,落 `.lane-question` 升级;master 经 Q1 授权后落地。✅

## 3. 编译 / 测试验证

### `cargo build --lib` — 通过

```
warning: `skill-studio-tauri` (lib) generated 10 warnings
    Finished `dev` profile [unoptimized + debuginfo] target(s) in 7.22s
```

10 条 `never used` 警告全部是 `#[cfg(test)]`-only 辅助函数(`tmux_socket_label_is_safe` / `extract_tmux_socket_label` / `extract_ah_session_ids` / `ah_ps_output_has_inventory` / `SequenceArbiter`)在无测试的 `--lib` 构建下的正常产物——已 grep 逐一核实其调用点全在测试模块(lib.rs:5393/5397/5416/4183/… ),非本次消解引入,非死代码。

### `cargo test --lib -- --test-threads=1`(串行)— 166 passed / 1 failed

```
failures:
    native_fs::tests::publish_package_writer_maps_permission_error

test result: FAILED. 166 passed; 1 failed; 0 ignored; 0 measured; 0 filtered out; finished in 0.37s
```

唯一失败 `native_fs::tests::publish_package_writer_maps_permission_error` = master 已声明的 root 沙箱既有假象(root 绕过文件权限,只读父目录不产生 permission error),与本次改动无关。

关键测试均通过(逐名核实):

- 本 spec 合约夹具:`ah_contract_fixtures::self_validation::{starting_snapshot_is_hands_off, degraded_snapshot_matches_req_3_7_recorded_shape, config_ownership_fixtures_split_read_only_correctly, sequence_stream_advances_then_reset_returns_to_one, active_snapshot_reports_live_fleet_across_providers, …}` ✅
- typed 决策面:`test_decision_plane_consumes_typed_snapshot_not_ps_text` / `test_typed_snapshot_parser_projects_phase_sessions_and_health` / `test_starting_is_hands_off` / `test_degraded_exposes_working_open` / `test_sequence_guard_within_stream` / `test_sequence_reset_on_reason_initial` ✅
- 冲突 4 两站点:`test_lifecycle_only_on_studio_managed_config` / `test_quit_leaves_workspace_owned_config_untouched` ✅
- moirai 侧:`transient_ah_config_starts_moirai_team` / `moirai_launch_prompt_triggers_intro_skill_without_scripted_answer`(冲突 3) ✅

### 已知非阻断项:并行下的偶发 flaky(非本次合并引入)

默认多线程 `cargo test --lib` 下,`sidecar::tests::allocate_loopback_port_honors_pinned_env` **偶发**失败(`left: 46593, right: 49317`)。

- **根因**:`sidecar.rs` 测试模块 3 个测试(`returns_bindable_dynamic_port` / `honors_pinned_env` / `falls_back_on_invalid_env`)都无同步地读写 **process-global** 环境变量 `STUDIO_SIDECAR_PORT`;cargo 并行执行 → `honors_pinned_env` 的 `set_var(49317)` 与其读取之间被其它测试的 `remove_var`/`set_var` 插入 → 读到随机 OS 端口而非 pinned 值。
- **证据**:同一份代码「通过→失败」= 非确定性 = flaky;`--test-threads=1` 串行下**稳定消失**(见上 166/1);`git diff HEAD MERGE_HEAD -- sidecar.rs` **为空**(两侧字节一致)= 本次合并未触碰,是既有 flaky,非回归。
- **建议(超出本合并任务范围,留给 PM/master)**:该测试模块应给 env 读写加互斥或改用 `#[serial]`,消除 CI 并行下的偶发红。本次合并不修(不在 scope,合并未触碰 sidecar.rs)。

## 4. 边界遵守

全程未碰:`ah.toml`(master stash 中)/ `.operator-report.phase1` / `.operator-report.phase2` / `apps/studio/tauri/vendor/` —— 合并后仍为游离未追踪状态,未被吸入 merge commit(`git show --stat 2d3e20dc` 已核实无泄漏)。除 lib.rs 4 处消解外,未改动任何其它已合并文件内容。未使用 `git add -A`。前端门禁按分工由 master 另验,未跑。
