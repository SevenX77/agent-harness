# Studio MVP1 — §5 决策表系统性修复映射(unit 归位 + 真实动机)

> **问题**:retrofit 把每个 alignment 的 `## 5. 决策 + 动机` 表的"动机"列写成套话「对齐 X 设计单元，保证实现与测试可回扣」,且**多单元模块的多行决策常全指同一个单元**(unit drift)。
> codex 语义审计的 11 个 Q3 只覆盖约一半;本表是 **29 档全量**(compile-lint 已修、predict 是范例 0 套话)。
> **修法**:每行 = 决策 → **正确 unit**(按该决策切面 + 模块 frontmatter units + `DESIGN_UNITS_INDEX` owner)+ **真实动机**(为什么/约束,从 §2 F-section / §4 PM 原话 / §6 测试 提炼,非套话)。
> **不改代码、不碰 predict、不动已修的 6 P0**。

## 单单元模块(无 unit drift,只补真实动机)
conflict-overwrite · debug-resume · file-editing · golden-eval · graph-authoring · publish · local-history · welcome · shell-layout · assets · input(主 io-panel) — 三行都正确指其唯一/主单元,只把套话动机换成真实"为什么"。

## 多单元模块(unit 归位 + 真实动机)
| 模块 | 决策 → 正确 unit |
|---|---|
| skill-workspace | -1 Open Folder、-2 Import gate → `workspace-open-folder-mru`；**-3 子图 membership → `subgraph-path-inline-drilldown`** |
| copilot-assist | **-1 ThinkingBlock、-2 安全写、-3 session → `copilot-session-persistence`**；-4 SDK 测试 → `copilot-sdk-test-parity` |
| phase-editing | -1 字段白名单、-2 subgraph path 字段 → `phase-field-whitelist`；**-3 role test → `node-properties-role-test`** |
| run-execution | -1 Run 入口、-2 节点态、-3 batch → `run-execution-node-status`；**-4 golden seed → `golden-per-agent-node`** |
| trace-observability | -1 trace 挂载、-2 dot 黑板 → `trace-dot-blackboard`；**-3 节点态 → `run-execution-node-status`** |
| studio-settings | -1 六态 → `settings-six-state-provider-health`；**-2 materialize → `model-group-role-materialization`**；-3 Copilot test → `copilot-sdk-test-parity`；-4 设置不挡壳 → `settings-six-state-provider-health`(壳切面无独立 unit,挂状态 owner) |
| canvas | **-1 节点态 → `run-execution-node-status`**；**-2 dot 黑板 → `trace-dot-blackboard`**；-3 子图 inline → `subgraph-path-inline-drilldown` |
| center-action-bar | -1 Predict/Run wiring → `predict-execution`(+run 消费)；-2 compile drawer、-3 gate → `compile-stage-gate` |
| copilot(region) | -1 session UI、-2 analysis bar、-3 下钻 skillId → `copilot-session-persistence`(SDK test 切面归 `copilot-assist`,本 region 不重写) |
| editor | -1 写路径 → `native-rust-writer`；**-2 inline diagnostics → `compile-lint-structured-error`(消费)**；**-3 golden diff → `golden-per-agent-node`** |
| properties | -1 字段表单 → `phase-field-whitelist`;-2 role test 行 → `node-properties-role-test`；**-2/edge trace → `trace-dot-blackboard`**；-3 golden scope → 负向边界(golden 不在 Properties,标 `golden-per-agent-node` 负向) |
| settings(region) | -1 六态 → `settings-six-state-provider-health`；-2 role materialization UI → `model-group-role-materialization`；-3 Copilot settings → `copilot-sdk-test-parity` |
| timeline | **-1 live trace → `trace-dot-blackboard`**；**-2 run detail → `run-execution-node-status`**；**-3 golden actions → `golden-per-agent-node`** |
| engine | **-1 resume → `debug-resume-checkpoint`**；-2 engine SSOT → 引用 engine SSOT(compile 切面留 `compile-stage-gate`)；**-3 golden/path/schema → `golden-per-agent-node`** |
| gateway | -1 六态 → `settings-six-state-provider-health`；**-2 materialize → `model-group-role-materialization`**；-3 copilot route → `copilot-sdk-test-parity` |
| llm-copilot-http-api | -1 router 边界 → `settings-six-state-provider-health`(③a 壳);-2 Copilot SDK test → `copilot-sdk-test-parity`；**-3 DTO SSOT → `model-group-role-materialization`** |
| native-fs | -1 唯一写者、-2 打包写者 → `native-rust-writer`；**-3 sidecar gate → `shell-runtime-gate`** |
| state-engine | -1 状态源 → `run-execution-node-status`；-2 WS bridge → `run-execution-node-status`(+trace);**-3 sidecar failure → `shell-runtime-gate`** |

> 加粗 = 相对当前(错指)的**改动**。ambiguous 的(如 properties -2/-3、studio-settings -4)修时读正文确认。

## 执行
逐 tier:capabilities(13 剩)→ regions(12)→ platform(5)。每模块同时做:§5 unit 归位 + 真实动机 + 跨小节自洽(§3/§7/F-归属)+ migration 覆盖核。每 tier 提交。
