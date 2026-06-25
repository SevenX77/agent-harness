import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import { toast } from "sonner"
import { useAppSettings } from "@/hooks/useAppSettings"
import { buildPutPayload, useDebouncedCredentialsSave } from "@/hooks/useDebouncedCredentialsSave"
import { useDebouncedRolesSave } from "@/hooks/useDebouncedRolesSave"
import { composeRequestErrorMessage, composeTestErrorMessage } from "@/lib/llm-error-messages"
import { useStudioEventStream } from "@/hooks/useStudioEventStream"
import { deleteModelBundle, deleteRole, getCredentials, getModelGroups, getProviderModels, getRoles, syncRemoteModelCatalog, type CredentialsState, type ModelGroup, type ModelInfo, type ProviderTestResponse, type ProviderTestResult, type RolesData } from "../../../api/llm"
import type { AddProviderFormSubmission } from "../api-keys"
import { SettingsPageContent } from "./SettingsPageContent"
import { draftsFromCredentials, draftFromAddProviderSubmission, inferProviderKind, providerCachedTestResult, providerDraftForAction, providerEndpointDraftsForAction, providerTestParamsFingerprint, providerTestParamsMatch } from "./provider-utils"
import { normalizeRolesDraft, validateRolesDraft } from "./role-utils"
import type { ProviderDraft, SettingsPageProps, SettingsTab } from "./types"

const emptyCredentials: CredentialsState = { providers: [] }
const emptyModelGroups: ModelGroup[] = []

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

function modelInfoEvidenceRank(model: ModelInfo): number {
  if (
    model.status === "verified" ||
    model.status === "probe-verified" ||
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
  return {
    providers: found ? providers : [...providers, { ...nextProvider, test_results: [fallbackTestResult] }],
  }
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
  if (found) return { providers }
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
  return {
    providers: [...providers, nextProvider],
  }
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
  if (found || !draft) return { providers }
  return {
    providers: [
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
  }
}

export function SettingsPage({ onClose }: SettingsPageProps) {
  const appSettings = useAppSettings()
  const [activeTab, setActiveTab] = useState<SettingsTab>("general")
  const [credentials, setCredentials] = useState<CredentialsState>(emptyCredentials)
  const [credentialsLoading, setCredentialsLoading] = useState(true)
  const [credentialsError, setCredentialsError] = useState<string | null>(null)
  const [drafts, setDrafts] = useState<ProviderDraft[]>([])
  const [providerTestingActions, setProviderTestingActions] = useState<Record<string, ProviderDraft["testingAction"]>>({})
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
  const credentialsHydratedRef = useRef(false)
  const pendingRoleProjectionRefreshRef = useRef(false)
  // #6: a roles_changed event arrived while the Roles/Copilot tab had never been
  // opened (rolesData still null). Instead of dropping it, set this flag so the
  // lazy load refetches fresh the first time the tab opens.
  const rolesDirtyRef = useRef(false)
  const remoteModelCatalogSyncedRef = useRef(false)
  const visibleDrafts = useMemo(() => (
    drafts.map((draft) => {
      const testingAction = providerTestingActions[draft.id] ?? null
      return testingAction
        ? { ...draft, isTesting: true, testingAction }
        : { ...draft, isTesting: false, testingAction: null }
    })
  ), [drafts, providerTestingActions])

  const handleSaved = useCallback((next: CredentialsState) => {
    setCredentials({
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
    })
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

  useEffect(() => {
    const handleFocus = () => {
      getCredentials({ hydrateSecrets: credentialsHydratedRef.current })
        .then((next) => {
          setCredentials(next)
          setDrafts(draftsFromCredentials(next))
        })
        .catch(() => {})

      if ((activeTab === "llm_roles" || activeTab === "copilot") && rolesDataRef.current) {
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
  }, [activeTab])

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
        setDrafts(draftsFromCredentials(next))
      })
      .catch((error) => {
        console.warn("phase=settings-event-refresh action=credentials-refetch-failed error=%o", error)
      })
  }, [])

  const refetchRolesFromEvent = useCallback(() => {
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
    // Roles tab not opened yet: don't drop the event — mark dirty so the lazy
    // load refetches fresh when the user first opens Roles/Copilot.
    console.info("phase=settings-event-refresh action=roles-marked-dirty reason=roles-not-loaded")
    rolesDirtyRef.current = true
  }, [refetchRolesFromEvent])

  const handleEventResync = useCallback(() => {
    refetchCredentialsFromEvent()
    if (rolesDataRef.current) refetchRolesFromEvent()
  }, [refetchCredentialsFromEvent, refetchRolesFromEvent])

  const { connectionLost } = useStudioEventStream({
    onRegistryChanged: refetchCredentialsFromEvent,
    onRolesChanged: handleRolesChangedEvent,
    onResync: handleEventResync,
  })

  useEffect(() => {
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
    syncRemoteModelCatalog()
      .then(() => {
        refetchCredentialsFromEvent()
      })
      .catch((error) => {
        console.warn("phase=settings-catalog action=remote-model-catalog-sync-failed error=%o", error)
      })
  }, [
    appSettings.isLoading,
    appSettings.settings.remote_model_catalog_enabled,
    refetchCredentialsFromEvent,
  ])

  useEffect(() => {
    let cancelled = false
    getCredentials({ hydrateSecrets: false })
      .then((next) => {
        if (cancelled) return
        invalidatedTestOutcomeIdsRef.current.clear()
        setCredentialsError(null)
        setCredentials(next)
        setDrafts(draftsFromCredentials(next))
        setCredentialsLoading(false)
      })
      .catch((error) => {
        if (cancelled) return
        const message = error instanceof Error ? error.message : "Load failed"
        setCredentialsError(message)
        toast.error(`API Keys load failed: ${message}`)
        setCredentialsLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [])

  useEffect(() => {
    if (activeTab !== "api_keys" || credentialsHydratedRef.current) return
    let cancelled = false
    setCredentialsLoading(true)
    getCredentials()
      .then((next) => {
        if (cancelled) return
        credentialsHydratedRef.current = true
        invalidatedTestOutcomeIdsRef.current.clear()
        setCredentialsError(null)
        setCredentials(next)
        setDrafts(draftsFromCredentials(next))
        setCredentialsLoading(false)
      })
      .catch((error) => {
        if (cancelled) return
        const message = error instanceof Error ? error.message : "Load failed"
        setCredentialsError(message)
        toast.error(`API Keys load failed: ${message}`)
        setCredentialsLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [activeTab])

  useEffect(() => {
    if ((activeTab !== "llm_roles" && activeTab !== "copilot") || rolesData) return
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
  }, [activeTab, rolesData])

  useEffect(() => {
    if ((activeTab !== "llm_roles" && activeTab !== "copilot") || !rolesData) return
    if (!modelGroupsReferenceMissingCredentialProviders(modelGroups, credentials)) return
    void refreshLoadedLlmRolesProjection({
      rolesLoaded: true,
      setModelGroups,
      setRolesData,
      setRolesError,
    })
  }, [activeTab, credentials, modelGroups, rolesData])

  function scheduleSave() {
    queueSave(() => buildPutPayload(draftsRef.current))
  }

  function updateProviderField(providerId: string, patch: Partial<ProviderDraft>) {
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
    scheduleSave()
  }

  function setProviderTesting(providerId: string, testingAction: ProviderDraft["testingAction"]) {
    setProviderTestingActions((current) => {
      if (!testingAction) {
        const next = { ...current }
        delete next[providerId]
        return next
      }
      return { ...current, [providerId]: testingAction }
    })
  }

  function addProviderWithData(data: AddProviderFormSubmission) {
    const draft = draftFromAddProviderSubmission(data)
    setDrafts((current) => {
      const next = [...current, draft]
      queueSave(() => buildPutPayload(next))
      return next
    })
  }

  function deleteProvider(providerId: string) {
    pendingRoleProjectionRefreshRef.current = true
    setDrafts((current) => current.filter((draft) => draft.id !== providerId))
    scheduleSave()
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

  async function runProviderGetModels(providerId: string) {
    await flushCredentialsSave()
    const draft = providerDraftForAction(draftsRef.current, providerId)
    if (!draft) return
    const isOfficial = inferProviderKind(draft) === "official"
    const endpointDrafts = isOfficial ? [draft] : providerEndpointDraftsForAction(draft)

    setProviderTesting(providerId, "models")
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
      for (const endpointDraft of endpointDrafts) {
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
      }
      const latestDraft = providerDraftForAction(draftsRef.current, providerId)
      if (!latestDraft) {
        toast.info("Test result ignored because provider configuration changed.", { id: toastId })
        return
      }
      const latestEndpointDrafts = isOfficial ? [latestDraft] : providerEndpointDraftsForAction(latestDraft)
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
        const response = responses[0]
        toast.error(
          response
            ? composeTestErrorMessage(response.status, response.error_code, response.message)
            : "Provider test failed",
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

  return (
    <SettingsPageContent
      activeTab={activeTab}
      credentials={credentials}
      credentialsLoading={credentialsLoading}
      credentialsError={credentialsError}
      drafts={visibleDrafts}
      saveStatus={saveStatus}
      rolesData={rolesData}
      modelGroups={modelGroups}
      rolesSaveStatus={rolesSaveStatus}
      rolesError={rolesError}
      appSettings={{
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
      }}
      connectionLost={connectionLost}
      onClose={onClose}
      onTabChange={setActiveTab}
      onProviderFieldChange={updateProviderField}
      onGetProviderModels={(providerId) => void runProviderGetModels(providerId)}
      onDeleteProvider={deleteProvider}
      onAddProvider={addProviderWithData}
      onProviderModelsUpdated={updateProviderModels}
      onRolesDataChange={updateRolesData}
      onDeleteRole={deleteRoleByName}
      onDeleteModelBundle={deleteModelBundleById}
      onBeforeRoleTest={flushRolesSave}
      onAfterRoleTest={refreshRolesProjection}
      onNavigateToApiKeys={() => setActiveTab("api_keys")}
    />
  )
}

function providerEndpointIdentityMatches(left: ProviderDraft, right: ProviderDraft): boolean {
  return (
    left.id === right.id &&
    (left.provider_type ?? null) === (right.provider_type ?? null) &&
    comparableProviderBaseUrl(left.base_url) === comparableProviderBaseUrl(right.base_url)
  )
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
