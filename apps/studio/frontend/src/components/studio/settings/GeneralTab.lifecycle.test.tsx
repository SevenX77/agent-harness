// @vitest-environment jsdom

import { act } from "react"
import { createRoot, type Root } from "react-dom/client"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import {
  getCommunityCatalogConfig,
  getTruthSourceContent,
  getTruthSources,
  type TruthSourcesResponse,
} from "@/api/client"
import { openLocalPath } from "@/lib/tauri"
import { GeneralTab } from "./GeneralTab"
import type { SettingsPageContentProps } from "./types"

;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true

vi.mock("@/api/client", () => ({
  getCommunityCatalogConfig: vi.fn(),
  getTruthSourceContent: vi.fn(),
  getTruthSources: vi.fn(),
}))

vi.mock("@/lib/tauri", () => ({
  openLocalPath: vi.fn(),
  selectSkillDirectory: vi.fn(),
}))

type AppSettingsProp = SettingsPageContentProps["appSettings"]

const emptyTruthSources: TruthSourcesResponse = { sections: [] }

const truthSourcesWithPreview: TruthSourcesResponse = {
  sections: [
    {
      id: "runtime",
      label: "Runtime",
      description: "Runtime truth.",
      sources: [
        {
          id: "llm_credentials",
          label: "LLM credentials",
          path: "C:\\Users\\test\\AppData\\Roaming\\AgentStudio\\llm\\llm_credentials.json",
          kind: "json",
          description: "Credential truth.",
          open_mode: "file",
          exists: true,
          size_bytes: 128,
          updated_at: "2026-07-06T00:00:00Z",
          logs: [],
          can_preview: true,
        },
      ],
    },
  ],
}

function makeAppSettings(overrides: Partial<AppSettingsProp> = {}): AppSettingsProp {
  return {
    userId: "alice",
    giteaHost: "",
    defaultSkillsDirectory: "",
    language: "en",
    remoteModelCatalogEnabled: false,
    isLoading: false,
    saveStatus: "idle",
    setUserId: vi.fn(),
    setGiteaHost: vi.fn(),
    setDefaultSkillsDirectory: vi.fn(),
    setLanguage: vi.fn(),
    setRemoteModelCatalogEnabled: vi.fn(),
    cliSessions: { claude: { model: '', effort: '' }, codex: { model: '', effort: '' }, agents: {} },
    setCliSessions: vi.fn(),
    ...overrides,
  }
}

async function flushEffects(): Promise<void> {
  await act(async () => {
    await Promise.resolve()
  })
}

describe("GeneralTab request lifecycle", () => {
  let container: HTMLDivElement
  let root: Root

  beforeEach(() => {
    vi.mocked(getTruthSources).mockResolvedValue(emptyTruthSources)
    vi.mocked(getCommunityCatalogConfig).mockResolvedValue({
      manifest_url: "https://example.test/catalog.json",
      signing_pubkey: "pubkey",
    })
    vi.mocked(getTruthSourceContent).mockResolvedValue({
      source_id: "llm_credentials",
      path: "C:\\Users\\test\\AppData\\Roaming\\AgentStudio\\llm\\llm_credentials.json",
      kind: "json",
      content: "{}",
      truncated: false,
      size_bytes: 2,
    })
    vi.mocked(openLocalPath).mockResolvedValue(true)
    container = document.createElement("div")
    document.body.appendChild(container)
    root = createRoot(container)
  })

  afterEach(() => {
    act(() => {
      root.unmount()
    })
    container.remove()
    vi.clearAllMocks()
  })

  it("cold-loads settings truth metadata once and does not refetch on rerender", async () => {
    await act(async () => {
      root.render(<GeneralTab appSettings={makeAppSettings()} />)
    })
    await flushEffects()

    expect(getTruthSources).toHaveBeenCalledTimes(1)
    expect(getCommunityCatalogConfig).toHaveBeenCalledTimes(1)
    expect(getTruthSourceContent).not.toHaveBeenCalled()

    await act(async () => {
      root.render(<GeneralTab appSettings={makeAppSettings({ userId: "bob" })} />)
    })
    await flushEffects()

    expect(getTruthSources).toHaveBeenCalledTimes(1)
    expect(getCommunityCatalogConfig).toHaveBeenCalledTimes(1)
    expect(getTruthSourceContent).not.toHaveBeenCalled()
  })

  it("loads truth-source content only after an explicit open action needs preview fallback", async () => {
    vi.mocked(getTruthSources).mockResolvedValue(truthSourcesWithPreview)
    vi.mocked(openLocalPath).mockResolvedValue(false)

    await act(async () => {
      root.render(<GeneralTab appSettings={makeAppSettings()} />)
    })
    await flushEffects()

    expect(getTruthSourceContent).not.toHaveBeenCalled()

    const truthSourcesTrigger = Array.from(container.querySelectorAll("button"))
      .find((button) => button.textContent?.includes("Runtime truth source files"))
    expect(truthSourcesTrigger).toBeDefined()

    await act(async () => {
      truthSourcesTrigger?.dispatchEvent(new MouseEvent("click", { bubbles: true }))
    })
    await flushEffects()

    const openButton = Array.from(container.querySelectorAll("button"))
      .find((button) => button.textContent?.trim() === "Open")
    expect(openButton).toBeDefined()

    await act(async () => {
      openButton?.dispatchEvent(new MouseEvent("click", { bubbles: true }))
    })
    await flushEffects()

    expect(openLocalPath).toHaveBeenCalledWith(
      "C:\\Users\\test\\AppData\\Roaming\\AgentStudio\\llm\\llm_credentials.json",
    )
    expect(getTruthSourceContent).toHaveBeenCalledTimes(1)
    expect(getTruthSourceContent).toHaveBeenCalledWith("llm_credentials")
  })
})
