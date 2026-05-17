# Studio Screenshots · 2026-05-17 Playwright Baseline

> 配套 [STUDIO-BASELINE-2026-05-17.md](../../STUDIO-BASELINE-2026-05-17.md) §1.2 + §3.1 实测证据。

| 文件 | 截屏对象 | 用途 |
|---|---|---|
| `studio-01-welcome.png` | Welcome 屏 (含 "Save conflict" + "GRAPH.md changed externally" modal 错渲) | 实测发现的 polish bug #1 证据 (启动状态泄漏) |
| `studio-02-welcome-clean.png` | Welcome 屏 (modal 关掉后) | 真实 welcome 布局 |
| `studio-03-skill-loaded.png` | text-segmentation 加载后的 Workspace 三栏 (Header + Canvas + Files 右栏) | 主 baseline 视觉证据 |
| `studio-04-trace-tab.png` | 右栏 Trace tab ("Waiting for run events") | Trace 当前是占位 |
| `studio-05-diff-tab.png` | 右栏 Diff tab (Golden Diff + Compare/Promote) | Golden 工作流已 ship |
| `studio-06-history-tab.png` | 右栏 History tab (含 "0 runs tracked" + 大量 toast 堆叠) | polish bug #2 证据 (toast 不去重) |
| `studio-07-batch-tab.png` | 右栏 Batch tab (Batch Runner / No JSON test inputs) | Batch 框架在 |
| `studio-08-cli-tab.png` | 右栏 CLI tab ("No CLI session") | CLI session 入口 |
| `studio-09-artifacts-drawer.png` | Artifacts 弹出面板 (Run Input + Raw JSON) | Playground 输入入口 |
| `studio-10-settings.png` | Settings (LLM API Keys: OpenAI / Anthropic / Google Gemini) | api-keys-v1 部分 ship 证据 |
| `studio-11/12/13-batch-analysis*.png` | batch-analysis 切换后 canvas | 多 skill 切换会触发 toast 堆叠 |

**注**: 这批截图是 2026-05-17 13:07 - 13:12 UTC Playwright 实测一次性产出, 不代表 frontend 实时状态。下次 baseline 更新前如果 frontend 大幅改动, 需重新跑一遍 Playwright 生成新批次截图 (建议目录命名 `screenshots-YYYY-MM-DD/`)。
