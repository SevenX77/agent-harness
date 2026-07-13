# Tasks — studio-runtime-import-intent-model

> **Status: 随 design.md（operator 2026-07-13 三态裁决，d1 执笔落地论证；待 operator 确认后派实施）。** 本文件是 design.md 的 TDD 转写，不含新设计决策。
> **依据**：`design.md`（§2 三态 / §3 refresh 重构点 C1–C6 / §4 迁移 / §5 测试矩阵 / §6 红线）。
> **TDD 铁律（每任务顺序）**：**① 先写 RED**（测试名 + 断言目标**照抄 design §5**，不臆造）→ **② 实施**（对着 RED 变绿，形状照 §3）→ **③ 自验**（RED 转绿 + 回滚自检 + CI 门禁）。
> **拓扑（classic）**：全部实施归 **实施线（c1/c2，master 后续派单二选一或都派，本文件不点名）**——全链路自写自测 TDD；**审核 = r1**（只审不写，回滚自检必跑）。d1 不碰 src/tests。
> **断言锚**：`refresh_runtime_config` / 移除端点返回 config 的 `inputs.manifest`/`inputs.active`/`inputs.removed`；引擎侧 `runtime_input_fields_for_engine` 输出。落 `apps/studio/backend/tests/services/`（与 `test_runtime_config_io_conflicts.py` 同域）。

## 范围边界（design §0.4 精神）
- **In**：`apps/studio/backend/app/services/runtime_config.py` 三态数据模型 + reconcile-refresh + 移除/恢复端点 + v1→v2 regenerate 迁移 + 引擎只消费 active。
- **Out**：不改 io.inputs 声明 SSOT（F3，勾选写 md 归 native-fs/前端，不在本稿）；不改前端配置树渲染（另单，本稿只保证后端三态契约正确）；不改 conflict 语义（只保不回退）。
- **纯边界**：三态持久归 studio backend；引擎只经 `compile_skill(runtime_input_fields=…)` 消费 active，不反向依赖。

---

## Task T1 — R1 三态持久化 + 复活修复（核心 · C1/C3）
- **归属**：实施线（c1/c2）
- **① RED（照抄 §5 R1）**

| 测试名 | 断言目标 |
|---|---|
| `test_refresh_preserves_active_binding_not_overwritten` | active 字段跨 refresh 不被 scan 覆盖 |
| `test_refresh_does_not_resurrect_removed_candidate` | removed 字段跨 refresh 不复活到 active（复活 bug 反锚） |
| `test_manifest_rederived_each_refresh` | manifest 反映当前磁盘候选（增/删同步） |
| `test_three_states_mutually_exclusive` | 任一 `(scope,field)` 恰属 {active,removed,candidate-only} 之一 |

- **② 实施（design §3 C1/C3）**
  - `default_runtime_config`（`runtime_config.py:35-51`）改 v2 形状：`inputs: {import_root, manifest, active:{root:{},phases:{}}, removed:{root:[],phases:{}}, conflicts}`；**删顶层 `root`/`phases`**（并入 `active`）。
  - `refresh_runtime_config`（`:83-96`）由「覆盖 root/phases/manifest/conflicts」改 **reconcile**：`manifest`/`conflicts` 覆盖（派生）；`active`/`removed` **读旧值保留**，只按 §2 规则演进（不覆盖 active、不复活 removed）。
- **③ 自验**：四条 RED 全绿；**回滚自检**——把 reconcile 还原成旧「覆盖」写法 → `test_refresh_does_not_resurrect_removed_candidate` 必须由绿转红（证明复活修复是真锚）。CI：`ruff` · `mypy apps/studio/backend/app` · `pytest apps/studio/backend/tests`。

## Task T2 — R2 auto-match 幂等（C2）
- **归属**：实施线（c1/c2）
- **① RED（照抄 §5 R2）**

| 测试名 | 断言目标 |
|---|---|
| `test_auto_match_activates_new_matching_candidate` | 新候选 normalize 命中已声明 io.inputs 字段 → 自动进 active（F5） |
| `test_auto_match_suppressed_for_removed_field` | removed 字段的命中候选**不**自动激活（幂等核心） |

- **② 实施（design §3 C2）**：`_bindings_from_entries`（`:473`）/`_scan_import_files`（`:203`）拆两职责——产出 candidate 全集（manifest）+ auto-match 建议（命中 io.inputs 且**不在 removed** 的新候选）；不再把「全部候选」等同 active。auto-match 分支须查 removed 墓碑再决定是否激活。
- **③ 自验**：两条 RED 绿；回滚自检——去掉 removed 查询 → `test_auto_match_suppressed_for_removed_field` 转红。CI 同 T1。

## Task T3 — R3 active 源生命周期（C1）
- **归属**：实施线（c1/c2）
- **① RED（照抄 §5 R3）**

| 测试名 | 断言目标 |
|---|---|
| `test_active_binding_descriptor_refreshed_from_current_file` | active 字段文件改名/换目录/批量号变 → 字段仍 active，binding 描述子按当前候选刷新 |
| `test_active_source_missing_surfaced_not_deleted` | active 字段候选文件被删 → 不静默移出 active，标 `source-missing` |

- **② 实施**：reconcile 内对 active 字段：有当前候选 → 重派生 binding 描述子；无候选 → 标 `source-missing`（不删）。镜像 F3 missing 态精神（design §2）。
- **③ 自验**：两条 RED 绿；回滚自检——把 source-missing 改成静默删 → `test_active_source_missing_surfaced_not_deleted` 转红。CI 同 T1。

## Task T4 — R4 移除/恢复端点 + 引擎消费边界（C4/C5）
- **归属**：实施线（c1/c2）
- **① RED（照抄 §5 R4）**

| 测试名 | 断言目标 |
|---|---|
| `test_remove_binding_persists_tombstone_survives_refresh` | 移除端点写 removed 墓碑，跨 refresh 存活 |
| `test_restore_removed_candidate_reactivatable` | 恢复端点使字段出 removed、可再 active |
| `test_engine_runtime_input_fields_reads_active_only` | `runtime_input_fields_for_engine` 只吐 active；removed/candidate-only 不泄漏进引擎 |

- **② 实施（design §3 C4/C5）**
  - 新增服务函数 + 端点（`services/runtime_config.py` + `routers/runtime_config.py`）：把 `(scope,field)` 从 active 移入 removed（写墓碑，持久）+ 逆操作（从 removed 恢复）；写后照常 `write_runtime_config` 持久化。
  - `runtime_input_fields_for_engine`（`:99-111`）改读 `inputs["active"]["phases"]`（不再读旧 `inputs["phases"]`）——引擎只消费 active。
- **③ 自验**：三条 RED 绿；回滚自检——`runtime_input_fields_for_engine` 改回读 manifest/candidate → `test_engine_runtime_input_fields_reads_active_only` 转红。CI 同 T1（+ 若触及引擎消费面，跑 `pytest packages/graph-agent/tests` 相关）。

## Task T5 — R5 迁移 no-backward-compat（C3/§4）
- **归属**：实施线（c1/c2）
- **① RED（照抄 §5 R5）**

| 测试名 | 断言目标 |
|---|---|
| `test_v1_config_regenerated_not_translated` | 读 v1（root/phases、无 active/removed）→ 结果 v2、有 active/removed、manifest 重扫重建、无 v1 root/phases 顶层残留 |
| `test_migration_has_no_dual_format_branch` | 读取路径不因 v1 保留旧绑定（无兼容分支）；v1 import 槽丢弃重建 |
| `test_non_import_slots_survive_migration` | 迁移只重建 import 三态；node_llm_params/compare_candidates/artifacts 不丢 |

- **② 实施（design §4）**：`_SCHEMA_VERSION`（`:15`）→ `"studio.runtime_config.v2"`；`read_runtime_config`（`:54-63`）见非 v2/缺 active|removed → 丢弃 `inputs` 下 import 旧槽（root/phases/manifest/conflicts）、`active={}`/`removed={}` 起步，交下次 reconcile-refresh 重建。**不写 v1→v2 翻译 shim、不写双格式分支**。非 import 槽经 `_deep_update` 照常保留。
- **③ 自验**：三条 RED 绿；回滚自检——加一条「保 v1 root/phases」的兼容分支 → `test_migration_has_no_dual_format_branch` 转红（证明确无兼容路径）。CI 同 T1。

## Task T6 — R6 契约不回归（守护）
- **归属**：实施线（c1/c2），随 T1–T5 同交付包收尾守护。
- **① RED/守护（照抄 §5 R6）**

| 测试名 | 断言目标 |
|---|---|
| `test_conflict_detection_unchanged` | 同 scope 多候选撞同字段仍进 `inputs.conflicts` + `STUDIO_RUNTIME_INPUT_CONFLICT` 不回退 |
| `test_import_into_workspace_still_surfaces_candidates` | 导入流程仍把候选写进 manifest |

- **②/③**：不变量守护，T1–T5 期间保持其绿；转红即说明改动破坏既有契约，回炉。

---

## 验收清单 — design §6 红线（r1 审核逐条核 + 回滚自检）
1. 不放宽既有检查（conflict / io.inputs SSOT 不动，只加意图层）。
2. 无向后兼容 shim（v1→v2 直接 regenerate，无双格式分支）。
3. 第一性非补丁（改数据模型三态 + reconcile，非覆盖时序特例）。
4. 让非法状态不可表示（三态互斥；refresh 只演进不违约：不复活、不覆盖 active、不静默删）。
5. 模块边界即落点（三态/reconcile 落 studio backend；io.inputs 归 md；引擎只消费 active）。

**全 spec DoD**：T1–T6 全 RED→绿；五条红线 r1 逐条核过（含各任务回滚自检）；CI 全绿（`ruff` / `mypy apps/studio/backend/app` / `pytest apps/studio/backend/tests`；触及引擎消费面则加 `pytest packages/graph-agent/tests`）。PR 可多 PR 落地，排期由 master 编排。

## 遗留 / 待拍板（design §7）
- **auto-match 默认自动激活 vs 只建议**：本稿据 FROZEN 设计 F5「命中即自动勾选」默认**自动进 active**（幂等由 removed 保证）。若 PM 改「只建议不自动激活」，仅调 T2 的 auto-match 分支，三态/reconcile 骨架不变——登记待 operator/PM 一句确认，不阻塞 T1/T3/T4/T5。
- 前端配置树按三态渲染（candidate/active/removed 的 UI 呈现 + 移除/恢复交互）= 另单（本稿只交付后端三态契约）。

## 完成后回写
- 合并后在 `.kiro/specs/INDEX.md` 登记一行（Implemented）。
- INDEX「遗留/跨项」栏备注前端三态渲染另单。
