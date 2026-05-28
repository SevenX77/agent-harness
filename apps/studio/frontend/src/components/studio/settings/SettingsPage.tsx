import { useCallback, useEffect, useRef, useState } from "react"
import { toast } from "sonner"
import { useAppSettings } from "@/hooks/useAppSettings"
import { buildPutPayload, useDebouncedCredentialsSave } from "@/hooks/useDebouncedCredentialsSave"
import { useDebouncedRolesSave } from "@/hooks/useDebouncedRolesSave"
import { composeRequestErrorMessage, composeTestErrorMessage } from "@/lib/llm-error-messages"
import { getCredentials, getModelGroups, getProviderModels, getRoles, testProviderEndpoint, type CredentialsState, type ModelGroup, type ModelInfo, type ProviderTestResponse, type ProviderTestResult, type RolesData } from "../../../api/llm"
import type { AddProviderFormSubmission } from "../api-keys"
import { SettingsPageContent } from "./SettingsPageContent"
import { draftsFromCredentials, draftFromAddProviderSubmission, providerCachedTestResult, providerDraftForAction, providerTestParamsFingerprint, providerTestParamsMatch } from "./provider-utils"
import { normalizeRolesDraft, validateRolesDraft } from "./role-utils"
import type { ProviderDraft, SettingsPageProps, SettingsTab } from "./types"

const emptyCredentials: CredentialsState = { providers: [] }
const emptyModelGroups: ModelGroup[] = []

function mergeModelInfos(left: ModelInfo[] = [], right: ModelInfo[] = []): ModelInfo[] {
  const merged = new Map<string, ModelInfo>()
  for (const model of left) merged.set(model.id, model)
  for (const model of right) merged.set(model.id, model)
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

export function upsertProviderTestResponse(
  current: CredentialsState,
  latestDraft: ProviderDraft,
  response: ProviderTestResponse,
): CredentialsState {
  const fingerprint = providerTestParamsFingerprint(latestDraft)
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
    available_models: response.available_models ?? [],
    available_sdks: response.available_sdks ?? [],
  }
  const lastTestStatus = nextProvider.last_test_status ?? "untested"
  let found = false
  const providers: CredentialsState["providers"] = current.providers.map((provider): CredentialsState["providers"][number] => {
    if (provider.id !== latestDraft.id) return provider
    found = true
    const previousResult = (provider.test_results ?? []).find((item) => item.params_fingerprint === fingerprint)
    const visibleModels = lastTestStatus === "ok"
      ? mergeModelInfos(provider.available_models, response.available_models)
      : previousResult?.available_models ?? provider.available_models ?? []
    const visibleSdks = lastTestStatus === "ok"
      ? mergeStrings(provider.available_sdks, response.available_sdks)
      : previousResult?.available_sdks ?? provider.available_sdks ?? []
    const testResult: ProviderTestResult = {
      params_fingerprint: fingerprint,
      base_url: latestDraft.base_url,
      provider_type: latestDraft.provider_type,
      last_test_status: lastTestStatus,
      last_test_at: nextProvider.last_test_at,
      last_test_message: nextProvider.last_test_message,
      last_error_code: nextProvider.last_error_code,
      available_models: visibleModels,
      available_sdks: visibleSdks,
    }
    const testResults = [
      ...(provider.test_results ?? []).filter((item) => item.params_fingerprint !== testResult.params_fingerprint),
      testResult,
    ]
    return {
      ...provider,
      ...nextProvider,
      available_models: visibleModels,
      available_sdks: visibleSdks,
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
    const testResults = [
      ...(provider.test_results ?? []).filter((item) => item.params_fingerprint !== testResult.params_fingerprint),
      testResult,
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
      available_models: models,
      available_sdks: sdks,
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
  }, [])

  const { flush: flushCredentialsSave, queue: queueSave, status: saveStatus } = useDebouncedCredentialsSave({
    onSaved: handleSaved,
  })
  const { cancel: cancelRolesSave, queue: queueRolesSave, status: rolesSaveStatus } = useDebouncedRolesSave({
    onSaved: (next) => {
      setRolesData(next)
      setRolesError(null)
    },
    onError: (error) => {
      setRolesError(composeRequestErrorMessage(error, "Save failed"))
    },
  })

  useEffect(() => {
    let cancelled = false
    getCredentials()
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
    if (activeTab !== "llm_roles" || rolesData) return
    let cancelled = false
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
    setDrafts((current) => current.map((draft) => (
      draft.id === providerId ? { ...draft, isTesting: Boolean(testingAction), testingAction } : draft
    )))
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
    const testedParams = {
      api_key: draft.api_key,
      base_url: draft.base_url,
      provider_type: draft.provider_type,
    }

    setProviderTesting(providerId, "models")
    const toastId = `get-models-${providerId}`
    toast.loading(`Getting models for ${draft.name || "provider"}...`, { id: toastId })

    try {
      const response = await getProviderModels({
        id: draft.id,
        provider_type: draft.provider_type,
        api_key: draft.api_key.trim(),
        base_url: draft.base_url || undefined,
      })

      const latestDraft = providerDraftForAction(draftsRef.current, providerId)
      if (!latestDraft || !providerTestParamsMatch(latestDraft, testedParams)) {
        toast.info("Test result ignored because provider configuration changed.", { id: toastId })
        return
      }
      invalidatedTestOutcomeIdsRef.current.delete(providerId)

      setCredentials((current) => upsertProviderModelsListResponse(current, latestDraft, response))

      if (response.status === "ok") {
        const modelCount = response.available_models?.length ?? 0
        if (modelCount > 0) {
          toast.success(`Models listed (${modelCount} models)`, { id: toastId })
        } else {
          toast.warning("Model-list endpoint is reachable, but no models were returned.", { id: toastId })
        }
      } else {
        toast.error(composeTestErrorMessage(response.status, response.error_code, response.message), { id: toastId })
      }
    } catch (error) {
      toast.error(composeRequestErrorMessage(error, "Get models failed"), { id: toastId })
    } finally {
      setProviderTesting(providerId, null)
    }
  }

  async function runProviderEndpointTest(providerId: string, modelId: string) {
    await flushCredentialsSave()
    const draft = providerDraftForAction(draftsRef.current, providerId)
    const trimmedModelId = modelId.trim()
    if (!draft || !trimmedModelId) return
    const testedParams = {
      api_key: draft.api_key,
      base_url: draft.base_url,
      provider_type: draft.provider_type,
    }

    setProviderTesting(providerId, "endpoint")
    const toastId = `endpoint-test-${providerId}`
    toast.loading(`Testing ${draft.name || "provider"} endpoint...`, { id: toastId })

    try {
      const response = await testProviderEndpoint({
        id: draft.id,
        provider_type: draft.provider_type,
        api_key: draft.api_key.trim(),
        base_url: draft.base_url || undefined,
        model_id: trimmedModelId,
      })

      const latestDraft = providerDraftForAction(draftsRef.current, providerId)
      if (!latestDraft || !providerTestParamsMatch(latestDraft, testedParams)) {
        toast.info("Endpoint test result ignored because provider configuration changed.", { id: toastId })
        return
      }
      invalidatedTestOutcomeIdsRef.current.delete(providerId)
      setCredentials((current) => upsertProviderTestResponse(current, latestDraft, response))

      if (response.status === "ok") {
        toast.success(`Connected (${trimmedModelId})`, { id: toastId })
      } else {
        toast.error(composeTestErrorMessage(response.status, response.error_code, response.message), { id: toastId })
      }
    } catch (error) {
      toast.error(composeRequestErrorMessage(error, "Endpoint test failed"), { id: toastId })
    } finally {
      setProviderTesting(providerId, null)
    }
  }

  function updateRolesData(next: RolesData) {
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
  }

  return (
    <SettingsPageContent
      activeTab={activeTab}
      credentials={credentials}
      credentialsLoading={credentialsLoading}
      credentialsError={credentialsError}
      drafts={drafts}
      saveStatus={saveStatus}
      rolesData={rolesData}
      modelGroups={modelGroups}
      rolesSaveStatus={rolesSaveStatus}
      rolesError={rolesError}
      appSettings={{
        userId: appSettings.settings.user_id,
        giteaHost: appSettings.settings.gitea_host,
        defaultSkillsDirectory: appSettings.settings.default_skills_directory,
        isLoading: appSettings.isLoading,
        saveStatus: appSettings.saveStatus,
        setUserId: appSettings.setUserId,
        setGiteaHost: appSettings.setGiteaHost,
        setDefaultSkillsDirectory: appSettings.setDefaultSkillsDirectory,
      }}
      onClose={onClose}
      onTabChange={setActiveTab}
      onProviderFieldChange={updateProviderField}
      onGetProviderModels={(providerId) => void runProviderGetModels(providerId)}
      onTestProviderEndpoint={(providerId, modelId) => void runProviderEndpointTest(providerId, modelId)}
      onDeleteProvider={deleteProvider}
      onAddProvider={addProviderWithData}
      onProviderModelsUpdated={updateProviderModels}
      onRolesDataChange={updateRolesData}
    />
  )
}
