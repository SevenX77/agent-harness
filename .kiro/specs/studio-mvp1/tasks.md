# Implementation Plan

## Phase 0: Studio Backend Foundation (API Scaffold)

- [ ] 0.1 (a1) 初始化 FastAPI 工程骨架
  - 创建标准目录结构 (`app/routers`, `app/services`, `app/models`, `app/core`)。
  - 配置 `uvicorn` 启动项及跨域 CORS 设定。
  - **Acceptance Criteria**:
    1. 能够通过 `python -m app.main` 成功启动服务并在 `:8787/docs` 看到 Swagger UI。
    2. CORS 允许本地开发前端跨域请求。
  - _Requirements: 4_
  - blocked_by: none

- [ ] 0.2 (a1) 定义核心 Pydantic 契约模型 (P)
  - 参照 `design.md` §4.3，在 `app/models` 中声明 `ErrorResponse`, `SkillSummary`, `LintResult` 等约 17 个 DTO。
  - 导入 `graph_agent` 现有的 `SkillManifest` 与 `CallbackEvent`。
  - **Acceptance Criteria**:
    1. 所有请求/响应模型能通过 Pydantic 严格校验，包含正确的类型提示。
    2. `graph_agent` 模型可直接作为依赖包被无缝复用，无冲突。
  - _Requirements: 1, 4_
  - blocked_by: 0.1

- [ ] 0.3 (a1) 占位实现所有的 REST Endpoints (P)
  - 在 `app/routers` 中编写 API 路由装饰器，对应 `design.md` §4.1。
  - 暂时全量返回 Mock 格式或 `HTTPException(status_code=501)`。
  - **Acceptance Criteria**:
    1. 前端能针对所有列出的 API 地址发送请求而不报 404。
    2. Swagger 文档完整呈现所有端点的 Request / Response Schema。
  - _Requirements: 4_
  - blocked_by: 0.2

- [ ] 0.4 (a1) 全局异常捕获中间件
  - 捕获 `PydanticValidationError` 及框架异常，格式化为统一的 `ErrorResponse` (包含 `error_code` 和 `retry_strategy`)。
  - **Acceptance Criteria**:
    1. 提供错误接口模拟报错，必须返回标准化的 `ErrorResponse`。
    2. 明确区分 422 和 500 的 `http_status`。
  - _Requirements: 4_
  - blocked_by: 0.1

## Phase 1: Real Engine Integration

- [ ] 1.1 (a1) 实现 Skill 详情读取与解析 API
  - 移除 `GET /api/skills/{id}` 的 Mock。
  - 调用 `graph_agent` parser 加载指定路径的 `SKILL.md`，返回 `SkillManifest`。
  - **Acceptance Criteria**:
    1. 对合法的 SKILL.md，API 返回完整的 AST JSON。
    2. 若文件不存在返回 `SKILL_NOT_FOUND` (404)。
  - _Requirements: 1_
  - blocked_by: 0.3

- [ ] 1.2 (a1) 实现 Lint 校验端点
  - 在 `POST /api/skills/{id}/lint` 调用 `compile_skill()`。
  - 将编译结果映射转化为 `LintResult`。
  - **Acceptance Criteria**:
    1. 合法语法返回 `status="passed"` 及空错误列表。
    2. 错构或违反业务规则的语法，正确返回 `status="failed"` 及带行号的 `LintError` 列表。
  - _Requirements: 2_
  - blocked_by: 1.1

- [ ] 1.3 (a1) 实现 Monaco 内容更新与保存端点 (P)
  - 接收 `PUT /api/skills/{id}` 的完整 Markdown 字符串。
  - 将文件覆写至磁盘对应的位置，后触发 Lint 校验。
  - **Acceptance Criteria**:
    1. 保存成功后文件系统里的内容一致。
    2. 接口响应同时包含新的 `SkillDetail` 与保存触发的 `LintResult`。
  - _Requirements: 3_
  - blocked_by: 1.1

- [ ] 1.4a (a1) 实现 Run Subprocess 执行池隔离
  - 接收 `POST /api/skills/{id}/runs`。
  - 初始化一个 OS 级 Subprocess 以拉起 `graph_agent` 运行时，不阻塞主进程。
  - **Acceptance Criteria**:
    1. API 立即返回包含 `run_id` 的 `RunMetadata` (状态 `running`)。
    2. 子进程能在后台执行完整技能。
  - _Requirements: 2_
  - blocked_by: 0.3

- [ ] 1.4b (a1) WebSocket 事件代理与推送
  - 将 Subprocess 的事件流注入跨进程 `Queue`，并桥接到 `/ws/runs/{run_id}` 发送给客户端。
  - 落盘日志至 `tracing.jsonl`。
  - **Acceptance Criteria**:
    1. 客户端连接 WS 后能流式接收保序的 `CallbackEvent` 数据包。
    2. 运行结束时输出正确落盘，且前端收到完成标记。
  - _Requirements: 2, 6_
  - blocked_by: 1.4a

- [ ] 1.5a (a1) PTY Terminal 隔离管理器
  - 使用 `ptyprocess` 创建与分配特定于 PM 会话的子进程终端。
  - 环境变量及执行路径锁定到当前的 Skill 工作目录。
  - **Acceptance Criteria**:
    1. `/api/skills/{id}/terminal` 成功下发 `term_id` 和 `ws_url`。
    2. 进程无法 `cd` 出越界的项目根目录。
  - _Requirements: 4_
  - blocked_by: 0.3

- [ ] 1.5b (a1) WebSocket 终端字节流透传
  - 在 `/ws/terminal/{term_id}` 实现前端 `xterm.js` 与 `pty` 之间二进制数据的双向无缝桥接。
  - **Acceptance Criteria**:
    1. 通过客户端可以正常输入 `ls`，并且收到 stdout 回显。
  - _Requirements: 4_
  - blocked_by: 1.5a

- [ ] 1.6 (a1) FileWatcher 全局监控与事件分发 (P)
  - 启动 `watchdog` 监听 `skills/` 下的文件变更，挂接防抖动 (debounce) 逻辑。
  - 通过全局 `/ws/events` 下发 `skill_changed` 通知。
  - **Acceptance Criteria**:
    1. 用户在外部 IDE/CLI 保存文件时，FastAPI 服务能够控制台日志打印变动。
    2. 连接的 WS 客户端立刻收到通知 JSON。
  - _Requirements: 5_
  - blocked_by: 0.1

## Phase 2: Frontend Refactor

- [ ] 2.1 (a1) 移除 mvp0 前端正则表达式逻辑
  - 清理 `CustomNodes.tsx` 和 API 服务调用桩点中的 `.match()`。
  - 引入 `SWR` 获取 `GET /api/skills/{id}`，获得 `SkillManifest`。
  - **Acceptance Criteria**:
    1. 代码库中不再存在直接解析 `<phase>` 标签的正则。
    2. 应用层状态转由 API 响应的数据层全权驱动。
  - _Requirements: 1_
  - blocked_by: 1.1

- [ ] 2.2 (a1) ReactFlow 画布数据重新映射 (P)
  - 根据 `SkillManifest` JSON 中的 `phases` 及 `depends_on` 字段，重算 Dagre 布局。
  - **Acceptance Criteria**:
    1. 页面刷新后，ReactFlow 依然能呈现具有层级与分支依赖的拓扑图。
    2. 支持 `subgraph` 类型的异形渲染样式。
  - _Requirements: 1_
  - blocked_by: 2.1

- [ ] 2.3 (a1) 对接 Monaco 实时保存与 Lint 面板
  - 实现 Ctrl+S 触发 `PUT /api/skills/{id}` 请求，并用返回的 `LintResult` 更新 Error Drawer 状态。
  - **Acceptance Criteria**:
    1. 语法出错时，前端能够明确标记行号。
    2. 成功时侧边栏绿色标记“通过”。
  - _Requirements: 3_
  - blocked_by: 1.2, 1.3

- [ ] 2.4 (a1) 接入 Trace Timeline 实时渲染流
  - 使用 React Context 或类似订阅机制管理 WebSocket 事件状态阵列。
  - 将收到的 `CallbackEvent` 追加至时间轴与 Prompt Inspector 弹窗数据池中。
  - **Acceptance Criteria**:
    1. Run 开始后，侧边栏逐步渲染每一阶段的耗时及内容。
    2. 点击 Prompt 事件图标，弹出正常的三元组对比 Modal。
  - _Requirements: 2_
  - blocked_by: 1.4b

- [ ] 2.5 (a1) 终端 XTerm 接入
  - 实现一个前端悬浮的或底部驻留的终端容器。
  - 基于 `/api/skills/{id}/terminal` 获取句柄后连接 WS。
  - **Acceptance Criteria**:
    1. 打开控制台界面，可以键入 Claude CLI 相关命令并观察流畅输出。
  - _Requirements: 4_
  - blocked_by: 1.5b

- [ ] 2.6 (a1) 对接全局 FileWatcher 通知 (P)
  - 建立全局 WebSocket Hook 连接 `/ws/events`。
  - 收到变更事件时弹出右下角 Toast，并调用 SWR `mutate()` 获取最新清单。
  - **Acceptance Criteria**:
    1. 监测到变更时页面无需强制整页刷新即可应用最新的结构状态。
  - _Requirements: 5_
  - blocked_by: 1.6

## Phase 3: Integration, Security & E2E Testing

- [ ] 3.1 (a1) 安全防御隔离校验 (PTY Jailing)
  - 在 Backend 进行硬代码检测，拒绝带有 `../` 指向项目上层的 terminal cwd 请求。
  - **Acceptance Criteria**:
    1. 请求跨目录操作直接报 HTTP 500 `TERMINAL_SPAWN_FAILED`。
  - _Requirements: 4_
  - blocked_by: 1.5a

- [ ] 3.2 (a3) E2E: Monaco Edit & Lint 回环验证
  - 使用 Playwright 自动化修改一份测试 prompt，触发保存并获取通过信号。
  - **Acceptance Criteria**:
    1. Playwright 捕捉到相应的 Network Call 和正确的 DOM class 变动。
  - _Requirements: 3_
  - blocked_by: 2.3

- [ ] 3.3 (a3) E2E: Full Run Cycle 验证
  - 在 UI 模拟点击 Run，断言从 running 变迁至 finish 的全历程。
  - 校验本地 `tracing.jsonl` 文件成功生成。
  - **Acceptance Criteria**:
    1. 进程能够在超时时间阈值内自动结束，客户端 UI 获得最终的完整 Metrics 结果。
  - _Requirements: 2, 6_
  - blocked_by: 2.4

- [ ] 3.4 (a3) E2E: CLI File System Sync 验证
  - 在 E2E 中启动 Open CLI，向终端发命令利用 `sed` 修改文件，监控前端 Toast 组件是否成功出现。
  - **Acceptance Criteria**:
    1. 从触发 `skill_changed` 事件到出现 Toast，延迟符合期望，应用未发生崩溃。
  - _Requirements: 5_
  - blocked_by: 2.5, 2.6
