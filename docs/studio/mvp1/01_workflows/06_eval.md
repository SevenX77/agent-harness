# 06 · 保存与发布(autocommit 存档 + publish 发布) — Workflow 节点

> **Tier**: workflow
> **旅程**: [04 运行与验收](./04_run-and-verify.md) 验收通过 → 本地 git autocommit 存档 → (低优先)发布分发上线 → 回主页闭环
> **走查完整记录**(atom actions + 决策 + 原话 + 测试关键点)。PM 2026-06-04 走查。
> **定性**: **发布 = 占坑低优先**(PM 沿用 settings 走查定调)。本地 git commit 存档够用;发布走 **Artifact Registry**(zip 上传,**非 git push**);旧散文的 git add/commit/push + commit-message 托底 + 撒花特效都是 **stale-doc 虚需求**,删。

## 旅程位
04 run 成功 + golden 验收(归 [`golden-eval`](../02_capabilities/golden-eval/mvp1-alignment.md),04 已走查)通过 → 06:① 每次成功 run 本地 git **autocommit 存档**;②(低优先)**发布分发**上线到 Artifact Registry;③ 回主页开始新探索(回 [01_init](./01_init.md))。

> ⚠️ **golden 固化 / Diff 视图 / Copilot Judge / 打磨编排 不在本节点** —— 归 `golden-eval`(04_run-and-verify 已走查),06 只管"存档 + 发布"。旧 06 散文把它们和 publish 混在一起,已随节点重组拆走。

## Atom actions
| # | 动作 | status | 能力·区域 |
|---|---|---|---|
| P1 | 成功 run 后本地 git **autocommit 存档** | live | publish(保存)· `native-fs`(Rust 写,D12) |
| P2 | 点 **Release** 发布(现在 Header『Team』下拉项里) | live | publish · `shell-layout`(Header) |
| P3 | 发布底层 = 打包 zip 上传 **Artifact Registry**(`skills.py:286`/`artifact_registry.py:46`,**非 git**) | live | publish · `native-fs`(打包落盘 D12) |
| P4 | 发布前置校验失败退路(user_id / registry host+token 缺 → 报错 + 指引去 Settings,非静默) | live | publish · `shell-layout` |
| P5 | 发布成功 → 回主页开始新探索(闭环;现不自动跳主页) | live | `skill-workspace` · `shell-layout` |
| ~~P6~~ | ~~commit message 输入 + Copilot 自动生成~~ | **删(stale-doc 虚需求)** | — |
| ~~P7~~ | ~~confetti 撒花~~ | **删(stale-doc;`lib/confetti.ts` orphan 不接入)** | — |

## 决策(PM 2026-06-04)
- **发布 = 维持最小·占坑低优先**(沿用 settings 走查):本地 git commit 存档够用;发布 Artifact Registry 保持现状最小(上传 + 前置校验);**不做** commit-msg UI / confetti / 独立 Publish 按钮 —— 留坑未来。团队协作(Gitea)+ 发布鉴权 UI 同 settings 占坑(见 [00_settings](./00_settings.md))。
- **纠 stale-doc**:旧散文「git add/commit/push + 撒花 + commit-message 托底」与实现相反——实测发布 = Artifact Registry zip 上传;git 只用于 Save/Sync-to-Team(非 publish)。这些虚需求删。
- **autocommit 存档 = 保留**(本地够用,成功 run 自动 commit)。

## 原话(留底)
> (settings 走查)「整套gitea 部署起来麻烦吗? 这个功能其实我现在还没有碰过, 因为现在没那么紧急, 保存在本地够用, 只是占了个坑」
> (本节点 2026-06-04)「维持最小·占坑低优先」

## 测试关键点
- 发布走 **Artifact Registry**(zip 上传),**不是 git push**(回归旧散文 stale)。
- 前置校验:user_id / registry host / token 缺 → 明确报错 + 指引 Settings(非静默失败)。
- 成功 run 本地 **autocommit 存档**(本地够用)。
- **不出现** commit-msg 弹窗 / confetti(虚需求已删)。

## gaps / 未来(占坑)
- 团队协作(Gitea)+ 发布鉴权 UI + commit-msg + Copilot 生成 + confetti + 独立 Publish 按钮 = **占坑低优先**,未来真要做团队发布再启。
- **D12**:发布打包落盘目标态走 Rust(现 Python `build_publish_package`)。
- 发布入口现藏 Header『Team』下拉(Save/Sync/Submit/Release 四合一),未来若提优先级可拆独立按钮。
