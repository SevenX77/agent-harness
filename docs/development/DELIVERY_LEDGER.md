# 交付台账(Delivery Ledger)

> 本文件是本仓**当前活动工作的唯一可变状态载体**:在做什么、到哪一步、被什么挡住、过哪道门算完。
> 新会话接手推进工作,**先读本文件**,不靠考古会话交接件。
> 维护规则:每合并一个在册 PR,同 PR(或紧随其后的台账 PR)更新对应行状态;状态翻转只增写不删史(旧状态留在 git 历史)。
> 状态词汇:`待开工` / `进行中(分支名)` / `✅ 已合并(#PR)` / `阻塞(原因)` / `已搁置(重启条件)`。

## 当前冲刺:Copilot 闭环(决议 2026-07-30)

### 决议(用户裁决,2026-07-30)

1. **闭环重定义**:产品闭环 = 用户通过 Studio copilot(MoirAI)面板**对话式走完 MVP1 七节旅程**(00 settings → 01 init → 02 authoring → 03 compile → 04 run-and-verify → 05 debugging → 06 eval/publish,旅程定义见 `docs/studio/mvp1/01_workflows/INDEX.md`)。copilot 是闭环主角,不是辅助。
2. **推进方式 = 接线冲刺**:2026-07-30 三路代码勘察(引擎 / Studio 前后端 / copilot 工具面)证实:缺口无一例外是"后端能力已存在但未暴露成 copilot 工具"或"组件写完未挂载"。因此本冲刺只做接线,**不做 ontology 改造、不做模块化重构、不做文档系统工程**(三者对闭环零贡献,明确后置)。
3. 本台账是冲刺的唯一状态源;`HANDOFF-operator-*.md` 交接件自本决议起只写"读台账 + 本次增量",不再承载队列。

### 验收判据(因果验证,冲刺完成的唯一标准)

一段**脚本化真实对话**在 copilot 面板全程跑通,除审批卡外不碰鼠标,每步有盘上证据(skill 目录 / run 目录 / golden 文件 / publish 产物):

1. "帮我建一个〈X〉skill" → `create_skill` 建出 UI 可见的 skill;
2. 配置/确认模型角色(既有工具);
3. 编译(`compile_skill`)→ 如有诊断,copilot 修复后复译通过;
4. predict 试飞(`predict_skill`);
5. 真跑(`run_skill`,经审批卡放行);
6. 读结果与 trace(`get_run_detail`),向用户复述模型实际产出;
7. 按用户反馈修改 skill → 复译 → 复跑;
8. 将满意的 run 定为 golden 基准(golden 工具);
9. 发布(`publish_skill`)。

### 关键设计决定

1. **真实 run 允许 agent 触发**,交互走与 LLM 配置写工具相同的阻塞式审批卡(`can_use_tool` 挂起,机制见 `apps/studio/backend/app/services/copilot.py:606-625`)。此决定推翻 `copilot_tools.py:158` 工具描述中"真实运行只能由用户在 UI 触发"的禁令。
2. **新工具全部是既有后端端点的薄包装**,照 `copilot_tools.py` 既有 16 工具的模式实现;业务逻辑留在 routers/services 层,工具层不长逻辑。
3. **引擎并联缺陷两步走**:先在编译期对并联拓扑发正式 `[F-v3-*]` 诊断(堵住"编译绿灯→运行炸框架原生错"的谎),后做真修(执行态状态写入迁 delta 语义 + 接上已有的 `blackboard_data_merge` 合并器),真修合并时撤除编译拦截。
4. **明确后置项**(重启条件 = 用户重新裁决):~~CLI 路 MCP 暴露(N5)~~(已被 2026-07-31 裁决提为最高优先,见下);新建向导/模板 UI(copilot 成为新建主路后降级);gateway 状态投影 7 条毛刺(不阻断闭环);文档系统工程(类型学 / docs 门禁 / AGENTS.md 瘦身)。

### 第二轮裁决(用户裁决,2026-07-31,首次真机测试后)

用户在面板里真跑了一轮 demo-loop(session 证据:`~/.claude/projects/D--coding-skills-demo-loop/54db2ab2….jsonl`,编译诊断 4→2→1 收敛后卡死在 `STUDIO_RUNTIME_INPUT_MISSING`),据此裁决:

1. **CLI 路(N5)提为最高优先**:"先修 Open in CLI,因为 cli 是成熟的 agent,不需要调试这些细节"。面板细节修复全部排在 N5 之后。
2. 真机测试坐实的面板缺口(N5 之后按序清账,登记为 P-系列):
   - P-1 **运行输入缺工具**:copilot 无法供给/绑定 test input,`STUDIO_RUNTIME_INPUT_MISSING` 是对话闭环的死墙;应能在无真实输入文件时自行 mock 一份 test input。
   - P-2 **AskUserQuestion 黑洞**:模型提问但面板不渲染、SDK 空答继续(session 记录 24-25 实证);用户从未收到提问。处置方向:面板会话禁用该工具,让模型用正文提问收尾。
   - P-3 **Bash 只读白名单**:`ls` 等无害只读命令免审批(代码强制解析:单命令、无管道/重定向/连接符才放行),不靠提示词。
   - P-4 **审批卡状态服务端权威化**:决议状态只存组件本地 state,重渲染即复活可点(`tool-approval-card.tsx:49-73`);后端 resolve 时应发 resolved 事件,前端从事件流投影。
   - P-5 **编译诊断结构化渲染**:is_error 工具结果(编译诊断集)不该渲染成系统故障样的红色 JSON 堆;中断后 CLI 聚合错误回声("SDK returned an error: …McpToolCallError×N")一并评估降噪。
   - P-6 **copilot 面板宽度自适应**:随窗口宽度伸缩(clamp + 可拖拽),窗口宽裕时面板加宽。✅ 已修(2026-08-02):宽度真相改为画布宿主宽度的比例(默认 0.275,历史默认 352px@1280 不变),拖拽把手回写比例,ResizeObserver 跟随窗口重算,仍夹在 280-720px;纯函数 `rightPanelWidthPx`/`rightPanelRatioFromPx` 带单测,复用规则已入 FRONTEND_UI_SPEC §4。
3. ~~**新讨论项(设计探讨,未裁决实施)**:把 Open in CLI 的终端内嵌进 copilot 面板区域,启动 CLI 时以终端界面替代对话界面("CLI 即 copilot");依赖 N5 工具面先就位。~~ → **PM 2026-08-02 裁决实施**(三条修正:宽度沿用现状不放宽、保留 header CLI 控制按钮作为唯一关 CLI 出口、tmux 滚动必须可用)。设计与验收判据落在 `docs/studio/mvp1/03_regions/copilot/ah-orchestration-design.md` §10;实现见下「阶段 3」行。

#### N5 · Open in CLI 工具面(当前最高优先)

| # | 项 | 状态 | 关键坐标 |
|---|---|---|---|
| N5-1 | 设计(operator 自决 2026-07-31,免上抛,以效果为裁) | ✅ 已定 | 决定:①出口=同一批工具对象再建 Server,官方 `StreamableHTTPSessionManager` 挂 sidecar `/mcp`,复用全局 Bearer 中间件,sidecar 保持只绑 127.0.0.1(本机 WSL mirrored 网络实测 localhost 直通 HTTP 200);②审批=A 案,交互式 Open in CLI 摘 bypass 旗标,用 CLI 原生审批当闸,读档经 allowedTools 预放行;③CLI 首版不暴露 delete_llm_endpoint/delete_llm_route(级联删凭据);④claude 用 `--mcp-config`(装机 2.1.199 实证支持 http+headers),token 走 `.mcp.json` 的 `${STUDIO_API_TOKEN}` env 展开不落明文;⑤codex 0.142.5 原生 `--url`+`--bearer-token-env-var`,无需桥。**不确定项(以效果为裁)**:U1 非 mirrored 网络的机器 localhost 不通→改为 lib.rs 注入宿主 IP;U2 codex 摘 bypass 对 ah 编队流的影响→先只动 claude,codex 看效果;U3 FastAPI BaseHTTPMiddleware 与 SSE 流的兼容→TestClient 已过,真机 CLI 长会话再验 |
| N5-2 | 实现:sidecar `/mcp` streamable HTTP 出口(工具面=面板 27−2) | ✅ 随本行同 PR 合入 | `app/services/cli_mcp_surface.py` + `main.py` lifespan 内建 manager/`app.state` 转发挂载;4 测试(工具差集/内存会话协议/401/initialize 200+session-id);`mcp>=1.29` 补为 backend 直接依赖(uv.lock 变更→合并后根 uv sync + vendor 重建) |
| N5-3 | 实现:lib.rs 注册 studio MCP(claude `--mcp-config` + 摘 bypass + allowedTools 读档;codex config.toml `[mcp_servers.studio]` url+bearer_token_env_var)+ 资产回写 | ✅ 随本行同 PR 合入 | payload 注入 `STUDIO_MCP_URL`/`STUDIO_API_TOKEN`(sidecar 未起则整段省略、会话照常启动);5 个新 Rust 测试绿(本机既有 4 个无关失败,干净树复现过);cli.md 新增「Studio Tool Surface」节、KB-13 撤销「CLI 无工具」警示 |

#### 阶段 4 · copilot 工具面的能力对等与状态对等(2026-08-03 用户批准)

决议正本:`docs/design/2026-08-03-copilot-state-parity-and-tool-surface-decision.md`
(两条原则、6 条关键设计决定、PR 拆分、8 条验收判据、边界)。事实基础全部来自
exp-b-round3 北极星实测,证据在 `D:/coding/skills/_copilot-lab/rounds/exp-b-round3/`。

| # | 项 | 状态 | 关键坐标 |
|---|---|---|---|
| P4-A | 后端三关领域事件(compile/predict/run 在 service 层发 `skill_gate`) | ✅ 随本行同 PR 合入 | 新模块 `app/services/gate_events.py`(载荷构造 + async/from-thread 两个发布入口,广播失败只记日志不影响闸门);发布点:`compile_skill_for_studio` 包一层薄壳分派 pass/fail、`predictor.dispatch_predict_job` 用**同一个投影函数** `export_predict_diagnostics(result).status` 判定通过与否(与前端判定同源)、`run_manager.start_run` 发 started 且 `_finalize_terminal_run` 的 `finally` 发终态;6 测试含一条**结构断言**钉住"router 不得自行发布、三个 service 必须发布"——若发布点漂回 router,MCP 路径就不发事件,而只走 HTTP 的行为测试看不出来 |
| P4-B | 前端闸门归约器重构 + 订阅 | ✅ 随本行同 PR 合入 | 决议 D4;新模块 `apps/studio/frontend/src/components/studio/gate-state.ts`(纯函数 `projectGateEvent` + 去重键 `gateEventKey` + 载荷解析),`Workspace` 里唯一施加点 `applyGateEvent`——**点击处理器与事件流都走它**,两条路径不可能分叉;去重键让本地投影与随后到达的广播只生效一次(抽屉不弹两回),作用域限定当前打开的skill(别的 skill 只更新 stage、不夺走视图);失败事件带上**同一份聚合诊断**,接收方不再自算一份(diagnostics SSOT);10 条前端测试含一条双路径投影一致性断言 |
| P4-C | run 可观测性:`query_run_trace` + `wait_for_run` | ✅ 随本行同 PR 合入 | 决议 D6;新模块 `app/services/run_trace_query.py` 为纯投影(逐 phase 汇总循环轮数 / llm 与 tool 调用数 / finish_task 提交与驳回次数 / 驳回原因 top-N,外加按 phase·事件类型·seq 切片并投影成小体积事件——prompt 与完整 context 不进工具结果);判定规则取自 exp-b-round3 真实 trace:`finish_task` 的 result 等于 `PHASE_COMPLETE` 为接受、非空且不等于它为驳回、空串两者都不算(不猜)。`wait_for_run` 挂在 `run_manager` 既有 `subscribers` 队列上,run 结束该队列收到 None,等待因此由事件驱动、零轮询;已结束的 run 立即返回终态。两个工具都进面板与 CLI 的**只读预放行清单**。7 条纯函数测试 + Rust 171 绿 |
| P4-D | `set_output_artifacts` 工具 | ✅ 随本行同 PR 合入 | I/O 面板 "Configure output artifacts" 的后端等价物,调用**同一个** service `update_artifacts_payload`;产物 schema 从路由内联提到 `app/models/runtime_config.py`,面板与工具共用一份校验(两个写入方各带一套校验正是它们悄悄漂开的方式,已用一条结构断言钉住路由不得再自带 schema)。整份清单全量替换,空清单即取消全部声明;形状不合法在边界拒绝并回具体 pydantic 错误。它是**写工具**,不进只读预放行清单,照常走审批。4 条测试 |
| P4-E | CLI 会话注入 `skill_id` + `workspace_root` | ✅ 随本行同 PR 合入 | 修 F3/F13(两次独立复现)。id **从 skill_index 反查**(`native_fs::registered_skill_id_for_root`)而不是由打开方传入——会话必须绑在**已登记**的那个 skill 上,而由调用方给 id 正是第一次就出错的那个输入;身份随 master 首条 prompt 下发(`master_prompt`),claude 与 codex 两条命令都带。未登记的工作区照旧发裸 prompt,不编造 id。Rust 新增 4 测(共 171 绿) |
| P4-E2 | **回归修复:身份注入把 ah.toml 写坏,Open in CLI 起不来** | ✅ 随本行同 PR 合入 | P4-E 注入的身份文本含换行,而 TOML 基本字符串不允许字面换行——生成的瞬态 ah.toml 在第 7 行断开,`ah start` 以 `invalid basic string` 退出码 3 失败,**CLI 会话完全打不开**。真机第一次点开就撞到;P4-E 的 Rust 测试只断言 `cmd.contains(<skill id>)`,从不校验生成物能否解析,所以那条测试一直是绿的。修复=`toml_string` 转义换行/回车/制表符(序列化器本就该做,不是给这一处打补丁);新增两测:转义单测 + **把生成的瞬态配置真的 parse 一遍**(claude 与 codex 两条),后者正是原本缺的那道门。红态实证:去掉修复后两测红(171 passed / 2 failed),修复后 173 全绿 |
| P4-E3 | **封存的 predict 无人能问:补状态账 + 把 trace 纳入 seal** | ✅ 随本行同 PR 合入 | 真机 exp-b-round4 第一轮实测暴露:会话想查"review 在 predict 里收到了什么", 无工具可用, 遂用 Bash 手扒 `.workspace/runs/predict-*`, 又被 Claude Code 持久 shell 的 cwd 绊倒(第一条命令 `cd` 进 run 目录后, 第二条的相对路径就落到了 run 目录之内), 把 `No such file or directory` 误判成"目录被扫了"并一路追着幻觉跑到 scratchpad。**产品侧真因有两条, 都是 predict 的产物目录不如 run 完整**:(1) predict 一结束就被 `finish_transient_predict_run` 从注册表摘掉(`run_manager.py`), 而目录里没有 `run_metadata.json`, 于是 `_metadata_for` 两头落空, `get_run_detail`/`query_run_trace` 一律 RESUME_CHECKPOINT_NOT_FOUND;(2) 封存只把 `result.json` 写进 manifest, 而读取一律经 manifest, 所以引擎写在同一目录里的 `trace.jsonl`/`final_state.json` 对所有 reader 不可见(实测该目录 8 个文件, manifest 只认 1 个)。修法都落在生产端, 不在读取端打特例:predict 封存时补写状态账(格式归 run_manager, 新增 `record_predict_outcome`; status 取 `export_predict_diagnostics` 同一投影, 与 gate 广播共用一次判定, 不另立裁判), 并把 `trace.jsonl` + `final_state.json` 一起纳入 seal。同时拆掉诱因:`predict_skill` 的描述与 `detail_hint` 不再指向 `.workspace/runs/<run_id>/`, 改为指向 `query_run_trace`。TDD 三测(状态账存在/失败判定与 gate 同源/跑完的 predict 能被 query_run_trace 读出 trace 与 final_context)先红后绿 |
| P4-E6 | **跑起来只能等:补暂停/恢复/终止三态** | ✅ 随本行同 PR 合入 | PM 反馈"run 跑的时候至少该能停", 追问"不是有 checkpoint 吗, 为什么无法表达暂停"——**追问是对的, 我第一版把它做成了单一终态 `cancelled`, 漏了中间那层**。证据:`runner.py:426` `cleanup_checkpoints_on_finish: bool = True`, 即**只有自然跑完才清 checkpoint**;被中途终止的 run 走不到清理, `checkpoints.db` 完整留着(round4 真实 run 留了 11MB), 而 `runner.py:503` `resume_skill(skill_path, workspace_dir, run_id, ...)` 正是从它接着跑。所以"终止进程"≠"这次 run 结束了", 中间隔着"可恢复"。更正后的模型:**暂停**(`POST /{run_id}/pause`, status `paused`, 只停 worker、不做终态封存)与**终止**(`POST /{run_id}/stop`, status `cancelled`, 走终态封存)是两个动作;终止从 running 与 paused 两处都可达。状态词表 `RunStatus` 与 gate 词表各补 `paused`/`stopped`, "状态→广播"仍走显式映射表。工具条按 PM 指定的三态:running → 单个 **Pause**;paused → **Resume + Stop 两个按钮并列**(一个暂停的 run 有两个去向, 不由另一个隐含);其余照旧 Compile/Predict/Run。Resume 复用既有 `handleResume`(engine resume 通路早已存在)。测试:后端 4 条(暂停落 paused / 重复暂停 409 / **paused 仍可终止** / running 可直接终止)+ 前端 3 条工具条形态, 先红后绿;backend 1549 全绿, 前端 1910 全绿 |
| P4-E4 | **Open folder 跳去"文档":Windows 资源管理器不认正斜杠** | ✅ 随本行同 PR 合入 | I/O 面板 input file 行的文件夹按钮打开的是"文档"而非目标目录。链条:`IoConfigDialog.tsx:484` 拼完路径做 `.replaceAll("\\", "/")` → `lib.rs` `existing_path` 原样保留分隔符 → `Command::new("explorer").arg(target)`。**实证**:同一目录分别用反斜杠与正斜杠调 explorer, 前者窗口标题 `import_files`, 后者 `文档` —— 资源管理器对正斜杠路径不报错、静默打开默认目录。修法落在唯一出口:新增 `file_manager_argument`, Windows 下把分隔符归一成 `\` 再交给 explorer(任何调用方都可能传正斜杠, 在出口治比在每个调用点治对)。**红态踩坑并已修正**:首版断言比较两个 `PathBuf`, 而 Windows 上 `/` 与 `\` 都是路径分隔符、两者判等, 于是不修也绿(与 P4-E2 的 `cmd.contains` 同一类空断言)。改为比较真正交给进程的参数字符串后红态成立, 修复后 174 全绿 |
| P4-E5 | **跑完动画不停 / 工具栏横跳 / Trace 面板不跟 copilot** | ✅ 随本行同 PR 合入 | PM 真机反馈三条, 落点都在"用错判据"。**(a) 动画**:`ContextEdge` 的流动动画绑 `hasTraceData`, 而那是"这条边有数据可点开看", 一旦跑过就永久为真, 于是 run 结束后画布仍在流。改为绑"上下文此刻正在过这条边"=目标 phase 正在执行;判据 `runningPhaseOf` 抽进 `node-status.ts`, Workspace 的 trace 高亮与画布的边动画共用一条规则, 不各推一遍。有数据但未在流的边保留静态 accent 描边。**(b) 工具栏**:`center-action-bar` 按左右安全区取中点, 而两侧面板都是**浮层**(不挤占画布), 面板一开合就横移(实测 239px)。#567 曾因按窗口居中被拖宽的 copilot 面板压住——两次反馈是同一规则的两个特例:**默认钉在画布正中, 仅当浮层真会盖住时才让开**, 用 `clamp()` 表达, bar 自身宽度由 `useLayoutEffect` 实测发布成 CSS 变量(标签会随 stage 变, 不能写死)。**(c) Trace 面板**:人点 Run 走 `setActivePanel("timeline")`, 而 copilot 路径的 `follow-run` 只 `setRunId` —— 工具栏跟了、抽屉跟了、面板漏了(P4 自身缺口)。新增 `open-trace` 效果由 `projectGateEvent` 统一产出;predict 也补了 started 广播(predict 同样流事件), 点击路径删掉自己那份 `setActivePanel`, 两条路径同一实现。测试:边流动 2 条 + 面板效果 3 条 + 工具栏 clamp 1 条, 先红后绿;前端 1912 全绿, backend 1545 全绿 |
| P4-E7 | **产出契约是 skill 的固有一端:引擎导出字段全集 + MoirAI 能判断能配置** | ✅ 随本行同 PR 合入 | PM 定性:"产出 artifacts 是常态, 就和最初要输入 input 一样", 但"也有可能这个 skill 确实不需要, 这就需要 moirai 对 skill 本身的理解"。round4 实测正是这个形状——run 报 success、artifacts/ 空目录, 因为 `runtime_config.artifacts` 默认 `[]` 且只能人去 I/O 面板手点(`InputPanel.tsx` 的 "No artifacts configured yet." 就是默认态), **全程没有任何一处提出过"这个 skill 该产出什么"这个问题**。根因:"跑到出口时黑板上有哪些字段"这条推导只存在于前端 `lib/io-config.ts` 的 `blackboardAtOutput`/`reconcileOutputFields`——那是**图的契约事实**却被 UI 私有了, 所以后端、工具、任何检查都无从判断(这正是 P4-F 当时明确挂起的另一半)。落点在引擎(编译单出口本就在解析每个 phase 的 io schema):新增 `core/blackboard_contract.py`, 纯函数投影 `blackboard_fields_at_output`(根 io.inputs ∪ 各 phase io.outputs, 拓扑序后者覆盖同名, 每字段带 produced_by/type/是否被 io.outputs 声明)与 `undeclared_output_names`(声明了却无人产出 = 图honour不了的契约)。adapter 加 `get_output_contract`, copilot 加只读工具 `get_skill_output_contract`, 返回声明的输出 / 出口黑板全集 / 当前落盘声明 / **declared_outputs_not_landed**(声明了输出却一个字段都不落盘= 这次 run 什么可读的东西都没留下)。工具描述把这件事写成判断题而非配置项:多数 skill 需要落盘, 确有 skill 只在黑板里传给同图下游——那要**判断为不需要**, 而不是漏掉。测试:引擎 5 条(输入打底/后写覆盖先写/声明标记/缺产出被报/自洽时无遗漏)+ 工具 3 条, 先红后绿。engine 1523 全绿、backend 1548 全绿、mypy --strict 干净。**注意**:两套 pytest 必须分开跑(AGENTS.md 本就分两条)——混在一条命令里跑会互相干扰出 5 条假红 |
| P4-E8 | **零产物成功要说话:wait_for_run 在成功时报 artifacts_landed + 契约提醒** | ✅ 随本行同 PR 合入 | round4(干净阴性)与 round5(被会话死亡污染, 不作数但同形)连续两轮:run success、artifacts/ 空、全程无人问"这个 skill 该产出什么"。P4-E7 的 get_skill_output_contract 是**被动**工具, 只帮已经决定要问的 agent;缺的是把问题递到 agent 眼前的**主动触发点**。落点=wait_for_run 的成功返回(agent 读到成功的那一刻):附 `artifacts_landed`(真实落盘文件表), 为空时附 `output_contract_reminder`, 点名 get_skill_output_contract/set_output_artifacts 并保留"确实不需要落盘就说出理由"的出口(PM 定性:产出是常态但非必然, 判断归 MoirAI)。失败的 run 不提醒——该谈的是失败本身, 混在一起会把它埋掉。TDD 3 条先红后绿, backend 1558 全绿。**附带记录两条独立缺陷**:(a) round5 会话在 run 结束前 48s 被 systemd 外部 stop (anchor unit 干净 Stopped、Studio app 日志零 kill/close、发起者未查明)→ 提 ah 仓 issue;(b) run 刚结束时 frontend GET run detail 吃到 409 run_not_sealed(sealing 竞态窗口)→ 待修 |
| P4-F | engine 编译期校验未知声明(`target` 枚举) | ✅ 随本行同 PR 合入 | 决议 D5;实测 `target: __probe_invalid__` 编译 0 缺陷且透传进 manifest,而运行期只认 `{file, artifact}`(`runner.py:1952`)。落点在 engine loader 的 `_validate_inline_io_schema`(io.outputs 是引擎契约、compile 是单出口),诊断文案直接列出合法取值;运行期那句写死的字面量换成共享常量 `DECLARED_OUTPUT_TARGETS`,校验与执行读同一份枚举。**沿用既有码 `[F-v3-graph-io-schema-invalid]`,不新增码**——码表有 97 码冻结(R4.3/design §6.5,五道锁),未知 target 本就属于 inline io schema 不合法,具体字段与合法取值由 message + field_path 承载。4 测。**遗留**:决议里 F 的另一半(`runtime_config.artifacts` 的 fields 必须是黑板真实字段)本 PR **未做**——字段全集推导目前只有前端一份,后端要校验须先统一那份推导(归 P4-I `get_workspace_config`),复制一份会重犯两个实现的错。现状:写错 target 编译报缺陷,写错 fields 仍只在 run 完表现为空目录 |
| P4-G | `get_skill_overview(skill_id)`:manifest 摘要 + phase 列表 + 每 phase 的 io 字段名与类型 + validator 有无 + llm_role | ✅ 已合并(#603);真机:经 sidecar `/mcp` 真端点 MCP 握手+`tools/call`,27 工具在列,exp-a-round3 返回 3 phase 结构投影(字段名+类型+required),断言全过 | 实现:走 `_load_compiled`+`_graph_topology` 同一条编译路径,不带 detail 副作用(git init/watch/读正文);投影=graph 摘要+graph_io/每 phase 的字段名+类型+required(非整份 schema 转储)+mode/validator/llm_role/depends_on/is_graph_output/subgraph path。有界锁死:正文零泄漏有 marker 断言;编译不过 fail-fast 指向 compile_skill(诊断 SSOT 不复述)。三面注册:工具表+免审批清单+CLI claude allowlist;两个工具面契约锁按新工具更新。5 新测,backend 1563 全绿,Rust 196 绿 |
| P4-H | `read_skill_file(skill_id, path, range?)` | 待开工 | 经 skill 索引解析、限定 skill 目录内,替代会话裸用 Bash/Read 摸文件 |
| P4-I | `get_workspace_config(skill_id)` + `list_run_artifacts` / `read_run_artifact` | 待开工 | runtime_config 的结构化投影(输入绑定 / test inputs / artifacts 声明 / llm 覆盖);现状 `get_run_detail` 的 artifacts 字段永远是空数组 |
| P4-J | 知识资产:新增 KB「产物与落盘」;KB-09 补 `query_run_trace` 诊断套路;KB-13 随工具面更新;修 KB-08 矛盾 | 待开工 | KB-08 第 22 行 "users cannot override this behavior manually" 与第 27 行 P1 档 "manual mock overrides are supplied ... in the test panel or copilot callbacks" 互斥 |
| P4-K | P2 写工具收口(`write_skill_file`/`bind_test_input`) | 待排期 | 现状:CLI 会话直接 Write 磁盘,绕过「Rust native-fs 是 skill 文件唯一写者」 |

#### 阶段 3 · CLI 终端内嵌 copilot 面板(「CLI 即 copilot」,2026-08-02)

| # | 项 | 状态 | 关键坐标 |
|---|---|---|---|
| T3-1 | Rust PTY 宿主 + 输出走 Tauri channel;外部终端窗口路径整条删除 | ✅ 随本行同 PR 合入 | 新模块 `apps/studio/tauri/src/cli_terminal.rs`(portable-pty + channel + 会话 owner 去重);删 `spawn_terminal_with_launcher`/`focus_existing_windows_terminal`/`windows_cmd_start_powershell_args`/`spawn_linux_terminal`/两个 .ps1 生成器/窗口标题;PTY 字节链有实测单测(`pty_delivers_the_child_process_output`,含 ConPTY 光标查询应答) |
| T3-2 | 面板内终端视图:面板持有会话、组件只渲染;xterm 依赖升到 `@xterm/*` | ✅ 随本行同 PR 合入 | `cli-terminal-session.ts`(会话工厂 + 可重放输出历史)+ `cli-terminal-view.tsx`(纯渲染器,懒加载);删孤儿 `TerminalPanel.tsx` 与 `TerminalSession`/`TerminalStatus` 类型 |
| T3-3 | tmux 鼠标滚动(D6) | ✅ 随本行同 PR 合入 | 启动/attach 脚本 attach 前按**会话工作目录**发现 ah 的 tmux socket 并 `set-option -g mouse on`(不复制 ah 的 socket 哈希);真机实测 `mouse on` 已生效、滚轮上下滚动可逆 |
| T3-5 | PM 反馈两处修正:动作栏压面板 + 收起面板丢终端 | ✅ 随本行同 PR 合入 | ①动作栏改为在画布安全区之间居中(`center-action-bar.tsx`,与 minimap 同一组 safe-area 变量);②CLI 会话所有权从 copilot 面板上移到 `Workspace`——面板收起会被卸载,会话存那里必然随之消失且泄漏终端客户端;设计源 §10 D3 同步修正 |
| T3-6 | **CLI 会话拿不到 Studio 工具面(N5 实际失效)** | ✅ 随本行同 PR 合入 | 根因:master 由 ahd 派生,ahd **不继承** launcher shell 的 export(实测 daemon 与其下所有进程 STUDIO_* 变量为 0),`--mcp-config` 整段被 `${STUDIO_MCP_URL:-}` 守卫静默丢弃,会话起来后 `/mcp` 报 No MCP servers configured;修复=端点与 token 烤进 master `cmd` 串本身(ahd 原样执行),与 `build_ah_bash_script` 的同类推理一致。真机实证:修前 `No MCP servers configured` → 修后 `studio · ✔ connected · 25 tools` |
| T3-7 | **run 结束后 `get_run_detail` 永久报 `running`** | ✅ 随本行同 PR 合入 | 现象(2026-08-03 exp-b-round3 run `2026-08-03T07-01-08_ff0be8c9`,独立 MCP 会话复现):同一份响应里 `status: running` + `metrics: null`,而它自己的 `event_type_counts` 已含 `run_ended: 1`,盘上 `sealed`/`result.json` 早已写完;同一 run 的 HTTP `/runs` 列表却报 `success`。根因:列表读盘(`list_runs` glob `run_metadata.json`),`get_run_detail` 走 `_metadata_for` → 内存 `RunRecord`,而 `record.metadata = metadata` 是 `_finalize_terminal_run` 的**最后一句**、排在两次存储 await 之后,任一次抛错就永远停在 `running`。修复=该赋值移进 `finally`。**保持记录为状态 owner(不改成读盘)**:盘上 `run_metadata.json` 在 `latest/` 同步**之前**就写成终态,以盘为准等于提前宣布完工——实测会让 `test_api`/`test_skill_git_p0` 的 `latest/run_metadata.json` 断言按 1/3 概率竞态失败 |
| T3-8 | **CLI 在跑,面板却渲染 `Open in CLI`(状态生产者被订阅者杀掉)** | ✅ 已合并(#586);真机点验 6/6 通过 | 现场取证(2026-08-03 21:37,exp-b-round4):`ah events` 自报 `runtime_state:"active"`(master pid 938 + 3 worker 全 IDLE),而 Tauri 进程下**一个 `ah events` 子进程都不剩**,面板于是停在挂载初值 `inactive` 渲染 Open。根因是所有权错误:MoirAI 面板条件挂载(`Workspace.tsx:2663`),折叠即卸载 → dispose 发 `unwatch_code_assistant_status` → Rust 无条件杀掉**共享**的 `ah events` 流并清空快照缓存(`lib.rs:1675-1703`,无引用计数);它与新挂载发的 `watch` 之间没有顺序保证,后落地即让活着的订阅者永远收不到状态,且无兜底重连。叠加第二处:"没有快照帧"被投影成 `inactive` 这句断言(`unwrap_or(AssistantStatus::Inactive)`)。修复=删掉整条订阅者驱动的 teardown(生产者归 `CodeAssistantRuntimeState`,`watch` 幂等且顺带收敛到单工作区)+ 新增 `unknown` 相位表示"尚未观测"(面板 hands-off)+ 流启动时 `status --json` 播种。决议落盘 `.kiro/specs/studio-ah-state-contract-v1/decision-2026-08-03-status-stream-ownership.md` |
| T3-9 | **回归:Close 之后 Open 控件永久禁用** | ✅ 已合并(#587);真机复验:Close 后约 1 秒回到可点的 `Open in CLI`,观察者 PID 19860→88993 证明流确实重建 | T3-8 的真机点验抓到:`ah stop` 杀掉 ahd 后,该 config 的 `ah events` 子进程**不退出**、只是永远不再发帧(实测存活 3 分 08 秒、`events-exited-respawning` 计数 0)。T3-8 在 Close 里清空快照缓存,指望重生的流填回来——重生根本不发生,于是投影永久停在 `unknown`,Open 控件禁用点不动,连重开 CLI 的入口都没了。修复=删掉"只清缓存"这个动作,Close 确认消失后改为**重开观察流**(`restart_status_streams_for_workspace`),重建的 `ah events` 立刻发 `daemon_absent` → 投影 `inactive` → Open 恢复可点。一般规则:一条流绑定的是某个 daemon 实例而非 config,Studio 自己改变 daemon 存亡就必须重开观察者。决议 D-C7 已改写(原"可接受的短暂窗口"依据被实测推翻) |
| T3-10 | **`lingering` 判据误报:没有 tmux server 也说"CLI running"** | ✅ 已合并(#589) | 真机取证(2026-08-04,本机 WSL,`ah 1.7.0`):Studio 管的 6 份 config 里 **4 份**处于 `runtime_state:"inactive"` + `ahd_alive:true` + `tmux_server_alive:false` + `ahd_has_inventory:false`,全部 agent `KILLED`/`tmux_alive:false`——2026-08-02 决议 D-A1 的 `ahd_alive` 判据把它们全报成 `lingering`,面板给出一个 attach 不到任何东西、也无事可关的 Close 控件。D-A1 的推理是单向蕴含:ah 只在 ahd 退出时回收 tmux,但 ahd 活着**不蕴含** tmux server 存在(机器重启把 tmux 带走、ahd 又被拉起就是这个形状)。修正=面板呈现改判 `tmux_server_alive`(死窗格活在 server 里,server 没了就什么都没剩下);`/exit` 留死窗格的原始场景 server 仍在,判定不变。**只改呈现**,启动前清残留那条道继续用 `ahd_alive`(D-A4 宁可多清)。逐字捕获帧冻结为 fixture `SNAPSHOT_AHD_ALIVE_TMUX_GONE`;D-A1 已加修正块 |
| T3-11 | **CLI 控件的 hands-off 窗口改成进行态(loading),不再像"功能不可用"** | ✅ 已合并(#590) | T3-8 引入 `unknown` 相位后,状态未观测的那一两秒头部渲染的是一个**外观与不可用无异**的禁用 `Open in CLI`,使用者分不清"正在查"和"这功能挂了",第一反应是反复点。改为带 `Loader2` spinner 的进行态控件 + 说明在等什么的文案(`Checking…` / `Starting…`,更具体的事实优先)+ `aria-busy`。渲染优先级 = 有真实可执行动作 > 进行态 > 空闲入口,所以"一个在跑、另一个正在启动"时头部仍给 Attach/Close,不被 spinner 顶掉。可复用规则已回写 `FRONTEND_UI_SPEC.md` §2.7a「进行态 vs 不可用」|
| T3-12 | **残留 = 还有运行时:attach 打开死窗格,Close 才销毁** | ✅ 已合并(#591);⚠️ 真机未观测到,可达性依赖 [ah#53](https://github.com/SevenX77/ah/issues/53)(`tmux_server_alive` 在残留存在时报 false) | PM 裁决 2026-08-04(取代 D-A3):有残留就当作还在 running,attach 上去看那块 `remain-on-exit` 死窗格,必须 Close 清干净才能再 Open(最后一条本来就是现状)。推翻 D-A3 的理由:那块窗格正是 ah **有意**留下供事后取证的,而使用者想看的就是它——CLI 怎么退的、最后报了什么;原方案等于保留一份证据再让自己的 UI 拒绝展示。更糟的是它的落地方式:"不给 attach"被实现成"attach 即销毁"(走 `CleanupStale` 清掉整个运行时再报错),一次**观察**动作毁掉**观察对象**。落地=attach 独立判据 `reconcile_snapshot_attach`(与 Open 那条道分开),残留→`AttachResidue` 直接 attach 不清理,`degraded` 仍先清(坏状态没有可读窗格);菜单项标 `(exited)`,否则冻住的窗格会被读成卡死;「面板说有运行时」与「attach 有落点」共用谓词 `runtime_has_unreaped_residue` 并有测试锁死一致 |
| T3-13 | **bearer token 移出进程表:MCP 端点与 token 改走 `[master.env]`** | ✅ 已合并(#592) | ahd 不继承启动 shell 的环境(T3-6),所以这两个值此前只能烤进 master 的**命令串**——而命令串在进程表里全机可读,`ps` 一眼就能看到 bearer token(2026-08-04 实测可见)。ah 1.8.2 给了 master 席位自己的 env 通道(ah#37,由本仓提的 issue 促成),改走 `[master.env]`:启动脚本读法不变(`${STUDIO_MCP_URL:-}`),值不再进 argv。**同时把 `AH_VERSION_MIN` 从 1.4.0 抬到 1.8.2**——旧版 ah 会静默忽略未知配置段,不报错只是工具面消失,这种无声降级必须挡在启动前;launcher 脚本里那句硬编码的 `# requires ah >= 1.3.4` 注释也改成从 `AH_VERSION_MIN` 派生,免得再漂移。版本 fixture 换成本机实测的 1.8.2(门槛)/1.8.1(实际因缺 `[master.env]` 起不来的那一版) |
| T3-14 | **launcher 版本门禁把合规版本挡在门外(四份拷贝各自腐烂)** | ✅ 已合并(#593);真机复验:Open in CLI 3 秒起会话,token 在进程表零命中,`/proc/<pid>/environ` 两个变量都在,sidecar 收到已鉴权的 `/mcp` 流量 | T3-13 把门槛抬到 1.8.2 后真机复现:装着 1.8.2 的机器被自己的门禁拒绝,报 `ah 1.8.2 is installed; Studio requires ah >= 1.8.2`。根因不是门槛写错——是那段 shell 门禁被复制成**四份**,已经各自腐烂:一份的第三分支写成 `[ "$min_minor" -eq "$min_minor" ]`(拿一个从未赋值的 shell 变量跟自己比,恒假),让「主次版本相等、只看 patch」这条路彻底不通;另一份混进 `[ "$----" = "$----" ]`(恒真);剩两份是干净的。门槛还是 1.4.0 时看不出来(装的都是 1.7/1.8,minor 更大,走前一条分支就过了)。修复=四份合成**一份** `ah_version_gate_script()`,并把三分支比较换成一次数值比较(没有分支就没地方藏恒真恒假条件);非数字版本串(ah 缺失时的 "unknown")落进 case 拒绝分支,不让 `$(( ))` 炸出来。测试改成**行为验证**:把生成的片段喂给真 `sh` 跑八个版本档(门槛/上下邻居/非数字),断言放行结果 |
| T3-15 | **恒假的 state_dir 前置门把 bootstrap 整条路杀死** | ✅ 已合并(#598);真机复验:切走切回后 `bootstrap-seeded runtime_state=Active` 首次出现 | 补测轮观测:运行时活着、status 退 0、两条道身份字段一致,`bootstrap-seeded` 仍恒 0。根因:`verify_snapshot_identity` 要求 ah 的 `state_dir` 位于工作区下或含 Studio 的 workspace hash——而它是 ah 用自己的内部算法从 **config 路径**派生的 hash(实测 `/root/.local/state/ah/9cc1e7dd`),两个条件恒假 ⇒ 恒 Err ⇒ bootstrap 播种、Close 的 kill 升级、Open 冷窗口全部拿不到快照。第一性原理:验证=比较预期与观察,请求方无法独立形成预期的字段不能当验证条件。修复=身份锚只取 session `path`+`project_id`(请求方可预测、可跨 Windows↔WSL 规范化),`state_dir` 降为诊断(与 `config_path` 同级);空 sessions=无证据而非反证,接受。测试改以逐字捕获快照为准(旧的 SchemaDerived 身份 fixture 按错误预期构造 state_dir,让实现和测试共享同一假设互相印证了七周)。决议 `decision-2026-08-05-identity-anchor-and-tmux-server-alive.md`;Req 2.7/design.md 已加修订块 |
| T3-16 | **Resume:关闭清场后显式恢复上次对话(PM 裁决 2026-08-05)** | ✅ 已合并(#600+#601);真机 F-6/F-7 全过:软链 `sandbox/.claude/projects → /root/.claude/projects` 建对(getent 派生,#601 修掉死守卫+空目录坑);暗号对话落宿主(slug `-mnt-d-coding-skills-exp-a-round3` 与设计预判一致)、活过 Close;Resume 1 秒起、argv 带 `--continue`、恢复的终端里搜到上次暗号 ×2;从未开过会话的 demo-loop 点 Resume → 打印回落说明、无 `--continue` 全新启动 | 两项裁决落盘 `decision-2026-08-05-close-cleans-resume-restores.md`:R1=退出全量清扫是产品预期(此前"另案待裁"关闭);R2=恢复对话走显式 Resume。机制:ah 给 claude master 设 `CLAUDE_CONFIG_DIR=<沙箱>/.claude`(home_layout.rs:1813),`ah stop` 删 master 沙箱(ahd.rs:278) ⇒ 对话记录活不过关闭。修复=包装脚本把 `$HOME/.claude/projects` 软链到宿主 WSL home(与凭据同一手法,新开与恢复都做);`Open in CLI` 下拉加 "Resume Claude code",同一条启动流程,执行尾分叉:对话目录非空→`--continue`(不带初始 prompt),空→打说明回落全新启动(安全降级)。仅 claude,codex 命令不暴露该参数(类型层面)。worker 不共享目录=天然隔离,resume 不会捞到 worker 的对话 |
| T3-17 | **`STUDIO_AH_HOST_HOME` 整体退役(#596 遗留死代码清理)** | ✅ 已合并(#604) | 证据:payload 三处 `export` 在 payload 内零读取者,而 master 由 ahd 从零拼环境 spawn 收不到它(2026-08-05 实测 /proc 环境无此变量);`.claude.json` 是 ah 材料化拷的真文件、`.credentials.json` 不存在而登录正常(#596 shared_credentials_dir)、codex auth.json 由 ah 3a9c130 共享。处置:三 export+三软链段删除;claude/codex 的 binary 回退**用途仍活**(daemon PATH 无保证)→ 重锚 getent `host_home`;测试升级为「生成物零 STUDIO_AH_HOST_HOME」终局锁。Rust 196 绿 |
| T3-18 | **copilot 默认模型 = DeepSeek V4 Flash(PM 裁决 2026-08-06)** | ✅ 已合并(#607);真机:冷加载角色 chip 即 DeepSeek V4 Flash,DeepSeek 面板答题 10s 且 DOM 现 `studio:get_skill_overview completed` | 默认写死在前端家族阶梯 `pickDefaultCopilotGroupIds`,flash 插排位第一;设计源 00_settings-ux-spec.md §3.2 + 手册三张 copilot 切片同步。官方 DeepSeek /models 实测 = v4-flash + v4-pro,双双 verified |
| T3-19 | **内置 copilot 角色 = 固定模型;v4 pro 退役(PM 裁决 2026-08-06)** | ✅ 已合并(#608);真机:掏空 PUT 422/换模型 PUT 422/删固定角色 409 全在真端点复验;设置页两张内置卡零模型移除钮,V4 Pro 卡消失 | 真机点验抓到的缺陷:固定角色模型可被 UI 移除 → copilot_deepseek_v4_pro 成空壳。修在两层:前端藏移除钮+拖拽只认推荐组;后端 `fixed_copilot_model_change_error` 双 PUT 入口边界校验。固定配置 v4_pro→v4_flash;数据清理后终态=opus_4_8+deepseek_v4_flash 两只固定角色 |
| T3-20 | **Resume 跟随上次打开的 CLI + codex resume(D-G,2026-08-06)** | ✅ 已合并(#609);真机 G-5:codex 开→暗号→Close→菜单现 "Resume Codex"→恢复终端见暗号+codex 自报 resuming+argv 含 `resume --last`;无记录工作区无 Resume 项 | owner=Tauri 启动记录 `code_assistant_last_opened.json`;codex sessions 软链回 host home(与 claude projects 同构);`codex resume` 默认按 cwd 过滤(0.142.5 实证)。决议文档 D-G1..G3 修订块 |
| T3-21 | **codex_apps 空段拒启修复** | ✅ 已合并(#611);真机:修复后 Codex TUI 正常起,codex 内置 codex_apps MCP 自行启动 | 真机点验抓到:旧脚本在 codex_apps 段缺失时凭空创建仅含 startup_timeout_sec 的空段,codex >=0.142 校验 `invalid transport` 拒启 master 秒死。删凭空创建分支,只留已有段的补丁路径(RED→GREEN,201 Rust 测试) |
| T3-22 | **Settings「CLI」区(安装/鉴权/一键装/分角色配置)** | ✅ 已合并(#613 状态面板 + #614 安装/配置);真机:七行依赖全 ok(截图)、安装钮全 ok 时隐藏、effort 下拉=CLI 档位、autosave 落 /api/settings、claude master argv 现 `--effort low`、clotho 覆盖入 ah.toml `env = { ANTHROPIC_MODEL = ... }` | 设计已写回 00_settings-ux-spec.md §3.9(含两处修订:一键安装拉真控制台因 OAuth 交互;codex worker/worker 级 effort 无 env 证据不注入)。提案 #610 存档。期间 GitHub 大面积故障拖了合并数小时(外因) |
| T3-23 | **P1 数据面读工具 PR-H/PR-I(read_skill_file / get_workspace_config / list_run_artifacts / read_run_artifact)** | ✅ 已合并(#616+#617+#618);真机:/mcp 端点 34 工具在面,整读/切片/逃逸拒/投影/空枚举全过 | 全部有界(D6):400 行/48KB 截断如实标注,路径限定 skill 目录与 artifacts 目录内。真机直测抓出两个既有缺陷并修复:① query_run_trace/wait_for_run/set_output_artifacts 定义了却没进注册表,两个面全是死工具(#618 补注册+「定义即注册」防漂移测试);② (type, None) 可选参数约定从未生效(SDK 无 tuple 分支落 string 兜底、dict 名单一律全必填),四工具改完整 JSON schema 透传(#617 错机制、#618 纠正) |
| T3-24 | **PR-J 知识资产** | ✅ 已合并(#616) | 新增 KB-14 产物与落盘(两条声明路径 target∈{file,artifact}+runtime_config.artifacts、<stem>_latest_<ts> 命名、fingerprint 参与、验证链);KB-09 补 query_run_trace 有界诊断套路;KB-13 工具地图补齐现役读写工具;KB-08 P0-P2 矛盾修复;hub 注册 |
| T3-4 | mvp0 遗留后端终端栈删除(`routers/terminal.py` / `terminal_manager.py` / `models/terminal.py` / ws 路由 / `ptyprocess` 依赖) | 待开工(单独 PR) | 与 T3-1/2 无调用关系,且要动依赖清单(uv.lock + vendor 重建),按「一个任务一个 PR」拆出 |

#### 事故修复 · copilot 权限模型"未知工具默认放行"漏洞(exp-B,2026-08-01)

**事故**:无头实验 exp-B(证据 `D:\coding\skills\_copilot-lab\rounds\exp-b-round1\events.jsonl`)中,copilot 的 Write 被写白名单拒绝后,模型改用 Windows CLI 自带的 PowerShell 工具把 `runtime_config.json` 和 import 文件直接写进无权目录 —— 16 次调用全部放行,零审批卡。

**根因**:`copilot.py` 的 `can_use_tool` 只显式处理 Write/Edit、Bash、MCP 写三类,末行对一切未知工具默认 `PermissionResultAllow`(黑名单模型);PreToolUse 的写边界 hook(`_WRITE_CLASS_TOOLS`)与 Bash 强制-ask hook 也都不覆盖 PowerShell,硬边界同时失效。

**决议(操作指令,2026-08-01)**:权限模型改为"已知语义白名单"三档 —— ①声明式免审批名单(`_DECLARATIVE_ALLOWED_TOOLS`,本次补入 TodoWrite/Skill 两个已知声明式工具)直放,该名单同时喂 `allowed_tools` 预放行与 `can_use_tool` 直放两层(单一事实源);②名单之外的一切 —— 执行类(`_EXECUTION_CLASS_TOOLS` = Bash/PowerShell,PreToolUse ask-hook matcher 与审批档共用这份定义)、写类、MCP 写、未知工具 —— 一律 `_hold_for_tool_approval` 挂起审批;③默认放行档删除,不存在 fall-through Allow。`Task`(三女神 subagent)无使用实证,留在默认审批档,未来凭证据显式分类。

| # | 项 | 状态 | 关键坐标 |
|---|---|---|---|
| SEC-1 | can_use_tool 三档白名单 + PowerShell/未知工具默认审批 | ✅ 随本行同 PR 合入 | 回归测试 `tests/services/test_copilot_guardrails.py`「exp-B 事故回归」节(PowerShell/未知工具必须挂起、免审批名单分类互斥);验收 = 全 CI 门禁绿 |

**与 P-3 的合并语义**(P-3 是反方向的放宽,后续处理时以此为准):只读命令白名单免审批、其余执行类一律审批、未知工具默认审批。

### 冲刺清单

#### 第一波 · copilot 旅程工具(关键路径)

| # | 项 | 状态 | 关键坐标 |
|---|---|---|---|
| W1-1 | `create_skill` 工具(包 `POST /api/skills`,走索引落库) | ✅ 已合并(#526) | 8 测试 + 完整 backend 套件绿;顺带修服务层缺陷:失败创建现在回滚目录,skill_id 不再被半成品毒死 |
| W1-2 | `run_skill` + `get_run_detail` 工具 + 真跑审批放行 | ✅ 随本行同 PR 合入 | 真跑走审批卡(推翻旧"只能 UI 触发"禁令);get_run_detail 有界投影(事件只给计数+错误摘录,final_context 4000 字符截断);9 测试 |
| W1-3 | golden 工具组(list / read / set / delete) | ✅ 随本行同 PR 合入 | 四工具:读免审批、写走审批卡;写直调 golden_diff 服务层(HTTP 层 browser-fallback 护栏是防浏览器绕 Rust 的边界,copilot 后端写=DEF-027 同族的已接受写路径);plan 端点不包(其写计划无人执行);10 测试 |
| W1-4 | `resume_run` + resume 有效性工具 | ✅ 随本行同 PR 合入(与 W1-5 同 PR) | get_resume_validity 免审批;resume_run 走审批卡,支持 checkpoint/节点区间/human_input/context_overrides;9 测试(与 W1-5 合计) |
| W1-5 | `publish_skill` / `fork_skill` 工具 | ✅ 随本行同 PR 合入(与 W1-4 同 PR) | 两工具都走审批卡;publish 直调路由函数并显式供给同组依赖(不复制发布管线);fork 走服务层 |
| W1-6 | 资产纠偏:KB-13 工具清单与"Rust 唯一写者"两处失实 | ✅ 随本行同 PR 合入 | §2 重写为 27 工具两审批档真相 + CLI 表面"无工具"诚实声明;§3 改为三条写路径(Rust D12 / Write-Edit 直写例外 / MCP 审批写) |

#### 第二波 · 引擎(run 路径的诚实与补全)

| # | 项 | 状态 | 关键坐标 |
|---|---|---|---|
| W2-1 | 并联拓扑编译期诊断(暂不支持并联执行,`[F-v3-*]` 码 + 指位) | 待开工 | 校验落点 `packages/graph-agent/src/graph_agent/core/loader.py:1777-1814`;诊断出口 `core/compiler.py` |
| W2-2 | 并联真修:执行态写入迁 delta + 接 `blackboard_data_merge`;同 PR 接 `recursion_limit`;撤 W2-1 拦截 | 待开工 | 裸通道 `core/state.py:226-237`;现成合并器 `runtime/state.py:39-93`;全量写病灶 `runtime/state_mapper.py:207-321`;invoke 点 `core/runner.py:2081` |

#### 第三波 · 人看的面(闭环"看懂"半边)

| # | 项 | 状态 | 关键坐标 |
|---|---|---|---|
| W3-1 | LLM 原始回复查看:PromptInspector 加 Response tab | 待开工 | 数据已齐 `packages/graph-agent/src/graph_agent/core/callback_bridge.py:308-345`;组件 `apps/studio/frontend/src/components/PromptInspector.tsx:61-77` |
| W3-2 | 批量 run 挂线(client 函数 + 挂载点;组件/类型/报告模板已就绪) | 待开工 | 后端 `routers/runs.py:92/316`;孤儿组件 `components/history/BatchSummary.tsx` |
| W3-3 | fork 按钮 + delete skill 接线(消灭 7 处死胡同文案) | 待开工 | 后端 `routers/skills.py:953/985`;文案位 `components/studio/Workspace.tsx:1220` 等 |

### 环境 blocker(在册)

| # | 项 | 状态 | 处置 |
|---|---|---|---|
| B-1 | `gh` CLI 被失效的 `GITHUB_TOKEN` 环境变量压制(keyring 登录本身有效) | 已绕过(2026-07-30) | 调 gh 一律 `env -u GITHUB_TOKEN gh ...`;根治 = 从系统环境变量删除该变量 |
| B-2 | dependabot 开放 PR 积压(#520-#524,2026-07-24 起) | 部分处理 | 预言应验:mcp/pyasn1 共 6 个 CVE 曾把全部 PR 拦死,已修(#527);npm/cargo/actions 的 #520-#524 仍待审合 |

### 在册搁置项(非本冲刺,重启 = 用户裁决)

- Studio IO 数据流设计回写(用户 2026-07-16 原话"全部搁置,先不动");
- ah 编队(用户 2026-07-16 原话"忽略ah编队");
- N5 CLI 路 Studio MCP 工具(本决议后置,见关键设计决定 4);
- gateway 状态投影毛刺(含 `route.status` 与 `ui_state` 双状态字段的实体收敛,勘察 2026-07-30 记录);
- `ah attach master` 落到非活跃窗口(ah 仓缺陷,用户 2026-08-02 裁决"不改 ah" ⇒ 搁置):
  attach 是 session 级(`src/bin/ah.rs:1617-1624`),而新 master 以 `new-window -d` 建窗、
  不切换当前窗口,于是 attach 显示的是上一轮 `remain-on-exit` 留下的死窗格。Studio 侧已用
  `lingering` 状态(残留运行时保持可 Close)规避,取证与范围边界见
  `.kiro/specs/studio-ah-state-contract-v1/decision-2026-08-02-lingering-state-and-cli-autoupdate.md`;
- 更早的跨 spec 延期项见 `docs/deferred-items.md`(停更于 2026-06-21,恢复维护待用户排程)。

### 勘察证据存档

三路勘察(引擎执行能力 / Studio 前后端接线 / copilot 工具面×七节旅程矩阵)的结论要点与 file:line 证据已内联在上方各清单"关键坐标"列;勘察发生于 2026-07-30,基线 commit `1afaf27b`(main,2026-07-16)。若清单坐标与未来代码漂移,以重扫为准,不以本文件为设计权威——本文件只是台账,设计权威仍是 MVP1 设计源体系。
