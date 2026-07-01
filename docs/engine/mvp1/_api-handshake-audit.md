---
doc: _api-handshake-audit
status: drafted（U10 锁前核查;2026-06-06;engine↔studio API 牵手审计,先不改、待 codex 复审）
owns: engine↔studio API 对接现状审计(run/predict/compile + 事件流 + 错误契约 + golden/resume)
scope: U10 API 操作面;studio 已改完等 engine,过一遍能否牵手 + 问题清单
---

# Engine ↔ Studio API 牵手审计(2026-06-06)

> 背景:U10(API 操作面)是 engine↔studio 边界,studio 侧已改完、在等 engine。本文过一遍两边 API:**能不能牵手 + 有什么问题**。**先不改**,待 codex 复审。结论基于两侧代码实读(file:line),非推测。

## 0. 结论(TL;DR,2026-06-06 codex 复审后修正)
**predict 这条能牵手;run 这条不算端到端对齐**——codex 复现 3 个 studio 侧 P0(见 §5)。`predict_skill`/`compile_skill` 签名、`RunResult`/`CompiledSkill` 形状、事件流(event_subscriber + trace.jsonl + TypeAdapter 判别 union)、resolver/gateway DI **对得上**;`current_hashes`/`mock_llm`/predict-trace 已亲验 OK。
**run 路径 3 个 P0(studio 侧 misuse,engine 契约本身正确,归 studio session)**:① studio 传 `SKILL.md` 应传 skill root;② `workspace_dir` 双层 → trace 落 `runs/runs/`;③ worker 忽略 `success=False` → 假成功。详见 §5。
**3 类设计层待解决**:① ErrorPayload 四轴 → 已决定做 **error-contract-V2**(G1-G6,见 `compile-rules`/`data-contracts`/`03-api-contract`);② V4 trace 事件 studio 已就绪 / engine 未发(目标归 kiro);③ resume(F6)/ per-node golden(F5)= 目标。

## 1. 两边对照(engine 产出 vs studio 消费)

| 能力 | engine 产出(file:line) | studio 消费(file:line) | 牵手 |
|---|---|---|---|
| run_skill | `core/runner.py:376` `(skill_path,*,workspace_dir,thread_id,unattended=False,event_subscriber,artifact_saver,initial_context,cleanup_checkpoints_on_finish=True,skill_resolver=None,model_resolver,**inputs)→RunResult` | `app/services/run_manager.py:95` 传 skill_path/workspace_dir/thread_id/event_subscriber/model_resolver/skill_resolver/unattended=True/cleanup=False/**inputs | ✅ |
| predict_skill | `core/runner.py:163` `(...,unattended=True,event_subscriber,skill_resolver=None,model_resolver,copilot_predict,**inputs)→RunResult`(source="predict"+phases+path_diff) | `app/services/predictor.py:114` 传 mock_llm/current_hashes/model_resolver/skill_resolver/unattended=True/**input_data | ✅ |
| compile_skill | `core/compiler.py:41` `(root,*,chat_model=None,cache=True,skill_resolver=None)→CompiledSkill` | `app/services/skills.py:316/335` 传 skill_path/cache/skill_resolver;读 `.manifest.phases/.name`、`.nodes`、`.raw["io"]["inputs"]` | ✅ |
| RunResult | `core/result.py:68` `success/run_id/skill_id/context/metrics/trace_path/error/started_at/finished_at/wall_time_sec/source/phases/path_diff` | 读 success/run_id/context/metrics/source/phases/path_diff/error | ✅ |
| 事件流 | `callbacks/events.py` **33 类** typed event(`event_type` 判别)→ event_subscriber + trace.jsonl(`callbacks/emit.py` `model_dump(mode="json")`) | `run_manager.py:529` `TypeAdapter[CallbackEvent].validate_json` 逐行解析;WS `/ws/runs/{id}` + `RunDetail.events` | ✅ 机制对得上 |
| resolver / gateway | `core/skill_resolver_protocol.py` `SkillResolverProtocol.resolve_skill(skill_id)->Path`;公共入口省略 `skill_resolver` 时补默认 `LocalWorkspaceResolver`;`model_resolver` 可选 | `app/services/skill_resolver.py` `StudioSkillResolver` + `app/services/gateway_resolver.py` `build_gateway_model_resolver()`,每次注入 | ✅ |

## 2. 已验证 OK(亲读代码,非推测)
- **current_hashes**:studio 传(`predictor.py:58`),engine **消费**——`runner.py:197` `inputs.pop("current_hashes")` + `:246` `_warn_on_stale_golden_hashes_sdk(strategy, current_hashes)`(golden 失效告警);pop 掉不漏进 blackboard。
- **predict 写 trace.jsonl**:`runner.py:359`(trace_path)+ `:368`(write trace.jsonl)——studio `run_manager.py:166/315` 读得到内容(Agent 疑的 gap 不成立)。
- **mock_llm**:studio 显式传(`predictor.py:57`),engine `runner.py:196` pop。
- **prompt 三视图**:`PromptCapturedEvent`(`events.py:217`)带 `template_source`/`variables`/`resolved_prompt`——studio Prompt Inspector(F4)能牵手。
- **事件数 = 33 类**(`events.py` PhaseStart..InternalError),与 engine docs「33 类」一致(两个 Explore agent 报「34」是误数)。

## 3. 待解决(先不改)

### 3.1 ⚠️ ErrorPayload 四轴对接(要查 / 契约 Task 3)
- **engine**:`ErrorPayload`(`core/exceptions.py:21`)= `{code, level, stage, message, doc_link, skill_id, phase_id, field_path, source_path}` + `@model_validator _fill_registry_metadata`(code 不在 `ERROR_REGISTRY` 或 metadata 不全 → **raise ValueError**)。
- **studio**:后端**没显式消费**任一轴(`.level`/`.stage`/`source_path`/`field_path`/`.phase_id`/`doc_link` grep 空);studio 自带 `app/models/errors.py` 的 `{...,details}` error 模型,`run_manager.py:212/498` 用 `details={...}` 构造**自己的** error(非 engine ErrorPayload)。
- **问题**:engine 的 4 轴(canvas 标红需 `source_path:line` + `phase_id`,studio F4)是否真到达 studio error UI?后端没映射 → 要么 `model_dump` 整体透传给前端(前端是否用未核)、要么转 studio 模型时四轴丢失。= 契约的 **Task 3「错误码四轴完整性」**。
- **附带风险**:engine `ErrorPayload` 对未注册 code **raise**;新码(`[F-v3-golden-stale-fields]` / `[F-v3-iterate-*]`)还没进 `ERROR_REGISTRY` → 若先 emit 会炸。

### 3.2 🎯 V4 trace 事件:studio 已就绪、engine 未发(目标归 kiro)
- studio F4(`docs/studio/mvp1/01_workflows/04_run-and-verify.md:75-101`)canvas 微观拓扑 / dot 追踪 / 逐轮分组**依赖**:`parent_node_id`+`node_type`(agent 内子事件)、3 个边操作事件(`blackboard_reduce`/`input_dispatch`/`input_file_injected`)、`phase_execution_id`/`iteration`/`edge_transition_id`。
- engine `events.py` **还没这些**(边操作事件未定义;事件只有 `sub_run_id`/`group_key`,无 `phase_execution_id`/`iteration`)。U9 已锁为**目标归 kiro**。
- **判定**:最大功能缺口——**studio 建在前、engine impl 在后**;studio canvas 微观/dot/逐轮视图在 engine 补这些事件前**渲染不出**。非签名 mismatch,是 impl 时序。

### 3.3 🎯 resume(F6)/ per-node golden(F5)= Engine 已补,Studio 仍需薄接
- **resume**:WS-E7 后,engine public `resume_skill(...)` 已实现 checkpoint_id / checkpoint_ns latest 选择、context_overrides 与 HITL ToolMessage 注入;studio `app/routers/runs.py:69` `POST .../resume` 仍是 **501**。F6 调试不可用的剩余 blocker 在 Studio HTTP/UI 投影,不在 Engine 通用能力。
- **golden**:WS-E7 后,engine public `evaluate_golden_baseline(...)` 读取 `workspace_dir/golden/<baseline_id>` 并产逐节点字段 diff/report;studio F5 仍需改为消费 Engine report。旧 studio `golden_diff.py` whole-state diff 不是 Engine truth。

## 4. codex 复审 prompt(已发,结果见 §5)
要点:独立复核两边 API,逐条 challenge §2/§3 draft finding,重点回答"能不能端到端跑通 run/predict + 哪些是签名级 mismatch(改了才调通)vs 功能未实现(能调通缺特性)+ 有无漏掉的签名级 mismatch"。

## 5. codex 复审结果(2026-06-06)
codex 跑了 13 测试(`test_predict_e2e` / `test_workspace_dir_contract_red` / `test_run_manager_gateway_events` / `test_predict_skill_run_result` / `test_event_subscriber_cutover`,13 passed)+ 临时 V0.3 skill 复现 run worker 路径/落盘错位。

### 3 个 run 路径 P0(studio 侧 misuse,engine 契约正确 → 归 studio session 修)
1. **[P0] skill 路径错**:studio `run_manager.py:184` 设 `skill_dir/"SKILL.md"`,worker `:95` 传给 `run_skill`;engine `_run_skill_dict`(`runner.py:499`)只接受"目录且含 `GRAPH.md`"。复现:传 SKILL.md → `RunResult(success=False)` + `[F-v3-graph-root-missing]`。(对比:predict 路径 studio 传的是 skill_dir/root,正确。)
2. **[P0] workspace_dir 双层**:worker 传 `workspace_dir=run_dir.parent`(`run_manager.py:97`),而 `run_dir_for`(`skills.py:762`)已是 `.workspace/runs/{id}`,engine 又写 `workspace_dir/runs/{id}`(`runner.py:644`)→ 真 trace/result 落 `.workspace/runs/runs/{id}/`,studio 读的 `.workspace/runs/{id}/trace.jsonl` 是空文件。
3. **[P0] 假成功**:worker 调完 `run_skill` 不查 `result.success`,直接推 `"status":"success"`(`run_manager.py:95→111`)→ engine 的 `[F-v3-graph-root-missing]` 在 studio metadata 上变成成功。

### 逐条 challenge(对 §2/§3 draft)
1. "核心路径能牵手" → **部分错**:predict/compile/resolver/gateway DI 对;run 有上述 3 P0。
2. current_hashes → **对**;但目前只 log warning、非 studio 可消费诊断(= error-V2 动机之一)。
3. predict 写 trace → **对**(`predictor.py:114` 传 `.workspace`,路径对)。
4. ErrorPayload 四轴 → **对、更具体**:studio `ErrorResponse`(`errors.py:10`)只 `{error_code,http_status,message,details}`;compile 投影(`skills.py:1449`)只 `file/line/field/severity/message`;predict 原样 model_dump 能带 `result.error`,run/compile/lint 路径基本丢失。
5. 未注册 code 会炸 → **机制对**(`exceptions.py:37`);golden/iterate 目标码当前源码未见已 emit(= error-V2 G6 要先注册)。
6. V4 trace 字段 → **对**(事件 union 无 `parent_node_id/node_type/phase_execution_id`,`events.py:55`)。
7. resume/per-node golden → **2026-06-10 更新**:studio resume 仍 501,但 engine 已有 public `resume_skill`;per-node golden Engine eval 已有 `evaluate_golden_baseline`,Studio 仍需薄接。

## 交叉引用
`03-api-contract/mvp1-alignment.md`(U10 ◆, engine↔Studio API 契约 SSOT)· `docs/studio/mvp1/04_platform/engine/mvp1-alignment.md`(studio 侧 F1-F6 期望)· `02-observability`(U9,V4 trace 目标)
