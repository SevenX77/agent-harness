# MVP-0 Requirements — Baseline Cleanup

**Spec:** `v1-reset-mvp-0-baseline-cleanup`
**Date:** 2026-04-28
**Parent:** `docs/superpowers/specs/2026-04-28-v1-reset-direction.md`
**Estimated:** 3-4 days (codex + a3 parallel)
**Status:** Draft — pending Gemini design review

---

## Introduction

MVP-0 是 v1 reset 的第 0 步：**地基清创**。范围 = Gemini reset plan 的 5 项功能砍除（B1-B5）+ 2 项重画（A6 异常体系 + A8 ContextBridge 单一来源）。

**MVP-0 完成定义**（不变量同时成立）：
1. 5 项 B 全部从代码库消失（不留 pyc / cached references）
2. A6 异常体系建立 + 所有 silent failure 清零
3. A8 ContextBridge 单一来源（`types.py` 副本删除，全部引用 `manifest.py`）
4. 4 个核心 SKILL（text-segmentation / event-extraction / batch-analysis / global-synthesis）pytest 全绿 + e2e smoke 跑通
5. 单 pyproject.toml（双 pyproject 二选一）
6. 新代码 mypy strict 通过 + ruff 通过

**这个 MVP 的特点**：纯减法 + 收尾。不引入新 feature，不重画接口。地基扫干净给后续 MVP 腾出空间。

---

## Requirements

### Requirement 1：B1 砍 parallel_delegate + subgraph runtime
**Objective:** As a framework maintainer, I want to remove parallel_delegate and subgraph runtime, so that v1 不再背"无类型字典 + 隐式控制总线"导致的并发竞态隐患。

#### Acceptance Criteria

1. WHEN MVP-0 完成，THEN `src/core/graph_agent/core/parallel_delegate.py` 不再存在
2. WHEN MVP-0 完成，THEN `src/core/graph_agent/core/subgraph.py` 不再存在
3. WHEN MVP-0 完成，THEN `src/core/graph_agent/core/validators/subgraph_cycle.py` 不再存在
4. WHEN MVP-0 完成，THEN `manifest.py` 中跟 parallel_delegate / subgraph 相关的 schema 字段（`subgraph` / `parallel_delegate` / `aggregate_to` / `parallel_outputs` 等）从 `LLMPhase` / `LogicPhase` 类移除
5. WHEN MVP-0 完成，THEN `loader.py` 中加载这些字段的解析逻辑（`build_subgraph_node` / `build_parallel_delegate_node` 等）一同移除
6. WHEN MVP-0 完成，THEN `tests/graph_agent/core/test_parallel_delegate.py` / `test_subgraph.py` / `test_subgraph_cycle.py` 一同删除
7. WHEN MVP-0 完成，THEN 4 个核心 SKILL（text-segmentation / event-extraction / batch-analysis / global-synthesis）的 SKILL.md 不需要修改（它们均不使用这两个 feature）
8. WHEN MVP-0 完成，THEN `story-deconstruction` SKILL 在 v1 期间被标记为 unsupported（移到 `skills/_v2_pending/` 或加 README 说明，不删除文件）
9. WHEN MVP-0 完成，THEN `pytest tests/graph_agent/ -x` 全绿（删除上述测试文件后剩下的）

### Requirement 2：B2 砍 multimodal tools
**Objective:** As a framework maintainer, I want to remove multimodal tools (generate_image/generate_video/understand_video), so that 核心框架 API surface 收敛到"文本 SKILL 编排"职责。

#### Acceptance Criteria

1. WHEN MVP-0 完成，THEN `src/core/graph_agent/tools/generate_image.py` 不再存在
2. WHEN MVP-0 完成，THEN `src/core/graph_agent/tools/generate_video.py` 不再存在
3. WHEN MVP-0 完成，THEN `src/core/graph_agent/tools/understand_video.py` 不再存在
4. WHEN MVP-0 完成，THEN `src/core/graph_agent/config/multimodal_config.py` 不再存在
5. WHEN MVP-0 完成，THEN 这些 tool 在 `src/core/graph_agent/tools/__init__.py` 中的注册条目一同移除
6. WHEN MVP-0 完成，THEN `tests/graph_agent/tools/test_multimodal*.py` / `test_generate_*.py` 一同删除
7. WHEN MVP-0 完成，THEN 4 个核心 SKILL 的 SKILL.md 不需要修改（它们均不使用 multimodal tools）
8. WHEN MVP-0 完成，THEN `pyproject.toml` 移除 multimodal 相关依赖（如 PIL / opencv-python / 等）

### Requirement 3：B3 + B4 砍 vendored deerflow + 双 pyproject 整合
**Objective:** As a framework maintainer, I want to clean the package structure to single pyproject and decoupled deerflow dependency, so that 包边界清晰、构建发布单一来源、Summarization+LoopDetection middleware（实现在 vendored deerflow 内部）一并被砍。

**Critical finding：** Summarization 和 LoopDetection middleware 实际实现在 `src/core/graph_agent/deerflow/agents/middlewares/` 内部，砍 B4 vendored deerflow 时会**自然砍掉** B3 这两个 middleware，因此本 requirement 把 B3 + B4 合并处理。

**B4 处理方向（已定）**：**完全删除 vendored deerflow**，graph_agent 真正需要的 deerflow primitives 通过 `pip install deerflow>=2.0` 引入正式依赖（Gemini 2026-04-28 sanity check 推荐方向 A，理由：8+ 架构纯洁度 + 框架剥离业务负担 + 避免 graph_agent 核心被 deerflow 内部更新绑架）。

#### Acceptance Criteria

1. WHEN MVP-0 完成，THEN 项目根只剩**一个** `pyproject.toml`（删除 `src/core/graph_agent/pyproject.toml`）
2. WHEN MVP-0 完成，THEN `Summarization` middleware 在代码库不再被引用（grep 0 hits）
3. WHEN MVP-0 完成，THEN `LoopDetection` middleware 在代码库不再被引用（grep 0 hits）
4. WHEN MVP-0 完成，THEN `models/resolver.py` 中跟 SummarizationMiddleware 相关的 metadata 注释 / max-input profile attach 逻辑移除
5. WHEN MVP-0 完成，THEN 4 个核心 SKILL pytest + e2e 仍能跑通（即 vendored deerflow 砍掉的部分均不为核心路径所需）
6. WHEN MVP-0 完成，THEN `src/core/graph_agent/deerflow/` 目录**完全删除**（`find src/core/graph_agent/deerflow -type d | wc -l` = 0）
7. WHEN MVP-0 完成，THEN `src/core/graph_agent/__init__.py` 中 sys.path 修改的 hack 代码（用于 vendored deerflow 绝对导入）一并清理
8. WHEN graph_agent 真实需要的 deerflow primitives，THEN 在 `pyproject.toml` 添加 `deerflow>=X.Y` 作为正式依赖（具体 X.Y 在 design.md 阶段确定）；如果 deerflow 没有公开 release，则把真正用到的代码 inline 复制到 graph_agent 内部 + 在 commit message 中标 `inlined-from-deerflow:<commit-hash>` 作为来源
9. WHEN MVP-0 完成，THEN 仓库不再依赖 `src/core/graph_agent/deerflow/skills/parser.py`（与 `core/parser.py` 冗余，B5 一同删除）

### Requirement 3.5：删除前 snapshot diff（防过度激进清理）
**Objective:** As a project manager, I want a snapshot baseline before any cleanup so that 过度激进清理打死 4 SKILL 之外的隐藏用例时能立刻发现 + 决定是不是该回滚。

#### Acceptance Criteria

1. WHEN MVP-0 第一个删除 commit 落地之前，THEN 主控生成 baseline 快照：
   - 仓库所有 SKILL.md（不只 4 个核心）`compile_skill()` 输出（FATAL/WARNING/PASS 状态）
   - `pytest tests/graph_agent/ -x --tb=no -q` 完整输出
   - `find src -type f -name "*.py" | xargs wc -l` 行数清单
2. WHEN MVP-0 完成，THEN 重新运行上述命令 + diff 对比 baseline；任何"应该不变但变了"的项必须解释（哪条删除导致的、是否预期内）
3. IF baseline 比对发现某 SKILL 状态从 PASS 退步到 FATAL/WARNING（4 个核心之外），THEN 主控决策：(a) 回滚那条删除 / (b) 修该 SKILL / (c) 把该 SKILL 移到 `_v2_pending/`

### Requirement 4：B5 砍 dead code + 冗余 parser
**Objective:** As a framework maintainer, I want to remove identified dead code so that codebase 不留过时实现误导维护者。

#### Acceptance Criteria

1. WHEN MVP-0 完成，THEN `src/core/graph_agent/core/loader.py` 中 `_phase_string` / `_phase_int` / `_phase_bool` / `_phase_string_list` 4 个函数不再存在（codex audit 确认无调用方）
2. WHEN MVP-0 完成，THEN `src/core/graph_agent/deerflow/skills/parser.py` 不再存在（与 `core/parser.py` 冗余，按 B4 一并处理）
3. WHEN MVP-0 完成，THEN 整库 `grep -r "^from .* import _phase_string" src/` 0 hits

### Requirement 5：A6 异常体系建立 + silent failure 清零
**Objective:** As a framework maintainer, I want a complete exception hierarchy and zero silent failures, so that 线上故障可定位 root cause、框架可靠性达"大厂 SDK 标准"。

#### Acceptance Criteria

1. WHEN MVP-0 完成，THEN `src/core/graph_agent/core/exceptions.py` 至少包含以下异常类：
   - `GraphAgentError` (base)
   - `ExecutionError` (运行时执行失败：phase 执行 / tool 调用 / state 转换)
   - `ValidationError` (校验失败：schema / contract / pre-flight)
   - `PersistenceError` (持久化失败：file / artifact / checkpoint；改名避免压盖 Python 内建 IOError)
   - `ToolExecutionError` (工具调用失败：tool 自身抛错，框架感知)
   - `LoaderError` (SKILL 加载失败：parse / module / phase build)
2. WHEN MVP-0 完成，THEN 以下已知 silent failure 全部消除（按 codex / 主控查证）：
   - `runner.py:227` (`except OSError: pass`)
   - `runner.py:336` (`except ImportError: pass`)
   - `runner.py:253` 附近（codex audit 报告 `except Exception: pass`）
   - `models/resolver.py:626` (`except Exception: pass # noqa: BLE001`)
   - `cognitive/middlewares.py:336` (`except (TypeError, ValueError): return {}`)
   - `cognitive/middlewares.py:615` (`except (TypeError, ValueError): return {}`)
   - `core/validators/tool_paths.py:228` (`except (OSError, UnicodeDecodeError, SyntaxError): return None`)
   - `config/llm_config.py:594` (`except OSError: return None`)
   - `core/harness.py:307` (deepcopy 失败浅拷继续 → 改抛 StateTransformError)
   - `core/harness.py:431` (auto-checkpointer 初始化失败 warning 返回 None → 改抛 CheckpointError，由顶层捕获)
   - `core/harness.py:715` (trace 保存失败 warning 续 emit run_completed → 改抛 TraceWriteError)
   - `cognitive/middlewares.py:336` & `:615` (JSON parse 失败 → 改用 Pattern C：返回 Command(goto="model") + ToolMessage(status="error") 让 LLM 自我纠错；不允许返回 `{}` sentinel，按 Gemini design review)
3. WHEN 任一 silent failure 在 fix 时发现"该位置确实需要降级而非抛错"，THEN 必须显式 `logger.warning("phase=X fallback from=Y to=Z reason=W", ...)` 并记录到 `_io_errors` / metrics，而不是 silent
4. WHEN MVP-0 完成，THEN `python3 -c "import re,pathlib; ..."` (按上面 grep 模式) 命中数从 8 降到 0（或 explained warnings ≥ 0）
5. WHEN MVP-0 完成，THEN `tool_wrapper.py:138` 的"tool 异常字符串化返回"在 MVP-0 范围内**不修改**（这是 A6 异常体系应用到 tool 层，归到 MVP-4 一起做，因为涉及 finish_task 重画）

### Requirement 6：A8 ContextBridge 单一来源
**Objective:** As a framework maintainer, I want a single ContextBridge definition so that loader / executor / validator 不会因为字段漂移产生 AttributeError。

#### Acceptance Criteria

1. WHEN MVP-0 完成，THEN `src/core/graph_agent/core/types.py:17` 的 `ContextBridge` dataclass 定义不再存在
2. WHEN MVP-0 完成，THEN 全代码库引用 `ContextBridge` 时全部 import 自 `src.core.graph_agent.core.manifest` 或 `graph_agent.core.manifest`（grep 验证）
3. WHEN MVP-0 完成，THEN 删除 `types.py` 副本不破坏任何已绿测试
4. IF 删除时发现 `types.py` 那个版本有独有方法 / 字段（manifest 版本没有），THEN 把那些方法 / 字段合并进 manifest 版本，再删除副本

### Requirement 7：MVP-0 不变量 — 4 SKILL e2e 不破坏
**Objective:** As a framework maintainer, I want 4 core SKILLs e2e to pass after MVP-0 completion, so that 减法不引入回归。

#### Acceptance Criteria

1. WHEN MVP-0 完成，THEN `pytest tests/graph_agent/ -x` 全绿
2. WHEN MVP-0 完成，THEN 4 SKILL e2e（text-segmentation → event-extraction → batch-analysis → global-synthesis 顺序）能跑通至少 1 章测试数据
3. WHEN 上述 e2e 失败，THEN 必须在 MVP-0 内修复，不允许携带 regression 进入 MVP-1

### Requirement 8：MVP-0 工程门禁部分启动
**Objective:** As a framework maintainer, I want mypy strict + ruff to pass on changed code, so that v1 工程门禁基线在 MVP-0 起步生效（虽然全库收敛要到 MVP-5）。

#### Acceptance Criteria

1. WHEN MVP-0 完成，THEN 新增 / 修改的 .py 文件全部 `mypy --strict` 通过（mypy 配置可在 MVP-0 引入 `pyproject.toml`）
2. WHEN MVP-0 完成，THEN 新增 / 修改的 .py 文件全部 `ruff check --select E,F,B,I,UP,SIM,N` 通过
3. WHEN MVP-0 完成，THEN `.pre-commit-config.yaml` 文件存在且至少配置 `ruff format` + `ruff check` + `mypy` hook（旧文件 mypy 失败可暂时 ignore，但新代码必须 pass）
4. IF mypy strict 在改的文件遇到 `Any` 来自上游 LangGraph / LangChain 未类型化，THEN 写 inline `# type: ignore[...]` + 说明，不允许"全文件忽略"

### Requirement 9：删除影响 e2e 时回滚机制
**Objective:** As a project manager, I want to safely revert if a deletion breaks e2e, so that MVP-0 失败不污染 main / 不留半成品 commit history.

#### Acceptance Criteria

1. WHEN 任一删除导致 4 SKILL e2e 失败 AND 修复 > 4 小时未完成，THEN agent 必须 git revert 该删除 commit + 报告主控
2. WHEN MVP-0 进入合并阶段，THEN 全部子任务 commit 在独立 feat/v1-reset-mvp-0 分支上，最后 squash-merge 到主分支
3. WHEN 主控确认 MVP-0 完成 commit 进 main 后，THEN 关闭对应 orchestrator scope（`stop-task-scope v1-reset-mvp-0-baseline-cleanup`）

---

## Out-of-Scope（明确不做的事）

- **A1 WorkflowState 拆解** — 在 MVP-1 做（影响所有 phase / middleware，独立做）
- **A5 SchemaEngine** — 在 MVP-2 做（独立基础设施）
- **A7 IOManager StorageAdapter** — 在 MVP-2 做（独立基础设施）
- **tool_wrapper.py:138 异常字符串化** — 在 MVP-4 做（涉及 finish_task 重画）
- **harness.py:307 deepcopy fallback** — 留在 MVP-0 内修是因为它是 silent failure 类（按 A6 范围）；如果发现修起来需要重画 state，移到 MVP-1
- **新增 feature** — MVP-0 是减法，不允许加任何新 feature

---

## Verification

MVP-0 完成后由主控触发以下验证：

1. **静态**：`grep -r "parallel_delegate\|subgraph\|generate_image\|generate_video\|_phase_string\|SummarizationMiddleware\|LoopDetectionMiddleware" src/ | wc -l` = 0
2. **结构**：`find . -name pyproject.toml -not -path "*/node_modules/*"` 输出仅 1 行
3. **silent failure**：自定义 grep 模式输出全部 zero（或 only with explanatory warning log）
4. **单元测试**：`pytest tests/graph_agent/ -x --tb=short`
5. **e2e**：`/tmp/e2e_chain.py`（之前 v11 跑通的脚本）继续跑通 1 章
6. **门禁**：`mypy --strict src/core/graph_agent/core/exceptions.py src/core/graph_agent/core/manifest.py` 通过；`ruff check src/core/graph_agent/core/` 通过

任一不通过 → MVP-0 不能进 main，回到对应子任务修复。
