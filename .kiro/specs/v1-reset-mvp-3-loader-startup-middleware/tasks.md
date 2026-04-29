# MVP-3 Tasks — A2 Loader / A9 hack / B3 Middleware 子任务派发

> 整合 Gemini Part F 12 任务清单 + 主控调度优化 (修订 a2 design Part E 实施顺序, 见 research D4)。

## 派发策略

- **a1 codex 主线**: T2 → T4 → T5 → T8 (重型: SkillManifest 模型 + validate_manifest + build_graph_nodes + CognitiveFlowMiddleware)
- **a3 claude 副线**: T0-prep → T1 → T3 / T7 (并行) → T6 / T9 / T10 → T11 → T12 (短链 + 测试 + 清理)
- **a3 代码必须由 a1 codex review** (按 ccb-collaboration 角色铁律)
- **a2 gemini design review**: 本 spec 落盘后 PM 派 a2 审 design.md, 重点 review research D2 (A9 误读纠正) 和 D3 (4 middleware 顺序契约), 30-60 min, 分歧时 PM vs Gemini 辩论 3 轮

每个 brief 必含**铁律 block**:
```
🚨 严禁 git mutate HEAD: git checkout/switch/reset/cherry-pick/merge/rebase/pull/stash. 只允许 read-only.
🚨 不要 commit / push / 创 PR / 派 ccb 给其他 agent.
```

## 关键路径

```
T0-prep (1.5h, a3) ──┐
                     ↓
T1 (2h, a1) ─────────┤
T2 (2h, a1) ─────────┴→ T3 (2h, a3) → T4 (2h, a1) → T5 (3h, a1) ──┐
                                      └─→ T7 (1h, a3) → T8 (3h, a1) ─┤
                                                       T9 (2h, a3) ──┤
                                                       T6 (2h, a3) ──┤
                                      T1 done → T10 (1h, a3) ──────┤
                                                                   ├→ T11 (4h, a3) → T12 (2h, a3)
```

最长链 = T0-prep + T2 + T3 + T4 + T5 + T8 + T11 + T12 = 1.5+2+2+2+3+3+4+2 = **19.5h** (a1+a3 并行版)。  
含 a2 design review + a1 cumulative review + CI/PR overhead, 总估 **22-26h** (≈ 3 工作日)。

## 子任务清单

### T0-prep — Baseline 数据测量 + 现状审计

- **Owner**: a3 claude
- **依赖**: 无
- **估时**: 1.5h
- **产物**: `docs/v1-reset/mvp-3-baseline-snapshot.md` 含:
  - `loader.py` 当前总行数 (MVP-2 后) + 各方法 SLOC 分布
  - `runner.py` 内所有 `os.environ.*` / `sys.path.*` / `sys.modules.*` 站点完整清单 (file:line + 上下文 5 行)
  - `_resolve_output_schema_path` 当前实现位置 + 内部 sys.modules 写入站点
  - Monkey-patch 散落清单 (grep `setattr.*langchain` / `__patch__` / `pytest_plugins` 等模式)
  - 当前 middleware 物理清单 (含派生类 + 装饰器 + 方法注册)
  - 启动延迟 baseline (跑 `scripts/measure_startup_latency.py` 10 次取中位数, 记数字)
  - 4 SKILL persona 渲染 snapshot (每 SKILL 跑 `python -c "from graph_agent.core.loader import SkillLoader; ...print(persona)"` 存到 `tests/graph_agent/snapshots/persona_<skill>.txt`)
- **验收**:
  - `ls docs/v1-reset/mvp-3-baseline-snapshot.md` 存在
  - persona snapshot 4 文件存在
  - 文档含 baseline metrics 数字 (不允许仅占位符)
  - 不动任何 src/ tests/ (snapshot 文件除外, 它们本就是新增的 baseline 资产)

### T1 — 创建 `Bootstrap` 类 + `Settings` (A9-bis: startup hack 清理)

- **Owner**: a1 codex
- **依赖**: T0-prep
- **估时**: 2h
- **产物**:
  - `src/core/graph_agent/bootstrap.py` 新文件 (Bootstrap 类, design §3.2)
  - `src/core/graph_agent/settings.py` 新文件 (Settings dataclass, design §3.3)
  - `src/core/graph_agent/patches/__init__.py` + 内部 monkey-patch 文件 (从 T0-prep grep 出的散落 patch 集中)
  - 单测 `tests/graph_agent/test_bootstrap.py` 含 5+ 测试 (apply_patches 一次性 / load_settings round-trip / 异常路径)
- **验收**:
  - `python -c "from graph_agent.bootstrap import Bootstrap; b=Bootstrap(); b.apply_patches(); s=b.load_settings()"` 不报错
  - mypy strict 在 bootstrap.py / settings.py 通过
  - 单测覆盖率 ≥ 95%
  - pytest 不退步 (此时 runner.py 还没改, 仍用旧 hack, 但新 Bootstrap 模块独立可用)

### T2 — 定义 `SkillManifest` Pydantic 全量模型

- **Owner**: a1 codex
- **依赖**: T0-prep
- **估时**: 2h (跟 T1 并行)
- **产物**:
  - `core/manifest.py` 扩展, 加 `SkillManifest` 顶层模型 (design §2)
  - `compiled_schemas: dict[str, SchemaObject]` 字段 (来自 MVP-2 SchemaObject)
  - 单测扩展 `tests/graph_agent/core/test_manifest.py` 含:
    - `test_skill_manifest_round_trip` (model_dump + model_validate)
    - `test_skill_manifest_extra_forbid`
    - `test_skill_manifest_compiled_schemas` (注入 SchemaObject 字段)
- **验收**:
  - `from graph_agent.core.manifest import SkillManifest` import 成功
  - mypy strict 通过
  - pytest 不退步

### T3 — 实现 `parse_skill_md` (Phase 1 纯文本解析)

- **Owner**: a3 claude
- **依赖**: T2
- **估时**: 2h
- **产物**:
  - `core/loader.py` 加 `parse_skill_md(text) -> dict` 函数 (design §1.1, Phase 1)
  - 仅 markdown 块结构化分割 + 顶层字段提取, **不**解析 schema 内部 (那是 Phase 2 调 SchemaEngine 的活)
  - 单测 `tests/graph_agent/core/test_parse_skill_md.py` 含:
    - 5+ 正向 (4 SKILL 现有 SKILL.md 解析得到 dict 含预期 keys)
    - 5+ 负向 (缺顶层 yaml 块 / 重复 key / 错乱 markdown 等)
- **验收**:
  - `parse_skill_md(open("skills/text-segmentation/v3/SKILL.md").read())` 返回 dict 含 `name / description / phases / io` 等顶层 keys
  - 不调任何对象/类 (mypy strict 检查无 import 复杂依赖)
  - pytest 不退步

### T4 — 重写 `validate_manifest` 集成 MVP-2 SchemaEngine + IOManager

- **Owner**: a1 codex
- **依赖**: T2 + T3
- **估时**: 2h
- **产物**:
  - `core/loader.py` 加 `validate_manifest(raw, schema_engine, io_manager_factory) -> SkillManifest` 函数 (design §1.1, Phase 2)
  - 调 `schema_engine.validate_spec_dict` 校验 manifest 顶层
  - 调 `schema_engine.parse_from_md` 把每 phase output_schema_md → SchemaObject 存入 SkillManifest.compiled_schemas
  - 调 `io_manager_factory(io_specs).validate_spec` 校验 io.outputs / hoist_to 路径
  - 单测扩展 `tests/graph_agent/core/test_validate_manifest.py` 含:
    - 正向: 4 SKILL 全部通过校验
    - 负向: schema 无效 / hoist_to 路径不存在 / 重复 phase 名 等
- **验收**:
  - `validate_manifest(parse_skill_md(open(...).read()), SchemaEngine(), lambda specs: IOManager(specs, SchemaEngine()))` 4 SKILL 全过
  - mypy strict 通过
  - pytest 不退步

### T5 — 实现 `build_graph_nodes` + `ModuleSandbox` (A9-original: output_schema hack 剥离)

- **Owner**: a1 codex
- **依赖**: T4
- **估时**: 3h
- **产物**:
  - `core/module_sandbox.py` 新文件 (ModuleSandbox 类, design §4.2)
  - `core/loader.py` 加 `build_graph_nodes(manifest, schema_engine, module_sandbox) -> list[PhaseNode]` 函数
  - `core/phase_node.py` 新文件 (PhaseNode 类, 暴露 `.execute(state) -> WorkflowState`, design §1.1)
  - 调 `build_business_data_for_skill(manifest, schema_engine)` (MVP-2 工厂) 生成 BusinessData 子类
  - 通过 `module_sandbox.import_class(path)` 解析 output_schema_path / validator path, **不再**写 sys.modules
  - 单测 `tests/graph_agent/core/test_module_sandbox.py` + `tests/graph_agent/core/test_build_graph_nodes.py`
- **验收**:
  - `grep 'sys\.modules\[' src/core/graph_agent/core/loader.py src/core/graph_agent/core/module_sandbox.py` 0 hits
  - `_resolve_output_schema_path` 旧函数 (如果保留) 内部不再写 sys.modules
  - 4 SKILL 通过 build_graph_nodes 编译, 输出 list[PhaseNode]
  - PhaseNode 含 `.execute(state)` 同步方法
  - mypy strict 通过
  - pytest 不退步

### T6 — 废弃旧 `SkillLoader` 上帝类, 全面切换至三阶段 Pipeline

- **Owner**: a3 claude
- **依赖**: T5
- **估时**: 2h
- **产物**:
  - `core/loader.py` 旧 `SkillLoader._load_skill_md / _parse_manifest / _build_graph / _setup_namespace / _resolve_persona` 全部物理删除或迁移
  - 保留 `SkillLoader` 名字 (调用方稳定), 内部改为 thin orchestrator (design §1.2)
  - 调用方 (`runner.py` / `harness.py`) 不需要改动
- **验收**:
  - `cloc src/core/graph_agent/core/loader.py` 输出 SLOC ≤ 200
  - 4 SKILL compile 状态不变 (WARN-only / 1 PASS)
  - 4 SKILL e2e smoke 跑 1 chapter 不破裂
  - persona snapshot byte-equal (T0-prep 存的 4 文件)
  - pytest 不退步

### T7 — 整合 `ProtocolValidationMiddleware`

- **Owner**: a3 claude
- **依赖**: T4 (SkillManifest + SchemaEngine 集成完毕)
- **估时**: 1h
- **产物**:
  - `src/core/graph_agent/middleware/protocol_validation.py` 新文件 (design §5.2)
  - 吸收 `cognitive/middlewares.py:ValidationMiddleware` 的契约校验逻辑
  - 加入 MVP-1 BusinessData / FrameworkState extra 校验
  - 加入 MVP-2 SchemaEngine.validate 集成
  - 单测 `tests/graph_agent/middleware/test_protocol_validation.py` 含 5+ 测试
- **验收**:
  - 单测覆盖率 ≥ 95%
  - 旧 `cognitive/middlewares.py:ValidationMiddleware` 类已被吸收 (相关测试改 import 新模块)

### T8 — 实现 `CognitiveFlowMiddleware` (收拢 finish_task + Clarification)

- **Owner**: a1 codex
- **依赖**: T7 (协议层先稳, 才能在其后做 cognitive 逻辑)
- **估时**: 3h
- **产物**:
  - `src/core/graph_agent/middleware/cognitive_flow.py` 新文件 (design §5.3)
  - 整合 finish_task interception (调 IOManager.resolve_hoist 写 BusinessData)
  - 整合 ClarificationMiddleware + UnattendedClarificationMiddleware (统一 attended / unattended 模式)
  - 单测覆盖 finish_task / clarification (attended) / clarification (unattended) 三场景
  - 旧 `cognitive/clarification_middleware.py` + `cognitive/middlewares.py:UnattendedClarification` 物理删除或迁移
- **验收**:
  - 4 SKILL e2e 跑 attended + unattended 模式不破裂
  - 单测覆盖率 ≥ 95%
  - 旧 ClarificationMiddleware / UnattendedClarification 类不再存在 (grep 0 hits)

### T9 — 实现 `ExecutionControlMiddleware` (retry / loop / metrics)

- **Owner**: a3 claude
- **依赖**: T8 (CognitiveFlow 处理 tool call 拦截后, ExecutionControl 才接 retry 等运维事件)
- **估时**: 2h
- **产物**:
  - `src/core/graph_agent/middleware/execution_control.py` 新文件 (design §5.4)
  - 整合 retry (max_retries 计数 + retry_target 路由)
  - 复活精简版 LoopDetection (MVP-0 砍掉的 LoopDetectionMiddleware 在此处轻量级实现, 仅检测同一 phase 连续重复 N 次)
  - metrics 收集 (token / wall time / 每 phase 计数)
  - 单测 `tests/graph_agent/middleware/test_execution_control.py` 含 retry / loop / metrics 三场景 5+ 测试
- **验收**:
  - 单测覆盖率 ≥ 95%
  - retry 行为不变 (跟 MVP-2 末尾的 retry_router 协同)

### T10 — 清理 `runner.py` 内 `os.environ` / `sys.path` 副作用

- **Owner**: a3 claude
- **依赖**: T1 (Bootstrap + Settings 已可用)
- **估时**: 1h
- **可与 T6 / T7 / T9 并行**
- **产物**:
  - `core/runner.py` 把所有 `os.environ.set` / `os.environ[...] = ...` 站点改为通过 Settings 对象访问
  - `runner.py` `__main__` 段内 `sys.path.append` 全部删除 (移到 ModuleSandbox 内部)
  - 启动序列改为 `Bootstrap().apply_patches() → Bootstrap().load_settings() → SchemaEngine() → SkillLoader().compile_skill() → Harness().run()`
- **验收**:
  - `grep -E 'os\.environ\.set|os\.environ\[.*\] *=' src/core/graph_agent/core/runner.py` 0 hits
  - `grep 'sys\.path\.append' src/core/graph_agent/core/runner.py` 0 hits
  - 4 SKILL e2e 跑 1 chapter 不破裂

### T11 — 更新所有单元测试的 Mock Loader

- **Owner**: a3 claude
- **依赖**: T6 (新 SkillLoader pipeline 可用)
- **估时**: 4h
- **产物**:
  - `tests/graph_agent/` 下所有 mock SkillLoader 的测试改为 mock 三阶段函数 (parse / validate / build) 中的对应一个
  - middleware 改造后, 旧 mock middleware 的测试改为 mock 4 核心 middleware
  - `conftest.py` 加 middleware 拓扑序回归测试 (research D3 + design §5.6)
- **验收**:
  - pytest 全过 (--ignore test_strict_v2)
  - test_strict_v2 14 pre-existing failures 仍 isolated
  - middleware 拓扑序测试 (`test_middleware_topological_order`) 在 conftest.py 存在并通过

### T12 — 集成压力测试 (Loop Detection + 启动延迟)

- **Owner**: a3 claude
- **依赖**: T9 + T11
- **估时**: 2h
- **产物**:
  - `tests/graph_agent/integration/test_mvp3_loop_detection.py` 跑 4 SKILL 各 10 次, 检测 loop 命中率
  - `scripts/measure_startup_latency.py` 重跑, 中位数对比 T0-prep baseline
  - `docs/v1-reset/mvp-3-completion-report.md` 汇总指标 (loader SLOC / middleware count / startup latency / 4 SKILL persona equality / pytest pass count)
- **验收**:
  - Loop detection 命中率不变 (跟 baseline 比)
  - 启动延迟下降 ≥ 20% (中位数 ≤ baseline × 0.8)
  - 完成报告所有指标达标

## a1 review 节奏

- **每子任务 review** (针对 a3 的 T0-prep / T3 / T6 / T7 / T9 / T10 / T11 / T12): a3 完成后 a1 立刻 review
- **MVP-3 整体 review**: T12 done 后 a1 把所有 MVP-3 commits 整体过一遍 + cumulative spotcheck (重点验证 design §7 baseline diff 全部满足)

## 主控调度

派发顺序 (伪时间线):

```
t=0     spec 4 docs 落盘 commit; 派 a3 T0-prep + 同时派 a2 design review (30-60 min)
t=1.5h  a3 T0-prep done; a2 design review done; 主控整合 review 反馈
t=1.5h  派 a1 T1 + a1 T2 (并行, T2 占 a1 主线; T1 可让 a1 单独单核跑或推迟)
        实际策略: a1 顺序 T2 → T1, a3 等 T0-prep done 后接 T3
t=3.5h  a1 T2 done → 派 a3 T3
t=5.5h  a3 T3 done + a1 T1 done → 主控 commit T1+T2+T3 → 派 a1 T4
t=7.5h  a1 T4 done → 主控 commit T4 → 派 a1 T5 + a3 T7 (并行)
t=8.5h  a3 T7 done → a1 review (10min) → 主控 commit T7
t=9.5h  a1 T5 done → 主控 commit T5 → 派 a1 T8 + a3 T6 + a3 T10 (并行 3 路)
t=10.5h a3 T10 done + a3 T6 推进中 → 主控 commit T10
t=11.5h a3 T6 done → a1 review (15min) → 主控 commit T6
t=12.5h a1 T8 done → 主控 commit T8 → 派 a3 T9
t=14.5h a3 T9 done → a1 review (15min) → 主控 commit T9 → 派 a3 T11
t=18.5h a3 T11 done → a1 review (30min) → 主控 commit T11 → 派 a3 T12
t=20.5h a3 T12 done → 主控 commit + a1 整体 review
t=22h   a1 整体 review done → 主控 squash + push + PR + CI green + merge
```

总估 = 22-26h wall-clock (含 a2 design review / a1 cumulative review / CI / PR 周转, ≈ 3 工作日)。

## Pre-flight checklist

派 T0-prep 前主控自检:
- [ ] MVP-1 + MVP-2 已 merge 到 main
- [ ] BusinessData / FrameworkState / SchemaEngine / IOManager / build_business_data_for_skill 工厂在 main 可用
- [ ] spec 4 docs 落盘 (.kiro/specs/v1-reset-mvp-3-loader-startup-middleware/{requirements,research,design,tasks}.md)
- [ ] Gemini design 已审 (job_d22adb45e517 reply 整合到 design.md)
- [ ] research D2 (A9 误读) + D3 (4 middleware) 已派 a2 二轮确认
- [ ] orchestrator scope 起好 (推荐 MVP-3 起 dedicated scope, 因为 T11 要跑全量 pytest, 子进程多)
- [ ] a1 codex 当前状态 = idle (已 /clear)
- [ ] a3 claude 当前状态 = idle

## 跟 MVP-2 / MVP-4 的衔接

- **MVP-2 已就位 (前置依赖)**: SchemaEngine / IOManager / build_business_data_for_skill 工厂 / SchemaObject 中间表示
- **MVP-4 接口约定 (后置)**: PhaseNode.execute(state) 接口稳定 (MVP-3 同步, MVP-4 改 async); 4 middleware 顺序契约稳定 (MVP-4 拆 phase_executor 时不能改 middleware 顺序)
- **MVP-5 接口约定**: harness.run 拆解时, Bootstrap + Settings + SchemaEngine + SkillLoader + Harness 启动序列保持不变 (只把 harness.run 内部拆为 .compile/.prepare_state/.invoke_graph/.persist_outputs)
