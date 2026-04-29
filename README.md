# graph-agent-harness

## 1. 项目定位

**GraphAgent Harness** 是面向产品经理 (PM) 和内容创作者的 Agent 工作流编排引擎。它把复杂的 LLM 流水线抽象成可审阅、可版本化的 Markdown 协议，让团队用 `SKILL.md` 描述业务流程，再由 Harness 编译成 LangGraph 执行图。

可以把它理解成 Agent 时代的"文本版生产线": PM 描述每个工位做什么、上游产物怎么流到下游、质检员如何判定合格；Harness 负责把这份 SOP 编译成可运行、可重试、可验证的图执行流程。

项目源自 `deerflow 1.0` 的重构分支，当前重点已经从代码迁移转向严格契约、工程门禁和可发布质量线。

## 2. 项目状态

当前状态: **Phase 3 ship-ready release candidate (RC)**。阶段 1 工程卫生、阶段 2 中间件/校验管道重构、阶段 3 mypy/ruff 全库收敛已完成；待 must-fix Group 2 + Group 3 关闭后正式切 1.0.0。

当前分支已完成工程类 must-fix:

- CI 门禁全库化: `ruff check src/ tests/`、`mypy src/`、`pytest tests/ -x --tb=short`、coverage gate、dependency audit。
- License 元数据统一为 Apache-2.0。
- README 从早期研发说明更新为 RC 状态说明。
- Dependabot + `pip-audit` 进入依赖安全门禁。

仍在 1.0.0 前收敛的项目:

- Group 2: `phase_executor` 架构拆解、旧 `ValidationMiddleware` 双系统退役。
- Group 3: 覆盖率治理、真实 LLM 或高保真 LLM mock e2e 门禁。

## 3. 工程质量门禁

当前本地基线:

- `mypy src/`: 0 errors, `Success: no issues found in 86 source files`
- `ruff check src/ tests/`: 0 errors
- `pytest tests/ -x --tb=short -q`: 912 passed, 0 failed, 2 skipped
- Coverage: 73.25%, CI gate 73%

跳过的测试是需要外部 API key 的真实 LLM smoke，以及一个明确标注的阈值边界 case。编译期、合成状态、runtime validator、routing、live SKILL smoke 已在常规测试套件中覆盖。

Task #13 大厂双审结果已落库到 `docs/v1-reset/BIG_TECH_AUDIT_TASK13.md`: a1 工程基线 6.7/10，a2 架构设计 6.2/10。当前 Group 1 修复关闭的是配置、文档、CI 和依赖安全类 hard fail；架构和测试类 hard fail 仍按后续任务推进。

## 4. 核心概念

- **SKILL.md**: 工作流配置文档，相当于给 Agent 的 SOP。它描述输入、阶段、输出、校验器和工具。
- **Phase**: 工作阶段。复杂任务被拆成多个可验证的工位，例如提取、整理、审阅、合成。
- **State**: 阶段之间传递的状态托盘。上游明确产物会进入 State，供下游消费。
- **Validator**: 阶段末尾的质检员。输出不符合 Pydantic schema 或业务校验时，系统会给 LLM 可操作的 retry feedback。
- **LangGraph 编译产物**: Harness 把 Markdown DSL 编译为 LangGraph 执行图，获得图执行、状态流转和重试控制能力。

## 5. 适用场景

1. **长篇内容流水线**: 世界观设定 -> 大纲 -> 章节拆分 -> 逐章生成 -> 一致性检查。
2. **多步骤信息处理**: 长文提取事实 -> 翻译 -> 生成播客脚本 -> 审核格式。
3. **PM 原型验证**: 用 Copilot 口述业务流程，让模型生成 `SKILL.md`，本地跑通业务闭环。
4. **团队沉淀 Agent SOP**: 使用纯文本协议接受 Git 版本控制、Code Review 和审计。

## 6. 与其他框架的区别

- **对比 Langflow / Dify**: 可视化低代码适合快速试验，但复杂流程容易变成难以 review 的连线图。GraphAgent 采用 Docs-as-Code 的 Markdown DSL，更适合长期维护和团队协作。
- **对比基础 Tool Calling / Skills**: 常规 Skills 多是单点 Prompt + 工具。GraphAgent 的 `SKILL.md` 还定义阶段编排、状态依赖、schema 校验和多轮 retry，是完整工作流协议。

## 7. 快速开始

```bash
python -m venv .venv
. .venv/bin/activate
pip install -e .[dev]
ruff check src/ tests/
mypy src/
pytest tests/ -x --tb=short -q
```

运行 CLI:

```bash
graph-agent --help
```

## 8. 项目结构

- `src/core/graph_agent/`: 核心引擎源码，负责 `SKILL.md` 解析、编译、执行和中间件管道。
- `skills/`: 业务工作流样例和 live SKILL。
- `tests/`: 单元测试、编译期测试、middleware/runtime smoke 和 live SKILL e2e smoke。
- `docs/v1-reset/`: 阶段性设计、审计、复盘和后续修复计划。
- `docs/archive/`: deerflow 时代历史规划文档归档。
- `.github/workflows/ci.yml`: 全库质量门禁。
- `pyproject.toml`: 包元数据、依赖、mypy/ruff/coverage 配置。

## 9. License

Apache-2.0. See `LICENSE`.
