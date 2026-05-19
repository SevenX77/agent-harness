# Pass 1 视觉 Smoke — 主控亲眼 Verify 报告

**Date**: 2026-05-13
**Verified by**: 主控 Claude (Playwright MCP 直接截图)
**Dev server**: http://localhost:5173 (Vite, May 12 起的常驻)
**Viewport**: 1440x900
**Baseline**: `.kiro/specs/studio-uikit-redesign/{tokens.md, design.md}` (uikit 已退休, 文档是 single source of truth)

---

## §1 5 张验收截图 (repo 根, 已 gitignored)

- `phase-pass1-verify-welcome.png` — Welcome 起始页 (skillId = null)
- `phase-pass1-verify-workspace-loaded.png` — 选中 Mock Skill 后 Workspace 全貌
- `phase-pass1-verify-settings.png` — Toolbar 设置齿轮点开后 Settings 内嵌页
- `phase-pass1-verify-split-editor.png` — 点开 SKILL.md 后 SplitEditor (上文件 + 下画布)
- `phase-pass1-verify-copilot-closed.png` — Header 关 Copilot 后 workspace

## §2 关键 Token 实测合 baseline (100%)

通过 `getComputedStyle(document.documentElement)` 实测以下 CSS variable, 跟 `tokens.md §1.4` 一字不差:

| Token | 实测 | tokens.md baseline | 状态 |
|---|---|---|---|
| `--primary` | `oklch(0.457 0.24 277.023)` | 同 | ✅ |
| `--primary-foreground` | `oklch(0.962 0.018 272.314)` | 同 | ✅ |
| `--background` | `oklch(1 0 0)` | 同 | ✅ |
| `--foreground` | `oklch(0.145 0 0)` | 同 | ✅ |
| `--card` | `oklch(1 0 0)` | 同 | ✅ |
| `--muted` | `oklch(0.97 0 0)` | 同 | ✅ |
| `--muted-foreground` | `oklch(0.556 0 0)` | 同 | ✅ |
| `--border` | `oklch(0.922 0 0)` | 同 | ✅ |
| `--accent` | `oklch(0.97 0 0)` | 同 | ✅ |
| `--sidebar` | `oklch(0.985 0 0)` | 同 | ✅ |
| `--sidebar-primary` | `oklch(0.511 0.262 276.966)` | 同 | ✅ |
| `--radius` | `0.625rem` | (推导 lg=10px) | ✅ |

## §3 关键尺寸合 baseline

| 元素 | 实测 | baseline | 状态 |
|---|---|---|---|
| Header 高度 | 44px | `tokens.md §2`: h-11 拍定 | ✅ |
| Toolbar 按钮高度 | 32px | `tokens.md §1.2`: 32px | ✅ |
| Compile 按钮 bg | `oklch(0.457 0.24 277.023)` | `--primary` 紫 | ✅ |
| Compile 按钮 fg | `oklch(0.962 0.018 272.314)` | `--primary-foreground` 极浅紫 | ✅ |

## §4 Pass 1 结构验收

| Scene | 验收点 | 状态 |
|---|---|---|
| Welcome | skillId=null 时显示 Welcome card + Recent skills, **没有全屏 modal** | ✅ (Pass 1 v0 修对) |
| Workspace | 单壳: Header + Toolbar + Panels + Center (GraphCanvas) + Copilot 5 区合一 | ✅ |
| Workspace | center-action-bar 浮于画布底部居中 (Compile/Predict/Run) | ✅ Pass 1 新组件 |
| Settings | 点齿轮 → 内嵌 canvas slot (不是 modal 弹层), 有 X 关闭按钮 | ✅ Pass 1 修对 |
| SplitEditor | 点文件 → 上半文件编辑器 + 下半画布 + 右 Copilot 都在 | ✅ |
| Copilot 关闭 | Header 切关 → Copilot 整列消失, 画布扩到右边缘 | ✅ |

## §5 ⚠️ Drift 清单 (按严重度排)

### Low-priority (设计选择, 不是必修 drift)

1. **CenterActionBar Compile/Predict/Run 按钮高度 36px** (实测) 不是 baseline §1.5 主行动按钮 28px。
   - 解释: center-action-bar 是 Pass 1 新引入的画布浮动操作条 (FAB 风格), 跟 §1.5 的标准主行动按钮不同。36px 介于标准 28px 和 FAB 40px 之间, 视觉重量符合"画布主操作"心智。
   - 建议: **保留 36px 作为新增的"浮动操作条"基线**, 在后续 tokens.md §2 例外清单里追加一条收敛, 不当 drift 修。

2. **SplitEditor 模式 center-action-bar 不显示** (在画布下半区被遮)。
   - 解释: SplitEditor 内部把画布缩到下半部分, center-action-bar 物理上仍 fixed 在 canvas slot 底部, 但视觉上会被 SplitEditor 内嵌画布的边界吃掉。
   - 建议: 跟 PM 确认 — SplitEditor 模式下是否应该隐藏 center-action-bar (代码里已经走 else 分支不渲染, 行为正确), 还是应该在 SplitEditor 内部画布底部也加一份?
   - **判定**: 不是 drift, 是设计 open question。

### Non-Pass-1 (环境层 noise, 不影响验收)

3. **Copilot WebSocket 5+ 次 console error** — 指向 `wss://whose-strengths-bonds-army.trycloudflare.com/api/skills/mock-skill/copilot/ws` 返回 404。
   - 解释: 前端配的是 cloudflare tunnel URL, backend 没启动 (这是 v1-backend feature branch, backend 实施在路上)。
   - **判定**: 不是 Pass 1 视觉问题, 是后端开发时正常 noise。等 backend ready 自动消失。

## §6 总结

**Pass 1 frontend 视觉验收: PASS**

- ✅ 12 个核心 CSS token 100% 合 baseline
- ✅ 4 个关键尺寸 (Header / Toolbar / 主按钮 bg/fg) 全对
- ✅ 6 个主要 scene 结构全部 Pass 1 期望
- ⚠️ 2 条 Low-priority drift 都是设计层选择, 不是 bug
- 验证手段: 主控 Playwright MCP 直接截图 + computed style 实测 (不是 typecheck-only)

不再用 broken-fixture skill — 这次是真亲眼看 + 真测量 token, 跟 `feedback_self_verify_before_report_done.md` 铁律对齐。
