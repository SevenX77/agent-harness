# Domain D · 项目过程 (`process/`)

> 这里是**当前正在做什么** + **接下来打算做什么** 的入口。
>
> 内容指向 `.kiro/specs/` (实施中 + Backlog spec) + `tools/` (CLI 工具) + `archive/` (已 ship 的历史 spec)。

← 回 [docs/](../README.md) | 当前基线: [STUDIO-BASELINE-2026-05-17.md](../STUDIO-BASELINE-2026-05-17.md)

---

## Spec 现状清单 (2026-05-17 实测)

| Spec | Status | 完成度 (tasks done/pending) | 下一步 |
|---|---|---|---|
| `studio-canvas-v2` | 🔵 Shipped | 12/12 | 待 archive 到 `.kiro/specs/archive/` |
| `studio-frontend-v21-multifile-editor` | 🔵 Shipped | T-apps-1 ship | 待 archive |
| `graph-agent-v2.1` | 🔵 Shipped | cutover done (9 skills 迁) | 待 archive |
| `graph-agent-v2.1-doc-fixes` | 🔵 Shipped | done | 待 archive |
| `tauri-t2` | 🔵 Shipped | 6/6 | 待 archive |
| `v1-reset-mvp-0..5` (6 个) | 🔵 Shipped / 🔴 Superseded | — | 待 archive |
| `harness-split` | 🔴 Superseded | handoff doc 历史 | 待 archive |
| `predict-v2` | 🟢 Implementing | 1/10 | audit 实际进度, 决定是 push 完成还是 backlog |
| `studio-mvp1` | ⚠️ Outdated tasks | 0/28 (但大部分实际已隐式 ship) | audit + 勾上已 ship 的 |
| `graph-agent-studio` | ⚪ Backlog | 0/59 | audit, 跟当前 baseline 对齐再决定 |
| `graph-agent-optimizations` | ⚪ Backlog | 0/47 | 评估优先级 |
| `graph-agent-state-mgmt-optimization` | ⚪ Backlog | R/D done, 实施 0 | 评估优先级 |
| `studio-skill-git-system` | ⚪ Backlog (空 spec, 无 tasks) | — | 决定是否启动 |
| `tauri-t3` | 🟢 Active (待起草 tasks) | 0/0 | a2 起草 tasks |
| `studio-execution-loop` | 🟢 Drafting (R/D done) | 0/0 (tasks 未起草) | a1 起 backend tasks + apps master 起 frontend tasks |

---

## 当前活跃工作 (2026-05-17 晚)

**主线**: baseline 重整 + 起新 spec 阶段

**完成顺序**:
1. ✅ 派 Gemini 设计科学文档索引 (taxonomy)
2. ✅ 应用索引重整文档 (commit a5d1c2f + 796ff74)
3. ✅ Playwright 实测 Studio 产出能力清单 + 13 张截图归档 `docs/studio/screenshots-2026-05-17/`
4. ✅ 写 STUDIO-BASELINE-2026-05-17 完整版 (§1.2 + §3.1 + §3.2 实测填完)
5. ✅ 起 `studio-execution-loop` spec (research + requirements + design 三件, a2 主笔)
6. ⏳ a1 起 backend tasks.md (P1.1-P1.3 + P3.1 backend 部分)
7. ⏳ apps master 起 frontend tasks.md (P1.4 + P2.1-P2.2 + P3.1 frontend)
8. ⏳ Spec audit + archive 已 ship spec (12 个待 archive)

---

## CLI 工具 (`tools/`, `scripts/`)

待清点, 下个 baseline 迭代写。

---

## Backlog 高优 (按 baseline 目标"让 PM 可用" 排序)

1. **Studio 执行态闭环** (Canvas 接 run 状态 + 现代 trace panel + 还清 React Compiler 20 lint 债) — block 目标核心 "跑完看 phase 输入输出"
2. **tauri-t3** (桌面壳 t3 spec 起草 + 实施) — 实现"PM 不开终端"
3. **studio-mvp1 audit** (28 pending 实际多数 ship, 勾上 + 砍掉跟目标不对齐的)
4. **V1 → V2.1 harness test 终结** (V1 兼容 stub 决定是补 attr 还是废弃)

---

## 已被砍掉 / 不在目标内 (避免规划撞车)

- 跨平台 bundle CI (低优, M2 内事)
- Skill author SDK + 外部贡献者生态 (M3, user 明示删)
- `packages/graph-agent-engine/` (legacy 空死 package, archive)
