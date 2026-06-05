# Studio docs — MVP1 / 新设计(重设计目标)

> **新设计文档**(MVP1 重设计目标)的三维体系。旧设计(MVP0 当前实现)baseline 在 [`../mvp0/`](../mvp0/)。
> 治理总纲 [`../INDEX.md`](../INDEX.md);**设计权威(最新)** = `01_workflows/` 走查 + [`../_reorg/workflow-action-catalog.md`](../_reorg/workflow-action-catalog.md) + `../_reorg/alignment-notes.md` + `01_workflows/00_settings-ux-spec.md`。(`.kiro/specs/studio-*` 仅**历史参考**、不作 SSOT。)
> 设计单元索引(轴③ · R8 枢纽)= [`DESIGN_UNITS_INDEX.md`](./DESIGN_UNITS_INDEX.md)。

- `01_workflows/` — ① 用户旅程脊柱(7 节点, 含 `00_settings` 运行底座)。
- `02_capabilities/` — ② 能力(14, 跨区域数据流/行为)。
- `03_regions/` — ③ UI 区域(12, 组件结构/状态)。
- `04_platform/` — 基础设施: 后端三分 + state-engine(D10) + i18n 横切。

## Scope — 做什么 / 不做什么（四层边界 · 审计 Q5 权威）

studio 文档**永远分四层**（权威：gateway `packages/graph-agent-gateway/README.md` §2 + `01_workflows/00_settings-ux-spec.md` §6.0 + [`../../graph-agent-gateway/mvp1/`](../../graph-agent-gateway/mvp1/)）。**判据一句话：换个完全不同的 app 装上 gateway，这能力还原样能用吗？能 = ③b 公共内核，不能 = ③a 应用加工。**

| 层 | 是什么 | 代码 |
|---|---|---|
| ① 前端 | UI + 录入 + 渲染（只投影后端） | `apps/studio/frontend` |
| ② 后端(rust) | 本地写(D12) + sidecar 拉起 + copilot session 落盘；设置数据永不 Rust | tauri |
| **③a Studio 应用加工** | **studio 文档主战场** | `apps/studio/backend` |
| **③b gateway 公共内核** | **studio 不拥有，只引用** | `packages/graph-agent-gateway` |

**✅ 做什么（studio 文档 own）**：UI / 交互 / 区域结构 / 能力数据流 + **应用加工四件事(③a)**：① UI 渲染 ② 产品策略（默认推荐 / 浮出 / 弃用 / family 折叠）③ 实际 SDK 调用方式 ④ 存储介质注入。

**❌ 不做什么（NON-GOALS —— 不在 studio 写实现、只引用 SSOT；写了 = 撞旧源违规）**：
- **gateway 公共内核(③b)**：model group 分组 / **6 态标准投影** / **materialize 编排** / endpoint 标准化 + canonical id / draft 知识库 / 批量探测策略 / 熔断持久化 → 归 `packages/graph-agent-gateway`，引用 [`../../graph-agent-gateway/mvp1/`](../../graph-agent-gateway/mvp1/)，**不在 studio 复制**。
- **engine 拥有的契约**：子图 path 解析 / golden 落点 / skill 语法 / 错误码 / resolver 协议 / checkpoint·resume → 归 engine，引用 [`../../engine/mvp1/`](../../engine/mvp1/)，**不在 studio 复制**。
- 握手：③a 把"角色编排结构 + 意图"交 ③b 的 materialize → fallback 链；③b 看得到结构、**看不到** UI 怎么编出来的。

---

> **MVP1 内的延后项(deferred)**: copilot brain 场景 / canvas REQ-8 策略开关 / trace REQ-7 结构化 diff / debug-resume DEF-005 —— 在各文档内标 `target-design` 且依赖引擎, 见 catalog。
