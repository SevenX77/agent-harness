---
module: 03_regions/center-action-bar
doc: baseline
status: drafted（现状对齐 pinned 代码 0d9fbaf；Compile 入口 live；Predict/Run handler 仍是 `console.info` 桩，compile error 仍底部浮层 ⚠️。）
binds_alignment: ./mvp1-alignment.md
binds_code: apps/studio/frontend/src/components/studio/center-action-bar.tsx:CenterActionBar · apps/studio/frontend/src/components/studio/center-action-bar.tsx:deriveButtons · apps/studio/frontend/src/components/studio/Workspace.tsx:handleCompile · apps/studio/frontend/src/components/studio/Workspace.tsx:onPredict · apps/studio/frontend/src/components/studio/Workspace.tsx:onRun · apps/studio/frontend/src/components/studio/Workspace.tsx:CompileErrorPanel
units: [compile-stage-gate, predict-execution]
---

# center-action-bar — Baseline（当下代码实现逻辑）

> **Scope**: 中心主操作条：Compile、Predict、Run 的 stage-gated primary actions 与 compile drawer 入口。
> **现状一句话**: Compile 入口 live；Predict/Run handler 仍是 `console.info` 桩，compile error 仍底部浮层 ⚠️。

## UI/UX
| 面 | 现状 | 证据（文件:符号名） |
|---|---|---|
| Stage type | Center action bar knows idle, compile, predict, and run stages. | `apps/studio/frontend/src/components/studio/center-action-bar.tsx:center-action-bar（L4）` |
| Gate derivation | `deriveButtons` enables Compile, Predict, or Run based on stage. | `apps/studio/frontend/src/components/studio/center-action-bar.tsx:deriveButtons（L31）` |
| Buttons | Component renders Compile, Predict, and Run buttons with lucide icons. | `apps/studio/frontend/src/components/studio/center-action-bar.tsx:CenterActionBar（L62）`, `apps/studio/frontend/src/components/studio/center-action-bar.tsx:d（L73）` |
| Stage source | Workspace derives stage from manual compile state or debounced lint status. | `apps/studio/frontend/src/components/studio/Workspace.tsx:deriveBuildStage（L429）` |
| Compile handler | Compile invokes backend compile and sets compile-pass/fail. | `apps/studio/frontend/src/components/studio/Workspace.tsx:handleCompile（L397）` |
| Predict/Run handlers | Predict and Run currently call `console.info`. | `apps/studio/frontend/src/components/studio/Workspace.tsx:currentCompileErrors（L537）`, `apps/studio/frontend/src/components/studio/Workspace.tsx:currentCompileErrors（L538）` |
| Error panel | Current compile errors render as a bottom floating panel. | `apps/studio/frontend/src/components/studio/Workspace.tsx:currentCompileErrors（L531）`, `apps/studio/frontend/src/components/studio/Workspace.tsx:CompileErrorPanel（L571）` |

## 前端逻辑
| 面 | 现状 | 证据（文件:符号名） |
|---|---|---|
| Stage type | Center action bar knows idle, compile, predict, and run stages. | `apps/studio/frontend/src/components/studio/center-action-bar.tsx:center-action-bar（L4）` |
| Gate derivation | `deriveButtons` enables Compile, Predict, or Run based on stage. | `apps/studio/frontend/src/components/studio/center-action-bar.tsx:deriveButtons（L31）` |
| Buttons | Component renders Compile, Predict, and Run buttons with lucide icons. | `apps/studio/frontend/src/components/studio/center-action-bar.tsx:CenterActionBar（L62）`, `apps/studio/frontend/src/components/studio/center-action-bar.tsx:d（L73）` |
| Stage source | Workspace derives stage from manual compile state or debounced lint status. | `apps/studio/frontend/src/components/studio/Workspace.tsx:deriveBuildStage（L429）` |
| Compile handler | Compile invokes backend compile and sets compile-pass/fail. | `apps/studio/frontend/src/components/studio/Workspace.tsx:handleCompile（L397）` |
| Predict/Run handlers | Predict and Run currently call `console.info`. | `apps/studio/frontend/src/components/studio/Workspace.tsx:currentCompileErrors（L537）`, `apps/studio/frontend/src/components/studio/Workspace.tsx:currentCompileErrors（L538）` |
| Error panel | Current compile errors render as a bottom floating panel. | `apps/studio/frontend/src/components/studio/Workspace.tsx:currentCompileErrors（L531）`, `apps/studio/frontend/src/components/studio/Workspace.tsx:CompileErrorPanel（L571）` |

## 后端功能
| 面 | 现状 | 证据（文件:符号名） |
|---|---|---|
| Compile handler | Compile invokes backend compile and sets compile-pass/fail. | `apps/studio/frontend/src/components/studio/Workspace.tsx:handleCompile（L397）` |

## 当前边界（center-action-bar 现在不是什么）
- gate 规则 owner 是 `compile-lint`；本 region 只承载按钮与状态展示。
- 不拥有 predict/run 执行机制。

## baseline / alignment 差异（测试锚点）
| 维度 | 现状（baseline） | 目标（alignment） |
|---|---|---|
| Predict/Run wiring | `onPredict/onRun` 只 `console.info` ⚠️ | Predict/Run 真发请求并驱动状态 |
| compile drawer | 错误仍底部浮层 ⚠️ | Compile error drawer 由操作条入口/自动弹出 |
| gate | Run 依赖永不会置位的 predict-pass ⚠️ | compile-pass -> Predict；predict-pass -> Run |
> **验"是否按目标改了"**：1. Predict/Run wiring；2. compile drawer；3. gate。

## 读代码主路径提示
`apps/studio/frontend/src/components/studio/center-action-bar.tsx:CenterActionBar` → `apps/studio/frontend/src/components/studio/center-action-bar.tsx:deriveButtons` → `apps/studio/frontend/src/components/studio/Workspace.tsx:handleCompile` → `apps/studio/frontend/src/components/studio/Workspace.tsx:onPredict` → `apps/studio/frontend/src/components/studio/Workspace.tsx:onRun` → `apps/studio/frontend/src/components/studio/Workspace.tsx:CompileErrorPanel`。

> 旧 Coverage/Drift 暂存 [`_migrated-coverage-drift.md`](../../_migrated-coverage-drift.md#03-regions-center-action-bar)（迁移期安全网，代码实现验证后删）。

## 交叉引用（链接, 不复制）
[alignment](./mvp1-alignment.md)（目标,双向）· `compile-lint` · `predict` · `run-execution` · `timeline`
