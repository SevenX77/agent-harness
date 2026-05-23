import { renderToStaticMarkup } from "react-dom/server"
import type { ReactNode } from "react"
import { describe, expect, it, vi } from "vitest"
import { ShortcutsCheatSheet } from "./ShortcutsCheatSheet"

vi.mock("../ui/dialog", () => ({
  Dialog: ({ children }: { children: ReactNode }) => <div data-slot="dialog">{children}</div>,
  DialogContent: ({ children }: { children: ReactNode }) => <div data-slot="dialog-content">{children}</div>,
  DialogDescription: ({ children }: { children: ReactNode }) => <p data-slot="dialog-description">{children}</p>,
  DialogHeader: ({ children }: { children: ReactNode }) => <div data-slot="dialog-header">{children}</div>,
  DialogTitle: ({ children }: { children: ReactNode }) => <h2 data-slot="dialog-title">{children}</h2>,
}))

vi.mock("../ui/kbd", () => ({
  Kbd: ({ children }: { children: ReactNode }) => <kbd data-slot="kbd">{children}</kbd>,
}))

describe("ShortcutsCheatSheet", () => {
  it("uses the shadcn dialog and kbd primitives instead of a custom modal", () => {
    const html = renderToStaticMarkup(<ShortcutsCheatSheet open onClose={vi.fn()} />)

    expect(html).toContain('data-slot="dialog-content"')
    expect(html).toContain('data-slot="dialog-title"')
    expect(html).toContain('data-slot="kbd"')
    expect(html).not.toContain("bg-slate")
    expect(html).not.toContain("dark:bg-slate")
  })
})
