# 跨泳道审计 · task10 收尾 lib.rs moirai-intro skill 文案订正(938fb5e7)

- **审计人**:g2-claude(泳道2 gatekeeper),跨泳道独立核实泳道1 产出
- **日期**:2026-07-11
- **被审对象**:
  - RED 测试 commit `47e6f95b`(g1-claude 执笔)
  - GREEN 实施 commit `938fb5e7`(g1-m1 实施)
- **分支**:`feat/studio-ah-state-contract-impl`
- **裁定**:**ACCEPT**

---

## 背景

tasks.md 任务10 第4条验收点:订正 `apps/studio/tauri/src/lib.rs` 里 `MOIRAI_INTRO_SKILL`
常量中一句已被 ah 1.4.0 证伪的旧话「`ah status` 不是可用命令」。此前在纯文档 commit
`26308bd3` 里暂缓,因订正会牵动测试断言、超出 docs-only 权限。master 拆成两步:
先 g1-claude 写 RED 测试(`47e6f95b`),再 g1-m1 改生产字符串变绿(`938fb5e7`)。
g1 不能自审其测试锚定的实现,故由 g2 跨泳道审。

---

## 核对结果

### 1a. 47e6f95b 只改测试断言,未碰生产代码 ✅

`git show --stat 47e6f95b`:仅 `apps/studio/tauri/src/lib.rs`,`2 insertions(+), 1 deletion(-)`。
diff 落点在 `#[cfg(test)] mod tests` 区域(第 3512-3515 行附近):

```diff
         assert!(MOIRAI_INTRO_SKILL.contains("ah status"));
-        assert!(MOIRAI_INTRO_SKILL.contains("不是可用命令"));
+        assert!(MOIRAI_INTRO_SKILL.contains("ah status --json"));
+        assert!(!MOIRAI_INTRO_SKILL.contains("不是可用命令"));
```

断言从「必须包含『不是可用命令』」反转为「必须包含 `ah status --json` 且不得包含『不是可用命令』」。
未触碰任何生产常量。RED 证据已记入 commit message(生产未改时新断言必红,panic 于
`assertion failed: MOIRAI_INTRO_SKILL.contains("ah status --json")`)。✅

### 1b. 938fb5e7 只改 lib.rs:599 生产字符串,未触碰测试断言 ✅

`git show --stat 938fb5e7`:仅 `apps/studio/tauri/src/lib.rs`,`1 insertion(+), 1 deletion(-)`。
diff 落点在 `MOIRAI_INTRO_SKILL` 常量内(第 599 行,信息来源第 3 点):

```diff
-3. 用 `ah ps` 确认三位子 agent 的运行状态。`ah status` 不是可用命令，不要调用；如果 `ah ps` 也无法确认，状态写“未确认”。
+3. 优先用 `ah status --json` 确认三位子 agent 的运行状态，必要时辅以 `ah ps`；daemon 不存在时 `ah status --json` 会非零退出且无 JSON，无法确认就写“未确认”。
```

单行改写,未动任何 `mod tests` 断言。✅

### 2. 当前 HEAD 测试与常量自洽,不再互相矛盾 ✅

测试函数 `moirai_launch_prompt_triggers_intro_skill_without_scripted_answer`(lib.rs:3501-3517)
逐条比对常量 `MOIRAI_INTRO_SKILL`(lib.rs:586-614)当前文本:

| 断言 | 常量落点 | 结论 |
|---|---|---|
| `contains("name: moirai-intro")` | 第 587 行 `name: moirai-intro` | 真 ✅ |
| `contains("ah ps")` | 第 599 行「辅以 \`ah ps\`」+ 第 607 行「从 \`ah ps\` 看到」 | 真 ✅ |
| `contains("ah status")` | 第 599 行 `ah status --json` 的子串 | 真 ✅ |
| `contains("ah status --json")` | 第 599 行 `ah status --json` | 真 ✅ |
| `!contains("不是可用命令")` | 全文已删除该串 | 真 ✅ |

五条断言全部与当前常量文本一致,无自相矛盾。✅

### 3. 独立重跑证实(不信 commit message 贴的输出)✅

单测(`--exact`):
```
test tests::moirai_launch_prompt_triggers_intro_skill_without_scripted_answer ... ok
test result: ok. 1 passed; 0 failed; 0 ignored; 0 measured; 166 filtered out
```

全量 `cargo test --lib`:
```
test result: FAILED. 166 passed; 1 failed; 0 ignored; 0 measured; 0 filtered out
failures:
    native_fs::tests::publish_package_writer_maps_permission_error
```

失败集合仍**只有既有的** `native_fs::tests::publish_package_writer_maps_permission_error`:
它期望写只读父目录时映射为权限错误,而 root 沙箱下 root 绕过文件权限、写入成功导致断言失败
(panic 于 `native_fs.rs:1947`「read-only parent maps to permission」)——纯 root 环境假象,
与本次改动(仅动 `MOIRAI_INTRO_SKILL` 字符串及其断言,与 `native_fs` 无任何交集)无关。
**无新增红。**✅

### 4. 改后文案语义与设计源一致 ✅

`docs/studio/mvp1/03_regions/copilot/ah-orchestration-design.md:651`:

> `.ah/skills/moirai-intro/SKILL.md` 用 `ah status --json`(1.4.0 起可用的结构化
> bootstrap/fallback 读)确认三位子 agent 状态,必要时辅以 `ah ps`;并注明 daemon 不存在时
> `status --json` 非零退出且无 JSON(F1),无法确认就写"未确认";

订正后的生产字符串(lib.rs:599)语义逐项对齐:
- 优先 `ah status --json` 做结构化确认 ✅
- 必要时辅以 `ah ps` ✅
- daemon 不存在时非零退出且无 JSON、无法确认写"未确认" ✅

### 5. 无夹带 ah.toml / vendor/ / .operator-report.phase1 ✅

两个 commit 的完整 `--name-only` 均只有 `apps/studio/tauri/src/lib.rs`。
对 `ah\.toml|vendor/|operator-report` 过滤:`NONE (clean)`。

> 注:当前工作树的 `M ah.toml` / `?? .operator-report.phase1` / `?? apps/studio/tauri/vendor/`
> 是会话开始前已存在的本地未提交噪声,**不在**被审的两个 commit 内,与本次审计无关。

---

## 锚定硬项复核(每单必查)

- **断言的是契约边界的可观测行为,还是实现内部状态?** —— 契约边界。测试读取的
  `MOIRAI_INTRO_SKILL` 正是受管文件 `.ah/skills/moirai-intro/SKILL.md` 的字面 `body`
  (lib.rs:682-684 `StudioAhManagedFile { relative_path: ".ah/skills/moirai-intro/SKILL.md",
  body: MOIRAI_INTRO_SKILL }`),即 Studio 准备 workspace 时真正落盘的 skill 文件内容。
  断言的是**出厂 skill 文本**这一可观测产物,不是内部私有状态。**非自指测试。**✅
- **回滚自检(基于 diff + 已记录 RED 证据推断,未改工作树)**:`ah status --json` 在常量中的
  唯一来源就是 938fb5e7 改出的第 599 行;回滚该生产改动后,常量恢复为「`ah status` 不是可用命令」,
  `contains("ah status --json")` 变假、`!contains("不是可用命令")` 变假 —— 两条新断言必红。
  与 47e6f95b commit message 记录的 RED 输出(`assertion failed:
  MOIRAI_INTRO_SKILL.contains("ah status --json")`)一致。测试确实穿过本次 diff、锚在生产真实路径上,
  **非空转测试。**✅

---

## 裁定

**ACCEPT。**

- RED(47e6f95b)只改测试断言,GREEN(938fb5e7)只改生产字符串,二者职责边界干净、无 scope 越界;
- 当前 HEAD 测试与常量自洽,不再互相矛盾;
- 独立重跑:单测绿,全量仅剩既有 root 沙箱假象红,无新增红;
- 文案语义与设计源 `ah-orchestration-design.md:651` 一致(F1);
- 无夹带 ah.toml / vendor / operator-report;
- 锚定硬项通过:测试锚在出厂 skill 文件内容这一契约边界,回滚生产改动即变红,非自指、非空转。

task10 第4条验收点收口通过。
