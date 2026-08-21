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
  deployVendoredAh: vi.fn(),
}))

vi.mock("@/lib/tauri", () => ({
  cliDependencyStatus: mocks.cliDependencyStatus,
  launchCliInstaller: mocks.launchCliInstaller,
  launchCliUpdate: mocks.launchCliUpdate,
  launchCliLogin: mocks.launchCliLogin,
  deployVendoredAh: mocks.deployVendoredAh,
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
    mocks.deployVendoredAh.mockReset()
  })

  it("renders one row per dependency with the state light vocabulary", async () => {
    mocks.cliDependencyStatus.mockResolvedValue([
      { id: "wsl", state: "ok", version: null, detail: null, account: null },
      { id: "ah", state: "outdated", version: "1.7.0", detail: "Studio requires ah >= 1.8.2", account: null },
      { id: "claude", state: "broken", version: null, detail: "Windows binary on PATH (/mnt/c/x)", account: null },
      { id: "codex_auth", state: "missing", version: null, detail: null, account: null },
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

  // 修订 2026-08-12 —— 行内动作按钮判定表:CLI 行过时 → 更新;登录行常驻「登录」;
  // ah 行缺失/过时 → 「部署」;其余好行没有行内按钮。
  it("offers an update button only on outdated CLI rows and wires it to the updater", async () => {
    mocks.cliDependencyStatus.mockResolvedValue([
      { id: "claude", state: "ok", version: "2.1.228 (Claude Code)", detail: null, account: null },
      { id: "codex", state: "outdated", version: "codex-cli 0.147.0", detail: "latest 0.148.0 available", account: null },
      { id: "ah", state: "outdated", version: "1.7.0", detail: "Studio requires ah >= 1.8.2", account: null },
    ])
    mocks.launchCliUpdate.mockResolvedValue(null)
    const { container, root } = await renderSection()

    expect(container.querySelector('[data-cli-dependency="claude"] [data-cli-row-action]')).toBeNull()
    // ah 行的动作是「部署」不是「更新」(决议 2026-08-12,ah 随 app 打包)。
    expect(
      container.querySelector('[data-cli-dependency="ah"] [data-cli-row-action="deploy"]'),
    ).toBeTruthy()
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

  // 修订 2026-08-12(用户裁决):登录钮常驻——已登录也可能要换账号;登录行显示
  // 账号身份(探测第 5 列)。
  //
  // 2026-08-20 改写(台账 P4):这条用例原本给 `broken` 行喂 `account: null`,
  // 于是它钉住的是缺陷而不是判据——探测脚本当时在 `broken` 分支丢掉了账号,
  // 用例照抄那个形状,看起来一直是绿的。现在两行都带账号:**过期恰恰是最需要
  // 知道当前挂着谁的时刻**,渲染层对 state 一无所知(`row.account ? … : null`),
  // 所以这里断言的是「给了就画」这条契约本身。
  it("keeps the sign-in button on every auth row and shows the signed-in account", async () => {
    mocks.cliDependencyStatus.mockResolvedValue([
      {
        id: "claude_auth",
        state: "broken",
        version: null,
        detail: "token expired",
        account: "expired@example.com",
      },
      { id: "codex_auth", state: "ok", version: null, detail: null, account: "me@example.com" },
    ])
    mocks.launchCliLogin.mockResolvedValue(null)
    const { container, root } = await renderSection()

    // 已登录(ok)的行同样有「登录」= 换账号入口。
    expect(
      container.querySelector('[data-cli-dependency="codex_auth"] [data-cli-row-action="login"]'),
    ).toBeTruthy()
    // 登录身份显式可见。
    expect(container.querySelector('[data-cli-account="codex_auth"]')?.textContent).toBe(
      "me@example.com",
    )
    // token 过期的那一行同样要说出账号。
    expect(container.querySelector('[data-cli-account="claude_auth"]')?.textContent).toBe(
      "expired@example.com",
    )
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

  // 决议 2026-08-12(docs/design/2026-08-12-ah-vendored-auto-deploy.md §2.4):
  // ah 随 app 打包,缺失行给「部署」;部署成功后整体重新探测(显式用户命令,
  // 属允许的 revalidation 触发)。
  it("offers a deploy button on a missing ah row, wires it to the bundled deploy, then re-probes", async () => {
    mocks.cliDependencyStatus.mockResolvedValue([
      { id: "ah", state: "missing", version: null, detail: "wsl.exe returned error", account: null },
    ])
    mocks.deployVendoredAh.mockResolvedValue({
      row: { id: "ah", state: "ok", version: "1.14.3", detail: null, account: null },
    })
    const { container, root } = await renderSection()

    const deployButton = container.querySelector<HTMLButtonElement>(
      '[data-cli-dependency="ah"] [data-cli-row-action="deploy"]',
    )
    expect(deployButton).toBeTruthy()
    expect(mocks.cliDependencyStatus).toHaveBeenCalledTimes(1)

    await act(async () => {
      deployButton?.click()
    })
    expect(mocks.deployVendoredAh).toHaveBeenCalledTimes(1)
    expect(mocks.cliDependencyStatus).toHaveBeenCalledTimes(2)

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
