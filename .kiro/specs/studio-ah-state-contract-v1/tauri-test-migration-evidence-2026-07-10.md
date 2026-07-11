# tauri.test.ts → 新 per-assistant payload 形状迁移证据

- 日期:2026-07-10
- 执笔:g2-claude(泳道2 gatekeeper;既有测试迁移只能闸门本人做,g2-m1 无权碰测试文件)
- 唯一交付文件:`apps/studio/frontend/src/lib/tauri.test.ts`(+ 本证据文件)
- 严格不碰:`apps/studio/frontend/src/lib/tauri.ts`(生产代码,删 shim 是 g2-m1 下一棒)

---

## 1. 为什么这是"第4处遗漏耦合点"

契约从旧布尔形状 `{ claude: boolean; codex: boolean }` 迁到新 per-assistant 形状
`{ claude: AssistantState; codex: AssistantState }`(`AssistantState = { status: 'inactive'
| 'starting' | 'active' | 'degraded' | 'error'; reason?: string; readOnly: boolean }`)。

已迁移轨迹(git 实证):

- `871c3546` / `2be93b82`:迁 `src/components/copilot/copilot-panel.test.ts`(task8+9 主战场)。
- `68ee4cee`:g2-m1 实现 task8 生产侧新形状(`tauri.ts` 的 `AssistantState` /
  `CodeAssistantStatus` / `inactiveCodeAssistantStatus`)。

`tauri.test.ts` 是订阅链路 `subscribeCodeAssistantStatus` 的**单元测试锚点**,直接消费
`onStatus(status)` 的形状,却在上面几轮迁移里被漏掉——因为 g2-m1 无权改测试文件,为了让
`68ee4cee` 变绿,他在生产代码里加了一条**环境嗅探 shim** 把测试模式单独喂回旧布尔值(见 §4),
把这处旧形状耦合"藏"了起来,没有暴露成红灯。所以它成了这条契约迁移里**第4处**需要单独派单
清理的遗漏耦合点(前三处 = copilot-panel.test.ts 的既有断言块 + 生产 `tauri.ts` 新形状 +
task9 只读 Detach 断言,均已在前序提交落地)。

### 附带发现(不在本单范围,已 flag 给 PM)

`src/components/copilot/copilot-panel.test.ts:291,295,315` 仍残留一处旧布尔形状
(`emitStatus?.({ claude: false, codex: true })` 及其类型注解 `{ claude: boolean; codex: boolean }`)。
该文件其余部分(337 行起 task9 新形状)已迁移。这是**另一处疑似遗漏耦合点**,但按本单纪律
「只改 tauri.test.ts 一个文件」,**我未触碰它**——建议 PM 单独派单(归 task9 territory / 需与
g2-m1 协调),不在本次交付内。

---

## 2. grep 完整覆盖(不只信 brief 列的4处)

```
$ grep -n "claude:\|codex:\|CodeAssistantStatus" apps/studio/frontend/src/lib/tauri.test.ts
48:  payload: { workspaceRoot: string; status: { claude: boolean; codex: boolean } }   # 类型定义
266: ...status: { claude: false, codex: true } ...                                     # 喂给回调(被 workspaceRoot 过滤掉)
267: ...status: { claude: true, codex: false } ...                                     # 喂给回调(命中)
275: expect(onStatus).toHaveBeenCalledWith({ claude: true, codex: false })             # Tauri 路径断言
291: expect(onStatus).toHaveBeenCalledWith({ claude: false, codex: false })            # shim 回退路径断言
```

其余命中(14/27 行 import、245/257/259/264/287 行)为函数名 import / `CodeAssistantStatusTestEvent`
类型引用 / `ensureCodeAssistantStatusEvents` / `resolves.toEqual(Function)`,不含形状字面量,
随类型定义迁移后自动生效。确认耦合点恰好 4 处:类型定义(48-49)、喂入负载(266-267)、
两处断言(275、291)。

---

## 3. 迁移前后断言对照

语义映射(brief 锁定):`true`→`{ status: 'active', readOnly: false }`,
`false`→`{ status: 'inactive', readOnly: false }`;统一 `readOnly: false`(Studio-managed),
**不引入所有权断言维度**(那是 task9 只读 Detach 的专属范围,已在 copilot-panel.test.ts 覆盖)。

| 位置 | 迁移前(旧布尔) | 迁移后(新 per-assistant) |
| --- | --- | --- |
| 48-49 类型 | `status: { claude: boolean; codex: boolean }` | `status: CodeAssistantStatus`(import 生产类型,SSOT,不重复定义) |
| 266 喂入(被过滤) | `{ claude: false, codex: true }` | `{ claude: {status:'inactive',readOnly:false}, codex: {status:'active',readOnly:false} }` |
| 267 喂入(命中) | `{ claude: true, codex: false }` | `{ claude: {status:'active',readOnly:false}, codex: {status:'inactive',readOnly:false} }` |
| 275 Tauri 断言 | `{ claude: true, codex: false }` | `{ claude: {status:'active',readOnly:false}, codex: {status:'inactive',readOnly:false} }` |
| 291 shim 回退断言 | `{ claude: false, codex: false }` | `{ claude: {status:'inactive',readOnly:false}, codex: {status:'inactive',readOnly:false} }` |

类型注解改用 `import type { CodeAssistantStatus } from './tauri'`(`verbatimModuleSyntax: true`
要求 type-only import 用 `import type`),让测试事件负载的 `status` 直接锚定生产契约类型,而非
在测试里复制一份字面量类型(DRY / 底座一)。

---

## 4. vitest 真实输出:1 红 31 绿(红是预期,不是 bug)

```
$ cd apps/studio/frontend && npx vitest run src/lib/tauri.test.ts
 FAIL  src/lib/tauri.test.ts > desktop shell helpers > treats code assistants as inactive outside desktop runtime
 AssertionError: expected "vi.fn()" to be called with arguments: [ { claude: { …(2) }, …(1) } ]
 Received:
   1st vi.fn() call:
   [ {
-      "claude": { "readOnly": false, "status": "inactive" },
-      "codex":  { "readOnly": false, "status": "inactive" },
+      "claude": false,
+      "codex": false,
   } ]

 Test Files  1 failed (1)
      Tests  1 failed | 31 passed (32)
```

### 红因分析(锚定硬项 / 回滚自检的正向证明)

只有 1 条红:`treats code assistants as inactive outside desktop runtime`。它走**非 Tauri
回退路径**,命中生产代码里仍在的环境嗅探 shim:

```ts
// apps/studio/frontend/src/lib/tauri.ts  subscribeCodeAssistantStatus 内(生产代码,本单不碰)
if (!targetPath || !isTauriRuntime() || !nativeHelpersAreAvailable()) {
  if (typeof process !== 'undefined' && process.env.NODE_ENV === 'test') {
    onStatus({ claude: false, codex: false } as any)   // ← shim 仍喂旧布尔值,故红
  } else {
    onStatus(inactiveCodeAssistantStatus)              // ← 生产真实路径,已是新形状
  }
  return () => {}
}
```

vitest 的 `Received` 段实测到 `{ claude: false, codex: false }`——这正是 shim 的**活输出**。
即:红灯断言穿过了本次迁移目标的生产真实路径(shim 分支),锚在**生产代码的真实可观测行为**上,
不是自指 mock。删掉 shim 后回退分支统一走 `onStatus(inactiveCodeAssistantStatus)`(新形状),
`Received` 会变成 `{ claude:{status:'inactive',readOnly:false}, codex:{...} }`,该测试即转绿。

**删 shim 是 g2-m1 下一棒的活,不是本单范围**(本单只迁测试文件,不碰生产代码)。此刻红是**预期**。

### 为何另一条订阅测试保持绿(不是漏测)

`subscribes to code assistant status events and unwatches on dispose` 走 **Tauri 真实路径**
(`window.__TAURI_INTERNALS__` + `markRuntimeReady()`),生产代码在此把 `payload.status`
**原样透传**给 `onStatus`(`tauri.ts:207 onStatus(payload.status)`),不经 shim。测试喂什么形状、
断言什么形状由测试自身驱动,迁移时喂入(267)与断言(275)同步换新形状即保持绿——这条本就
不该红,它验证的是"透传 + workspaceRoot 过滤",与 shim 无关。

---

## 5. typecheck:通过(无新增类型错误)

```
$ npm run typecheck            # tsc -b --noEmit
> studio-frontend@0.0.0 typecheck
> tsc -b --noEmit             # 无输出 = 通过
```

shim 的 `as any` 仍在,绕过了生产侧类型检查,故 typecheck 依旧过;本证据只确认**我改的测试类型**
(`CodeAssistantStatusTestEvent.status: CodeAssistantStatus` + 新形状字面量)未引入任何新类型错误。

---

## 6. 纪律自检

- [x] 只改 `apps/studio/frontend/src/lib/tauri.test.ts` 一个生产/测试文件(+ 本证据文件)。
- [x] 未碰 `apps/studio/frontend/src/lib/tauri.ts`(g2-m1 删 shim 的活)。
- [x] 未碰 `ah.toml`;commit 用显式文件列表,不 `git add -A`。
- [x] 未为了让测试自绿而改动 shim(那是越权改生产代码)。
- [x] 红灯锚在生产真实路径(shim 活输出),非自指 mock;删 shim 后可转绿(可复现验法见 §4)。
