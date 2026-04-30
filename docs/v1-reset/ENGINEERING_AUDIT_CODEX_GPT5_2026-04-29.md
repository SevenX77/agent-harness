---
title: 工程全量审核报告
作者: a1 (Codex, GPT-5 coding agent)
派任务方: 用户 (非主控派)
日期: 2026-04-29 16:07
类型: agent 工程基线审核 (Engineering Baseline Audit)
范围: 本地仓库 /home/sevenx/coding/agent-harness, 只读, 未修改代码
区别声明:
  - 本文件 a1 (codex) **工程基线视角** — 12 个 P0/P1/P2 具体 issue 带 file:line 证据
  - AUDIT_REPORT_2026-04-29.md a2 (gemini, 用户派) **架构治理视角** — 编译期严格契约
  - ARCHITECTURE_AUDIT_PHASE1.md a2 (gemini, 主控派) **架构溯源视角** — 接口契约 + 设计文件回溯
  - MASTER_REVIEW_PHASE1.md 主控 Claude **PM 视角** — 大厂对标 + 工程性能评分
---

# 工程全量审核报告

报告人：Codex，GPT-5 coding agent  
检查日期：2026-04-29  
检查范围：本地仓库 `/home/sevenx/coding/agent-harness`  
性质：只读工程审核，未修改代码

## 结论摘要

按成熟 Python/agent infra 项目的工程基线对表，本项目当前的核心问题不是单点代码风格，而是质量门禁、可导入性、仓库卫生和运行契约不一致。

`graph_agent` 主体已有较多测试，核心 happy path 可以运行；但 CI 明确绕过失败测试，静态检查只覆盖极少文件，覆盖率门槛偏低。外围 `src/visual_learning` 和部分 `src/core` 遗留模块当前不可导入。仓库还纳入了 `.venv/`、`.claude/sessions/` 等本地状态文件，这在成熟项目中属于严重工程卫生问题。

## P0 问题

### 1. CI 绕过失败测试，质量信号不可信

证据：

- `.github/workflows/ci.yml:27` 显式忽略 `tests/graph_agent/core/validators/test_strict_v2.py`
- 本地执行 `.venv/bin/python -m pytest tests/graph_agent` 结果为 `861 passed, 2 skipped, 14 failed`
- 加上 CI ignore 后，`.venv/bin/python -m pytest tests/graph_agent --ignore=tests/graph_agent/core/validators/test_strict_v2.py` 结果为 `857 passed, 2 skipped`

失败集中在 strict v2 validator。根因是 validator 和 manifest schema 已经脱节：

- `src/core/graph_agent/core/validators/strict_v2.py:132` 读取 `phase.is_router`
- `src/core/graph_agent/core/validators/strict_v2.py:207` 起读取 `inp.schema_ref`、`inp.example`、`inp.allow_empty`、`inp.on_empty`
- `src/core/graph_agent/core/manifest.py:107` 的 `IoInput` 并没有这些字段
- `src/core/graph_agent/core/manifest.py:212` 的 `LLMPhase` 也没有 `is_router`

影响：

CI 当前给出的是被裁剪过的通过结果，不能代表全量质量。strict v2 要么是应修复的 validator，要么是应删除的 stale 代码；不能继续通过 ignore 掩盖。

### 2. `src/visual_learning` 当前不可导入

证据：

- `import src.visual_learning.multimodal_client_manager` 失败
- `src/visual_learning/__init__.py:3` 导入 `phase1_gt_extraction`
- `src/visual_learning/__init__.py:4` 导入缺失的 `phase2_alignment_analysis`
- `src/visual_learning/phase1_gt_extraction.py:31` 依赖不存在的 `src.core.config`
- 同文件还依赖不存在的 `src.core.agent_harness`、`src.core.multimodal_client_manager`、`src.core.error_recovery_agent`

影响：

这部分代码如果仍属于产品边界，就是阻断级 bug；如果已经废弃，应从包边界、文档和 CI 中明确隔离，避免误导后续开发。

### 3. 仓库纳入本地虚拟环境和会话状态

证据：

- `.gitignore` 未覆盖 `.venv/`、`.claude/`、`.coverage`、`.mypy_cache/`、`.pytest_cache/`、`.ruff_cache/`
- `git ls-files` 可见 `.venv/bin/python`、`.venv/bin/ruff` 等虚拟环境文件
- `git ls-files` 可见 `.claude/sessions/*`
- 本地仓库体积约 378M

影响：

这会污染 review diff、拖慢仓库、破坏环境可复现性，并可能泄露本地上下文。成熟项目不应追踪虚拟环境、模型会话和本地缓存。

## P1 问题

### 4. Python 版本契约冲突

证据：

- `pyproject.toml:5` 写 `requires-python = ">=3.11"`
- `.github/workflows/ci.yml:16` 使用 Python 3.11
- `src/core/graph_agent/README.md:38` 写最低 Python 3.12
- `src/core/graph_agent/README.md:39` 还描述了低于 3.12 时 checkpoint downgrade 的常见症状

影响：

用户、CI、发布包和文档的运行预期不一致。应明确项目真实最低版本，并让 pyproject、CI、README 和测试矩阵保持一致。

### 5. 静态检查覆盖严重不足

证据：

- `.github/workflows/ci.yml:20` 只对 `exceptions.py`、`manifest.py`、`checkpointer.py` 跑 ruff
- `.github/workflows/ci.yml:24` 只对同样三个文件跑 mypy strict
- 本地执行 `.venv/bin/python -m ruff check src` 有 242 个问题
- 本地执行 `.venv/bin/python -m ruff check src/core/graph_agent tests/graph_agent --statistics` 有 114 个问题
- 本地执行 `.venv/bin/python -m mypy src/core/graph_agent` 被 `skills/builtin/md-patch/__init__.py` 的非法包名阻塞

影响：

当前 CI 的静态检查不能代表项目真实质量。它只验证了少量文件，且绕开了大量实际代码。

### 6. code-only phase 静默丢弃 dict 返回值

证据：

- `src/core/graph_agent/core/phase_executor.py:274` 调用工具
- `src/core/graph_agent/core/phase_executor.py:276` 只在返回值是 `str` 时更新 `last_output`
- 工具返回 `dict` 时没有合并到状态，也没有报错

影响：

如果 code-only 工具按直觉返回结构化结果，结果会被静默丢弃。除非工具直接原地修改 `BusinessData`，否则调用看似成功但状态无变化。这是容易产生隐性生产 bug 的行为。

### 7. 覆盖率门槛偏低，关键模块覆盖不足

证据：

- CI coverage gate 是 65%
- 按 CI ignore 跑覆盖率，总覆盖约 71.31%
- 关键模块覆盖明显偏低：
  - `callback_bridge.py` 17%
  - `models/factory.py` 19%
  - `models/resolver.py` 54%
  - `tool_wrapper.py` 46%
  - `tools/builtin/parallel_map.py` 13%
  - `validators/strict_v2.py` 0%

影响：

总覆盖率勉强过线，但 agent runtime、模型解析、回调桥接、并行工具等风险较高模块没有足够测试保护。

### 8. 构建和包边界存在隐患

证据：

- `skills/builtin/md-patch` 目录名含 hyphen 且包含 `__init__.py`，导致 mypy 认为它是非法 Python package
- `.venv/bin/python -m hatchling build -t wheel` 因本地缺少 `hatchling` 无法验证构建
- `pyproject.toml` 只将 `src/core/graph_agent` 映射为 `graph_agent` 包，但仓库还有大量 `src/core`、`src/visual_learning` 代码

影响：

仓库里哪些代码属于发布包、哪些只是遗留脚本，目前边界不清。工具链也会被非 Python package 的 skill 目录干扰。

## P2 问题

### 9. IO manager 缺少路径边界约束

证据：

- `src/core/graph_agent/io/manager.py:106` 直接按配置路径读文件
- `src/core/graph_agent/io/manager.py:203` 直接按配置路径写文件
- 没有看到限制到 `output_dir`、workspace 或明确 allowlist 的逻辑

影响：

当 skill manifest 或 IO 配置可变时，存在越权读写风险。即使当前 skill 被视作可信，也建议在工程层加入边界约束。

### 10. 模型 failover 可能掩盖真实请求错误

证据：

- `src/core/graph_agent/models/resolver.py:49` 起的 `_RUNTIME_FAILOVER_EXCEPTIONS_LIST`
- 其中包含 `BadRequestError`

影响：

400 类错误通常代表 prompt、schema、参数或 provider contract 错误。把它纳入通用 failover 容易把真实工程问题伪装成 provider fallback，降低可观测性和定位效率。

### 11. 旧 API 面和重复概念增加维护成本

证据：

- `src/core/graph_agent/core/types.py:54` 起仍保留 `subgraph`、`parallel_subgraphs`、`reducer_path` 等字段
- 同时仓库内存在 `src/core/graph_agent/io/manager.py` 和 `src/core/graph_agent/core/io_manager.py` 两套 IOManager 命名
- 文档中已出现 v1 reset 和 delegate/parallel 清理语境，但类型面仍残留旧概念

影响：

这会增加新开发者理解成本，也容易让后续功能误用已经计划删除或不再推荐的字段。

### 12. 若干健壮性问题

证据：

- `src/core/data_manager.py:30` 依赖不存在的 `story_forge.core.config`
- `src/core/data_manager.py:32` 的 `_PROJECT_ROOT` 从当前路径向上爬四级，实际会落到仓库父级，而不是 repo root
- `src/core/artifact_manager.py:165` 起 broad except 后返回 `None`，可能吞掉文件损坏或权限错误
- `src/core/graph_agent/tools/synthesize_speech.py:77` 写 ffmpeg concat 文件时直接拼接路径，遇到特殊字符路径时可能出错

影响：

这些问题单独看不一定阻断主流程，但会让故障变得更难定位，并降低项目在复杂环境中的稳定性。

## 本次执行的验证命令

```bash
.venv/bin/python -m pytest tests/graph_agent
.venv/bin/python -m pytest tests/graph_agent --ignore=tests/graph_agent/core/validators/test_strict_v2.py
.venv/bin/python -m pytest tests
.venv/bin/python -m ruff check src
.venv/bin/python -m ruff check src/core/graph_agent tests/graph_agent --statistics
.venv/bin/python -m mypy src/core/graph_agent
.venv/bin/python -m pytest tests/graph_agent --ignore=tests/graph_agent/core/validators/test_strict_v2.py --cov=src/core/graph_agent --cov-report=term-missing
```

## 建议修复顺序

1. 去掉 CI 对 `test_strict_v2.py` 的 ignore，选择修复 strict v2 或正式删除 stale validator。
2. 决定 `src/visual_learning` 是否仍属于当前项目。如果属于，修复导入链并补测试；如果不属于，从包边界和文档中隔离。
3. 清理 `.venv/`、`.claude/`、`.coverage`、缓存目录等本地状态出 git，并补齐 `.gitignore`。
4. 统一 Python 版本契约，让 `pyproject.toml`、CI、README 和测试矩阵一致。
5. 将 ruff 和 mypy 的 CI 范围扩大到实际代码边界，而不是只检查三个文件。
6. 修复 code-only phase 对结构化返回值的处理，至少应明确报错或合并状态。
7. 提高关键 runtime 模块覆盖率，尤其是模型解析、callback bridge、parallel map、IO、checkpoint/resume 路径。
8. 明确 skill 目录和 Python package 的边界，避免 `md-patch` 这类资源目录干扰 Python 工具链。

## 署名

本报告由 Codex，GPT-5 coding agent 生成。  
用于和其他模型或人工审核报告区分。
