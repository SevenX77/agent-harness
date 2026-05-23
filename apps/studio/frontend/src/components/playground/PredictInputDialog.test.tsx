import { renderToStaticMarkup } from "react-dom/server"
import type { ReactNode } from "react"
import { describe, expect, it, vi } from "vitest"
import { PredictInputDialog } from "./PredictInputDialog"

vi.mock("../ui/dialog", () => ({
  Dialog: ({ children }: { children: ReactNode }) => <div data-slot="dialog">{children}</div>,
  DialogContent: ({ children }: { children: ReactNode }) => <div data-slot="dialog-content">{children}</div>,
  DialogDescription: ({ children }: { children: ReactNode }) => <p data-slot="dialog-description">{children}</p>,
  DialogFooter: ({ children }: { children: ReactNode }) => <div data-slot="dialog-footer">{children}</div>,
  DialogHeader: ({ children }: { children: ReactNode }) => <div data-slot="dialog-header">{children}</div>,
  DialogTitle: ({ children }: { children: ReactNode }) => <h2 data-slot="dialog-title">{children}</h2>,
}))

vi.mock("../ui/button", () => ({
  Button: ({ children }: { children: ReactNode }) => <button data-slot="button">{children}</button>,
}))

vi.mock("../ui/textarea", () => ({
  Textarea: () => <textarea data-slot="textarea" />,
}))

describe("PredictInputDialog", () => {
  it("uses shadcn dialog, textarea, and button primitives instead of a custom overlay", () => {
    const html = renderToStaticMarkup(
      <PredictInputDialog
        skillId="demo-skill"
        inputs={[{ name: "topic", source: "runtime", type: "string", default: "demo" }]}
        onClose={vi.fn()}
        onSubmit={vi.fn()}
      />,
    )

    expect(html).toContain('data-slot="dialog-content"')
    expect(html).toContain('data-slot="textarea"')
    expect(html).toContain('data-slot="button"')
    expect(html).not.toContain("z-modal")
  })
})
