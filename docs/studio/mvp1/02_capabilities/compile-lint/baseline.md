---
module: 02_capabilities/compile-lint
doc: baseline
status: FROZEN（现状对齐 pinned 代码 0d9fbaf；lint/compile 触发与 compile-pass stage live；错误仍是底部浮层/toast，drawer 与上下文标记未落 ⚠️。）
binds_alignment: ./mvp1-alignment.md
binds_code: apps/studio/frontend/src/hooks/useDebouncedLint.ts:useDebouncedLint · apps/studio/frontend/src/components/studio/Workspace.tsx:handleCompile · apps/studio/frontend/src/components/studio/Workspace.tsx:CompileErrorPanel · apps/studio/frontend/src/components/studio/center-action-bar.tsx:CenterActionBar · apps/studio/backend/app/routers/skills.py:compile_skill_endpoint
units: [compile-stage-gate, compile-lint-structured-error]
---

# compile-lint — Baseline（当下代码实现逻辑）

> **Scope**: 实时 lint、手动 Compile、结构化编译错误呈现，以及 Compile -> Predict -> Run 的 stage gate。
> **现状一句话**: lint/compile 触发与 compile-pass stage live；错误仍是底部浮层/toast，drawer 与上下文标记未落 ⚠️。

## UI/UX
实时 lint、手动 Compile、结构化编译错误呈现，以及 Compile -> Predict -> Run 的 stage gate。 当前在 UI 上的可见入口、提示、面板或状态详见下方前端证据；带 ⚠️ 的项是已验真的 code↔design drift。

## 前端逻辑
| 面 | 现状 | 证据（文件:符号名） |
|---|---|---|
| Debounced lint | Editor markdown triggers `/lint` after 800ms and publishes status through sessionStorage/event. | `apps/studio/frontend/src/hooks/useDebouncedLint.ts:useDebouncedLint（L30）`, `apps/studio/frontend/src/hooks/useDebouncedLint.ts:timeout（L48）` |
| Lint API | Lint hook posts to `/skills/{skill_id}/lint`. | `apps/studio/frontend/src/hooks/useDebouncedLint.ts:timeout（L49）` |
| Manual compile | Center Compile calls `compileSkill`, sets compile stages, stores errors, and toasts result. | `apps/studio/frontend/src/components/studio/Workspace.tsx:handleCompile（L397）`, `apps/studio/frontend/src/api/client.ts:compileSkill（L83）` |
| Stage derivation | Workspace derives stage from explicit compile state, otherwise reads lint status. | `apps/studio/frontend/src/components/studio/Workspace.tsx:deriveBuildStage（L429）` |
| Center gate | Center action bar gates Compile, Predict, Run by stage. | `apps/studio/frontend/src/components/studio/center-action-bar.tsx:deriveButtons（L31）`, `apps/studio/frontend/src/components/studio/center-action-bar.tsx:CenterActionBar（L62）` |
| Old error panel | Compile errors render in a bottom floating panel, not a drawer. | `apps/studio/frontend/src/components/studio/Workspace.tsx:currentCompileErrors（L531）`, `apps/studio/frontend/src/components/studio/Workspace.tsx:CompileErrorPanel（L571）` |
| Engine compile | Studio backend delegates compile to graph-agent compiler. | `apps/studio/backend/app/services/skills.py:lint_skill_path（L313）`, `packages/graph-agent/src/graph_agent/core/compiler.py:compile_skill（L41）` |

## 后端功能
| 面 | 现状 | 证据（文件:符号名） |
|---|---|---|
| Backend compile | Skill router exposes compile and graph/lint routes through FastAPI. | `apps/studio/backend/app/routers/skills.py:get_skill（L109）`, `apps/studio/backend/app/routers/lint.py:lint（L13）` |
| Engine compile | Studio backend delegates compile to graph-agent compiler. | `apps/studio/backend/app/services/skills.py:lint_skill_path（L313）`, `packages/graph-agent/src/graph_agent/core/compiler.py:compile_skill（L41）` |

## 当前边界（compile-lint 现在不是什么）
- 不重新定义 engine 编译错误码；engine contract 只引用 `engine`。
- 不拥有 Predict/Run 的执行机制，只拥有 gate 规则。

## baseline / alignment 差异（测试锚点）
| 维度 | 现状（baseline） | 目标（alignment） |
|---|---|---|
| 错误呈现 | `CompileErrorPanel` 仍是底部浮层/toast ⚠️ | Compile drawer 自动弹出、可复制、只盖画布 |
| 上下文定位 | 主要只有按钮颜色/toast/浮层 ⚠️ | 同一错误投到 canvas 节点、Properties/input 字段、Monaco 行 |
| stage gate | compile-pass 可驱动 Predict；predict-pass 未置位导致 Run 链路断 ⚠️ | warning 不阻塞 Predict；error 阻塞；predict-pass 解锁 Run |
> **验"是否按目标改了"**：1. 错误呈现；2. 上下文定位；3. stage gate。

## 读代码主路径提示
`apps/studio/frontend/src/hooks/useDebouncedLint.ts:useDebouncedLint` → `apps/studio/frontend/src/components/studio/Workspace.tsx:handleCompile` → `apps/studio/frontend/src/components/studio/Workspace.tsx:CompileErrorPanel` → `apps/studio/frontend/src/components/studio/center-action-bar.tsx:CenterActionBar` → `apps/studio/backend/app/routers/skills.py:compile_skill_endpoint`。

> 旧 Coverage/Drift 暂存 [`_migrated-coverage-drift.md`](../../_migrated-coverage-drift.md#02-capabilities-compile-lint)（迁移期安全网，代码实现验证后删）。

## 交叉引用（链接, 不复制）
[alignment](./mvp1-alignment.md)（目标,双向）· `center-action-bar` · `editor` · `properties` · `timeline` · `predict` · `run-execution` · `engine`
