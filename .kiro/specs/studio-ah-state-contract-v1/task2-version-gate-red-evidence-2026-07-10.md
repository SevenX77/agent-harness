# task2 版本门 RED 证据(机器验证)— 2026-07-10

commit 549358a0 写红测试时无法机器验证(缺 tauri 系统库,cargo 卡在 build.rs)。
operator 装齐系统库 + 补 vendor/python_runtime 占位后,本次在 worktree 用
`RUSTUP_HOME=/root/.rustup CARGO_HOME=/root/.cargo` 真跑,记录实际 RED。

- worktree HEAD:`549358a0`
- 工具链:`cargo 1.96.1 (356927216 2026-06-26)`
- 命令:`cd apps/studio/tauri && cargo test --lib`

## test_version_gate_rejects_below_1_4_0 → RED(编译期,E0425)

生产 seam `ah_version_gate` 尚不存在,整个 lib-test 目标编译失败 3 条 E0425:

```
error[E0425]: cannot find function `ah_version_gate` in this scope
    --> src/lib.rs:3336:24
error[E0425]: cannot find function `ah_version_gate` in this scope
    --> src/lib.rs:3349:13
error[E0425]: cannot find function `ah_version_gate` in this scope
    --> src/lib.rs:3353:13
error: could not compile `skill-studio-tauri` (lib test) due to 3 previous errors
```

RED 属实且落在预期符号上(与 549358a0 commit message 声明一致)。g1-m1 加
`fn ah_version_gate(&str)->Result<(),String>` 后此三处消解。

## test_version_parse_uses_bare_ah_version → RED(断言,当前被同一编译错误遮蔽)

该测试的 RED 是断言级:对 4 个 launcher/attach 生产脚本断言用裸 `ah version`、
无 `ah --version`、无 `print $2`。核对当前生产模板(未改):

```
src/lib.rs:1760:ah_version="$(ah --version 2>/dev/null | awk '{{print $2}}')"
src/lib.rs:1842:ah_version="$(ah --version 2>/dev/null | awk '{{print $2}}')"
src/lib.rs:1909:ah_version="$(ah --version 2>/dev/null | awk '{{print $2}}')"
src/lib.rs:1966:ah_version="$(ah --version 2>/dev/null | awk '{{print $2}}')"
```

模板仍全用 `ah --version | awk '{print $2}}'`,故三条断言(含 `!contains("ah --version")`、
`!contains("print $2")`)在原理上必红。但两测试同处一个 `#[cfg(test)] mod tests`,
上面缺 `ah_version_gate` 导致 lib-test 二进制无法编译,本测试此刻**跑不起来**,
其断言 RED 被编译 RED 遮蔽。按"纯验证、不写生产/测试代码"约束,未加临时 stub 单独跑它;
g1-m1 实现 `ah_version_gate` 使二进制可编译后,此测试才会以断言失败形式独立现红,
待模板改裸 `ah version` 后转绿。

## 结论

两条测试 RED 均属实:gate 测试编译期硬红(符号缺失,命中预期 seam);parse 测试断言
原理上红(生产模板未改)但当前被同一编译错误遮蔽,无法独立起跑——符合 task2「先写红」
半程状态,等待 g1-m1 纯实施变绿。
