# PR492 合并跨泳道审计报告 — origin/main(#491 studio-moirai-agent-system)→ feat/studio-ah-state-contract-impl

- **日期**:2026-07-11
- **执笔**:泳道2 gatekeeper(g2)——独立跨泳道审计
- **被审对象**:g1 执笔、master 裁决的 4 处合并冲突消解(merge commit `2d3e20dc` + 报告 `e146cd45` + 追记 `43a885a6`)
- **审计原则**:不采信任何 commit message / 报告自报;所有结论均由 g2 自己跑命令、读代码、做 git 考古独立坐实
- **审计边界**:只读审计 + 独立重跑,未改任何现有代码/测试/报告文件;未碰 `ah.toml` / `.operator-report*` / `vendor/`
- **HEAD**:`43a885a6309ba7535304ee758949c9699cf52f5f`
- **merge-base**(双亲共同祖先):`880164ad`;双亲 = `c56967ff`(本分支)+ `ffeff566`(origin/main)

---

## 总裁定:**ACCEPT**

四处冲突消解全部技术正确;冲突4的 master Q1 追认在纯技术层面独立复核**站得住**,g2 无异议。唯一非阻断项(root 沙箱假象)与本次合并无关,与既有结论一致。

---

## 冲突 1 — 删除三布尔旧生命周期模型 · **ACCEPT**

**核实结论**:三个旧符号在合并树里**已彻底删除,无任何真实调用点**,仅剩注释提及。

独立证据(`grep -n` on `apps/studio/tauri/src/lib.rs`):

- `AhRuntimeEventLine` → 0 命中
- `lifecycle_snapshot_from_ah_event` → 0 命中
- `decide_code_assistant_open`(词边界、排除 `_v2`,`grep -nE "decide_code_assistant_open\b"`)→ 仅 4 处,**全是注释/字符串**:
  - `lib.rs:3144` 注释:`Replaces the deleted boolean` decide_code_assistant_open``
  - `lib.rs:4520` / `4545` / `4548` 注释与测试说明文本,引用旧名做对照说明,非调用
- 活跃决策面 `decide_code_assistant_open_v2` → **17 处**命中(生产调用 + 大量测试),是真实入口。

判定:按「无向后兼容」铁律删死路径,正确。✅

---

## 冲突 2 — 内联 moirai const 让位于随包资产目录加载 · **ACCEPT**

**核实结论**:内联 const / struct / 旧数组**全删**;`register_studio_resource_root` 与 `studio_agents_dir()` 均有**真实生产调用点**,非孤儿。

独立证据:

- 已删符号 `grep -n` 全部 **0 命中**:`MOIRAI_MASTER_RULES` / `CLOTHO_RULES` / `LACHESIS_RULES` / `ATROPOS_RULES` / `MOIRAI_INTRO_SKILL` / `EVAL_JUDGEMENT_SKILL` / `StudioAhManagedFile` / `STUDIO_AH_MANAGED_FILES`(旧消费者数组一并消失)。
- `register_studio_resource_root`:定义 `lib.rs:514`,**生产调用 `lib.rs:2904`** —— 位于 Tauri app setup(`STUDIO_TAURI_DISABLE_SIDECAR != 1` 分支,sidecar 启动路径),把 `resource_root` 写入 `STUDIO_RESOURCE_ROOT` OnceLock(`lib.rs:512/515`),供 `studio_agents_dir()`(`lib.rs:532` `STUDIO_RESOURCE_ROOT.get()`)消费。是真实生产入口。
- `studio_agents_dir()`:定义 `lib.rs:523`,被**两条生产链**消费:
  - `lib.rs:656`,在 `studio_ah_managed_payloads()`(`lib.rs:655`)内 → 被 `prepare_studio_ah_workspace()`(`lib.rs:860/861`)调用 → 被生产入口 `ah_config_for_workspace()`(`lib.rs:911`)调用。
  - `lib.rs:883`,在生产函数 `transient_ah_config_content()`(`lib.rs:881`)内 → 同样被 `ah_config_for_workspace()`(`lib.rs:918`)调用。
  - 另 `lib.rs:3560/3686` 为测试消费,不影响"生产路径确有消费"的结论。

判定:各留其一、删被淘汰部分,机制真实接进生产路径,正确。✅

---

## 冲突 3 — moirai-intro 测试锚定真实资产文件 · **ACCEPT**

**核实结论**:测试锚在真实资产文件而非已删常量;资产文件内容**不含**"不是可用命令"类假话。

独立证据:

- 测试 `moirai_launch_prompt_triggers_intro_skill_without_scripted_answer`(`lib.rs:3548`)读的是**真实产物**:
  ```rust
  let intro = std::fs::read_to_string(
      studio_agents_dir().expect("agents dir")
          .join("skills").join("moirai-intro").join("SKILL.md"),   // lib.rs:3559-3564
  ).expect("moirai-intro skill asset");
  assert!(intro.contains("name: moirai-intro"));   // lib.rs:3567
  assert!(intro.contains("ah ps"));                // lib.rs:3570
  ```
  不引用任何已删常量(仅引用仍存在的 `MOIRAI_MASTER_REPORT_PROMPT`,`lib.rs:505`)。
- 资产文件 `apps/studio/backend/app/agents/skills/moirai-intro/SKILL.md` 实际存在(2137 bytes),内容:
  - 第 2 行 `name: moirai-intro` ✅(命中断言)
  - 第 19 行 `Run \`ah ps\` to query active subagent processes and their states.` ✅(命中断言,且语义真实)
  - 全文英文、技术中立,**不含**"ah status/ps 不是可用命令"这类假话——冲突2/3 的旧文案订正无需迁移的结论成立。
- 独立运行该测试:`test tests::moirai_launch_prompt_triggers_intro_skill_without_scripted_answer ... ok`。

判定:锚点正确、内容真实、测试通过。✅

---

## 冲突 4(重点)— `transient_ah_config_content` 返回类型分叉 + 两处 `.expect` 适配 · **ACCEPT**

master 在 `43a885a6` 追认 Q1=ACCEPT。g2 按任务要求**不因"已追认"跳过独立核实**,逐条复核如下,结论:**技术裁决站得住,g2 无异议**。

### (根因)git 考古独立坐实——语义 mis-merge 属实

`fn transient_ah_config_content` 签名三方对比(g2 亲跑 `git show <rev>:...lib.rs | grep`):

| 版本 | 签名 |
|---|---|
| merge-base `880164ad` | `-> String` |
| 本分支 `c56967ff` | `-> String`(**相对 base 未改**) |
| origin/main `ffeff566` | `-> Result<String, String>` |

两处冲突测试的出身:

- `test_lifecycle_only_on_studio_managed_config` / `test_quit_leaves_workspace_owned_config_untouched` 在 origin/main(`ffeff566`)**不存在**;在本分支 `c56967ff:4973/5273`**存在**。

→ git 三方合并无文本冲突地取了 origin/main 的 `Result` 签名(本分支没碰那行),又保留了本分支这 2 个假设 `String` 的测试 → 语义打架。`cargo build --lib` 不报(测试不编译),仅 `cargo test --lib` 暴露 `E0277`。报告 §2 冲突4 / §5 对根因的描述**属实,无夸大**。

### (2a)写法逐字一致 + 无遗留吞 Err 站点

`transient_ah_config_content` 全部调用点普查(`grep -nE` on 合并树 `lib.rs`):

| 行 | 用途 | 处理方式 |
|---|---|---|
| 881 | 函数定义 | `-> Result<String, String>` |
| 918 | **生产**(`ah_config_for_workspace`)| `...(assistant)?` —— `?` 正确传播 Err,write 自身错误另行 map |
| 3576 | 测试(既有兄弟)| `.expect("transient claude ah config")` |
| 3624 | 测试(既有兄弟)| `.expect("transient codex ah config")` |
| 3703 | 测试(既有兄弟)| `.expect("transient claude ah config")` |
| 4701 | 测试(既有兄弟)| `.expect("codex config")` |
| **5072** | 测试(**本次新增适配**)| `.expect("transient claude ah config")` |
| **5354** | 测试(**本次新增适配**)| `.expect("transient claude ah config")` |
| 5461 | 测试(既有兄弟)| `.expect("claude config")` |

- 5072/5354 两处新增站点与 3576/3703 **逐字一致**(`transient_ah_config_content(CodeAssistant::Claude).expect("transient claude ah config")`)。
- **不存在**任何"没有 `.expect` 就把 Result 直接塞给期望 `String`/`&[u8]`"的遗留站点:唯一生产站点 918 用 `?` 传播,其余 7 处测试站点全部显式 `.expect` 消费。**无吞 Err**(`.expect` 会 panic,不会静默吞掉),编译能过(见 2b),行为可观测(见 2c)。
- `git diff ffeff566 2d3e20dc -- ...lib.rs` 中 `transient_ah_config_content` 的新增行恰为这 2 条 `.expect`,别无他处。
- 附:报告称"与 5 处兄弟站点一致"——g2 核实 5 处兄弟站点(3576/3624/3703/4701/5461)+ 2 处新增 = 7 处测试站点,表述准确,**无遗漏、无夸大**。

### (2b)独立重跑编译/测试——全绿(唯一失败为已知假象)

g2 亲跑(非采信 commit 贴的输出),`RUSTUP_HOME=/root/.rustup CARGO_HOME=/root/.cargo`:

- `cargo build --lib` → **exit 0**,`Finished dev profile`,10 条 `never used` 警告(全为 `#[cfg(test)]`-only 辅助函数在 `--lib` 无测试构建下的正常产物,非死代码、非本次引入)。
- `cargo test --lib -- --test-threads=1`(串行,避开已知 sidecar flaky)→ **166 passed / 1 failed**。
  - 唯一失败:`native_fs::tests::publish_package_writer_maps_permission_error`(`native_fs.rs:1947`)。
  - g2 独立坐实其为 **root 沙箱假象**:该测试把父目录设 `0o500` 后 `.expect_err("read-only parent maps to permission")`;当前 `id -u = 0`(root 绕过权限位),写入反而成功 → `expect_err` 拿到 `Ok` → panic。`native_fs.rs` 被本次合并触碰行数 = **0**(`git diff 2d3e20dc^1 2d3e20dc -- native_fs.rs | wc -l`),故与本次合并无关,是既有假象。此为 `.ah` 纪律白名单里唯一允许的失败。
- 四处冲突锚点测试单独跑,全绿:
  ```
  test tests::moirai_launch_prompt_triggers_intro_skill_without_scripted_answer ... ok
  test tests::test_lifecycle_only_on_studio_managed_config ... ok
  test tests::test_quit_leaves_workspace_owned_config_untouched ... ok
  test tests::transient_ah_config_starts_moirai_team ... ok
  test result: ok. 4 passed; 0 failed
  ```

### (2c)`.expect` 写法本身是否妥当——g2 独立判断:妥当,无更优替代

- 两站点均为 `#[test] fn -> ()`,其函数体内已大量使用 `.unwrap()`(`lib.rs:5068/5074`)/`.expect()`(`lib.rs:5077`)处理"不该失败的测试前置条件",`.expect` 是本代码库对该场景的**一贯写法**(另有 5 处兄弟站点佐证)。
- 两站点是**载荷型**而非空转:`.expect` 解出的 Ok 内容被写进临时 `ah.toml`(`lib.rs:5070-5074` / `5352-5356`),随后驱动 `ah_config_for_status` / `classify_config_ownership` / `ensure_lifecycle_command_allowed` 真实断言——`.expect` 是穿过本次 diff 的真实前置,回滚(去掉 `.expect`)必然 `E0277` 编译不过(Rust 类型系统保证,非运行期漂移)。
- 若改用 `?` 传播,需把每个测试函数返回类型改成 `Result<(), String>`,与本库测试约定相悖,属无谓改动。
- **g2 结论**:纯技术层面 `.expect` 是此处唯一合规且最简的写法,**无更优替代,g2 不提异议**。

### (3)master 裁决理由是否属实——属实,无夸大/遗漏

- "与 5 处兄弟站点写法一致":属实(见 2a 普查)。
- "main 签名是唯一真相、本分支不适配即编译错误、不存在'不改'的选项":属实(见根因三方对比 + 2b 编译验证;`Result` 是 canonical 唯一签名,无第二版本共存)。
- "g1 两次独立验证全绿 166/1":g2 独立重跑复现**同一** 166/1 结果,与报告记录一致。
- **程序瑕疵的处置**:报告 §5 如实记录了"未经 master 会话确认的 Q1 授权经 operator 误判转投"这一裁决来源瑕疵,并以追加 commit 留痕、不重写历史。g2 认为此处置正确:**技术结论与授权来源的程序瑕疵相互独立**——由于该修法是被类型系统强制的唯一解,无论授权来源如何,代码结果都收敛到同一处;master 事后独立复核追认、决定不回滚(回滚重走只得同一结论)成立。程序瑕疵已透明留痕,未掩盖。

判定:**ACCEPT**。✅

---

## 边界与非阻断项

- **合并未吸入禁区文件**:`git show --stat 2d3e20dc` 中 `ah.toml` / `.operator-report*` / `vendor/` **零出现**;三者当前仍为游离未追踪状态。g2 全程未碰。
- **本分支 typed 合约仍在**:合并树 `runtime_state` / `parse_ah_runtime_snapshot` 命中 46 处,本 spec 的四值结构化合约未被 moirai 改动冲掉。
- **并行 flaky(非阻断、非本次引入)**:`sidecar::tests::allocate_loopback_port_honors_pinned_env` 在默认多线程下偶发失败(process-global env 竞态);`sidecar.rs` 被本次合并触碰行数 = 0,串行即消失。与本次合并无关,建议(留 PM/master)后续给该测试模块加 `#[serial]`。

---

## 附:g2 独立执行的关键命令(可复现)

```
git merge-base c56967ff ffeff566                                  # 880164ad
git show 880164ad:apps/studio/tauri/src/lib.rs | grep -nE "fn transient_ah_config_content"   # -> String
git show c56967ff:...lib.rs | grep -nE "fn transient_ah_config_content"                       # -> String
git show ffeff566:...lib.rs | grep -nE "fn transient_ah_config_content"                       # -> Result<String, String>
git show ffeff566:...lib.rs | grep -n "test_lifecycle_only_on_studio_managed_config"          # 缺席
git diff 2d3e20dc^1 2d3e20dc -- apps/studio/tauri/src/sidecar.rs | wc -l                      # 0
git diff 2d3e20dc^1 2d3e20dc -- apps/studio/tauri/src/native_fs.rs | wc -l                    # 0
cd apps/studio/tauri && cargo build --lib                                                     # exit 0
cd apps/studio/tauri && cargo test --lib -- --test-threads=1                                  # 166 passed / 1 failed
```
