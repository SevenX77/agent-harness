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
- `ContextBridge` — **从顶层 13-export 剔除**, 但允许从 `graph_agent.core.manifest` 子模块带 ascendence 引用 (跟其他子类型一样)
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
│    Compile      │  ⚙️ 自动 (无按钮) — compile_skill() 在编辑过程中实时跑
└────────┬────────┘  lint SKILL.md 自身合规, 错误实时高亮
         ↓
┌─────────────────┐
│  选 input 文件   │  PM 选本地 JSON/YAML 文件作为测试输入
└────────┬────────┘  ⚙️ 选完自动 Validate 一次 (POST /api/skills/{id}/validate_input)
         ↓          失败直接报错 (a1 commit dcd81ac, 见 F1_T3_FILE_INPUT_SPEC.md)
┌─────────────────┐
│ Predict (V2 规划) │  按钮 — ★ V2 储备 ★ 模拟跑 (不烧 token), 推算业务逻辑流
└────────┬────────┘  ⚙️ 点击前自动 Validate 一次, 失败阻塞
         ↓          实施: run_skill(mock_llm=True, ...) 见 PREDICT_SPEC.md
         ↓          (V1 阶段不实施, V1 路径直接选完 input 文件就 Run)
┌─────────────────┐
│      Run        │  按钮 — run_skill() 真 e2e 实测
└────────┬────────┘  ⚙️ 点击前自动 Validate 一次, 失败阻塞
         ↓
┌─────────────────┐
│    Publish      │  按钮 — git commit + push (后端 git ops, 不归 SDK)
└─────────────────┘

⚙️ = 自动后台校验 (无 PM 按钮):
  - Compile: 编辑过程中实时跑, 校验 SKILL.md 自身
  - Validate: 3 个触发点 — 上传 input 文件后 / 点 Predict 前 / 点 Run 前
              按 io.inputs schema 校验文件内容; 失败直接报错或阻塞按钮
              backend Service `services/validator.py` 提供, 3 个触发点共用
```

### 3.1 关键设计原则

- **研发端 PM 工作流 = 生产端所需 API 的超集 (仅 API 设计层面, 跟部署架构无关)**:
  PM 在 Skill Studio 里要做的事 (编辑 / Compile / Predict / Run / Publish + 看 trace + metrics + log) 涵盖了 cloud / video-analysis 等生产端实际跑 LLM workflow 时所需的全部 API (生产端只用 `run_skill` + `WorkflowResult` + Callback 几个,是研发端的真子集)。所以 SDK 13-export 表面**只按 PM 工作流推导**就够,生产端自动覆盖,不需要单独审。
  ⚠️ **这条原则只管 API 表面,不管部署形态**:
  - 研发端 (Skill Studio) 永远是 **Tauri Local-First 桌面应用** (FastAPI sidecar 跟前端同机, 见 `TAURI_KICKOFF_PLAN.md` + `LOCAL_FIRST_CLOUD_READY.md`)
  - 生产端 (agent-harness-cloud) 是**独立仓库下游消费者**, 部署到 Cloud (见 `REPO_SPLIT_AND_SDK_PLAN.md` §6 + `CLOUD_READINESS_AUDIT.md`), 不复用 Studio backend
  - 两者部署**完全独立**, 切不可把"API 覆盖原则"误用为"部署架构覆盖原则"
- **PM 可点击的按钮只有 4 个**: Predict (V2) / Run / Publish + 选 input 文件的文件选择对话框。**没有 Compile 按钮、没有 Validate 按钮**——这两个都是后台自动跑的检查。
- **自动校验 (Compile / Validate) 跟按钮门禁的关系**:
  - **Compile 错** → 编辑器实时高亮 + 阻塞所有后续按钮 (Predict / Run / Publish 全灰)
  - **Validate 错** → 在三个触发点都直接报错:
    - 上传文件后立即报 (Schema 不匹配, 字段缺失等)
    - 点 Predict 时自动复跑一次, 失败阻塞 Predict (V2 阶段)
    - 点 Run 时自动复跑一次, 失败阻塞 Run
  - **Run 失败** → Publish 按钮灰 (V1 + V2)
- **后端 API 必须解耦无状态**:
  后端**不**维护"PM 是否已经跑过 Validate"这种状态; Run / Predict 内部独立调用 `services/validator.py` Service 做前置校验 (RESTful 无状态防穿透——PM 用 curl 绕过前端直接调 Run 也校验; 见 F1_T3_FILE_INPUT_SPEC.md §4 Task 1)。standalone `/api/skills/{id}/validate_input` endpoint 只是给前端 "选完文件立即报错" 这个 UX 触发点用的快路径,backend 内部 Predict / Run 不依赖它已经被前端调过。
- **输入用文件不用表单**: 测试输入是一个本地 JSON/YAML 文件, 后端按 manifest.io.inputs schema 校验后下发。在 Tauri 桌面形态下后端可以直接接受**本地文件路径**(前后端同机),不用走 multipart 上传。生产端形态下不复用 Studio backend, 不存在跨机文件传输问题。
- **V1 阶段 PM 实际操作步骤**: 打开 app → 选 skill → 编辑 (Compile 后台自动跑) → 选 input 文件 (Validate 后台自动跑) → 点 Run (Run 内部再自动 Validate 一次) → 点 Publish。Predict 按钮 V2 才出现。

### 3.2 各步骤跟 SDK 13-export 的关系

| Step | 类型 | SDK 用到 | 新增需求 |
|---|---|---|---|
| 编辑 | PM action | `serialize_skill` | 0 |
| **Compile** | ⚙️ 自动 (无按钮) | `compile_skill`, `CompileResult`, `SkillCompilationError` | 0 |
| 选 input 文件 | PM action | — (走 Tauri `dialog.open()`) | 0 |
| **Validate** | ⚙️ 自动 (无按钮, 3 触发点) | `SkillManifest.io.inputs` (反射 Pydantic), `compile_skill` | 0 (Studio backend 直接从 `graph_agent.core.manifest` 子模块 import, 实施在 commit `dcd81ac` 的 `services/validator.py`) |
| Predict (V2) | 按钮 | `run_skill(mock_llm=True)`, `WorkflowResult`, `TracingCallback` | run_skill 加 mock_llm 参数 (不加新顶层 API) |
| Run | 按钮 | `run_skill`, `WorkflowResult`, `Callback` 系列, `GraphAgentError`, `SkillLoadError` | 0 (Run 内部隐含调一次 Validate Service) |
| Publish | 按钮 | 无 | 0 (后端 git ops) |

**13-export 完全够用, 0 新顶层 API**。

---

## 4. Predict 落地计划

详见 `docs/architecture/PREDICT_SPEC.md` (Gemini 起草, 2026-05-06)。

要点:
- **复用 `run_skill()`** 加参数 `mock_llm: bool | dict[str, Any]` (单一参数, 不暴露 `MockProvider` 顶层 class)
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

已随本次决策同时归档 (跟本文档同 commit 系列 ship):
- ✅ `docs/architecture/PREDICT_SPEC.md` (Gemini 起草, V2 储备)
- ✅ `docs/architecture/F1_T3_FILE_INPUT_SPEC.md` (Gemini 起草, V1 实施)

---

## 6. 已完成 + 已锁定

到 2026-05-06 (commit `dcd81ac` 系列) 为止:

- ✅ 删 `packages/graph-agent-engine/` 整包 (commit `c3de7d4`)
- ✅ 删 14 lazy deprecated, 13 stable export 完整 ship (commit `c3de7d4`)
- ✅ 删 4 份 obsolete docs (R1/R2 决策报告 + 2 份 video-analysis migration runbook) (commit `c3de7d4`)
- ✅ Tauri T1 bootstrap (`apps/studio/tauri/`, cargo check 通过) (commit `d15a1dc`)
- ✅ root pytest 1058 collected (importlib mode + namespace_packages) (commit `53d4c8a`)
- ✅ ruff lint 全 clean + mypy strict no_implicit_reexport 修 (commits `6531b8c` + `0297aa2`)
- ✅ pytest-cov + coverage 进 root deps (commit `03d0ae2`)
- ✅ POST_PLAN_C + PREDICT_SPEC + 旧文档 OBSOLETE 标记 + tech debt 登记 (commit `0388d17`)
- ✅ F1_T3_FILE_INPUT_SPEC.md (Gemini 起草) (commit `a99d2ad`)
- ✅ F1_T3 Task 1: backend `/api/skills/{id}/validate_input` API (a1 codex 实施, commit `dcd81ac`)
- ✅ CI: ruff / mypy / pytest-cov / pytest 全过 (剩 1 个 backend test 偶发 CI flaky, 已记 TD-S1)

PR: <https://github.com/SevenX77/agent-harness/pull/37>

---

## 7. 此后规划范围 (脱本文档协议)

凡是这份文档**没**明确包含的范围 = 不在"实验阶段最后一次大决断"内。后续如果出现:

- 新功能 (比如 multi-turn conversation skill)
- 新 SDK API export 候选
- SkillManifest schema breaking change

需要走**正式审议流程** (RFC / 决策辩论), 不能 silent merge。

User 和主控 / a2 / a3 都按本文档行事, 直到下一次大决断显式覆盖。
