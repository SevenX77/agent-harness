# INTEGRATION_GUIDE

本指南面向“把 `graph_agent` 迁移到另一个项目中继续使用”的集成场景。

## 1. 最小集成路径

> In the AI-narrated-recap-analyst parent project, use `from src.core.graph_agent import ...` instead.

1. 复制 `src/core/graph_agent/`
2. 使用 Python 3.12 安装 `src/core/graph_agent/requirements.txt`
3. 提供 `config/llm_roles.yaml`
4. 在 `.env` 中配置至少一个 provider 的 API Key
5. 把业务工具和 SKILL.md 一起迁移

如果宿主项目需要 DeerFlow 原生全局入口，再额外提供 `config/deerflow_config.yaml`。

## 2. 集成边界

### framework 负责什么

- 多阶段编排
- DeerFlow agent loop 接入
- 模型解析与 provider failover
- 声明式 I/O
- context blackboard
- callback / trace / checkpoint
- 通用多模态工具

### 宿主项目负责什么

- 业务 skill 与业务工具
- 最终产物如何落盘或登记
- 项目级目录结构
- 外部系统连接与权限

## 3. ArtifactManager 接入

`graph_agent` 不直接依赖宿主项目的 `ArtifactManager` 类。

推荐接法是“出餐口模式”：

1. Phase 把最终结果写入 `context`
2. `io.outputs` 把目标声明为 `artifact_manager`
3. 调用方通过 `run_skill(..., artifact_saver=...)` 注入保存函数
4. `IOManager` 调这个回调完成落盘

这样做的好处：

- framework 不被宿主项目类名和签名绑死
- `graph_agent` 可以跨项目复制
- 测试时可以直接注入 mock saver

如果宿主项目暂时不接 ArtifactManager，也可以先使用 `target: file`。

## 4. 配置迁移

### `llm_roles.yaml`

这是 `graph_agent` 运行的硬前置。

推荐做法：

- 保留角色名稳定，例如 `balanced`、`fast`、`premium`
- 在宿主项目中只换 provider 与 model 映射
- 不要在 skill 里直接写死底层模型名

### `deerflow_config.yaml`

只在你需要 DeerFlow 全局工具入口、sandbox、summarization 等功能时提供。

### `multimodal_roles.yaml`

仅当你要继续复用 `graph_agent/tools/` 下的多模态工具时需要。

## 5. 运行入口

### 最常用：`run_skill`

适合：

- 一个 SKILL.md 对应一次工作流
- 由宿主项目传入 runtime inputs
- 需要 callback、trace、artifact_saver

### 直接用 `GraphAgentHarness`

适合：

- 你想在代码中手动构造 `Phase`
- 需要把 graph_agent 嵌到更大的编排系统里

### DeerFlow 全局入口

适合：

- 你要复用 DeerFlow 原生的全局 agent 模式
- 你已经有完整的 `deerflow_config.yaml`

## 6. 并发使用指南

### Phase 内并发

优先走 DeerFlow subagent：

- 在 `phase_config` 里开启 `subagent_enabled`
- DeerFlow 当前线程池上限是 `3`
- 适合一个 Phase 内存在多个边界清晰、彼此独立的子任务

### Skill 外并发

如果宿主项目要同时跑多个 skill，可以并发调用多个 `run_skill()` 实例。

要求：

- 每个实例使用独立 `thread_id`
- 每个实例有独立输出目录或 artifact key
- 不共享会被原地修改的输入对象

### 不再使用的旧约定

- `max_concurrent` 不是当前 graph_agent 的有效参数链

## 7. 工具迁移策略

推荐分层：

- `graph_agent/tools/`：通用多模态能力、认知工具、基础 provider helper
- `skills/**/tools/`：业务工具

判断标准：

- 跨项目都可能复用：留在 framework
- 只服务单一业务语义：留在 skill 本地

## 8. Callback 与 Trace 接入

默认可直接使用：

- `LoggingCallback`
- `MetricsCallback`
- `TracingCallback`

宿主项目若有自己的日志/监控系统，建议实现 `Callback` 子类并注入到 `run_skill()` 或 `GraphAgentHarness(...)`。

重点事件：

- `phase_start`
- `phase_end`
- `llm_call`
- `tool_call`
- `validation_fail`
- `retry`
- `finish_task`
- `nudge`
- `working_memory_update`
- `ambiguity_report`

## 9. 集成检查清单

- `requirements.txt` 已安装
- `llm_roles.yaml` 可解析
- `.env` 中至少一个 provider key 已配置
- skill 本地工具可以被 loader 解析
- `artifact_saver` 在宿主项目中可用
- trace 目录可写
- checkpoint 使用唯一 `thread_id`

## 10. Post-Migration Verification

After migrating to the new sub-package structure, verify the installation:

### 10.1 Import Verification

Test that all public APIs are importable:

```bash
python3 -c "
from graph_agent import (
    run_skill,
    GraphAgentHarness,
    Phase,
    WorkflowState,
    load_workflow_from_md,
    ModelResolver,
    get_model_resolver,
    get_skill_type,
    ContextResolver,
    IOManager,
    GraphAgentError,
    SkillLoadError,
    SkillCompilationError,
    TemplateRenderError,
    AllProvidersFailedError,
    MaxRetriesExceededError,
)
print('✅ All imports successful')
"
```

### 10.2 Lint Check

Run ruff to verify no import errors:

```bash
ruff check src/core/graph_agent/ --exclude deerflow
```

Expected: `All checks passed!`

### 10.3 Compiler Self-Check

Verify the compiler can parse the built-in compiler skill:

```bash
python3 -c "
from graph_agent.core.compiler import compile_skill
r = compile_skill('src/core/graph_agent/skills/compiler/SKILL.md')
print(f'FATAL: {len(r.fatals)}, WARNINGS: {len(r.warnings)}')
assert len(r.fatals) == 0, 'Compiler skill has FATAL errors'
print('✅ Compiler self-check passed')
"
```

### 10.4 Run Hello World Example

Verify the minimal example works:

```bash
export PYTHONPATH="${PYTHONPATH}:./src"

python3 -c "
from graph_agent import run_skill, LoggingCallback

callback = LoggingCallback()
result = run_skill(
    'src/core/graph_agent/examples/hello_world/SKILL.md',
    initial_context={'user_name': 'Developer'},
    callbacks=[callback]
)
print('Result:', result)
print('✅ Hello world example completed')
"
```

Expected: `Result: {'greeting': 'Hello, Developer! Welcome to graph_agent.', ...}`

### 10.5 Full Test Suite (Optional)

If you have access to the test suite:

```bash
# Run core tests (requires pytest)
pytest tests/core/test_graph_agent_audit_fixes.py -v --tb=short
pytest tests/core/test_compiler.py -v --tb=short
pytest tests/core/test_cognitive_loop.py -v --tb=short
```

### 10.6 Troubleshooting

| Issue | Cause | Fix |
|-------|-------|-----|
| `ModuleNotFoundError: src.core.graph_agent` | PYTHONPATH not set | `export PYTHONPATH="${PYTHONPATH}:./src"` |
| `No config found` | Missing llm_roles.yaml | Create `config/llm_roles.yaml` or set `GRAPH_AGENT_ROLES_PATH` |
| `API key not found` | Missing .env | Create `.env` with required API keys |
| `ImportError: No module named 'xxx'` | Missing deps | `pip install -r src/core/graph_agent/requirements.txt` |

---

## Migration Checklist (Post-Restructure)

- [ ] All imports updated in external consumers
- [ ] Sub-package structure verified (`core/`, `callbacks/`, `cognitive/`, `config/`, `models/`, `io/`)
- [ ] Root `__init__.py` re-exports correct paths
- [ ] Tests pass with new import paths
- [ ] Hello world example runs successfully
- [ ] Documentation updated (README.md, CONFIG_REFERENCE.md, COGNITIVE_LOOP_GUIDE.md)


### Subagent Middleware 限制

当 Phase 配置 subagent_enabled: true 时，DeerFlow 的 SubagentExecutor 通过内部的 make_lead_agent() 创建子 agent。该路径不经过 harness 的 create_agent(middleware=...) 调用，因此子 agent 不会注入 WorkingMemory 和 DeadEnd middleware。

子 agent 执行简单隔离任务，通常无需这些中间件。如需为子 agent 也启用自定义中间件，可在应用启动时注册全局 hook：

```python
from deerflow.agents.lead_agent.agent import set_custom_middlewares_hook
from graph_agent.cognitive.middlewares import create_custom_middlewares

set_custom_middlewares_hook(lambda: create_custom_middlewares(
    working_memory=True,
    dead_end_pruning=True,
))
```
