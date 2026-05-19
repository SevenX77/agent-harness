# MVP-2 Tasks — A5 SchemaEngine + A7 IOManager 子任务派发

> 整合 Gemini Part E 子任务清单 + 主控调度优化（a1/a3 并行 + 依赖图修订）。

## 派发策略

- **a1 codex 主线**: T1 → T2 → T3（连续 SchemaEngine + IOManager 创建, 重型基础设施）
- **a3 claude 副线**: T0-prep（基线测量）→ T4 → T6 → T5 → T7 → T8（等 a1 主线完成相应依赖后接调用方改造 + 单测）
- **a3 代码必须由 a1 codex review**（按 ccb-collaboration 角色铁律）
- **a2 gemini design review**: 本 spec 落盘后 PM 派 a2 审 design.md（30-60 min）, 分歧时 PM vs Gemini 辩论 3 轮

每个 brief 必含**铁律 block**:
```
🚨 严禁 git mutate HEAD: git checkout/switch/reset/cherry-pick/merge/rebase/pull/stash. 只允许 read-only.
🚨 不要 commit / push / 创 PR / 派 ccb 给其他 agent.
```

## 关键路径

```
T0-prep (1h, a3) ──┐
                   ↓
T1 (2h, a1) → T2 (2h, a1) → T3 (2h, a1) ──┐
                            └─→ T6 (1h, a3) ─┐
                                T4 (1h, a3) ─┤
                                T5 (2h, a3) ─┼→ T8 (3h, a3)
                                T7 (1h, a3) ─┘
```

最长链 = T0-prep + T1 + T2 + T3 + T5 + T8 = 1+2+2+2+2+3 = **12h**（a1+a3 并行版）。  
Gemini 原估时未含 T0-prep 与 review/CI overhead，本表估总 14-18h（含 design 审 + a1 review + PR 周转）。

## 子任务清单

### T0-prep — Baseline 数据测量 + 现状审计

- **Owner**: a3 claude
- **依赖**: 无（在派 T1 前必须完成）
- **估时**: 1h
- **产物**: `docs/v1-reset/mvp-2-baseline-snapshot.md` 含:
  - `loader.py` 总行数 + schema/io 相关函数清单
  - `finish.py` 总行数 + schema/io 相关函数清单
  - 5 处 schema 解析弥散点的具体函数 + 行号
  - output_example 解析正则的精确位置（cleaning patterns）
  - 4 核心 SKILL 的 output_schema / output_example 多样性统计
  - md_to_json.py 访问 Manifest 私有方法的清单
- **验收**:
  - `ls docs/v1-reset/mvp-2-baseline-snapshot.md` 存在
  - 文档含 baseline metrics 数字（不允许仅有占位符）
  - 不动任何 src/ tests/ 文件

### T1 — 创建 `SchemaEngine` 核心类，迁移文本解析逻辑

- **Owner**: a1 codex
- **依赖**: T0-prep
- **估时**: 2h
- **产物**:
  - `src/core/graph_agent/core/schema_engine.py` 新文件
  - `SchemaObject` / `ValidationResult` dataclass 定义
  - `SchemaEngine.parse_from_md` / `validate_spec_dict` / `get_json_schema` 方法实现
  - 现有 loader.py output_schema/output_example 解析正则**完全复制**到 schema_engine.py（不重写, 见 design D7）
  - 单测 `tests/graph_agent/core/test_schema_engine.py` 含:
    - 5+ 正向测试（合法 schema 解析）
    - 5+ 负向测试（畸形 schema：缺字段 / 错类型 / 重复 key / output_example 缩进破坏）
    - SchemaObject frozen + hashable round-trip 测试
- **验收**:
  - `python -c "from graph_agent.core.schema_engine import SchemaEngine; SchemaEngine().parse_from_md('---\\nfield_a: str\\n---')"` 不报错
  - mypy strict 在 schema_engine.py 通过
  - SchemaEngine 单测覆盖率 ≥ 95%
  - pytest 不退步（loader.py 此时未改, 仍用旧解析, 行为不变）

### T2 — 迁移 Pydantic 模型动态生成逻辑至 SchemaEngine

- **Owner**: a1 codex
- **依赖**: T1
- **估时**: 2h
- **产物**:
  - `SchemaEngine.get_pydantic_model` 方法实现 + lru_cache（design §1.3）
  - `SchemaEngine.validate` 方法实现（基于 get_pydantic_model）
  - `core/state.py` 新增 `build_business_data_for_skill` 工厂函数（design §5.1）
  - 单测扩展（在 test_schema_engine.py 内追加）:
    - `test_pydantic_model_caching`（同一 schema 多次调用返同一类）
    - `test_validate_round_trip`（validate ok → parsed dict equals input）
    - `test_validate_negative_cases`（畸形输入 → ValidationResult.errors 非空）
    - `test_business_data_subclass_factory`（动态生成的子类继承 BusinessData + extra="allow"）
- **验收**:
  - `from graph_agent.core.schema_engine import SchemaEngine, SchemaObject, ValidationResult` 全部 import 成功
  - mypy strict 在 schema_engine.py + state.py（factory 部分）通过
  - 单测覆盖率仍 ≥ 95%
  - pytest 不退步

### T3 — 创建 `IOManager`，迁移 `hoist_to` 定向搬运逻辑

- **Owner**: a1 codex
- **依赖**: T2
- **估时**: 2h
- **产物**:
  - `src/core/graph_agent/core/io_manager.py` 新文件
  - `IOManager.__init__` / `resolve_hoist` / `validate_spec` 方法实现
  - 单测 `tests/graph_agent/core/test_io_manager.py` 含:
    - `test_resolve_hoist_basic`（基础字段搬运）
    - `test_resolve_hoist_missing_field`（缺字段 → io_errors 非空）
    - `test_resolve_hoist_type_mismatch`（类型不匹配 → io_errors + advisory mode 仍写入）
    - `test_resolve_hoist_nested_path`（嵌套字段路径）
    - `test_validate_spec_negative`（非法 io_specs 编译期报错）
    - 5+ 测试覆盖以上场景
- **验收**:
  - `from graph_agent.core.io_manager import IOManager` 不报错
  - mypy strict 在 io_manager.py 通过
  - 单测覆盖率 ≥ 95%
  - pytest 不退步

### T4 — 重构 `ContextBridge`，使其依赖 `SchemaEngine`

- **Owner**: a3 claude
- **依赖**: T1（仅需 SchemaEngine.parse_from_md 接口可用）
- **估时**: 1h
- **可与 T3 并行**
- **产物**:
  - `core/manifest.py:ContextBridge` 增加 `to_business_data_schema(schema_engine: SchemaEngine) -> SchemaObject` 方法（design §3.2）
  - 内部不含任何 markdown 解析或 Pydantic 类构造逻辑
  - 单测扩展 `tests/graph_agent/core/test_manifest.py` 含:
    - `test_context_bridge_to_business_data_schema`（调用 SchemaEngine 取 schema）
    - `test_context_bridge_no_schema_returns_empty`（缺 schema 时返空 SchemaObject）
- **验收**:
  - `grep "re\\.compile\\|json\\.loads" src/core/graph_agent/core/manifest.py` 在 ContextBridge 上下文 0 hits
  - pytest tests/graph_agent/core/test_manifest.py 全过

### T5 — 改造 `finish.py`，调用 SchemaEngine 校验 + IOManager 搬运

- **Owner**: a3 claude
- **依赖**: T3（IOManager 完整可用）
- **估时**: 2h
- **产物**:
  - `cognitive/finish.py` 改造（design §4.2）:
    - 不再含 schema 字符串解析 / 校验 / 手动赋值
    - 改为返回 `{"finish_task_result": parsed, "diagnostics": ...}` 由 phase_executor 路由
  - `phase_executor.py` 在 LLM phase 收尾段加 IOManager.resolve_hoist 调用（design §4.3, 最小改动, 不重画）
- **验收**:
  - `grep -E 'state\\["data"\\]\\[.*\\] *=' src/core/graph_agent/cognitive/finish.py` 0 hits
  - `grep -E 're\\.compile|json\\.loads' src/core/graph_agent/cognitive/finish.py` 在 schema 解析上下文 0 hits
  - pytest tests/graph_agent/cognitive/test_finish*.py 全过
  - 4 SKILL e2e smoke 跑 1 chapter 不破裂

### T6 — 改造 `loader.py`，移除冗余解析代码，改调用 SchemaEngine

- **Owner**: a3 claude
- **依赖**: T2（需要 SchemaEngine.parse_from_md + get_pydantic_model）
- **估时**: 1h
- **可与 T4 并行**
- **产物**:
  - `core/loader.py` 改造（design §4.1）:
    - 添加 `self._schema_engine = SchemaEngine()` 实例
    - 把现有 schema 解析点改为 `self._schema_engine.parse_from_md(...)` 调用
    - phase 对象改保存 `compiled_schema: SchemaObject` 不再保存 raw dict
  - `tools/md_to_json.py` 改造:
    - 不再访问 Manifest 私有方法
    - 改通过 `SchemaEngine.get_json_schema` 获取 prompt 视图
- **验收**:
  - `grep -E 're\\.compile.*output_schema|json\\.loads' src/core/graph_agent/core/loader.py` 在 schema 解析上下文 0 hits
  - `loader.py` 行数减少比例 ≥ 30%（vs T0-prep baseline）
  - pytest tests/graph_agent/core/test_loader*.py 全过
  - 4 SKILL compile 状态不变（WARN-only / 1 PASS）

### T7 — 迁移 `io_errors` 收集逻辑至 FrameworkState

- **Owner**: a3 claude
- **依赖**: T3（IOManager 已写入 io_errors）
- **估时**: 1h
- **产物**:
  - `phase_executor.py` 中 io_errors 累积逻辑改为写到 `state["flow"].io_errors`（research D6）
  - 不再写到 `flow.metrics["io_errors"]`（修订 Gemini 原方案）
  - 旧 `tools/io/manager.py` 中的 io_errors 处理逻辑（如有）剥离或重定向到 IOManager
- **验收**:
  - `grep 'metrics\\["io_errors"\\]' src/core/graph_agent/` 0 hits
  - pytest tests/graph_agent/core/test_phase_executor*.py 全过
  - flow.io_errors 在 e2e smoke 中能正确累积错误（4 SKILL 无错误时为空 list）

### T8 — 针对新模块的单元测试覆盖 + 集成测试

- **Owner**: a3 claude
- **依赖**: T1-T7 全部完成
- **估时**: 3h
- **产物**:
  - 补全 SchemaEngine 单测覆盖率到 ≥ 95%（含 10+ 畸形 SKILL.md 片段）
  - 补全 IOManager 单测覆盖率到 ≥ 95%
  - 新增集成测试 `tests/graph_agent/integration/test_mvp2_schema_io.py` 含:
    - `test_compile_skill_uses_schema_engine`（loader 编译 1 SKILL 不抛错, schema 通过 SchemaEngine）
    - `test_finish_task_routes_via_io_manager`（finish_task 触发 IOManager.resolve_hoist, BusinessData 字段被填）
    - `test_io_errors_propagate_to_flow`（缺字段时 flow.io_errors 非空）
    - `test_4_skill_compile_unchanged`（4 SKILL compile 状态对比 baseline）
  - 4 SKILL e2e smoke 报告（跑 1 chapter）
- **验收**:
  - SchemaEngine + IOManager 单测覆盖率均 ≥ 95%
  - pytest 全过（不退步），test_strict_v2 14 pre-existing failures 仍 isolated
  - 4 SKILL compile 状态 unchanged
  - 4 SKILL e2e smoke 跑 1 chapter 全过
  - coverage 不退步（≥ 65% 整体）

## a1 review 节奏

- **每子任务 review**（针对 a3 的 T0-prep / T4 / T5 / T6 / T7 / T8）: a3 完成后 a1 立刻 review，找出问题后 a3 修，主控 commit
- **MVP-2 整体 review**: T8 done 后 a1 把所有 MVP-2 commits 整体过一遍 + cumulative spotcheck 一致性, 验证 design.md §6 baseline diff 全部满足

## 主控调度

派发顺序（伪时间线）:

```
t=0    spec 4 docs 落盘 commit; 派 a3 T0-prep + 同时派 a2 design review (30 min)
t=1h   a3 T0-prep done; a2 design review done; 主控整合 review 反馈; 派 a1 T1
t=3h   a1 T1 done; 主控 commit T1; 派 a1 T2 + a3 T4 (并行)
t=4h   a3 T4 done → a1 review (10min); a3 fix → 主控 commit T4
t=5h   a1 T2 done; 主控 commit T2; 派 a1 T3 + a3 T6 (并行)
t=6h   a3 T6 done → a1 review (15min); a3 fix → 主控 commit T6
t=7h   a1 T3 done; 主控 commit T3; 派 a3 T5 + a3 T7 (并行)
t=9h   a3 T5+T7 done → a1 review (20min); a3 fix → 主控 commit T5+T7
t=10h  派 a3 T8
t=13h  a3 T8 done → 主控 commit + a1 整体 review
t=14h  a1 整体 review done → 主控 squash + push + PR + CI green + merge
```

总估 = 14-18h wall-clock（含 a2 design review / a1 cumulative review / CI / PR 周转）。

## Pre-flight checklist

派 T0-prep 前主控自检:
- [ ] MVP-1 已 merge 到 main（feat/v1-reset-mvp-1 → main）
- [ ] BusinessData / FrameworkState / StateManager 在 main 可用
- [ ] spec 4 docs 落盘（.kiro/specs/v1-reset-mvp-2-schema-io/{requirements,research,design,tasks}.md）
- [ ] Gemini design 已审（job_dc2b328ebc8e reply 整合到 design.md）
- [ ] a2 design review 派出（30-60 min, 跟 T0-prep 并行）
- [ ] orchestrator scope 起好（可选；MVP-1 没有强依赖；可走 default ccbd）
- [ ] a1 codex 当前状态 = idle (已 /clear)
- [ ] a3 claude 当前状态 = idle

## 跟 MVP-1 / MVP-3 的衔接

- **MVP-1 已就位 (前置依赖)**: BusinessData (extra="allow") / FrameworkState (extra="forbid") / StateManager / `flow.io_errors: list[str]`
- **MVP-3 接口约定 (后置)**: SchemaEngine 提供 SchemaObject 中间表示, MVP-3 loader 拆解时 Parser 直接复用; A9 路径解析 hack 不归 MVP-2 管
- **MVP-4 接口约定**: phase_executor MVP-4 重画时, IOManager.resolve_hoist 调用点会被吸收/重画, MVP-2 加的最小调用段是过渡形态
