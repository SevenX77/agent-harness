// @vitest-environment jsdom

import { act } from "react"
import { createRoot, type Root } from "react-dom/client"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { configureApiToken } from "../../../api/client"
import { getCredentials } from "../../../api/llm"
import { useSettingsPageController } from "./SettingsPage"

;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true

vi.mock("sonner", () => ({
  toast: {
    error: vi.fn(),
    success: vi.fn(),
  },
}))

vi.mock("@/hooks/useAppSettings", () => ({
  useAppSettings: () => ({
    settings: {
      user_id: "default",
      gitea_host: "",
      default_skills_directory: "",
      language: "en",
      remote_model_catalog_enabled: false,
    },
    isLoading: false,
    saveStatus: "idle",
    setUserId: vi.fn(),
    setGiteaHost: vi.fn(),
    setDefaultSkillsDirectory: vi.fn(),
    setLanguage: vi.fn(),
    setRemoteModelCatalogEnabled: vi.fn(),
  }),
}))

vi.mock("@/hooks/useDebouncedCredentialsSave", () => ({
  buildPutPayload: vi.fn(() => ({ providers: [] })),
  useDebouncedCredentialsSave: () => ({
    flush: vi.fn(),
    queue: vi.fn(),
    status: "idle",
  }),
}))

vi.mock("@/hooks/useDebouncedRolesSave", () => ({
  useDebouncedRolesSave: () => ({
    cancel: vi.fn(),
    flush: vi.fn(),
    queue: vi.fn(),
    status: "idle",
  }),
}))

vi.mock("@/hooks/useStudioEventStream", () => ({
  useStudioEventStream: () => ({ connectionLost: false }),
}))

vi.mock("../../../api/llm", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../../api/llm")>()
  return {
    ...actual,
    deleteEndpoint: vi.fn(),
    deleteModelBundle: vi.fn(),
    deleteRole: vi.fn(),
    getCredentials: vi.fn(() => Promise.resolve({ providers: [] })),
    getModelGroups: vi.fn(() => Promise.resolve([])),
    getProviderModels: vi.fn(),
    getRoles: vi.fn(() => Promise.resolve({ models: {}, providers: {}, roles: {} })),
    syncVerifiedCommunityCatalog: vi.fn(),
  }
})

function ControllerProbe() {
  useSettingsPageController()
  return null
}

describe("useSettingsPageController lifecycle", () => {
  let container: HTMLDivElement
  let root: Root

  beforeEach(() => {
    vi.clearAllMocks()
    container = document.createElement("div")
    document.body.appendChild(container)
    root = createRoot(container)
  })

  afterEach(() => {
    if (root) {
      act(() => {
        root.unmount()
      })
    }
    delete (window as { __TAURI_INTERNALS__?: unknown }).__TAURI_INTERNALS__
    configureApiToken(null)
    container?.remove()
  })

  it("hydrates API key credentials as part of the app-level controller mount", async () => {
    await act(async () => {
      root.render(<ControllerProbe />)
    })
    await act(async () => {
      await Promise.resolve()
      await Promise.resolve()
    })

    expect(getCredentials).toHaveBeenCalled()
    expect(vi.mocked(getCredentials).mock.calls[0]?.[0]).toBeUndefined()
  })

  it("waits for the Tauri API token before app-level hydration", async () => {
    ;(window as { __TAURI_INTERNALS__?: unknown }).__TAURI_INTERNALS__ = {}
    configureApiToken(null)

    await act(async () => {
      root.render(<ControllerProbe />)
    })
    await act(async () => {
      await Promise.resolve()
      await Promise.resolve()
    })

    expect(getCredentials).not.toHaveBeenCalled()

    await act(async () => {
      configureApiToken("sidecar-token")
      await Promise.resolve()
      await Promise.resolve()
    })

    expect(getCredentials).toHaveBeenCalled()
  })
})
