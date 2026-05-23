# MVP-2 Baseline Snapshot (2026-04-29 pre-T2/T3/T6)

> 主控漏派 T0-prep, MVP-2 T1 a3 报告里指出后补做.
> 测的是 MVP-2 改造**前**的状态, 给 T6 (loader.py -30%) + T8 (单测覆盖 ≥ 95%) 提供验收参考.
> MVP-1 T1/T2/T6 已 commit, T3/T4/T7 仍在 a1/a3 实施中, 因此一些 _md_schema 等字段已迁移到 flow.X 但旧 `ctx[...]` 调用仍部分存在.

## 1. loader.py 现状

### 总行数
| 指标 | 值 |
|---|---|
| `loader.py` 总行数 | **776** |
| schema/output_schema/output_example/md_schema 关键词出现次数 (grep -c) | 58 |
| schema 相关行数 (file:line 实测, 唯一行) | ~30 行直接, ~80-100 行间接 (含函数体) |

### 关键 schema 处理函数 (T6 改造目标)

| 行 | 函数名 | 责任 |
|---|---|---|
| 49-65 | `_parse_output_example_or_raise` | 把 SKILL.md `output_example` 文本 → schema dict (调 `parse_output_example`) — **T6 整段抽到 SchemaEngine.parse_from_md** |
| 460-476 | `_render_output_format_markdown` 内部 | 渲染 schema 给 prompt — **T6 部分抽到 SchemaEngine.get_json_schema** |
| 485-567 | `_resolve_output_schema_path` | dotted path → Pydantic class, **含 sys.modules hack** — **MVP-3 A9-original 范围, MVP-2 T6 不动** |
| 671-755 | `_phase_from_graph_phase` 内 schema 段 | 处理 `phase_def.output_example` / `output_schema` 二选一 + 注入 hoist_to / dynamic_schema — **T6 部分抽** |

### 估 T6 可减行数

- `_parse_output_example_or_raise` (17 行) + `_render_output_format_markdown` 含 schema 的部分 (~50 行) + `_phase_from_graph_phase` schema 段 (~30 行) = **~97 行**
- 776 → 776 - 97 = **679 行** = 减 12.5% ⚠️ **不足 30%**
- **风险: T6 单独无法达到 -30% 目标**, 需结合 T2/T3 合并削减或调整 KPI (见第 7 段)

## 2. 5 处 schema 弥散点 (a2 design Part A 复核)

| 文件 | 行号 | 函数 | 责任 | T6 可剥离量 |
|---|---|---|---|---|
| `core/loader.py` | 49-65, 460-485, 485-567, 671-755 | 多个 | output_example 解析 + output_schema 路径解析 + dynamic_schema 构造 | ~97 行 |
| `cognitive/finish.py` | 24, 34, 41-42, 88 | finish_task | schema_validation 错误消息 + skipped 标记 | ~10 行 (主要错误消息字符串模板) |
| `tools/md_to_json.py` | 521-547 | `md_to_json` | 读 ctx["_md_schema"] / ctx["_md_schema_path"] | ~10 行 (T6 改用 SchemaEngine.get_json_schema 后) |
| `core/manifest.py` | 198-210 | `LLMPhase` | output_schema / output_example / hoist_to 字段定义 | ~5 行 (字段定义不动, 但 ContextBridge 接口归 T4) |
| `core/artifact_manager.py` | (无) | (无) | **a2 design 列出但实际 0 站点** | 0 (a2 估错) |
| `core/phase_executor.py` | 380-381, 562-563 | `_inject_md_schema_path` 区段 | 把 phase.output_schema_path 注入 flow.md_schema_path / agent_config | ~5 行 (T6 不动, 后续 MVP-4 重画 phase_executor 时一起处理) |

**结论**: a2 design Part A 列出 5 处弥散点中 1 处 (artifact_manager) 实际不存在; 另外 4 处中, loader.py 是大头 (~97 行), 其他 3 处合计 ~25 行. T6 改造**实际**可剥离量 = ~120 行 (loader 97 + finish 10 + md_to_json 10 + 余下小段 ~3 行).

## 3. 4 SKILL schema 多样性

### 顶层 SKILL.md 扫描

| SKILL | 路径 | output_schema (顶层) | <output_example> 标签 (顶层) |
|---|---|---|---|
| text-segmentation | skills/text-segmentation/SKILL.md | 0 | 0 |
| batch-analysis | skills/batch-analysis/SKILL.md | 0 | 0 |
| event-extraction | skills/event-extraction/SKILL.md | 0 | 0 |
| global-synthesis | skills/global-synthesis/SKILL.md | 0 | 0 |

**关键发现**: 4 核心 SKILL **顶层 SKILL.md 全部没有 output_schema / output_example**! 它们是 graph 类型 SKILL, schema 声明在 **phase 级** (phases[i].output_schema), 不是顶层级.

### Phase 级 schema 分布

`grep -c 'output_schema:\|output_example:' skills/*/SKILL.md skills/*/v*/SKILL.md` 实际跑得到 phase 级 schema 分布 — 但 grep 也大量命中 docstring 引用. 准确分布需 T3/T6 实施时手工确认.

### versioned 子 SKILL

text-segmentation 有 4 个 versioned 子 SKILL (`versions/v0..v3/SKILL.md`), 每版本都有自己的 phase + schema. T6 改造时必须保证 4 版本都能 compile 不破裂.

## 4. IOManager 现状

### io.outputs / hoist_to / io_errors 站点统计

| 文件 | 站点数 | 责任分类 |
|---|---|---|
| `core/validators/strict_v2.py` | ~25 (line 117-454) | 编译期校验 hoist_to + io.outputs 合法 — **T3 IOManager.validate_spec 应吸收** |
| `io/manager.py` | 5 (line 141, 326, 329 + 其他) | 运行时 io 搬运 + io_errors 累积 (旧 `context["_io_errors"]` 路径) — **T3 IOManager.resolve_hoist 替代** |
| `core/loader.py` | 4 (line 704, 721, 722, 755) | hoist_to 字段从 phase_def 传到 dynamic_schema / validator — **T3 改为通过 IOManager 接管** |
| `core/manifest.py` | 2 (line 119, 202) | IODef 模型定义 + LLMPhase.hoist_to 字段 — **不动** |
| `core/state.py` | 1 (line 69) | `io_errors: list[str]` FrameworkState 字段 (MVP-1 已声明) — **不动** |
| `core/template.py` | 1 (line 41) | error message 引用 hoist_to 关键词 — **不动** |
| `core/phase_executor.py` | (未列, 需 T0-prep 之后 T7 实施时再 grep) | io_errors 收集逻辑 — **T7 迁到 flow.io_errors** |

总计: **43 处** 站点 (跟主 brief 的 grep 数字一致).

### IO 现状关键耦合点

- `io/manager.py:326-329` 仍写 `context["_io_errors"]` (MVP-1 已废, 但代码未跟进) — T7 必清
- `validators/strict_v2.py` 25 站点 schema 校验逻辑很重 (line 286-415 含 schema_ref 解析 + 上游 io.outputs[key].example 提取) — T3 IOManager.validate_spec 吸收时要 careful

## 5. T6 验收 baseline (loader.py -30%)

### 当前 baseline
- loader.py 总行数: **776**
- 30% 削减目标: ≤ 776 × 0.7 = **≤ 543 行**

### 实际可达性评估

按 §1 估算, T6 单独可剥离 ~97 行 (loader 内部 schema 段) → 776 - 97 = **679 行** = 减 **12.5%**, **远低于 30% 目标**.

### 主控决策选项

- **A) 调 T6 KPI 到 -15%** (实际可达, 776 → ≤ 660): 跟 MVP-3 A2 (loader 拆三阶段 + ModuleSandbox) 累计达 -75% 目标. MVP-3 spec design.md §7 已写 "loader.py SLOC ≤ 200", MVP-2 阶段先减到 ~660, MVP-3 进一步减到 ≤ 200, 累计 -75% 仍达成
- **B) 维持 -30% 目标, T6 + T7 合并削减**: T7 把 io_errors 迁移到 flow.io_errors 时, 顺便把 loader.py 内 hoist_to 注入逻辑 (line 704-755) 也抽到 IOManager, 估额外 ~30 行剥离 → 总 ~127 行剥离 = **776 → 649** = 减 **16.4%**, 仍不足
- **C) 维持 -30% 目标, 顺手把 _resolve_output_schema_path (line 485-567, ~82 行) 也抽**: 但 MVP-3 §A9-original 已规划这个改造, MVP-2 提前做会破坏 MVP-3 边界. 不推荐.
- **D) 重新定义 KPI**: -30% 是从 MVP-2 后 baseline 算 (776) 还是 MVP-1 baseline 算? 如果是 MVP-1 baseline (假设 ~820 行) 算到 MVP-2 末尾达 ≤ 575 行 (即剥离 ~245 行), 那需要 T2/T3/T4/T5/T6/T7 全部累计剥离才行 — 不切实际.

**a3 推荐**: **选项 A** — 调 T6 KPI 到 -15%, 把 -30% 留给"MVP-2 + MVP-3 累计"目标. 主控 commit MVP-2 spec 时同步修订 design.md §6 + tasks.md T6 验收门槛.

## 6. T8 验收 baseline (新模块覆盖率 ≥ 95%)

| 模块 | 当前状态 | T8 目标 |
|---|---|---|
| `core/schema_engine.py` | T1 已建 (132 行), 11 测试覆盖 stub 100% | 接入实际逻辑后保持 ≥ 95% |
| `core/io_manager.py` | **未建** (T3 才建) | 建后单测覆盖 ≥ 95% |
| `tests/graph_agent/core/test_schema_engine.py` | T1 已建 (136 行, 11 tests) | T2/T3 增加 ~10-15 测试覆盖真实逻辑 |
| `tests/graph_agent/core/test_io_manager.py` | **未建** (T3 才建) | 建后含 5+ 测试 (基础 hoist / 缺字段 / 类型不匹配 / 嵌套 / 空 io_specs) |

**当前覆盖率**: SchemaEngine = 100% (stub 全覆盖), IOManager = N/A (未建).

## 7. 风险点

### R1: a2 design Part A 现状审计有偏差
- **artifact_manager.py 在 a2 列表但实际 0 schema 站点** — T6 实施时不要去那找代码, a2 估错
- **4 SKILL 顶层 SKILL.md 全部 0 output_schema** — schema 都在 phase 级, 跟 a2 design 假设的"output_schema 字段"分布不一致
- **影响**: T6 改造范围比 a2 design 估的小, T6 -30% 目标不切实际 (见 §5)

### R2: text-segmentation 4 versioned 子 SKILL 兼容性
- text-segmentation 有 v0/v1/v2/v3 4 版本, 每版 phase 数 + schema 不同
- T6 改 schema 解析路径后, 必须保证 4 版本全部 compile 不破裂
- **缓解**: T6 验收脚本必须含 `for v in v0 v1 v2 v3; do scripts/compile_skill skills/text-segmentation/versions/$v-...; done`

### R3: md_to_json.py 跟 MVP-1 flow.md_schema 字段联动
- md_to_json.py:537-547 当前仍读 `ctx["_md_schema"]` / `ctx["_md_schema_path"]` (MVP-1 旧路径)
- MVP-1 T6 已 commit (commit 9e011ff), 该 commit 的产物是 finish.py + md_to_json.py 元数据剥离 — 但本次 grep 仍看到 ctx[...] 调用
- **可能解释**: 9e011ff 移除了**注入**端 (从 phase_executor 注入 _md_id 到 ctx 的逻辑), 但**消费**端 (md_to_json 读 ctx) 仍在
- **影响 T6**: MVP-2 T6 改造时必须确认 md_to_json 接入 SchemaEngine.get_json_schema 后, ctx[] 读取路径完全消失 (而不是仅注入端清理)
- **缓解**: T6 验收必须 grep `ctx\["_md_schema` 在 md_to_json.py 0 hits

### R4: validators/strict_v2.py 14 pre-existing failures
- MVP-0 baseline 14 failures isolated, MVP-2 T6 不能恶化
- strict_v2.py 内 schema_ref / io.outputs 解析 (line 196-454) 是 T3 IOManager.validate_spec 吸收的目标
- **缓解**: T3 实施时把 strict_v2 的 schema 校验逻辑搬到 IOManager 但保持函数签名兼容 (避免引入新 failure)

### R5: output_example 跟 output_schema 互斥规则
- loader.py:690-693 强制 phase 不能同时声明 output_example + output_schema
- T6 抽 SchemaEngine 后必须保留这个互斥规则
- **缓解**: T6 单测覆盖 "phase 同时声明两者 → 抛 LoaderError"

完结. 报告 nothing-to-commit, untracked. 主控决策 T6 KPI 选项 (A/B/C/D) 后即可继续派 T2/T3/T4.
