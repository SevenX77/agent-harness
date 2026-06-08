# Task Spec Standard

> Status: living standard for multi-agent task requirements and handoffs.
> Scope: Studio / engine / gateway MVP work where one agent writes requirements, another writes RED tests, and another may implement.

## 一、流水线铁律

1. **需求书不是实现计划**。需求书只写目标、SSOT、文件锁、RED 清单、验收和不做范围；不得写逐步改法、函数体、before/after patch 或实现阶段。
2. **RED 先行**。任何实现或修复任务必须先有会失败的测试。测试失败原因必须来自目标契约未满足，而不是人为制造无关失败。
3. **人工确认闸门**。写完需求书后，必须经过 RED 测试、PM 契约门和用户在聊天窗口明确确认，才能进入实现。系统自动审批不算确认。
4. **实现者只能把已批准 RED 做到 GREEN**。实现者不得削弱 RED、删除断言、扩大文件范围或顺手修未授权问题。
5. **baseline 回写只能在实现落地后发生**。baseline 写真实现状，不把目标态提前写成 live。

## 二、SSOT 与证据优先级

1. **MVP1 设计文档是唯一目标真相源**。需求书必须先读并引用相关 MVP1 workflow、capability、region、platform、engine/gateway alignment 文档；判断目标行为时不得把当前代码、旧测试或 mvp0 文档放在 MVP1 之上。
2. **当前代码只作 baseline / drift 证据**。代码说明现在发生了什么，不说明 MVP1 应该做什么。若代码与 MVP1 冲突，需求书应把冲突写成待 RED 捕获的 drift。
3. **mvp0 / FROZEN 只能在 MVP1 明确继承时作为下级依据**。如果 MVP1 文档已反转或放松某条 mvp0 规则，必须以 MVP1 为准。不得只读 mvp0 FROZEN 或当前实现就推断 MVP1 目标。
4. **外部契约必须整棵核实**。涉及 engine 或 gateway 时，需求书作者必须读对应 `docs/engine/mvp1/` 或 `docs/graph-agent-gateway/mvp1/` 的相关 alignment / baseline / README，而不是只看一个旧 spec、一个当前源码文件或一个子 agent 转述。
5. **冲突必须写明裁决**。若 Studio UI spec、MVP1 workflow、engine/gateway 文档之间存在看似冲突，需求书必须写明哪份是该行为的上位 SSOT、哪份只作为 UI/现状/历史参考。
6. **不存在的文档不能当 SSOT**。如果计划或旧需求书引用的文件不存在，需求书必须记录为文档锚点缺口，并改用当前真实存在的 MVP1 文档。

## 三、需求书结构

每份 WS 需求书必须包含 frontmatter 和 12 个固定章节：

1. 目标：说明要解决的用户/系统问题，以及为什么这个 WS 是前置或旁路。
2. SSOT 指针：列出现实存在的 MVP1 目标文档、baseline 文档、外部契约和必读源码；说明现状证据不能覆盖目标真相。
3. 文件归属：按实施计划写 owns_files、共享文件串行策略、禁止触碰范围。
4. 现状锚点：只描述 baseline/drift，不把旧行为写成目标。
5. 目标行为：写可测契约，不写具体改法。
6. 测试要求：列出 RED 测试、真实 e2e/手动验证、no-fake 边界和旧测试清理要求。
7. 硬依赖约束：写 pinned / floating-draft / blocked 状态。
8. 验收标准：用 checklist 写硬退出条件。
9. 不做：写清范围锁和 deferred 处理。
10. baseline 回写指令：只允许按真实代码回写。
11. 评审检查点：写 PM 契约门、Codex 审、PM 终审关注点。
12. 给 Codex 的交接：说明 task.md / Gemini prompt 的后续边界。

## 四、RED 与旧测试清理

1. **先审旧测试**。写 RED 前，必须搜索本 WS owns_files 相关的现有测试，找出断言 MVP0 行为、mock 成功、旧字段、旧写盘路径、旧 API 或当前实现假绿的测试。
2. **旧测试不能绑架 MVP1**。若旧测试与 MVP1 冲突，必须先把它改写为 MVP1 RED、删除过期断言或标为 deferred/blocked；不得通过恢复旧行为让它继续通过。
3. **旧测试清理也要 TDD 化**。改写测试时要证明旧实现会失败，并在契约门说明失败点为何对应 MVP1 目标。不能只把测试改宽。
4. **不许 fake mock 到绿**。允许 mock 外部网络、时间、SDK 进程边界，但不能 mock 掉本 WS 要验证的核心事实源。例如不能 mock 掉 native writer、真实 DTO、route handoff、SDK parity、SkillDetail 刷新、文件 hash conflict 或 evidence 写回。
5. **回归锁要诚实标注**。如果某条目标行为现状已 GREEN，它是回归锁，不是 RED。需求书和 task.md 必须如实标注，不能伪造失败。
6. **旧测试清理必须进入验收**。每份需求书的 §8 必须要求记录哪些 MVP0 旧测试被改写/删除/保留，以及保留理由。

## 五、外部契约与推断纪律

1. **不得用局部旧证据推出全局目标**。读到 mvp0 FROZEN、当前 engine 代码、manifest model 或旧测试，只能得出“现状/历史是这样”，不能直接得出“MVP1 只认这样”。
2. **必须沿设计树回溯**。例如子图规则要同时核对 Studio authoring workflow、phase-editing alignment、graph-authoring alignment、engine physical-layout、skill-syntax、resolver 相关文档；只有这些共同支持的结论才能写进需求书。
3. **放松或反转要显式写出**。如果 MVP1 放松了 mvp0 的严格规则，例如子图不再严格 1:1 或 path 解析替代 registry 推断，需求书必须点名禁止旧推断。
4. **当前实现未更新不是目标阻塞**。如果 MVP1 设计已定而当前代码未更新，需求书应把它写成 drift / RED，而不是把旧代码当 blocked。
5. **blocked 只给真正外部未定契约**。如果只是代码没实现，不能标 blocked；如果 engine/gateway API 字段确实未 pinned，才写 floating-draft 或 blocked。

## 六、UI 与后端专项规则

1. 涉及 `apps/studio/frontend` UI 时，必须读 `docs/development/FRONTEND_UI_SPEC.md` §2，先查 `apps/studio/frontend/src/components/ui/`，并要求 Playwright 或浏览器真实点击验证和窄宽度检查。
2. 涉及后端 FastAPI/Python 改动时，需求书必须要求完成后重启 Studio App 或重新拉起 `cd apps/studio/tauri && cargo tauri dev`。
3. 涉及 Tauri/native-fs 时，必须要求 Tauri bridge 或等价原生路径验证；普通浏览器 fallback 不能证明原生能力。

## 七、评审硬栏

评审者必须拒绝以下需求书：

- 把 MVP0/current code 写成 MVP1 目标。
- 没读完整相关 MVP1 设计树就下外部契约结论。
- 没有旧测试清理要求。
- 没有明确 no-fake 边界。
- 引用不存在的 SSOT 文件。
- 对共享文件没有串行/排队说明。
- 把实现步骤、代码片段或逐行改法写进需求书。
- 让实现者可以通过恢复旧行为、mock 核心事实源或削弱测试过关。

## 八、术语

- **SSOT**：Single Source of Truth，目标真相源。
- **baseline**：当前实现证据，只说明现状，不定义目标。
- **alignment**：MVP 目标对齐文档，是需求书的主要目标来源。
- **RED**：预期先失败的测试，用来证明当前实现未满足目标。
- **回归锁**：目标当前已满足的测试；它应防止回归，但不是 RED。
- **floating-draft**：外部契约有目标方向但字段/接口仍可能调整。
- **blocked**：外部契约缺失到无法诚实写 RED 或实现。
