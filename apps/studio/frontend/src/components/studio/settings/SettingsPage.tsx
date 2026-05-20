import { useCallback, useEffect, useRef, useState } from "react"
import { toast } from "sonner"
import { useAppSettings } from "@/hooks/useAppSettings"
import { buildPutPayload, useDebouncedCredentialsSave } from "@/hooks/useDebouncedCredentialsSave"
import { composeTestErrorMessage } from "@/lib/llm-error-messages"
import { getCredentials, getRoles, putRoles, testProvider, type CredentialsState, type ModelInfo, type RolesData } from "../../../api/llm"
import type { AddProviderFormSubmission } from "../api-keys"
import { SettingsPageContent } from "./SettingsPageContent"
import { draftsFromCredentials, draftFromAddProviderSubmission } from "./provider-utils"
import { validateRoleDraft, visibleRoleNames } from "./role-utils"
import type { ProviderDraft, SettingsPageProps, SettingsTab } from "./types"

const emptyCredentials: CredentialsState = { providers: [] }

export function SettingsPage({ onClose }: SettingsPageProps) {
  const appSettings = useAppSettings()
  const [activeTab, setActiveTab] = useState<SettingsTab>("general")
  const [credentials, setCredentials] = useState<CredentialsState>(emptyCredentials)
  const [credentialsLoading, setCredentialsLoading] = useState(true)
  const [drafts, setDrafts] = useState<ProviderDraft[]>([])
  const [rolesData, setRolesData] = useState<RolesData | null>(null)
  const [selectedRole, setSelectedRole] = useState("copilot_chat")
  const [rolesDirty, setRolesDirty] = useState(false)
  const [rolesError, setRolesError] = useState<string | null>(null)

  // Keep a ref of the most recent draft list so the debounced save can read it
  // at fire time (avoids re-binding the timer on every keystroke).
  const draftsRef = useRef<ProviderDraft[]>(drafts)
  draftsRef.current = drafts

  const handleSaved = useCallback((next: CredentialsState) => {
    setCredentials(next)
    // Re-sync plaintext api_key per provider from the persisted response.
    setDrafts((current) => current.map((draft) => {
      const persisted = next.providers.find((provider) => provider.id === draft.id)
      if (!persisted) return draft
      return {
        ...draft,
        api_key: persisted.api_key,
      }
    }))
  }, [])

  const { queue: queueSave, status: saveStatus } = useDebouncedCredentialsSave({
    onSaved: handleSaved,
  })

  useEffect(() => {
    let cancelled = false
    getCredentials()
      .then((next) => {
        if (cancelled) return
        setCredentials(next)
        setDrafts(draftsFromCredentials(next))
        setCredentialsLoading(false)
      })
      .catch((error) => {
        if (cancelled) return
        const message = error instanceof Error ? error.message : "Load failed"
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
        if (!next.roles[selectedRole]) setSelectedRole(visibleRoleNames(next)[0] ?? "")
      })
      .catch(() => {
        if (!cancelled) setRolesError("Roles unavailable")
      })
    return () => {
      cancelled = true
    }
  }, [activeTab, rolesData, selectedRole])

  function scheduleSave() {
    queueSave(() => buildPutPayload(draftsRef.current))
  }

  function updateProviderField(providerId: string, patch: Partial<ProviderDraft>) {
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
    const draft = draftsRef.current.find((d) => d.id === providerId)
    if (!draft) return

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

      // F5: splice the persisted Test outcome into local credentials without a GET round-trip.
      setCredentials((current) => ({
        providers: current.providers.map((provider) => {
          if (provider.id !== providerId) return provider
          return {
            ...provider,
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
      const message = error instanceof Error ? error.message : "Unknown error"
      toast.error(`Test failed: ${message}`, { id: toastId })
    } finally {
      setProviderTesting(providerId, false)
    }
  }

  function updateRolesData(next: RolesData) {
    setRolesData(next)
    setRolesDirty(true)
    setRolesError(null)
  }

  async function saveRoles() {
    if (!rolesData) return
    const validationError = validateRoleDraft(rolesData, selectedRole)
    if (validationError) {
      setRolesError(validationError)
      toast.error(`Validation failed: ${validationError}`)
      return
    }
    try {
      const saved = await putRoles(rolesData)
      setRolesData(saved)
      setRolesDirty(false)
      setRolesError(null)
      toast.success("Roles saved")
    } catch (error) {
      const message = error instanceof Error ? error.message : "Save failed"
      setRolesError(message)
      toast.error(`Validation failed: ${message}`)
    }
  }

  return (
    <SettingsPageContent
      activeTab={activeTab}
      credentials={credentials}
      credentialsLoading={credentialsLoading}
      drafts={drafts}
      saveStatus={saveStatus}
      rolesData={rolesData}
      selectedRole={selectedRole}
      rolesDirty={rolesDirty}
      rolesError={rolesError}
      appSettings={{
        userId: appSettings.settings.user_id,
        giteaHost: appSettings.settings.gitea_host,
        isLoading: appSettings.isLoading,
        setUserId: appSettings.setUserId,
        setGiteaHost: appSettings.setGiteaHost,
        save: appSettings.save,
      }}
      onClose={onClose}
      onTabChange={setActiveTab}
      onProviderFieldChange={updateProviderField}
      onTestProvider={(providerCode) => void runProviderTest(providerCode)}
      onDeleteProvider={deleteProvider}
      onAddProvider={addProviderWithData}
      onProviderModelsUpdated={updateProviderModels}
      onSelectedRoleChange={setSelectedRole}
      onRolesDataChange={updateRolesData}
      onSaveRoles={() => void saveRoles()}
    />
  )
}
