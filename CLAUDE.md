# Claude Code — Agent Harness

The canonical, cross-tool project rules live in **[AGENTS.md](AGENTS.md)** —
baseline & environment, CI gates, the three-module architecture, and the
standard documents. Read it first; it is imported below so it is always in
context.

> **Frontend UI task?** Before planning or touching anything under
> `apps/studio/frontend`, first read that folder's own
> [`apps/studio/frontend/CLAUDE.md`](apps/studio/frontend/CLAUDE.md) — a
> directory-scoped override that swaps the heavy multi-agent PM workflow for a
> lightweight single-agent loop. Claude Code only auto-loads that nested file
> *lazily* (the moment you first read a file in that subtree), so a session
> starting at the repo root won't have it yet — load it explicitly at task start.

## 铁律:论据先行,绝不臆测(Evidence-before-claims)

抛任何观点前,必须先找到论据并把论据**原样写出来**,再下结论。禁止"我觉得/应该是/大概"式臆测。具体:

- **当我说"设计意图是 X"**:必须引用**权威设计文件**(MVP1 设计源:`docs/studio/mvp1/` 的 `mvp1-alignment.md` / `README.md` / `DESIGN_UNITS_INDEX.md`、`docs/mvp1-three-module-interface-design-and-changes-2026-06-11/`、各 work-order)、**明确的决策记录**、或**用户的原话**来论证,并给出**文件路径 + 行号 + 引文**。
  - `docs/studio/mvp1/_impl/frontend-handbook/` 下的 `tpl-*.json` / `index.html` 是 **agent 自动生成的派生视图,不是设计真相**,不能拿它当"设计意图"的权威论据;它和 MVP1 设计源冲突时以设计源为准。引用它最多只能说"手册如此记录",且必须同时去设计源核对。
- **当我说"现在的实现是 X"**:必须给出**确切的代码**(文件路径 + 行号 + 代码片段)。不能凭印象描述行为。
- **找不到论据时**:直接说"我在 X/Y/Z 都查过,没找到权威依据",**不允许**用猜测填补,更不允许把猜测包装成结论。
- **区分"设计怎么写"与"代码怎么做"**:两者各自独立举证;若二者打架,按 AGENTS.md「MVP1 design = source of truth」以设计为准并指出 drift。

违反以上任意一条 = 直接出错。宁可说"还没坐实"也不许猜。

@AGENTS.md
