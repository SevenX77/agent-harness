import { renderToStaticMarkup } from "react-dom/server"
import type { ReactNode } from "react"
import { describe, expect, it, vi } from "vitest"
import { DraftRestoreModal } from "./DraftRestoreModal"

vi.mock("../ui/alert", () => ({
  Alert: ({ children }: { children: ReactNode }) => <div data-slot="alert">{children}</div>,
  AlertDescription: ({ children }: { children: ReactNode }) => <div data-slot="alert-description">{children}</div>,
}))

vi.mock("../ui/alert-dialog", () => ({
  AlertDialog: ({ children }: { children: ReactNode }) => <div data-slot="alert-dialog">{children}</div>,
  AlertDialogAction: ({ children }: { children: ReactNode }) => <button data-slot="alert-dialog-action">{children}</button>,
  AlertDialogCancel: ({ children }: { children: ReactNode }) => <button data-slot="alert-dialog-cancel">{children}</button>,
  AlertDialogContent: ({ children }: { children: ReactNode }) => <div data-slot="alert-dialog-content">{children}</div>,
  AlertDialogDescription: ({ children }: { children: ReactNode }) => <p data-slot="alert-dialog-description">{children}</p>,
  AlertDialogFooter: ({ children }: { children: ReactNode }) => <div data-slot="alert-dialog-footer">{children}</div>,
  AlertDialogHeader: ({ children }: { children: ReactNode }) => <div data-slot="alert-dialog-header">{children}</div>,
  AlertDialogMedia: ({ children }: { children: ReactNode }) => <div data-slot="alert-dialog-media">{children}</div>,
  AlertDialogTitle: ({ children }: { children: ReactNode }) => <h2 data-slot="alert-dialog-title">{children}</h2>,
}))

describe("DraftRestoreModal", () => {
  it("uses shadcn alert dialog primitives instead of a custom overlay", () => {
    const html = renderToStaticMarkup(
      <DraftRestoreModal
        open
        skillId="demo-skill"
        baseHash="base"
        draft={{ content: "one\ntwo", baseHash: "old", timestamp: 1 }}
        onRestore={vi.fn()}
        onDiscard={vi.fn()}
        onCancel={vi.fn()}
      />,
    )

    expect(html).toContain('data-slot="alert-dialog-content"')
    expect(html).toContain('data-slot="alert-dialog-action"')
    expect(html).toContain('data-slot="alert"')
    expect(html).not.toContain("bg-slate")
    expect(html).not.toContain("bg-gray")
  })
})
