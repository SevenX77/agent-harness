# Post-Plan-C Final Decisions (2026-05-06)

**版本**: 1.0
**日期**: 2026-05-06
**主控**: Claude Opus 4.7 (1M context)
**联合分析**: a2 Gemini

---

## 0. 性质

这份文档**锁定**实验阶段的最后一次大决断结果。Plan C (graph-agent + graph-agent-engine 双兼容) 在 2026-05-06 被 user 明确撤销, 后续所有项目以本文档为准。

凡跟本文档冲突的旧 spec / 旧决策, 以本文档为准, 旧文档会标 OBSOLETE 或部分 update, 不再继承其结论。

---

## 1. graph_agent SDK 公共 ABI: 13 个稳定 export

```
顶层 from graph_agent import:
  执行       run_skill, WorkflowResult
  静态分析   compile_skill, CompileResult, SkillManifest, serialize_skill
  可观测性   Callback, LoggingCallback, MetricsCallback, TracingCallback
  异常       GraphAgentError, SkillLoadError, SkillCompilationError
```

### 1.1 取舍依据

User + Gemini + master 三方 reach consensus:
- **不为 video-analysis 等下游做兼容**——video-analysis 自己适应新 SDK
- **不留 14 个 lazy deprecated** (上一版 Plan C 的妥协方案被推翻)
- **不留 graph-agent-engine 空壳子包** (Plan C 的 meta-package alias 全删)
- 这是"实验阶段最后一次大决断", 后续按这 13 个收敛

### 1.2 子类型走 `core.manifest` 直接 import (不暴露顶层)

Studio backend / video-analysis / 其他下游需要 manifest 子类型时:
```python
from graph_agent.core.manifest import (
    AgentSkillDef, GraphSkillDef, PersonaSkillDef,
    AgentProfile, LLMPhase, LogicPhase, PhaseDef,
    IoInput, IoOutput, IoDeclaration, ContextBridge,
    SkillManifest,
)
```

manifest.py 自己有 `__all__` 暴露这 12 个名字 (本身就是子模块层级的 public API, 跟顶层 13-export 是两层概念)。

### 1.3 Cut / Internal 名单 (源码留, 顶层不暴露)

**Internal** (源码留, 供 SDK 内部用, 不从 graph_agent 顶层 import):
- `GraphAgentHarness` — run_skill 内部用
- `Phase` — Harness 跑时的运行时表达
- `WorkflowState` — LangGraph state dict
- `parse_skill_file` — compile_skill 内部第一步
- `load_workflow_from_md` — run_skill 内部 step
- `IOManager`, `ContextResolver`, `ModelResolver` — 各类 internal manager

**Cut** (从顶层暴露面剔除, 源码暂留待 dead-code 后续清):
- `AllProvidersFailedError`, `MaxRetriesExceededError` — 控制流异常不上 ABI
- `ContextBridge` 顶层暴露 cut (源码在 manifest.py 留, 子类型层暴露)
- `clear_cache` — 全局副作用反模式
- `get_model_resolver` — singleton getter 反模式
- `get_skill_type` — trivial helper, 用 `compile_skill().manifest.type` 替代

---

## 2. 命名: Commit-and-Push 步骤改名为 **Publish**

PM 在 Skill Studio 里完成 compile + predict + run 三关后, 按 "Publish" 按钮把 SKILL.md 推到 git 远端。

### 2.1 为什么改名

原本 user 称这步为 "save", 但跟"实时持久化到 SKILL.md"那个动作冲突 (PM 已经感觉每键都在 save)。

### 2.2 候选 + 推荐

| 候选 | 推荐? | 理由 |
|---|---|---|
| **Publish** | 🏆 推荐 | 贴 PM 心智模型 (像发文章/上线配置), 掩盖底层 git 复杂度 |
| Commit & Push | ❌ | 工程师思维, PM 认知负担 |
| Release Version | ❌ | 强调版本概念但当前还没建 versioning |
| Sync to Cloud / Team | ❌ | 暗示云端同步, 但实际是 git push |

---

## 3. PM 在 Skill Studio 的标准研发流程

```
┌─────────────────┐
│  WelcomeScreen  │  打开 app, 选 skill (类 VS Code 启动页, 已实现)
└────────┬────────┘
         ↓
┌─────────────────┐
│      编辑       │  实时持久化到 SKILL.md (像 IDE), 已实现
└────────┬────────┘
         ↓
┌─────────────────┐
│    Compile      │  compile_skill() 静态校验, 已实现
└────────┬────────┘
         ↓
┌─────────────────┐
│    Predict      │  ★ 待实施 ★ 模拟跑 (不烧 token), 推算业务逻辑流
└────────┬────────┘  实施: run_skill(mock_llm=True, ...) 见 PREDICT_SPEC.md
         ↓
┌─────────────────┐
│      Run        │  run_skill() 真 e2e 实测 (输入用文件), 部分实现需改造
└────────┬────────┘  改造: F1_T3 spec 重写, InputPlayground 表单→文件
         ↓
┌─────────────────┐
│    Publish      │  git commit + push (后端 git ops, 不归 SDK)
└─────────────────┘
```

### 3.1 关键设计原则

- **研发端覆盖生产端**: PM 工作流是 cloud / video-analysis 的超集, 满足研发端 = 自动满足生产端
- **每步前一步通过才能进下一步**: compile 不过禁 predict, predict 不过禁 run, run 不过禁 publish
- **输入用文件不用表单**: 测试输入是一个本地 JSON/YAML 文件, 后端 schema validate 后下发 (用 manifest.io.inputs Pydantic 校验, 不需要 SDK 暴露专门 API)

### 3.2 各步骤跟 SDK 13-export 的关系

| Step | SDK 用到 | 新增需求 |
|---|---|---|
| 编辑 | `serialize_skill` | 0 |
| Compile | `compile_skill, CompileResult, SkillCompilationError` | 0 |
| Predict | `run_skill (mock_llm=True), WorkflowResult, TracingCallback` | run_skill 加 mock_llm 参数 (不加新顶层 API) |
| Run | `run_skill, WorkflowResult, Callback 系列, GraphAgentError, SkillLoadError` | 0 (input 校验后端自己做) |
| Publish | 无 | 0 (后端 git ops) |

**13-export 完全够用, 0 新顶层 API**。

---

## 4. Predict 落地计划

详见 `docs/architecture/PREDICT_SPEC.md` (Gemini 起草, 2026-05-06)。

要点:
- **复用 `run_skill()`** 加参数 `mock_llm=True` (或 `provider=MockProvider()`)
- **不加顶层 `predict_skill` API**, 避免污染 13-export
- 实施时点: **v2 阶段** (v1-reset 后), 不在 PR #37 范围内
- spec 起草是"储备", 不立刻开工

---

## 5. 旧文档处置

| 文档 | 处置 | 说明 |
|---|---|---|
| `docs/architecture/F1_T3_INPUT_PLAYGROUND_SPEC.md` | **🔴 OBSOLETE** | 整篇 schema→表单设计, 跟"输入用文件"冲突, 顶部加 OBSOLETE banner 指向新 spec |
| `docs/architecture/STUDIO_FRONTEND_DEV_SPEC.md` | **🟡 部分更新** | §1.2 测试输入"自动生成表单"→"文件关联+验证"; Backlog 加 Predict + Publish |
| `docs/architecture/F3_T2_VIRTUAL_TRACE_SPEC.md` | **🟢 保留+澄清** | 是 DOM 滚动优化, **跟 Predict 完全无关**, 顶部加澄清段防混淆 |
| `docs/architecture/F2_T2_PHASE_FORM_SPEC.md` | **🟢 保留** | PhaseDrawer 双向绑定跟"IDE 实时持久化"理念一致 |

待新建:
- `docs/architecture/PREDICT_SPEC.md` (Gemini 起草中)
- `docs/architecture/F1_T3_FILE_INPUT_SPEC.md` (新 file-input spec, 替代旧 F1_T3)

---

## 6. 已完成 + 已锁定

到 2026-05-06 commit `03d0ae2` 为止:

- ✅ 删 `packages/graph-agent-engine/` 整包
- ✅ 删 14 lazy deprecated, 13 stable export 完整 ship
- ✅ 删 4 份 obsolete docs (R1/R2 决策报告 + 2 份 video-analysis migration runbook)
- ✅ Tauri T1 bootstrap (`apps/studio/tauri/`, cargo check 通过)
- ✅ root pytest 1058 collected (importlib mode + namespace_packages)
- ✅ CI: ruff / mypy / pytest-cov 全过 (剩 1 个 backend test CI 环境特有 fail, 已记 TD-001)

PR: <https://github.com/SevenX77/agent-harness/pull/37>

---

## 7. 此后规划范围 (脱本文档协议)

凡是这份文档**没**明确包含的范围 = 不在"实验阶段最后一次大决断"内。后续如果出现:

- 新功能 (比如 multi-turn conversation skill)
- 新 SDK API export 候选
- SkillManifest schema breaking change

需要走**正式审议流程** (RFC / 决策辩论), 不能 silent merge。

User 和主控 / a2 / a3 都按本文档行事, 直到下一次大决断显式覆盖。
