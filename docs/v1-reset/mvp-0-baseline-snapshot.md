# MVP-0 Baseline Snapshot — 2026-04-28T19:46Z

**Spec:** `.kiro/specs/v1-reset-mvp-0-baseline-cleanup/`
**Captured by:** 主控 Claude
**Purpose:** 删除前的 baseline 数据，MVP-0 完成后用于 diff 对比，确保过度激进清理没破坏 4 SKILL 之外的隐藏用例（按 design.md §6 + Gemini 2026-04-28 sanity check）

---

## 1. SKILL.md compile status (7 SKILLs)

```
SKILL                                             FATAL   WARN STATUS
---------------------------------------------------------------------------
skills/text-segmentation/SKILL.md                     0      1 WARN
skills/event-extraction/SKILL.md                      0      2 WARN
skills/batch-analysis/SKILL.md                        0      5 WARN
skills/global-synthesis/SKILL.md                      0      4 WARN
skills/story-deconstruction/SKILL.md                  2      9 FATAL
skills/adaptation_v1/SKILL.md                         0      0 PASS
skills/producer/SKILL.md                              0      0 PASS
```

**MVP-0 完成后预期变化**:
- text-segmentation / event-extraction / batch-analysis / global-synthesis：**WARN 计数允许下降不允许上升**（移除 multimodal config / parallel_delegate 字段可能让某些 W 消失）
- story-deconstruction：移到 `skills/_v2_pending/` 后从该列表消失（v1 期间不可用）
- adaptation_v1 / producer：**必须保持 PASS**

## 2. pytest summary

```
.venv/bin/python -m pytest tests/graph_agent/ -x --tb=no -q
... (8 dot rows + 13 dots) ...
661 passed in 9.13s
```

**MVP-0 完成后预期变化**:
- 删除测试文件后 passed 数会减少（test_parallel_delegate / test_subgraph / test_multimodal 等被删）
- **底线**：剩下的测试**全部** still pass，0 failures
- 估算 MVP-0 完成后 passed ≈ 580-610（取决于实际删除的 test 数）

## 3. Python 文件总行数 + Top 大文件

**总行数**: 28,494 lines (164 .py files in `src/core/graph_agent/`, 不含 `__pycache__`)

**Top 9 大文件**:

| Lines | File | MVP-N 拆解 |
|---|---|---|
| 1154 | `core/harness.py` | MVP-5 (A10) |
| 1013 | `core/loader.py` | MVP-3 (A2) |
| 961 | `deerflow/client.py` | MVP-0 删除 (B4) |
| 805 | `cognitive/middlewares.py` | MVP-4 (随 phase_executor 拆) |
| 777 | `core/phase_executor.py` | MVP-4 (A3) |
| 741 | `deerflow/sandbox/tools.py` | MVP-0 删除 (B4) |
| 722 | `tools/md_to_json.py` | MVP-2 (随 SchemaEngine 收编) |
| 677 | `config/llm_config.py` | 保留 |
| 661 | `models/resolver.py` | MVP-0 (silent failure 修) |

**MVP-0 完成后预期变化**:
- deerflow 相关 ~3000+ 行减少（vendored deerflow 完全删除 + skills/parser.py 冗余）
- multimodal tools ~600 行减少
- parallel_delegate + subgraph + subgraph_cycle ~600-800 行减少
- 总行数估算降到 ~24,000 lines（~15% 减少）
- Top 大文件清单不变（拆解归后续 MVP）

## 4. e2e metrics (reference baseline — from 2026-04-28T17 v11 chain run)

来自 `/tmp/claude-1001/-home-sevenx-coding-agent-harness/ca77c4d7-0622-4591-a7e3-4a18f1229615/tasks/bgcemu3sg.output`（v11 e2e chain，4 SKILL 链）：

| Stage | 耗时 | input tokens | output tokens | 关键 metrics |
|---|---|---|---|---|
| text-segmentation | 缓存（之前跑过） | - | - | - |
| event-extraction | 348.8s | 82,993 | 23,500 | aggregate phase: 8 events; review: 8 events_reviewed; settings: 7 |
| batch-analysis | 131.9s | 55,737 | 7,300 | continuity_warnings: 1 |
| global-synthesis | 57.5s | 13,095 | 3,338 | retroactive_corrections: 1; final story_framework saved |
| **总计** | **538.2s** | **151,825** | **34,138** | **events: 8 / settings: 7 / continuity: 1 / retroactive: 1** |

**输出文件**:
- `chapter_1_segments.json` (text-seg)
- `chapter_1_events.json` (event-extr)
- `output/batch-analysis/batch__result.json` + `batch__accumulated.json`
- `output/global-synthesis/story_framework.json`

**MVP-0 完成后预期变化**:
- 耗时 ±20% 内（ruff / mypy 等门禁不影响 runtime）
- token 用量 ±10% 内
- **关键 metrics 不允许退步**（events: 8 / settings: 7 / continuity: 1 / retroactive: 1 必须 ≥ baseline）
- 输出文件结构 + JSON schema 完全一致

## 5. silent failure clean count

**当前已知 silent failure 位置**（A6 范围）：

```
src/core/graph_agent/core/runner.py:227 except OSError -> pass
src/core/graph_agent/core/runner.py:336 except ImportError -> pass
src/core/graph_agent/models/resolver.py:626 except Exception -> pass
src/core/graph_agent/cognitive/middlewares.py:336 except (TypeError, ValueError) -> return {}
src/core/graph_agent/cognitive/middlewares.py:615 except (TypeError, ValueError) -> return {}
src/core/graph_agent/core/validators/tool_paths.py:228 except (...) -> return None
src/core/graph_agent/config/llm_config.py:594 except OSError -> return None
src/core/graph_agent/config/multimodal_config.py:298 except OSError -> return None  # B2 删除时一并消失
src/core/graph_agent/core/harness.py:307 except TypeError -> 浅拷贝 fallback
src/core/graph_agent/core/harness.py:431 except Exception -> warning + return None
src/core/graph_agent/core/harness.py:715 except Exception -> warning + emit run_completed
```

**MVP-0 完成后预期**:
- 上述 11 处全部消除：要么抛错（PersistenceError / CheckpointError / TraceWriteError 等），要么显式降级（Pattern B 加 logger.warning），要么 LLM 反馈（Pattern C，仅 middlewares.py 那两条）
- **目标**：grep silent failure pattern 命中数 = 0（含 explained warnings）

## 6. 双 ContextBridge 定义位置

```
src/core/graph_agent/core/types.py:17       class ContextBridge (dataclass)   # MVP-0 删除
src/core/graph_agent/core/manifest.py:180   class ContextBridge (BaseModel)   # MVP-0 保留
```

**MVP-0 完成后预期**:
- `grep -rn "class ContextBridge" src/core/graph_agent` 输出仅 1 行（`manifest.py:180`）

## 7. 双 pyproject.toml 位置

```
./pyproject.toml                                  # 根目录，MVP-0 保留
./src/core/graph_agent/pyproject.toml             # MVP-0 删除（合并到根）
```

**MVP-0 完成后预期**:
- `find . -name pyproject.toml -not -path "*/.venv/*"` 输出仅 1 行（`./pyproject.toml`）

---

## Diff 验证清单（MVP-0 完成后主控做）

| # | 静态对比 | baseline | 完成后预期 | pass criteria |
|---|---|---|---|---|
| 1 | 7 SKILL compile 状态 | 见 §1 | 4 核心 WARN 不增 / story-deconstruction 移走 / 2 PASS 仍 PASS | strict |
| 2 | pytest passed 数 | 661 | ≥ 580 (允许减，不允许 fail) | strict |
| 3 | 总行数 | 28,494 | ≈ 24,000 (15% 减) | range |
| 4 | e2e key metrics | events:8 / settings:7 / continuity:1 / retroactive:1 | 全部 ≥ baseline | strict |
| 5 | silent failure 命中 | 11 处 | 0 处 | strict |
| 6 | ContextBridge 定义数 | 2 | 1 (`manifest.py`) | strict |
| 7 | pyproject 数 | 2 | 1 (根) | strict |
| 8 | 大文件清单 | top 9 见 §3 | deerflow/* 消失，其他不变 | structure |
