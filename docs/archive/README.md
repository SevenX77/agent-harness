# 历史归档 (archive/)

> 这里的所有文档都是 **💀 Archived** 状态: 已被 superseded / 已废弃 / 已 ship 的中间过程产物。
>
> **不要**修改这里的文件来反映当前现状 — 当前现状去 `docs/{engine,studio,skills,process}/` 找。这里的文件保留是为了**审计 trail** 和**回顾设计演进**。

---

## 子目录说明

| 子目录 | 内容 | 时间窗口 |
|---|---|---|
| [`v1-reset/`](./v1-reset/) | V1 reset MVP-0 到 MVP-5 的所有阶段文档 (PHASE2..4 DESIGN / CHANGELOG_MVP0..3 / 各 baseline snapshot / e2e_traces / 审计报告) | 2026-04-28 → 2026-04-29 V1 reset 期间 |
| [`architecture-old/`](./architecture-old/) | F1/F2/F3 phase 旧设计 spec (F1_T2_SKILL_CREATOR / F2_T1_GOLDEN_DIFF / F3_T2_VIRTUAL_TRACE 等 25 个) + REPO_SPLIT_AND_SDK_PLAN + TAURI_KICKOFF_PLAN + PR37_LAUNCH_READINESS_REVIEW + STUDIO_FRONTEND_DEV_SPEC | 2026-04 上半月 V0/V1 早期 Studio 开发期 |
| [`superpowers-plans/`](./superpowers-plans/) | superpowers 框架 session plans (PR6/PR7 系列 validator plans + cohesion plan + prompt schema 9 round) + 1 个 v1-reset-direction spec | 2026-04-08 → 2026-04-28 |
| 顶层散文件 | V21_PR_META / V21_ROLLBACK_SOP / UNDERSTANDING_REPORT_2026-04-23 / skill-health-2026-04-28 / v1-reset-mvp-0-done / plan-2026-pre-v1-reset / 2026-04-08-graph-agent-origin-session | 一次性报告 / 早期 origin session 记录 |

---

## 为什么 archive 而不是删除

- **审计 trail**: ship 出去的设计如果 6 个月后想"当时为什么这么做", 应该能查到
- **历史教训**: V1 reset 系列文档记录了"为什么砍掉 V1 直接做 V2.1"的根因, 删了等于丢历史教训
- **回顾设计演进**: F1/F2/F3 phase plans 记录了 Studio 从零做到 Canvas + Multifile Editor 的全过程

---

## 找当前现状的入口

| 你想找... | 去这里 |
|---|---|
| Studio 现在能干什么 | [../STUDIO-BASELINE-2026-05-17.md](../STUDIO-BASELINE-2026-05-17.md) |
| Engine 怎么用 | [../engine/](../engine/) |
| Skill 怎么写 | [../skills/SKILL_AUTHORING_GUIDE.md](../skills/SKILL_AUTHORING_GUIDE.md) |
| 当前在做什么 spec | [../../.kiro/specs/](../../.kiro/specs/) |
