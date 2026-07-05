import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import { toast } from "sonner"
import { apiClientConfigChangedEvent, authenticatedApiReady } from "@/api/client"
import { useAppSettings } from "@/hooks/useAppSettings"
import { buildPutPayload, useDebouncedCredentialsSave } from "@/hooks/useDebouncedCredentialsSave"
import { shouldApplyExternalRolesRefresh, useDebouncedRolesSave } from "@/hooks/useDebouncedRolesSave"
import { composeRequestErrorMessage, composeTestErrorMessage } from "@/lib/llm-error-messages"
import i18n from "@/i18n"
import { useStudioEventStream } from "@/hooks/useStudioEventStream"
import { deleteEndpoint, deleteModelBundle, deleteRole, deleteRoute, forceTestEndpoint, getCredentials, getModelGroups, getProviderModels, getRoles, syncVerifiedCommunityCatalog, type CredentialsState, type ModelGroup, type ModelInfo, type ProviderTestResponse, type ProviderTestResult, type RolesData } from "../../../api/llm"
import { clearActiveProbeEndpoints, updateActiveProbeEndpoint } from "../api-keys/active-probe-store"
import type { AddProviderFormSubmission } from "../api-keys"
import { SettingsPageContent } from "./SettingsPageContent"
import { blankThirdPartyProviderDraft, draftsFromCredentials, draftFromAddProviderSubmission, inferProviderKind, providerCachedTestResult, providerDraftForAction, providerDraftIdentityKey, providerEndpointDraftsForAction, providerTestParamsFingerprint, providerTestParamsMatch } from "./provider-utils"
import { normalizeRolesDraft, validateRolesDraft } from "./role-utils"
import type { ProviderDraft, ProviderDraftChangeOptions, SettingsPageController, SettingsPageProps, SettingsPageViewProps, SettingsTab } from "./types"

const emptyCredentials: CredentialsState = { providers: [] }
const emptyModelGroups: ModelGroup[] = []
const emptyActiveProbeModelIdsByEndpoint: Record<string, string[]> = Object.freeze({})

function useAuthenticatedApiReady(): boolean {
  const [ready, setReady] = useState(() => authenticatedApiReady())

  useEffect(() => {
    if (typeof window === "undefined") return undefined
    const handleConfigChange = () => setReady(authenticatedApiReady())
    window.addEventListener(apiClientConfigChangedEvent, handleConfigChange)
    handleConfigChange()
    return () => {
      window.removeEventListener(apiClientConfigChangedEvent, handleConfigChange)
    }
  }, [])

  return ready
}

export async function refreshLoadedLlmRolesProjection({
  loadModelGroups = getModelGroups,
  loadRoles = getRoles,
  rolesLoaded,
  setModelGroups,
  setRolesData,
  setRolesError,
}: {
  loadModelGroups?: () => Promise<ModelGroup[]>
  loadRoles?: () => Promise<RolesData>
  rolesLoaded: boolean
  setModelGroups: (next: ModelGroup[]) => void
  setRolesData: (next: RolesData) => void
  setRolesError: (next: string | null) => void
}) {
  if (!rolesLoaded) return
  try {
    const [nextRoles, nextModelGroups] = await Promise.all([loadRoles(), loadModelGroups()])
    setRolesData(nextRoles)
    setModelGroups(nextModelGroups)
    setRolesError(null)
  } catch {
    setRolesError("Roles unavailable")
  }
}

export function isStaleRouteReferenceError(error: unknown): boolean {
  return errorText(error).toLowerCase().includes("references unknown route")
}

export function modelGroupsReferenceMissingCredentialProviders(
  modelGroups: ModelGroup[],
  credentials: CredentialsState,
): boolean {
  const providerIds = new Set(credentials.providers.map((provider) => provider.id))
  if (providerIds.size === 0) return modelGroups.some((group) => group.provider_models.length > 0)
  return modelGroups.some((group) => group.provider_models.some((providerModel) => {
    const endpointId = providerModel.endpoint_id ?? providerModel.route_id.split(":")[0]
    return Boolean(endpointId && !providerIds.has(endpointId))
  }))
}

export function shouldSyncRemoteModelCatalog({
  settingsLoading,
  enabled,
  alreadySynced,
}: {
  settingsLoading: boolean
  enabled: boolean
  alreadySynced: boolean
}): boolean {
  return !settingsLoading && enabled && !alreadySynced
}

function errorText(error: unknown): string {
  if (typeof error === "string") return error
  if (typeof error !== "object" || error === null) return ""
  const chunks: string[] = []
  const message = (error as { message?: unknown }).message
  if (typeof message === "string") chunks.push(message)
  const response = (error as { response?: unknown }).response
  if (typeof response === "object" && response !== null) {
    const data = (response as { data?: unknown }).data
    if (typeof data === "string") chunks.push(data)
    if (typeof data === "object" && data !== null) {
      const detail = (data as { detail?: unknown }).detail
      const responseMessage = (data as { message?: unknown }).message
      if (typeof detail === "string") chunks.push(detail)
      if (typeof responseMessage === "string") chunks.push(responseMessage)
    }
  }
  return chunks.join(" ")
}

function draftEditableSignature(draft: ProviderDraft): string {
  const rows = (draft.base_urls?.length ? draft.base_urls : [{
    id: draft.id,
    value: draft.base_url,
    provider_type: draft.provider_type,
  }]).map((row) => ({
    value: row.value.trim(),
  }))
  return JSON.stringify({
    id: draft.id,
    name: draft.name,
    base_url: draft.base_url.trim(),
    api_key: draft.api_key,
    base_urls: rows,
  })
}

export function reconcileDraftsWithCredentials(
  credentials: CredentialsState,
  currentDrafts: ProviderDraft[],
  dirtyProviderIds: Set<string>,
  deletedProviderIds: Set<string>,
): ProviderDraft[] {
  const credentialDrafts = draftsFromCredentials(credentials)
  const credentialDraftIds = new Set(credentialDrafts.map((draft) => draft.id))
  for (const deletedProviderId of deletedProviderIds) {
    if (!credentialDraftIds.has(deletedProviderId)) {
      deletedProviderIds.delete(deletedProviderId)
    }
  }
  const nextDrafts = credentialDrafts.filter((draft) => !deletedProviderIds.has(draft.id))
  if (currentDrafts.length === 0) return nextDrafts
  const currentById = new Map(currentDrafts.map((draft) => [draft.id, draft]))
  const nextIds = new Set(nextDrafts.map((draft) => draft.id))
  const reconciled = nextDrafts.map((nextDraft) => {
    const currentDraft = currentById.get(nextDraft.id)
    if (!currentDraft || !dirtyProviderIds.has(nextDraft.id)) return nextDraft
    if (draftEditableSignature(currentDraft) === draftEditableSignature(nextDraft)) {
      dirtyProviderIds.delete(nextDraft.id)
      return nextDraft
    }
    return currentDraft
  })
  // A just-saved provider is rebuilt from credentials under a DIFFERENT id than
  // its locally-minted draft (`custom-<uuid>` → `custom-<uuid>-<protocol>`), so
  // an id-only "not yet persisted" check keeps the stale local copy alongside
  // the reconciled one — the duplicate-card bug. Drop any dirty local draft
  // whose stable provider IDENTITY (name + api_key) is already represented in
  // the reconciled set; only genuinely-unsaved providers survive.
  const nextIdentityKeys = new Set(nextDrafts.map(providerDraftIdentityKey))
  const dirtyDraftsNotInCredentials = currentDrafts.filter((draft) => (
    dirtyProviderIds.has(draft.id)
    && !nextIds.has(draft.id)
    && !nextIdentityKeys.has(providerDraftIdentityKey(draft))
  ))
  return [...reconciled, ...dirtyDraftsNotInCredentials]
}

export function activeProbeModelIdsForDraft(
  draft: ProviderDraft,
  activeProbeModelIdsByEndpoint: Record<string, string[]>,
): Record<string, string[]> {
  const endpointIds = new Set(providerEndpointDraftsForAction(draft).map((endpointDraft) => endpointDraft.id))
  const entries = Object.entries(activeProbeModelIdsByEndpoint).filter(([endpointId, modelIds]) => (
    endpointIds.has(endpointId) && modelIds.length > 0
  ))
  if (entries.length === 0) return emptyActiveProbeModelIdsByEndpoint
  return Object.fromEntries(entries)
}

function modelInfoEvidenceRank(model: ModelInfo): number {
  if (
    model.status === "verified" ||
    model.status === "probe-verified" ||
    model.ui_state === "ready" ||
    model.ui_state === "historical_ready" ||
    (model.verified_profile_count ?? 0) > 0 ||
    (model.verified_profiles ?? []).some((profile) => profile.status === "ready")
  ) return 4
  if (model.status === "failed") return 3
  if (model.status === "disabled") return 2
  if (model.status === "testing") return 1
  return 0
}

function mergeModelInfo(previous: ModelInfo, incoming: ModelInfo): ModelInfo {
  const previousRank = modelInfoEvidenceRank(previous)
  const incomingRank = modelInfoEvidenceRank(incoming)
  const winner = incomingRank >= previousRank ? incoming : previous
  const base = winner === incoming ? previous : incoming
  const merged: ModelInfo = { ...base, ...winner }
  const mergedCapabilities = {
    ...(base.capabilities ?? {}),
    ...(winner.capabilities ?? {}),
  }
  if (Object.keys(mergedCapabilities).length > 0) {
    merged.capabilities = mergedCapabilities
  } else {
    delete merged.capabilities
  }
  return merged
}

function mergeModelInfos(left: ModelInfo[] = [], right: ModelInfo[] = []): ModelInfo[] {
  const merged = new Map<string, ModelInfo>()
  for (const model of left) merged.set(model.id, model)
  for (const model of right) {
    const previous = merged.get(model.id)
    merged.set(model.id, previous ? mergeModelInfo(previous, model) : model)
  }
  return Array.from(merged.values())
}

function mergeStrings(left: string[] = [], right: string[] = []): string[] {
  return Array.from(new Set([...left, ...right]))
}

function resetProviderTestOutcome(
  provider: CredentialsState["providers"][number],
): CredentialsState["providers"][number] {
  return {
    ...provider,
    last_test_status: "untested",
    last_test_at: "",
    last_test_message: "",
    last_error_code: "",
    available_models: [],
    available_sdks: [],
  }
}

function withCredentialProviders(
  current: CredentialsState,
  providers: CredentialsState["providers"],
): CredentialsState {
  return { ...current, providers }
}

export function officialProviderTestSummary(models: ModelInfo[]): {
  kind: "success"
  message: string
} {
  const verifiedCount = models.filter((model) => (
    model.status === "verified" || model.status === "probe-verified"
  )).length
  const notVerifiedCount = Math.max(0, models.length - verifiedCount)
  if (verifiedCount === 0) {
    return {
      kind: "success",
      message: "Catalog loaded. Route candidates are listed.",
    }
  }
  const verifiedLabel = verifiedCount === 1 ? "1 already verified" : `${verifiedCount} already verified`
  const notVerifiedLabel = notVerifiedCount === 1
    ? "1 not generation-probe verified"
    : `${notVerifiedCount} not generation-probe verified`
  return {
    kind: "success",
    message: notVerifiedCount > 0
      ? `Catalog loaded (${verifiedLabel}, ${notVerifiedLabel})`
      : `Catalog loaded (${verifiedLabel})`,
  }
}

export function upsertProviderTestResponse(
  current: CredentialsState,
  latestDraft: ProviderDraft,
  response: ProviderTestResponse,
): CredentialsState {
  const fingerprint = providerTestParamsFingerprint(latestDraft)
  const responseModels = response.available_models ?? []
  const responseSdks = response.available_sdks ?? []
  const nextProvider: CredentialsState["providers"][number] = {
    id: latestDraft.id,
    name: latestDraft.name,
    api_key: latestDraft.api_key,
    base_url: latestDraft.base_url,
    provider_type: latestDraft.provider_type,
    last_test_status: response.status === "missing_api_key" ? "untested" : response.status,
    last_test_at: new Date().toISOString(),
    last_test_message: response.message ?? "",
    last_error_code: response.error_code ?? "",
    available_models: responseModels,
    available_sdks: responseSdks,
  }
  const lastTestStatus = nextProvider.last_test_status ?? "untested"
  let found = false
  const providers: CredentialsState["providers"] = current.providers.map((provider): CredentialsState["providers"][number] => {
    if (provider.id !== latestDraft.id) return provider
    found = true
    const testResult: ProviderTestResult = {
      params_fingerprint: fingerprint,
      base_url: latestDraft.base_url,
      provider_type: latestDraft.provider_type,
      last_test_status: lastTestStatus,
      last_test_at: nextProvider.last_test_at,
      last_test_message: nextProvider.last_test_message,
      last_error_code: nextProvider.last_error_code,
      available_models: responseModels,
      available_sdks: responseSdks,
    }
    const testResults = [
      ...(provider.test_results ?? []).filter((item) => item.params_fingerprint !== testResult.params_fingerprint),
      testResult,
    ]
    return {
      ...provider,
      ...nextProvider,
      available_models: responseModels,
      available_sdks: responseSdks,
      test_results: testResults,
    }
  })
  const fallbackTestResult: ProviderTestResult = {
    params_fingerprint: fingerprint,
    base_url: latestDraft.base_url,
    provider_type: latestDraft.provider_type,
    last_test_status: lastTestStatus,
    last_test_at: nextProvider.last_test_at,
    last_test_message: nextProvider.last_test_message,
    last_error_code: nextProvider.last_error_code,
    available_models: nextProvider.available_models,
    available_sdks: nextProvider.available_sdks,
  }
  return withCredentialProviders(
    current,
    found ? providers : [...providers, { ...nextProvider, test_results: [fallbackTestResult] }],
  )
}

export function upsertProviderModelsListResponse(
  current: CredentialsState,
  latestDraft: ProviderDraft,
  response: ProviderTestResponse,
): CredentialsState {
  const models = response.available_models ?? []
  const sdks = response.available_sdks ?? []
  const lastTestAt = new Date().toISOString()
  const testResult: ProviderTestResult = {
    params_fingerprint: providerTestParamsFingerprint(latestDraft),
    base_url: latestDraft.base_url,
    provider_type: latestDraft.provider_type,
    last_test_status: "untested",
    last_test_at: lastTestAt,
    last_test_message: response.message ?? "",
    last_error_code: response.error_code ?? "",
    available_models: models,
    available_sdks: sdks,
  }
  let found = false
  const providers: CredentialsState["providers"] = current.providers.map((provider): CredentialsState["providers"][number] => {
    if (provider.id !== latestDraft.id) return provider
    found = true
    const lastTestStatus: CredentialsState["providers"][number]["last_test_status"] = provider.last_test_status === "ok" ? "ok" : "untested"
    const visibleModels = mergeModelInfos(provider.available_models, models)
    const visibleSdks = mergeStrings(provider.available_sdks, sdks)
    const testResults = [
      ...(provider.test_results ?? []).filter((item) => item.params_fingerprint !== testResult.params_fingerprint),
      {
        ...testResult,
        available_models: visibleModels,
        available_sdks: visibleSdks,
      },
    ]
    return {
      ...provider,
      id: latestDraft.id,
      name: latestDraft.name,
      api_key: latestDraft.api_key,
      base_url: latestDraft.base_url,
      provider_type: latestDraft.provider_type,
      last_test_status: lastTestStatus,
      last_test_at: provider.last_test_status === "ok" ? provider.last_test_at : lastTestAt,
      last_test_message: provider.last_test_status === "ok" ? provider.last_test_message : response.message ?? "",
      last_error_code: provider.last_test_status === "ok" ? provider.last_error_code : response.error_code ?? "",
      available_models: visibleModels,
      available_sdks: visibleSdks,
      test_results: testResults,
    }
  })
  if (found) return withCredentialProviders(current, providers)
  const nextProvider: CredentialsState["providers"][number] = {
    id: latestDraft.id,
    name: latestDraft.name,
    api_key: latestDraft.api_key,
    base_url: latestDraft.base_url,
    provider_type: latestDraft.provider_type,
    last_test_status: "untested",
    last_test_at: lastTestAt,
    last_test_message: response.message ?? "",
    last_error_code: response.error_code ?? "",
    available_models: models,
    available_sdks: sdks,
    test_results: [testResult],
  }
  return withCredentialProviders(current, [...providers, nextProvider])
}

export function upsertProviderModels(
  current: CredentialsState,
  draft: ProviderDraft | null,
  providerId: string,
  models: ModelInfo[],
): CredentialsState {
  let found = false
  const providers = current.providers.map((provider) => {
    if (provider.id !== providerId) return provider
    found = true
    return { ...provider, available_models: models }
  })
  if (found || !draft) return withCredentialProviders(current, providers)
  return withCredentialProviders(
    current,
    [
      ...providers,
      {
        id: draft.id,
        name: draft.name,
        api_key: draft.api_key,
        base_url: draft.base_url,
        provider_type: draft.provider_type,
        last_test_status: "ok",
        available_models: models,
        available_sdks: [draft.provider_type],
      },
    ],
  )
}

export function useSettingsPageController(): SettingsPageController {
  const appSettings = useAppSettings()
  const apiReady = useAuthenticatedApiReady()
  const [credentials, setCredentials] = useState<CredentialsState>(emptyCredentials)
  const [credentialsLoading, setCredentialsLoading] = useState(true)
  const [credentialsError, setCredentialsError] = useState<string | null>(null)
  const [drafts, setDrafts] = useState<ProviderDraft[]>([])
  const [pendingAddProviderDraft, setPendingAddProviderDraft] = useState<ProviderDraft | null>(null)
  const [providerTestingActions, setProviderTestingActions] = useState<Record<string, ProviderDraft["testingAction"]>>({})
  // Item 2 follow-up: which endpoint id is currently being tested. The full
  // card Test updates this per endpoint as the loop advances, so progress never
  // falls back to "everything under the provider is spinning".
  const [providerTestingEndpointIds, setProviderTestingEndpointIds] = useState<Record<string, string | null>>({})
  const [rolesData, setRolesData] = useState<RolesData | null>(null)
  const [modelGroups, setModelGroups] = useState<ModelGroup[]>(emptyModelGroups)
  const [rolesError, setRolesError] = useState<string | null>(null)

  // Keep a ref of the most recent draft list so the debounced save can read it
  // at fire time (avoids re-binding the timer on every keystroke).
  const draftsRef = useRef<ProviderDraft[]>(drafts)
  draftsRef.current = drafts
  const credentialsRef = useRef<CredentialsState>(credentials)
  credentialsRef.current = credentials
  const rolesDataRef = useRef<RolesData | null>(rolesData)
  rolesDataRef.current = rolesData
  const invalidatedTestOutcomeIdsRef = useRef<Set<string>>(new Set())
  const dirtyProviderIdsRef = useRef<Set<string>>(new Set())
  const deletedProviderIdsRef = useRef<Set<string>>(new Set())
  const controllerMountedRef = useRef(true)
  const credentialsHydratedRef = useRef(false)
  const credentialsHydratingRef = useRef(false)
  const pendingRoleProjectionRefreshRef = useRef(false)
  // #6: a roles_changed event arrived while the Roles/Copilot tab had never been
  // opened (rolesData still null). Instead of dropping it, set this flag so the
  // lazy load refetches fresh the first time the tab opens.
  const rolesDirtyRef = useRef(false)
  const remoteModelCatalogSyncedRef = useRef(false)
  const pendingAddProviderId = pendingAddProviderDraft?.id ?? null
  const visibleDrafts = useMemo(() => {
    const displayDrafts = pendingAddProviderDraft ? [...drafts, pendingAddProviderDraft] : drafts
    return displayDrafts.map((draft) => {
      const testingAction = providerTestingActions[draft.id] ?? null
      return testingAction
        ? {
          ...draft,
          isTesting: true,
          testingAction,
          testingEndpointId: providerTestingEndpointIds[draft.id] ?? null,
        }
        : { ...draft, isTesting: false, testingAction: null, testingEndpointId: null }
    })
  }, [drafts, pendingAddProviderDraft, providerTestingActions, providerTestingEndpointIds])

  useEffect(() => {
    return () => {
      controllerMountedRef.current = false
    }
  }, [])

  const handleSaved = useCallback((next: CredentialsState) => {
    const nextCredentials: CredentialsState = {
      providers: next.providers.map((provider) => {
        if (!invalidatedTestOutcomeIdsRef.current.has(provider.id)) return provider
        const draft = draftsRef.current.find((item) => item.id === provider.id)
        const cached = draft ? providerCachedTestResult(provider, draft) : null
        if (cached) {
          invalidatedTestOutcomeIdsRef.current.delete(provider.id)
          return {
            ...provider,
            last_test_status: cached.last_test_status,
            last_test_at: cached.last_test_at ?? "",
            last_test_message: cached.last_test_message ?? "",
            last_error_code: cached.last_error_code ?? "",
            available_models: cached.available_models ?? [],
            available_sdks: cached.available_sdks ?? [],
          }
        }
        return resetProviderTestOutcome(provider)
      }),
      probe_catalog: next.probe_catalog ?? null,
    }
    setCredentials(nextCredentials)
    setDrafts((current) => reconcileDraftsWithCredentials(nextCredentials, current, dirtyProviderIdsRef.current, deletedProviderIdsRef.current))
    if (pendingRoleProjectionRefreshRef.current) {
      pendingRoleProjectionRefreshRef.current = false
      void refreshLoadedLlmRolesProjection({
        rolesLoaded: Boolean(rolesDataRef.current),
        setModelGroups,
        setRolesData,
        setRolesError,
      })
    }
  }, [])

  const { flush: flushCredentialsSave, queue: queueSave, status: saveStatus } = useDebouncedCredentialsSave({
    onSaved: handleSaved,
  })
  const { cancel: cancelRolesSave, flush: flushRolesSave, queue: queueRolesSave, status: rolesSaveStatus } = useDebouncedRolesSave({
    isRecoverableError: isStaleRouteReferenceError,
    onRecoverableError: () => {
      void refreshLoadedLlmRolesProjection({
        rolesLoaded: Boolean(rolesDataRef.current),
        setModelGroups,
        setRolesData,
        setRolesError,
      })
    },
    onSaved: (next) => {
      setRolesData(next)
      setRolesError(null)
    },
    onError: (error) => {
      setRolesError(composeRequestErrorMessage(error, "Save failed"))
    },
  })
  const rolesSaveStatusRef = useRef(rolesSaveStatus)
  rolesSaveStatusRef.current = rolesSaveStatus

  useEffect(() => {
    if (!apiReady) return undefined
    const handleFocus = () => {
      getCredentials({ hydrateSecrets: credentialsHydratedRef.current })
        .then((next) => {
          setCredentials(next)
          setDrafts((current) => reconcileDraftsWithCredentials(next, current, dirtyProviderIdsRef.current, deletedProviderIdsRef.current))
        })
        .catch(() => {})

      if (rolesDataRef.current) {
        Promise.all([getRoles(), getModelGroups()])
          .then(([next, nextModelGroups]) => {
            setRolesData(next)
            setModelGroups(nextModelGroups)
          })
          .catch(() => {})
      }
    }
    window.addEventListener("focus", handleFocus)
    return () => {
      window.removeEventListener("focus", handleFocus)
    }
  }, [apiReady])

  // R-F19.2 — when the Tauri shell intercepts `WindowEvent::CloseRequested`
  // (Cmd+Q / window close / Quit menu) it emits `before-quit` and blocks the
  // shutdown for `QUIT_FLUSH_BUDGET` (1500ms) waiting for the FE to ack via
  // `confirm_quit_ready`. We flush any debounced/in-flight roles save first,
  // then ack — so a yaml edit that was still sitting in the 300ms debounce
  // window doesn't get lost on Quit. Browser-mode (no Tauri) gracefully
  // no-ops: the dynamic import resolves but `listen` never fires.
  useEffect(() => {
    let cancelled = false
    let unlisten: (() => void) | null = null
    void (async () => {
      try {
        const [{ listen }, { invoke }] = await Promise.all([
          import("@tauri-apps/api/event"),
          import("@tauri-apps/api/core"),
        ])
        if (cancelled) return
        unlisten = await listen("before-quit", async () => {
          try {
            await flushRolesSave()
          } catch (error) {
            // Surfacing via warn so silent loss is observable
            // (rules/logging.md). We still ack so the shell isn't blocked
            // for the full budget; the unmount cleanup helper also takes a
            // best-effort pass if anything is still buffered.
            console.warn(
              "phase=quit action=flush-before-quit-failed reason=%o",
              error,
            )
          }
          try {
            await invoke("confirm_quit_ready")
          } catch (error) {
            console.warn(
              "phase=quit action=confirm-quit-ready-invoke-failed reason=%o",
              error,
            )
          }
        })
      } catch (error) {
        // Not running under Tauri (e.g. dev browser tab). Quietly skip —
        // this is expected and not a degradation.
        if (import.meta.env.DEV) {
          console.info(
            "phase=quit action=before-quit-listener-unavailable reason=%o",
            error,
          )
        }
      }
    })()
    return () => {
      cancelled = true
      if (unlisten) unlisten()
    }
  }, [flushRolesSave])

  // #5/#6 WebSocket auto-refresh, extracted into useStudioEventStream (resilient
  // reconnect + observable logging). registry_changed re-pulls credentials;
  // roles_changed re-pulls roles+model-groups when loaded, else marks them dirty
  // so the next Roles/Copilot tab open refetches (the event is no longer
  // silently dropped). onResync runs on every (re)connect to backfill any gap.
  const refetchCredentialsFromEvent = useCallback(() => {
    getCredentials({ hydrateSecrets: credentialsHydratedRef.current })
      .then((next) => {
        setCredentials(next)
        setDrafts((current) => reconcileDraftsWithCredentials(next, current, dirtyProviderIdsRef.current, deletedProviderIdsRef.current))
      })
      .catch((error) => {
        console.warn("phase=settings-event-refresh action=credentials-refetch-failed error=%o", error)
      })
  }, [])

  const refetchRolesFromEvent = useCallback(() => {
    if (!shouldApplyExternalRolesRefresh(rolesSaveStatusRef.current)) {
      rolesDirtyRef.current = true
      return
    }
    Promise.all([getRoles(), getModelGroups()])
      .then(([next, nextModelGroups]) => {
        setRolesData(next)
        setModelGroups(nextModelGroups)
      })
      .catch((error) => {
        console.warn("phase=settings-event-refresh action=roles-refetch-failed error=%o", error)
      })
  }, [])

  const handleRolesChangedEvent = useCallback(() => {
    if (rolesDataRef.current) {
      refetchRolesFromEvent()
      return
    }
    // Roles tab not opened yet: mark dirty so the lazy
    // load refetches fresh when the user first opens Roles/Copilot.
    console.info("phase=settings-event-refresh action=roles-marked-dirty reason=roles-not-loaded")
    rolesDirtyRef.current = true
  }, [refetchRolesFromEvent])

  const handleLlmProbeActiveEvent = useCallback((event: { endpointId: string; activeModelIds: string[] }) => {
    updateActiveProbeEndpoint(event.endpointId, event.activeModelIds)
  }, [])

  const handleEventResync = useCallback(() => {
    refetchCredentialsFromEvent()
    if (rolesDataRef.current) refetchRolesFromEvent()
  }, [refetchCredentialsFromEvent, refetchRolesFromEvent])

  const { connectionLost } = useStudioEventStream({
    onRegistryChanged: refetchCredentialsFromEvent,
    onRolesChanged: handleRolesChangedEvent,
    onLlmProbeActive: handleLlmProbeActiveEvent,
    onResync: handleEventResync,
  }, { enabled: apiReady })

  // A mutating settings action (delete / test / add) must never fire into an
  // unreachable backend: the request gets no response and surfaces a bare
  // "Backend unavailable" toast, and an optimistic delete removes the card
  // before silently reverting. Gate every mutation on LIVE reachability:
  // config resolved (apiReady) AND the event stream connected (!connectionLost).
  // When not reachable the action is refused with a clear "reconnecting"
  // message and the UI disables the buttons (see `backendReachable` in the
  // returned controller).
  const backendReachable = apiReady && !connectionLost
  function ensureBackendReachable(): boolean {
    if (backendReachable) return true
    toast.error("Backend is reconnecting — please try again in a moment.")
    return false
  }

  useEffect(() => {
    if (!apiReady) return
    const enabled = appSettings.settings.remote_model_catalog_enabled
    if (!enabled) {
      remoteModelCatalogSyncedRef.current = false
      return
    }
    if (!shouldSyncRemoteModelCatalog({
      settingsLoading: appSettings.isLoading,
      enabled,
      alreadySynced: remoteModelCatalogSyncedRef.current,
    })) {
      return
    }
    remoteModelCatalogSyncedRef.current = true
    syncVerifiedCommunityCatalog()
      .then(() => {
        refetchCredentialsFromEvent()
      })
      .catch((error) => {
        console.warn("phase=settings-catalog action=verified-community-catalog-sync-failed error=%o", error)
      })
  }, [
    apiReady,
    appSettings.isLoading,
    appSettings.settings.remote_model_catalog_enabled,
    refetchCredentialsFromEvent,
  ])

  useEffect(() => {
    if (!apiReady) return
    let cancelled = false
    credentialsHydratingRef.current = true
    getCredentials()
      .then((next) => {
        if (cancelled) return
        credentialsHydratedRef.current = true
        invalidatedTestOutcomeIdsRef.current.clear()
        setCredentialsError(null)
        setCredentials(next)
        setDrafts((current) => reconcileDraftsWithCredentials(next, current, dirtyProviderIdsRef.current, deletedProviderIdsRef.current))
        setCredentialsLoading(false)
      })
      .catch((error) => {
        if (cancelled) return
        const message = error instanceof Error ? error.message : "Load failed"
        setCredentialsError(message)
        toast.error(`API Keys load failed: ${message}`)
        setCredentialsLoading(false)
      })
      .finally(() => {
        credentialsHydratingRef.current = false
      })
    return () => {
      cancelled = true
    }
  }, [apiReady])

  const ensureCredentialsHydrated = useCallback(() => {
    if (!apiReady) return
    if (credentialsHydratedRef.current || credentialsHydratingRef.current) return
    credentialsHydratingRef.current = true
    getCredentials()
      .then((next) => {
        if (!controllerMountedRef.current) return
        credentialsHydratedRef.current = true
        invalidatedTestOutcomeIdsRef.current.clear()
        setCredentialsError(null)
        setCredentials(next)
        setDrafts((current) => reconcileDraftsWithCredentials(next, current, dirtyProviderIdsRef.current, deletedProviderIdsRef.current))
        setCredentialsLoading(false)
      })
      .catch((error) => {
        if (!controllerMountedRef.current) return
        const message = error instanceof Error ? error.message : "Load failed"
        setCredentialsError(message)
        toast.error(`API Keys load failed: ${message}`)
        setCredentialsLoading(false)
      })
      .finally(() => {
        credentialsHydratingRef.current = false
      })
  }, [apiReady])

  useEffect(() => {
    if (!apiReady) return
    if (rolesData) return
    let cancelled = false
    // #6: clear any pending roles-dirty flag — this lazy load IS the refetch the
    // dropped roles_changed event was waiting for.
    if (rolesDirtyRef.current) {
      console.info("phase=settings-event-refresh action=roles-dirty-consumed reason=tab-open")
      rolesDirtyRef.current = false
    }
    Promise.all([getRoles(), getModelGroups()])
      .then(([next, nextModelGroups]) => {
        if (cancelled) return
        setRolesData(next)
        setModelGroups(nextModelGroups)
      })
      .catch(() => {
        if (!cancelled) setRolesError("Roles unavailable")
      })
    return () => {
      cancelled = true
    }
  }, [apiReady, rolesData])

  useEffect(() => {
    if (!apiReady) return
    if (!rolesData) return
    if (!modelGroupsReferenceMissingCredentialProviders(modelGroups, credentials)) return
    void refreshLoadedLlmRolesProjection({
      rolesLoaded: true,
      setModelGroups,
      setRolesData,
      setRolesError,
    })
  }, [apiReady, credentials, modelGroups, rolesData])

  function scheduleSave() {
    queueSave(() => buildPutPayload(draftsRef.current))
  }

  function updateProviderField(
    providerId: string,
    patch: Partial<ProviderDraft>,
    options?: ProviderDraftChangeOptions,
  ) {
    dirtyProviderIdsRef.current.add(providerId)
    const currentDraft = draftsRef.current.find((draft) => draft.id === providerId)
    const nextDraft = currentDraft ? { ...currentDraft, ...patch } : null
    if (currentDraft && nextDraft && !providerTestParamsMatch(currentDraft, nextDraft)) {
      const persisted = credentialsRef.current.providers.find((provider) => provider.id === providerId)
      if (persisted && providerTestParamsMatch(nextDraft, persisted)) {
        invalidatedTestOutcomeIdsRef.current.delete(providerId)
      } else {
        invalidatedTestOutcomeIdsRef.current.add(providerId)
      }
    }
    setDrafts((current) => {
      const found = current.some((draft) => draft.id === providerId)
      if (found) {
        return current.map((draft) => (
          draft.id === providerId ? { ...draft, ...patch } : draft
        ))
      }
      return [
        ...current,
        {
          id: providerId,
          name: patch.name ?? providerId,
          provider_type: patch.provider_type ?? "openai_compatible",
          base_url: patch.base_url ?? "",
          api_key: patch.api_key ?? "",
          isTesting: patch.isTesting ?? false,
          testingAction: patch.testingAction ?? null,
        },
      ]
    })
    if (options?.save !== false) {
      scheduleSave()
    }
  }

  function setProviderTesting(
    providerId: string,
    testingAction: ProviderDraft["testingAction"],
    testingEndpointId: string | null = null,
  ) {
    if (!testingAction) {
      const owner = providerDraftForAction(draftsRef.current, providerId)
      const endpointIds = owner ? providerEndpointDraftsForAction(owner).map((endpointDraft) => endpointDraft.id) : [providerId]
      clearActiveProbeEndpoints(endpointIds)
    }
    setProviderTestingActions((current) => {
      if (!testingAction) {
        const next = { ...current }
        delete next[providerId]
        return next
      }
      return { ...current, [providerId]: testingAction }
    })
    setProviderTestingEndpointIds((current) => {
      if (!testingAction || !testingEndpointId) {
        const next = { ...current }
        delete next[providerId]
        return next
      }
      return { ...current, [providerId]: testingEndpointId }
    })
  }

  function addProviderWithData(data: AddProviderFormSubmission) {
    if (!ensureBackendReachable()) return
    const draft = draftFromAddProviderSubmission(data, pendingAddProviderDraft?.id)
    setPendingAddProviderDraft(null)
    dirtyProviderIdsRef.current.add(draft.id)
    setDrafts((current) => {
      const next = [...current, draft]
      queueSave(() => buildPutPayload(next))
      return next
    })
  }

  function beginAddProvider() {
    setPendingAddProviderDraft((current) => current ?? blankThirdPartyProviderDraft())
  }

  function cancelAddProvider() {
    setPendingAddProviderDraft(null)
  }

  function deleteProvider(providerId: string) {
    if (!ensureBackendReachable()) return
    const draft = providerDraftForAction(draftsRef.current, providerId)
    const endpointIds = draft
      ? providerEndpointDraftsForAction(draft).map((endpointDraft) => endpointDraft.id)
      : [providerId]
    pendingRoleProjectionRefreshRef.current = true
    dirtyProviderIdsRef.current.delete(providerId)
    deletedProviderIdsRef.current.add(providerId)
    setDrafts((current) => current.filter((draft) => draft.id !== providerId))
    void deleteProviderEndpoints(endpointIds)
  }

  async function deleteProviderEndpoints(endpointIds: string[]) {
    if (!ensureBackendReachable()) return
    const uniqueEndpointIds = Array.from(new Set(endpointIds.filter(Boolean)))
    if (uniqueEndpointIds.length === 0) return
    pendingRoleProjectionRefreshRef.current = true
    try {
      for (const endpointId of uniqueEndpointIds) {
        await deleteEndpoint(endpointId)
      }
      const next = await getCredentials({ hydrateSecrets: credentialsHydratedRef.current })
      setCredentials(next)
      setDrafts((current) => reconcileDraftsWithCredentials(next, current, dirtyProviderIdsRef.current, deletedProviderIdsRef.current))
    } catch (error) {
      toast.error(composeRequestErrorMessage(error, "Base URL delete failed"))
    }
  }

  function updateProviderModels(providerId: string, models: ModelInfo[]) {
    setCredentials((current) => (
      upsertProviderModels(
        current,
        providerDraftForAction(draftsRef.current, providerId),
        providerId,
        models,
      )
    ))
  }

  // Design protocol matrix point 4: re-probe one (URL, protocol) cell NOW,
  // bypassing the protocol_unsupported half-life gate. This is the affordance for
  // "the provider may have started supporting this protocol today".
  async function forceReprobeEndpoint(endpointId: string) {
    if (!ensureBackendReachable()) return
    pendingRoleProjectionRefreshRef.current = true
    const toastId = `force-endpoint-test-${endpointId}`
    toast.loading(`Re-probing protocol for ${endpointId}...`, { id: toastId })
    try {
      // The response already carries the freshly-updated registry — merge it
      // locally like runProviderGetModels does, instead of a second network
      // round trip that re-fetches and re-decrypts every provider's secret
      // (that redundant getCredentials call was why this hung far longer than
      // a single endpoint-tag probe).
      const next = await forceTestEndpoint(endpointId)
      setCredentials(next)
      setDrafts((current) => reconcileDraftsWithCredentials(next, current, dirtyProviderIdsRef.current, deletedProviderIdsRef.current))
      const reprobed = next.providers.find((provider) => provider.id === endpointId)
      if (reprobed?.last_error_code === 'protocol_unsupported') {
        toast.info(`Still unsupported: ${reprobed.last_test_message ?? 'the URL does not speak this protocol.'}`, { id: toastId })
      } else {
        toast.success(`Re-probed ${endpointId}: ${reprobed?.last_test_message ?? 'done.'}`, { id: toastId })
      }
    } catch (error) {
      toast.error(composeRequestErrorMessage(error, "Endpoint re-probe failed"), { id: toastId })
    }
  }

  // P2: remove a model from a provider by deleting every route it covers (a chip
  // can span endpoints). The backend refuses (409) when a role still uses the
  // route, so a referenced model is kept and the user is told why. Merges the
  // refreshed credentials locally like the other single-route mutations.
  async function removeModelRoutes(modelId: string, routeIds: string[]) {
    if (!ensureBackendReachable()) return
    if (routeIds.length === 0) return
    pendingRoleProjectionRefreshRef.current = true
    const toastId = `remove-model-${modelId}`
    toast.loading(i18n.t("settings:apiKeys.card.removeModelLoading", { modelId }), { id: toastId })
    try {
      let next: CredentialsState | null = null
      for (const routeId of routeIds) {
        next = await deleteRoute(routeId)
      }
      if (next) {
        const merged = next
        setCredentials(merged)
        setDrafts((current) => reconcileDraftsWithCredentials(merged, current, dirtyProviderIdsRef.current, deletedProviderIdsRef.current))
      }
      toast.success(i18n.t("settings:apiKeys.card.removeModelSuccess", { modelId }), { id: toastId })
    } catch (error) {
      const inUse = (error as { response?: { status?: number } })?.response?.status === 409
      const fallback = inUse
        ? i18n.t("settings:apiKeys.card.removeModelInUse", { modelId })
        : i18n.t("settings:apiKeys.card.removeModelFailed", { modelId })
      toast.error(composeRequestErrorMessage(error, fallback), { id: toastId })
    }
  }

  async function runProviderGetModels(providerId: string, options: { onlyEndpointId?: string } = {}) {
    if (!ensureBackendReachable()) return
    await flushCredentialsSave()
    const draft = providerDraftForAction(draftsRef.current, providerId)
    if (!draft) return
    const isOfficial = inferProviderKind(draft) === "official"
    const allEndpointDrafts = providerEndpointDraftsForAction(draft)
    // Item 2: clicking one endpoint tag runs THIS SAME card-Test flow, only
    // scoped to the one clicked (URL, protocol) endpoint, so the get-models
    // probe and its per-step toast are identical to pressing Test, not a
    // separate lighter path with its own toast.
    const requestedEndpointDrafts = options.onlyEndpointId
      ? allEndpointDrafts.filter((endpointDraft) => endpointDraft.id === options.onlyEndpointId)
      : allEndpointDrafts
    const persistedByEndpointId = new Map(credentialsRef.current.providers.map((provider) => [provider.id, provider]))
    const endpointDrafts = requestedEndpointDrafts.filter((endpointDraft) => (
      routineEndpointTestShouldQueue(endpointDraft, persistedByEndpointId.get(endpointDraft.id))
    ))
    if (endpointDrafts.length === 0) return
    const baseUrlSteps = isOfficial ? [] : providerBaseUrlStepsForEndpointDrafts(endpointDrafts)
    const baseUrlStepByKey = new Map(baseUrlSteps.map((step, index) => [step.key, { ...step, index }]))
    const totalProgressSteps = endpointDrafts.length + baseUrlSteps.length
    const announcedBaseUrlSteps = new Set<string>()
    const reportedBaseUrlSteps = new Set<string>()

    setProviderTesting(providerId, "models", endpointDrafts[0]?.id ?? options.onlyEndpointId ?? null)
    const toastId = `get-models-${providerId}`
    toast.loading(
      isOfficial
        ? `Checking ${draft.name || "provider"} endpoint and loading route candidates...`
        : `Getting models for ${draft.name || "provider"}...`,
      { id: toastId },
    )

    try {
      // apikeys#24/#25: official and third-party share the same endpoint test
      // authority. A third-party provider test is a single UI transaction over
      // every base-url/protocol endpoint, so local rows and toast settle together.
      const endpointResults: Array<{
        endpointDraft: ProviderDraft
        response: ProviderTestResponse
      }> = []
      for (let index = 0; index < endpointDrafts.length; index += 1) {
        const endpointDraft = endpointDrafts[index]
        if (!endpointDraft) continue
        setProviderTesting(providerId, "models", endpointDraft.id)
        const baseUrlKey = comparableProviderBaseUrl(endpointDraft.base_url)
        const baseUrlStep = baseUrlStepByKey.get(baseUrlKey)
        if (baseUrlStep && !announcedBaseUrlSteps.has(baseUrlKey)) {
          announcedBaseUrlSteps.add(baseUrlKey)
          toast.loading(
            `${providerBaseUrlProgressLabel(baseUrlStep, baseUrlSteps.length, totalProgressSteps)}: loading model list with the current API key...`,
            { id: toastId },
          )
        }
        const stepLabel = isOfficial
          ? providerEndpointStepLabel(endpointDraft, index, endpointDrafts.length)
          : providerEndpointProgressLabel(endpointDraft, index, endpointDrafts.length, baseUrlSteps.length, totalProgressSteps)
        toast.loading(`${stepLabel}: probing generation endpoint...`, { id: toastId })
        try {
          endpointResults.push({
            endpointDraft,
            response: await getProviderModels({
              id: endpointDraft.id,
              name: endpointDraft.name,
              provider_type: endpointDraft.provider_type,
              api_key: endpointDraft.api_key.trim(),
              base_url: endpointDraft.base_url || undefined,
            }),
          })
        } catch (error) {
          endpointResults.push({
            endpointDraft,
            response: providerTestResponseFromRequestFailure(error),
          })
        }
        const latestResult = endpointResults[endpointResults.length - 1]
        const resultSummary = latestResult ? providerEndpointResultSummary(latestResult.response) : "request failed"
        if (baseUrlStep && latestResult && !reportedBaseUrlSteps.has(baseUrlKey)) {
          reportedBaseUrlSteps.add(baseUrlKey)
          toast.loading(
            `${providerBaseUrlProgressLabel(baseUrlStep, baseUrlSteps.length, totalProgressSteps)}: ${providerModelListStepSummary(latestResult.response)}.`,
            { id: toastId },
          )
        }
        if (index < endpointDrafts.length - 1) {
          toast.loading(`${stepLabel}: ${resultSummary}. Next step...`, { id: toastId })
        }
      }
      const latestDraft = providerDraftForAction(draftsRef.current, providerId)
      if (!latestDraft) {
        toast.info("Test result ignored because provider configuration changed.", { id: toastId })
        return
      }
      const latestEndpointDrafts = providerEndpointDraftsForAction(latestDraft)
      const staleResult = endpointResults.some(({ endpointDraft }) => {
        const latestEndpointDraft = latestEndpointDrafts.find((item) => item.id === endpointDraft.id)
        return !latestEndpointDraft || !providerEndpointIdentityMatches(latestEndpointDraft, endpointDraft)
      })
      if (staleResult) {
        toast.info("Test result ignored because provider configuration changed.", { id: toastId })
        return
      }

      if (endpointResults.length > 0) {
        for (const { endpointDraft } of endpointResults) {
          invalidatedTestOutcomeIdsRef.current.delete(providerId)
          invalidatedTestOutcomeIdsRef.current.delete(endpointDraft.id)
        }
        setCredentials((current) => (
          endpointResults.reduce((nextCredentials, { endpointDraft, response }) => {
            const latestEndpointDraft = latestEndpointDrafts.find((item) => item.id === endpointDraft.id) ?? endpointDraft
            return upsertProviderTestResponse(nextCredentials, latestEndpointDraft, response)
          }, current)
        ))
      }

      const responses = endpointResults.map((result) => result.response)
      const okResponses = responses.filter((response) => response.status === "ok")
      if (okResponses.length > 0) {
        const models = okResponses.flatMap((response) => response.available_models ?? [])
        const modelCount = models.length
        if (isOfficial) {
          const summary = officialProviderTestSummary(okResponses[0]?.available_models ?? [])
          toast[summary.kind](summary.message, { id: toastId })
        } else if (okResponses.length < endpointDrafts.length) {
          const notReadyCount = endpointDrafts.length - okResponses.length
          toast.warning(`Models listed on ${okResponses.length}/${endpointDrafts.length} endpoints (${modelCount} models); ${notReadyCount} not ready.`, { id: toastId })
        } else if (modelCount > 0) {
          toast.success(
            responses.length > 1
              ? `Models listed on ${responses.length} endpoints (${modelCount} models).`
              : `Models listed (${modelCount} models)`,
            { id: toastId },
          )
        } else {
          toast.warning("Model-list endpoint is reachable, but no models were returned.", { id: toastId })
        }
      } else {
        toast.error(
          providerEndpointFailureSummary(endpointResults, baseUrlSteps.length),
          { id: toastId },
        )
      }
    } catch (error) {
      toast.error(composeRequestErrorMessage(error, "Provider test failed"), { id: toastId })
    } finally {
      setProviderTesting(providerId, null)
    }
  }

  const updateRolesData = useCallback((next: RolesData) => {
    const normalized = normalizeRolesDraft(next)
    rolesDataRef.current = normalized
    setRolesData(normalized)
    const validationError = validateRolesDraft(normalized)
    if (validationError) {
      setRolesError(validationError)
      cancelRolesSave()
      return
    }
    setRolesError(null)
    queueRolesSave(() => normalized)
  }, [cancelRolesSave, queueRolesSave])

  const deleteRoleByName = useCallback(async (roleName: string) => {
    await flushRolesSave()
    cancelRolesSave()
    try {
      const next = await deleteRole(roleName)
      rolesDataRef.current = next
      setRolesData(next)
      setRolesError(null)
    } catch (error) {
      const message = composeRequestErrorMessage(error, "Delete failed")
      setRolesError(message)
      toast.error(`LLM Role delete failed: ${message}`)
    }
  }, [cancelRolesSave, flushRolesSave])

  const deleteModelBundleById = useCallback(async (bundleId: string) => {
    await flushRolesSave()
    cancelRolesSave()
    try {
      const next = await deleteModelBundle(bundleId)
      rolesDataRef.current = next
      setRolesData(next)
      setRolesError(null)
    } catch (error) {
      const message = composeRequestErrorMessage(error, "Delete failed")
      setRolesError(message)
      toast.error(`Model Bundle delete failed: ${message}`)
    }
  }, [cancelRolesSave, flushRolesSave])

  const refreshRolesProjection = useCallback(async () => {
    await refreshLoadedLlmRolesProjection({
      rolesLoaded: Boolean(rolesDataRef.current),
      setModelGroups,
      setRolesData,
      setRolesError,
    })
  }, [])

  return {
    credentials,
    credentialsLoading,
    credentialsError,
    drafts: visibleDrafts,
    pendingAddProviderId,
    saveStatus,
    rolesData,
    modelGroups,
    rolesSaveStatus,
    rolesError,
    appSettings: {
      userId: appSettings.settings.user_id,
      giteaHost: appSettings.settings.gitea_host,
      defaultSkillsDirectory: appSettings.settings.default_skills_directory,
      language: appSettings.settings.language,
      remoteModelCatalogEnabled: appSettings.settings.remote_model_catalog_enabled,
      isLoading: appSettings.isLoading,
      saveStatus: appSettings.saveStatus,
      setUserId: appSettings.setUserId,
      setGiteaHost: appSettings.setGiteaHost,
      setDefaultSkillsDirectory: appSettings.setDefaultSkillsDirectory,
      setLanguage: appSettings.setLanguage,
      setRemoteModelCatalogEnabled: appSettings.setRemoteModelCatalogEnabled,
    },
    connectionLost,
    backendReachable,
    ensureCredentialsHydrated,
    onProviderFieldChange: updateProviderField,
    onGetProviderModels: (providerId) => void runProviderGetModels(providerId),
    onProbeEndpoint: (endpointId) => {
      // Item 2: a single endpoint-tag click runs the SAME card-Test flow scoped
      // to just this endpoint (same get-models probe + toast). Guard readiness
      // first so a disconnected backend refuses uniformly (§ backend readiness
      // gate), then route through the owning provider's get-models.
      if (!ensureBackendReachable()) return
      const owner = draftsRef.current.find((candidate) =>
        providerEndpointDraftsForAction(candidate).some((endpointDraft) => endpointDraft.id === endpointId),
      )
      if (owner) void runProviderGetModels(owner.id, { onlyEndpointId: endpointId })
    },
    onForceEndpointTest: (endpointId) => void forceReprobeEndpoint(endpointId),
    onDeleteProvider: deleteProvider,
    onDeleteProviderEndpoints: (endpointIds) => void deleteProviderEndpoints(endpointIds),
    onRemoveModel: (modelId, routeIds) => void removeModelRoutes(modelId, routeIds),
    onBeginAddProvider: beginAddProvider,
    onAddProvider: addProviderWithData,
    onCancelAddProvider: cancelAddProvider,
    onProviderModelsUpdated: updateProviderModels,
    onRolesDataChange: updateRolesData,
    onDeleteRole: deleteRoleByName,
    onDeleteModelBundle: deleteModelBundleById,
    onBeforeRoleTest: flushRolesSave,
    onAfterRoleTest: refreshRolesProjection,
  }
}

export function SettingsPageView({ onClose, initialTab = "general", controller }: SettingsPageViewProps) {
  const [activeTab, setActiveTab] = useState<SettingsTab>(initialTab)
  const { ensureCredentialsHydrated } = controller

  useEffect(() => {
    setActiveTab(initialTab)
  }, [initialTab])

  useEffect(() => {
    if (activeTab === "api_keys") {
      ensureCredentialsHydrated()
    }
  }, [activeTab, ensureCredentialsHydrated])

  return (
    <SettingsPageContent
      {...controller}
      activeTab={activeTab}
      onClose={onClose}
      onTabChange={setActiveTab}
      onNavigateToApiKeys={() => setActiveTab("api_keys")}
    />
  )
}

export function SettingsPage(props: SettingsPageProps) {
  const controller = useSettingsPageController()
  return <SettingsPageView {...props} controller={controller} />
}

function providerEndpointIdentityMatches(left: ProviderDraft, right: ProviderDraft): boolean {
  return (
    left.id === right.id &&
    (left.provider_type ?? null) === (right.provider_type ?? null) &&
    comparableProviderBaseUrl(left.base_url) === comparableProviderBaseUrl(right.base_url)
  )
}

function routineEndpointTestShouldQueue(
  endpointDraft: ProviderDraft,
  persisted: CredentialsState["providers"][number] | undefined,
): boolean {
  if (!persisted) return true
  if (persisted.endpoint_status === "disabled") return false
  if (!providerTestParamsMatch(endpointDraft, persisted)) return true
  const cached = providerCachedTestResult(persisted, endpointDraft)
  const status = cached?.last_test_status ?? persisted.last_test_status
  const errorCode = cached?.last_error_code ?? persisted.last_error_code
  return status !== "protocol_unsupported" && errorCode !== "protocol_unsupported"
}

type ProviderBaseUrlStep = {
  key: string
  baseUrl: string
}

function providerBaseUrlStepsForEndpointDrafts(endpointDrafts: ProviderDraft[]): ProviderBaseUrlStep[] {
  const steps: ProviderBaseUrlStep[] = []
  const seen = new Set<string>()
  for (const endpointDraft of endpointDrafts) {
    const key = comparableProviderBaseUrl(endpointDraft.base_url)
    if (!key || seen.has(key)) continue
    seen.add(key)
    steps.push({ key, baseUrl: endpointDraft.base_url })
  }
  return steps
}

function providerBaseUrlProgressLabel(
  step: ProviderBaseUrlStep & { index: number },
  baseUrlTotal: number,
  progressTotal: number,
): string {
  return `Step ${step.index + 1}/${progressTotal}: Checking base URL ${step.index + 1}/${baseUrlTotal} / ${compactProviderHost(step.baseUrl)}`
}

function providerEndpointStepLabel(
  draft: ProviderDraft,
  index: number,
  total: number,
): string {
  const ordinal = total > 1 ? `${index + 1}/${total} ` : ""
  return `Testing ${ordinal}${providerTypeShortName(draft.provider_type)} / ${compactProviderHost(draft.base_url)}`
}

function providerEndpointProgressLabel(
  draft: ProviderDraft,
  index: number,
  total: number,
  stepOffset: number,
  progressTotal: number,
): string {
  return `Step ${stepOffset + index + 1}/${progressTotal}: ${providerEndpointStepLabel(draft, index, total)}`
}

function providerModelListStepSummary(response: ProviderTestResponse): string {
  const modelCount = response.available_models?.length ?? 0
  if (modelCount > 0) return `model list returned ${modelCount}`
  if (response.status === "missing_api_key") return "model list skipped because the API key is empty"
  return "model list empty or unavailable"
}

function providerEndpointResultSummary(response: ProviderTestResponse): string {
  const modelCount = response.available_models?.length ?? 0
  const modelList = modelCount > 0
    ? `model list returned ${modelCount}`
    : "model list empty or unavailable"
  if (response.status === "ok") return `${modelList}; generation probe passed`
  const reason = composeTestErrorMessage(response.status, response.error_code, response.message)
  return `${modelList}; generation probe failed (${reason})`
}

function providerEndpointFailureSummary(
  endpointResults: Array<{ endpointDraft: ProviderDraft; response: ProviderTestResponse }>,
  baseUrlStepCount = 0,
): string {
  if (endpointResults.length === 0) return "Provider test failed"
  const lines = endpointResults.map(({ endpointDraft, response }, index) => {
    const label = providerEndpointStepLabel(endpointDraft, index, endpointResults.length).replace(/^Testing /, "")
    return `${label}: ${providerEndpointResultSummary(response)}`
  })
  const preview = lines.slice(0, 3).join(" | ")
  const omitted = lines.length > 3 ? ` | ${lines.length - 3} more endpoints tested` : ""
  if (baseUrlStepCount > 0) {
    const baseUrlStepLabel = baseUrlStepCount === 1 ? "base URL model-list step" : "base URL model-list steps"
    return `Checked ${baseUrlStepCount} ${baseUrlStepLabel} and tested ${lines.length} protocol endpoints; none generated successfully. ${preview}${omitted}`
  }
  return `All ${lines.length} endpoints tested; none generated successfully. ${preview}${omitted}`
}

function providerTypeShortName(providerType: ProviderDraft["provider_type"]): string {
  if (providerType === "anthropic_compatible") return "Anth"
  if (providerType === "google_genai") return "Gemini"
  if (providerType === "ark_runtime") return "Ark"
  return "OpenAI"
}

function compactProviderHost(value: string): string {
  const trimmed = value.trim()
  if (!trimmed) return "empty URL"
  try {
    const parsed = new URL(trimmed)
    return parsed.hostname.replace(/^www\./, "")
  } catch {
    return trimmed.replace(/^https?:\/\//, "").replace(/\/.*$/, "")
  }
}

function providerTestResponseFromRequestFailure(error: unknown): ProviderTestResponse {
  return {
    status: "network_error",
    latency_ms: null,
    model_seen: null,
    message: composeRequestErrorMessage(error, "Provider test request failed"),
    error_code: "request_failed",
    available_models: [],
    available_sdks: [],
  }
}

function comparableProviderBaseUrl(value?: string | null): string {
  return (value ?? "").trim().replace(/\/+$/, "").toLowerCase()
}
