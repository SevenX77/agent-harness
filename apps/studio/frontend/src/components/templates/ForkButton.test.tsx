import { renderToStaticMarkup } from "react-dom/server"
import type { ReactNode } from "react"
import { describe, expect, it, vi } from "vitest"
import { ForkButton } from "./ForkButton"
import type { SkillSummary } from "../../api/types"

vi.mock("../ui/button", () => ({
  Button: ({ children }: { children: ReactNode }) => <button data-slot="button">{children}</button>,
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

describe("ForkButton", () => {
  it("uses the shadcn button primitive for the trigger", () => {
    const html = renderToStaticMarkup(<ForkButton skill={skill} onForkSkill={vi.fn()} />)

    expect(html).toContain('data-slot="button"')
    expect(html).not.toContain("text-gray")
    expect(html).not.toContain("text-sky")
  })
})
