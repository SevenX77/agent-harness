import type { RunMetadata } from "@/api/types"

/**
 * viewed-run 状态模型(决议 2026-08-07):timeline 区域展示哪次 run 与
 * 实时流订阅哪个 run 分离。
 *
 * - `live`    — 展示当前实时流(Workspace 的 runStream;predict 与 run 共用)。
 * - `history` — 回看一次已落盘的 run:事件由 Workspace 一次性拉取并缓存,
 *               timeline 与 Full Trace 文档共读同一份(diagnostics 同源)。
 * - `null`    — 没有在看任何 run:timeline 区域显示历史列表。
 */
export type TraceView =
  | { source: "live" }
  | { source: "history"; runId: string; metadata: RunMetadata; reportPath: string | null }
