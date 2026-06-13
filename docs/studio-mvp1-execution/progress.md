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
- 正在构建 debug `.app` 以验证 see+click(后台)。

### 下一步
1. 验证 computer-use 在 debug `.app` 上能 see+click。
2. 据此定 e2e 驱动方案(computer-use 驱真 .app vs 混合);注意:若每次 e2e 都要打包 .app,headline 经济性需重估。
3. 给新 worktree 装依赖(`npm install` + `uv sync`)做正式活。
4. 进 Phase 1:嫁接 wave3 前端增量 + i18n(见 integration-plan §3 阶段1)。

### 硬约束提醒(详见 goal-charter.md §5)
仅新分支、永不碰 main;密钥永不打印/提交;Studio 只渲染 gateway 事实;e2e 凭证用 `STUDIO_LLM_CREDENTIALS_PATH` 隔离不碰用户真库;LLM 主用第三方+DeepSeek+ARK、其他官方 fallback。
