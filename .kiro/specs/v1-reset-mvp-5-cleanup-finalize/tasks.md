# MVP-5 Tasks — Cleanup & Finalize (1.0.0 ship)

> 基于 design.md (a3 commit c295f4c, 701 行 / 8 D points) + research.md (a2 5337a13, 100 行) 拆 28 子任务. 总估 23-31h wall-clock, 关键路径 22-26h. 预估 ≈ 3 工作日 (跟 a2 research 估时一致).

## 派发策略

- **a1 codex 主线**: T4 / T5 (ruff 高危) / T7-T8 / T10-T11 / T13 (mypy 适配器层 + 入口) / T16 (providers cov) / T23-T25 (RELEASE_NOTES audit + CI workflow)
- **a3 claude 副线**: T0-prep / T1-T3 (ruff 安全 + I001 + UP037) / T6 / T9 / T12 (mypy Layer 1+2 部分+4) / T14-T15 / T17-T19 (cov 集成测试) / T20 (io/manager 砍) / T21 (test_strict_v2 修) / T22 (RELEASE_NOTES 草拟) / T26 (invariants verify)
- **a2 gemini reviewer**: T23 (1.0.0 RELEASE_NOTES honesty audit) + design 复核如有需要
- **a3 编码必须由 a1 codex review** (按 ccb-collaboration 角色铁律 + Phase 1 Learning #3)
- **主控**: T27 (final ship summary + verify 8 工程门禁全 PASS)

每个 brief 必含**铁律 block**:
```
🚨 严禁 git mutate HEAD: git checkout/switch/reset/cherry-pick/merge/rebase/pull/stash. 只允许 read-only.
🚨 不要 commit / push / 创 PR / 派 ccb 给其他 agent.
```

## 关键路径

```
T0-prep (1h, a3) ────────────────────────────────────────────┐
                                                              ↓
[D1 ruff 5 阶段串行]                                           │
T1 (0.5h, a3) → T2 (1h, a3) → T3 (1.5h, a3) → T4 (2h, a1) → T5 (1h, a1)  ← 6h 串行
                                                              │
[D2 mypy 8 阶段, layer 反向遍历]                               │
T6 (2h, a3) → T7 (1.5h, a1) → T8 (2h, a1) → T9 (1.5h, a3) → T10 (1.5h, a1) → T11 (3h, a1) → T12 (1h, a3) → T13 (1h, a1)  ← 13.5h 串行 (最长链)
                                                              │
[D3 coverage 6 阶段, 部分并行]                                 │
T14 (2h, a3) ─ T15 (1.5h, a3) ─ T16 (2.5h, a1) ─ T17 (1.5h, a3) ─ T18 (2h, a3) → T19 (1h, a3)  ← 10.5h 顺序累加, 实际并行 ≈ 7h
                                                              │
[D4/D5/D8 短任务并行]                                          │
T20 (1h, a3) ─ T21 (1.5h, a3) ─ T26 (0.5h, a3)  ← 3h, 三路并行 ≈ 1.5h
                                                              │
[D6 RELEASE_NOTES 3 阶段串行]                                  │
T22 (1.5h, a3) → T23 (0.5h, a2) → T24 (0.5h, a3+a1)  ← 2.5h
                                                              ↓
[D7 + final]                                          T25 (1h, a1) → T27 (0.5h, 主控)
```

最长链 = T0-prep + (D1 6h) + (D2 13.5h) + (D6 2.5h) + T25 + T27 = 1 + 6 + 13.5 + 2.5 + 1 + 0.5 = **24.5h**.
含 a1 review + CI / PR 周转 ≈ 26-30h wall-clock (≈ 3 工作日, 跟 a2 research 21-30h 估时对齐).

D2 (mypy) 单链 13.5h 是关键路径瓶颈, 风险点 §11.1 警示可能膨胀至 20h+ legacy 深水区.

## 子任务清单 (28 个)

### T0-prep — Baseline 数据测量 + MVP-4 完成态确认

- **Owner**: a3 claude
- **依赖**: 无 (但必须 MVP-4 已 merge 到 main)
- **估时**: 1h
- **必读**:
  - `.kiro/specs/v1-reset-mvp-5-cleanup-finalize/design.md` §0.3 baseline 表
  - MVP-4 final commit log (确认 phase_executor.py / cognitive/middlewares.py / cognitive/clarification_middleware.py 已删, ctx 残留 = 0)
- **产物**: `docs/v1-reset/mvp-5-baseline-snapshot.md` 含:
  - `ruff check src/core/graph_agent/` 实测 errors 数 + 按 rule code 分布表 (从 MVP-3 完成态 66 errors 的 baseline 推算 MVP-4 后预计 ≤ 56)
  - `mypy --strict src/core/graph_agent/ --explicit-package-bases` 实测 errors 总数 + 按文件分布 (Layer 1/2/3/4 各层 errors)
  - `pytest --cov=src/core/graph_agent --cov-report=term` 实测 TOTAL coverage % + 各文件 coverage 排序 (找低覆盖区)
  - `grep -rn 'context\["_\|ctx\["_' src/ tests/ --include="*.py" | wc -l` 应 ≤ 0 (验 MVP-4 T7a 完成)
  - `ls src/core/graph_agent/io/manager.py` 应仍存在 (D4 待砍)
  - `pytest tests/graph_agent/core/validators/test_strict_v2.py -v` 跑出 14 fail 详细原因 (D5 修测试参考)
- **验收**:
  - `ls docs/v1-reset/mvp-5-baseline-snapshot.md` 存在
  - 文档含数字 (不允许占位符)
  - 不动任何 src/ tests/ 文件

### T1 — D1 阶段 1: ruff 安全自动批量

- **Owner**: a3 claude
- **依赖**: T0-prep
- **估时**: 0.5h
- **必读**: design.md §1.3 阶段 1
- **必做**:
  1. 跑 `ruff check src/core/graph_agent/ --select=UP017,UP007,SIM103,SIM102,SIM118 --fix`
  2. 跑 `pytest tests/graph_agent/ --ignore=tests/graph_agent/core/validators/test_strict_v2.py -q` 确认不退步
  3. 跑 `git diff` 人工 spot-check 改动语义 (UP017 datetime.timezone.utc → datetime.UTC 是否影响序列化)
  4. 4 SKILL compile 跑一遍确认不破裂
- **验收**: 14 errors 减少 + pytest 不退步 + 4 SKILL compile pass

### T2 — D1 阶段 2: I001 import 排序

- **Owner**: a3 claude
- **依赖**: T1
- **估时**: 1h
- **必做**:
  1. 跑 `ruff check src/core/graph_agent/ --select=I001 --fix`
  2. **手工 review** 每个改动的 conditional import / TYPE_CHECKING 块顺序
  3. 若发现 lazy import (例 phase_executor.py:231 内 `from .io_manager import IOManager`) 被打乱, 保留 lazy 形态 + `# noqa: I001  # lazy import for ...` 标 reason
  4. 跑 `python -c "import graph_agent"` + `python -c "from graph_agent.core.harness import GraphAgentHarness"` 启动期烟雾测试 (循环引用早暴露)
- **验收**: I001 0 hits + pytest 不退步 + 4 SKILL compile pass

### T3 — D1 阶段 3: UP037 forward reference + TYPE_CHECKING block

- **Owner**: a3 claude
- **依赖**: T2
- **估时**: 1.5h
- **必做**: 复用 MVP-3 personas.py 修法 (commit 3973824) 模板:
  1. 找出 11 处 UP037 errors
  2. 对每处, 加 `from typing import TYPE_CHECKING` + `if TYPE_CHECKING:` block 声明类型符号 (避免 F821)
  3. 删字符串引号
  4. 验证 ruff + mypy 同时不报新错
- **验收**: UP037 + F821 同时 0 hits + pytest 不退步

### T4 — D1 阶段 4: F401 unused imports (高风险手工)

- **Owner**: a1 codex
- **依赖**: T3
- **估时**: 2h
- **必做**: per-import 流程:
  1. grep 每个 unused import 的 caller (`grep -rn "from <module> import <symbol>"` 全库)
  2. caller = 0 → 安全删
  3. caller > 0 但是 lazy load (例 plugin registry / api hide) → 保留 + `# noqa: F401  # public re-export, see ...`
  4. caller > 0 但应转 `_X` 私有 → 改 `from X import Y as _Y` 隐藏
- **验收**: F401 0 hits + 4 SKILL e2e smoke (启动期 ImportError 必须能在此层暴露) 不破裂

### T5 — D1 阶段 5: 高危 SIM / B904 / E402 人工审

- **Owner**: a1 codex
- **依赖**: T4
- **估时**: 1h
- **必做**:
  1. B904 (3): 加 `from err` 或 `from None` (按业务语义保留原因链与否)
  2. SIM108 (2): 三元式仅在 ≤ 30 字符时改, 否则保留 + `# noqa: SIM108`
  3. SIM105 (1): 确认 `try-pass` 真的只 catch 特定异常, 改 `contextlib.suppress(...)`, 否则保留
  4. E402 (1): 检查 lazy import 必要性, 保留则加 `# noqa: E402  # lazy load to avoid circular import`
- **验收**: `ruff check src/core/graph_agent/` **0 errors** (D1 总 5 阶段完成)

### T6 — D2 Layer 1: manifest / loader / cognitive 剩余 / tools/builtin

- **Owner**: a3 claude
- **依赖**: T5 (ruff 全过避免类型错误跟 lint 错误混淆)
- **估时**: 2h
- **必做**: 按 design.md §2.3 Layer 1 文件清单, 单文件跑 mypy strict → 修注解 → 通过
  - `core/manifest.py` / `core/loader/*.py` / `cognitive/finish.py` (MVP-4 后 stub) / `cognitive/ambiguity.py` / `cognitive/memory.py` / `tools/builtin/*.py`
- **验收**: 每文件 `mypy --strict <file>` Success + 跟 Layer 0 不矛盾

### T7 — D2 Layer 2 (适配器): models/resolver

- **Owner**: a1 codex
- **依赖**: T6
- **估时**: 1.5h
- **必做**: LangChain 外部 stub 缺失处理: 优先安装 langchain-stubs (若有) → 不行用 cast() + Protocol → 最后手段 `# type: ignore[no-untyped-def]  # langchain.X 无 stub`
- **验收**: `mypy --strict src/core/graph_agent/models/resolver.py` Success + 4 SKILL compile

### T8 — D2 Layer 2 (适配器): providers/*

- **Owner**: a1 codex
- **依赖**: T7
- **估时**: 2h
- **必做**: 各 provider (openai / anthropic / etc) 的 LLM 调用签名加注解, 外部 stub 缺失参考 T7 的兜底
- **验收**: `mypy --strict src/core/graph_agent/providers/` Success + 4 SKILL e2e smoke

### T9 — D2 Layer 2 (适配器): callbacks/*

- **Owner**: a3 claude
- **依赖**: T6 (Layer 1 完成即可, 跟 T7/T8 可并行)
- **估时**: 1.5h
- **必做**: Callback 协议 + 各类实现 (RecordingCallback / TracingCallback / MetricsCallback) 加完整类型注解
- **验收**: `mypy --strict src/core/graph_agent/callbacks/` Success

### T10 — D2 Layer 3: graph_builder + runner

- **Owner**: a1 codex
- **依赖**: T7 + T8 + T9 (Layer 2 全部完成)
- **估时**: 1.5h
- **必做**: graph_builder.py + runner.py 加完整类型注解
- **验收**: `mypy --strict src/core/graph_agent/core/graph_builder.py src/core/graph_agent/core/runner.py` Success

### T11 — D2 Layer 3: harness.py (11+ errors, 重头戏)

- **Owner**: a1 codex
- **依赖**: T10
- **估时**: 3h (legacy 深水区, 实际可能膨胀)
- **必读**: design.md §2.5 hazards (链式 error 爆炸风险)
- **必做**: harness.py 11 errors 修复:
  - line 709 / 753 / 1134: `no-any-return` + `unused-ignore` 联动 (返回类型不是 Any 时 `# type: ignore[no-any-return]` 失效)
  - line 1027: `assignment` (`str | Any | None` → `str` 不兼容)
  - line 1104: `arg-type` (list[Callback] → tuple[Callback, ...])
  - 每修一个, mypy 重跑确认没引发新错; 若新错连环爆 > 5 个, 暂停, a3/a1 一起 review 是否需要重构 harness.py 部分签名
- **验收**: `mypy --strict src/core/graph_agent/core/harness.py` Success (11 → 0)

### T12 — D2 Layer 4: settings + bootstrap

- **Owner**: a3 claude
- **依赖**: T11
- **估时**: 1h
- **必做**: config/settings.py + core/bootstrap.py 加注解
- **验收**: `mypy --strict <file>` Success

### T13 — D2 全库 final pass + mypy.ini 配置

- **Owner**: a1 codex
- **依赖**: T12
- **估时**: 1h
- **必做**:
  1. 跑 `mypy --strict src/core/graph_agent/ --explicit-package-bases` 全库一次
  2. 修 `mypy.ini` (或 `pyproject.toml [tool.mypy]`) 加 `exclude = ["skills/"]` 避开 md-patch 包名问题
  3. 加 `[mypy.X]` per-module override (如 LangChain stub 缺失而本地用 ignore 兜底), 必须**每个 override** 带 reason 注释
  4. grep 全库 `# type: ignore[^ ]*$` 找裸 ignore, 全部加 reason
- **验收**: `mypy --strict src/core/graph_agent/ --explicit-package-bases` Success (zero issues), 0 裸 ignore

### T14 — D3 callback_bridge.py 17 → 95% (集成测试)

- **Owner**: a3 claude
- **依赖**: T0-prep (低优先级阻塞), 可 D2 完成前并行
- **估时**: 2h
- **必做**: 按 design.md §3.4 策略 1 — 写 `tests/graph_agent/integration/test_callback_bridge_integration.py`, 用真实 RecordingCallback + 模拟 LangChain message stream, 跑 1 SKILL e2e 验证 events 完整性
- **验收**: callback_bridge.py coverage ≥ 95% + pytest 不退步

### T15 — D3 skill_tool_factory.py 0 → 95%

- **Owner**: a3 claude
- **依赖**: T0-prep
- **估时**: 1.5h
- **必做**: 写 `tests/graph_agent/core/test_skill_tool_factory.py`, 用真实 SkillManifest + SchemaEngine, 验证 build_business_data_for_skill 等公共 API
- **验收**: coverage ≥ 95%

### T16 — D3 providers/* 30 → 90% (record-replay)

- **Owner**: a1 codex
- **依赖**: T0-prep + T8 (mypy 通过后)
- **估时**: 2.5h
- **必做**: 写 record-replay fixture (例 `DummyOpenAIProvider`), 测 streaming chunk 边界 + error code + retry 路径
- **验收**: providers coverage ≥ 90% (允许 < 95%, 因为外部 IO 不全可测), pytest 不退步

### T17 — D3 runner + bootstrap 集成测试

- **Owner**: a3 claude
- **依赖**: T0-prep
- **估时**: 1.5h
- **必做**: 写 `tests/graph_agent/integration/test_runner_e2e.py`, 跑 argparse + Bootstrap.apply_patches() + load_settings(), 验证 main() 启动序列
- **验收**: runner.py + bootstrap.py coverage ≥ 90%

### T18 — D3 cognitive 剩余 + tools 单测

- **Owner**: a3 claude
- **依赖**: T0-prep
- **估时**: 2h
- **必做**: 按 baseline cov 报告补低覆盖文件 (cognitive 剩余 / tools/builtin/* / md_to_json 等)
- **验收**: 各文件 coverage ≥ 95% (除 providers 允许 90%)

### T19 — D3 全库 final cov pass

- **Owner**: a3 claude
- **依赖**: T14 + T15 + T16 + T17 + T18
- **估时**: 1h
- **必做**: 跑 `pytest --cov=src/core/graph_agent --cov-report=term-missing --cov-fail-under=95`, 找剩余 gap (单文件 < 70% 死角必须补)
- **验收**: TOTAL coverage ≥ 95% + 单文件最低 ≥ 70% (无死角)

### T20 — D4 io/manager.py 砍除

- **Owner**: a3 claude
- **依赖**: T0-prep (确认 caller 只剩 re-export)
- **估时**: 1h
- **必做**:
  1. 改 `src/core/graph_agent/__init__.py:26` `from .io.manager import IOManager` → `from .core.io_manager import IOManager`
  2. 改 `src/core/graph_agent/io/__init__.py:4` 同上
  3. 删 `src/core/graph_agent/io/manager.py` 文件
  4. (可选) 若 `io/__init__.py` 内只剩 re-export, 整个 `io/` 子包也可保留 (向后兼容 `from graph_agent.io import IOManager`)
- **验收**:
  - `ls src/core/graph_agent/io/manager.py` ENOENT
  - `python -c "from graph_agent import IOManager"` 工作
  - `python -c "from graph_agent.io import IOManager"` 工作 (re-export 仍指向 core/io_manager)
  - pytest 不退步 + 4 SKILL e2e smoke 不破裂

### T21 — D5 test_strict_v2 14 fail 重写

- **Owner**: a3 claude
- **依赖**: T0-prep (T0-prep 已跑详细 fail 原因)
- **估时**: 1.5h
- **必做**:
  1. 按 T0-prep baseline 文档的 14 fail 原因分类
  2. 逐个 fixture 修复 + 测试断言对齐新 schema (Pydantic v2 / extra="forbid" / 字段名变化等)
  3. 跑 `pytest tests/graph_agent/core/validators/test_strict_v2.py -v` 全过
  4. 删 CI 配置 (`.github/workflows/ci.yml` 或 pyproject.toml) 中的 `--ignore=tests/graph_agent/core/validators/test_strict_v2.py` 行
- **验收**:
  - `pytest tests/graph_agent/core/validators/test_strict_v2.py` 全过
  - `pytest tests/graph_agent/` 不带 --ignore 也全过
  - CI workflow `--ignore` 列表无 test_strict_v2

### T22 — D6 阶段 1: a3 草拟 1.0.0 RELEASE_NOTES

- **Owner**: a3 claude
- **依赖**: T13 (mypy strict 完成数据可用) + T19 (cov 95% 数据可用) + T5 (ruff 0 数据可用) + T20 + T21
- **估时**: 1.5h
- **必读**: design.md §13 推荐结构 + Phase 1 RELEASE_NOTES (反吹牛纪律)
- **必做**: 按 design.md §13 8 段结构起草:
  - TL;DR / 工程门禁达标 (8 条数据 + 实测命令证据) / 用户感知改变 / Breaking Changes / 5 MVP 阶段完整回顾 / Migration Guide (Phase 1 + Phase 2 整合) / Known Limitations / Future Work / AI 协作模式致谢 / 附录 commit 范围
  - **每条数字必须当场跑命令**, 不允许复制 Phase 1 数据
  - 200-250 行, 比 Phase 1 (115 行) 长 1 倍但内容扎实
- **验收**: docs/v1-reset/RELEASE_NOTES.md 落盘 (整体重写, 不是补丁) + 所有数据有命令证据

### T23 — D6 阶段 2: a2 honesty audit

- **Owner**: a2 gemini reviewer
- **依赖**: T22
- **估时**: 0.5h (a2 audit 时间, 主控派单等待时间另算)
- **必做**: a2 跑 honesty audit, 标三类问题:
  1. 宣发越界 (类似 Phase 1 "16-Dim ≥ 8.5" 这种主观夸大)
  2. 数据不实 (文档说 "0 errors" 但 CI 没拦截)
  3. 表述模糊 (例 "工程门禁达标" 没说具体哪些)
- **验收**: a2 给评分 + must-fix list (期望 ≥ 9.5/10)

### T24 — D6 阶段 3: a3 修订 + a1 final review

- **Owner**: a3 claude (修订) + a1 codex (final review)
- **依赖**: T23
- **估时**: 0.5h
- **必做**: a3 按 a2 audit must-fix 修订 RELEASE_NOTES → a1 verify 工程数据 (跟 CI 实跑结果咬合) → 主控 final spotcheck
- **验收**: a2 audit 第二轮 PASS + a1 final review approve + 主控 spotcheck pass

### T25 — D7 CI workflow .github/workflows/ci.yml 整合 8 工程门禁

- **Owner**: a1 codex
- **依赖**: T13 + T19 + T5 + T20 + T21 (前置门禁数据全部可用)
- **估时**: 1h
- **必做**: 按 design.md §7.1 yaml 示意整合到 `.github/workflows/ci.yml`:
  - ruff check (exit 0)
  - mypy --strict (exit 0)
  - pytest (含 test_strict_v2)
  - coverage (--cov-fail-under=95)
  - 4 SKILL compile (新写 script `scripts/ci_compile_check.py`)
  - invariants grep (`context["_X"]` / `ctx["_X"]` 0 hits)
  - no_legacy_io (ls io/manager.py 失败)
  - release_notes_audit (manual / a2 reviewer 标记)
- **验收**: CI workflow 推到 throwaway branch 跑过, 8 jobs 全 PASS

### T26 — D8 invariants 验证 (context["_X"] 残留)

- **Owner**: a3 claude
- **依赖**: T0-prep (MVP-4 完成态确认)
- **估时**: 0.5h
- **必做**:
  1. 跑 `grep -rn 'context\["_\|ctx\["_' src/core/graph_agent/ tests/graph_agent/ --include="*.py" | grep -v "core/state.py:" | wc -l`
  2. 期望结果 0
  3. 若 N > 0, 立即反馈到 MVP-4 owner 补迁 (按 design.md §8.3 hazards), 不在 MVP-5 内做
  4. 若 state.py:legacy_context_from_state 等 shim 函数 phase_executor.py 已删后无 caller, 顺手物理删除 (跟 D8 一起做)
- **验收**: grep 0 hits + state.py 桥函数无 caller (verify by `grep -rn "legacy_context_from_state"`) 已删

### T27 — Final ship summary + 主控 verify 8 工程门禁全 PASS

- **Owner**: 主控 Claude
- **依赖**: T25 + T26 + T24 全部完成
- **估时**: 0.5h
- **必做**:
  1. CI 跑 8 个工程门禁 jobs, 全 PASS
  2. 主控写 final summary (commit message + PR description), 列 8 个 PASS evidence (CI run URL)
  3. squash + push + 创 PR + a2 final spotcheck → merge to main
  4. 1.0.0 release tag (`git tag v1.0.0`, push tag)
- **验收**: 1.0.0 ship final, main HEAD 指向 1.0.0 final commit + tag v1.0.0 推到 origin

## a1 review 节奏

- **每 a3 子任务 review** (T0-prep / T1-T3 / T6 / T9 / T12 / T14-T15 / T17-T22 / T24 / T26 共 16 个 a3 owner 子任务): a3 完成后 a1 立即 review (10-30 min/单), Phase 1 节奏沿用
- **MVP-5 cumulative review**: T25 done 后 a1 整体 review 全部 commits, spotcheck 8 工程门禁数据真实性 + RELEASE_NOTES 跟 CI 咬合
- **a2 design audit**: 不需要 (design.md 已落盘 + a2 research 已为基础)
- **a2 honesty audit**: T23 一次

## 主控调度时间线 (伪)

```
t=0      派 a3 T0-prep
t=1h     T0-prep done → 派 a3 T1 (D1 启动)
t=1.5h   T1 done → 派 a3 T2
t=2.5h   T2 done → 派 a3 T3
t=4h     T3 done → 派 a1 T4
t=6h     T4 done → 派 a1 T5
t=7h     T5 done (D1 完成) → 派 a3 T6 (D2 启动)
t=9h     T6 done → 派 a1 T7 + a3 T9 (并行) + a3 T14-T15 启动 (D3 与 D2 并行)
t=10.5h  T7 done + T9 done → 派 a1 T8
t=11h    T14 done → 派 a3 T17
t=12h    T15 done → 派 a3 T18
t=12.5h  T8 done → 派 a1 T10 + a3 T20 + a3 T21 + a3 T26 (4 路并行)
t=13.5h  T10 done + T20 done + T26 done → 派 a1 T11 + a1 T16
t=14h    T17 done + T18 done + T21 done → 派 a3 T19
t=16.5h  T11 done + T16 done → 派 a3 T12
t=15h    T19 done → 等待 D2 完成
t=17.5h  T12 done → 派 a1 T13
t=18.5h  T13 done (D2 完成) → 派 a3 T22 (D6 启动, 此时 ruff + mypy + cov 数据全可用)
t=20h    T22 done → 派 a2 T23 (honesty audit)
t=20.5h  T23 done → 派 a3+a1 T24
t=21h    T24 done → 派 a1 T25 (CI workflow 整合)
t=22h    T25 done → 派 主控 T27 (final ship)
t=22.5h  T27 done → 1.0.0 ship 完成 → squash + push + PR + tag v1.0.0
```

总估 22-26h wall-clock (含 a2 audit + a1 cumulative review + CI / PR 周转, ≈ 3 工作日, 跟 a2 research 21-30h 估时一致).

## Pre-flight checklist

派 T0-prep 前主控自检:
- [ ] MVP-4 已 merge 到 main (1.0.0 ship 必须基于 MVP-4 完成态)
- [ ] phase_executor.py 已物理删除 (MVP-4 T12)
- [ ] cognitive/middlewares.py + cognitive/clarification_middleware.py 已物理删除 (MVP-4 T10a)
- [ ] state.py:legacy_context_from_state 桥函数已删 (MVP-4 T7a 或 T12)
- [ ] context["_X"] / ctx["_X"] 残留 = 0 (MVP-4 T7a)
- [ ] BusinessData / FrameworkState / SchemaEngine / IOManager / 4 middleware / Bootstrap / Settings / nodes/* / state_reducers 全部稳定可用
- [ ] orchestrator scope 起好 (MVP-5 涉及多路并行 + 大量 commit, 起 dedicated scope --tasks-max 800)
- [ ] a1 codex / a3 claude 当前状态 = idle (已 /clear)

## Migration 警告 (Phase 1 → MVP-4 → MVP-5 → 1.0.0)

v1-reset 演进路径含 3 个不兼容升级点:

1. **Phase 1 ship (5decd0a..85bc4b8)** — WorkflowState 顶层从 `context: dict` 拆为 `data: BusinessData / flow: FrameworkState / messages: list[BaseMessage]`. 升级时**必须清空旧 LangGraph checkpoint 存储** (反序列化失败).
2. **MVP-4 ship** — phase_executor.py 物理删除 + LangGraph 图节点拓扑改变 (LLMPhaseNode / LogicPhaseNode / ValidationPhaseNode). 升级时**必须清空 SQLite checkpoint + _history sidecar** (Node 名 + 执行步数强绑定 checkpoint, 旧 checkpoint 在新图必硬 crash). 详见 MVP-4 tasks.md "Migration" 段.
3. **MVP-5 / 1.0.0 ship** — io/manager.py 物理删除 (re-export 改指向 core/io_manager). 第三方深度 import (例 `from graph_agent.io.manager import IOManager`) 会 break, 需改为 `from graph_agent import IOManager` 或 `from graph_agent.core.io_manager import IOManager`.

升级到 1.0.0 必须**累加**做以上 3 项 Migration. 1.0.0 RELEASE_NOTES Migration Guide 段必须明列.

## 跟 MVP-4 / Phase 1 / 1.0.0 的衔接

- **MVP-4 已就位 (前置硬阻塞)**: phase_executor 物理删除 + cognitive/* 物理删除 + ctx 残留 0 + state_manager → state_reducers 已迁
- **Phase 1 RELEASE_NOTES (5decd0a..85bc4b8) 不删**: 作为 v1-reset 中间发布历史保留, 1.0.0 RELEASE_NOTES 在 D6 整体重写替代为正式 release 版本
- **1.0.0 RELEASE_NOTES (D6 落盘)**: 整合 Phase 1 + Phase 2 (MVP-4 + MVP-5) 全部 Migration + 致谢 + 工程指标
- **后续路线图 (1.0.0 RELEASE_NOTES Future Work 段引导)**:
  - v1.1: parallel_delegate v2 (LangGraph Send API)
  - v1.2: Multimodal 增强
  - v1.5+: 动态 Schema 进化
  - v2.0: 跨 Agent 协议栈 + Studio 适配
