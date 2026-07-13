# Design — Studio runtime import 显式意图三态模型 (studio-runtime-import-intent-model)

> **Status: 操作者裁决已定（2026-07-13 operator 直投 #28）——采「显式意图层三态模型」（自动发现候选 manifest + 用户选择 active bindings + removed intent），依据 AGENTS.md「First-principles fixes, not patches」+「让非法状态不可表示」。本稿由 d1 执笔做「论证落地」（证据绑定 + 机制 + 三态定义 + refresh 重构点 + no-backward-compat 迁移），不重开三态决策本身。** d1 不自宣 FROZEN；落地论证待 operator 确认后由 master 派 c1/c2 实施。
> **权威对照基线**
> - 代码：`apps/studio/backend/app/services/runtime_config.py`（`refresh_runtime_config` / `_scan_import_files` / `_bindings_from_entries`）· `apps/studio/backend/app/routers/runtime_config.py` · `routers/io_scan.py`
> - **MVP1 设计源（source of truth）**：`docs/studio/mvp1/03_regions/input/mvp1-alignment.md`（FROZEN，input region owner；F3 输入配置树 + F5 扫描/自动匹配/manifest + line 42 candidate/conflict）
> - **代码基线**：`origin/main`（= 当前 `ops/lane-dispatch` 树），所有 file:line d1 亲验。

---

## §0. 课题根源（一句话 + 实测 bug）

Studio 试跑输入的 runtime import 把「磁盘上扫到的候选文件」直接当成「用户选中的活动绑定」，且**每次刷新全量重算覆盖**——用户删掉/不想要的候选，下一次刷新又从磁盘扫回来复活。根因是**没有一层表示「用户意图」的持久态**：discovered（磁盘有什么）与 active（用户要什么）被压成同一份、且被 removed（用户明确不要）无处安放。这既违反「让非法状态不可表示」（同一字段的三种语义压成一个可被 scan 覆盖的槽），也是「打补丁 vs 第一性」的典型——过去只在覆盖时序上打转，没有从「意图该被表示」这层重构。

---

## §1. 证据（code + 设计源绑定 + 诚实缺口）

### 1.1 code：active 绑定 100% 由磁盘扫描派生、零用户意图、每刷新覆盖（bug 坐实）
- `refresh_runtime_config`（`runtime_config.py:83-96`）：读 config → `_scan_import_files` 全量扫 `import_files/` → **无条件覆盖** `inputs["manifest"]`（:92）、`inputs["root"]`（:93）、`inputs["phases"]`（:94）、`inputs["conflicts"]`（:95）。
- `_bindings_from_entries`（`runtime_config.py:473-495`）：对**每一个**扫出来的候选字段，按 normalize 名去重后**唯一者即生成 binding**（`bindings[candidate["field"]] = candidate["binding"]`，:483），多者进 conflict。**全程不读节点 `io.inputs` 声明、不读任何用户选择/移除状态**——即「凡磁盘上有、名字不撞的候选，一律自动变成活动绑定」。
- 触发面：`GET /runtime-config` 每次都调 `refresh_runtime_config`（`routers/runtime_config.py:32`）；`import_into_workspace` 导入后也调（`routers/io_scan.py:350`）。
- ⇒ **用户对 active 绑定的任何移除都不可持久**：只要候选文件还在盘上，下一次 refresh 就把它重新派生成 active，复活。且今天**根本没有**「保留文件但移除绑定」的可表示状态——要么删文件（连候选一起没了），要么无法移除。

### 1.2 设计源绑定：三态里的两态是权威设计直接支持的
`docs/studio/mvp1/03_regions/input/mvp1-alignment.md`（FROZEN）：
- **active binding = 用户选择（F3）**：`:38`「勾选/取消勾 = **直接修改该节点 md 的 `io.inputs` schema** 并实时保存」；勾中的字段「只写成普通 `io.inputs` JSON Schema 字段，**路径/目录/pattern 留在 `.workspace/runtime_config.json`**」；`:118` r7 点8 复述「checkbox 勾选/取消直接修改 md io.inputs schema」。**⇒ 活动绑定是用户意图的投影，不是「凡扫到就绑」。**
- **candidate manifest = 后端纯读扫描（F5）**：`:60-62`「后端扫描端点解析…候选字段」「IO 面板显示已导入文件时**只读 `.workspace/runtime_config.json` 中当前 scope 的 manifest**」。**⇒ manifest = 派生候选集，权威设计已把它和 binding 分开命名。**
- **candidate ≠ binding，冲突不静默生成 binding（line 42）**：`:42`「同一 scope 下多个 candidate 能匹配同一 schema 字段时，**不静默覆盖、不生成 binding**」。**⇒ 设计已明确「candidate」「生成 binding」是两回事，且反对无差别自动绑定。**
- **刷新即重新派生匹配（F5，line 62）= 复活载体**：`:62`「import_files 文件树刷新、文件内容更新、input schema 改变都必须刷新 runtime_config/**重新派生匹配**」。这条在**缺少 removed 记忆**时，正是「自动匹配把用户取消的又勾回来」的复活向量。

### 1.3 诚实缺口：设计源**没有**显式的「removed intent / 墓碑」态——按第一性补
- 我查了 input region owner `03_regions/input/mvp1-alignment.md`（F2–F8 + §4 PM 原话）、`01_workflows/04_run-and-verify.md`、`01_workflows/02_authoring.md`、以及 `runtime_config.py` 全量：**权威设计定义了 candidate（F5）与 active=io.inputs 勾选（F3），但没有为「保留文件、但用户明确不要这个候选」定义一个持久态**。设计对「移除」的隐含答案是「不在 io.inputs 里就是不活动」，但它同时又要求「自动匹配命中即自动勾选」（`:61`）+「刷新重新派生匹配」（`:62`）——两者叠加在**没有移除记忆**时必然复活。
- **裁定（第一性，非臆造）**：`removed intent` 是让「自动匹配幂等、移除可持久」成立所**必需**的最小状态，且与 FROZEN 设计**不冲突、只补齐**——它把设计里「auto-match 是便利、active 是用户意图」这条精神做实。依据 AGENTS.md「让非法状态不可表示」（同字段三语义必须各有其位）+「first-principles fixes」（在「意图该被表示」这层修，而非在覆盖时序打补丁）。**这一态是 operator 裁决显式点名的「removed intent」，本稿据设计精神 + 第一性把它落地，如实标注它超出 FROZEN 设计的显式条文。**

---

## §2. 三态模型（定义 + 不可表示非法状态的不变量）

**论域**：每个 `(scope, field)`，scope ∈ {`root`, `phase:<phase_id>`}，field = normalize 后的输入字段名。

| 态 | 含义 | 持久性 | 存放 |
|---|---|---|---|
| **candidate（发现态）** | 扫描 `import_files/` 当前 scope 得到的候选字段（含其 binding 描述子：dir/pattern/numbers/value_type…） | **派生、易失**：每次 refresh 从磁盘重算 | `inputs.manifest`（覆盖安全） |
| **active（选择态）** | 用户选中、用来供给一个 io.inputs 声明字段的候选 = 持久化的**用户意图** | **持久**：refresh 不得抹除 | `inputs.active`（新，取代旧 auto-派生的 `root`/`phases`） |
| **removed（移除态）** | 用户明确移除、但文件仍留在盘上的候选墓碑 = 持久化的**否定意图** | **持久**：refresh/auto-match 不得复活 | `inputs.removed`（新） |

**核心不变量（让非法状态不可表示）**：对任一 `(scope, field)`，它在 {active, removed, candidate-only} 中**恰属其一**（互斥且无第四态）。
- `refresh` 对这三态的**唯一合法动作**：① 重算 `manifest`（候选全集，派生）；② 对 active 字段**按当前候选重新派生其 binding 描述子**（文件改名/换目录/批量号变→描述子刷新，但**字段不移出 active**）；③ 把「新出现、未在 active、未在 removed、且 normalize 命中某 io.inputs 声明字段」的候选**自动激活**（auto-match，F5）；④ candidate-only = 扫到但既不 active 也不 removed 也未命中声明的候选（仅陈列，供用户选）。
- `refresh` **绝不允许**：把字段移出 `removed`（复活）、覆盖 `active` 的用户选择、或因某轮扫描没扫到就静默删掉 active（见 §2 source-missing）。

**auto-match 幂等（复活修复核心）**：auto-match 只对「不在 removed」的新候选做自动激活；**removed 里的字段即便有命中候选也不激活**。这一条把 F5「命中即自动勾选」从「每刷新重来」修成「尊重用户否定意图的一次性」。

**active 源失踪（对齐设计 missing 态，F3 line 41）**：active 字段的候选文件本轮扫不到时，**不静默从 active 删除**，而是标 `source-missing`（供 UI 置顶报错「declared active · source file gone」），保留用户意图直到用户显式改选/移除。这镜像 F3 的 missing 三态精神（声明了但没供上 = 报错，不是自动抹）。

> **与 io.inputs SSOT 的关系（不越权改 F3）**：F3 已定「字段是否被声明消费」的真相在节点 md `io.inputs`（勾选写 md）。本三态治的是 **runtime_config 侧「该声明字段用哪个候选文件供给 + 用户对候选的取舍」** 这一层的意图持久化。runtime_config 不是字段声明的 SSOT（那是 io.inputs），它是**「候选→声明字段」绑定意图**的 SSOT。二者不重叠：io.inputs 说「要不要 chapter 这个输入」，runtime_config.active 说「chapter 用盘上哪个候选供给」，runtime_config.removed 说「这个候选用户不要」。

---

## §3. `refresh_runtime_config` 重构点（交实施线，d1 只给形状）

现状（`runtime_config.py:83-96`）= 「scan → 覆盖 root/phases/manifest/conflicts」。改为「scan → **reconcile**（只覆盖派生态，保留意图态）」：

| # | 位置 | 现状 | 改造 |
|---|---|---|---|
| C1 | `refresh_runtime_config`（`:83-96`） | `inputs["root"]=root_bindings` / `inputs["phases"]=phase_bindings` 无条件覆盖 | 改为 reconcile：`manifest`/`conflicts` 覆盖（派生）；`active`/`removed` **读旧值保留**，只按 §2 规则增量演进（新候选 auto-match 入 active、active 描述子按当前候选刷新、扫不到标 source-missing、removed 恒不复活） |
| C2 | `_bindings_from_entries`（`:473`）/ `_scan_import_files`（`:203`） | 返回「所有候选→binding」当 active | 拆成两职责：产出 **candidate 集（manifest，全量）** 与 **auto-match 建议（命中 io.inputs 且不在 removed 的新候选）**；不再把「全部候选」等同 active |
| C3 | `default_runtime_config`（`:35-51`） | `inputs: {import_root, manifest, root, phases, conflicts}` | 改 v2 形状：`inputs: {import_root, manifest, active:{root:{},phases:{}}, removed:{root:[],phases:{}}, conflicts}`；删 `root`/`phases` 顶层（并入 `active`） |
| C4 | `runtime_input_fields_for_engine`（`:99-111`） | 读 `inputs["phases"]`（= 旧 auto 派生绑定） | 改读 `inputs["active"]["phases"]`——**引擎只消费 active**，candidate-only / removed 一律不喂给引擎（保证移除的候选不泄漏进运行期） |
| C5 | 新增「移除/恢复候选」写入口 | 无（今天只能删文件） | 新增服务函数 + 端点：把某 `(scope, field)` 从 active 移进 removed（写墓碑，持久）；及其逆操作（从 removed 恢复→重新可 active）。写完照常 `write_runtime_config` 持久化 |
| C6 | `get_runtime_config` 端点（`routers/runtime_config.py:32`） | GET 即 refresh（覆盖式） | refresh 语义改为 reconcile（C1）后，GET-触发 refresh 不再破坏意图（幂等）；行为保持「GET 返回最新对账结果」，但不再复活 |

**副作用隔离**：reconcile 是纯函数式对账（旧 intent + 新 scan → 新 config），IO（读盘 scan、写 runtime_config.json）保持薄且集中，与现有 `write_runtime_config`（含 file_watcher 回声记录 `:71-79`）复用，不新造写路径。

---

## §4. 迁移（no-backward-compat：直接 regenerate，不留兼容）

- **`_SCHEMA_VERSION`**：`"studio.runtime_config.v1"`（`:15`）→ `"studio.runtime_config.v2"`。
- **不写 v1→v2 翻译 shim、不写双格式读取分支**（AGENTS.md no-backward-compat）。依据：v1 的 `inputs.root`/`inputs.phases` **本就是磁盘扫描的派生产物、零用户意图**（§1.1 坐实）——它们**100% 可由重新扫描重建**，丢弃它们**不丢任何真实意图**（因为 v1 里根本没有可持久的意图）。
- **regenerate 机制**：`read_runtime_config`（`:54-63`）见到非 v2 的 `schema_version`（或缺 `active`/`removed` 键）时，**丢弃 `inputs` 下的 import 相关旧槽（root/phases/manifest/conflicts）**，`active={}`/`removed={}` 起步，交由下一次 reconcile-refresh 从磁盘重建 `manifest` + auto-match 初始化 active。用户的 io.inputs 声明（在 md，另一 SSOT）不动，故「声明了哪些输入」不丢；丢的只是「哪个候选供给」这一层——而那层 v1 本就是自动派生、用户重开面板即按 auto-match 重新命中。
- **落盘数据可弃**：现存 `.workspace/runtime_config.json` 的 v1 import 槽视为一次性，不迁移。node_llm_params / compare_candidates / artifacts 等**非 import 槽**不受影响（迁移只碰 `inputs.*` import 三态，其余槽 `_deep_update` 照常保留）。

---

## §5. 测试矩阵（TDD 框线：测试名 + 断言目标；RED 代码归实施线，d1 只给名+断言+造样）

> 断言锚：`refresh_runtime_config` / 移除端点返回的 config dict 的 `inputs.manifest` / `inputs.active` / `inputs.removed`；引擎侧锚 `runtime_input_fields_for_engine` 输出。落 `apps/studio/backend/tests/services/`（与 `test_runtime_config_io_conflicts.py` 同域）。

### R1 三态持久化 + 复活修复（核心）
| 测试名 | 造样输入 | 断言目标 |
|---|---|---|
| `test_refresh_preserves_active_binding_not_overwritten` | 选中一个 active 绑定，再对同一批文件 refresh | 该字段仍在 `inputs.active`，binding 未被抹（scan 不覆盖 active） |
| `test_refresh_does_not_resurrect_removed_candidate` | 把一候选移入 removed（文件仍在盘），再 refresh | 该字段仍在 `inputs.removed`、**不**出现在 `inputs.active`（复活 bug 反锚） |
| `test_manifest_rederived_each_refresh` | refresh 前后增/删 import 文件 | `inputs.manifest` 反映当前磁盘候选（新增出现、删除消失） |
| `test_three_states_mutually_exclusive` | 构造 active/removed/candidate-only 混合 | 任一 `(scope,field)` 恰属一态；无字段同时在两态 |

### R2 auto-match 幂等
| 测试名 | 造样输入 | 断言目标 |
|---|---|---|
| `test_auto_match_activates_new_matching_candidate` | 新导入一个 normalize 命中已声明 io.inputs 字段的候选 | 该候选自动进 `inputs.active`（F5 auto-match） |
| `test_auto_match_suppressed_for_removed_field` | 已 removed 的字段，refresh 时其命中候选仍在盘 | **不**自动激活（removed 尊重，幂等核心） |

### R3 active 源生命周期
| 测试名 | 造样输入 | 断言目标 |
|---|---|---|
| `test_active_binding_descriptor_refreshed_from_current_file` | active 字段的文件改名/换目录/批量号变，refresh | 字段仍 active，但其 binding 描述子（dir/pattern/numbers）按当前候选刷新 |
| `test_active_source_missing_surfaced_not_deleted` | active 字段的候选文件被删，refresh | 字段**不**被静默移出 active，而标 `source-missing`（供 UI 置顶报错） |

### R4 移除端点 + 引擎消费边界
| 测试名 | 造样输入 | 断言目标 |
|---|---|---|
| `test_remove_binding_persists_tombstone_survives_refresh` | 调移除端点，再 refresh | removed 墓碑持久，跨 refresh 存活 |
| `test_restore_removed_candidate_reactivatable` | 对 removed 字段调恢复端点 | 出 removed、可再被 active（逆操作可用） |
| `test_engine_runtime_input_fields_reads_active_only` | active + removed + candidate-only 混合 | `runtime_input_fields_for_engine` 只吐 active 的字段；removed/candidate-only 不泄漏进引擎 |

### R5 迁移（no-backward-compat）
| 测试名 | 造样输入 | 断言目标 |
|---|---|---|
| `test_v1_config_regenerated_not_translated` | 盘上放一份 v1（含 root/phases，无 active/removed）runtime_config.json，read+refresh | 结果 `schema_version=="studio.runtime_config.v2"`；`inputs.active`/`removed` 存在；manifest 由重新扫描重建；**无 v1 root/phases 顶层残留** |
| `test_migration_has_no_dual_format_branch` | 读 v1 与 v2 | 读取路径不因 v1 保留旧绑定（无兼容分支保 v1 意图）；v1 import 槽被丢弃重建 |
| `test_non_import_slots_survive_migration` | v1 config 含 llm.node_params/artifacts | 迁移只重建 import 三态；node_llm_params/compare_candidates/artifacts 不丢 |

### R6 契约不回归
| 测试名 | 断言目标 |
|---|---|
| `test_conflict_detection_unchanged` | 同 scope 多候选撞同字段仍进 `inputs.conflicts` 并触发 `STUDIO_RUNTIME_INPUT_CONFLICT`（设计 line 42 不回退） |
| `test_import_into_workspace_still_surfaces_candidates` | 导入流程仍把候选写进 manifest（F5 不回退） |

---

## §6. 红线自检
1. **不放宽既有检查**：conflict 检测（`STUDIO_RUNTIME_INPUT_CONFLICT`）、io.inputs SSOT（F3，勾选写 md）不动；本稿只**加**意图持久层，不删既有校验。
2. **无向后兼容 shim**：v1→v2 直接 regenerate，删 v1 import 槽读取路径，不留双格式分支（NFR/no-backward-compat）。
3. **第一性、非补丁**：根因定位到「意图无处表示」，改的是数据模型（三态 + reconcile），不是给 refresh 覆盖时序打特例。
4. **让非法状态不可表示**：三态互斥 + refresh 只能演进不能违约（不复活、不覆盖 active、不静默删）——用结构编码约束，不靠散落 if。
5. **模块边界即落点**：三态持久 + reconcile 落 studio backend（`runtime_config.py`，它本就是 runtime_config owner）；io.inputs 声明仍归 md（native-fs 写）；引擎只消费 active（`runtime_input_fields_for_engine`→`compile_skill(runtime_input_fields=…)`）。不反向泄漏。

---

## §7. 交付说明
- 本稿 = operator 三态裁决的**论证落地**（证据 + 机制 + 三态定义 + 重构点 + 迁移），非重开决策。§1.3 如实标注「removed 态超出 FROZEN 设计显式条文、按第一性补齐、与设计不冲突」。
- **一处需 operator/PM 拍板的小口**（不阻塞实施主体）：auto-match 对「新候选（不在 removed、命中声明）」是**自动进 active** 还是**只高亮建议、待用户勾选**——FROZEN 设计 F5 `:61` 写「命中即自动勾选」，本稿据此默认**自动进 active**（幂等由 removed 保证）。若 PM 后续想改成「只建议不自动激活」，仅调 C2 的 auto-match 分支，三态与 reconcile 骨架不变。
- d1 不自审、不实施；落盘后报 operator，由 master 派 c1/c2 按本稿 + tasks.md 落地（实施线自写自测 TDD，r1 回滚自检把关）。
