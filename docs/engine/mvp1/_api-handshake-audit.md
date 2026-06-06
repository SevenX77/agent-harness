---
doc: _api-handshake-audit
status: drafted（U10 锁前核查;2026-06-06;engine↔studio API 牵手审计,先不改、待 codex 复审）
owns: engine↔studio API 对接现状审计(run/predict/compile + 事件流 + 错误契约 + golden/resume)
scope: U10 API 操作面;studio 已改完等 engine,过一遍能否牵手 + 问题清单
---

# Engine ↔ Studio API 牵手审计(2026-06-06)

> 背景:U10(API 操作面)是 engine↔studio 边界,studio 侧已改完、在等 engine。本文过一遍两边 API:**能不能牵手 + 有什么问题**。**先不改**,待 codex 复审。结论基于两侧代码实读(file:line),非推测。

## 0. 结论(TL;DR)
**核心路径能牵手**:`run_skill`/`predict_skill`/`compile_skill` 签名、`RunResult`/`CompiledSkill` 形状、事件流(event_subscriber + trace.jsonl + TypeAdapter 判别 union)、resolver/gateway DI——studio call site 与 engine 签名**对得上**;`current_hashes`/`mock_llm`/predict-trace 已亲验 OK。
**3 类待解决**:① ErrorPayload 四轴对接(查 / Task 3);② V4 trace 事件 studio 已就绪 / engine 未发(目标归 kiro);③ resume(F6)/ per-node golden(F5)= 目标。

## 1. 两边对照(engine 产出 vs studio 消费)

| 能力 | engine 产出(file:line) | studio 消费(file:line) | 牵手 |
|---|---|---|---|
| run_skill | `core/runner.py:376` `(skill_path,*,workspace_dir,thread_id,unattended=False,event_subscriber,artifact_saver,initial_context,cleanup_checkpoints_on_finish=True,skill_resolver*,model_resolver,**inputs)→RunResult` | `app/services/run_manager.py:95` 传 skill_path/workspace_dir/thread_id/event_subscriber/model_resolver/skill_resolver/unattended=True/cleanup=False/**inputs | ✅ |
| predict_skill | `core/runner.py:163` `(...,unattended=True,event_subscriber,skill_resolver*,model_resolver,copilot_predict,**inputs)→RunResult`(source="predict"+phases+path_diff) | `app/services/predictor.py:114` 传 mock_llm/current_hashes/model_resolver/skill_resolver/unattended=True/**input_data | ✅ |
| compile_skill | `core/compiler.py:41` `(root,*,chat_model=None,cache=True,skill_resolver*)→CompiledSkill` | `app/services/skills.py:316/335` 传 skill_path/cache/skill_resolver;读 `.manifest.phases/.name`、`.nodes`、`.raw["io"]["inputs"]` | ✅ |
| RunResult | `core/result.py:68` `success/run_id/skill_id/context/metrics/trace_path/error/started_at/finished_at/wall_time_sec/source/phases/path_diff` | 读 success/run_id/context/metrics/source/phases/path_diff/error | ✅ |
| 事件流 | `callbacks/events.py` **33 类** typed event(`event_type` 判别)→ event_subscriber + trace.jsonl(`callbacks/emit.py` `model_dump(mode="json")`) | `run_manager.py:529` `TypeAdapter[CallbackEvent].validate_json` 逐行解析;WS `/ws/runs/{id}` + `RunDetail.events` | ✅ 机制对得上 |
| resolver / gateway | `core/skill_resolver_protocol.py` `SkillResolverProtocol.resolve_skill(skill_id)->Path`(必填,缺则 `[F-v3-resolver-missing]`);`model_resolver` 可选 | `app/services/skill_resolver.py` `StudioSkillResolver` + `app/services/gateway_resolver.py` `build_gateway_model_resolver()`,每次注入 | ✅ |

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

### 3.3 🎯 resume(F6)/ per-node golden(F5)= 目标
- **resume**:studio `app/routers/runs.py:69` `POST .../resume` → **501**;engine `resume_run` 未实现(依赖 C2 checkpoint 寻址)。双边都 stub,F6 调试不可用。
- **golden**:studio F5 要 per-node 字段级 golden diff;engine 是 whole-pipeline `mock_llm` + studio `golden_diff.py` whole-state。per-node `golden.json` 存储 + `evaluate_golden_baseline()` = 目标(未 live)。whole-run golden 能牵手。

## 4. codex 复审 prompt(已发 / 待发)
见对话;要点:独立复核两边 API,逐条 challenge §2/§3 draft finding,重点回答"能不能端到端跑通 run/predict + 哪些是签名级 mismatch(改了才调通)vs 功能未实现(能调通缺特性)+ 有无漏掉的签名级 mismatch"。

## 交叉引用
`03-api-contract/mvp1-alignment.md`(U10 ◆)· `_migration-src/api-engine-studio-contract.md`(17 块契约源)· `docs/studio/mvp1/04_platform/engine/mvp1-alignment.md`(studio 侧 F1-F6 期望)· `02-observability`(U9,V4 trace 目标)
