# Implementation Plan — Studio LLM 温度百分比化 + 跨 provider 兼容

> **STATUS: IMPLEMENTATION IN PROGRESS ? 2026-07-05 ?? A(linear remap)?**
> worktree: `feat/temperature-percentage-runtime`. ??? red/green ?????/????; Phase 3 ? ?? + ????????

## Phase 0 · 定方向 & 补前置调研
- [x] 0.1 请求方拍板 **A 还是 B**(design.md §5),更新 `spec.json.phase` 与 approvals。
- [x] 0.2 枚举 `GenericRouteChatModel` 承载的 protocol,坐实 §2 上限表无漏网 0~1 provider(design.md §6.1)。
- [x] 0.3 核查 Studio skill run 实际走路径 X / Y / 两者(design.md §6.2),确保测试覆盖真实热路径。
- [x] 0.4 查 `apps/studio/frontend/src/hooks/` 是否已有 debounce 封装可复用(design.md §6.4)。

## Phase 1 · Gateway 换算(TDD;方案 A)
- [x] 1.1 **(Red)** `packages/graph-agent-gateway/tests` 加失败测试:
  - 同一授权值 `1.5` 经 anthropic 候选 → 真实温度 `≤1`(A 下 `0.75`);经 openai 候选 → `1.5`。
  - 未设置(None)→ 两路径都**不发** temperature(A 删 0.7 伪造)。
  - 一个 role fan-out openai+anthropic 双候选 → 各按自己 protocol 换算。
  - _Requirements: 2.1, 2.2, 2.3, 2.4, 5.1_
- [x] 1.2 **(Green)** 加 `_authored_to_provider_temperature(authored, protocol)` + protocol→上限表(§2)。
  - 路径 X:在 `route_chat_model_factory` 每候选最后一公里按 `route.protocol` 换算(仅非 None)。
  - 路径 Y:在 `gateway_chat_model` 删 0.7 伪造(None→省略),node 覆盖入口按候选 protocol 换算;
    `ordinary_chat._*_chat` 收到的即真实温度。
  - 保证**每候选换算一次**,不重复、不遗漏(design.md §1.3)。
  - _Requirements: 2.1–2.5, 3(文案), 5.1_
- [x] 1.3 `registry/lint.py` 温度数值 lint 的边界随新语义校准(若 A 改了量程含义)。
  - _Requirements: 2, 5.3_
  - 2026-07-05 note: storage remains provider-neutral 0..2, so registry numeric lint keeps the existing lower-bound-only contract; provider-specific max is enforced by runtime remap, not schema clamp.

## Phase 2 · 前端:百分比读数 + "?" + debounce(TDD 业务逻辑部分)
- [x] 2.1 **(Red)** vitest:百分比 ↔ 内部值换算正确;拖动只更本地 state、不逐跳落库;
  停止后落最终值;卸载/reset 取消在途 debounce。
  - _Requirements: 1, 4, 5.2_
- [x] 2.2 **(Green)** 两处滑条(`LlmNodeParamsField` / `RoleSettingsFields`):
  - 读数改百分比(`内部值/2*100%`),未设置显示 `—`;滑条组件/字体/颜色沿用现状。
  - 落库(`persist` / `onSubmit`)套 debounce hook;`setDraft` 即时。
  - 加 `HelpTooltip` "?",文案按 A/B 定稿(design.md §5)。
  - _Requirements: 1, 3, 4_
- [x] 2.3 更新/收窄两处相关旧测试(如 `LlmRolesTab.test.tsx` 里约束温度读数/值的断言)。
  - _Requirements: 5.2_

## Phase 3 · 门禁 + 亲眼验证
- [x] 3.1 Gateway 门禁:`ruff check` / `mypy --strict packages/graph-agent-gateway/src` /
  `pytest packages/graph-agent-gateway/tests`;backend `pytest apps/studio/backend/tests`。
  - _Requirements: 5.3_
- [x] 3.2 前端门禁:`npm run lint && npm run typecheck && npm test && npm run build`。
  - _Requirements: 5.3_
- [x] 3.3 **改了 gateway → `scripts/wt-dev.sh --backend`** 起本 worktree 私有 sidecar,
  浏览器亲眼验证:node + role 两处温度栏百分比读数、"?" 说明、拖动顺滑(debounce)、
  以及(尽量)命中 anthropic 路由时真实温度 ≤1。截图留档。
  - _Requirements: 1, 2, 3, 4_
  - 2026-07-05 verification: wt-dev --backend on Vite 5175/private sidecar 8788; role Temperature 40% -> 55% -> 40%, node unset ? -> 55%, both tooltips verified; node override and temporary opener restored.

## Phase 4 · 设计源 & 手册回写
- [x] 4.1 把"温度百分比 + 跨 provider 换算"新语义写回 gateway MVP1 设计源
  `docs/graph-agent-gateway/mvp1/`(设计成为真相,不只是改代码)。
  - _Requirements: 5.4_
- [x] 4.2 若对应 N6 手册切片涉及 LLM role/node 温度栏,同轮回写切片状态 + 重生成 `index.html`。

## Phase 5 · 发 PR
- [ ] 5.1 `scripts/wt-ship.sh`,PR 含 gateway + 前端 src + 设计源(+ 手册切片/index.html);
  `main` protected,auto-merge on green。合并后主仓根 `git pull`;
  **gateway 源码变了 → 按 AGENTS.md 第 7 条重建 vendor**(`build_vendor.py` + `compileall` 预热 pyc)再重启 app,否则桌面 app 跑旧 gateway。
- [ ] 5.2 报 done 附「逐项 PM 验证清单」(SOP Phase 8 格式),等 PM 逐条确认才算收敛。

---

## 附:未纳入本 spec 的遗留项(独立处理)
- **PR2/PR3 手册切片回写**(上一 session 遗留):属独立 docs 任务,走「纯手册任务」
  流程(SOP 附录),不并入本功能 spec。
