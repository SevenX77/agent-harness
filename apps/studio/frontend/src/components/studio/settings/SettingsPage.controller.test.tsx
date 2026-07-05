// @vitest-environment jsdom

import { act, useEffect } from "react"
import { createRoot, type Root } from "react-dom/client"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { toast } from "sonner"
import { configureApiToken } from "../../../api/client"
import { deleteEndpoint, forceTestEndpoint, getCredentials, getModelGroups, getProviderModels, getRoles } from "../../../api/llm"
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
    warning: vi.fn(),
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

const llmRolesCacheMocks = vi.hoisted(() => ({
  syncLlmRolesCache: vi.fn(),
}))
vi.mock("../llm-roles-cache", () => ({
  LLM_ROLES_SWR_KEY: "llm/roles",
  syncLlmRolesCache: llmRolesCacheMocks.syncLlmRolesCache,
}))

const mockRolesSave = vi.hoisted(() => ({ status: "idle" }))
vi.mock("@/hooks/useDebouncedRolesSave", () => ({
  shouldApplyExternalRolesRefresh: (status: string) => status !== "pending" && status !== "saving",
  useDebouncedRolesSave: () => ({
    cancel: vi.fn(),
    flush: vi.fn(),
    queue: vi.fn(),
    status: mockRolesSave.status,
  }),
}))

const mockEventStream = vi.hoisted(() => ({
  callbacks: null as null | import("@/hooks/useStudioEventStream").StudioEventStreamCallbacks,
  connectionLost: false,
}))
vi.mock("@/hooks/useStudioEventStream", () => ({
  useStudioEventStream: (callbacks: import("@/hooks/useStudioEventStream").StudioEventStreamCallbacks) => {
    mockEventStream.callbacks = callbacks
    return { connectionLost: mockEventStream.connectionLost }
  },
}))

vi.mock("../../../api/llm", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../../api/llm")>()
  return {
    ...actual,
    deleteEndpoint: vi.fn(),
    deleteModelBundle: vi.fn(),
    deleteRole: vi.fn(),
    forceTestEndpoint: vi.fn(),
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
    mockRolesSave.status = "idle"
    mockEventStream.callbacks = null
    mockEventStream.connectionLost = false
    llmRolesCacheMocks.syncLlmRolesCache.mockReset()
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

  it("does not refetch credentials or roles when the window receives focus", async () => {
    await act(async () => {
      root.render(<ControllerProbe />)
    })
    await act(async () => {
      await Promise.resolve()
      await Promise.resolve()
      await Promise.resolve()
    })

    vi.mocked(getCredentials).mockClear()
    vi.mocked(getRoles).mockClear()
    vi.mocked(getModelGroups).mockClear()

    act(() => {
      window.dispatchEvent(new Event("focus"))
    })
    await act(async () => {
      await Promise.resolve()
      await Promise.resolve()
    })

    expect(getCredentials).not.toHaveBeenCalled()
    expect(getRoles).not.toHaveBeenCalled()
    expect(getModelGroups).not.toHaveBeenCalled()
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

  it("does not apply roles_changed refresh while a roles save is still pending or saving", async () => {
    configureApiToken("sidecar-token")
    mockRolesSave.status = "saving"
    await act(async () => {
      root.render(<ControllerProbe capture={(controller) => { capturedController = controller }} />)
    })
    await act(async () => {
      await Promise.resolve()
      await Promise.resolve()
      await Promise.resolve()
    })

    expect(capturedController?.rolesData).not.toBeNull()
    const getRolesCallsAfterInitialLoad = vi.mocked(getRoles).mock.calls.length
    const getModelGroupsCallsAfterInitialLoad = vi.mocked(getModelGroups).mock.calls.length

    act(() => {
      mockEventStream.callbacks?.onRolesChanged()
    })
    await act(async () => {
      await Promise.resolve()
      await Promise.resolve()
    })

    expect(getRoles).toHaveBeenCalledTimes(getRolesCallsAfterInitialLoad)
    expect(getModelGroups).toHaveBeenCalledTimes(getModelGroupsCallsAfterInitialLoad)

    mockRolesSave.status = "idle"
    await act(async () => {
      root.render(<ControllerProbe capture={(controller) => { capturedController = controller }} />)
    })
    act(() => {
      mockEventStream.callbacks?.onRolesChanged()
    })
    await act(async () => {
      await Promise.resolve()
      await Promise.resolve()
    })

    expect(getRoles).toHaveBeenCalledTimes(getRolesCallsAfterInitialLoad + 1)
    expect(getModelGroups).toHaveBeenCalledTimes(getModelGroupsCallsAfterInitialLoad + 1)
  })

  it("syncs successful roles_changed refreshes into the shared roles cache", async () => {
    configureApiToken("sidecar-token")
    const initialRoles = { schema_version: 3, models: {}, providers: {}, roles: { initial: {} } }
    const refreshedRoles = { schema_version: 3, models: {}, providers: {}, roles: { refreshed: {} } }
    vi.mocked(getRoles)
      .mockResolvedValueOnce(initialRoles as never)
      .mockResolvedValueOnce(refreshedRoles as never)
    vi.mocked(getModelGroups).mockResolvedValue([])

    await act(async () => {
      root.render(<ControllerProbe capture={(controller) => { capturedController = controller }} />)
    })
    await act(async () => {
      await Promise.resolve()
      await Promise.resolve()
      await Promise.resolve()
    })

    llmRolesCacheMocks.syncLlmRolesCache.mockClear()
    act(() => {
      mockEventStream.callbacks?.onRolesChanged()
    })
    await act(async () => {
      await Promise.resolve()
      await Promise.resolve()
      await Promise.resolve()
    })

    expect(capturedController?.rolesData).toEqual(refreshedRoles)
    expect(llmRolesCacheMocks.syncLlmRolesCache).toHaveBeenCalledWith(refreshedRoles)
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

  it("does not fire a get-models probe for an endpoint with no owning provider (item 2 safe no-op)", async () => {
    // A tag click routes through the owning provider's card-Test flow. An
    // endpoint with no matching provider draft (nothing to scope to) is a safe
    // no-op — it must not crash or fire a get-models call. The positive path
    // (owner found → scoped get-models with the card-Test toast) is verified in
    // the browser, since it needs rendered provider drafts this mock omits.
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

    expect(getProviderModels).not.toHaveBeenCalled()
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

    expect(getProviderModels).not.toHaveBeenCalled()
    expect(vi.mocked(toast.error)).toHaveBeenCalled()
  })

  // PM 2026-07-03: the Re-probe icon (protocol_unsupported cells) hung on a
  // "loading" toast far longer than a single endpoint-tag probe. Root cause:
  // forceReprobeEndpoint discarded forceTestEndpoint's own response (which
  // already carries the fresh registry) and instead made a SECOND network
  // round trip — a full getCredentials({hydrateSecrets}) reload that
  // re-decrypts every provider's secret. onProbeEndpoint's scoped
  // runProviderGetModels never does this extra round trip; forceReprobeEndpoint
  // must not either.
  it("re-probes a protocol_unsupported endpoint by merging forceTestEndpoint's own response, without a second getCredentials round trip", async () => {
    configureApiToken("sidecar-token")
    mockEventStream.connectionLost = false
    vi.mocked(forceTestEndpoint).mockResolvedValue({
      providers: [{ id: "qiniu-google", name: "Qiniu", api_key: "sk-1", base_url: "https://qiniu.example", provider_type: "google_genai", last_test_status: "ok" }],
    })
    await act(async () => {
      root.render(<ControllerProbe capture={(controller) => { capturedController = controller }} />)
    })
    await act(async () => {
      await Promise.resolve()
      await Promise.resolve()
    })

    const getCredentialsCallsBeforeReprobe = vi.mocked(getCredentials).mock.calls.length

    await act(async () => {
      capturedController?.onForceEndpointTest("qiniu-google")
      await Promise.resolve()
      await Promise.resolve()
    })

    expect(forceTestEndpoint).toHaveBeenCalledWith("qiniu-google")
    expect(vi.mocked(getCredentials).mock.calls.length).toBe(getCredentialsCallsBeforeReprobe)
  })

  it("omits protocol_unsupported endpoints from the full-card routine Test queue", async () => {
    configureApiToken("sidecar-token")
    mockEventStream.connectionLost = false
    vi.mocked(getCredentials).mockResolvedValue({
      providers: [
        {
          id: "openrouter-openai",
          name: "OpenRouter",
          api_key: "sk-openrouter",
          base_url: "https://openrouter.ai/api",
          provider_type: "openai_compatible",
          last_test_status: "ok",
        },
        {
          id: "openrouter-anthropic",
          name: "OpenRouter",
          api_key: "sk-openrouter",
          base_url: "https://openrouter.ai/api",
          provider_type: "anthropic_compatible",
          last_test_status: "ok",
        },
        {
          id: "openrouter-google",
          name: "OpenRouter",
          api_key: "sk-openrouter",
          base_url: "https://openrouter.ai/api",
          provider_type: "google_genai",
          last_test_status: "protocol_unsupported",
          last_error_code: "protocol_unsupported",
          last_test_message: "Protocol not supported.",
        },
      ],
    })
    vi.mocked(getProviderModels).mockResolvedValue({
      status: "ok",
      latency_ms: null,
      model_seen: "~anthropic/claude-sonnet-latest",
      message: "Generation verified.",
      available_models: [{ id: "~anthropic/claude-sonnet-latest" }],
      available_sdks: ["openai_compatible"],
    })

    await act(async () => {
      root.render(<ControllerProbe capture={(controller) => { capturedController = controller }} />)
    })
    await act(async () => {
      await Promise.resolve()
      await Promise.resolve()
      await Promise.resolve()
    })

    await act(async () => {
      capturedController?.onGetProviderModels("openrouter-openai")
      for (let index = 0; index < 10; index += 1) await Promise.resolve()
    })

    expect(getProviderModels).toHaveBeenCalledTimes(2)
    expect(vi.mocked(getProviderModels).mock.calls.map(([request]) => request.id)).toEqual([
      "openrouter-openai",
      "openrouter-anthropic",
    ])
    expect(vi.mocked(toast.warning)).not.toHaveBeenCalledWith(
      expect.stringContaining("2/3 endpoints"),
      expect.anything(),
    )
  })

  it("omits explicitly disabled endpoints from the full-card routine Test queue", async () => {
    configureApiToken("sidecar-token")
    mockEventStream.connectionLost = false
    vi.mocked(getCredentials).mockResolvedValue({
      providers: [
        {
          id: "openrouter-openai",
          name: "OpenRouter",
          api_key: "sk-openrouter",
          base_url: "https://openrouter.ai/api",
          provider_type: "openai_compatible",
          endpoint_status: "verified",
          last_test_status: "ok",
        },
        {
          id: "openrouter-anthropic",
          name: "OpenRouter",
          api_key: "sk-openrouter",
          base_url: "https://openrouter.ai/api",
          provider_type: "anthropic_compatible",
          endpoint_status: "verified",
          last_test_status: "ok",
        },
        {
          id: "openrouter-google",
          name: "OpenRouter",
          api_key: "sk-openrouter",
          base_url: "https://openrouter.ai/api",
          provider_type: "google_genai",
          endpoint_status: "disabled",
          last_test_status: "untested",
        },
      ],
    })
    vi.mocked(getProviderModels).mockResolvedValue({
      status: "ok",
      latency_ms: null,
      model_seen: "~anthropic/claude-sonnet-latest",
      message: "Generation verified.",
      available_models: [{ id: "~anthropic/claude-sonnet-latest" }],
      available_sdks: ["openai_compatible"],
    })

    await act(async () => {
      root.render(<ControllerProbe capture={(controller) => { capturedController = controller }} />)
    })
    await act(async () => {
      await Promise.resolve()
      await Promise.resolve()
      await Promise.resolve()
    })

    await act(async () => {
      capturedController?.onGetProviderModels("openrouter-openai")
      for (let index = 0; index < 10; index += 1) await Promise.resolve()
    })

    expect(getProviderModels).toHaveBeenCalledTimes(2)
    expect(vi.mocked(getProviderModels).mock.calls.map(([request]) => request.id)).toEqual([
      "openrouter-openai",
      "openrouter-anthropic",
    ])
  })
})
