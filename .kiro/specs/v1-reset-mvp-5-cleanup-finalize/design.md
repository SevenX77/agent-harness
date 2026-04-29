# MVP-5 Design — Cleanup & Finalize (1.0.0 ship)

> 整合 a2 research (`.kiro/specs/v1-reset-mvp-5-cleanup-finalize/research.md`) + Phase 1 RELEASE_NOTES "Pending MVP-5" 段 + Phase 1 RETROSPECTIVE §6 cheat sheet。
> 本 design.md 是 v1-reset 6-MVP roadmap 的最后一份 design.md, 落盘后 1.0.0 ship 之前不再有架构改动。

## §0 TL;DR

MVP-5 是 v1-reset 序列的最后冲刺，目标是**还清最后的技术债 + 锁死工程门禁 + 正式发布 1.0.0**。

### 0.1 工程门禁 (1.0.0 Ship 标准)

按 a2 research §3 列的 8 条不变量, 1.0.0 主干 merge 前 CI 必须 hard fail:

```
[1] ruff check src/core/graph_agent/                           → 0 errors
[2] mypy --strict src/core/graph_agent/                        → zero issues
[3] pytest tests/ (含 test_strict_v2.py)                        → 全过
[4] 全库 coverage                                                → ≥ 95%
[5] 4 SKILL compile + e2e smoke                                 → 不破裂
[6] context["_X"] / ctx["_X"] 全库残留                           → 0 hits (state.py shim 除外)
[7] src/core/graph_agent/io/manager.py 文件                      → 不存在 (ENOENT)
[8] a2 1.0.0 RELEASE_NOTES honesty audit                        → ≥ 9.5/10
```

### 0.2 实施时序

```
MVP-4 完成 (合 main) → MVP-5 启动 (本设计) → 1.0.0 ship
                       ↓
              D1-D8 子任务并行/串行实施
                       ↓
              CI 8 工程门禁全过
                       ↓
              a2 1.0.0 RELEASE_NOTES honesty audit PASS
                       ↓
              主控 squash + push + PR + merge → 1.0.0 final
```

### 0.3 当前 baseline (MVP-3 完成态实测, MVP-4 完成后会变)

| 指标 | MVP-3 完成态 | MVP-4 预计 | MVP-5 目标 (1.0.0 ship) |
|---|---|---|---|
| ruff errors | 66 | ≤ 66 (MVP-4 砍 phase_executor 后预计 -10) | **0** |
| mypy --strict (全库) | ~50+ errors (harness.py 单文件 11) | 不动 (MVP-4 范畴是新增模块, 不收紧旧) | **zero issues** |
| pytest | 856 passed + 2 skipped | 不退步 | 不退步 + 解禁 test_strict_v2 |
| coverage | 71% | 不动 (MVP-4 范畴是新增 nodes 95%) | **≥ 95%** |
| context["_X"] 残留 | 12+ 处 (cognitive / harness / tools) | 0 (MVP-4 T7a 已迁) | 0 (验证不变量) |
| io/manager.py 文件 | 存在 (有 re-export caller) | 存在 (MVP-4 不动) | **物理删除** |
| test_strict_v2.py 处置 | 14 stale failures (CI --ignore 续命) | 不动 | **删除 OR 重写** |

---

## §1 D1 — 全库 ruff 拍平 (66 errors → 0)

### 1.1 目标

`ruff check src/core/graph_agent/ --output-format=concise` 报 **0 errors**, 不允许 `# noqa` 临时压制 (除非 a2/a1 双方书面同意, 标 reason)。

### 1.2 当前 ruff error 分布 (MVP-3 完成态实测, n=66)

| Rule code | 数量 | 风险 | 备注 |
|---|---|---|---|
| **I001** (Import block un-sorted) | 17 | Low | `--fix` 安全, 但仍需人工 review (避免 conditional / TYPE_CHECKING import 顺序被打乱) |
| **F401** (unused imports) | 17 | **Medium-High** | `harness.py` 等入口文件可能依赖 lazy import / API 隐式暴露, `--fix` 必须人工核对每个 import |
| **UP037** (quoted forward references) | 11 | Medium | `from __future__ import annotations` 后字符串注解多余, 但删除前必须确保 TYPE_CHECKING 块已就位 (见 MVP-3 personas.py F821 教训, commit 3973824) |
| **UP017** (datetime.timezone.utc → datetime.UTC) | 9 | Low | Python 3.11+ 安全 |
| **B904** (raise without from) | 3 | Low | 显式 `from err` / `from None` 改写, 不破坏语义 |
| **SIM118** (`X in dict.keys()` → `X in dict`) | 2 | Low | 安全 |
| **SIM108** (if-else → ternary) | 2 | **High** | 三元表达式可读性陷阱, 必须人工 case-by-case 审 |
| **UP007** (Optional X → X \| None) | 1 | Low | Python 3.10+ 安全 |
| **SIM105** (try-pass → contextlib.suppress) | 1 | Medium | 改了行为语义 (suppress 只 catch 指定异常), 需确认捕获面 |
| **SIM103** (return condition) | 1 | Low | 安全 |
| **SIM102** (collapsible if) | 1 | Low | 安全 |
| **E402** (Module level import not at top) | 1 | **High** | 通常是 lazy import 故意为之, 移上去可能撞循环引用; 必须人工 review |

### 1.3 实施方案 (按 rule 类别拆 commit)

**阶段 1 — 安全自动批量 (一 commit)**:
- 处理 UP017 (9) + UP007 (1) + SIM103 (1) + SIM102 (1) + SIM118 (2) = **14 errors**
- 命令: `ruff check src/core/graph_agent/ --select=UP017,UP007,SIM103,SIM102,SIM118 --fix`
- 验收: pytest 不退步

**阶段 2 — I001 import 排序 (一 commit)**:
- 17 errors, 先 a3 跑 `ruff check --select=I001 --fix`, 再手工对照 conditional / TYPE_CHECKING 块 review
- 边界: 若发现某文件用 lazy import 规避循环引用 (例 phase_executor.py:231 内的 `from .io_manager import IOManager`), 必须保留 lazy 形态, 这种情况加 `# noqa: I001` 并标 reason
- 验收: pytest 不退步 + 4 SKILL e2e smoke 不破裂 (导入顺序错会在启动期 crash, 而非测试期)

**阶段 3 — UP037 forward reference (一 commit)**:
- 11 errors, 复用 MVP-3 personas.py 的修法模板:
  1. 加 `from typing import TYPE_CHECKING` + `if TYPE_CHECKING:` block 声明类型符号
  2. 删字符串引号
- 边界: 必须先确认目标符号在 TYPE_CHECKING 块外**不**被运行时使用 (否则引发 F821)
- 验收: ruff + mypy 同步通过, 不能"修了 UP037 触发 F821"

**阶段 4 — F401 unused imports (1-2 commits, 按 caller graph 分组)**:
- 17 errors, **最高风险**. `harness.py:50-79` 区域有大量 import 跟运行时 lazy load API 暴露相关
- 实施流程 (per import):
  1. grep 该 import 的 caller (`grep -rn "from <path>" src/`)
  2. caller = 0 → 安全删
  3. caller > 0 → 检查是否有 `__all__` 导出, 是则改 `from X import Y as _Y` (避免被外部访问) 或保留 + `# noqa: F401` 加 reason
  4. caller > 0 但是 lazy load (例 plugin registry) → 保留 + `# noqa: F401` 加 reason
- 验收: `grep -rn "from .X import" src/ tests/` 跨改造前后行为一致

**阶段 5 — 高危 SIM 改写 (B904 / SIM108 / SIM105 / E402, 一 commit)**:
- 共 8 errors, 必须 a2/a1 人工逐条审
- B904 (3): 改 `raise X from err` 或 `from None`, 选择按业务语义 (是否需要保留原因链)
- SIM108 (2): 三元表达式必须**只**在 ≤ 30 字符时改, 否则保留 if-else 加 `# noqa: SIM108` (可读性 > 简洁)
- SIM105 (1): 确认 `try-pass` 真的只捕特定异常, 是则改 `contextlib.suppress`, 否则保留 + `# noqa`
- E402 (1): 检查 lazy import 必要性, 是则保留 + `# noqa: E402` 标 reason

### 1.4 hazards

- **F401 删 lazy import 引发运行时 ImportError**: 删除前**必须**跑 4 SKILL e2e smoke (而非仅单测), 因为 lazy import 失败常在 phase 实际启动时才触发
- **I001 重排 conditional import 引发循环引用**: 修后必须跑 `python -c "import graph_agent"` + `python -c "from graph_agent.core.harness import ..."` 等启动期烟雾测试
- **UP037 + F821 联动错**: MVP-3 personas.py 教训, 必须先建 TYPE_CHECKING block 再删引号

### 1.5 验收

- `ruff check src/core/graph_agent/` → 0 errors
- pytest 不退步 (856 passed)
- 4 SKILL compile + e2e smoke 不破裂
- 所有 `# noqa` 必须有 reason 注释 (`# noqa: F401  # lazy plugin registry, see issue #X`)

---

## §2 D2 — 全库 mypy --strict (zero issues)

### 2.1 目标

`mypy --strict src/core/graph_agent/` 报 **zero issues** (不区分 error / warning), 全库强类型。

### 2.2 当前 mypy 状态 (MVP-3 完成态实测)

- MVP-3 新增 16 文件 (`schema_engine.py` / `state.py` / `middleware/*.py` / `loader pipeline 三模块` 等) 已通过 `mypy --strict`, zero issues
- **harness.py 单文件**实测 **11 errors** (见 baseline section). 错误类型:
  - `no-any-return` (returning Any from declared return type)
  - `unused-ignore` (`# type: ignore` 注释失效)
  - `assignment` (类型不兼容赋值)
  - `arg-type` (参数类型不匹配, 例 list[Callback] 期望 tuple[Callback, ...])
- 其他 legacy 模块 (`cognitive/` 在 MVP-4 后部分被砍, 剩余 / `models/` / `providers/` / `tools/` / `runner.py`) 未跑过 mypy strict, 估计累计 50+ errors (a2 research §6 警示这是 "深水炸弹")
- **执行陷阱**: `mypy --strict src/core/graph_agent/` 直接跑会撞 `md-patch contains __init__.py but is not a valid Python package name` (skills/md-patch 包名带 hyphen). 必须用 `--explicit-package-bases` 或者 mypy.ini 的 `exclude` 规则跳过 skills/

### 2.3 模块依赖图 (反向遍历起点, a3 grep 推导)

按 a2 research §2.2 "反向遍历 (叶子模块先, harness.py 最后)", 推导依赖图分组:

**Layer 0 — 纯叶子 (无内部依赖, 已 strict 或近 strict)**:
- `core/state.py` ✅ (MVP-1 已 strict)
- `core/exceptions.py` ✅
- `core/schema_engine.py` ✅ (MVP-2 已 strict)
- `core/io_manager.py` ✅ (MVP-2 已 strict)
- `core/state_reducers.py` ✅ (MVP-4 已 strict)
- `middleware/*.py` (4 个) ✅ (MVP-3 已 strict)
- `core/nodes/*.py` (4 个) ✅ (MVP-4 已 strict)

**Layer 1 — 单层依赖**:
- `core/manifest.py` (依赖 schema_engine + state)
- `core/loader/*.py` (依赖 manifest + io_manager + schema_engine)
- `cognitive/finish.py` (MVP-4 后只剩 stub)
- `cognitive/ambiguity.py` / `memory.py` (MVP-4 T7a 后已迁出 ctx)
- `tools/builtin/*.py` (依赖 cognitive 工具)

**Layer 2 — 适配器层**:
- `models/resolver.py` (依赖外部 LangChain stub, 高风险)
- `providers/*.py` (依赖外部 provider stub, 高风险)
- `callbacks/*.py` (Callback 协议 + 各类实现)

**Layer 3 — 入口 (依赖一切)**:
- `core/harness.py` (11 个已知 errors)
- `core/graph_builder.py`
- `core/runner.py`

**Layer 4 — Settings / Bootstrap (启动期)**:
- `config/settings.py`
- `core/bootstrap.py`

### 2.4 实施方案 (按 layer 反向推进)

每个 Layer 一个 commit, 阶梯式收紧:

**阶段 1 — Layer 1 (3-4 子任务)**:
- 每个文件独立跑 `mypy --strict <file>` → 修类型注解 → 通过
- 估时单文件 30-60 分钟 (按错误数量)

**阶段 2 — Layer 2 (适配器层, 3-5 子任务)**:
- LangChain / LangGraph 外部依赖触发的 mypy 错误处理:
  - 选项 A: 安装 langchain-stubs (若存在第三方 stub 包)
  - 选项 B: 局部 `# type: ignore[no-untyped-def]` 加 reason 注释
  - 选项 C: 用 `cast()` + `assert isinstance(...)` 把 Any 收紧
  - 选项 D (最后手段): 改设计, 加 Protocol class 替代外部签名
- 优先级: A > C > B > D
- 每个文件**必须**跑 4 SKILL e2e smoke 不破裂

**阶段 3 — Layer 3 (入口, 2-3 子任务)**:
- harness.py 已有 11 errors, 估计修完 4-6h (每个 error 可能引发 1-3 个连锁 error)
- graph_builder.py / runner.py 较小

**阶段 4 — Layer 4 + 全库 final pass (1 子任务)**:
- 最后跑 `mypy --strict src/core/graph_agent/ --explicit-package-bases` 全库 zero issues
- 修 mypy.ini / pyproject.toml 配置, 加 `exclude = ["skills/"]` 跳过 skills 目录

### 2.5 hazards

- **链式 error 爆炸**: a2 research §6 警示, 12h 估时可能膨胀至 20h+
- **Stub 缺失**: LangChain/LangGraph 主版本 stub 在 PyPI 可能缺失, 必须用 cast / Protocol 兜底
- **`# type: ignore` 滥用**: 写一次容易, 后续 mypy 升级时这些 ignore 会过期 (`unused-ignore` warning), 必须加 reason 注释 (`# type: ignore[no-untyped-def]  # langchain.X.Y has no stub`)

### 2.6 验收

- `mypy --strict src/core/graph_agent/ --explicit-package-bases` → Success: no issues found
- `# type: ignore` 全部带 reason 注释 (grep `# type: ignore[^ ]*[^#]*$` 检测裸 ignore)
- pytest 不退步
- 4 SKILL e2e smoke 不破裂

---

## §3 D3 — Coverage 提升至 95%

### 3.1 目标

`pytest --cov=src/core/graph_agent --cov-report=term-missing` TOTAL ≥ **95%**.

### 3.2 当前 coverage (MVP-3 完成态实测, 71%)

- TOTAL: 7498 行 / 2156 行 missing / **71%**
- gap: 24 个百分点, 约需补盖 **1800 行** (按 95% × 7498 = 7123 应覆盖 - 当前 5342 已覆盖)

### 3.3 低覆盖区清单 (a2 research §2.3 提示 + a3 推导)

| 模块 | 当前 coverage | 目标 | 难点 |
|---|---|---|---|
| `models/callback_bridge.py` | 17% | 95% | 强依赖 LangChain runtime callback, 难 mock; 需 Dummy Provider Fixture |
| `core/skill_tool_factory.py` | 0% | 95% | 工厂模式, 依赖 SkillManifest + SchemaEngine; 需集成测试 |
| `providers/*.py` | < 30% | 90% (允许 < 95%) | LLM 调用副作用, 不允许真 LLM 测试; 用 record-replay fixture |
| `runner.py` | < 50% | 90% | argparse + Bootstrap, 集成测试覆盖 |
| `cognitive/*.py` (剩余) | 60-70% | 95% | MVP-4 砍除大部分后, 剩余文件各自补单测 |

### 3.4 实施方案

按 a2 research §2.3 + 反 mock 反模式 (Phase 1 RETROSPECTIVE Learning #4 教训):

**策略 1 — 集成测试覆盖关键路径 (优先)**:
- `tests/graph_agent/integration/test_<module>_integration.py` 跑真实组件 (除 LLM 外)
- 例: callback_bridge 跟真实 RecordingCallback + 模拟 LangChain message stream 一起跑
- 单文件 1 集成测试可覆盖 70-90% lines

**策略 2 — Dummy Fixture 替代 Mock**:
- providers/ 写 `DummyOpenAIProvider` (静态返回固定 message), 而非 mock 调用链
- callbacks/ 写 `RecordingCallback` (Phase 1 已有), 在测试中验证 events 流
- 严禁 `unittest.mock.patch.object(...)` 这种"测自己 mock" 的反模式

**策略 3 — 真实 schema fixture (Phase 1 教训复用)**:
- 单测必须用真实 SKILL schema (text-segmentation / event-extraction 等), 不允许 hand-empty schema
- 跟 Phase 1 RETROSPECTIVE Learning #4 一致

### 3.5 子任务划分 (按低覆盖文件清单)

预计 4-6 个子任务, 每子任务针对 1-2 个低覆盖文件:

- **T-cov-1**: callback_bridge.py 17% → 95% (集成测试 + Dummy Provider, 2h)
- **T-cov-2**: skill_tool_factory.py 0% → 95% (集成测试用真实 manifest, 1.5h)
- **T-cov-3**: providers/*.py 平均 30% → 90% (record-replay fixture, 2-3h)
- **T-cov-4**: runner.py + bootstrap.py (集成测试, 1.5h)
- **T-cov-5**: cognitive 剩余文件 + tools (各自单测, 2h)
- **T-cov-final**: 跑全库 cov 达 95%, 找剩余 gap 补齐 (1h)

### 3.6 hazards

- **测自己 mock 反模式**: 必须由 a1 review 把关, 任何 `mock.patch.object` 测试必须 a1 验证它真的覆盖业务逻辑 (而非测试用例自己写的 mock 行为)
- **Dummy fixture 不真实**: DummyOpenAIProvider 等 fixture 需要复刻真实 provider 的关键不变量 (例: 流式输出 chunk 边界 / 错误码), 不能写过简
- **集成测试慢**: 集成测试如果跑过慢 (> 10s), 整个测试套时间会爆, 加 `@pytest.mark.slow` 标记 + CI 分阶段跑

### 3.7 验收

- `pytest tests/graph_agent/ --cov=src/core/graph_agent --cov-report=term` TOTAL ≥ 95%
- 单文件 coverage report 没有任何文件 < 70% (避免某个文件死角拉低均值)
- 集成测试在 60s 内跑完 (整套 < 90s)
- a1 review 确认无"测 mock"反模式

---

## §4 D4 — 旧 io/manager.py 处置 (砍除)

### 4.1 现状审计 (a3 grep 实测)

```bash
$ grep -rn "io.manager\|io/manager\|from .manager\|from ..io.manager" src/core/graph_agent/ tests/

src/core/graph_agent/__init__.py:26:from .io.manager import IOManager  # noqa: E402
src/core/graph_agent/io/__init__.py:4:from .manager import IOManager
```

发现 **2 处 caller**, 都是 re-export (从根包 / io 包重新暴露 IOManager), 不是逻辑调用.

新 `core/io_manager.py` (MVP-2) 跟旧 `io/manager.py` 是**两个不同路径的 IOManager 类**, 两者**不能共存**, 否则 SKILL 作者 import 不一致会用错版本.

### 4.2 决策: 砍除

按 a2 research §2.4: 旧 `io/manager.py` 在 MVP-2/3 已被 `core/io_manager.py` 完全替代, 直接砍除。砍除前必须:
1. 把 `src/core/graph_agent/__init__.py:26` 的 `from .io.manager import IOManager` 改为 `from .core.io_manager import IOManager`
2. 把 `src/core/graph_agent/io/__init__.py:4` 的 `from .manager import IOManager` 改为 `from ..core.io_manager import IOManager` (或者删整个 `io/` 子包)
3. 删 `src/core/graph_agent/io/manager.py` 文件

### 4.3 hazards

- **deprecation 兼容**: 第三方 SKILL 作者可能在自己代码里 `from graph_agent.io.manager import IOManager`, 直接砍会破坏向后兼容
- **缓解**: `graph_agent/__init__.py` + `graph_agent/io/__init__.py` 的 IOManager re-export **必须保留**, 改为指向 `core/io_manager`. 只删 `io/manager.py` 文件本身, 用户的 `from graph_agent import IOManager` / `from graph_agent.io import IOManager` 仍可工作
- **第三方深度 import**: 若有用户写 `from graph_agent.io.manager import IOManager` (深度 import), 这种会 break. 1.0.0 RELEASE_NOTES Migration 段必须明写

### 4.4 实施

1 个原子 commit:
- 改 `__init__.py` × 2 个文件的 re-export 路径
- 删 `io/manager.py` 文件
- 验收 `pytest` 不退步 + `python -c "from graph_agent import IOManager"` 仍工作

### 4.5 验收

- `ls src/core/graph_agent/io/manager.py` → ENOENT
- `from graph_agent import IOManager` → import 成功 (re-export 仍指向 core/io_manager)
- pytest 不退步
- 4 SKILL compile + e2e smoke 不破裂

---

## §5 D5 — test_strict_v2.py 处置

### 5.1 现状审计

- 文件: `tests/graph_agent/core/validators/test_strict_v2.py` (290 行)
- 测试目标: `graph_agent.core.validators.strict_v2` (290 行模块, 含 `_has_exit_contract_marker` / `_is_legacy_data_piping_tool` / `_parse_inline_example` / `check_exit_contract` / `check_io_schema` / `check_io_traceability` / `check_pipeline_alignment` 等 7+ 函数)
- **关键事实**: `src/core/graph_agent/core/validators/strict_v2.py` **仍存在**, 14 个测试 fail 是因为 Pydantic schema 收紧 (extra="forbid") 后 fixture 数据跟新 schema 不兼容, 不是因为模块本身被废弃
- 当前 CI 配置用 `--ignore=tests/graph_agent/core/validators/test_strict_v2.py` 续命

### 5.2 决策: 重写 (不删)

a2 research §2.5 给"删 OR 重写", a3 推荐**重写**, 理由:
1. `strict_v2.py` 模块本体仍在用 (是 SKILL compile 时的 strict-tier rules 校验, 在 loader pipeline T4 阶段被调用)
2. 14 个测试覆盖了 7+ 个内部函数 + 4 个 check_X 函数, 重写工作量比 "重新写一份等价测试" 小
3. ProtocolValidationMiddleware (MVP-3) 是**运行时**校验, strict_v2 是**编译期**校验, 两者**不重叠**, 不能因为前者就删后者

### 5.3 实施

1 个 commit:
1. 跑 `pytest tests/graph_agent/core/validators/test_strict_v2.py -v` 看具体 fail 原因
2. 按 fail 类型分类 (例如: SimpleNamespace fixture 缺字段 / Pydantic v2 API 变更 / schema 重构后字段名变化)
3. 逐个 fixture 修复 + 测试断言对齐新 schema
4. 跑 `pytest tests/graph_agent/core/validators/test_strict_v2.py` 全过
5. 删 CI 配置中的 `--ignore=tests/graph_agent/core/validators/test_strict_v2.py` 行

### 5.4 hazards

- **底层 strict_v2 模块本身有 bug**: 修测试时若发现某个 `check_X` 函数行为有 bug, **不要在测试里绕过**, 改回模块本体修. 这是 Phase 1 "测试障眼法" 教训复用
- **测试 fixture 跟 SKILL.md schema 强耦合**: SKILL.md schema 在 MVP-2/3 收紧, fixture 必须跟新 schema 对齐, 否则 fix 一个 break 一个

### 5.5 验收

- `pytest tests/graph_agent/core/validators/test_strict_v2.py` 全过
- pytest **不带** `--ignore=test_strict_v2` flag 跑全库也全过
- CI 配置 `--ignore` 列表中已删 test_strict_v2

---

## §6 D6 — 1.0.0 RELEASE_NOTES 升级

### 6.1 目标

把当前 `docs/v1-reset/RELEASE_NOTES.md` (Phase 1, 锚定 5decd0a..85bc4b8 共 40 commits) **整体重写**为 1.0.0 final 版本。

### 6.2 升级版结构 (按 v1-reset 风格 + 反 Phase 1 吹牛错)

```markdown
# graph_agent 1.0.0 — v1-reset 完整 Ship

## TL;DR
1.0.0 是 graph_agent 自诞生以来最彻底的一次重构, 通过 v1-reset 序列 5 个 MVP 阶段
(MVP-1 到 MVP-5), 框架从"动态字典脚本"进化为"强类型图引擎"。
此版本确立了未来 3 年的核心接口契约, 工程门禁 100% 达标。

## 工程门禁达标数据 (Phase 1 + Phase 2 整合)
- ruff: 0 errors / 0 warnings (0 noqa 残留)
- mypy --strict: zero issues (全库, 不仅核心)
- pytest: 全过 (含 test_strict_v2.py 解禁)
- coverage: TOTAL ≥ 95% (集成测试 + 真实 fixture)
- 4 SKILL compile + e2e smoke: byte-equal vs Phase 1 baseline (性能偏差 ≤ ±5%)
- context["_X"] 残留: 0 (state.py shim 也已删)
- io/manager.py 文件: ENOENT
- a2 honesty audit: ≥ 9.5/10

## 用户感知改变 (UX for SKILL Authors)
[复用 Phase 1 RELEASE_NOTES TL;DR 的 5 项, 但加 "类型完整暴露" / "covereage 95% 含义"]

## 5 MVP 阶段完整回顾
- MVP-1 (state split): BusinessData/FrameworkState 物理拆分
- MVP-2 (schema/io): SchemaEngine + IOManager
- MVP-3 (loader/middleware): 三阶段 Pipeline + 4 middleware + DEFAULT_MIDDLEWARE_ORDER
- MVP-4 (executor/finish): phase_executor 重画 + 节点多态 + finish_task 通道
- MVP-5 (cleanup/finalize): ruff 0 / mypy strict / coverage 95% / io/manager 删 / strict_v2 修

## Migration Guide (1.0.0 整合版)
1. SKILL.md 升级 (schema_version 2.0 强制)
2. WorkflowState 顶层结构 (data / flow / messages, 不再有 context)
3. 调用方 API (RunConfig + Harness.run 拆解)
4. checkpoint 不兼容声明 (升级时清空)
5. 第三方深度 import 弃用 (例: graph_agent.io.manager 路径已删, 用 graph_agent.IOManager)

## 致谢
按 Phase 1 RELEASE_NOTES 致谢段扩展, 加 Phase 2 (MVP-4 + MVP-5) 协作 commits 数
```

### 6.3 反吹牛纪律 (Phase 1 教训复用)

按 Phase 1 RETROSPECTIVE §3 失败 #4 教训:
1. **指标必须真实可验证**: 每条 "0 errors / ≥ 95%" 等数字, 必须在 PR description 附 `command + output snippet` 证据
2. **no 越界声称**: 不写"工时 21 天 → 4 天"这种主观 / 难以验证的话; 写实际数据
3. **加 'Known Limitations / Future Work' 段**: 1.0.0 ship 不代表完美, 必须诚实列后续 v1.1 / v1.2 计划

### 6.4 实施

子任务结构:
- **T-rn-1** (a3 草拟): 按上面结构起草 1.0.0 RELEASE_NOTES.md, 实测每条数据
- **T-rn-2** (a2 honesty audit): a2 跑 audit, 标 "宣发越界 / 数据不实 / 表述模糊" 三类问题
- **T-rn-3** (a3 修订 + a1 final review): 按 audit 修订, a1 verify 工程数据准确

### 6.5 hazards

- **a2 audit 也可能漏**: 1.0.0 是 final ship, 必须主控 + a2 + a1 三方过 (跨 agent 评估冲突 ↓ 调和方法见 Phase 1 RETROSPECTIVE §4)
- **指标实测 vs 文档脱节**: a3 草拟时一定要**当场跑命令拿数据**, 不允许复制 Phase 1 数据假装

### 6.6 验收

- a2 honesty audit ≥ 9.5/10 (Phase 1 audit 满分基准)
- a1 final review 确认所有指标可在 CI 复跑验证
- 主控 verify: 跟 Phase 1 RELEASE_NOTES 对比, 没有 Phase 1 已暴露的"吹牛模式"

---

## §7 D7 — Final ship gate (8 工程门禁)

### 7.1 8 个 CI hard fail 不变量

按 a2 research §3:

```yaml
# .github/workflows/v1-reset-final-ship.yml (示意, 实施时落)
jobs:
  ruff:
    run: ruff check src/core/graph_agent/
    expect: exit 0
  mypy:
    run: mypy --strict src/core/graph_agent/ --explicit-package-bases
    expect: exit 0  
  pytest:
    run: pytest tests/graph_agent/  # 不带 --ignore=test_strict_v2
    expect: 全过
  coverage:
    run: pytest --cov=src/core/graph_agent --cov-fail-under=95
    expect: TOTAL ≥ 95%
  skill_compile:
    run: python -c "from graph_agent.core.compiler import compile_skill; ..."
    expect: 4 SKILL 全过 + WARN-only
  invariants_grep:
    run: |
      grep -rn 'context\["_\|ctx\["_' src/ tests/ --include="*.py" \
        | grep -v "core/state.py" | wc -l
    expect: 0
  no_legacy_io:
    run: ls src/core/graph_agent/io/manager.py
    expect: ENOENT
  release_notes_audit:
    manual: a2 honesty audit, ≥ 9.5/10
```

### 7.2 实施

CI workflow 整合到 `.github/workflows/ci.yml`, 设置成 PR-blocking. 主分支 push 时也跑.

### 7.3 hazards

- **CI 跑全库 mypy 慢**: 估时 3-5 min, 可能让 CI 超时. 缓解: cache mypy `.dmypy.json` 增量
- **coverage 数字浮动**: pytest-cov 在并发跑时 line counts 可能微变, `--cov-fail-under=95` 设 hard threshold 时, 95.0% vs 95.1% 都算过, 不要设 `--cov-fail-under=95.5`

### 7.4 验收

- 所有 8 工程门禁在 CI 跑过 + 主分支 PR 触发跑过
- 失败时 CI 必须 fail (不允许 warn-only)
- 主控 final summary 确认 8 / 8 PASS

---

## §8 D8 — 跟 MVP-4 协同 (context["_X"] = 0 不变量)

### 8.1 背景

MVP-4 T7a 负责把 12 处 `ctx["_X"]` 残留迁移到 `state["flow"]` 直接读, 并删 `state.py:legacy_context_from_state` 桥函数. MVP-5 任务**不**重新做迁移, 只**验证不变量**.

### 8.2 验证方法

CI 工程门禁 #6 (上面 D7) 已写: 

```bash
grep -rn 'context\["_\|ctx\["_' src/core/graph_agent/ tests/graph_agent/ --include="*.py" \
  | grep -v "core/state.py:" \
  | wc -l
# expect: 0
```

例外白名单 (允许保留):
- `core/state.py` 内的 shim 逻辑 (若 MVP-4 没删完, MVP-5 在此 task 一起删)
- `tests/graph_agent/core/test_state.py` 内测桥函数本体的测试

### 8.3 hazards

- **MVP-4 T7a 漏迁某些 ctx 站点**: 跑 D8 grep 时若发现 N > 0, 必须**先反馈**到 MVP-4, 由 MVP-4 owner 补迁, 不在 MVP-5 内做
- **state.py shim 实际仍有 phase_executor caller**: MVP-4 T12 未删 phase_executor 前 shim 必须保留, MVP-5 启动时若 phase_executor 已删则 shim 也可删

### 8.4 验收

- D8 grep → 0 hits
- `legacy_context_from_state` / `workflow_state_from_legacy_context` 函数在 `state.py` 不存在 (MVP-4 T12 已删 OR MVP-5 在此 task 删)

---

## §9 子任务划分原则

### 9.1 总规模

按 a2 research §4 估时:

| 大任务 | 子任务数 | 估时 |
|---|---|---|
| D1 ruff 拍平 | 5 | 4-6h |
| D2 mypy strict | 8-10 | 8-12h |
| D3 coverage 95% | 4-6 | 6-8h |
| D4 io/manager 砍 | 1 | 1h |
| D5 test_strict_v2 修 | 1 | 1h |
| D6 RELEASE_NOTES 升级 | 3 | 2h (含 audit) |
| D7 CI workflow 整合 | 1 | 1h |
| D8 invariants 验证 | 1 | 0.5h |
| **总计** | **24-28** | **23-31h** |

a2 research 估 12-16 个子任务 + 21-30h. a3 design 拆得更细 (24-28), 估时一致 (23-31h ≈ 21-30h). 实施时按 brief 派单粒度可再合并 (例: D1 5 个 ruff 阶段合 2-3 commit).

### 9.2 子任务规则 (Phase 1 复用)

- 单子任务 1-3h, 单 commit (超过 4h 必须再拆)
- 单 commit 后 pytest 不退步
- 子任务依赖关系清晰
- a3 owner 必须 a1 review (Phase 1 Learning #3)
- 测试必须用真实 fixture (Phase 1 Learning #4)

### 9.3 owner 划分预估

按 Phase 1 实战:
- **a1 codex 主线**: D1 (ruff 高危 SIM/E402) + D2 (mypy harness.py) + D6 (T-rn-3 final review) + D7 (CI workflow)
- **a3 claude 副线**: D1 (ruff 安全批量 + I001 + UP037) + D2 (mypy Layer 0-1) + D3 (coverage 集成测试) + D4 (io/manager 砍) + D5 (test_strict_v2 修) + D6 (T-rn-1 草拟) + D8 (invariants 验证)
- **a2 gemini**: D6 (T-rn-2 honesty audit) + 必要的 design review

### 9.4 关键路径

```
[D8 invariants verify (短)]──┐
                              ↓
[D4 io/manager 砍 (短)]──┐
[D5 test_strict_v2 修 (短)]──┤
[D1 ruff 拍平 (中等, 串行 5 阶段)]──→
[D2 mypy strict (长, Layer 1→2→3→4)]──→
[D3 coverage (中等, 并行)]──┘
                                          ↓
                                 [D6 RELEASE_NOTES 草拟]→[a2 audit]→[a1 final review]
                                          ↓
                                 [D7 CI workflow + final ship]
```

最长链 = D2 (8-12h) + D6 (2h) + D7 (1h) ≈ 12-15h 顺序; 加上 D1 + D3 + D4 + D5 并行的关键路径, 总估 22-26h wall-clock (跟 a2 research 21-30h 估时一致).

---

## §10 跟 Phase 1 / MVP-4 / 1.0.0 RELEASE_NOTES 的 alignment

### 10.1 跟 Phase 1 RELEASE_NOTES 关系

- Phase 1 RELEASE_NOTES (`5decd0a..85bc4b8` 锚定) **不删**, 作为 v1-reset 序列的中间发布历史保留
- 1.0.0 RELEASE_NOTES (`docs/v1-reset/RELEASE_NOTES.md` 整体重写) **新写**, 替代 Phase 1 版本作为正式 release 文档
- Phase 1 版本可改名为 `RELEASE_NOTES_PHASE1.md` 移到 `docs/v1-reset/archive/` 或保留原位 (1.0.0 中明确 reference)

### 10.2 跟 RETROSPECTIVE_PHASE1.md 关系

- Phase 1 RETROSPECTIVE 不动, 作为 5 MVP 中间 retrospective 保留
- MVP-4 + MVP-5 完成后**新写** `RETROSPECTIVE_PHASE2.md` (覆盖 MVP-4 + MVP-5 实施过程, 估时偏差, learning 等)
- 1.0.0 ship 完成后**新写** `RETROSPECTIVE_V1_RESET_FINAL.md` (整合 Phase 1 + Phase 2, 给 v2 起步参考)

### 10.3 跟 MVP-4 关系 (硬阻塞 / 软依赖)

按 a2 research §5:
- **硬阻塞**: D8 (invariants verify) 必须在 MVP-4 T7a + T10a + T12 全部 merge 后才能跑
- **硬阻塞**: D1 (ruff 拍平) 必须在 MVP-4 T12 (phase_executor.py 物理删除) 后再跑, 否则浪费算力修被删的代码
- **软依赖**: D2 (mypy strict) 可以从 MVP-4 完成态开始 Layer 0/1 并行, harness.py / runner.py 必须等 MVP-4 final ship 才动
- **软依赖**: D3 (coverage) 可以提前从 callback_bridge / providers 着手 (跟 MVP-4 改动无强冲突)

### 10.4 跟 v1.1 / v1.2 后续版本 alignment

1.0.0 final ship 后, 后续路线图 (RELEASE_NOTES Future Work 段):
- **v1.1**: `parallel_delegate v2` (LangGraph Send API)
- **v1.2**: `Multimodal` 增强
- **v1.5+**: 动态 Schema 进化
- **v2.0**: 跨 Agent 协议栈 / Studio 适配

---

## §11 风险点 (按严重性排序)

### §11.1 [High] D2 mypy strict legacy 修起来工作量爆

- **现象**: a2 research §6 警示, 估 12h 可膨胀到 20h+. harness.py 单文件已 11 errors, 推算 Layer 2/3 总错误数 50+
- **缓解**: 
  1. 严格按 layer 反向遍历, 不允许跳级 (跳级会撞依赖未修问题, 错误数指数爆炸)
  2. 每 layer 独立 commit, 可单独回滚
  3. 实施期监控时间, 若某 layer 估时超 +50%, 立即停下来 reseval (是不是跳级了 / stub 真的缺失)
- **回滚**: 单文件 mypy strict 实在过不去, 加 `mypy.ini` `[mypy-graph_agent.<problem_module>]` ignore 该文件 + 在 1.0.0 RELEASE_NOTES Known Limitations 段如实标 "若干 legacy 模块 mypy 暂未达 strict, 推 v1.1"
- **风险等级**: High — 因为这是 1.0.0 ship 的关键门禁

### §11.2 [High] D3 coverage 难测区无价值 mock 测试

- **现象**: 写 "测自己 mock" 反模式 (Phase 1 RETROSPECTIVE Learning #4)
- **缓解**: 
  1. 严禁 `unittest.mock.patch.object` 用法 (覆盖率脚本 grep 拦截)
  2. 优先集成测试 + Dummy Fixture
  3. a1 review 重点把关 (任何 mock 调用必须 a1 verify 真覆盖业务逻辑)
- **风险等级**: High — 写错等于没写, 而且会通过 95% 覆盖率门禁形成假阳性

### §11.3 [Medium] D6 1.0.0 RELEASE_NOTES 再次吹牛

- **现象**: Phase 1 教训重演 (commit 8136efd → 85bc4b8 降级)
- **缓解**: 
  1. 强制三方 audit (a2 honesty + a1 工程 + 主控 final)
  2. 每条数字必须**当场跑命令**得到, 不允许复制 Phase 1 数字
  3. CI workflow 必须验证 RELEASE_NOTES 中声明的数字 (例: 写"95%" 时 `--cov-fail-under=95` 必须在 CI 配)
- **风险等级**: Medium — 翻车后 a2 audit 会抓出来, 但耽误时间

### §11.4 [Medium] D5 test_strict_v2 重写发现底层 strict_v2 模块本身 bug

- **现象**: 修测试时发现某 `check_X` 函数行为异常, 测试一改就过, 其实是模块本体 bug
- **缓解**: a3 实施时严格遵守 "测试障眼法" 反模式禁忌, 任何 fail 改不通的, 先 a1 verify 是模块 bug 还是测试 bug
- **风险等级**: Medium

### §11.5 [Low] D1 ruff auto-fix 误伤

- **现象**: F401 删 lazy import → 运行时 ImportError; SIM108 三元改写 → 可读性下降; E402 移导入 → 循环引用
- **缓解**: 
  1. 阶段 1 安全批量 + 阶段 2-5 手动审核分开
  2. 每阶段后跑 4 SKILL e2e smoke (启动期 ImportError 在单测层不暴露)
  3. 高危 rule (F401 / SIM108 / E402) 必须 a1/a2 人工审
- **风险等级**: Low — 错了能马上发现 + 回滚 + 单 commit 不影响其他工作

### §11.6 [Low] D7 CI workflow 配错导致 8 门禁误判

- **现象**: 例如 `--cov-fail-under=95` 写成 95.5 让数字浮动 fail; 例如 mypy 命令漏 `--explicit-package-bases` 让 md-patch crash
- **缓解**: CI workflow 落盘前在本地全部跑过, 用 `act` 或者直接 push 一个 throwaway PR 验证
- **风险等级**: Low — 配置问题, 不是设计问题

---

## §12 Invariants (1.0.0 ship 后运行时检查)

```python
def _verify_v1_reset_final_invariants() -> None:
    """1.0.0 ship 后框架必须保持的不变量, MVP-5 实施期间不能破坏."""
    # 1. ruff check src/ → 0 errors (CI 已验)
    # 2. mypy --strict src/ → zero issues (CI 已验)
    # 3. pytest 全过 → coverage ≥ 95% (CI 已验)
    # 4. context["_X"] / ctx["_X"] 全库残留 == 0 (CI grep 已验)
    # 5. io/manager.py 文件不存在 (CI ls 已验)
    # 6. v1-reset 6 MVP 序列的所有架构决策 (BusinessData 拆分 / SchemaEngine 收口 / 三阶段
    #    Pipeline / 4 middleware DEFAULT_MIDDLEWARE_ORDER / phase_executor 节点多态 /
    #    state_reducers / Bootstrap) 跟 spec 一致, 没人用补丁式 ifelse 绕过
    # 7. # noqa 全部带 reason 注释 (规则: 不允许裸 noqa)
    # 8. # type: ignore 全部带 reason 注释 (同上)
```

---

## §13 与 RELEASE_NOTES 1.0.0 升级版的最终结构 (a3 推荐)

`docs/v1-reset/RELEASE_NOTES.md` 1.0.0 整体结构:

```
# graph_agent 1.0.0 — v1-reset 完整 Ship

## TL;DR (3-5 句)
## 工程门禁达标 (8 条数据 + 实测命令)
## 用户感知改变 (UX for SKILL Authors, 5 条)
## Breaking Changes (从 0.x 升级)
## 5 MVP 阶段完整回顾 (每 MVP 1 段)
## Migration Guide (整合 Phase 1 + Phase 2 全部 Migration)
## Known Limitations / Future Work (诚实段, 不伪装完美)
## AI 协作模式致谢 (按 Phase 1 致谢段扩展)
## 附录: 关键 commit 历史 (Phase 1 + Phase 2 commit ranges)
```

总长度估计 200-250 行, 比 Phase 1 (115 行) 长 1 倍但内容更扎实.
