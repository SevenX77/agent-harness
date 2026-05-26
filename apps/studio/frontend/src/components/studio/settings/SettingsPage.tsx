import { useCallback, useEffect, useRef, useState } from "react"
import { toast } from "sonner"
import { useAppSettings } from "@/hooks/useAppSettings"
import { buildPutPayload, useDebouncedCredentialsSave } from "@/hooks/useDebouncedCredentialsSave"
import { useDebouncedRolesSave } from "@/hooks/useDebouncedRolesSave"
import { composeRequestErrorMessage, composeTestErrorMessage } from "@/lib/llm-error-messages"
import { getCredentials, getRoles, testProvider, type CredentialsState, type ModelInfo, type RolesData } from "../../../api/llm"
import type { AddProviderFormSubmission } from "../api-keys"
import { SettingsPageContent } from "./SettingsPageContent"
import { draftsFromCredentials, draftFromAddProviderSubmission, providerCachedTestResult, providerDraftForAction, providerTestParamsMatch } from "./provider-utils"
import { normalizeRolesDraft, validateRolesDraft } from "./role-utils"
import type { ProviderDraft, SettingsPageProps, SettingsTab } from "./types"

const emptyCredentials: CredentialsState = { providers: [] }

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

export function SettingsPage({ onClose }: SettingsPageProps) {
  const appSettings = useAppSettings()
  const [activeTab, setActiveTab] = useState<SettingsTab>("general")
  const [credentials, setCredentials] = useState<CredentialsState>(emptyCredentials)
  const [credentialsLoading, setCredentialsLoading] = useState(true)
  const [credentialsError, setCredentialsError] = useState<string | null>(null)
  const [drafts, setDrafts] = useState<ProviderDraft[]>([])
  const [rolesData, setRolesData] = useState<RolesData | null>(null)
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

  const { queue: queueSave, status: saveStatus } = useDebouncedCredentialsSave({
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
    getRoles()
      .then((next) => {
        if (cancelled) return
        setRolesData(next)
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
        },
      ]
    })
    scheduleSave()
  }

  function setProviderTesting(providerId: string, isTesting: boolean) {
    setDrafts((current) => current.map((draft) => (
      draft.id === providerId ? { ...draft, isTesting } : draft
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
    setCredentials((current) => ({
      providers: current.providers.map((provider) => (
        provider.id === providerId ? { ...provider, available_models: models } : provider
      )),
    }))
  }

  async function runProviderTest(providerId: string) {
    const draft = providerDraftForAction(draftsRef.current, providerId)
    if (!draft) return
    const testedParams = {
      api_key: draft.api_key,
      base_url: draft.base_url,
      provider_type: draft.provider_type,
    }

    setProviderTesting(providerId, true)
    const toastId = `test-${providerId}`
    toast.loading(`Testing ${draft.name || "provider"}...`, { id: toastId })

    try {
      const response = await testProvider({
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

      // F5: splice the persisted Test outcome into local credentials without a GET round-trip.
      setCredentials((current) => ({
        providers: current.providers.map((provider) => {
          if (provider.id !== providerId) return provider
          return {
            ...provider,
            name: latestDraft.name,
            api_key: latestDraft.api_key,
            base_url: latestDraft.base_url,
            provider_type: latestDraft.provider_type,
            last_test_status: response.status === "missing_api_key" ? "untested" : response.status,
            last_test_at: new Date().toISOString(),
            last_test_message: response.message ?? "",
            last_error_code: response.error_code ?? "",
            available_models: response.available_models ?? provider.available_models ?? [],
            available_sdks: response.available_sdks ?? provider.available_sdks ?? [],
          }
        }),
      }))

      if (response.status === "ok") {
        const latency = response.latency_ms ? `${response.latency_ms}ms` : ""
        const modelCount = response.available_models?.length ?? 0
        const detail = [latency, modelCount > 0 ? `${modelCount} models` : ""].filter(Boolean).join(" · ")
        toast.success(detail ? `Connected (${detail})` : "Connected", { id: toastId })
      } else {
        toast.error(composeTestErrorMessage(response.status, response.error_code, response.message), { id: toastId })
      }
    } catch (error) {
      toast.error(composeRequestErrorMessage(error, "Test failed"), { id: toastId })
    } finally {
      setProviderTesting(providerId, false)
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
      onTestProvider={(providerCode) => void runProviderTest(providerCode)}
      onDeleteProvider={deleteProvider}
      onAddProvider={addProviderWithData}
      onProviderModelsUpdated={updateProviderModels}
      onRolesDataChange={updateRolesData}
    />
  )
}
