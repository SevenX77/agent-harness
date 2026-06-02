# 04_platform — 后端三分(D10, 锁定 2026-06-01)

> 平台层(非 UI、非用户能力的真 infra)。详见 [../../INDEX.md](../../INDEX.md) §6 + [alignment-notes D10/D12](../../_reorg/alignment-notes.md)。

| 块 | 形态 | 职责 |
|---|---|---|
| `gateway` | Python sidecar | provider/role/credential/model 解析 + copilot chat LLM 流 |
| `engine` | Python sidecar | graph-agent: compile/lint/predict/run/eval/trace |
| `native-fs` | Rust(Tauri) | **唯一写者**: FS 读写/打开文件夹/watch/MRU/reveal + runs/golden/artifacts 目录 + 闭环编排 + sidecar 生命周期 + copilot session 落盘 |
| `state-engine` | 前端 | 前端状态 + WS / Rust-event ipc 桥 |

> **[D12]** 本地写全量 Rust(native-fs 唯一写者); 仅 engine/gateway 走 Python sidecar。两 sidecar 启动期由 Rust eager-spawn, 非全屏 bootstrap gate(RuntimeGate 退役)。
