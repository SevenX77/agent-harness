# agent-harness 项目文档索引

> 本目录的组织原则: 按"领域职责"切分, 物理隔离历史。
>
> **如果你刚来 / 想知道项目现状**: 读 [STUDIO-BASELINE-2026-05-17.md](./STUDIO-BASELINE-2026-05-17.md) (单一真相文档)。

---

## 锁定目标 (2026-05-17)

**让 PM (user 自己, 未来扩到团队) 可用 Studio — 不开终端、不写 YAML、不拼目录, 在 Studio 里可视化地写 / 改 / 跑 V2.1 skill, 跑完能看到每个 phase 的输入输出。**

---

## 4 大领域 (Domain) + 子目录

| 子目录 | 领域 | 范围 | 文档类型 |
|---|---|---|---|
| [`engine/`](./engine/) | **A · 引擎** | `packages/graph-agent/` (V2.1 SDK 内核) | 架构 / Loader / Executor / Compiler 规则 / Config / Tool 开发 |
| [`studio/`](./studio/) | **B · Studio 工作台** | `apps/studio/{frontend,backend,tauri}` (用户实际看到的 GUI) | 前端组件 / 后端 API / Tauri 桌面壳 / 远程测试 |
| [`skills/`](./skills/) | **C · Skills 库 (fixture)** | `skills/` (测试 corpus, **不是产品**) | Skill 编写规范 / 多版本归档约定 / Claude SKILL 参考资料 |
| [`process/`](./process/) | **D · 项目过程** | `.kiro/specs/` + `tools/` + 路线图 | 当前实施中 spec / Backlog / CLI 使用 |
| [`archive/`](./archive/) | **历史归档** | 已废弃 / 已 superseded 的文档 | V1 reset 系列 / 旧 architecture phase plans / superpowers session plans |

---

## Spec vs Docs 边界 (核心约定)

| 概念 | 角色 | 落点 | 生命周期 |
|---|---|---|---|
| **Spec** (`.kiro/specs/X/`) | "我打算做什么" — 动词, 过程 | `.kiro/specs/` | 起草 → 实施中 → ship → **冻结成历史记录, 不再改** |
| **Doc** (`docs/X.md`) | "现在系统是怎样的" — 名词, 状态 | `docs/{engine,studio,skills,process}/` | **跟着代码一起更新**, 永远反映此刻真相 |

**ship 一个 spec 完, 最后一步必须把"这次做的东西"提炼一段进 `docs/` 对应活文档**。这样 `docs/` 永远是真相, `specs/` 只记录"当时怎么想的"。

---

## 状态标签

每条 Living 文档应在头部声明:

```yaml
---
status: Living    # Living | Outdated-Needs-Sync | Archived
target_goal: "Studio MVP — 让 PM 可用"
linked_code_paths:
  - apps/studio/frontend/src/...
  - apps/studio/backend/app/...
linked_specs:
  - studio-canvas-v2
---
```

Spec 应在头部声明:

```yaml
---
status: Implementing   # Draft | Implementing | Shipped | Deprecated
shipped_at: 2026-05-17  # 仅 Shipped 状态需要
serves_capability: "B.3 画布可视化"
---
```

---

## 历史

- 2026-05-17: 按 4 领域 taxonomy 重整目录, 历史 v1-reset / architecture-old / superpowers-plans 物理 mv 到 `archive/`
- 2026-05-08 之前: 散乱布局 (`docs/architecture/` + `docs/v1-reset/` + `docs/graph_agent_docs/` + `docs/compiler/` + `docs/superpowers/` + `docs/knowledge/` 6 个并列子目录, 文档跟代码不对齐)
