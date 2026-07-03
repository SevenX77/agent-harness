// @vitest-environment jsdom

import { act, useEffect } from "react"
import { createRoot, type Root } from "react-dom/client"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { toast } from "sonner"
import { configureApiToken } from "../../../api/client"
import { deleteEndpoint, getCredentials, testEndpoint } from "../../../api/llm"
import { useSettingsPageController } from "./SettingsPage"

type Controller = ReturnType<typeof useSettingsPageController>
let capturedController: Controller | null = null

;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true

vi.mock("sonner", () => ({
  toast: {
    error: vi.fn(),
    success: vi.fn(),
    loading: vi.fn(),
    info: vi.fn(),
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

const mockEventStream = vi.hoisted(() => ({ connectionLost: false }))
vi.mock("@/hooks/useStudioEventStream", () => ({
  useStudioEventStream: () => ({ connectionLost: mockEventStream.connectionLost }),
}))

vi.mock("../../../api/llm", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../../api/llm")>()
  return {
    ...actual,
    deleteEndpoint: vi.fn(),
    deleteModelBundle: vi.fn(),
    deleteRole: vi.fn(),
    testEndpoint: vi.fn(() => Promise.resolve({})),
    getCredentials: vi.fn(() => Promise.resolve({ providers: [] })),
    getModelGroups: vi.fn(() => Promise.resolve([])),
    getProviderModels: vi.fn(),
    getRoles: vi.fn(() => Promise.resolve({ models: {}, providers: {}, roles: {} })),
    syncVerifiedCommunityCatalog: vi.fn(),
  }
})

function ControllerProbe({ capture }: { capture?: (controller: Controller) => void }) {
  const controller = useSettingsPageController()
  // Capture in an effect, not during render — reassigning an outer variable
  // during render is a lint-flagged side effect (react-hooks/globals).
  useEffect(() => {
    capture?.(controller)
  })
  return null
}

describe("useSettingsPageController lifecycle", () => {
  let container: HTMLDivElement
  let root: Root

  beforeEach(() => {
    vi.clearAllMocks()
    mockEventStream.connectionLost = false
    capturedController = null
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

  it("refuses a settings mutation when the backend event stream is disconnected", async () => {
    // A mutating action must not fire into an unreachable backend (the request
    // gets no response and surfaces a bare "Backend unavailable" toast, and an
    // optimistic delete removes the card before reverting).
    configureApiToken("sidecar-token")
    mockEventStream.connectionLost = true
    await act(async () => {
      root.render(<ControllerProbe capture={(controller) => { capturedController = controller }} />)
    })
    await act(async () => {
      await Promise.resolve()
      await Promise.resolve()
    })

    act(() => {
      capturedController?.onDeleteProvider("openrouter")
    })

    expect(deleteEndpoint).not.toHaveBeenCalled()
    expect(vi.mocked(toast.error)).toHaveBeenCalled()
    expect(capturedController?.backendReachable).toBe(false)
  })

  it("allows a settings mutation when the backend is reachable", async () => {
    configureApiToken("sidecar-token")
    mockEventStream.connectionLost = false
    await act(async () => {
      root.render(<ControllerProbe capture={(controller) => { capturedController = controller }} />)
    })
    await act(async () => {
      await Promise.resolve()
      await Promise.resolve()
    })

    expect(capturedController?.backendReachable).toBe(true)

    await act(async () => {
      capturedController?.onDeleteProvider("openrouter")
      await Promise.resolve()
    })

    expect(deleteEndpoint).toHaveBeenCalledWith("openrouter")
  })

  it("probes a single endpoint when its tag is activated (item 2)", async () => {
    // Clicking one endpoint tag re-probes only THAT (URL, protocol) cell via the
    // single-endpoint test path, not the whole provider.
    configureApiToken("sidecar-token")
    mockEventStream.connectionLost = false
    await act(async () => {
      root.render(<ControllerProbe capture={(controller) => { capturedController = controller }} />)
    })
    await act(async () => {
      await Promise.resolve()
      await Promise.resolve()
    })

    await act(async () => {
      capturedController?.onProbeEndpoint("qiniu-openai")
      await Promise.resolve()
      await Promise.resolve()
    })

    expect(testEndpoint).toHaveBeenCalledWith("qiniu-openai")
  })

  it("refuses to probe an endpoint when the backend is disconnected (item 2 + readiness gate)", async () => {
    configureApiToken("sidecar-token")
    mockEventStream.connectionLost = true
    await act(async () => {
      root.render(<ControllerProbe capture={(controller) => { capturedController = controller }} />)
    })
    await act(async () => {
      await Promise.resolve()
      await Promise.resolve()
    })

    act(() => {
      capturedController?.onProbeEndpoint("qiniu-openai")
    })

    expect(testEndpoint).not.toHaveBeenCalled()
    expect(vi.mocked(toast.error)).toHaveBeenCalled()
  })
})
