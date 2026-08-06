// @vitest-environment jsdom

import { beforeEach, describe, expect, it, vi } from "vitest"
import { act } from "react"
import { createRoot, type Root } from "react-dom/client"
import { CliSection } from "./CliSection"

const mocks = vi.hoisted(() => ({
  cliDependencyStatus: vi.fn(),
}))

vi.mock("@/lib/tauri", () => ({
  cliDependencyStatus: mocks.cliDependencyStatus,
}))

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, options?: { defaultValue?: string }) => options?.defaultValue ?? key,
  }),
}))

async function renderSection(): Promise<{ container: HTMLElement; root: Root }> {
  const container = document.createElement("div")
  document.body.appendChild(container)
  const root = createRoot(container)
  await act(async () => {
    root.render(<CliSection />)
  })
  return { container, root }
}

describe("CliSection — Open in CLI 依赖状态面板(提案 2026-08-06 PR-1)", () => {
  beforeEach(() => {
    ;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true
    mocks.cliDependencyStatus.mockReset()
  })

  it("renders one row per dependency with the state light vocabulary", async () => {
    mocks.cliDependencyStatus.mockResolvedValue([
      { id: "wsl", state: "ok", version: null, detail: null },
      { id: "ah", state: "outdated", version: "1.7.0", detail: "Studio requires ah >= 1.8.2" },
      { id: "claude", state: "broken", version: null, detail: "Windows binary on PATH (/mnt/c/x)" },
      { id: "codex_auth", state: "missing", version: null, detail: null },
    ])
    const { container, root } = await renderSection()

    expect(container.querySelectorAll("[data-cli-dependency]").length).toBe(4)
    expect(container.querySelector('[data-cli-dependency="ah"]')?.textContent).toContain("1.7.0")
    expect(
      container.querySelector('[data-cli-dependency="claude"] [data-cli-dependency-state]')?.getAttribute("data-cli-dependency-state"),
    ).toBe("broken")
    // 一色一义:ok 行是 success 灯,missing/broken 行是 destructive 灯。
    expect(container.querySelector('[data-cli-dependency="wsl"] .bg-success')).toBeTruthy()
    expect(container.querySelector('[data-cli-dependency="codex_auth"] .bg-destructive')).toBeTruthy()
    expect(container.querySelector('[data-cli-dependency="ah"] .bg-warning')).toBeTruthy()

    act(() => {
      root.unmount()
    })
    document.body.removeChild(container)
  })

  it("shows the desktop-only empty state when the runtime is not the desktop app", async () => {
    mocks.cliDependencyStatus.mockResolvedValue(null)
    const { container, root } = await renderSection()

    expect(container.querySelector('[data-cli-section-desktop-only="true"]')).toBeTruthy()
    expect(container.querySelectorAll("[data-cli-dependency]").length).toBe(0)

    act(() => {
      root.unmount()
    })
    document.body.removeChild(container)
  })
})
