# Studio MVP1 + Three-Module —— 目标章程(执行基线)2026-06-13

> 配套文档:集成路线见 `temp/studio-mvp1-integration-plan-corrected-2026-06-13.md`(以 main 为基的阶段划分)。
> 本文定义:**目标 / 完成判据 / e2e 分层 / 硬约束 / 凭证处理 / 自主执行规则**。

---

## 1. 目标 / 验证 / 最高决策原则(PM 2026-06-14 重申,铁律)

> 这三条是本工程的北极星。任何"要不要停 / 要不要碰某文件 / 该怎么做"的疑问,**唯一裁判是设计文档本身**(下方三模块 + MVP1),不是本章程、不是 §5.6、不是任何我自造的中间规则。我自己写的执行文档(本 charter / progress)只是设计文档的有损代理,与设计文档冲突时**以设计文档为准**。

1. **目标**:完整实现 **MVP1 设计 + 三模块接口设计** 两套(不挑不减,设计写的都做,只有设计自己登记的延期项才延期)。在新 worktree + 新分支(从 `main`=#139 切,全程不碰 main)上做。
2. **如何验证**:**e2e 测试——computer-use 鼠标模拟真实用户操作,把完整生命周期(设计→编译→debug→predict→run→看 trace→resume→发布)真跑通、肉眼无明显 bug。** 模块门禁/单测绿是必要不充分;**没真鼠标跑过 = 还没算分**。
3. **最高决策原则**:**MVP1 + 三模块设计文档**(下列四个权威根)。遇到任何决策,先回设计文档找答案;设计文档答了就照做,不停、不自造理由。**两套冲突处:以三模块接口设计为准(三模块 > MVP1)。**

### 权威设计文档(PM 待确认其完整性)
- **三模块接口设计**(D1–D12,跨模块契约):[`docs/mvp1-three-module-interface-design-and-changes-2026-06-11/`](../mvp1-three-module-interface-design-and-changes-2026-06-11/) — 入口 `01-design.md` + `README.md`
- **Engine MVP1**:[`docs/engine/mvp1/`](../engine/mvp1/) — 入口 `INDEX.md` / `README.md` / `00-architecture-overview.md`
- **Gateway MVP1**:[`docs/graph-agent-gateway/mvp1/`](../graph-agent-gateway/mvp1/) — 入口 `README.md` / `DESIGN_UNITS_INDEX.md`
- **Studio MVP1**:[`docs/studio/mvp1/`](../studio/mvp1/) — 入口 `README.md` / `DESIGN_UNITS_INDEX.md`

## 2. 完成判据(done-set,画死终点线)

> **范围 = MVP1 设计 + 三模块接口设计,两套全部实现,不挑不减**:① MVP1 设计(engine + gateway + studio 各自 `mvp1-alignment` 的全部 FROZEN capability)② 三模块接口设计 `docs/mvp1-three-module-interface-design-and-changes-2026-06-11`(D1–D12 全部:ArtifactRef/run_artifact、存储三线+成品库、冻结产物 run-by-version、Engine↔Gateway SPI 倒置、凭证/route/fallback、6态、golden headless、GRAPH parse/serialize、**D10 resume+RuntimeStateStore lease/fencing**、EventEnvelope、**D12 Rust native-fs 唯一写者**)。冲突处 three-module 赢。**设计里写的都做,只有设计自己登记的延期项才延期。**

**达成 = 下面全部满足:**

1. **主验收(headline)**:用 computer-use 驱动**真 Tauri 桌面构建**,把用户生命周期 **设计 → 编译 → debug → predict → run → 看 trace → 调试(resume)→ 发布** 端到端走通,无明显 bug。载荷用 story-deconstruction-v2 **跑一章** 或单个 subgraph(只为串通生命周期、暴露问题,不真做解构)。
2. **owner 边界成立**:三模块以 three-module 设计为准;Studio 只渲染 gateway 返回的事实,不自算 fallback/materialize/6态;无 `registry_snapshot` owner path;无 `run_skill/predict_skill` 隐藏 runtime。
3. **桶 B 前向工作落地**:D10/D12 Rust native-fs 唯一写者 + RuntimeGate 降级启动;D10 resume + RuntimeStateStore(lease/heartbeat/fencing);copilot 安全写/dispatch/@mention/冷启动恢复;TracePanel 挂载 + edge blackboard;`llm_state_projection`/`llm_role_materializer`/`llm_import_drafts` 下沉 gateway。
4. **底线(基础流程,不是 headline 但必须有)**:单元测试 + 单功能 smoke + 设计强制的错误/并发/传输测试(§4 那些 etag/lease/fencing/传输错误)+ owner 边界静态守卫,全绿;模块门禁全绿(Engine/Gateway/Studio **分进程** pytest + 前端 tsc/lint + `cargo test`)。

**明确不在范围(设计自身登记的延期项,保持延期,不做)**:3 个硬多机错误(时钟漂移/网络分区/跨节点配额,只留接口位)、`remote_vault`(仅枚举)、audit/intent-drift(501 scaffold,非 MVP1)。copilot **真功能在范围内**(安全写 / @mention / 冷启动,见桶B §3);旧 `/api/copilot` dispatch 按设计 = 非-MVP1 scaffold、copilot 走 WS 活路径。**这些延期项之外,设计写的全做。**

## 3. e2e 分层(主验收 + 底线)

| 层 | 覆盖 | 工具 | 角色 |
|---|---|---|---|
| ① 生命周期主脊 | 全部 happy-path 用户功能 + 三模块 adapter 端到端 + 真 native-fs/RuntimeGate | **computer-use 驱动真 Tauri 桌面构建** | 🎯 headline |
| ② skill 载荷 | 引擎机制(子图/iterate/agent-loop/golden/resume) | story-deconstruction-v2 跑一章 / 单 subgraph | 🎯 headline 的载荷 |
| ③ 错误/并发/传输 | §4 强制错误族 + 多 worker + HTTP loopback | 后端 pytest(复用 #139 已有 harness) | 🧱 底线 |
| ④ owner 边界守卫 | 无自算/无旧路 | grep guard + 契约测试 | 🧱 底线 |
| ⑤ 单元 + 单功能 smoke | 每个改动的功能 | pytest / vitest / cargo test | 🧱 底线 |
| ⑥(可选/将来) | 确定性桌面回归 | tauri-driver + xvfb(Linux CI) | 🔁 later |

## 4. 凭证 / API key 处理

- **来源**:repo 根 `.env`(gitignore,含 Anthropic/OpenAI/DeepSeek/Gemini/qiniu/ARK/OpenRouter 等真 key);Studio 真凭证库 `~/Library/Application Support/AgentStudio/llm/llm_credentials.json` 已有数据。
- **Provider 优先级(PM 定)**:主用 **第三方聚合(七牛 `QINIE_*` / 接口 `JIEKOU_*` / `OPENROUTER_*`)+ DeepSeek 官方(`DEEPSEEK_*`)+ ARK 官方(火山方舟 `ARK_API_KEY`)**;**其他官方(Anthropic/OpenAI/Gemini)只作 fallback 备用**。配 e2e 角色/路线时按此排 `fallback_chain`。
- **e2e 凭证隔离(铁律)**:e2e 用 `STUDIO_LLM_CREDENTIALS_PATH`(`llm_paths.py` 已支持的 env override)指向**隔离的临时凭证文件**,从 `.env` 播种,**绝不覆盖/污染用户真凭证库**。
- **成本**:载荷只跑一章/单子图,真 LLM 成本有界;不无谓循环真 LLM。

## 5. 硬约束(绝对不能违反)

### 5.1 Git / 分支
- 全程在**新 worktree + 新分支**;**可以 commit 到新分支(鼓励小步提交)**;唯一禁区是 main——**永不 commit/push/force-push main、永不把新分支合进 main**;暂存按文件名(**不用 `git add .`/`-A`**);不 `--no-verify`;不 amend 已发布提交。

### 5.2 密钥 / 数据
- **永不打印/提交/外传** `.env`、`llm_credentials.json` 的**值**;永不把 key 塞进 LLM prompt 或外部服务;`.env` 保持 gitignore,绝不 stage;e2e 凭证走隔离路径,不碰用户真库(见 §4)。

### 5.3 设计不变量(违反 = 实现了错的东西)
- 冲突处 **three-module 赢**;**Studio 只渲染 gateway 事实**,不自算 fallback/materialize/6态;无 `registry_snapshot` owner path;无 `run_skill/predict_skill` 隐藏 runtime;adapter 是唯一跨模块路径。

### 5.4 范围 / 忠实
- 只做服务目标的工作;**不顺手重构无关代码**;忠实实现设计,改进点写报告不静默动手;不动 FROZEN 设计文档(除非走 exemption/哈希锁流程)、不无故改 `uv.lock`。

### 5.5 诚实 / 门禁
- **永不伪造绿**:没真跑过不报通过;失败如实报。每次 commit 前过 lint + typecheck + 相关测试(`/finish` 流);声称"目标达成"前必须真把生命周期走一遍、观察到无明显 bug。

### 5.6 合法中断条件(界定"不中途停"的边界)
仅在以下三种**才**停下问:① 真正无法自解的硬 blocker(工具链装不上 / 凭证确实失效);② 不可逆/破坏性动作且意图不明;③ 文档与代码都答不了的业务/范围歧义。**其余一律自主解决、不停。**

## 6. 自主执行规则

- **执行主体**:Claude 自己写代码 + 自己派 subagent / Workflow 编排;能自决的不外包给 PM。
- **跑到完成不停**:Phase 0 → 验收全程自主,**只在 §5.6 三种硬 blocker 才停**;里程碑汇报但不 halt。
- **持久进度**:程序规模大(跨多会话/会被 compaction 截断),进度必须落盘(plan + `progress.md`),靠文件恢复,不靠对话记忆。
- **小批次**:大分支内部仍拆小批次,每批独立可验、可回滚;每批走 RED→GREEN。
- **桶 B 的 e2e 先 RED**:resume/native-fs/安全写的 e2e 先写成红,随实现转绿。
- **报告节奏**:积累问题批量报,不一步一问;阶段里程碑达成时汇报一次。

## 7. 其他已识别的遗漏/风险(开工前心里有数)

1. **Tauri 构建是主验收的前置**:要 computer-use 驱动真桌面,得先把真 app 构建出来——需 Rust/cargo + Tauri CLI + vendor/runtime 资源(`download_runtime.js` + `build_vendor.py`);且早前发现的 dev-bootstrap 缺口(`download_runtime.js` 不在 `beforeDevCommand`)要补。构建失败 = 主验收跑不了,**优先级最高的前置**。
2. **dev 需多进程**:Vite + 后端 uvicorn + tauri,需后台进程协调(Bash run_in_background)。
3. **computer-use 要真显示**:驱动真 app 时会占用你的屏幕;无显示环境跑不了主验收(那时退化到 tauri-driver/xvfb 或 cargo+组件测)。
4. **程序规模**:这不是一次不间断冲刺,是跨多会话的工程;"自主"指会话内不中途问、跨会话靠落盘续跑。
