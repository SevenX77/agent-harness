# MVP-0 Research — Decisions & Sources

**Spec:** `v1-reset-mvp-0-baseline-cleanup`
**Date:** 2026-04-28
**Parent:** `docs/superpowers/specs/2026-04-28-v1-reset-direction.md`

## 1. 触发原因

2026-04-28 全库审计后，主控将 Gemini reset plan 翻译成 6 个 MVP 切分。MVP-0 = "基石清创"，为后续 MVP-1 ~ MVP-5 腾干净空间。

## 2. 关键决策记录

### 决策 D1：B3 (middleware) 与 B4 (vendored deerflow) 在实现上耦合

**事实**：审计 + 主控独立查证后发现，`SummarizationMiddleware` 和 `LoopDetectionMiddleware` 实际实现在 `src/core/graph_agent/deerflow/agents/middlewares/` 内部（vendored deerflow 子目录），并不是 graph_agent 自己的代码。

**决定**：在 MVP-0 把 B3 + B4 合并处理，避免重复工作。砍 vendored deerflow 自然把 Summarization / LoopDetection 也带走。

**Why this matters**：Gemini reset plan 把 B3 / B4 列为两条独立项，但实际上 B4 的删除会无可避免地触发 B3 的删除。如果按"先删 B3 再删 B4"分两步走，第一步删 B3 时会把 vendored deerflow 改坏，后续 B4 操作变得复杂。合并处理成一条更稳。

### 决策 D2：B4 vendored deerflow 处理方向 = **完全删除 + 独立 pip 包**

**事实**：当前 `src/core/graph_agent/` 里 vendored 了一份 deerflow（`deerflow/` 子目录，包含 agents / config / models / skills 等），并通过 `__init__.py` 里 sys.path hack 让它可以用绝对导入访问。

**对比方案**：
- **方向 A（已选）**：完全删除 `src/core/graph_agent/deerflow/` 目录，改用 `pip install deerflow>=2.0` 作为正式依赖
- **方向 B（拒绝）**：保留 vendored deerflow 但只保留 graph_agent 真正用到的子集

**决策来源**：Gemini 2026-04-28 sanity check 推荐 (`/tmp/gemini-direction-sanity-reply.txt`):
> 推荐拆为独立 pip 包 (`pip install deerflow>=2.0`)。理由：既然我们要追求 8+ 的架构纯洁度，框架就应该完全剥离业务负担和第三方生态的内部纠缠。如果强行将其融入本项目，未来必然要面对 graph_agent 核心代码被 deerflow 更新绑架的局面。保持独立分发，版本契约才清晰。

**风险**：deerflow 上游不一定有公开 release。如果没有，应急方案 = 把 graph_agent 真正用到的 deerflow primitives **inline 复制**到 graph_agent 内部，并在 commit message 标 `inlined-from-deerflow:<commit-hash>`。完整删除 vendored 目录 + 不加 inline 复制是不可行的（会破 4 SKILL e2e）。

**design.md 阶段必须答的问题**：
1. graph_agent 真正依赖 deerflow 的哪些 primitives？grep 全库 + manifest 查证清单
2. 这些 primitives 在 deerflow 上游是否公开 / 是否有 PyPI release
3. 如果没有，inline 复制方案具体范围

### 决策 D3：异常体系优先建立完整继承树（不复用现有 `exceptions.py`）

**事实**：当前 `src/core/graph_agent/core/exceptions.py` 仅 63 行，只有薄的几个异常类（codex audit 评价"自定义异常体系偏薄"）。

**决定**：MVP-0 在 `exceptions.py` 内重建完整继承树：
```
GraphAgentError (base)
├── ExecutionError      # phase 执行 / tool 调用 / state 转换失败
├── ValidationError     # schema / contract / pre-flight 校验失败
├── IOError             # 持久化失败：file / artifact / checkpoint
├── ToolExecutionError  # 工具调用自身抛错（区别于框架抛错）
└── LoaderError         # SKILL 加载失败：parse / module / phase build
```

每条继承层级都要有 docstring 说明"什么时候抛 / 谁应该 catch / 哪一层包装"。

### 决策 D4：silent failure 不一刀切删，每条单独决"抛 vs 显式降级"

**清单**（A6 范围内 v1 必清的 8-10 处）：

| 位置 | 当前行为 | 决策方向 |
|---|---|---|
| `runner.py:227` `except OSError: pass` | 静默 | 抛 IOError（checkpoint 操作） |
| `runner.py:336` `except ImportError: pass` | 静默 | 抛 LoaderError（imports 必须存在） |
| `models/resolver.py:626` `except Exception: pass # noqa` | 静默 | 显式降级：`logger.warning + 失败上报到 metrics`（circuit breaker 设计意图就是降级） |
| `cognitive/middlewares.py:336` `except (TypeError, ValueError): return {}` | 静默返空 | 显式降级：`logger.warning + 返回 sentinel`（防御性 parse） |
| `cognitive/middlewares.py:615` `except (TypeError, ValueError): return {}` | 静默返空 | 同上 |
| `core/validators/tool_paths.py:228` `except (...): return None` | 静默返空 | 显式降级：`logger.warning + 返回 None`（path 不存在是预期 case） |
| `config/llm_config.py:594` `except OSError: return None` | 静默返空 | 抛 LoaderError 或显式降级（看具体语义） |
| `core/harness.py:307` deepcopy 失败浅拷继续 | fail-open | 抛 ExecutionError（state 污染风险无法接受） |
| `core/harness.py:431` checkpointer init 失败 warning + None | fail-open | 抛 IOError，由 `harness.run()` 顶层捕获包装 |
| `core/harness.py:715` trace 保存失败 warning + 续 emit | fail-open | 抛 IOError 同上 |

**Why each-case-decided not blanket**：每条 silent failure 背后有不同设计意图。`circuit_breaker` 故意设计为降级；`deepcopy` 失败是真异常。不区分一律抛错会破坏正常的 graceful degradation 路径。

### 决策 D5：删除前必须 baseline snapshot

**事实**：仓库里除 4 个核心 SKILL 还有其他 SKILL（producer / adaptation_v1 等）；MVP-0 不能假设它们不被影响。

**决定**：在第一个删除 commit 落地前，主控生成 baseline 包含：
- 所有 SKILL.md `compile_skill()` 输出（FATAL/WARNING/PASS 状态）
- `pytest tests/graph_agent/ -x --tb=no -q` 完整输出
- `find src -type f -name "*.py" | xargs wc -l`
- 落盘到 `docs/v1-reset/mvp-0-baseline-snapshot.md`

MVP-0 完成后重新跑这些命令 + diff 对比。任何"应该不变但变了"的项目必须解释清楚。

**Why**：Gemini sanity check 提醒（`/tmp/gemini-direction-sanity-reply.txt`）："过度激进清理导致的向前兼容性崩塌：如果把之前用户在 SKILL.md 里乱写的某些 undocumented 配置一并干掉，可能会导致某些未纳入 E2E 的隐藏测试用例崩盘"。

### 决策 D6：tool_wrapper.py:138 异常字符串化推迟到 MVP-4

**事实**：codex audit 把这条列为 P0：tool 异常被转成 `[Tool Error] ...` 字符串返回给 agent，框架感知不到 tool 失败。

**决定**：**不在 MVP-0 修**。在 MVP-4 修。

**Why**：A4 finish_task 控制流原语化的设计跟 tool 异常处理深度绑定。在 MVP-0 修这条会做半截设计后又被 MVP-4 推翻。归到 MVP-4 一起重画。

### 决策 D7：MVP-0 子任务并行分派（codex + a3 同时跑）

**事实**：MVP-0 子任务按"独立性 + 工作量"可分两组：
- **重型 / 涉及核心**：A6 异常体系建立 + silent failure 重构 + B4 vendored deerflow 删除
- **短链 / 独立**：B1 parallel_delegate + B2 multimodal + B5 dead code + A8 ContextBridge 合并

**决定**：派 a1 codex 拿重型组（一条线），派 a3 claude 拿短链组（另一条线），两线并行。完成后交叉审：a3 编码必须 codex 审一遍。

## 3. 来源资料索引

| 来源 | 用于 |
|---|---|
| `docs/superpowers/specs/2026-04-28-v1-reset-direction.md` | 顶层方针 + 16 维度 mapping + MVP 切分依据 |
| `/tmp/gemini-v1-reset-reply.txt` | Gemini reset plan 原文：10 重画 + 5 砍 + 4 阶段 + 门禁 |
| `/tmp/gemini-direction-sanity-reply.txt` | Gemini direction doc 审，提供 B4 方向 + 风险补漏 |
| `/tmp/codex-audit-pane-full.txt` | Codex 工程审：silent failure 清单 + 双 ContextBridge + 双 pyproject 等 |
| `/tmp/gemini-audit-full.txt` | Gemini 架构审：B4 + B3 耦合 + 上帝模块判断 |
| `~/.claude/rules/architecture-discipline.md` | 设计缺陷 vs 实现缺陷判断框架（适用于 silent failure 决策） |

## 4. 已知未决问题（需 design.md 阶段决）

| Q# | 问题 | 决策机制 |
|---|---|---|
| Q1 | deerflow 上游是否有公开 PyPI release | design.md 前主控查 PyPI；如有，定 `>=X.Y` 版本；如无，inline 复制方案具体清单 |
| Q2 | `cognitive/middlewares.py` 文件本身是否要拆 | MVP-0 不拆；middlewares.py 拆解归到 MVP-4 一起做（middlewares 跟 phase_executor 深度耦合）。MVP-0 只删 Summarization+LoopDetection 在 middlewares.py 中的引用 |
| Q3 | story-deconstruction SKILL 的处理方式 | 移到 `skills/_v2_pending/`，加 README 说明依赖 parallel_delegate（v2 复活），文件本身不删 |
| Q4 | 双 pyproject 选择：删根目录的 `pyproject.toml` 还是删 `src/core/graph_agent/pyproject.toml`？ | 主控判断：保留**根目录** `pyproject.toml`，删除内层（`src/core/graph_agent/pyproject.toml`）；理由：标准 Python 包结构 `src/` layout，根目录 pyproject 是 industry standard |
| Q5 | mypy 配置位置 | 加到根 `pyproject.toml` 的 `[tool.mypy]` section（不另起 `mypy.ini`） |

## 5. MVP-0 完成后立刻做的事

1. 给 codex / a3 / gemini 各发一次 `/clear`（释放 context budget）
2. 关闭 orchestrator scope `v1-reset-mvp-0-baseline-cleanup`
3. 主控写 MVP-0 完成总结（learnings + 风险记录）入 memory
4. 进入 MVP-1 spec 起草

## 6. References / 链接

- LangGraph docs: https://langchain-ai.github.io/langgraph/
- DeerFlow upstream: 查询中（design.md 阶段确认是否有 PyPI 包）
- Pydantic v2 strict mode: https://docs.pydantic.dev/latest/concepts/strict_mode/
- ruff rules: https://docs.astral.sh/ruff/rules/
