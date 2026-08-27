---
doc: INDEX
role: index
status: living
updated: 2026-08-27
---

# Graph Agent MVP1 文档索引

本文是 engine MVP1 文档入口。历史迁移目录 `docs/engine/mvp1/_migration-src/` 已在 2026-06-28 删除；已迁内容以正式模块文档为准，需要历史记录时看 git 历史。

本文只索引**当前 engine MVP1 契约**。将 engine 提炼为独立 Python runtime/PyPI 包的未来目标另见 [Graph Skill Runtime 文档索引](../graph-skill-runtime/README.md)。该目标目前为 `drafted`，尚未替代本目录或当前 FROZEN skill format。

## 1. 三层结构

| Layer | Scope | Directory |
| --- | --- | --- |
| A. Contract | skill 文件格式、编译规则、数据契约、失效规则 | `01-contract/` |
| B. Mechanism | compile / resolve / assemble / run outer / run inner / seam / runtime | `02-mechanism/` |
| C. API Contract | engine 与 Studio 的操作边界 | `03-api-contract/` |

## 2. Contract Modules

| Module | Purpose |
| --- | --- |
| `01-contract/01-physical-layout` | 文件树、`.workspace`、运行产物位置 |
| `01-contract/02-skill-syntax` | skill 语法在 MVP1 中的职责边界；格式模板唯一真相源见 `../skill-spec/00-FORMAT-GROUND-TRUTH.md` |
| `01-contract/03-compile-rules` | 编译/装配/运行生命周期规则与错误码 |
| `01-contract/04-data-contracts` | WorkflowState / result / error payload 等数据形状 |
| `01-contract/05-invalidation` | source change 到 golden/checkpoint/cache 的失效模型 |

## 3. Mechanism Modules

| Module | Purpose |
| --- | --- |
| `02-mechanism/01-compile` | loader/parser/validator/cache/purity scanner |
| `02-mechanism/02-resolver` | subgraph path resolver |
| `02-mechanism/03-assemble` | AST 到 runnable graph / prompt assembly |
| `02-mechanism/04-run-outer/01-graph-exec` | graph-level execution, StateMapper, LOGIC/SUBGRAPH dispatch |
| `02-mechanism/04-run-outer/02-iterate` | batch/loop/graph-level iterate runtime |
| `02-mechanism/04-run-outer/03-checkpoint` | shared checkpoint base and outer blackboard persistence |
| `02-mechanism/05-run-inner/01-agent-loop` | Agent loop |
| `02-mechanism/05-run-inner/02-middleware` | middleware slots and order |
| `02-mechanism/05-run-inner/03-cognitive` | cognitive flow and finish_task |
| `02-mechanism/05-run-inner/04-tools` | tools and tool error behavior |
| `02-mechanism/05-run-inner/05-exit-control` | explicit exit gate |
| `02-mechanism/05-run-inner/06-golden-eval` | golden evaluation |
| `02-mechanism/05-run-inner/07-subagent` | runtime subagent dispatch |
| `02-mechanism/05-run-inner/08-messages-state` | inner messages state and resume |
| `02-mechanism/06-seam/01-models` | model gateway seam and predict mocks |
| `02-mechanism/06-seam/02-observability` | typed events, traces, metrics |
| `02-mechanism/07-runtime` | public SDK runtime entrypoints |

## 4. API Contract

| Module | Purpose |
| --- | --- |
| `03-api-contract` | compile/run/predict/resume/golden API signatures, event protocol, Studio HTTP contract |

## 5. Current SSOT Notes

- Skill file templates: [`docs/engine/skill-spec/00-FORMAT-GROUND-TRUTH.md`](../skill-spec/00-FORMAT-GROUND-TRUTH.md).
- MVP1 syntax alignment links to the skill-spec template and must not duplicate YAML examples.
- `_migration-src` is no longer part of the live doc set.
- Future extraction target: [`docs/engine/graph-skill-runtime/v1-alignment.md`](../graph-skill-runtime/v1-alignment.md). It remains drafted until implementation, migration verification, and reference cutover are complete.
