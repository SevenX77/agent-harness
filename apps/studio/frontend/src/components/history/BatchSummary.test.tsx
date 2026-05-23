import { renderToStaticMarkup } from "react-dom/server"
import type { ComponentProps, ReactNode } from "react"
import { describe, expect, it, vi } from "vitest"
import type { BatchRunStatus } from "../../api/types"
import { BatchSummary } from "./BatchSummary"

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

vi.mock("../ui/progress", () => ({
  Progress: (props: { value?: number }) => <div data-slot="progress" data-value={props.value} />,
}))

vi.mock("../ui/table", () => ({
  Table: ({ children }: { children: ReactNode }) => <table data-slot="table">{children}</table>,
  TableBody: ({ children }: { children: ReactNode }) => <tbody data-slot="table-body">{children}</tbody>,
  TableCell: ({ children, ...props }: ComponentProps<"td"> & { children: ReactNode }) => (
    <td data-slot="table-cell" {...props}>{children}</td>
  ),
  TableHead: ({ children, ...props }: ComponentProps<"th"> & { children: ReactNode }) => (
    <th data-slot="table-head" {...props}>{children}</th>
  ),
  TableHeader: ({ children }: { children: ReactNode }) => <thead data-slot="table-header">{children}</thead>,
  TableRow: ({ children, ...props }: ComponentProps<"tr"> & { children: ReactNode }) => (
    <tr data-slot="table-row" {...props}>{children}</tr>
  ),
}))

vi.mock("../export/ExportButton", () => ({
  ExportButton: () => <button data-slot="export-button">Export</button>,
}))

const status: BatchRunStatus = {
  batch_id: "batch-1",
  skill_id: "skill-1",
  status: "running",
  total: 2,
  completed: 1,
  items: [
    {
      input_id: "case-1",
      run_id: "run-1",
      status: "success",
      started_at: "2026-05-21T12:00:00.000Z",
      metrics: {
        input_tokens: 1,
        output_tokens: 2,
        total_tokens: 3,
        cost_estimate: null,
      },
    },
  ],
}

describe("BatchSummary", () => {
  it("uses shadcn progress, table, badge, and button primitives", () => {
    const html = renderToStaticMarkup(<BatchSummary status={status} onOpenRun={vi.fn()} />)

    expect(html).toContain('data-slot="progress"')
    expect(html).toContain('data-value="50"')
    expect(html).toContain('data-slot="table"')
    expect(html).toContain('data-slot="badge"')
    expect(html).toContain('data-slot="button"')
    expect(html).not.toContain("bg-slate")
    expect(html).not.toContain("text-slate")
    expect(html).not.toContain("bg-sky")
  })
})
