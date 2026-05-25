import { useCallback, useEffect, useRef, useState } from "react"
import { toast } from "sonner"
import {
  applyModelProfile,
  applyProviderImportDraft,
  deleteEndpoint,
  getRegistry,
  probeRoute,
  testEndpoint,
  type CredentialRegistryResponse,
  type ProviderEndpoint,
  type ProviderImportDraft,
  type RegistryResponse,
  type RolesData,
} from "@/api/llm"
import { useDebouncedCredentialsSave } from "@/hooks/useDebouncedCredentialsSave"
import { useDebouncedRolesSave } from "@/hooks/useDebouncedRolesSave"
import { useRoleTestChainRunner } from "@/hooks/useRoleTestChainRunner"
import { useAppSettings } from "@/hooks/useAppSettings"
import { composeRequestErrorMessage } from "@/lib/llm-error-messages"
import { SettingsPageContent } from "./SettingsPageContent"
import type { SettingsPageProps, SettingsTab } from "./types"

function rolesFromRegistry(registry: RegistryResponse | null): RolesData | null {
  if (!registry) return null
  return {
    schema_version: 2,
    model_profiles: registry.model_profiles,
    roles: registry.roles,
  }
}

function mergeCredentials(registry: RegistryResponse | null, next: CredentialRegistryResponse): RegistryResponse | null {
  if (!registry) return registry
  return {
    ...registry,
    provider_endpoints: next.provider_endpoints,
    provider_routes: next.provider_routes,
    runtime_policy: next.runtime_policy,
  }
}

function newEndpointId(): string {
  const id = globalThis.crypto?.randomUUID?.() ?? `${Date.now()}`
  return `custom-${id.toLowerCase()}`
}

function blankEndpoint(endpointId: string): ProviderEndpoint {
  return {
    endpoint_id: endpointId,
    display_name: "New Endpoint",
    protocol: "openai_compatible",
    base_url: "",
    api_key: "",
    status: "unverified_manual",
    timeout_seconds: 60,
    trust_env: false,
    proxy_env: null,
    metadata: {},
  }
}

export function mergeEndpointTestResult(
  current: ProviderEndpoint,
  response: ProviderEndpoint,
): ProviderEndpoint {
  return {
    ...current,
    status: response.status,
    last_test_at: response.last_test_at ?? null,
    last_test_message: response.last_test_message ?? null,
  }
}

export function SettingsPage({ onClose }: SettingsPageProps) {
  const appSettings = useAppSettings()
  const [activeTab, setActiveTab] = useState<SettingsTab>("general")
  const [registry, setRegistry] = useState<RegistryResponse | null>(null)
  const [registryLoading, setRegistryLoading] = useState(true)
  const [registryError, setRegistryError] = useState<string | null>(null)
  const [rolesError, setRolesError] = useState<string | null>(null)
  const [importDrafts, setImportDrafts] = useState<ProviderImportDraft[]>([])
  const registryRef = useRef<RegistryResponse | null>(registry)
  registryRef.current = registry

  const { queue: queueEndpointSave, status: endpointSaveStatus } = useDebouncedCredentialsSave({
    onSaved: (next) => {
      setRegistry((current) => mergeCredentials(current, next))
      setRegistryError(null)
    },
    onError: (error) => {
      setRegistryError(composeRequestErrorMessage(error, "Endpoint save failed"))
    },
  })

  const { queue: queueRolesSave, cancel: cancelRolesSave, status: rolesSaveStatus } = useDebouncedRolesSave({
    onSaved: (next) => {
      setRegistry((current) => current ? {
        ...current,
        model_profiles: next.model_profiles,
        roles: next.roles,
      } : current)
      setRolesError(null)
    },
    onError: (error) => {
      setRolesError(composeRequestErrorMessage(error, "Role save failed"))
    },
  })

  const { run: runRoleProbe } = useRoleTestChainRunner()

  const refreshRegistry = useCallback(async () => {
    const next = await getRegistry()
    setRegistry(next)
    setRegistryError(null)
    return next
  }, [])

  useEffect(() => {
    let cancelled = false
    getRegistry()
      .then((next) => {
        if (cancelled) return
        setRegistry(next)
        setRegistryError(null)
        setRegistryLoading(false)
      })
      .catch((error) => {
        if (cancelled) return
        setRegistryError(composeRequestErrorMessage(error, "Registry load failed"))
        setRegistryLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [])

  function scheduleEndpointSave(nextRegistry: RegistryResponse) {
    queueEndpointSave(() => Object.values(nextRegistry.provider_endpoints))
  }

  function addEndpoint() {
    setRegistry((current) => {
      if (!current) return current
      const endpointId = newEndpointId()
      const next = {
        ...current,
        provider_endpoints: {
          ...current.provider_endpoints,
          [endpointId]: blankEndpoint(endpointId),
        },
      }
      scheduleEndpointSave(next)
      return next
    })
  }

  function updateEndpoint(endpointId: string, patch: Partial<ProviderEndpoint>) {
    setRegistry((current) => {
      const endpoint = current?.provider_endpoints[endpointId]
      if (!current || !endpoint) return current
      const next = {
        ...current,
        provider_endpoints: {
          ...current.provider_endpoints,
          [endpointId]: { ...endpoint, ...patch },
        },
      }
      scheduleEndpointSave(next)
      return next
    })
  }

  async function runEndpointTest(endpointId: string) {
    const toastId = `endpoint-test-${endpointId}`
    toast.loading(`Testing endpoint ${endpointId}...`, { id: toastId })
    try {
      const endpoint = await testEndpoint(endpointId)
      setRegistry((current) => current ? {
        ...current,
        provider_endpoints: {
          ...current.provider_endpoints,
          [endpointId]: current.provider_endpoints[endpointId]
            ? mergeEndpointTestResult(current.provider_endpoints[endpointId], endpoint)
            : endpoint,
        },
      } : current)
      toast.success(`Endpoint ${endpointId} tested.`, { id: toastId })
    } catch (error) {
      toast.error(composeRequestErrorMessage(error, "Endpoint test failed"), { id: toastId })
    }
  }

  async function removeEndpoint(endpointId: string) {
    try {
      await deleteEndpoint(endpointId)
      await refreshRegistry()
      toast.success(`Endpoint ${endpointId} deleted.`)
    } catch (error) {
      toast.error(composeRequestErrorMessage(error, "Delete endpoint failed"))
    }
  }

  async function runRouteProbe(routeId: string) {
    const toastId = `route-probe-${routeId}`
    toast.loading(`Probing route ${routeId}...`, { id: toastId })
    try {
      const route = await probeRoute(routeId, { capabilities: ["thinking", "tool_calling", "structured_output", "vision"] })
      setRegistry((current) => current ? {
        ...current,
        provider_routes: {
          ...current.provider_routes,
          [routeId]: route,
        },
      } : current)
      toast.success(`Route ${routeId} probed.`, { id: toastId })
    } catch (error) {
      toast.error(composeRequestErrorMessage(error, "Route probe failed"), { id: toastId })
    }
  }

  async function applyDraft(draftId: string) {
    try {
      const nextDraft = await applyProviderImportDraft(draftId, "merge")
      setImportDrafts((current) => current.map((draft) => draft.draft_id === draftId ? nextDraft : draft))
      await refreshRegistry()
      toast.success(`Import draft ${draftId} applied.`)
    } catch (error) {
      toast.error(composeRequestErrorMessage(error, "Apply draft failed"))
    }
  }

  function updateRolesData(next: RolesData) {
    setRegistry((current) => current ? {
      ...current,
      model_profiles: next.model_profiles,
      roles: next.roles,
    } : current)
    setRolesError(null)
    queueRolesSave(() => next)
  }

  function probeRole(roleName: string) {
    const current = registryRef.current
    const data = rolesFromRegistry(current)
    if (!current || !data) return
    void runRoleProbe({ data, roleName, registry: current })
    void Promise.all(data.roles[roleName]?.fallback_chain.map((entry) => runRouteProbe(entry.route_id)) ?? [])
  }

  async function applyProfile(roleName: string, profileId: string) {
    try {
      const role = await applyModelProfile(roleName, { model_profile_id: profileId })
      setRegistry((current) => current ? {
        ...current,
        roles: {
          ...current.roles,
          [roleName]: role,
        },
      } : current)
      toast.success(`Profile ${profileId} applied to ${roleName}.`)
    } catch (error) {
      setRolesError(composeRequestErrorMessage(error, "Apply profile failed"))
      toast.error(composeRequestErrorMessage(error, "Apply profile failed"))
    }
  }

  useEffect(() => {
    return () => {
      cancelRolesSave()
    }
  }, [cancelRolesSave])

  return (
    <SettingsPageContent
      activeTab={activeTab}
      registry={registry}
      registryLoading={registryLoading}
      registryError={registryError}
      endpointSaveStatus={endpointSaveStatus}
      importDrafts={importDrafts}
      rolesData={rolesFromRegistry(registry)}
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
      onAddEndpoint={addEndpoint}
      onEndpointChange={updateEndpoint}
      onDeleteEndpoint={(endpointId) => void removeEndpoint(endpointId)}
      onTestEndpoint={(endpointId) => void runEndpointTest(endpointId)}
      onProbeRoute={(routeId) => void runRouteProbe(routeId)}
      onApplyDraft={(draftId) => void applyDraft(draftId)}
      onRolesDataChange={updateRolesData}
      onProbeRole={probeRole}
      onApplyProfile={(roleName, profileId) => void applyProfile(roleName, profileId)}
    />
  )
}
