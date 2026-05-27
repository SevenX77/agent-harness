# V0.3.0 Engine MVP0 Rebuild — 任务进度状态 (被打断快照)

> **用途**: 2026-05-25 服务器崩溃 + GRAPH.md 格式 ground truth 恢复事件打断了 round-14 实施。本文件记录被打断时的完整任务状态, 防止再次丢失。
> **唯一格式权威**: `docs/engine/skill-spec/00-FORMAT-GROUND-TRUTH.md` (PM 拍板恢复的双轨制真相)。
> **最后更新**: 2026-05-26 (parent master, 集成分支 `stage/engine-v030`; main 在 74950f4)

---

## §0 最新状态 (2026-05-26 session, 接续必读)

- **round-14 已 merge 进 main** (#96, squash, commit `74950f4`)。CI quality-gates 绿, 主控亲跑 928 passed 实证过。
- **编译器真实 e2e 已补**: a3 写 + a1 review (4 PASS, 1 NEEDS FIX 已补) + 主控亲跑 **22 passed**。commit `94fc6be`, 以 merge-commit `60c27e7` 并入 `stage/engine-v030`。
- **✅ PR C 组 (execution-runtime) 已完成** (round-15, SOP-08 9 步全走): C1-C8+D4, 双审 catch 2 must-fix (reference path escape 缺口1 + FATAL re-raise 缺口2) 已修。merge-commit `405e63d` 进 `stage/engine-v030`。主控亲跑 981 passed 实证。report 已发 PM (`/tmp/pr-c-report.md`)。
- **✅ PR E 组 (tracing) 已完成** (round-16, SOP-08 9 步全走): E1 AMBIGUITY_LOGGED runtime emission / E2 builtin reference reader ENTER/EXIT/FALLBACK / E3 fallback payload 瘦身 / E4 base.py 注册 4 新事件。tests-first 8 红转绿; a2+a3 双审零 must-fix; docs 字段级同步 + a3 文档审计 2 诚实补强。merge-commit `d3610e8` 进 `stage/engine-v030`。主控亲跑 **989 passed, 3 skipped, 38 xfailed** 实证 (stage 分支 post-merge 也 989 绿)。report 已发 PM (`/tmp/pr-e-report.md`)。
- **🔴 合并工作流变更 (PM 2026-05-26 拍板, 取代每 PR 直接 squash)**: 中间 PR 用 `git merge --no-ff` 进集成分支 `stage/engine-v030` (off main, 保留细粒度历史可 bisect); main 不动。整个 engine 阶段 PM **实测 golden** 后才**先打 tag 再 squash 进 main** 作 golden baseline。**铁律: squash 进 main 前必先打 tag**, 否则 granular 历史变游离对象被 git gc 清掉。详见 memory `[[staged-merge-workflow]]`。
- **✅ PR F 组 (错误码) 已完成** (round-17, SOP-08 9 步全走): F1 退役 `[F-v21-*]` 已完成; F2 standard error payload — 新 ErrorPayload model + error_registry (89 码, 实施期补 2 缺口码 purity-violation + cognitive-output-schema-invalid) autofill level/stage/doc_link; 退役粗码 → 11-spec 细码; 测试断言 message-regex → payload.code (24 文件); must-fix 堵静默失败 None 后门 → fail loud。a2+a3 双审 (catch must-fix 已修); tests-first 15 红转绿; logic-explained 字段级。merge-commit `487f11f` 进 `stage/engine-v030`。主控亲跑 **1005 passed** 实证。report 已发 PM (`/tmp/pr-f-report.md`)。
- **✅ PR G 组 (schema cleanup 收尾) 已完成** (round-18, SOP-08 9 步全走, **最后一个引擎 PR**): 删 codemod/context_mapping 全链/python_callable/`<steps>`壳/5 dead validators/12 个 collect_ignore 隐藏死测试; cognitive 模块保活。dead-vs-live **三重审计** (a2 plan 重判 catch 2 致命误判 cognitive+context_mapping + a3 plan audit conftest/gate gap + a2 impl audit catch **假绿** collect_ignore 隐藏 broken tests + a3 impl audit gate 收窄合法性+覆盖无丢失) + **主控物理复验亲跑 pytest**。must-fix: collect_ignore_glob 清空 → **诚实全绿 981 passed 0 fail 0 error** (不再靠隐藏凑绿); round18 gate 加防回归断言。Studio + 根 skills/ corpus V0.3.0 迁移 = §10 Deferred (engine-only charter scope)。4 granular commits (spec `55a57a6` / tests-first `f03d9ca` / impl `9877bf1` / docs `7d8c6d3`), merge-commit `1a540ca` 进 `stage/engine-v030`。report 已发 PM (`/tmp/pr-g-report.md`)。
- **🎉 engine 阶段 (C+E+F+G) 全部完成**: 4 个 PR 全在 `stage/engine-v030` 集成分支, **待 PM 实测 golden** 后才先打 tag 再 squash 进 main (§0 合并工作流铁律)。main 仍在 74950f4 (round-14)。
- git 仓库已 gc 清理 (15000→0 游离对象, auto-gc 恢复)。

---

## §0.5 WS3 工程化优化 (2026-05-26 PM 三工作流 brief, 进行中)

> PM brief: engine 到 mvp0 v0.3.0 后做 3 件事 — WS3 工程质量评估+优化 / WS1 内部文档对齐 / WS2 对外文档 (含 Studio Copilot 知识库)。执行序: **WS3 → WS1 → WS2**, 全在 `stage/engine-v030`, golden 后再 tag+squash 进 main。
> 三方深度评估已完成 (a1+a2+a3), 28 findings, PM 拍"全部修"。优化分 6 个 PR, 每个走 SOP-08 9 步。

| WS3-PR | 范围 | 状态 |
|---|---|---|
| PR-1 | 去 conftest 掩盖 + resolver 注入 (`local_workspace_resolver.py` + CLI/dual_run_shadow 接线) | **✅ done (merge-commit `b741a18` on stage)**: SOP-08 9 步全走. 989 passed/0 fail/19 xfailed+2 skipped (主控+a3 独立实证); step4b 歧义分支补码 `[F-v3-skill-id-ambiguous]`+反证覆盖测试; step5 a2+a3 双审 src 无掩盖无 creep; step6 文档字段级同步 + a3 drift 审计 catch 4 锚点漂移 a1 修+主控实证; step7 PM report `/tmp/ws3-pr1-FINAL-report.md`. 3 granular commits (spec `0936535` / impl+tests `2b7c887` / docs `86c66ad`). |
| PR-2 | 观测 + trace 落盘 (_skill_node 生命周期回调 / runner trace_path 真写) | **✅ done (merge-commit `65e2a83` on stage)**: SOP-08 9 步全走 + 三方实证 994 passed/0 fail/19xfailed+2skipped. design 双审 catch context 分叉盲点→a2 修订; 红灯双审纯净; 实施 trace 真落盘 (summary+tracing.jsonl 含 4 类事件); step5 src 双审 a3 catch PhaseStart flatten 偏移 (主控 grep 实证 a3 对 a2 漏)→a1 修回完整结构三引擎统一+补异常路径 PhaseEnd; step6 docs 字段级同步 (主控抽查锚点准). 3 granular commits (spec `5de4bf7`/impl+tests `aa6193c`/docs `047c83b`). PM report `/tmp/ws3-pr2-FINAL-report.md`. finding #1 (卡 Studio 核心) 达成. |
| PR-3 | persona + Context + 旧入口 | **✅ done (merge-commit `2c7dcca` on stage)**: SOP-08 9 步全走 + 三方实证 996 passed/0 fail/19xfailed+2skipped (主控亲跑确认). 设计双审 2 轮 (v1 a1+a3 catch persona 修法不可实施=PersonaSkillDef 已删, 主控亲跑 ImportError 确认+纠正自己 fact-check 错 → a2 git 考古定论 persona 是 charter 故意废弃死码→干净拆除, md-patch 重构/元数据 defer PR-6; v2 第 2 轮 catch run_skill 契约冲突须保 return-failure + md_to_json defer 留 latent KeyError 须 guard + 3 个"persona"测试实为 `_guard_v030_root` 拒绝覆盖须迁移非删 → v4 收口 7 点). tests-first 诚实红灯; 实施后 a3 src 审计 catch 2 must-fix (dotenv live 测试连带误删=已救回 `test_runner_main.py` / 孤儿死码岛 7 符号=已清净) + 收紧 1 松测试, 主控逐一 grep+rg 实证. 范围: persona 死码簇+legacy harness 执行路径拆除 + Context 4 dict 方法 + run_skill fail-loud `[F-v3-graph-root-missing]` + md_to_json deferred-path guard. 3 granular commits (spec `e02538a`/impl+tests `1cf825d`/docs `ca74d8a`). PM report `/tmp/ws3-pr3-FINAL-report.md`. |
| PR-4 | 缓存 (dehydrate/rehydrate 丢字段) + 递归环检测 | **✅ done (merge-commit `7979a95` on stage)**: SOP-08 9 步全走 + 三方实证 (主控亲跑 1003 passed/0 failed, 9 红灯转绿, 无 collect_ignore/skip/xfail/弱断言凑绿). 设计双审 2 轮 (a3 catch must-fix: 整 CompiledSkill `cold==hit` 不可达 — `actions`(ActionRegistry 无 `__eq__` identity)+`tools`(ToolDef.func/schema 动态 identity) 永假, a2 曾 rubber-stamp; 主控 grep 实证后 design §2.1.6 改逐片段断言, `input_model` 标 `compare=False` 仅保 `subagents_by_phase` 片段判等). tests-first 诚实红灯双审+主控验纯. src 偏移双审 (a3 PASS "忠实完整干净隔离" + a2 PASS "完美重构 5 文件精准锁定" + 主控亲跑 grep 实证 scope 恰 5 文件无 creep). docs 同步双审 (a2 PASS "极其忠实字段级" + a3 PASS "无幻觉无漏 两站点+9 子字段全列 eq 解释准确 三方一致 mvp0 诚实" + 主控 grep 实证 format v2/len>=20/compare=False/str(root.resolve()) 全与 src 一致). 范围: cache key format v2 + dehydrate/rehydrate phase_tokens(嵌套 PhaseAttributeSpan)+subagents_by_phase(剔 input_model 经 build_subagent_input_model 重建 + _inject_subagent_tools 重放) + 递归 guard(_loading_stack/_compilation_cache / 环→[F-v3-compile-recursion-cycle] / push 前 len>=20→[F-v3-compile-depth-exceeded]) + graph_assembler 两站点透传 + cache warning 降级 + 2 编译期错误码. 3 granular commits (spec `9850fa9`/impl+tests `35830f3`/docs `a14cbd4`). 唯一 Low (非阻塞, pre-existing, a3 catch): mvp0-alignment:317/323 `DehydratedCompiledSkill`/`schema_version` 示意段措辞 (PR-4 diff 未引入, 实为 dict round-trip 无 schema_version, 版本开关在 cache key format v2) → 记入 PR-6 治理顺手澄清. PR report 自然语言三段已发 PM. |
| PR-5 | 沙盒 + LLMclient 锁 + hoist_to | **✅ done (merge-commit `4a963fd` on stage)**: SOP-08 9 步全走 + 三方实证 (主控亲跑 1011 passed/0 failed, 7 红灯转绿, 无 collect_ignore/skip/xfail/弱断言凑绿). 设计双审 (a3 catch 3 真问题: M1 design hallucination — `hoist_to` 描述为"LLMPhase 只读字段"但 class LLMPhase 不存在; M2 design 只画 2 处 sys.modules 站点中的 1 处; M3 requirements 漏 forward-ref/失败路径验收, 主控 grep 实证后 a2/a1 修). tests-first 诚实红灯 (确定性注入并发测试 entered_event/release_event 假 SDK 工厂断言 len(created)==1, 非靠时序; a3 catch 红灯 spec.name 路径 gap — :100 真名路径比 :139 hash 名路径更危险却无红灯, a1 补第 7 红灯) 双审+主控验纯. src 偏移双审 (a3 catch 2 must-fix: F1 `_load_module` 无条件 `sys.modules.pop(spec.name)` 会误删宿主进程已合法 import 的同名模块=身份分裂, a1 改 `previous_module=sys.modules.get(name,_MISSING)` 快照守卫 pop-if-MISSING/restore-else 两路径; F2 `close_all` 单 client `.close()` 抛异常中断循环+漏 clear, a1 改 per-client try/except-log-continue; a2 PASS; 主控亲跑 1011 passed + grep 实证 previous_module :100/:146 + _lock:53/close_all:135/getattr close:140). docs 同步双审 (a2 PASS "高度忠实纯净精确到字段级" + a3 PASS "无偏移无 hallucination 无 must-fix 三方一致" + 主控 grep 实证 doc↔代码全一致). 范围 (finding1+2 真改, finding3+4 经核实 NO-OP): finding1 ModuleSandbox sys.modules 双路径隔离 [BREAKING] (临时注册不再常驻, 两路径 try/finally + previous_module 快照守卫) + finding2 LLMClientManager threading.Lock 完整 check-then-act + close_all 生命周期钩子 [NEW]; finding3 hoist_to (无 live monkey-patch 机制) + finding4 inline io schema (loader.py:1202 已 Draft202012Validator.check_schema 校验) = NO-OP 不动 src. 3 granular commits (spec+report `239255f`/impl+tests `009271d`/docs `50f5fef`). PR report 自然语言三段已发 PM. |
| PR-6 | 治理收尾 (parser _fatal / governance) | 待. **scope 追加** (从 PR-3/PR-4 defer): md_to_json/md-patch 重构 + 元数据通道 (PR-3 defer); mvp0-alignment:317/323 `DehydratedCompiledSkill`/`schema_version` 示意段澄清 (PR-4 a3 catch 的 pre-existing Low — 实为 dict round-trip 无 schema_version, 版本开关在 cache key format v2). |

WS3 完成后 → task#6 复评 (a1+a3 共设计扩展评估框架, 锚 ISO/IEC 25010 + CISQ + OpenSSF Scorecard + SE-at-Google) → WS1 → WS2。
PR-1 spec: `round-19-PR1-demask-resolver/` (design/research/requirements a2 + tasks a1, a3 audit catch scope error 已收窄)。

---

## §1 全程 PR 序列 todolist (V0.3.0 完整)

> **本表 + §0 是持久 todolist 真相源**。in-session Task 工具列表不跨 session (新 session TaskList 为空), 新 session 第一件事就是按本表 + §0 用 TaskCreate 重建 in-session todolist。
> **🔴 PR 流程铁律 (PM 2026-05-25)**: 每个 PR 做完**必须清空 a1/a2/a3 的 context** (`ccb ask <agent> /clear` 或 tmux keystroke `/clear`) 再开下一个 PR, 否则 agents context 越堆越多、注意力失焦严重。下一 PR brief 必含"读 ground truth + tasks.md + 上一 PR report"重建 context。

| # | Round/组 | PR | 范围 | 状态 |
|---|---|---|---|---|
| 1 | round-9 | PR α | Gateway 抽独立 package + LLM Roles Phase 1 | ✅ merged (934709e) |
| 2 | round-10 | PR γ0 | Agent AST/loader exit_contract removal + validator + middleware order 契约补丁 | ✅ merged (#92) |
| 3 | round-11 | PR β | Middleware refactor + CognitiveFlow 接管 finish_task/ask_clarification | ✅ merged (#93) |
| 4 | round-12 | PR δ | Skill Resolution hard cutover (engine + Studio + SUBGRAPH) | ✅ merged (#94) |
| 5 | round-13 | PR γ2 | State/IO Isolation 三区 state breaking cutover | ✅ merged (#95) |
| 6 | round-14 | PR skill-compilation (#96) | Task B (AgentNodeAST/loader/GRAPH双轨/body 5标签/mention/subgraph/inline io) | ✅ merged (#96, 74950f4) + 编译器真实 e2e 22 cases (60c27e7 on stage/engine-v030) |
| 7 | round-15 | PR C 组 | execution-runtime: cognitive 8插槽 / reference reader / read_reference+read_example tools / ActionRegistry / e2e | ✅ done (merge-commit `405e63d` on stage) |
| 8 | round-16 | PR E 组 | tracing: AMBIGUITY_LOGGED / BUILTIN_SUBAGENT events / fallback payload | ✅ done (merge-commit `d3610e8` on stage) |
| 9 | round-17 | PR F 组 | 错误码: 退役 [F-v21-*] + standard error payload (ErrorPayload + 89 码 registry) | ✅ done (merge-commit `487f11f` on stage) |
| 10 | round-18 | PR G 组 | schema cleanup: V2.1主路径/codemod/parser stub/fixture/context_mapping/python_callable 全清 (cutover 收尾, **最后一个引擎 PR**) | ✅ done (merge-commit `1a540ca` on stage) |

**注**: round 9-14 代码全已进 main (#92-#96); round-15 (PR C) + round-16 (PR E) + round-17 (PR F) + round-18 (PR G) 以 merge-commit 进 `stage/engine-v030` (未进 main)。**engine 阶段 4 个 PR 全部完成**, 整阶段待 PM 实测 golden 后 tag+squash 进 main。新 PR 走 §0 合并工作流 (merge-commit 进 `stage/engine-v030`, 不直接进 main)。

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

### 8.3 范围决策 (已收敛, PM 2026-05-25 拍板)

**cognitive template (C2) 移出 round-14, 留后续 Task C 组。**

- a2 收敛理由 (PM 认可): round-14 = 编译器静态契约切换 (loader/AST/manifest/静态校验)。B5 body 5 标签解析出 AgentNodeAST 后, 编译期闭环, 可用**纯数据结构 Unit Test** 验证 (断言 AST 属性), **不需** cognitive template 渲染做 e2e。纳入 C2 会牵扯 read_reference/read_example runtime 绑定 + knowledge_base subagent 注入, 静态编译 PR 膨胀成 runtime PR。
- a3 一致 (本来就倾向移出); a2 此理由反驳了 a1 之前"B5 需 template 消费验证"的纳入理由。三方收敛移出。
- **round-14 范围 = Task B only** (B1-B8); C2/C4/C5 入后续 C 组 PR (task #18)。

---

## §9 round-14 重做进度 (2026-05-25 更新)

### 已完成: spec 四件套重做 (SOP-08 step 1-3) — commit `93295b8`

| 阶段 | 产出 | 主笔 | 审计 | 状态 |
|---|---|---|---|---|
| step 1 spec 四件套 | design/research/requirements (a2) + tasks (a1) | a2/a1 | a1↔a2 交叉 + a3 PM 替身 | ✅ commit `4a794e7` |
| step 2 三审收敛修订 | design 8 点偏移修订 + tasks 对齐 + 11 補 name-mismatch | a2/a1 | 主控 grep verify 全属实 | ✅ commit `93295b8` |
| step 3 文档链一致 | 11 错误码总册 6 个 graph 码齐全, id-invalid 收窄 | a1 | 主控 verify | ✅ |

**三审 catch + 修订点 (全 grep verify 属实)**:
- design: mode 字段非法报错 (非绕错) / 補 `[F-v3-graph-phase-name-mismatch]` / A8-A9 禁 phase metadata + Logic validator / DAG 4 码 (cycle/island/duplicate/output) / SUBGRAPH IO 双向 1:1 / B4 io.outputs 退役 / python_callable 措辞 / §4 错误码清单补全
- tasks: 对齐修订后 design (tests-first red suite 在前, B1-B8 原子, 補 name-mismatch + 禁 metadata guard + Logic validator 测试)
- 11: 補 name-mismatch 三者不一致 FATAL, id-invalid 收窄为纯命名非法

### 下一步: step 4 a1 tests-first 重写 src + test

- 先写红灯 failing tests (按 design 验收 + [F-v3-*] 码), 再实施转绿
- 含 step 5 折叠点 (三方共识): schema_version+v / 删 mode 校验 / sweep 已 merge 污染 (`graph_serializer.py:34/41` / `loader.py:642/647` / pre-existing GRAPH.md fixture 纯 YAML / 十余处 merged test)
- 当前 working tree 的 src/test WIP = 被打断前错误前提实施, step 4 brief 必让 a1 看清并按新 spec 推翻重写, 不在污染基础上改
- B8 撤销 conftest blanket xfail (`:158/171`) + grep gate (merge 前)

### step 4 阶段进度

| 阶段 | 内容 | 状态 |
|---|---|---|
| step 4 阶段一 (r14.1) | a1 写红灯 suite `test_round14_skill_compilation_cutover.py` (27 test 函数: 双轨/schema_version v/禁 mode/禁 phase metadata/Logic validator/DAG 4 码/name-mismatch/IO deprecated/body 5 标签/mention/subgraph IO) | ✅ 主控实证 pytest 30 failed + 3 passed (3 pass = src 已满足契约: skill-mode pydantic 拒/physical-io deprecated, 非 false red) |
| step 4 阶段一 audit | a2 audit: 红灯 suite **够格做验收基准** (无 must-fix); 3 发现主控复核: schema_version "2.1" 增量 (属实, 阶段二补) / masking 轻微 (physical_io parametrize 混场景) / B4 脏数据 (误判, test 已覆盖 `("","io/inputs.json")`) | ✅ |
| step 4 阶段二 (r14.2-r14.9) | a1 实施转绿 (补 schema_version "2.1" 红灯; B1-B8; sweep 污染 + 18 modified test 同步; B8 撤 blanket xfail 改具名集合) | ✅ commit `b6b18f5` (主控亲跑 928 passed/3 skipped/38 xfailed/0 xpassed 实证) |
| step 5 双审 (SOP-08) | a2 审 src 偏移 + a3 PM 替身审整体 | ✅ 均 pass 无 must-fix; a2「教科书级 Hard Cutover 无 if-else 补丁」; a3「可 ship, 0 xpassed 误隔离消除, 对齐 A7」 |
| step 5 a3 唯一观察 (non-blocking) | impl 把 phase mismatch 细分 name-mismatch + id-duplicate (对齐 A7, 比 spec 正确); requirements §4 / 02-spec 字面统一 phase-id-invalid | ⏳ step 6 doc 同步追上 impl |
| step 4 阶段三 (r14.10) | grep gate + 全量 pytest 绿 | ⏳ |

**注**: 其他 18 个 working tree modified test WIP = 被打断前错误前提实施, 在阶段二随 src sweep 同步重写, 不单独处理。
