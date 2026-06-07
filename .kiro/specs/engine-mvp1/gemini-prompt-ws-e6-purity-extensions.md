---
ws_id: WS-E6-purity-extensions
artifact: gemini-prompt
status: drafted
created: 2026-06-06
task_file: .kiro/specs/engine-mvp1/task-ws-e6-purity-extensions.md
requirements: .kiro/specs/engine-mvp1/requirements-ws-e6-purity-extensions.md
---

# Gemini Prompt - WS-E6 Purity Extensions

```text
你是 /Users/sevenx/Documents/coding/agent-harness 仓库的 engine 模块实现者。请按 TDD 执行 WS-E6 purity 扩展：RED 测试已由 Codex 写好并已通过 Claude 契约门审查，你的任务是只做最小 GREEN 实现，不扩范围。

工作区：
/Users/sevenx/Documents/coding/agent-harness

任务书：
.kiro/specs/engine-mvp1/task-ws-e6-purity-extensions.md

需求书：
.kiro/specs/engine-mvp1/requirements-ws-e6-purity-extensions.md

必须先读并回述关键现状：
- packages/graph-agent/src/graph_agent/core/purity.py
  重点：PurityViolation、scan_python_purity、scan_tool_imports_context、_collect_import_aliases、_violation_for_call、_violation_for_name_call、_violation_for_attribute_call、_open_violation_reason、_attribute_base_name。
- packages/graph-agent/src/graph_agent/core/loader.py
  只读：_load_action_dir、_load_tool_dir、_raise_on_purity_violations、_purity_fatal。不要改 loader.py。
- packages/graph-agent/src/graph_agent/core/error_registry.py
  只读：确认 [F-v3-logic-action-purity-violation] 已注册为 FATAL / 编译期。不要改 error_registry.py。
- 已批准 RED 测试：
  - packages/graph-agent/tests/core/test_purity_characterization.py
  - packages/graph-agent/tests/core/validators/test_tool_paths_escape.py
  - packages/graph-agent/tests/core/validators/test_purity_le2.py

RED 测试结果：
运行：
uv run pytest packages/graph-agent/tests/core/test_purity_characterization.py packages/graph-agent/tests/core/validators/test_tool_paths_escape.py packages/graph-agent/tests/core/validators/test_purity_le2.py -q
当前预期 RED：12 failed, 22 passed。失败都应集中在 LE2 新禁令缺失：scanner 不报 run_skill / FS 读 / sys.path / import 越界，真实 compile path 不抛 purity FATAL。

允许修改：
- packages/graph-agent/src/graph_agent/core/purity.py
- 必要时只做不削弱契约的测试维护：
  - packages/graph-agent/tests/core/test_purity_characterization.py
  - packages/graph-agent/tests/core/validators/test_tool_paths_escape.py
  - packages/graph-agent/tests/core/validators/test_purity_le2.py

禁止修改：
- packages/graph-agent/src/graph_agent/core/error_registry.py
- packages/graph-agent/src/graph_agent/core/loader.py
- packages/graph-agent/src/graph_agent/core/module_sandbox.py
- packages/graph-agent/src/graph_agent/core/graph_assembler.py
- packages/graph-agent/src/graph_agent/core/exceptions.py
- packages/graph-agent/src/graph_agent/core/result.py
- packages/graph-agent/src/graph_agent/callbacks/events.py
- packages/graph-agent/src/graph_agent/callbacks/emit.py
- apps/studio/**
- packages/graph-agent-gateway/**

目标行为：
1. skill-local action/tool Python 文件中的 run_skill 编排必须在 compile 阶段失败：
   - from graph_agent import run_skill; run_skill(...)
   - from graph_agent.core.runner import run_skill as call_child; call_child(...)
   - 动态 import 到 graph_agent.core.runner 后调用 run_skill 的 approved RED case 也必须被 scanner 提前挡住。
2. 直接文件系统访问必须在 compile 阶段失败：
   - open("input.txt").read()
   - open("out.txt", "w").write("bad")
   - Path("input.txt").read_text(...)
   - os.listdir(".")
   - 既有 path mutation、os/shutil mutation、tempfile 禁令不回归。
3. sys.path import 搜索边界修改必须失败：
   - sys.path.insert(...)
   - sys.path.append(...)
4. 高风险动态 import / import 越界路径必须失败：
   - importlib.import_module("graph_agent.core.runner")
   - importlib.util / from importlib import util 的 spec_from_file_location(...)
5. 失败统一由现有 loader path 报 [F-v3-logic-action-purity-violation]，保留 source_path 和 line 语义。
6. 纯标准库数据转换不能误杀：
   - json.loads(...)
   - str(...).strip().upper()
   - context.get(...)
7. tool Context facade import 禁令仍有效。

绝对不做：
- 不改 ERROR_REGISTRY，不新增错误码，不改 ErrorCodeMetadata 形状。
- 不改 loader.py；如果你认为必须改 loader 才能过测试，先停下汇报，不要擅自扩 owns。
- 不改 module_sandbox.py。
- 不改 graph_assembler.py，不实现 LOGIC 纯返回、不砍 Context mutation、不做 iterate/SUBGRAPH 迁移。
- 不改 exceptions.py/result.py，不做错误契约 V2。
- 不改 callbacks events/emit，不做 V4 trace 或 diagnostic event。
- 不改 studio 或 gateway。
- 不扫描全仓 Python 文件；purity 对象只来自 loader 识别的 skill-local action/tool 文件。

执行顺序：
1. 先运行 RED 命令确认失败形态：
   uv run pytest packages/graph-agent/tests/core/test_purity_characterization.py packages/graph-agent/tests/core/validators/test_tool_paths_escape.py packages/graph-agent/tests/core/validators/test_purity_le2.py -q
2. 按 task 文件 Phase 1 -> Phase 5 实现，每阶段跑对应命令。
3. 最后跑完整验证命令：
   uv run pytest packages/graph-agent/tests/core/test_purity_characterization.py packages/graph-agent/tests/core/validators/test_tool_paths_escape.py packages/graph-agent/tests/core/validators/test_purity_le2.py -q
4. 再跑 scope/hygiene：
   git diff -- packages/graph-agent/src/graph_agent/core/error_registry.py packages/graph-agent/src/graph_agent/core/loader.py packages/graph-agent/src/graph_agent/core/module_sandbox.py packages/graph-agent/src/graph_agent/core/graph_assembler.py packages/graph-agent/src/graph_agent/core/exceptions.py packages/graph-agent/src/graph_agent/core/result.py packages/graph-agent/src/graph_agent/callbacks/events.py packages/graph-agent/src/graph_agent/callbacks/emit.py
   git status --short -- apps/studio packages/graph-agent-gateway
   git diff --check -- packages/graph-agent/src/graph_agent/core/purity.py packages/graph-agent/tests/core/test_purity_characterization.py packages/graph-agent/tests/core/validators/test_tool_paths_escape.py packages/graph-agent/tests/core/validators/test_purity_le2.py

回报格式：
1. 修改了哪些文件。
2. 每条验证命令的结果摘要。
3. 明确说明 forbidden engine files 是否无 diff；apps/studio/** 和 packages/graph-agent-gateway/** 如已有 dirty，只报告为共享工作树既有状态，不要编辑。
4. 列出 scan_python_purity 最终已实现的 hard-ban 类别。
5. 若有任何无法满足的 hard-exit 项，说明原因并停下，不要扩大范围。
```
