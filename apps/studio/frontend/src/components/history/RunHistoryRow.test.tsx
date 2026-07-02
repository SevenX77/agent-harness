import { renderToStaticMarkup } from "react-dom/server"
import type { ComponentProps, ReactNode } from "react"
import { describe, expect, it, vi } from "vitest"
import type { RunMetadata } from "../../api/types"
import { RunHistoryRow } from "./RunHistoryRow"

vi.mock("../ui/badge", () => ({
  Badge: ({ children, ...props }: ComponentProps<"span"> & { children: ReactNode }) => (
    <span data-slot="badge" {...props}>
      {children}
    </span>
  ),
}))

vi.mock("../ui/button", () => ({
  Button: ({ children, ...props }: ComponentProps<"button"> & { children: ReactNode }) => (
    <button data-slot="button" {...props}>
      {children}
    </button>
  ),
}))

vi.mock("../ui/table", () => ({
  TableCell: ({ children, ...props }: ComponentProps<"td"> & { children: ReactNode }) => (
    <td data-slot="table-cell" {...props}>{children}</td>
  ),
  TableRow: ({ children, ...props }: ComponentProps<"tr"> & { children: ReactNode }) => (
    <tr data-slot="table-row" {...props}>{children}</tr>
  ),
}))

vi.mock("../export/ExportButton", () => ({
  ExportButton: () => <button data-slot="export-button">Export</button>,
}))

const run: RunMetadata = {
  run_id: "run-12345678901234567890",
  status: "success",
  started_at: "2026-05-21T12:00:00.000Z",
  metrics: {
    input_tokens: 10,
    output_tokens: 20,
    total_tokens: 30,
    cost_estimate: null,
  },
  input_summary: "Example input",
}

describe("RunHistoryRow", () => {
  it("uses shadcn table, badge, and button primitives", () => {
    const html = renderToStaticMarkup(
      <table>
        <tbody>
          <RunHistoryRow
            run={run}
            selected
            filenameBase="run"
            onSelect={vi.fn()}
            onReplay={vi.fn()}
            onCompare={vi.fn()}
            onExport={() => ""}
            onDelete={vi.fn()}
          />
        </tbody>
      </table>,
    )

    expect(html).toContain('data-slot="table-row"')
    expect(html).toContain('data-slot="table-cell"')
    expect(html).toContain('data-slot="badge"')
    // Action buttons are Tooltip triggers (TooltipTrigger asChild overrides the
    // Button data-slot); the buttons themselves are still the ui/button wrapper.
    expect(html).toContain('data-slot="tooltip-trigger"')
    expect(html).not.toContain("bg-slate")
    expect(html).not.toContain("text-slate")
    expect(html).not.toContain("bg-sky")
  })
})
