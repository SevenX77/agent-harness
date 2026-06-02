# 交接 Prompt — Studio 文档重组:续做 workflow 对齐(重新对齐 FROZEN spec + 真实代码)

> 用法: 新 session 清 context 后, 把本文件 `@docs/studio/_reorg/NEXT-SESSION-PROMPT.md` 带进去即可。

## 你在做什么

继续 Skill Studio(`apps/studio`)的**文档体系重组**:走 6 个用户 workflow 节点, 为每个动作对齐 **capability(能力)+ UI region(区域)+ 实现状态**, 驱动一个三维文档分类。这是**文档/设计工作, 不写应用代码**。

## 先读这些(按序, 别跳)

1. `docs/studio/INDEX.md` — **治理总纲**:三维模型(`01_workflows`①/`02_capabilities`②/`03_regions`③ + `04_platform`)、所有权不变量、路由决策树、status 词表、权威注册表(13 能力/12 区域/平台)、各 tier 文档模板。**全部已锁,不要重新讨论。**
2. `docs/studio/_reorg/alignment-notes.md` — **权威决策日志**(D1–D11 + 批次2核实 + 方法 M1/教训 L1)。这是真相源,含 PM 原话。
3. `docs/engine/skill-spec/00-FORMAT-GROUND-TRUTH.md` — **FROZEN、PM 逐条拍板**的 skill 文件格式唯一权威。配套 `02-graph-md-spec.md`/`05-agent-md-spec.md`/`03-logic-md-spec.md`/`04-subgraph-md-spec.md`。
4. `docs/studio/_reorg/workflow-derivation.md` — 最初 AI 推导的 ~120 动作清单。⚠️ **字段/spec 细节不可信**(基于 stale code + stale workflow doc)。只当"动作清单骨架"用,字段真相以 alignment-notes 逐批修正版为准。

## 铁律教训(全程贯彻 —— 这就是要重做的原因)

**任何文档都可能过时。采信前必须交叉验证:FROZEN spec + 当前代码 + 其他文档 + git。**
- 权威序(按关注点):skill **格式/字段** → `00-FORMAT-GROUND-TRUTH.md`(FROZEN)> 代码 > workflow-doc/derivation;**"实际实现/接线状态"** → 当前代码 > 文档。
- `01_workflows/*` 和 `workflow-derivation.md` 对 spec 字段是 STALE 的 —— 当假说去核实,绝不当真相。
- 代码在跑但实现的是过时格式 → 标 `stale-code`(区别于 stale-doc)。
- 不要问能自己核实的东西(先读 spec/代码/git)。

## 已锁决策(别重开;原话见 alignment-notes)

- **文档分类**:三维 + 平台(INDEX)。
- **IDE/workspace 模型(D11)**:skill = 文件夹;Home = 打开文件夹 + Recent(MRU);**无注册表**;子图按 `SUBGRAPH.md`/agent phase 内**显式 path**(D7);copilot cwd scope 必须含被引用子图 path。
- **不卡导入(D2)**:开任意文件夹,compile + copilot 修成标准 skill。
- **后端三分(D10)**:`gateway`(Python sidecar)/ `engine`(Python sidecar, `packages/graph-agent`)/ `native-fs + 编排`(Rust)/ `state-engine`(前端 ipc)。两 sidecar 启动期由 Rust 拉起,但**非全屏 bootstrap gate** —— 壳+FS 立即渲染,依赖 sidecar 的功能 skeleton + 全局就绪指示。RuntimeGate 退役。
- **copilot 持久化(D8, MUST)**:对话+session 落盘(Rust 写 skill 目录),退出再进恢复一模一样,跨窗口。
- **多窗口(D9)**:做(三分架构下不难)。
- **跨切 NFR(D6)**:所有后端数据组件 skeleton + lazy load(available models 巨长列表为首要)。
- **删**:外部 IDE 联动(D3)、mod+n(D4)。
- **copilot 建技能(D5)**:由一个 brainstorming 式 graph skill 支撑(graph_skill 背景 + skill spec 渐进暴露 + template few-shot)。
- status 词表含 `stale-code`。

## 进度

- **批次 1 `01_init`**:已对齐。修正后动作集在 alignment-notes(skill-registry → `skill-workspace`;welcome 区域;runtime-bootstrap → eager-spawn NFR)。
- **批次 2 `02_authoring`**:**核实已完成**。发现挂载的节点编辑表单 `apps/studio/frontend/src/components/studio/panels/phase-frontmatter.ts` 是 **stale-code** —— 写 `mode`/`<system_prompt>`/`<exit_contract>`/`<python_callable>`、删 `validator`/`llm_role`,与 FROZEN spec 几乎逐字段冲突。Ground-truth phase 字段集已在 alignment-notes「批次2」记录。**尚未重新呈现给 PM。**

## 任务(从这里续)

跟 PM 逐批重新对齐 workflow,**每批先核实(FROZEN spec + 真实代码)再呈现**:

1. **重做批次 2 `02_authoring`**:
   - Half A(宏观 manifest + 拓扑 + 子图):修正 manifest 动作(`name`/`schema_version`/`llm_role`/`description`/`phases`/`io` —— **无 `type: simple/graph`**)、io 动作(内联手写 JSON Schema,schema-infer 已过时)等。
   - Half B(微观节点表单按 ground-truth 字段集 + compile/lint/predict 门控 + 冲突/保存):呈现 spec 目标字段,当前表单标 `stale-code`。
   - 每个动作:`动作 | capability | region | status | 证据(已核实的 file:line)`。
2. **再做批次 3–6**(`03_prediction`/`04_execution`/`05_debugging`/`06_eval`):每批呈现前,先把 spec 相关动作对照对应 engine 文档核实:
   - 预测/执行/评估:`docs/engine/state-and-io-contract/`、`docs/engine/execution-runtime/`、`docs/engine/tracing-and-observability/`、`docs/graph-agent-gateway/`、`docs/engine/skill-compilation/`、`docs/engine/public-api-contract.md`。
   - 调试(resume/checkpoint):`docs/engine/execution-runtime/`、`tracing-and-observability/`。
   - **同时核实当前前后端代码,别信 derivation。**
3. **节奏**:一个节点(大节点拆半)一轮;每轮把 PM 决策**原话**记进 alignment-notes;derivation 旧表视为已被取代。
4. **终点**:得到完全 PM 对齐、spec 落地的动作清单 → 再按 INDEX 模板正式撰写 `02_capabilities/*` 和 `03_regions/*` 文档。

## 别做

- 别改应用代码(这是文档/设计工作)。
- 别重开已锁决策。
- 别把 derivation 的字段名不经核实就搬进结论。
