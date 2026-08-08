# Timeline/Trace:viewed-run 状态模型 + predict 入列 + Trace UI 统一(决议)

- 日期:2026-08-07
- 状态:已批准(PM 口头批准「修复他们,并且优化 UI,统一 UI 的样式,用 shadcn 组件,参考 copilot 的 tracing 流」),本文件为落盘决议
- 权威设计源:`docs/studio/mvp1/01_workflows/04_run-and-verify.md` §D、
  `docs/studio/mvp1/02_capabilities/trace-observability/mvp1-alignment.md`、
  `docs/studio/mvp1/03_regions/timeline/mvp1-alignment.md`

## 1. 背景:已核实的四个缺陷

以下缺陷全部以代码坐标坐实(2026-08-07 主会话审计):

- **A · 跑过一次 run 后历史列表永久不可达。** timeline 面板分支只看
  `runId`(`Panels.tsx` timeline 分支),而 `runId` 只在切 skill 时清空
  (`Workspace.tsx` effect 依赖 `[currentSkillId]`);`run_ended` 不触发任何回列表
  路径,TracePanel 也没有返回控件。违反 `04_run-and-verify.md:81`
  「run 后:predict/run 列表 → 点某次看」。
- **B · predict 在 timeline 两头落空。** predict 已落 `run_metadata.json`
  (`run_manager.record_predict_outcome`)并进入 `list_runs` glob,但元数据没有
  kind 判别字段,前端无法按 PM 原话「predict 历史行仅用 icon 与真实 run 行区分」
  渲染;live 时 `gate-state.ts` 只对 `gate === "run"` 发 `follow-run`,predict
  started 只发 `open-trace`——面板被切过去却仍显示上一次 run 的事件流(内容与
  标签不符)。
- **C · Full Trace 文档与所选 run 脱钩。** `trace-doc` 面板永远读实时流
  `runStream.events`;历史 run 的事件被 `TimelinePanel` 局部 state 私藏,
  查看历史 run 时打开 Full Trace 读到的不是这次 run。
- **D · 命名三口径打架。** Toolbar 第 4 格 `Event Trace` / 无 run 时面板标题
  `Timeline` / 有 run 时 `Event Trace` / 第 5 格 `Full Trace`。
  `04_run-and-verify.md:53`(C8)记录在案未正名。
- 附 **G · 死分支**:`TimelinePanel` 内部的 `selectedEdge → EdgeContextView`
  分支被 `Panels.tsx` 上游同名分支永久短路,且漏传 `onResumeDownstream`。

## 2. 决策

### D1 · viewed-run 状态模型(修 A/C)

timeline 区域的唯一状态 = 「当前查看哪次 run」,与「当前订阅哪个实时流」分离:

- Workspace 新增 `viewedRun: { runId: string; source: "live" | "history" } | null`。
  - `source: "live"`:事件来自 `useRunStream(runId)`(WS 实时流)。
  - `source: "history"`:事件来自 `GET /skills/{id}/runs/{run_id}`(一次性拉取,
    缓存在 Workspace 层,timeline 与 trace-doc 共读)。
- 面板分流(`Panels.tsx` timeline 分支)改为:
  `selectedEdge → EdgeContextView` > `viewedRun → TracePanel(带返回)` >
  `TimelinePanel 历史列表`。不再以 `runId` 分流。
- 触发规则:
  - gate `started`(predict **和** run)→ `follow-run` 置 `runId` 并置
    `viewedRun = { runId, source: "live" }`(修 B 的 live 半边)。
  - 列表点某行 → `viewedRun = { runId, source: "history" }`(该 run 恰是仍在流
    的 live run 时用 `source: "live"` 复用流)。
  - TracePanel 返回按钮 → `viewedRun = null`(任何时刻可回列表;run 结束后
    停留在已完成 trace 上,不自动弹走)。
  - 切 skill → 全清(既有行为)。
- `trace-doc` 面板读 viewed-run 的同一事件源,不再固定读实时流。
- Compare/Golden/Resume/HITL 等**动作**仍只绑 live run(`canCompare` 等只在
  `source === "live"` 时接线),查看历史 run 是只读回看——与现状语义一致。

### D2 · predict 元数据判别字段(修 B 的落盘半边)

- 后端 `RunMetadata` 新增 `kind: Literal["run", "predict"] = "run"`;
  `record_predict_outcome` 与 `register_transient_predict_run` 写 `kind="predict"`。
  前端 `RunMetadata` 同步加 `kind?: "run" | "predict"`。
  按「不向后兼容」原则不做 id 前缀嗅探、不写双格式读取;旧的无 kind 数据靠
  default `"run"` 自然收敛(predict 旧数据显示为 run 行,数据可弃,不迁移)。
- `TimelinePanel` 行渲染:predict 行仅换 icon(`FlaskConical`,语义=试飞),
  其余样式与 run 行一致(PM 原话锁定)。

### D3 · 命名统一(修 D)

一套口径:**Timeline**(区域,Toolbar 第 4 格 + 列表标题)/ **Trace**(某次
run 的事件流视图,标题 = run 身份行,不再挂第二个面板名)/ **Full Trace**
(第 5 格,只读文档)。Toolbar 第 4 格 label 由 `Event Trace` 改为 `Timeline`。

### D4 · Trace UI 统一到 shadcn + copilot tracing 语言

依据 `FRONTEND_UI_SPEC.md` §2:

- 所有手写 `<button className=…>` 换本地 `@/components/ui/button`(ghost /
  secondary / destructive 语义 variant);`Link views` 换 `Switch`;搜索框换
  `InputGroup`;compare tab 条继续 `role="tablist"` 但样式走 token。
- **流式贴底**:live trace 列表接入本地 `components/ui/message-scroller.tsx`
  (spec §2.6 明文「未来 trace 流」必须用它),流式贴底跟随 + 用户上滚释放 +
  回到底部按钮;虚拟化行高逻辑保留,滚动容器换 MessageScroller viewport。
- **行样式对齐 copilot**:次要信息淡一号(`text-muted-foreground`,hover 恢复);
  折叠语言与 `copilot/tool-call-bubble.tsx` 同族(语义 verb + chevron/details);
  hover 用背景变化不用边框跳动(spec §2.7);错误行保持 destructive。
- 每行补时刻显示(`HH:MM:SS`,muted mono)——设计源类比 LangSmith 竖向时间轴,
  时间轴须有时间;此为 UI 优化裁量,不改事件数据。
- 删 `TimelinePanel` 死分支(G)。

## 3. 验收判据

1. 同一 skill 内:Run → run 结束 → 点返回 → 看到历史列表(含刚结束的 run);
   再点该行 → 回看其完整 trace。(修 A)
2. 点 Predict:timeline 面板显示**这次 predict** 的实时事件流(不是上次 run);
   结束后列表出现 predict 行,与 run 行仅 icon 不同。(修 B)
3. 查看某历史 run 时切到 Full Trace:文档内容 = 该 run 的事件。(修 C)
4. Toolbar 第 4 格、列表标题、trace 视图三处命名一致(D3 口径)。(修 D)
5. 前端四门禁 + 后端 ruff/mypy/pytest 全绿;新增业务逻辑(gate-state 效果、
   viewed-run 归约、kind 字段)各有先红后绿的测试。
6. trace 相关组件无手写 `<button>`、无硬编码色值;live 流贴底跟随可释放。

## 4. 明确不做

- run 概要层(D3/D4 的 target-design「run_id 概要 → 按钮进完整 timeline」)
  本轮不建——属新增设计件,另行排期;本轮点行直接进完整 trace(现状语义)。
- 批量运行 UI、RunDetailDrawer、模型对比机制变更:不碰。
- 不为旧 `run_metadata.json` 写迁移/双读逻辑。
