# Research: Standard Error Payload (PR F2)

## 1. 验证 `[F-v21-*]` (PR F1 状态)
- **动作**: `grep -rn "F-v21-" src/ tests/` equivalents (通过 `grep_search` 确认)。
- **结果**: 在 `packages/graph-agent/src` 和 `packages/graph-agent/tests` 中命中数为 0。唯一一处残留在 `apps/studio/backend/app/services/skills.py` (line 1450)，不属于引擎核心范围。
- **结论**: PR F1 目标已实质完成，可在设计中标记完成。

## 2. 当前错误码发送 (Emission) 现状
- **代码结构**: `packages/graph-agent/src/graph_agent/core/exceptions.py` 定义了基类 `GraphAgentError(message, *, context)` 和各种子类（如 `SkillLoadError`, `SkillCompilationError` 等）。`SkillCompilationError` 含有如 `compile_result, skill_path, line, field_path, suggestion` 等字段，但没有统一的 `code`, `level`, `stage`, `doc_link`。
- **发送形式**: `F-v3-` 的使用分布在引擎 src 约 93 处 + tests 118 处 (含 F-v3- 的测试文件 24 个, message-regex `match=` 断言站点 41 处), 分为三种模式：
  1. 字符串拼接（硬编码）：`raise SkillLoadError(f"[F-v3-graph] {message}")` (主要在 `loader.py` 等)。
  2. dict/kwarg 传递：通过 `error_code="[F-v3-agent-output-schema-invalid]"` kwarg 传递给 `ValidationError` 或组装件（如 `cognitive_flow.py`, `graph_assembler.py`）。
  3. `dict` payload：如 `finish_task.py` 中的 `{"code": FATAL_CODE}`。
- **粗粒度码 (Coarse Codes) 漂移**:
  - `loader.py:265-287` 存在 `[F-v3-route]`, `[F-v3-io]`, `[F-v3-graph]`, `[F-v3-actions]`, `[F-v3-purity]` 粗粒度错误码。
  - 这些码不在 `11-error-code-spec.md` 速查表中，属于实现和规范之间的漂移 (drift)，由于其泛用性较高，主要被 `_fatal` 和其他基础验证函数捕获并前缀化报错。

## 3. 测试断言现状
- 核心引擎测试库包含含 `F-v3-` 的测试文件 24 个, message-regex `match=` 断言站点 41 处, `F-v3-` 总 occurrences 118。
- 这种正则匹配极易由于日志或 message 格式变动而导致脆性测试（brittle tests），无法直接验证传递给外部（如 Studio 或网关）的结构化 payload 语义。