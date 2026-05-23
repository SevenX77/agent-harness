import { renderToStaticMarkup } from "react-dom/server"
import type { ReactNode } from "react"
import { describe, expect, it, vi } from "vitest"
import type { RunDetail } from "../../api/types"
import { RunDetailDrawer } from "./RunDetailDrawer"

vi.mock("../ui/button", () => ({
  Button: ({ children, className }: { children: ReactNode; className?: string }) => (
    <button className={className} data-slot="button">
      {children}
    </button>
  ),
}))

vi.mock("../ui/sheet", () => ({
  Sheet: ({ children, open }: { children: ReactNode; open?: boolean }) => (
    open ? <div data-slot="sheet">{children}</div> : null
  ),
  SheetContent: ({
    children,
    className,
  }: {
    children: ReactNode
    className?: string
  }) => (
    <aside className={className} data-slot="sheet-content">
      {children}
    </aside>
  ),
  SheetDescription: ({ children }: { children: ReactNode }) => (
    <p data-slot="sheet-description">{children}</p>
  ),
  SheetHeader: ({ children }: { children: ReactNode }) => (
    <div data-slot="sheet-header">{children}</div>
  ),
  SheetTitle: ({ children }: { children: ReactNode }) => (
    <h2 data-slot="sheet-title">{children}</h2>
  ),
}))

vi.mock("../export/ExportButton", () => ({
  ExportButton: () => <button data-slot="export-button">Export</button>,
}))

const detail: RunDetail = {
  metadata: {
    run_id: "run-123",
    status: "success",
    started_at: "2026-05-21T12:00:00.000Z",
    metrics: {
      input_tokens: 4,
      output_tokens: 5,
      total_tokens: 9,
      cost_estimate: null,
    },
    input_summary: null,
  },
  input_data: { prompt: "hello" },
  events: [],
  final_context: { result: "ok" },
  artifacts: null,
}

describe("RunDetailDrawer", () => {
  it("uses shadcn sheet and button primitives instead of a custom drawer shell", () => {
    const html = renderToStaticMarkup(
      <RunDetailDrawer
        detail={detail}
        skillId="demo"
        open
        onClose={vi.fn()}
        onReplay={vi.fn()}
        onCompare={vi.fn()}
      />,
    )

    expect(html).toContain('data-slot="sheet-content"')
    expect(html).toContain('data-slot="sheet-title"')
    expect(html).toContain('data-slot="button"')
    expect(html).not.toContain("absolute inset-0")
    expect(html).not.toContain("bg-slate")
    expect(html).not.toContain("text-slate")
    expect(html).not.toContain("bg-sky")
  })
})
