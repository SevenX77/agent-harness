# Implementation Plan

> 这份任务清单是 `design.md` 的执行版本。更详细的 agent 可执行步骤见 `docs/superpowers/plans/2026-04-22-graph-agent-studio.md`（Superpowers 风格）。任务之间的依赖关系遵循 P0 → P1 档位 A → P1.5 gate 的顺序，每个 Phase 内允许并行的项已用 `(P)` 标注。

## Phase 0: 引擎地基

- [ ] 1. 定义 `SkillManifest` Pydantic v2 契约 (P)
  - 在 `src/core/graph_agent/core/manifest.py` 新建，含 `schema_version`/`name`/`description`/`type`/`io`/`phases`/`sub_skills`/`context_mapping`
  - 子模型：`PhaseConfig`、`Step`、`IoDeclaration`、`SubSkillSpec`；discriminated union on `type: graph|code`
  - 新字段：`Step.when`、`Step.skip_if`、`PhaseConfig.model_override`
  - 单测：5 个现有业务 skill 用 strict_mode=False 全通过
  - _Requirements: 1, 10_

- [ ] 2. 实现 `serialize_skill(manifest)` AST 反向序列化 (P)
  - frontmatter 走 ruamel.yaml round-trip 模式
  - body 自写 formatter：缩进 2、属性 alphabetical、EOF 换行
  - 单测：所有现有 skill parse → serialize → parse 幂等
  - 公开 API 导出到 `graph_agent/__init__.py`
  - _Requirements: 2_

- [ ] 3. 改造 4 处 SKILL.md 校验到共享 `SkillManifest`
- [ ] 3.1 `core/parser.py` 改为 YAML+XML → dict → `SkillManifest.model_validate()` (P)
  - 保留 YAML/XML 底层解析，只把 dict 喂给 Manifest
  - _Requirements: 1_
- [ ] 3.2 `core/loader.py` 引用 `SkillManifest`，删除重复校验
  - 保留 import 兜底逻辑，只在最终装配点依赖 Manifest
  - _Requirements: 1_
- [ ] 3.3 `core/compiler.py` 基于 `SkillManifest` 跑 `rules.yaml` 的业务规则
  - 结构错误归 Manifest 处理，规则错误归 compiler
  - _Requirements: 1_
- [ ] 3.4 `deerflow/skills/parser.py` 改为引用 `SkillManifest` 或删除（整合到 core/parser.py）
  - 优先删除，避免维护两套
  - _Requirements: 1_

- [ ] 4. CallbackEvent 类型化
- [ ] 4.1 新建 `callbacks/events.py`：Pydantic discriminated union 覆盖 14 种事件
  - 每种事件一个 payload 子类，`schema_version: Literal["1.0"]`
  - _Requirements: 3_
- [ ] 4.2 现有 `callbacks/` 的 14 个钩子改为发送类型化事件 (P)
  - 不改 DeerFlow 源码；在外层 callback 桥接层转换
  - _Requirements: 3_
- [ ] 4.3 新增 `TracingCallback` 落盘 `tracing.jsonl`（每行 `model_dump_json()`）
  - _Requirements: 3_

- [ ] 5. Prompt Capture 埋点
  - 在 DeerFlow `create_agent()` 外层包一层 LLM 调用拦截
  - 发 `PromptCapturedEvent`，含 `template_source`、`variables`、`final_prompt`、`loop_index`、`llm_role`、`resolved_model`
  - _Requirements: 4_

- [ ] 6. `Step.when` / `Step.skip_if` simpleeval 求值器
  - 白名单：`len/str/int/bool/in/and/or/not`，禁用所有 dunder
  - 上下文变量白名单：`context`、`working_memory`、`current_phase_metrics`
  - 求值失败抛 `WhenExpressionError`，不静默跳过
  - 单测：模糊测试 `__import__` / `getattr` 等必须被拒绝
  - _Requirements: 10_

- [ ] 7. `ModelResolver` fallback 扩展
- [ ] 7.1 主 provider 失败自动切同级代码模型，emit `LLMFallbackEvent` (P)
  - Claude Sonnet ↔ GPT-4o 配对在 `llm_roles.yaml` 声明
  - _Requirements: 11_
- [ ] 7.2 全部失败时返回 `FallbackExhaustedError`
  - Studio 端捕获后进入只读模式
  - _Requirements: 11_

- [ ] 8. 熔断阈值参数化
  - 30 分钟窗口、30 次错误阈值从 `llm_roles.yaml` 读取，不写死
  - _Requirements: 11_

## Phase 1: Studio 档位 A（Lint + Run + Open CLI + 只读可视化）

- [ ] 9. 新建 `studio/` 子项目骨架
  - `studio/server/`（FastAPI）、`studio/web/`（Vite + React + TS）
  - README 注明启动方式
  - _Requirements: 5, 6, 7, 8_

- [ ] 10. Studio Server REST API
- [ ] 10.1 `GET /api/skills` 扫描 `skills/` 返回 `SkillSummary[]` (P)
  - _Requirements: 5, 6, 7, 8_
- [ ] 10.2 `GET /api/skills/{id}` 返回 `SkillDetail{manifest, file_paths, has_golden}` (P)
  - _Requirements: 5, 6, 7, 8_
- [ ] 10.3 `POST /api/skills/{id}/lint` 调用 `compile_skill()`，返回 `LintResult` (P)
  - _Requirements: 5_
- [ ] 10.4 `POST /api/skills/{id}/run` spawn subprocess 跑 `run_skill`，返回 `run_id`
  - 子进程独立，避免阻塞主进程
  - _Requirements: 6_
- [ ] 10.5 `GET /api/skills/{id}/trace/{run_id}` 读 `tracing.jsonl` 返回全量事件 (P)
  - _Requirements: 6_

- [ ] 11. Studio Server WebSocket
- [ ] 11.1 `/ws/run/{run_id}` 推送 `CallbackEvent` 流
  - 用 asyncio Queue + 单 consumer 保序
  - _Requirements: 6_
- [ ] 11.2 `/ws/terminal/{term_id}` 字节双向透传
  - 客户端键入 → pty stdin；pty stdout → 客户端
  - _Requirements: 7_

- [ ] 12. `TerminalManager` + pty 管理
  - 每个 session 独立 `ptyprocess`，cwd=skill 目录，exec=`claude`
  - TTL 1 小时，到期 reap
  - 并发上限 3/PM
  - 环境变量注入 `SKILL_DIR`、`STUDIO_SESSION_ID`
  - _Requirements: 7_

- [ ] 13. FileWatcher
  - 用 `watchdog` 监听 `skills/{id}/` 目录
  - SKILL.md 变更 → WebSocket broadcast `skill.changed` → 前端 toast
  - _Requirements: 7_

- [ ] 14. 前端：Skill 列表页 (P)
  - 路由 `/`：调用 `/api/skills` 渲染卡片
  - 每个 skill 卡片有 [Lint] [Run] [Open CLI] 三按钮
  - _Requirements: 5, 6, 7_

- [ ] 15. 前端：Skill 详情页
- [ ] 15.1 React Flow 渲染 phase 图（只读，Dagre auto-layout） (P)
  - 节点含 name/tier/tools 简要；边为 phase 顺序 + retry_target
  - _Requirements: 8_
- [ ] 15.2 点击节点展开 Detail 面板 (P)
  - 显示 system_prompt / user_prompt / output_schema / sub_skills / validator
  - 用只读 Monaco 渲染文本
  - _Requirements: 8_
- [ ] 15.3 Lint 面板（Drawer 形式） (P)
  - 成功：绿色 "Lint passed" + phase 简表
  - 失败：错误列表，每条可点击跳转到 Monaco 对应行
  - _Requirements: 5_

- [ ] 16. 前端：Run 面板 + Trace Timeline
- [ ] 16.1 Input 选择器：下拉列 golden / 粘贴 JSON (P)
  - _Requirements: 6_
- [ ] 16.2 Trace Timeline 订阅 WebSocket 实时追加事件 (P)
  - 每个事件卡片显示 event_type / phase / elapsed / payload 摘要
  - 点击展开完整 payload
  - _Requirements: 6_
- [ ] 16.3 Prompt Inspector（弹窗）展示三元组（模板 / 变量 / 最终） (P)
  - 点击 `prompt_captured` 事件打开
  - 三个 tab，可复制
  - _Requirements: 4, 6_

- [ ] 17. 前端：Terminal 面板
  - 基于 xterm.js，WebSocket 双向透传
  - 适配深色主题 + 字体
  - 连接断开提示重连
  - _Requirements: 7_

- [ ] 18. Studio Security hardening
- [ ] 18.1 PTY cwd 白名单强校验（防止 `../` 越界） (P)
  - _Requirements: 7_
- [ ] 18.2 默认只监听 `127.0.0.1`，远程部署需 `--host` 显式
  - README 大字警告
  - _Requirements: 7_
- [ ] 18.3 simpleeval 模糊测试 CI
  - _Requirements: 10_

- [ ] 19. E2E/UI Playwright 测试
- [ ] 19.1 Lint 成功/失败两态渲染 (P)
- [ ] 19.2 Run 完整跑一个 echo skill，事件顺序正确 (P)
- [ ] 19.3 Terminal 启动 + `pwd` 回显 skill 目录 (P)
  - _Requirements: 5, 6, 7_

- [ ] 20. 只读模式（Copilot Fallback 兜底）
  - 当 `ModelResolver` 抛 `FallbackExhaustedError`，Studio 全局 banner "Copilot 不可用"
  - Run 按钮禁用，Lint / Open CLI 仍可用
  - _Requirements: 11_

## Phase 1.5: 用户验证关卡（Hard Gate）

- [ ] 21. 招募 2-3 个真实 PM 做 2 周 dogfood
  - 前置条件：Phase 1 交付
  - 不允许在 P1.5 结束前启动 P2 任何工作
  - _Requirements: 9_

- [ ] 22. 收集指标
- [ ] 22.1 PM 自主完成一次 skill 改动的成功率（计数）
- [ ] 22.2 Claude Code CLI 生成的 SKILL.md 首次过 Lint 率
- [ ] 22.3 PM 报告的 UX 摩擦点 top 3（定性）
  - _Requirements: 9_

- [ ] 23. 决定 P2 方向（三选一，不并行）
  - (a) 补强 Trace 可视化 / (b) 启动内嵌 Copilot / (c) 启动画布 Topology 编辑
  - 输出：P2 spec 启动 memo
  - _Requirements: 9_

## Phase 2+: 按 P1.5 反馈分支（本 spec 不展开）

> 这些条目仅作为占位，正式 spec 在 P1.5 完成后启动

- 选项 A: Trace 可视化增强（Working Memory diff / Subskill 嵌套视图 / Golden 回归）
- 选项 B: 内嵌 Copilot SDK 集成（Dry-run 自愈 / diff 预览 / AST patch）
- 选项 C: 画布 Topology 编辑（拖拽 step 顺序 / 增减并行分支 / JSON Patch → AST）

## 前置清理（与 Phase 0 并行）

- [ ] C1. 拆分 `harness.py` 952 行为 `GraphBuilder` / `PhaseExecutor` / `RetryRouter` / `NudgeInjector` 4 个合作者 (P)
  - _Technical Debt_
- [ ] C2. 合并 docs/（`src/core/graph_agent/docs/` 与 `docs/graph_agent_docs/`）为一份，另一份改 symlink (P)
  - _Technical Debt_
- [ ] C3. 删除 `skills/builtin/script/patch_tools.py` 副本，保留 `md-patch/script/patch_tools.py` (P)
  - _Technical Debt_
- [ ] C4. `.gitignore` 加入 `.ccb/`、`*.pyc`、`.studio_state/` (P)
  - _Technical Debt_
- [ ] C5. 补多模态工具（`generate_video` / `synthesize_speech` / `understand_video`）单测 (P)
  - _Technical Debt_
