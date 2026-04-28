# MVP-0 Tasks — Dispatch Sheet

**Spec:** `v1-reset-mvp-0-baseline-cleanup`
**Date:** 2026-04-28
**Parent:** `docs/superpowers/specs/2026-04-28-v1-reset-direction.md`
**Status:** Draft — pending Gemini design review then dispatch

---

## 0. 总览

按 design.md 拆为 12 个子任务，分配给 a1 codex（重型线）/ a3 claude（短链线）。

完成顺序约束：
- T0 baseline snapshot 必须最先做
- T9 (B4 vendored deerflow 删除) 依赖 T8 (deerflow 上游确认 + inline list) — 两条都给 codex
- 其他子任务可并行
- T11 (A8 ContextBridge 合并) 给 a3，但完成后必须 codex 审

---

## T0：baseline snapshot — 主控
**Owner:** 主控 Claude (PM)
**Dependencies:** 无
**Estimated:** 30 min

**Steps:**
1. 跑所有 7 个 SKILL `compile_skill()` 收集 FATAL/WARNING 状态
2. 跑 `pytest tests/graph_agent/ -x --tb=no -q` 收集结果
3. 跑 `find src -type f -name "*.py" | xargs wc -l` 收集行数
4. 落盘到 `docs/v1-reset/mvp-0-baseline-snapshot.md`
5. git commit: `docs(v1-reset): mvp-0 baseline snapshot`

**Verification:**
- baseline snapshot 文件存在 + 内容完整
- 主控读一遍确认数据可作为对比基准

---

## T1：建 MVP-0 orchestrator scope — 主控
**Owner:** 主控 Claude (PM)
**Dependencies:** T0 完成后
**Estimated:** 5 min

**Steps:**
```bash
claude-ccb-orchestrator start-task-scope v1-reset-mvp-0-baseline-cleanup \
  --agents a1:codex,a3:claude \
  --tasks-max 800
```

**Verification:**
- `claude-ccb-orchestrator list-my-scopes` 显示 scope 状态 active

---

## T2：建立异常体系（A6 第 1 段） — a1 codex
**Owner:** a1 codex（重型线）
**Dependencies:** T1
**Estimated:** 1 hour

**Scope:**
- 重画 `src/core/graph_agent/core/exceptions.py`（按 design.md §1.1 完整继承树）
- 加 `tests/graph_agent/core/test_exceptions.py`：每个异常类有 instantiation + context dict + chain 测试

**Acceptance:**
- exceptions.py mypy --strict 通过
- exceptions.py ruff check 通过
- pytest tests/graph_agent/core/test_exceptions.py 全绿
- 异常类继承层次跟 design.md §1.1 完全一致

**Brief（给 codex 的派任务文本）**: 写在 `/tmp/codex-mvp-0-T2-brief.md`，引用 design.md §1.1

---

## T3：silent failure 重构（A6 第 2 段，抛错类）— a1 codex
**Owner:** a1 codex
**Dependencies:** T2 完成（异常类必须先存在）
**Estimated:** 2 hours

**Scope（design.md §2.1 Pattern A）**:
- `runner.py:227` `except OSError: pass` → 抛 `IOError`
- `runner.py:336` `except ImportError: pass` → 抛 `LoaderError`
- `core/harness.py:307` deepcopy 失败 → 抛 `StateTransformError`
- `core/harness.py:431` checkpointer init → 抛 `CheckpointError`
- `core/harness.py:715` trace save → 抛 `TraceWriteError`

**Acceptance:**
- 上述 5 处不再静默
- pytest tests/graph_agent/ 不退步（如果某测试期望 silent failure，更新该测试为期望抛错）
- 改动文件 mypy --strict + ruff check 通过

---

## T4：silent failure 重构（A6 第 3 段，显式降级类）— a1 codex
**Owner:** a1 codex
**Dependencies:** T2 完成
**Estimated:** 1.5 hour

**Scope（design.md §2.2 Pattern B）**:
- `models/resolver.py:626` 显式降级 + `logger.warning`
- `cognitive/middlewares.py:336` & `:615` 显式降级
- `core/validators/tool_paths.py:228` 显式降级
- `config/llm_config.py:594` design 阶段确认抛 vs 降级（先 grep 调用方判断语义）

**Acceptance:**
- 上述 5 处全部带结构化 `logger.warning(...)` 输出
- 行为不变（降级仍然降级），但可观测
- pytest 不退步

---

## T5：B1 删 parallel_delegate + subgraph runtime — a3 claude
**Owner:** a3 claude（短链线）
**Dependencies:** T1
**Estimated:** 2 hours

**Scope（design.md §4.1）**:
- 删 3 个 .py 文件 + 相关测试
- 改 manifest.py / loader.py / __init__.py
- story-deconstruction 移到 `skills/_v2_pending/` + 加 README

**Acceptance:**
- `grep -rn "parallel_delegate\|class Subgraph" src/` 0 hit
- `pytest tests/graph_agent/` 不退步
- 4 SKILL pytest 全绿
- a3 commit 完成后**派给 codex 审一遍**（按用户铁律）

**Brief**: `/tmp/a3-mvp-0-T5-brief.md`

---

## T6：B2 删 multimodal tools — a3 claude
**Owner:** a3 claude
**Dependencies:** T1
**Estimated:** 1.5 hour

**Scope（design.md §4.2）**:
- 删 3 个 multimodal tool .py + multimodal_config.py + 相关测试
- 改 tools/__init__.py + pyproject.toml 移除依赖

**Acceptance:**
- `grep -rn "generate_image\|generate_video\|understand_video" src/` 0 hit
- `pytest tests/graph_agent/` 不退步
- a3 commit → codex 审

---

## T7：B5 删 dead code + 冗余 parser — a3 claude
**Owner:** a3 claude
**Dependencies:** T1
**Estimated:** 1 hour

**Scope（design.md §4.3）**:
- loader.py 删 4 个 _phase_* 函数
- 删 deerflow/skills/parser.py（B4 一起做时也会触发，但 a3 这里的删除独立 commit 验证）

**Acceptance:**
- `grep -rn "_phase_string\|_phase_int\|_phase_bool\|_phase_string_list" src/` 0 hit
- `pytest tests/graph_agent/` 不退步
- a3 commit → codex 审

---

## T8：deerflow 上游确认 + inline list — a1 codex（research 类）
**Owner:** a1 codex
**Dependencies:** T1
**Estimated:** 1 hour

**Scope（design.md §5.1 + §5.2）**:
1. 检查 PyPI: `pip search deerflow` 或 `curl https://pypi.org/pypi/deerflow/json`
2. 如有公开 release：记录可用版本号
3. grep `from graph_agent.deerflow|.deerflow|graph_agent.deerflow` 列出所有 graph_agent → deerflow 引用
4. 输出 inline 复制范围清单（如 deerflow 无公开 release）
5. 落盘到 `.kiro/specs/v1-reset-mvp-0-baseline-cleanup/deerflow-handover.md`

**Acceptance:**
- handover 文档完整：PyPI 状态 + 引用清单 + inline 范围（如适用）
- 主控基于该文档决定 T9 的执行细节

**Brief**: `/tmp/codex-mvp-0-T8-brief.md`

---

## T9：B3+B4 删 vendored deerflow + 双 pyproject 整合 — a1 codex
**Owner:** a1 codex
**Dependencies:** T8 完成（依赖 handover 文档）
**Estimated:** 4 hours

**Scope（design.md §5）**:
1. 删 `src/core/graph_agent/deerflow/` 目录（如有 inline 复制，先复制再删）
2. 加 `pyproject.toml` deerflow 依赖（如适用）
3. 改 `__init__.py` 移除 sys.path hack
4. 改 `models/resolver.py` 移除 SummarizationMiddleware metadata
5. 整合双 pyproject：保留根 + 删 src/core/graph_agent/pyproject.toml + 合并独有依赖

**Acceptance:**
- `find src/core/graph_agent/deerflow -type d | wc -l` = 0
- `grep -rn "SummarizationMiddleware\|LoopDetectionMiddleware" src/` 0 hit
- `find . -name pyproject.toml -not -path "*/.venv/*"` 输出仅 1 行
- `pytest tests/graph_agent/` 全绿
- 4 SKILL e2e 跑通
- 改动文件 mypy --strict + ruff check 通过

**Brief**: `/tmp/codex-mvp-0-T9-brief.md`

---

## T10：A8 ContextBridge 合并 — a3 claude
**Owner:** a3 claude
**Dependencies:** T1
**Estimated:** 1 hour

**Scope（design.md §3）**:
1. grep 所有 `ContextBridge` 引用 / import 路径
2. 字段对齐：dataclass 版本 vs Pydantic 版本逐字段
3. 差异字段合并到 Pydantic 版本（manifest.py）
4. 替换所有 import 到 `from graph_agent.core.manifest import ContextBridge`
5. 删除 `types.py:17` 的 dataclass 定义（保留 types.py 文件其他内容）

**Acceptance:**
- `grep -rn "class ContextBridge" src/core/graph_agent` 输出 1 行
- `grep -rn "from .*types import.*ContextBridge\|from graph_agent.core.types import ContextBridge" src/` 0 hit
- pytest 不退步
- a3 commit → codex 审

**Brief**: `/tmp/a3-mvp-0-T10-brief.md`

---

## T11：mypy + ruff + pre-commit 配置（部分启动）— a1 codex
**Owner:** a1 codex
**Dependencies:** T9 完成（pyproject 已整合）
**Estimated:** 1 hour

**Scope（design.md §1.2 + direction doc Part E）**:
1. 在根 `pyproject.toml` 添加 `[tool.mypy]` + `[tool.ruff]` 配置
2. 创建 `.pre-commit-config.yaml`
3. 验证 `mypy --strict` 在 `core/exceptions.py` + `core/manifest.py` 通过（其他文件可暂时 ignore）
4. `ruff check` 全库通过

**Acceptance:**
- pre-commit hook 安装 + 跑过测试 commit
- mypy strict 在新代码（exceptions.py, manifest.py 等）通过
- ruff check 全库通过

---

## T12：4 SKILL e2e + baseline diff — 主控
**Owner:** 主控 Claude (PM)
**Dependencies:** T2-T11 全部完成
**Estimated:** 1.5 hour

**Steps:**
1. 跑 `pytest tests/graph_agent/ -x --tb=short`（应全绿）
2. 跑 `python3 /tmp/e2e_chain.py`（4 SKILL 跑通 1 章）
3. 重新生成 baseline 对比数据 + diff 跟 T0 baseline
4. 任何 baseline 退步必须解释

**Acceptance:**
- pytest 全绿
- e2e 跑通
- baseline diff 全部解释清楚（或回滚相关删除 commit）

---

## T13：MVP-0 收尾 + scope 关闭 — 主控
**Owner:** 主控 Claude (PM)
**Dependencies:** T12 通过
**Estimated:** 30 min

**Steps:**
1. 写 MVP-0 完成总结到 memory（learnings + 风险记录）
2. squash 子任务 commit 到一个 feat/v1-reset-mvp-0 分支
3. push + 创 PR + merge 到 main
4. `claude-ccb-orchestrator stop-task-scope v1-reset-mvp-0-baseline-cleanup`
5. 给 a1 codex / a2 gemini / a3 claude 各发一次 `/clear`
6. 进入 MVP-1 spec 起草

---

## 任务依赖图

```
T0 baseline (主控)
  └─ T1 scope (主控)
       ├─ [重型线 a1 codex]
       │    ├─ T2 异常体系 ──┐
       │    ├─ T3 silent failure 抛错 (依赖 T2)
       │    ├─ T4 silent failure 降级 (依赖 T2)
       │    ├─ T8 deerflow handover ── T9 删 vendored
       │    └─ T11 mypy/ruff/pre-commit (依赖 T9)
       │
       └─ [短链线 a3 claude，每条 a3 commit 完后派 codex 审]
            ├─ T5 B1 parallel_delegate
            ├─ T6 B2 multimodal
            ├─ T7 B5 dead code
            └─ T10 A8 ContextBridge

  T12 e2e + baseline diff (主控，等所有 T 完成后)
  T13 收尾 (主控)
```

## 派任务时的 prompt 边界（每个 brief 必含）

按 ccb-collaboration 4.5：

```
你的任务边界：
1. 只在本 spec 指定的文件修改范围内动；不要扩展 scope
2. 完成后只报告结果（不要 commit / push / 创 PR — 主控会处理）
3. 不要 ccb ask 派任务给其他 agent
4. 不要跑 git status / diff（除了 git log 看历史 OK）
5. mypy --strict + ruff check 在你修改的文件必须通过
6. 完成后 reply 含：（1）改了哪些文件 + 改动总结；（2）新增/删除测试 list；（3）pytest 输出；（4）任何超出 scope 的发现
```
