import { renderToStaticMarkup } from "react-dom/server"
import { beforeEach, describe, expect, it, vi } from "vitest"
import { LazyMonacoPanel } from "./LazyMonacoPanel"

vi.mock("@/api/client", () => ({
  writeSkillFile: vi.fn(),
}))

vi.mock("sonner", () => ({
  toast: Object.assign(vi.fn(), {
    dismiss: vi.fn(),
    error: vi.fn(),
  }),
}))

describe("LazyMonacoPanel header controls", () => {
  beforeEach(() => {
    vi.stubGlobal("document", {
      documentElement: {
        classList: {
          contains: () => true,
        },
      },
    })
  })

  it("uses shadcn badge and icon buttons for editor chrome actions", () => {
    const html = renderToStaticMarkup(
      <LazyMonacoPanel
        title="Skill.md"
        skillId="skill-1"
        filePath="SKILL.md"
        value="# Skill"
        onChange={vi.fn()}
        onSaved={vi.fn()}
        onInFlightChange={vi.fn()}
        onConflict={vi.fn()}
        onClose={vi.fn()}
        onSplit={vi.fn()}
      />,
    )

    expect(html).toContain('data-slot="badge"')
    expect(html).toContain('data-slot="button"')
    expect(html).toContain('aria-label="Split editor"')
    expect(html).toContain('aria-label="Close editor"')
    expect(html).not.toContain(">x</button>")
    expect(html).not.toContain("inline-flex size-7")
  })

})
