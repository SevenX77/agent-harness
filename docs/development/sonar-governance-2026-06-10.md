# SonarCloud main 质量门治理记录（2026-06-10）

> 目的：留痕本次质量门修复中的全部人工判定（hotspot 标记 / CodeQL dismiss），防止治理决定变黑箱。
> SonarCloud UI 的标记理由检索不便，多 agent 协作下以本文为可追溯权威记录。

## 1. 背景

main @ `89cf12eb`（engine Wave 4A 三个 WS 合入后）SonarCloud 质量门 ERROR，四项失败：
安全热点 0% 已审查 / 安全评级 D / 可靠性评级 C / 新代码重复率 4.0%。

根因不是单次提交，而是三因素叠加：

1. **扫描范围错配**：仓库走 Automatic Analysis（round-30 PR #102 移除了 CI scanner），该模式**不读** `sonar-project.properties`，其 source/test 划分从未生效——测试文件、夹具 skill 包、诊断脚本一直按生产代码评分。
2. **新代码周期 = previous_version（起点 2026-05-29）**：gateway mvp1 + studio 批次 + engine 多波次数万行全算"新代码"，噪声被一次性聚合。
3. **少量真实源码缺陷**（约 15 处）。

## 2. 修复（三个 PR，均已合入 main）

| PR | 内容 |
|---|---|
| #129 `bc669fa1` | `.sonarcloud.properties` 接管扫描范围：测试归类 test scope（归类非排除）、排除 `code-diagnostics/`、`skills/`+测试排除出重复检测；删除失效的 `sonar-project.properties`；守卫测试同步改锁新配置 |
| #130 `385f483f` | loader 路径注入收口（normpath+前缀校验）、copilot 进程级随机 salt、workflow 最小权限、scorecard 守卫测试同步 |
| #131 `2f7128c3` | asyncio task 持引用、死逻辑化简、正则优先级显式化、前端 localeCompare/randomUUID |

## 3. 人工判定记录

### 3.1 CodeQL alert #155 — dismissed (false positive)

`py/path-injection @ loader.py _validate_phase_dir`：candidate 已经 `os.path.normpath` 归一化并对
phases_root 做前缀校验后才发生任何文件系统访问；越界走 `_graph_fatal`（必然 raise，CodeQL 推不出
NoReturn 所以认为污点流继续）。判定：误报。

### 3.2 安全热点 34 个 — 全部 REVIEWED/SAFE（2026-06-10，经由 API 批量标记）

| 规则 | 数量 | 位置 | SAFE 理由 |
|---|---|---|---|
| `githubactions:S7637`（action 未 pin SHA） | 6 | ci.yml ×5、scorecard.yml | 全部为可信发布方（actions/、astral-sh、ossf）主版本 tag 引用；SHA pinning 列为后续供应链加固项，不作质量门阻塞 |
| `S5852`（可回溯正则 ReDoS） | 25 | engine 解析工具（md2json/schema_engine/dynamic_schema/md_to_json）、studio skills.py、前端 welcome/yamlAst/build-nodes 等 | 输入均为本地开发者/agent 自著的 skill 内容或桌面应用（Tauri 单用户）UI 本地字符串，无不可信远程输入暴露面；最坏情形为拖慢自身编译 |
| `typescript:S2245`（Math.random） | 2 | components/ui/sidebar.tsx、uikit sidebar.tsx（均 :597） | shadcn/ui vendored 组件的 skeleton 装饰性随机宽度，非密码学用途；改写会制造上游 drift |
| `javascript:S4036`（PATH 可写目录） | 1 | tauri/scripts/download_runtime.js | 开发机构建期工具脚本，非交付运行时代码 |

### 3.3 后续加固项（非阻塞，择机做）

- workflow actions SHA pinning（S7637 的根治），可配 dependabot 的 SHA 更新模式
- `_graph_fatal` 标注 `typing.NoReturn`，让 CodeQL/类型检查理解其控制流，避免同类误报复发

## 4. 结果

main 质量门 **OK**（2026-06-10）：可靠性 A / 安全 A / 可维护性 A / 重复率 1.8% / 热点审查 100%。

## 5. 长期价值约定

扫描配置收口后，质量门反馈恢复信噪比。后续原则：
- **能用一行代码消除的告警，优先于人工标记**（标记是永久重复债）
- 测试惯例告警靠 **归类**（test scope）解决，不靠逐个 accept
- 静态分析误判标 **false-positive**，真问题但接受标 **accepted**，语义不可混用
- 新增人工标记必须同步追加到本文
