import { renderToStaticMarkup } from "react-dom/server"
import type { ReactNode } from "react"
import { describe, expect, it, vi } from "vitest"
import { CommandPalette } from "./CommandPalette"

vi.mock("../ui/command", () => ({
  Command: ({ children }: { children: ReactNode }) => <div data-slot="command">{children}</div>,
  CommandDialog: ({ children }: { children: ReactNode }) => <div data-slot="dialog-content">{children}</div>,
  CommandEmpty: ({ children }: { children: ReactNode }) => <div data-slot="command-empty">{children}</div>,
  CommandGroup: ({ children }: { children: ReactNode }) => <div data-slot="command-group">{children}</div>,
  CommandInput: () => <input data-slot="command-input" />,
  CommandItem: ({ children }: { children: ReactNode }) => <div data-slot="command-item">{children}</div>,
  CommandList: ({ children }: { children: ReactNode }) => <div data-slot="command-list">{children}</div>,
  CommandShortcut: ({ children }: { children: ReactNode }) => <span data-slot="command-shortcut">{children}</span>,
}))

describe("CommandPalette", () => {
  it("uses the shadcn command dialog primitives instead of a custom overlay", () => {
    const html = renderToStaticMarkup(
      <CommandPalette
        open
        actions={[{
          id: "save",
          label: "Save",
          description: "Save current skill",
          hotkey: "mod+s",
          run: vi.fn(),
        }]}
        onClose={vi.fn()}
      />,
    )

    expect(html).toContain('data-slot="dialog-content"')
    expect(html).toContain('data-slot="command"')
    expect(html).toContain('data-slot="command-input"')
    expect(html).toContain('data-slot="command-shortcut"')
    expect(html).not.toContain("bg-slate")
    expect(html).not.toContain("bg-sky")
  })
})
