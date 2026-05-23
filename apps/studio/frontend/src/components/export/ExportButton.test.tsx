import { renderToStaticMarkup } from "react-dom/server"
import type { ReactNode } from "react"
import { describe, expect, it, vi } from "vitest"
import { ExportButton } from "./ExportButton"

vi.mock("../ui/button", () => ({
  Button: ({ children }: { children: ReactNode }) => <button data-slot="button">{children}</button>,
}))

vi.mock("../ui/dropdown-menu", () => ({
  DropdownMenu: ({ children }: { children: ReactNode }) => <div data-slot="dropdown-menu">{children}</div>,
  DropdownMenuContent: ({ children }: { children: ReactNode }) => <div data-slot="dropdown-menu-content">{children}</div>,
  DropdownMenuItem: ({ children }: { children: ReactNode }) => <div data-slot="dropdown-menu-item">{children}</div>,
  DropdownMenuTrigger: ({ children }: { children: ReactNode }) => <div data-slot="dropdown-menu-trigger">{children}</div>,
}))

describe("ExportButton", () => {
  it("uses shadcn dropdown menu and button primitives", () => {
    const html = renderToStaticMarkup(
      <ExportButton filenameBase="demo" buildContent={() => ""} />,
    )

    expect(html).toContain('data-slot="dropdown-menu"')
    expect(html).toContain('data-slot="dropdown-menu-trigger"')
    expect(html).toContain('data-slot="button"')
    expect(html).not.toContain("border-slate")
    expect(html).not.toContain("text-slate")
  })
})
