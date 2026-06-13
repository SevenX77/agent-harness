# Progress — Studio MVP1 + three-module

- **分支**:`feat/studio-mvp1-mainbased-2026-06-13`(从 `main`=#139 切,含三模块 adapter)
- **更新**:2026-06-13
- **基线**:`goal-charter.md`(目标/done/硬约束)+ `integration-plan.md`(以 main 为基的阶段)

## 当前阶段:Phase 0 — 工作区搭建 + Tauri computer-use 能力探针

### 已完成
- 新 worktree + 分支从 main(#139)切出,工作区干净。
- 章程 + 路线挪到 `docs/studio-mvp1-execution/`(脱离 temp scratch)。
- 全局 `/goal` 命令建好,指向本目录的稳定路径。

### Tauri + computer-use 探针发现(重要)
- **`cargo tauri dev` 裸二进制不可被 computer-use 授权**:进程 `skill-studio-tauri` 的 bundle id = "missing value",access 层按 NSRunningApplication/bundle 匹配不到 → **computer-use 必须驱动打包后的 `.app`**,不是 dev 模式。
- dev sidecar 用 `.venv` + 源码 backend(`cfg!(debug_assertions)`),所以 dev **不需要** download_runtime。
- **构建坑**:`beforeBuildCommand` 调 `python`(本机只有 `python3`/`.venv`)→ `build_vendor` 失败 exit 127。debug bundle 绕过办法:跳过 build_vendor(debug 用 .venv 不需要 vendored site-packages)。
- ✅ **探针通过(2026-06-13)**:打包 debug `.app`(`apps/studio/tauri/target/debug/bundle/macos/Skill Studio.app`,有 bundle id `com.sevenx.skill-studio`)→ computer-use `request_access` 成功(tier **full**)→ 截屏看到完整 Studio UI → 点击设置齿轮成功打开 Settings 面板。**see + click 双双验证,headline「computer-use 驱真桌面」路线可行。**
- 构建很快:warm cargo 缓存下 `cargo tauri build --debug` 19s 编译完。dmg 打包步骤报错可忽略(只要 .app)。
- ⚠️ **遗留**:该 debug bundle **后端不通**(Could not load skills / API Keys Network Error)——跳过了 build_vendor + debug sidecar 没连上。**真生命周期 e2e 需要一个后端可用的 .app**。

### 下一步(已纠正:探针够了,不要现在跑生命周期)
- ✅ computer-use 探针已达成目的(确认能驱动真 .app)。**这是现阶段唯一需要的桌面验证。**
- ⏸️ **生命周期 e2e(新建→编译→run→trace)= 验收闸,推迟到功能实现到位后再跑。** 现在跑只会撞已知桶 B 缺口(run 桩 / resume 501 / trace 孤儿 / copilot 直写),无新信息。"后端可用 .app + 全程走" 留到验收期。
- ➡️ **现在进入实现**:① 新 worktree 装依赖(`npm install` + `uv sync`);② Phase 1 前端嫁接 wave3 增量 + i18n(integration-plan §3 阶段1),带 owner 边界改造。
- 实现期验证 = 单元 + 单功能 smoke + 模块门禁;computer-use 只在"需要肉眼看某个刚做完的 UI/桌面行为"时按需用(那时才需要后端可用 .app)。

## 执行状态(2026-06-13 续)

- **范围已更正**:目标 = MVP1 设计 + 三模块接口设计**两套全部**(charter §2,提交 2cd92edc)。执行主体 = Claude 自写 + 自派 subagent/Workflow,跑到完成不停。
- **Phase 0 ✅**:新 worktree + 依赖装好(uv sync + npm install,exit 0)。
- **前端回归基线绿**(嫁接前):`tsc -b --noEmit` 干净 + vitest **54 文件 / 412 测试全过**。
- **前端回归基线绿**(嫁接前):tsc clean + vitest 412;**studio 后端基线绿**:pytest 479 passed。
- **Phase 1 前端嫁接 ✅ 完成**(8 批,commit `eeac8cb5`→`31bfec39`,44 前端文件):i18n 基础设施 / 加性超集 / native 集群(tauri 并集+多会话 copilot store+client Tauri 写)/ copilot 去 mock(用 gateway 真数据)/ settings 集群+token-trio / copilot-panel thinking_delta / Workspace run-predict-trace 接线 / welcome open-folder UX。
  - **全门禁绿**:tsc clean + vitest **415**(基线 412,净+3,零回归)+ vite build ✓ + lint clean。
  - **api/llm.ts + 所有 KEEP-MAIN 三模块正确文件零改动**(git diff 空)——没回退契约。计划留档:`docs/studio-mvp1-execution/phase1-graft-plan.md`。
  - 关键判断:wave3 多数文件 main #139 反而更对(RouteStatus 契约 / mode+target_skill 的 D8 正确 schema / 确定性 ID),只 graft 了真正前进的子集。
  - **FLAG 转后端**:6 态词汇收敛(Studio adapter `needs_setup`→gateway 6 态 `historical_ready`/`failed`)= 三模块 D6 后端+前端耦合任务。Phase 1 按计划保留 main 5 态,待后端 adapter 收敛后再翻前端枚举 + 对应 KEEP-MAIN 文件。

## 下一步:Phase 3 桶 B 后端(三模块全部实现)

优先级:① run 路径打通(engine↔studio 握手 3 个 studio 侧 P0,直接关系生命周期 run)② 6 态收敛(配 Phase 1)③ D10 resume + RuntimeStateStore(lease/heartbeat/fencing)④ Rust native-fs 唯一写者(D10/D12)+ RuntimeGate 降级 ⑤ copilot 安全写/dispatch/@mention/冷启动 ⑥ TracePanel 挂载 ⑦ llm_* 下沉 gateway。
完成后:出后端可用 .app → computer-use 走完整生命周期验收。

### 硬约束提醒(详见 goal-charter.md §5)
仅新分支、永不碰 main;密钥永不打印/提交;Studio 只渲染 gateway 事实;e2e 凭证用 `STUDIO_LLM_CREDENTIALS_PATH` 隔离不碰用户真库;LLM 主用第三方+DeepSeek+ARK、其他官方 fallback。
