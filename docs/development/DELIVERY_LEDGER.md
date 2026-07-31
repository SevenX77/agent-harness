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
4. **明确后置项**(重启条件 = 用户重新裁决):CLI 路 MCP 暴露(N5,需后端先长出对外 MCP 出口);新建向导/模板 UI(copilot 成为新建主路后降级);gateway 状态投影 7 条毛刺(不阻断闭环);文档系统工程(类型学 / docs 门禁 / AGENTS.md 瘦身)。

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
- 更早的跨 spec 延期项见 `docs/deferred-items.md`(停更于 2026-06-21,恢复维护待用户排程)。

### 勘察证据存档

三路勘察(引擎执行能力 / Studio 前后端接线 / copilot 工具面×七节旅程矩阵)的结论要点与 file:line 证据已内联在上方各清单"关键坐标"列;勘察发生于 2026-07-30,基线 commit `1afaf27b`(main,2026-07-16)。若清单坐标与未来代码漂移,以重扫为准,不以本文件为设计权威——本文件只是台账,设计权威仍是 MVP1 设计源体系。
