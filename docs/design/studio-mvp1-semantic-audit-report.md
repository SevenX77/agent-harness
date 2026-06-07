# Studio MVP1 Semantic Audit Report

日期: 2026-06-05

范围: `docs/studio/mvp1/02_capabilities` 28 档 + `03_regions` 24 档 + `04_platform` 11 档, 共 63 档(62+1)。按 `docs/design/studio-mvp1-semantic-audit-prompt.md` 只审语义层: R0 内容正确、R1 SSOT、R3 最新决策, 以及 Q1-Q5。机械硬规则 R2/R4/R5/R6/R7/R8 不重跑, 只引用已存在锁态事实。

## 0. 权威锚点

- 审计规范: `docs/development/design-doc-standards/02-audit-standard.md:15-25` 定义 R0/R1/R3, `:50-63` 定义 Q1-Q5, `:82-91` 定义输出格式。
- Studio MVP1 当前 SSOT: `docs/studio/mvp1/README.md:4` 明确 `.kiro/specs/studio-*` 仅历史参考, 不作 SSOT；`:14-28` 明确四层边界和 non-goals。
- ③a/③b 最新反转: `docs/studio/mvp1/01_workflows/00_settings-ux-spec.md:338-352` 明确 model group、6 态、draft、materialize、endpoint 标准化等公共内核归 ③b gateway, Studio 只保留应用加工。
- finality 热点: 旧 `docs/studio/_reorg/alignment-notes.md:302` 说 03-06 截至 2026-06-02 未过 PM；但新 `docs/studio/mvp1/01_workflows/INDEX.md:17-20` 写全 7 节点走查完成, 03/04/05/06 正文均有“走查完整记录”与 PM 原话。结论: `_reorg/alignment-notes` 不再是 03-06 finality 当前 SSOT。
- 锁态: `docs/studio/mvp1/DESIGN_UNITS_INDEX.md:12` 写当前全部 `unit-lock=drafted`, `:51-53` 写所有单元不能宣称 locked。因此本次 63 档文件级均不可进 FROZEN。

## 1. 全局结论

### 1.1 R0/R1/R3 FAIL 总清单

| 优先级 | ID | 文件 | 规则 | 证据 | 修复建议 |
|---|---|---|---|---|---|
| P0 | S-01 | `02_capabilities/predict/mvp1-alignment.md` | R1 | `:51` 写“接线 / 签名实施归 kiro”。MVP1 README 已明确 `.kiro` 只历史参考。 | 删除 Kiro 归属, 改为“实施任务/接线待办”, 不把旧实施体系写成当前 SSOT。 |
| P0 | S-02 | `02_capabilities/golden-eval/mvp1-alignment.md` | R0/R3 | `:63` 明确 golden 不在 Properties, `:79` 又把 `properties` 放入 Region links。workflow `04_run-and-verify.md:128` 也说详细 diff 在 editor, 不在 properties。 | Region links 删除 `properties`, 补 `editor`; 如需提 Properties, 只能写负向边界。 |
| P0 | S-03 | `02_capabilities/debug-resume/mvp1-alignment.md` | R0/R3 | `:40` 仍写 HitL “top question frame”, 但 `:73` 写“不做固定画布顶栏”, 改为节点 debug 悬浮 bar 上方的富文本输入框。workflow `05_debugging.md:17` 仍保留旧顶部问题框。 | 以 2026-06-04 节点 debug bar 决策为准, 同步 workflow 与模块: HitL 表面锚定节点/agent phase 子节点, 不写固定顶栏。 |
| P0 | S-04 | `03_regions/local-history/mvp1-alignment.md` | R3 | frontmatter `:7` 对齐 `05_debugging.md`, 正文 `:17` 和 F1/F2/F3 实际对齐 `06_eval.md` 与 `04_run-and-verify.md`; `:40-45` 又明确 RunDetail/BatchSummary 不归 Local History。 | frontmatter 改为 `06_eval.md` + `04_run-and-verify.md`; 不把 local-history 挂 debug。 |
| P0 | S-05 | `03_regions/properties/mvp1-alignment.md` | R0/R3 | `:49-52`、`:62` 明确 golden 完全不在 Properties, 但接口 `:57` 仍写 `optional golden diff summary`; capability link `:59` 还无负向说明。 | 删除 `optional golden diff summary`; `golden-eval` link 如保留, 标成“不承载/负向边界”。 |
| P0 | S-06 | `03_regions/shell-layout/mvp1-alignment.md` | R0/R3 | `:31-32`、`:68` 明确子图 breadcrumb 不在 Header, 放 canvas 左上角；测试 `:34` 仍写 Header 的 breadcrumb click。 | Header 测试只保留 Back Home/Team/Release; breadcrumb 测试移动到 canvas。 |

### 1.2 Q3 跨模块 owner / unit 映射 drift

这些不是实现缺口, 而是语义映射会误导 owner 的问题。优先级低于 R0/R1/R3, 但进 FROZEN 前应统一。

| ID | 文件 | 证据 | 建议 |
|---|---|---|---|
| Q3-01 | `03_regions/timeline/mvp1-alignment.md` | `:6` 有 trace/run units, 但 `:85-87` 三项都对齐 `compile-lint-structured-error`。 | live trace -> `trace-dot-blackboard`; run detail -> `run-execution-node-status`; golden actions -> `golden-per-agent-node`/`copilot-assist`。 |
| Q3-02 | `03_regions/canvas/mvp1-alignment.md` | `:6` 有 subgraph/run/trace units, 但 `:80-82` 全对齐 `subgraph-path-inline-drilldown`。 | 节点态 -> `run-execution-node-status`; dot 黑板 -> `trace-dot-blackboard`; 子图 inline -> `subgraph-path-inline-drilldown`。 |
| Q3-03 | `03_regions/editor/mvp1-alignment.md` | `:77-79` 写路径、inline diagnostics、golden diff 全对齐 `native-rust-writer`。 | inline diagnostics -> `compile-lint-structured-error`; golden diff -> `golden-per-agent-node`; 只写路径对齐 `native-rust-writer`。 |
| Q3-04 | `02_capabilities/file-editing/mvp1-alignment.md` | `:78-80` “只读 trace” 也对齐 `native-rust-writer`, 但正文 `:63` 已归 `compile-lint`/editor/engine, trace 文档应消费 trace/debug。 | 只读 trace -> `trace-dot-blackboard`/`debug-resume-checkpoint` 的 editor 落点; 写路径才归 native writer。 |
| Q3-05 | `02_capabilities/graph-authoring/mvp1-alignment.md` | `:78-80` “节点态”对齐 subgraph unit, `:85` 又说节点态来自 run/predict/state projection。 | 节点态切面移到 `run-execution-node-status`/`state-engine`, graph-authoring 只消费。 |
| Q3-06 | `03_regions/properties/mvp1-alignment.md` | `:67-69` 字段表单、edge trace、golden scope 全对齐 `phase-field-whitelist`。 | edge trace -> `trace-dot-blackboard`; golden scope -> `golden-per-agent-node` 负向边界。 |
| Q3-07 | `04_platform/engine/mvp1-alignment.md` | `:88-90` resume / engine SSOT / golden-path-schema 全对齐 `compile-stage-gate`。 | resume -> `debug-resume-checkpoint`; golden/path/schema -> `golden-per-agent-node` + engine SSOT; compile 只管编译。 |
| Q3-08 | `04_platform/state-engine/mvp1-alignment.md` | `:76-78` 状态源、WS bridge、sidecar failure 全对齐 `shell-runtime-gate`。 | 状态源拆 `run-execution-node-status`、`trace-dot-blackboard`、`settings-six-state-provider-health`; sidecar failure 才归 shell runtime gate。 |
| Q3-09 | `04_platform/llm-copilot-http-api/mvp1-alignment.md` | `:59-61` router boundary / Copilot SDK test / DTO SSOT 全对齐 `settings-six-state-provider-health`。 | router boundary 对齐 ③a/③b handoff; Copilot SDK test -> `copilot-sdk-test-parity`; DTO SSOT -> gateway schema SSOT。 |
| Q3-10 | `04_platform/gateway/mvp1-alignment.md` | `:39-41` 六态/materialize/copilot route 全对齐 `settings-six-state-provider-health`。 | materialize -> `model-group-role-materialization`; copilot route -> `copilot-sdk-test-parity` 的 gateway route 切面。 |
| Q3-11 | `04_platform/native-fs/mvp1-alignment.md` | `:79-81` sidecar gate 对齐 `native-rust-writer`, 但 D10 sidecar gate 是 shell/runtime 状态问题。 | sidecar gate 改挂 `shell-runtime-gate`/`state-engine`; native-fs 保留唯一写者/打包写者。 |

### 1.3 Q2/Q4 全局债

- Q2: 多个 `mvp1-alignment.md` 的“决策 + 动机”表仍是模板句, 如“对齐某设计单元, 保证实现与测试可回扣”。这能做追溯, 但不是“为什么/约束”。重点涉及 compile-lint、run-execution、trace-observability、conflict-overwrite、timeline/canvas/editor、engine/state-engine 等。
- Q4: 31 处迁移附录 `_migrated-coverage-drift.md` 仍作为“迁移期安全网”链接, 例如 `04_platform/llm-copilot-http-api/mvp1-alignment.md:75`、`02_capabilities/copilot-assist/mvp1-alignment.md:120`。这不是 R1 FAIL, 因为它在当前 mvp1 内且声明“代码实现验证后删”, 但进 FROZEN 前应清理或明确“不作 SSOT”。
- FROZEN: 63 档全部 `status: drafted`; DESIGN_UNITS_INDEX 全部 `unit-lock=drafted`。本报告判定 0 档可直接进 FROZEN。

## 2. finality 热点结论: 03-06

| workflow | 结论 | 证据 | 仍需同步 |
|---|---|---|---|
| 03_compile | finality PASS | `03_compile.md:5` 写完整记录, `:26-35` 有 PM 原话与决策。 | 下游 alignment 的 Q2 表可补真实动机, 但不是 finality 空洞。 |
| 04_run-and-verify | finality PASS | `04_run-and-verify.md:6` 写完整记录; predict 决策 `:28-37`; trace/golden 决策 `:103-140`。 | golden 不在 Properties 的决策在 golden-eval/properties 两档未同步干净。 |
| 05_debugging | finality PASS, 但 HitL 表面有后续覆盖 | `05_debugging.md:5` 写完整记录, `:23-35` 有决策/测试; 但旧 `:17` 顶部问题框与后续 debug-resume `:73` 节点 bar 冲突。 | 以 2026-06-04 debug bar 决策统一 workflow 与模块。 |
| 06_eval | finality PASS | `06_eval.md:5-6` 写 PM 2026-06-04 走查与发布低优先; `:24-31` 有决策和 PM 原话。 | local-history frontmatter 仍误挂 05_debugging。 |

## 3. 分批逐档 verdict

记号: `R = R0/R1/R3` 语义判定；baseline 的 R3 记 `n/a`。`Q = Q1/Q2/Q3/Q4/Q5`。`✓` 为通过, `⚠` 为质量弱项, `FAIL` 为上方硬失败。`FROZEN` 全部为否, 原因相同: `status=drafted` 且 `unit-lock=drafted`。

### 3.1 capabilities: 28 档

| 档 | R | Q1/Q2/Q3/Q4/Q5 | FROZEN | 备注 |
|---|---|---|---|---|
| `02_capabilities/compile-lint/baseline.md` | R0✓ R1✓ R3 n/a | ✓/n/a/✓/⚠/✓ | 否 | 迁移安全网残留。 |
| `02_capabilities/compile-lint/mvp1-alignment.md` | R0✓ R1✓ R3✓ | ✓/⚠/✓/✓/✓ | 否 | 决策表动机模板化。 |
| `02_capabilities/conflict-overwrite/baseline.md` | R0✓ R1✓ R3 n/a | ✓/n/a/✓/⚠/✓ | 否 | 迁移安全网残留。 |
| `02_capabilities/conflict-overwrite/mvp1-alignment.md` | R0✓ R1✓ R3✓ | ✓/⚠/✓/✓/✓ | 否 | PM 原话/动机偏薄。 |
| `02_capabilities/copilot-assist/baseline.md` | R0✓ R1✓ R3 n/a | ✓/n/a/✓/⚠/✓ | 否 | 迁移安全网残留。 |
| `02_capabilities/copilot-assist/mvp1-alignment.md` | R0✓ R1✓ R3✓ | ✓/✓/✓/⚠/✓ | 否 | `:120` 迁移附录残留; SDK test/session/safe write 是实现债。 |
| `02_capabilities/debug-resume/baseline.md` | R0✓ R1✓ R3 n/a | ✓/n/a/✓/⚠/✓ | 否 | 迁移安全网残留。 |
| `02_capabilities/debug-resume/mvp1-alignment.md` | R0 FAIL R1✓ R3 FAIL | ✓/✓/⚠/✓/✓ | 否 | S-03 HitL top frame vs node bar 冲突。 |
| `02_capabilities/file-editing/baseline.md` | R0✓ R1✓ R3 n/a | ✓/n/a/✓/⚠/✓ | 否 | 迁移安全网残留。 |
| `02_capabilities/file-editing/mvp1-alignment.md` | R0✓ R1✓ R3✓ | ✓/⚠/⚠/✓/✓ | 否 | Q3-04: 只读 trace 误挂 native writer。 |
| `02_capabilities/golden-eval/baseline.md` | R0✓ R1✓ R3 n/a | ✓/n/a/✓/⚠/✓ | 否 | 迁移安全网残留。 |
| `02_capabilities/golden-eval/mvp1-alignment.md` | R0 FAIL R1✓ R3 FAIL | ✓/✓/⚠/✓/✓ | 否 | S-02: properties 正负边界冲突。 |
| `02_capabilities/graph-authoring/baseline.md` | R0✓ R1✓ R3 n/a | ✓/n/a/✓/⚠/✓ | 否 | 迁移安全网残留。 |
| `02_capabilities/graph-authoring/mvp1-alignment.md` | R0✓ R1✓ R3✓ | ✓/✓/⚠/✓/✓ | 否 | Q3-05: 节点态误挂 subgraph unit。 |
| `02_capabilities/phase-editing/baseline.md` | R0✓ R1✓ R3 n/a | ✓/n/a/✓/⚠/✓ | 否 | 迁移安全网残留。 |
| `02_capabilities/phase-editing/mvp1-alignment.md` | R0✓ R1✓ R3✓ | ✓/✓/✓/✓/✓ | 否 | L3 canvas-inline 与 Properties 边界一致。 |
| `02_capabilities/predict/baseline.md` | R0✓ R1✓ R3 n/a | ✓/n/a/✓/✓/✓ | 否 | 未见语义硬伤。 |
| `02_capabilities/predict/mvp1-alignment.md` | R0✓ R1 FAIL R3✓ | ✓/✓/✓/⚠/✓ | 否 | S-01: Kiro SSOT 泄漏。 |
| `02_capabilities/publish/baseline.md` | R0✓ R1✓ R3 n/a | ✓/n/a/✓/⚠/✓ | 否 | 迁移安全网残留。 |
| `02_capabilities/publish/mvp1-alignment.md` | R0✓ R1✓ R3✓ | ✓/✓/✓/✓/✓ | 否 | 与 06_eval 低优先/Artifact Registry 口径一致。 |
| `02_capabilities/run-execution/baseline.md` | R0✓ R1✓ R3 n/a | ✓/n/a/✓/⚠/✓ | 否 | 迁移安全网残留。 |
| `02_capabilities/run-execution/mvp1-alignment.md` | R0✓ R1✓ R3✓ | ✓/⚠/✓/✓/✓ | 否 | 决策表动机偏模板; 04 workflow finality 足。 |
| `02_capabilities/skill-workspace/baseline.md` | R0✓ R1✓ R3 n/a | ✓/n/a/✓/⚠/✓ | 否 | 迁移安全网残留。 |
| `02_capabilities/skill-workspace/mvp1-alignment.md` | R0✓ R1✓ R3✓ | ✓/⚠/✓/✓/✓ | 否 | PM 动机偏薄, 未见硬冲突。 |
| `02_capabilities/studio-settings/baseline.md` | R0✓ R1✓ R3 n/a | ✓/n/a/✓/⚠/✓ | 否 | 迁移安全网残留。 |
| `02_capabilities/studio-settings/mvp1-alignment.md` | R0✓ R1✓ R3✓ | ✓/✓/✓/✓/✓ | 否 | ③b 归属与 ux-spec/README 基本一致。 |
| `02_capabilities/trace-observability/baseline.md` | R0✓ R1✓ R3 n/a | ✓/n/a/✓/⚠/✓ | 否 | 迁移安全网残留。 |
| `02_capabilities/trace-observability/mvp1-alignment.md` | R0✓ R1✓ R3✓ | ✓/⚠/✓/✓/✓ | 否 | Q2 偏模板; trace/dot 主语义一致。 |

### 3.2 regions: 24 档

| 档 | R | Q1/Q2/Q3/Q4/Q5 | FROZEN | 备注 |
|---|---|---|---|---|
| `03_regions/assets/baseline.md` | R0✓ R1✓ R3 n/a | ✓/n/a/✓/⚠/✓ | 否 | 迁移安全网残留。 |
| `03_regions/assets/mvp1-alignment.md` | R0✓ R1✓ R3✓ | ✓/⚠/✓/✓/✓ | 否 | 动机偏模板。 |
| `03_regions/canvas/baseline.md` | R0✓ R1✓ R3 n/a | ✓/n/a/✓/⚠/✓ | 否 | 迁移安全网残留。 |
| `03_regions/canvas/mvp1-alignment.md` | R0✓ R1✓ R3✓ | ✓/✓/⚠/✓/✓ | 否 | Q3-02 unit 映射漂移。 |
| `03_regions/center-action-bar/baseline.md` | R0✓ R1✓ R3 n/a | ✓/n/a/✓/⚠/✓ | 否 | 迁移安全网残留。 |
| `03_regions/center-action-bar/mvp1-alignment.md` | R0✓ R1✓ R3✓ | ✓/⚠/✓/✓/✓ | 否 | 动机偏模板。 |
| `03_regions/copilot/baseline.md` | R0✓ R1✓ R3 n/a | ✓/n/a/✓/⚠/✓ | 否 | 迁移安全网残留。 |
| `03_regions/copilot/mvp1-alignment.md` | R0✓ R1✓ R3✓ | ✓/✓/✓/✓/✓ | 否 | 未见硬冲突。 |
| `03_regions/editor/baseline.md` | R0✓ R1✓ R3 n/a | ✓/n/a/✓/⚠/✓ | 否 | 迁移安全网残留。 |
| `03_regions/editor/mvp1-alignment.md` | R0✓ R1✓ R3✓ | ✓/✓/⚠/✓/✓ | 否 | Q3-03 unit 映射漂移。 |
| `03_regions/input/baseline.md` | R0✓ R1✓ R3 n/a | ✓/n/a/✓/⚠/✓ | 否 | 迁移安全网残留。 |
| `03_regions/input/mvp1-alignment.md` | R0✓ R1✓ R3✓ | ✓/⚠/✓/✓/✓ | 否 | 动机偏模板, 未见硬冲突。 |
| `03_regions/local-history/baseline.md` | R0✓ R1✓ R3 n/a | ✓/n/a/✓/⚠/✓ | 否 | 迁移安全网残留。 |
| `03_regions/local-history/mvp1-alignment.md` | R0✓ R1✓ R3 FAIL | ✓/✓/⚠/✓/✓ | 否 | S-04 frontmatter stale。 |
| `03_regions/properties/baseline.md` | R0✓ R1✓ R3 n/a | ✓/n/a/✓/⚠/✓ | 否 | 迁移安全网残留。 |
| `03_regions/properties/mvp1-alignment.md` | R0 FAIL R1✓ R3 FAIL | ✓/✓/⚠/✓/✓ | 否 | S-05 + Q3-06。 |
| `03_regions/settings/baseline.md` | R0✓ R1✓ R3 n/a | ✓/n/a/✓/⚠/✓ | 否 | 迁移安全网残留。 |
| `03_regions/settings/mvp1-alignment.md` | R0✓ R1✓ R3✓ | ✓/✓/✓/✓/✓ | 否 | ③b 投影/前端渲染边界一致。 |
| `03_regions/shell-layout/baseline.md` | R0✓ R1✓ R3 n/a | ✓/n/a/✓/⚠/✓ | 否 | 迁移安全网残留。 |
| `03_regions/shell-layout/mvp1-alignment.md` | R0 FAIL R1✓ R3 FAIL | ✓/✓/⚠/✓/✓ | 否 | S-06 breadcrumb 测试残留。 |
| `03_regions/timeline/baseline.md` | R0✓ R1✓ R3 n/a | ✓/n/a/✓/⚠/✓ | 否 | 迁移安全网残留。 |
| `03_regions/timeline/mvp1-alignment.md` | R0✓ R1✓ R3✓ | ✓/✓/⚠/✓/✓ | 否 | Q3-01 unit 映射漂移。 |
| `03_regions/welcome/baseline.md` | R0✓ R1✓ R3 n/a | ✓/n/a/✓/⚠/✓ | 否 | 迁移安全网残留。 |
| `03_regions/welcome/mvp1-alignment.md` | R0✓ R1✓ R3✓ | ✓/⚠/✓/✓/✓ | 否 | 动机偏模板, 未见硬冲突。 |

范围外但影响索引: `03_regions/README.md:19` 仍写 `RunDetailDrawer/BatchSummary ownership待定`, 与 `local-history/mvp1-alignment.md:40-45` 的已决口径冲突。README 不在 63 档内, 但后续清理时应一并修。

### 3.3 platform/i18n: 11 档

| 档 | R | Q1/Q2/Q3/Q4/Q5 | FROZEN | 备注 |
|---|---|---|---|---|
| `04_platform/engine/baseline.md` | R0✓ R1✓ R3 n/a | ✓/n/a/✓/⚠/✓ | 否 | 迁移安全网残留。 |
| `04_platform/engine/mvp1-alignment.md` | R0✓ R1✓ R3✓ | ✓/⚠/⚠/✓/✓ | 否 | Q3-07 unit 映射漂移; engine contract 只引用 SSOT 的方向正确。 |
| `04_platform/gateway/baseline.md` | R0✓ R1✓ R3 n/a | ✓/n/a/✓/⚠/✓ | 否 | 迁移安全网残留。 |
| `04_platform/gateway/mvp1-alignment.md` | R0✓ R1✓ R3✓ | ✓/✓/⚠/✓/⚠ | 否 | Q3-10; 定义句 `:15` 可改成“Studio consumption boundary”以免误读 owns ③b。 |
| `04_platform/i18n.md` | R0✓ R1✓ R3✓ | ✓/✓/✓/✓/✓ | 否 | Strategy C 与 §5.1 Copilot prompt carve-out 自洽; engine/gateway 零改动边界清楚。 |
| `04_platform/llm-copilot-http-api/baseline.md` | R0✓ R1✓ R3 n/a | ✓/n/a/✓/⚠/✓ | 否 | 迁移安全网残留。 |
| `04_platform/llm-copilot-http-api/mvp1-alignment.md` | R0✓ R1✓ R3✓ | ✓/✓/⚠/⚠/✓ | 否 | Q3-09; `:75` 迁移附录残留。 |
| `04_platform/native-fs/baseline.md` | R0✓ R1✓ R3 n/a | ✓/n/a/✓/⚠/✓ | 否 | 迁移安全网残留。 |
| `04_platform/native-fs/mvp1-alignment.md` | R0✓ R1✓ R3✓ | ✓/✓/⚠/✓/✓ | 否 | Q3-11 sidecar gate unit 映射可细化。 |
| `04_platform/state-engine/baseline.md` | R0✓ R1✓ R3 n/a | ✓/n/a/✓/⚠/✓ | 否 | 迁移安全网残留。 |
| `04_platform/state-engine/mvp1-alignment.md` | R0✓ R1✓ R3✓ | ✓/✓/⚠/✓/✓ | 否 | Q3-08 unit 映射漂移; `:40-45` 的 trace 语义 vs state implementation 解释可保留但需写清切面。 |

## 4. 去旧版 / SSOT 债

- 硬泄漏只确认 1 处: `predict/mvp1-alignment.md:51` 的 Kiro 归属。
- 未发现 mvp1 63 档中把 `.kiro`、mvp0、`_reorg/alignment-notes` 当当前 SSOT 的系统性引用。
- `_migrated-coverage-drift.md` 链接是迁移期安全网, 不是弃用 SSOT 硬失败；但 FROZEN 前建议统一删除或改为“实现校验附录, 不参与设计真理”。

## 5. 真空债

本次未发现 03-06 主线“PM 未签导致的大真空”。当前真空/同步债更具体:

1. HitL UI surface: 需要把 workflow 旧“顶部问题框”和后续“节点 debug bar 上方富文本输入框”收成一份当前 SSOT。
2. Golden negative boundary: golden-eval、properties、editor、input 的正负职责要一次性统一, 尤其 Properties 不能再出现在 inputs/positive links。
3. Event-to-node-state 切面: `trace-observability` 负责语义, `state-engine` 负责共享状态投影, `canvas` 负责渲染。多处文档写法已接近正确, 但 unit 表需要消歧。
4. Locking pipeline: DESIGN_UNITS_INDEX 仍全部 drafted, 机器锁/哈希锁未接, 所以即使语义修完也不能直接宣称 FROZEN。

## 6. 建议修复顺序

1. 先修 6 个 P0 硬 FAIL: S-01 到 S-06。
2. 再批量修 Q3 unit 映射表: timeline/canvas/editor/properties/engine/state-engine/gateway/llm-copilot-http-api/native-fs/file-editing/graph-authoring。
3. 最后处理 Q2/Q4 清理: 补真实“为什么/约束”, 清理迁移安全网链接, 更新范围外 `03_regions/README.md` 的 ownership 待定残留。
