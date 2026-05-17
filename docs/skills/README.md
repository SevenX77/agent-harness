# Domain C · Skills 库 (`skills/`)

> **重要定位 (2026-05-17 user lock)**: `skills/` 是 **fixture corpus**, 不是产品。
>
> 目的 = 提供测试样本覆盖 Studio + Engine 的功能矩阵, 不是给 user 跑业务。
>
> 因此: 多版本归档 by design, broken skill 当反例 corpus OK, **不追求** "全 skill 跑通"。

← 回 [docs/](../README.md) | 当前基线: [STUDIO-BASELINE-2026-05-17.md](../STUDIO-BASELINE-2026-05-17.md)

---

## Living 文档清单

| 文档 | 描述 | Status |
|---|---|---|
| [SKILL_AUTHORING_GUIDE.md](./SKILL_AUTHORING_GUIDE.md) | V2.1 skill 编写规范 (`SKILL.md` + `GRAPH.md` + `phases/<phase>/` 目录结构) | ⚠️ 需 sync (V2.1 cutover 后未 audit) |
| [references/The-Complete-Guide-to-Building-Skill-for-Claude.pdf](./references/The-Complete-Guide-to-Building-Skill-for-Claude.pdf) | Anthropic 官方 Claude SKILL 完整指南 (graph skill 沿用其基础契约) | ✅ Living (外部参考) |

---

## skills/ 目录现状 (实测)

```
skills/
├── text-segmentation/      # V2.1 完整, 有 versions/ 多版本归档 (v0/v1/v2/v3)
├── event-extraction/       # V2.1 完整
├── batch-analysis/         # V2.1 完整, fan-out 已修
├── global-synthesis/       # V2.1 完整
├── hello-world/            # V2.1 最小 fixture
├── producer/               # V2.1 完整
├── product-manual/         # V2.1 完整
├── examples/               # SKILL 示例集合
├── shared/                 # skill 间共享资源
└── _v2_pending/            # V1 待迁 backlog (story-deconstruction / adaptation_v1)
```

7 个真 V2.1 skill 都有 `phases/<phase>/` 真目录结构 (含 `SKILL.md` / `LOGIC.md` / `SUBGRAPH.md` / `io/inputs.json` / `io/outputs.json`)。

---

## 版本归档约定 (by design)

每个 skill 鼓励维护一个 `versions/` 子目录, 保留历史尝试 (作 A/B / regression 对比基线)。

**示例**: `skills/text-segmentation/versions/`:

| 版本目录 | 内容 |
|---|---|
| `v0-main-baseline/` | 137 行 system prompt 完整重写 (历史 baseline) |
| `v1-codex-attempt/` | Codex (a1) 加退出契约 + 瘦身 system prompt |
| `v2-gemini-rewrite-r1/` | Gemini (a2) 渐进披露 + 退出契约前置 |
| `v3-gemini-rewrite-r2/` | 最新版 |

详见 `skills/text-segmentation/versions/README.md`。

**待办**: 把这个 versioning 模式 generalize 到其他 6 个真 skill (优先 batch-analysis / event-extraction / global-synthesis 这种迭代多的)。

---

## 哪些 skill **暂不追求跑通** (by design, 不是 bug)

- `_v2_pending/story-deconstruction` — 依赖 parallel_delegate + subgraph runtime, V1 期间被砍, 等 V2 设计成熟回归
- `_v2_pending/adaptation_v1` — V1 遗留
- 任何 broken 的 V2.1 skill = **反例 corpus** (用来测试 Engine 是否能正确报错 / Studio 是否能正确显示错误)

---

## 已被砍掉的方向

- **Skill author SDK + 外部贡献者生态** — user 2026-05-17 明示 skills 是 fixture, 不追求外部贡献。M3 milestone 从路线图删除。
