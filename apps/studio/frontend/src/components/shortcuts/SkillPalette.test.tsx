import { renderToStaticMarkup } from "react-dom/server"
import type { ReactNode } from "react"
import { describe, expect, it, vi } from "vitest"
import { SkillPalette } from "./SkillPalette"
import type { SkillSummary } from "../../api/types"

vi.mock("../ui/badge", () => ({
  Badge: ({ children }: { children: ReactNode }) => <span data-slot="badge">{children}</span>,
}))

vi.mock("../ui/command", () => ({
  Command: ({ children }: { children: ReactNode }) => <div data-slot="command">{children}</div>,
  CommandDialog: ({ children }: { children: ReactNode }) => <div data-slot="dialog-content">{children}</div>,
  CommandEmpty: ({ children }: { children: ReactNode }) => <div data-slot="command-empty">{children}</div>,
  CommandGroup: ({ children }: { children: ReactNode }) => <div data-slot="command-group">{children}</div>,
  CommandInput: () => <input data-slot="command-input" />,
  CommandItem: ({ children }: { children: ReactNode }) => <div data-slot="command-item">{children}</div>,
  CommandList: ({ children }: { children: ReactNode }) => <div data-slot="command-list">{children}</div>,
}))

const skill: SkillSummary = {
  id: "demo-skill",
  name: "Demo Skill",
  description: "Demo description",
  phase_count: 1,
  has_golden: false,
  last_run_at: null,
  directory_path: "/tmp/demo-skill",
}

describe("SkillPalette", () => {
  it("uses the shadcn command dialog primitives instead of a custom overlay", () => {
    const html = renderToStaticMarkup(
      <SkillPalette
        open
        skills={[skill]}
        selectedSkillId="demo-skill"
        onSelect={vi.fn()}
        onClose={vi.fn()}
      />,
    )

    expect(html).toContain('data-slot="dialog-content"')
    expect(html).toContain('data-slot="command"')
    expect(html).toContain('data-slot="command-input"')
    expect(html).toContain("Current")
    expect(html).not.toContain("bg-slate")
    expect(html).not.toContain("bg-sky")
  })
})
