# 04_platform — 基础设施(后端三分 D10 锁定 2026-06-01 + i18n 横切 2026-06-03)

> 平台层(非 UI 用户能力的真 infra + 横切 NFR)。详见 [../../INDEX.md](../../INDEX.md) §6/§11 + [alignment-notes D10/D12](../../_reorg/alignment-notes.md)。

| 块 | 形态 | 职责 |
|---|---|---|
| `gateway` | Python sidecar | provider/role/credential/model 解析 + copilot chat LLM 流 |
| `engine` | Python sidecar | graph-agent: compile/lint/predict/run/eval/trace |
| `native-fs` | Rust(Tauri) | **唯一写者**: FS 读写/打开文件夹/watch/MRU/reveal + runs/golden/artifacts 目录 + 闭环编排 + sidecar 生命周期 + copilot session 落盘 |
| `state-engine` | 前端 | 前端状态 + WS / Rust-event ipc 桥 |
| `i18n` | 前端主导 | studio 多语言单权威: react-i18next 翻 UI+错误码; 后端只产 error_code+details; 引擎/网关语言无关。详见 [i18n.md](./i18n.md) |

> **[D12]** 本地写全量 Rust(native-fs 唯一写者); 仅 engine/gateway 走 Python sidecar。两 sidecar 启动期由 Rust eager-spawn, 非全屏 bootstrap gate(RuntimeGate 退役)。

## 子文档

| 文档 | 职责 |
|---|---|
| [`llm-copilot-http-api/`](./llm-copilot-http-api/mvp1-alignment.md) | **gateway 块的 ③a HTTP 适配壳**：`routers/llm.py`、`routers/copilot.py` 暴露给前端的 LLM/Copilot HTTP 端点面（registry CRUD / endpoint·model·role test / import draft / model profile / Copilot ws+test）。HTTP glue + DTO 投影 + job 包装 = ③a；底下 delegate 的能力内核（base_url 归一化 / capability / probe 策略 / materialize / 6 态 / draft / endpoint 拆分）= ③b 公共（gateway 包）。**2026-06-03 从 gateway mvp1 模块 14 迁入。** |
| [i18n.md](./i18n.md) | 多语言横切（react-i18next + 前端权威）。 |

> **copilot SDK 调用**（gateway 块的 copilot chat LLM 流的实际调用方式）= ③a，文档在能力层 [`../02_capabilities/copilot-assist/`](../02_capabilities/copilot-assist/mvp1-alignment.md) + 工作流 [`../01_workflows/00_settings-ux-spec.md`](../01_workflows/00_settings-ux-spec.md) §3.8（SDK 机制）；gateway 库不感知 copilot，只解析 `copilot_chat` role→route。
