# MVP1 conformance audit + fix plan (2026-06-15)

> PM 怒指:核对 MVP1 实现有没有问题、把功能全部点一遍、别连最基本功能都坏。10-agent 审计(每区域 design vs 真代码)+ synth triage。全量输出:`/private/tmp/.../tasks/wjax3lk87.output`(226KB)。

## Synth 总判:核心编辑器 = BROKEN（但 REQ-1 已修)
- ✅ **REQ-1 TB 竖排 = 已修**(commit 本轮;synth 复核 `lib/layout.ts:33 rankdir TB` + handles Top/Bottom 确认,"竖排没实现"不再成立;审计两个 region 看的是 stale 快照)。
- 其余 PM 三连 + 更多 **真坏**(见下)。

## 关键坏的基本功能(crit)
1. **加节点 "+" 缺 + 加节点链路整条死**:无画布/节点 "+";加 phase 只在右键菜单,且 `defaultPhaseMarkdown` 脚手架写 `mode:` 等违 FROZEN 字段 → 引擎编译 FATAL → "Could not create phase" + 残留孤儿目录。
2. **Properties 编错字段 + 数据破坏**:能存但编的是废弃 V2.x 字段(mode/system_prompt/exit_contract/python_callable/target_skill),**静默删 llm_role**,存出编译不过的 frontmatter。
3. **子图拓扑展开 = 硬编码 mock**:`SubgraphInline.tsx:19-21` 写死 entry/execute/return;后端不发子图 path;无下钻/面包屑。
4. **I/O 面板假文件 + 无字段级编辑器**:投影两个假可编辑 json(`input/schema.json`+`input/sample.json`,autosave 到死路径=静默丢数据);**根本没有字段级 io schema 编辑器**。
5. **真 agent(SKILL.md)节点渲染成 LOGIC**:node-kind 分类器忽略 mode='agent'。
6. **首节点假绿灯**:`build-nodes.ts:193` 没跑就给第一个节点 fake success。

## 修复波次(按 triage rank;FROZEN 字段权威 = engine `01-contract/02-skill-syntax/mvp1-alignment.md` §2.2-2.5)
**Wave 1(并行,文件不冲突,无 PM 决策 blocker,引擎 FROZEN schema 即契约)**:
- R1 `defaultPhaseMarkdown` 重写成 FROZEN-clean 三类脚手架(`canvas-authoring.ts`)— 解锁 R2。
- R3 Properties 重建 FROZEN 白名单 read+write、停删 llm_role、去废弃字段(`PropertiesPanel.tsx`+`phase-frontmatter.ts`)— 数据破坏,紧急。**边界(设计已定,非 PM 决策)**:Properties=phase frontmatter 白名单;**io schema 归 i/o 面板**(R7),两者不重叠。
- R6+R8 node-kind 加 'agent' + 去首节点假绿(`build-nodes.ts`)— near-trivial。
- R7 去假 io 文件 + 建字段级 io schema 编辑器(inputs+outputs,写 GRAPH.md frontmatter)(`panel-files.ts`+`InputPanel.tsx`)。
- R4 后端 `_graph_topology` 发子图绝对 path + child-graph-by-path resolver 端点(`skills.py`)— BACKEND-FIRST,解锁 R5。

**Wave 2(依赖 Wave 1)**:R2 加节点 "+" UI(依赖 R1)、R5 SubgraphInline 真 loader(依赖 R4)。

**后续波次**:R9 子图下钻+面包屑、R10 node 三通道(compile badge/status/debug)、R16/17 copilot session 持久化+tab bar、R18 @mention composer(tiptap,PM 已批"加")、R19-21 settings(6态/role test 持久化/bundle 引用)、R26 validation_fail 红节点、R27 batch UI、R28 刷新 stale FROZEN 文档、R29 删死码。

## 需 PM 决策(到该波次前先确认,留最终报告)
- **golden 模型**:FROZEN 要 per-node author golden 替整 run 快照 + predict mock-by-golden;现是旧整-run 快照。**大后端重做**,确认 MVP1 范围 + per-node 存储形状。
- **node-level resume**:05_debugging 要从选定失败节点精确续跑;现仅 run-level(ResumeReq 无 node/checkpoint 字段)。最大后端耦合缺口,确认是否本期。
- **copilot 范围**:@mention(已批加)、build-skill 向导(PM 已说先不做)、图片附件(缺)。确认哪些本期。
- **Bash HITL**:现 deny-only;确认是否本期做双向 WS approve/deny(DEF-024)。

## 验证
每波 gatekeep:tsc/eslint/vitest 全绿 + 新单测 + git diff 核 api/llm.ts/KEEP-MAIN 零改动;真 .app 鼠标复验(屏幕录制授权恢复后)。**screenshot 当前 infra 失败(SCContentFilter nil,5 retries),记录,不阻塞代码修复**。
