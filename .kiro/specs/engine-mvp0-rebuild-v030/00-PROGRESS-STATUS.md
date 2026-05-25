# V0.3.0 Engine MVP0 Rebuild — 任务进度状态 (被打断快照)

> **用途**: 2026-05-25 服务器崩溃 + GRAPH.md 格式 ground truth 恢复事件打断了 round-14 实施。本文件记录被打断时的完整任务状态, 防止再次丢失。
> **唯一格式权威**: `docs/engine/skill-spec/00-FORMAT-GROUND-TRUTH.md` (PM 拍板恢复的双轨制真相)。
> **最后更新**: 2026-05-25 (parent master, 分支 `feat/round-14-skill-compilation-cutover`)

---

## §1 全程 PR 序列 todolist (V0.3.0 完整)

> 显式 todolist 同步在 Task 工具 (TaskList 可查, task #12-#21)。
> **🔴 PR 流程铁律 (PM 2026-05-25)**: 每个 PR 做完**必须清空 a1/a2/a3 的 context** (`ccb ask <agent> /clear` 或 tmux keystroke `/clear`) 再开下一个 PR, 否则 agents context 越堆越多、注意力失焦严重。下一 PR brief 必含"读 ground truth + tasks.md + 上一 PR report"重建 context。

| # | Round/组 | PR | 范围 | 状态 |
|---|---|---|---|---|
| 1 | round-9 | PR α | Gateway 抽独立 package + LLM Roles Phase 1 | ✅ merged (934709e) |
| 2 | round-10 | PR γ0 | Agent AST/loader exit_contract removal + validator + middleware order 契约补丁 | ✅ merged (#92) |
| 3 | round-11 | PR β | Middleware refactor + CognitiveFlow 接管 finish_task/ask_clarification | ✅ merged (#93) |
| 4 | round-12 | PR δ | Skill Resolution hard cutover (engine + Studio + SUBGRAPH) | ✅ merged (#94) |
| 5 | round-13 | PR γ2 | State/IO Isolation 三区 state breaking cutover | ✅ merged (#95) |
| 6 | round-14 | PR skill-compilation | Task B (AgentNodeAST/loader/GRAPH双轨/body 5标签/mention/subgraph/inline io) — **含 ground truth 恢复后重做 (step 1-9 见 §7/§8)** | 🔄 进行中 (重做) |
| 7 | 待定 round | PR C 组 | execution-runtime: cognitive 8插槽 / reference reader / read_reference+read_example tools / ActionRegistry / e2e | ⏳ pending (PR 拆分待规划) |
| 8 | 待定 round | PR E 组 | tracing: AMBIGUITY_LOGGED / BUILTIN_SUBAGENT events / fallback payload | ⏳ pending |
| 9 | 待定 round | PR F 组 | 错误码: 退役 [F-v21-*] / standard error payload | ⏳ pending |
| 10 | 待定 round | PR G 组 | schema cleanup: V2.1主路径/codemod/parser stub/fixture/context_mapping/python_callable 全清 (cutover 收尾) | ⏳ pending |

**注**: round 9-13 代码全已进 main。round-14 是当前工作 (ground truth 恢复后重做中)。后续 7-10 的 PR 边界 (拆几个 round) 待 round-14 完成后规划。

---

## §2 ⚠️ 核心事件: GRAPH.md 格式 ground truth 恢复 (round-14 错误前提)

### 污染链 (PM 2026-05-25 揭示)

1. **第一污染源**: commit `e485261` (5-23) 把 `docs/engine/skill-spec/02-graph-md-spec.md` 写成**纯 YAML phases**(删了 body `<phase>` XML), 违反 PM "phase 写 body XML" 拍板。
2. 5-24 PM 重新拍板**双轨制定稿** + 打印 4 文件模版二次确认, 但**只存 `/tmp/`** → 服务器崩溃丢失。
3. round-14 spec 四件套 (`4a794e7`) + 顶层 `tasks.md` **B3** 继承了"删 `<phase>`"的错误理解。
4. a1 基于错误 spec 写了 round-14 src + test (当前 WIP modified files)。

### 已恢复的真相 (写进 ground truth)

GRAPH.md **双轨制 (DUAL-TRACK)**:
- frontmatter `phases:` = phase 名字 list[str] (注册)
- body `<phase depends_on="X" output>name</phase>` XML = DAG 拓扑
- **两者都必须存在**, 不是二选一。

### 受污染需修正的文件清单

| 文件 | 污染内容 | 修正方向 |
|---|---|---|
| `docs/engine/skill-spec/02-graph-md-spec.md` | 纯 YAML phases (删 XML) | 回归双轨制 |
| `docs/engine/skill-spec/01,03-12-*.md` | 可能受牵连 | 按 ground truth 逐份校 |
| `.kiro/specs/.../tasks.md` B3 | "GRAPH.md `<phase/>` 改为 phases: YAML list" | 改回双轨 |
| `.kiro/specs/.../tasks.md` B2 | mode 三值化 (要求作者写 mode) | ground truth 定 mode frontmatter **删除** (loader 从文件名注入) |
| `.kiro/specs/.../tasks.md` C2 | "Cognitive Template 7 插槽" | ground truth §5 定 **8 插槽** |
| round-14 spec 四件套 | 删 `<phase>` 前提 | 重做 |
| round-14 src + test (WIP) | 实施了错误前提 | 重做 (非全推翻, 见 §4) |
| `manifest.py:106` | `schema_version: Literal["0.3.0"]` 无 v | 改 `"v0.3.0"` |
| `loader.py:625` | `_validate_mode_matches_filename` 要求作者写 mode | 删 (纯文件名推导) |
| `cognitive/prompt.py` | cognitive template 自创 7 插槽 (commit 8d60106), 缺 knowledge_base 装载 subagent / read_reference / read_example | 按 ground truth §5 重写 8 插槽 |

---

## §3 ground truth 确认进度

`docs/engine/skill-spec/00-FORMAT-GROUND-TRUTH.md` (commit 684be1e→bfb8eff→790d780→77aad8d):

- §0 全局规则 / §1 GRAPH.md 双轨 / §2 LOGIC.md / §3 SUBGRAPH.md / §4 SKILL.md / §5 Cognitive Template 8 插槽 / §6 跨文件规则 — **待 PM 逐节确认 (对/错/错在哪)**
- §7 字段状态: schema_version ✅v0.3.0 / mode ✅删 / SkillResolverProtocol ✅认可 / target_skill key ✅PM 认可(功能正常即可) / @type ✅PM 无异议 / 错误码 ✅agents 设计功能正常即可 / **exit_contract 缺 md 格式约定 ⏳待补**(设计阶段补措辞, 非 PM 拍)

---

## §4 round-14 重做范围 (非全推翻)

round-14 src 改动里**方向可能对**的 (待逐条 grep diff 精校):
- B1 SkillNodeAST → AgentNodeAST ✅方向对
- B4 根 IO 物理文件退役 → inline io ✅方向对
- B5 Agent body XML 5 类标签 (禁 `<steps>` 壳) ✅方向对
- B6 `@type:NAME` mention 校验 ✅方向对
- B7 SUBGRAPH target_skill ✅方向对

**确定错的** (需修正):
- B3 GRAPH.md 删 `<phase>` XML → 必须回归双轨
- B2 mode 三值化要求作者写 mode → 删 mode frontmatter
- C2 cognitive 7 插槽 → 8 插槽

**待精校**: 逐个 `git diff` round-14 modified src/test, 标出受 B3/B2 错误前提影响的具体行。

---

## §5 规划内剩余任务 (tasks.md A-G, 待 round 覆盖核对)

tasks.md 共 A-G 约 40 个原子任务。已知 round 9-13 覆盖了 A(skill-resolution→δ) / C middleware 部分(β/γ0) / D(state-io→γ2) / gateway+llm_roles(α)。**精确映射待逐 round design 核对**。

明确**尚未做**的大块:
- **B 组 skill-compilation** (round-14, 重做)
- **C 组剩余**: C2 cognitive template 8 插槽 / C4 reference reader 装配 / C5 read_reference+read_example tools / C7 ActionRegistry / C8 e2e
- **E 组 tracing** (E1-E4)
- **F 组 错误码** (F1-F2)
- **G 组 schema cleanup** (G1-G8: V2.1 主路径/codemod/parser stub/fixture/context_mapping/python_callable 全清)

---

## §6 Loose Ends

- round-13 PR γ2 spec 目录在当前 working tree 是 **untracked** (`?? round-13-PR-gamma2-state-io-isolation/`), 虽然代码已 merge (#95)。需确认是否补 commit spec 文档。

---

## §7 下一步决策 (已定: 先修)

ground truth 恢复 → **先修污染源 + 重做 round-14, 再继续 C/E/F/G**。理由见 §8。即时前置 gate = PM 确认 ground truth §0-§6。

## §8 三方 cross-check 收敛 (2026-05-25, a1+a2+a3)

PM 指示"让 agents 过一遍, 统一就执行"。三方独立评估 §7 顺序, **大方向认可** (step 1→4 排序无依赖倒置 / redo 范围 B1/B4/B5/B6/B7 方向对 + B2/B3/C2 判错准, 没把对的当错或反之)。catch 出以下修正 (主控已 grep verify 为真):

### 8.1 污染范围比 §2 宽 — 已部分 ship 到 main (verify 真)

| 文件 | 污染 | 状态 |
|---|---|---|
| `core/graph_serializer.py:34,41` | 序列化硬编码 `schema_version: "0.3.0"` 无 v + `phases:` 纯 YAML (无 body `<phase>`) | **已 merge 到 main** |
| `core/loader.py:642,647` | 硬编码 `!= "0.3.0"` + 错误消息 `must be exactly "0.3.0"` | round-14 WIP, 只改 manifest 漏 loader → FATAL 拒正确 v0.3.0 |
| `tests/fixtures/v030_agent_demo/GRAPH.md` 等 | pre-existing fixture 纯 YAML 无 `<phase>` (e485261 时代) | **已在 main**, 非 round-14 新建 |
| 十余处已 merge test (`test_v030_agent_compilation` / `gamma0` / `gamma2_*` / `delta` / gateway `test_model_resolver_protocol`) | 硬编码 `schema_version: "0.3.0"` 无 v | **已在 main** |
| docs `01-physical-layout`(mode↔路径校验) / `03,04,05`(frontmatter mode) / `05,08,09,11,12`(example type:inline/content) / `06`(7 插槽旧 placeholder) | a1 指出; a3 提醒别 blanket: `01` 可能仅目录命名没污染, `06` 需逐句校 | 修文档时 grep 精确, 逐份校 |

**含义**: 修复范围 = round-14 重做 + **sweep 已 merge 的 graph_serializer + 全部 GRAPH.md fixture + 十余处 test**, 不只 round-14 modified。

### 8.2 采纳的顺序修正

1. **step 5 折叠进 step 4** (三方共识): schema_version+v / 删 mode 校验是 round-14 src (`loader`/`manifest`/`serializer`) 范围, 必须跟 src 重写同步, 割裂会导致 step4 写的 test 在 step5 崩。
2. **加 grep gate** (a3, round-14 merge 前): 任何 `GRAPH.md` 缺 body `<phase>` = fail; 任何 `schema_version "0.3.0"` 无 v = fail。防漏扫旧 fixture。
3. **B3 防半恢复** (a3): `depends_on` 必须在 body `<phase depends_on=...>`, loader 从 body XML 读拓扑, 不是 frontmatter YAML (否则"恢复 `<phase>` 当显示却仍从 YAML 读 depends_on" = 半恢复, 违反 R1.1)。
4. **B5 补全** (a1+a3): body 5 类 = role/goal/step/protocol/example (**不是 exit_contract**); 补 `manifest.ExampleSpec` body `<example>` 解析 (inline example 当前塞 frontmatter content 是反逻辑, 补全非推翻)。

### 8.3 待收敛分歧 (step 4 时 a1+a3 round 2)

**`prompt.py` cognitive 8 插槽重写放哪?**
- a1+a2: 放进 round-14 同 PR (单独 commit), 实施连续性 (B5 body 解析跟 template 消费耦合, 不一起做没法验证)
- a3: 移出, 作 round-14 merge 后独立 Task-C round (prompt.py 属 Task C, STATUS §5 自列 C 组; 塞进来 round-14 横跨 B+C 违反 SOP-08 一 PR 一 cohesive 组)

真张力 (cohesive vs 连续性), 非信息不对称。**到 step 4 (基于对的 spec 重写 src) 时派 a1+a3 round 2 辩论收敛 PR 边界**, 不现在拍。
