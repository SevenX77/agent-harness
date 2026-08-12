// @vitest-environment jsdom

import { beforeEach, describe, expect, it, vi } from "vitest"
import { act } from "react"
import { createRoot, type Root } from "react-dom/client"
import { CliSection } from "./CliSection"
import type { CliSessionSettings } from "@/api/types"

const mocks = vi.hoisted(() => ({
  cliDependencyStatus: vi.fn(),
  launchCliInstaller: vi.fn(),
  launchCliUpdate: vi.fn(),
  launchCliLogin: vi.fn(),
}))

vi.mock("@/lib/tauri", () => ({
  cliDependencyStatus: mocks.cliDependencyStatus,
  launchCliInstaller: mocks.launchCliInstaller,
  launchCliUpdate: mocks.launchCliUpdate,
  launchCliLogin: mocks.launchCliLogin,
}))

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, options?: { defaultValue?: string }) => options?.defaultValue ?? key,
  }),
}))

function emptySessionSettings(): CliSessionSettings {
  return {
    claude: { model: "", effort: "" },
    codex: { model: "", effort: "" },
    agents: {},
  }
}

async function renderSection(
  settings?: { value: CliSessionSettings; onChange: (next: CliSessionSettings) => void },
): Promise<{ container: HTMLElement; root: Root }> {
  const container = document.createElement("div")
  document.body.appendChild(container)
  const root = createRoot(container)
  await act(async () => {
    root.render(<CliSection settings={settings} />)
  })
  return { container, root }
}

function unmount(container: HTMLElement, root: Root) {
  act(() => {
    root.unmount()
  })
  document.body.removeChild(container)
}

describe("CliSection — Open in CLI 依赖状态面板(提案 2026-08-06 PR-1)", () => {
  beforeEach(() => {
    ;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true
    mocks.cliDependencyStatus.mockReset()
    mocks.launchCliInstaller.mockReset()
    mocks.launchCliUpdate.mockReset()
    mocks.launchCliLogin.mockReset()
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

    unmount(container, root)
  })

  it("shows the desktop-only empty state when the runtime is not the desktop app", async () => {
    mocks.cliDependencyStatus.mockResolvedValue(null)
    const { container, root } = await renderSection()

    expect(container.querySelector('[data-cli-section-desktop-only="true"]')).toBeTruthy()
    expect(container.querySelectorAll("[data-cli-dependency]").length).toBe(0)

    unmount(container, root)
  })

  // 修订 2026-08-12 —— 行内动作按钮判定表:CLI 行过时 → 更新;登录行缺失/损坏 →
  // 登录;好行/ah 行没有行内按钮(ah 的修复入口是区头「安装 / 修复」)。
  it("offers an update button only on outdated CLI rows and wires it to the updater", async () => {
    mocks.cliDependencyStatus.mockResolvedValue([
      { id: "claude", state: "ok", version: "2.1.228 (Claude Code)", detail: null },
      { id: "codex", state: "outdated", version: "codex-cli 0.147.0", detail: "latest 0.148.0 available" },
      { id: "ah", state: "outdated", version: "1.7.0", detail: "Studio requires ah >= 1.8.2" },
    ])
    mocks.launchCliUpdate.mockResolvedValue(null)
    const { container, root } = await renderSection()

    expect(container.querySelector('[data-cli-dependency="claude"] [data-cli-row-action]')).toBeNull()
    expect(container.querySelector('[data-cli-dependency="ah"] [data-cli-row-action]')).toBeNull()
    const updateButton = container.querySelector<HTMLButtonElement>(
      '[data-cli-dependency="codex"] [data-cli-row-action="update"]',
    )
    expect(updateButton).toBeTruthy()

    await act(async () => {
      updateButton?.click()
    })
    expect(mocks.launchCliUpdate).toHaveBeenCalledWith("codex")

    unmount(container, root)
  })

  it("offers a sign-in button on missing/broken auth rows and wires it to the login console", async () => {
    mocks.cliDependencyStatus.mockResolvedValue([
      { id: "claude_auth", state: "broken", version: null, detail: "token expired" },
      { id: "codex_auth", state: "ok", version: null, detail: null },
    ])
    mocks.launchCliLogin.mockResolvedValue(null)
    const { container, root } = await renderSection()

    expect(container.querySelector('[data-cli-dependency="codex_auth"] [data-cli-row-action]')).toBeNull()
    const loginButton = container.querySelector<HTMLButtonElement>(
      '[data-cli-dependency="claude_auth"] [data-cli-row-action="login"]',
    )
    expect(loginButton).toBeTruthy()

    await act(async () => {
      loginButton?.click()
    })
    expect(mocks.launchCliLogin).toHaveBeenCalledWith("claude")

    unmount(container, root)
  })

  // 修订 2026-08-12 —— 会话配置全部下拉:两个 provider 各 模型+effort,三个 MoirAI
  // worker 各 模型+effort;没有任何自由输入框。
  it("renders model and effort as selects for providers and MoirAI workers, with no free-text inputs", async () => {
    mocks.cliDependencyStatus.mockResolvedValue([])
    const { container, root } = await renderSection({
      value: emptySessionSettings(),
      onChange: () => {},
    })

    for (const provider of ["claude", "codex"]) {
      const row = container.querySelector(`[data-cli-provider-config="${provider}"]`)
      expect(row?.querySelectorAll('[role="combobox"]').length).toBe(2)
    }
    for (const agent of ["clotho", "lachesis", "atropos"]) {
      const row = container.querySelector(`[data-cli-agent-config="${agent}"]`)
      expect(row?.querySelectorAll('[role="combobox"]').length).toBe(2)
    }
    expect(container.querySelectorAll("input").length).toBe(0)

    unmount(container, root)
  })
})
