# Round 29 Requirements - C901 Complexity Gate

## §1 用户故事 (PM 视角)
作为产品经理，我希望我们的 Workflow 引擎底层能对标世界级成熟度（如 LangGraph / Temporal），在代码库中实现严格的 `C901` 复杂度门禁。这将有效阻止新的高复杂度假代码被合入，并通过重构现存的 13 个残余高复杂度函数，保障引擎未来的可维护性、测试可行性与执行的确定性。

## §2 验收标准 (Acceptance Criteria)
- **AC1**: 配置文件 `pyproject.toml` 中的 `[tool.ruff]` `lint.select` 必须开启 `C901`；且 `[tool.ruff.lint.mccabe]` 必须配置 `max-complexity = 10`。
- **AC2**: 核心库内的全部 13 个 C901 violations 必须被重构至复杂度 ≤10（禁止对这 13 个目标函数使用 `per-file-ignore` 残留，如因特殊原因必须保留的，需要显式的 `exemption_id` 配合豁免）。
- **AC3**: 黄金原则保障 —— 重构绝不能破坏任何 65 个公开的 API symbol（这 13 个被重构的函数全为 internal 级别，不改变对外的 Public 契约）。
- **AC4**: 架构映射同步 —— 从高复杂度函数（如 `execute`）中新抽离的独立 helper 文件，必须同步录入 `source_file_map.yaml` 并关联到对应模块。
- **AC5**: 零回归（Zero Regression）—— 所有重构必须在 pytest 中保持全线 GREEN（在现有的 Python 3.11 + 3.12 + 3.13 矩阵环境，与 ci.yml 行为严格一致）。

## §3 黄金原则 / 不可动摇约束
- 目标 13 个函数全为 internal 级别，重构仅限内部实现，**坚决不触碰、不动摇 65 个 public API**。
- 不破坏现有系统的核心模型，不修改现有的 92 个错误码、33 个核心事件与 53 个 H2 章节契约。
- 严禁修改 `docs/engine/skill-spec/*` 下已标记为 FROZEN 的系统规范文件。

## §4 范围边界
- **不在 scope**: 多 Python 版本矩阵构建（已经在 PR `6bacef9` 中处理完毕并 1010 passed）。
- **不在 scope**: Ruff 的其他 Lint 规则（如 E/F/B/I/UP 系列，本期专注解决 C901 即可）。
- **不在 scope**: 重构非 C901 的其他低劣代码（严格遵循最小爆破半径，只对准这 13 个 violations 进行精准手术）。
