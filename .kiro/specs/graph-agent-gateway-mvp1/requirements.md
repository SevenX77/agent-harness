# graph-agent-gateway MVP1 实施 — Requirements

> gateway ③b 公共能力内核(`packages/graph-agent-gateway`)MVP1 的**实施** kiro spec。
> **设计 SSOT 不在此** —— 在三轴 alignment `docs/graph-agent-gateway/mvp1/`(baseline/alignment/INDEX)。本 spec 只承载**实施任务**(`tasks.md`);`requirements.md`/`design.md` 指回 alignment、不重写(避免双份 SSOT)。

## 范围

把各模块 alignment 定的目标态落地为代码,按工作流(WS)拆分,走多-AI 流水线执行:
Claude 任务书 → Codex 写失败测试 → 契约门(Claude 审测试是否忠实编码 alignment) → Gemini 实现 → Codex 审 → 回写 baseline → Claude 终审。

## Requirements(指回 alignment)

- 各模块需求 = 对应 `mvp1-alignment.md` 的目标设计;WS→模块→alignment 映射见 [design.md](./design.md)。
- 与 studio 的关系:studio 侧消费另见 `.kiro/specs/studio-llm-gateway-redesign`(studio-scoped);本 spec 限 ③b gateway 包。

## Non-goals(本批不做)

- 06 错误分类(alignment 标「不变」)、predict→engine(卡 engine designer)、05 model 下沉、03-F4 endpoint 拆分 —— 见 `docs/deferred-items.md`(DEF-018/019)。
