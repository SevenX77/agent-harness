// @vitest-environment jsdom

// J-01.K (批示轮三 R3-2) — the registry snapshot is ONE shared store, not three
// diverging React copies. A probe/test write response carries the canonical
// registry snapshot (backend `_registry_response` includes fresh
// `model_groups`); committing it must converge EVERY consumer — the Roles
// "Available Models" sidebar and the Copilot tab project the same
// `modelGroups` the API-Key page's write already refreshed — in the same
// frame, with NO extra GET /llm/registry. These tests drive the REAL
// `api/llm` module (only the HTTP client is scripted) through the real
// controller, reproducing the fresh-machine journey: deepseek-v4-flash sits
// at `historical_ready` (blue), a manual probe verifies it, and the sidebar
// projection must read `ready` (green) immediately.

import { act, useEffect } from "react"
import { createRoot, type Root } from "react-dom/client"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import type { AxiosResponse } from "axios"
import {
  probeRoute,
  resetLlmApiCachesForTests,
  testProviderModels,
  type ModelGroup,
  type ProviderUiState,
  type RegistryResponse,
} from "../../../api/llm"
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
      community_sharing_choice: "declined",
    },
    isLoading: false,
    saveStatus: "idle",
    setUserId: vi.fn(),
    setGiteaHost: vi.fn(),
    setDefaultSkillsDirectory: vi.fn(),
    setLanguage: vi.fn(),
    setCommunitySharingChoice: vi.fn(),
    setCliSessions: vi.fn(),
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
  shouldApplyExternalRolesRefresh: (status: string) => status !== "pending" && status !== "saving",
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

vi.mock("../llm-roles-cache", () => ({
  LLM_ROLES_SWR_KEY: "llm/roles",
  syncLlmRolesCache: vi.fn(),
}))

vi.mock("./SettingsPageContent", () => ({
  SettingsPageContent: () => null,
}))

const clientMocks = vi.hoisted(() => ({
  get: vi.fn<(url: string) => Promise<{ data: unknown }>>(),
  post: vi.fn<(url: string, body?: unknown) => Promise<{ data: unknown }>>(),
  put: vi.fn<(url: string, body?: unknown) => Promise<{ data: unknown }>>(),
  delete: vi.fn<(url: string) => Promise<{ data: unknown }>>(),
}))

vi.mock("@/api/client", () => ({
  api: clientMocks,
  apiClientConfigChangedEvent: "studio-api-client-config-changed",
  authenticatedApiReady: () => true,
}))

const ROUTE_ID = "deepseek:deepseek-v4-flash"
const ENDPOINT_ID = "deepseek"

function registrySnapshot(uiState: ProviderUiState): RegistryResponse {
  const group: ModelGroup = {
    canonical_id: "deepseek-v4-flash",
    display_name: "DeepSeek V4 Flash",
    section_label: "deepseek",
    provider_models: [
      {
        route_id: ROUTE_ID,
        endpoint_id: ENDPOINT_ID,
        provider_label: "DeepSeek",
        provider_kind: "official",
        provider_model_id: "deepseek-v4-flash",
        ui_state: uiState,
        ui_detail: null,
        retry_at: null,
        reason_code: null,
        capability_state: "known",
        capabilities: {},
        call_method_id: "openai_chat_completions",
        copilot_sdk_compatible: true,
      },
    ],
    status_summary: {
      ready: uiState === "ready" ? 1 : 0,
      untested: 0,
      cooling_down: 0,
      historical_ready: uiState === "historical_ready" ? 1 : 0,
      failed: 0,
      off: 0,
    },
    capability_summary: {
      capability_known_count: 1,
      thinking: "unknown",
      tools: "unknown",
      structured_output: "unknown",
    },
  } as ModelGroup
  return {
    provider_endpoints: {
      [ENDPOINT_ID]: {
        endpoint_id: ENDPOINT_ID,
        display_name: "DeepSeek",
        protocol: "openai_compatible",
        base_url: "https://api.deepseek.example",
        api_key: "sk-test",
      },
    },
    provider_routes: {
      [ROUTE_ID]: {
        route_id: ROUTE_ID,
        endpoint_id: ENDPOINT_ID,
        route_slug: "deepseek-v4-flash",
        provider_model_id: "deepseek-v4-flash",
        canonical_id: "deepseek-v4-flash",
        display_name: "DeepSeek V4 Flash",
        status: uiState === "ready" ? "verified" : "untested",
        ui_state: uiState,
        metadata: {},
        capabilities: {},
      },
    },
    model_profiles: {},
    roles: {},
    canonical_groups: [],
    model_groups: [group],
    lint_results: [],
    setup_required: false,
  } as unknown as RegistryResponse
}

function asResponse(data: unknown): Promise<AxiosResponse> {
  return Promise.resolve({ data } as AxiosResponse)
}

function ControllerProbe() {
  const controller = useSettingsPageController()
  useEffect(() => {
    capturedController = controller
  })
  return null
}

let container: HTMLDivElement | null = null
let root: Root | null = null

async function renderController(): Promise<void> {
  container = document.createElement("div")
  document.body.appendChild(container)
  await act(async () => {
    root = createRoot(container!)
    root.render(<ControllerProbe />)
  })
  // Let the initial credentials + lazy roles loads settle.
  await act(async () => {
    await Promise.resolve()
  })
}

function sidebarUiState(): ProviderUiState | undefined {
  return capturedController?.modelGroups[0]?.provider_models[0]?.ui_state
}

function registryGetCount(): number {
  return clientMocks.get.mock.calls.filter(([url]) => url === "/llm/registry").length
}

// The scripted backend is a truth server: writes advance `serverTruth`, and
// every later read serves the SAME truth — exactly how the real sidecar
// behaves after a probe verifies a route.
let serverTruth: RegistryResponse

beforeEach(() => {
  vi.clearAllMocks()
  resetLlmApiCachesForTests()
  capturedController = null
  serverTruth = registrySnapshot("historical_ready")
  clientMocks.get.mockImplementation((url: string) => {
    if (url === "/llm/registry") return asResponse(serverTruth)
    if (url === "/llm/roles") {
      return asResponse({
        registry: serverTruth,
        roles_data: { models: {}, providers: {}, roles: {} },
      })
    }
    return asResponse({})
  })
})

afterEach(async () => {
  await act(async () => {
    root?.unmount()
  })
  container?.remove()
  container = null
  root = null
})

describe("registry snapshot is one shared store (J-01.K / R3-2)", () => {
  it("freshens the Roles-sidebar model groups from a probe write response in the same frame, without a registry refetch", async () => {
    clientMocks.post.mockImplementation((url: string) => {
      if (url.endsWith("/probe")) {
        serverTruth = registrySnapshot("ready")
        return asResponse(serverTruth)
      }
      return asResponse({})
    })

    await renderController()
    expect(sidebarUiState()).toBe("historical_ready")
    const registryGetsBeforeProbe = registryGetCount()

    await act(async () => {
      await probeRoute(ROUTE_ID)
    })

    // The write response carried the canonical snapshot (ready). All
    // consumers of the shared store must project it — the ledger's pinned
    // regression: 「probe 响应后 Roles 侧栏状态即新」.
    expect(sidebarUiState()).toBe("ready")
    // Convergence came from the write response, not from a refetch (SSOT:
    // the write response IS the truth-change trigger).
    expect(registryGetCount()).toBe(registryGetsBeforeProbe)
  })

  it("freshens the model groups from an endpoint model-test write response (the API-Key page Test flow)", async () => {
    clientMocks.post.mockImplementation((url: string) => {
      if (url.endsWith("/models/test")) {
        serverTruth = registrySnapshot("ready")
        return asResponse({ registry: serverTruth, results: [] })
      }
      return asResponse({})
    })

    await renderController()
    expect(sidebarUiState()).toBe("historical_ready")

    await act(async () => {
      await testProviderModels({ provider_id: ENDPOINT_ID, model_ids: ["deepseek-v4-flash"] })
    })

    expect(sidebarUiState()).toBe("ready")
  })
})
