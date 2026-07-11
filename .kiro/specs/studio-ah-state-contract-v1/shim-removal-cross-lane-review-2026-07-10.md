# 跨泳道审计:b6c780a5 环境嗅探 shim 移除

- **审计人**:g2-claude(泳道2 gatekeeper),跨泳道审 g1-claude 实施的生产代码
- **被审 commit**:`b6c780a58365471f9d60048bcef1efa3703c4b4a`
  `fix(studio): 移除 tauri.ts 环境嗅探 shim,回归单一 payload 形状`
- **日期**:2026-07-10
- **裁定**:**✅ 通过(ACCEPT)**

---

## 一、缺陷背景

`apps/studio/frontend/src/lib/tauri.ts` 的 `subscribeCodeAssistantStatus`
早点无早期返回分支里,原先有一条环境嗅探 shim:

```ts
if (typeof process !== 'undefined' && process.env.NODE_ENV === 'test') {
  onStatus({ claude: false, codex: false } as any)   // 旧 boolean payload 形状
} else {
  onStatus(inactiveCodeAssistantStatus)               // 新 per-assistant 形状
}
```

它按 `NODE_ENV==='test'` 分叉,给测试喂旧 boolean 形状、给生产喂新形状,
违反本仓 `AGENTS.md`「no backward compatibility / no version-sniffing branch」纪律,
且用 `as any` 逃逸类型。

## 二、Diff 合规核对(逐条对本单交付第 1 项)

`git show b6c780a5 --stat`:`1 file changed, 1 insertion(+), 5 deletions(-)`。
diff 主体:

```diff
   const targetPath = workspaceRoot?.trim() ?? ''
   if (!targetPath || !isTauriRuntime() || !nativeHelpersAreAvailable()) {
-    if (typeof process !== 'undefined' && process.env.NODE_ENV === 'test') {
-      onStatus({ claude: false, codex: false } as any)
-    } else {
-      onStatus(inactiveCodeAssistantStatus)
-    }
+    onStatus(inactiveCodeAssistantStatus)
     return () => {}
   }
```

| 核对项 | 结论 | 证据 |
| --- | --- | --- |
| a) 只改一个生产文件、没碰任何 `*.test.ts(x)` | ✅ 通过 | `git show b6c780a5 --name-only` 只列 `apps/studio/frontend/src/lib/tauri.ts`;无测试文件 |
| b) 无 dual-format/version-sniffing 替代品(非变形保留) | ✅ 通过 | if/else 整条删除,收敛为单行 `onStatus(inactiveCodeAssistantStatus)`;无换名变量继续判环境 |
| c) 无残留 `as any` 或其它类型逃逸 | ✅ 通过 | 被删的 `as any` 是该区唯一逃逸;`grep -rn "as any" src/lib/tauri.ts` 全文 0 命中 |
| d) 未动 `ah.toml`、未用 `git add -A/.`(精确暂存) | ✅ 通过 | commit 文件列表恰好 1 个;`git show b6c780a5 --name-only \| grep -c ah.toml` = 0;工作树 `M ah.toml`、`?? .operator-report.phase1`、`?? apps/studio/tauri/vendor/` 至今仍未提交——若用 `git add -A/.` 会被一并扫入,故确系精确暂存 |

## 三、独立重跑验证(不信自报,g2 亲跑)

| 命令 | 结果 | 判定 |
| --- | --- | --- |
| `cargo test --lib`(apps/studio/tauri,RUSTUP/CARGO_HOME 指定) | 162 passed / 1 failed | ✅ 唯一失败 = `native_fs::tests::publish_package_writer_maps_permission_error`,即本机 root 环境已知白名单项(root 能写只读父目录导致权限映射断言失败),与本次改动无关 |
| `npm run typecheck`(`tsc -b --noEmit`) | 无错误(仅 npm 版本提示) | ✅ 绿 |
| `npx vitest run src/lib/tauri.test.ts src/components/copilot/copilot-panel.test.ts` | 2 files / 54 tests passed | ✅ 绿 |

Rust 失败项即任务书授权的唯一豁免项,不影响裁定。

## 四、历史遗留隐藏 shim 排查(本单交付第 3 项)

对 `subscribeCodeAssistantStatus` 全函数(`tauri.ts` L182–L219)三处 `onStatus`
调用点逐一核对,并 grep 全文 boolean/NODE_ENV/`as any`/`claude: false` 模式:

- L188(`!targetPath ...` 早返回,本次修改点):`onStatus(inactiveCodeAssistantStatus)` —— 新 per-assistant 形状 ✅
- L203(事件监听回调):`onStatus(payload.status)`,`payload` 类型为
  `CodeAssistantStatusEventPayload { status: CodeAssistantStatus }`,静态类型即新形状 ✅
- L211(`invoke` 失败 catch 分支):`onStatus(inactiveCodeAssistantStatus)` —— 新形状 ✅

`inactiveCodeAssistantStatus`(L159–L162)本体也是新形状
(`{ claude: { status:'inactive', readOnly:false }, codex: {...} }`)。
全文 grep:除合法的 `Promise<boolean>` 返回签名与 `readOnly: boolean` 字段外,
**无任何** `NODE_ENV`/`process.env`/`claude: false`/`as any` 残留。

**结论:无其它隐藏 shim,无旧 boolean 形状残留,该函数已彻底收敛到单一 per-assistant 形状。**
本单第 3 项授权的「记录但不改」情形不存在——没有遗留问题需上报裁定。

## 五、总裁定

**✅ 通过(ACCEPT)。** g1-claude 的 b6c780a5 精确删除了违反 no-backward-compat
纪律的环境嗅探 shim,彻底而非变形保留;未越界改测试、未碰 `ah.toml`、精确暂存;
无类型逃逸残留;三套独立验证全绿(Rust 唯一失败为白名单项)。函数内无其它隐藏 shim。
无返工项。
