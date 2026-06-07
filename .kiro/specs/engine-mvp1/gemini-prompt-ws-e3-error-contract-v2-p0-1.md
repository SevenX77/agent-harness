---
ws_id: WS-E3-error-contract-v2-p0-1
artifact: gemini-prompt
status: drafted
created: 2026-06-06
task_file: .kiro/specs/engine-mvp1/task-ws-e3-error-contract-v2-p0-1.md
requirements: .kiro/specs/engine-mvp1/requirements-ws-e3-error-contract-v2-p0-1.md
---

# Gemini Prompt - WS-E3 Error Contract V2 P0-1

```text
你是 /Users/sevenx/Documents/coding/agent-harness 仓库的 engine 模块实现者。请按 TDD 执行 WS-E3 错误契约 V2 P0-1：RED 测试已由 Codex 写好并已通过 Claude 契约门审查，你的任务是只做最小 GREEN 实现，不扩范围。

工作区：
/Users/sevenx/Documents/coding/agent-harness

任务书：
.kiro/specs/engine-mvp1/task-ws-e3-error-contract-v2-p0-1.md

需求书：
.kiro/specs/engine-mvp1/requirements-ws-e3-error-contract-v2-p0-1.md

必须先读并回述关键现状：
- packages/graph-agent/src/graph_agent/core/exceptions.py
  重点：ErrorPayload、make_error_payload、GraphAgentError.__init__。
- packages/graph-agent/src/graph_agent/core/result.py
  重点：RunResult、WorkflowResult。
- packages/graph-agent/src/graph_agent/core/runner.py
  只读：run_skill / predict_skill 失败边界与 _write_workflow_result_artifacts。不要改 runner.py。
- packages/graph-agent/src/graph_agent/callbacks/events.py
  只读：确认 P0-1 不实现 DiagnosticEmittedEvent。
- packages/graph-agent/src/graph_agent/callbacks/emit.py
  只读：确认 P0-1 不改事件发射。
- 已批准 RED 测试：
  - packages/graph-agent/tests/core/test_error_payload_contract.py
  - packages/graph-agent/tests/exceptions/test_error_catalog_rightsizing.py
  - packages/graph-agent/tests/predict/test_predict_skill_run_result.py
  - packages/graph-agent/tests/runner/test_v030_error_contract_v2_diagnostics.py

RED 测试结果：
运行：
uv run pytest packages/graph-agent/tests/core/test_error_payload_contract.py packages/graph-agent/tests/exceptions/test_error_catalog_rightsizing.py packages/graph-agent/tests/predict/test_predict_skill_run_result.py packages/graph-agent/tests/runner/test_v030_error_contract_v2_diagnostics.py -q
当前预期 RED：9 failed, 53 passed。失败都应集中在 details / diagnostics 字段缺失。

允许修改：
- packages/graph-agent/src/graph_agent/core/exceptions.py
- packages/graph-agent/src/graph_agent/core/result.py
- 必要时只做不削弱契约的测试维护：
  - packages/graph-agent/tests/core/test_error_payload_contract.py
  - packages/graph-agent/tests/exceptions/test_error_catalog_rightsizing.py
  - packages/graph-agent/tests/predict/test_predict_skill_run_result.py
  - packages/graph-agent/tests/runner/test_v030_error_contract_v2_diagnostics.py

禁止修改：
- packages/graph-agent/src/graph_agent/core/error_registry.py
- packages/graph-agent/src/graph_agent/core/runner.py
- packages/graph-agent/src/graph_agent/callbacks/events.py
- packages/graph-agent/src/graph_agent/callbacks/emit.py
- apps/studio/**

目标行为：
1. ErrorPayload 新增 details，默认空对象，model_dump(mode="json") 与 model_dump_json() 都可读。
2. details 必须 JSON-safe 且稳定：
   - Path -> str
   - set -> sorted list
   - nested Pydantic BaseModel -> dict
   - Exception -> "TypeName: message"
   - 其他非 JSON 值要安全字符串化，不能让 dump/json/result.json 写盘失败。
3. GraphAgentError.context 必须进入 payload.details["context"]。
   - 无显式 payload 时，从 message 里的注册错误码生成 payload 后合入 context。
   - 有显式 payload 且 payload 已有 details 时，显式 details 不丢，context 也可见。
   - 外部 gateway code 兼容分支仍保持 payload is None。
4. RunResult 新增 diagnostics、diagnostics_limit、diagnostics_truncated、diagnostic_counts。
   - 成功结果默认 diagnostics == []。
   - 失败只传 error 时 diagnostics 至少包含主 fatal。
   - 显式 diagnostics 时，主 error 放第一位，去重，按 limit 确定性截断。
   - diagnostic_counts 按截断前的完整去重诊断集合统计 total / by_level / by_code。
5. WorkflowResult 继承新字段，旧 dict-like get / __getitem__ 继续可读。
6. 真实 run_skill 缺 GRAPH.md 失败 e2e 不改 runner.py 也要通过，因为 result.json 由 RunResult/WorkflowResult model_dump 自动带出 diagnostics。

绝对不做：
- 不改 ERROR_REGISTRY key set，不改 ErrorCodeMetadata 形状。
- 不新增 remediation、doc_ref、doc_url、details_schema、schema_version。
- 不实现 GET /errors。
- 不实现 DiagnosticEmittedEvent，不改 CallbackEvent union 或 emit.py。
- 不拆运行期细分错误码，不注册 golden/iterate 新码。
- 不改 studio。

执行顺序：
1. 先运行 RED 命令确认失败形态。
2. 按 task 文件 Phase 1 -> Phase 5 实现，每阶段跑对应命令。
3. 最后跑完整验证命令：
   uv run pytest packages/graph-agent/tests/core/test_error_payload_contract.py packages/graph-agent/tests/exceptions/test_error_catalog_rightsizing.py packages/graph-agent/tests/predict/test_predict_skill_run_result.py packages/graph-agent/tests/runner/test_v030_error_contract_v2_diagnostics.py -q
4. 再跑 scope/hygiene：
   git diff -- packages/graph-agent/src/graph_agent/core/error_registry.py packages/graph-agent/src/graph_agent/core/runner.py packages/graph-agent/src/graph_agent/callbacks/events.py packages/graph-agent/src/graph_agent/callbacks/emit.py
   git status --short -- apps/studio
   git diff --check -- packages/graph-agent/src/graph_agent/core/exceptions.py packages/graph-agent/src/graph_agent/core/result.py packages/graph-agent/tests/core/test_error_payload_contract.py packages/graph-agent/tests/exceptions/test_error_catalog_rightsizing.py packages/graph-agent/tests/predict/test_predict_skill_run_result.py packages/graph-agent/tests/runner/test_v030_error_contract_v2_diagnostics.py

回报格式：
1. 修改了哪些文件。
2. 每条验证命令的结果摘要。
3. 明确说明 forbidden engine files 是否无 diff；`apps/studio/**` 如已有 dirty，只报告为共享工作树既有状态，不要编辑。
4. 若有任何无法满足的 hard-exit 项，说明原因并停下，不要扩大范围。
```
