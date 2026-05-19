import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react"
import { ArrowDown, ArrowUp, Check, KeyRound, Loader2, Plug, Plus, Settings, TriangleAlert, X } from "lucide-react"
import { toast } from "sonner"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip"
import { useAppSettings } from "@/hooks/useAppSettings"
import {
  buildPutPayload,
  useDebouncedCredentialsSave,
  type SaveStatus,
} from "@/hooks/useDebouncedCredentialsSave"
import { composeTestErrorMessage } from "@/lib/llm-error-messages"
import { cn } from "@/lib/utils"
import {
  getCredentials,
  getRoles,
  putRoles,
  testProvider,
  type CredentialsState,
  type ModelInfo,
  type ProviderType,
  type RolesData,
} from "../../api/llm"
import { AddProviderForm, ProviderCard, ProviderListSkeleton, type AddProviderFormSubmission } from "./api-keys"

type SettingsTab = "general" | "api_keys" | "llm_roles"

const emptyCredentials: CredentialsState = { providers: [] }
const DISABLED_ROLE_EDITING = "Adding new model/provider coming in v2.5"

export interface ProviderDraft {
  id: string
  name: string
  provider_type: ProviderType
  base_url: string
  api_key: string
  isTesting: boolean
}

/** What the LLM Roles tab knows about a single provider. */
interface ProviderAvailabilityInput {
  api_key: string
  last_test_status?: string
}

/**
 * Categorise a model's runnable state based on its provider chain (F6).
 *
 * - `ok`           — at least one provider has a stored key AND the most
 *                    recent Test came back `ok`. The model is ready to run.
 * - `key_only`     — providers have keys but none have passed a Test. The
 *                    model *might* run; surface as a soft warning.
 * - `unavailable`  — no provider in the chain has a stored key, so the
 *                    engine has nothing to route to.
 *
 * The badge shown in the dropdown options follows the same enum.
 */
export type ModelAvailability = "ok" | "key_only" | "unavailable"

export function getModelAvailability(
  providers: ReadonlyArray<string>,
  credentialsByCode: Readonly<Record<string, ProviderAvailabilityInput | undefined>>,
): ModelAvailability {
  let sawKey = false
  for (const code of providers) {
    const credential = credentialsByCode[code]
    if (!credential?.api_key.trim()) continue
    sawKey = true
    if (credential.last_test_status === "ok") return "ok"
  }
  return sawKey ? "key_only" : "unavailable"
}

interface SettingsPageProps {
  onClose: () => void
}

interface SettingsPageContentProps {
  activeTab: SettingsTab
  /** Server-persisted credentials snapshot — feeds both the ApiKeys flat list and the LLM Roles availability filter. */
  credentials: CredentialsState
  credentialsLoading: boolean
  drafts: ProviderDraft[]
  saveStatus: SaveStatus
  rolesData: RolesData | null
  selectedRole: string
  rolesDirty: boolean
  rolesError: string | null
  appSettings: {
    userId: string
    giteaHost: string
    isLoading: boolean
    setUserId: (value: string) => void
    setGiteaHost: (value: string) => void
    save: () => void | Promise<unknown>
  }
  onClose: () => void
  onTabChange: (tab: SettingsTab) => void
  onProviderFieldChange: (providerId: string, patch: Partial<ProviderDraft>) => void
  onTestProvider: (providerId: string) => void
  onDeleteProvider: (providerId: string) => void
  onAddProvider: (data: AddProviderFormSubmission) => Promise<void> | void
  onProviderModelsUpdated: (providerId: string, models: ModelInfo[]) => void
  onSelectedRoleChange: (roleName: string) => void
  onRolesDataChange: (next: RolesData) => void
  onSaveRoles: () => void
}

/** Build a draft list from the server `CredentialsState` snapshot. */
export function draftsFromCredentials(credentials: CredentialsState): ProviderDraft[] {
  return credentials.providers.map((provider) => ({
    id: provider.id,
    name: provider.name,
    provider_type: (provider.provider_type ?? "openai_compatible") as ProviderType,
    base_url: provider.base_url ?? "",
    api_key: provider.api_key,
    isTesting: false,
  }))
}

export function visibleRoleNames(data: RolesData): string[] {
  return Object.keys(data.roles).filter((roleName) => !roleName.startsWith("deerflow_"))
}

export function updateActiveModel(data: RolesData, roleName: string, activeModel: string): RolesData {
  const next = cloneRolesData(data)
  next.roles[roleName] = { ...next.roles[roleName], active_model: activeModel }
  return next
}

export function toggleModelFallback(data: RolesData, roleName: string, enabled: boolean): RolesData {
  const next = cloneRolesData(data)
  next.roles[roleName] = { ...next.roles[roleName], model_fallback: enabled }
  return next
}

export function moveProviderInRole(
  data: RolesData,
  roleName: string,
  modelCode: string,
  providerIndex: number,
  direction: -1 | 1,
): RolesData {
  const next = cloneRolesData(data)
  const providers = [...next.roles[roleName].models[modelCode].providers]
  const targetIndex = providerIndex + direction
  if (targetIndex < 0 || targetIndex >= providers.length) return data
  ;[providers[providerIndex], providers[targetIndex]] = [providers[targetIndex], providers[providerIndex]]
  next.roles[roleName].models[modelCode] = { providers }
  return next
}

export function removeProviderFromRole(
  data: RolesData,
  roleName: string,
  modelCode: string,
  providerIndex: number,
): RolesData {
  const next = cloneRolesData(data)
  const providers = next.roles[roleName].models[modelCode].providers.filter((_, index) => index !== providerIndex)
  next.roles[roleName].models[modelCode] = { providers }
  return next
}

export function moveModelInRole(
  data: RolesData,
  roleName: string,
  modelCode: string,
  direction: -1 | 1,
): RolesData {
  const next = cloneRolesData(data)
  const entries = Object.entries(next.roles[roleName].models)
  const index = entries.findIndex(([code]) => code === modelCode)
  const targetIndex = index + direction
  if (index < 0 || targetIndex < 0 || targetIndex >= entries.length) return data
  ;[entries[index], entries[targetIndex]] = [entries[targetIndex], entries[index]]
  next.roles[roleName].models = Object.fromEntries(entries)
  return next
}

export function removeModelFromRole(data: RolesData, roleName: string, modelCode: string): RolesData {
  const next = cloneRolesData(data)
  const models = { ...next.roles[roleName].models }
  delete models[modelCode]
  const activeModel = next.roles[roleName].active_model === modelCode ? Object.keys(models)[0] ?? "" : next.roles[roleName].active_model
  next.roles[roleName] = { ...next.roles[roleName], models, active_model: activeModel }
  return next
}

export function validateRoleDraft(data: RolesData, roleName: string): string | null {
  const role = data.roles[roleName]
  if (!role) return "Role not found"
  const modelCodes = Object.keys(role.models)
  if (modelCodes.length === 0) return "Role must contain at least one model"
  if (!role.active_model || !role.models[role.active_model]) return "Active model must exist in this role"
  for (const modelCode of modelCodes) {
    if (role.models[modelCode].providers.length === 0) return `Model ${modelCode} must contain at least one provider`
  }
  return null
}

function cloneRolesData(data: RolesData): RolesData {
  return structuredClone(data) as RolesData
}

function newProviderId(): string {
  return (globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random().toString(36).slice(2)}`).toString()
}

const officialProviders = [
  { code: "anthropic", label: "Anthropic", baseUrl: "https://api.anthropic.com" },
  { code: "openai", label: "OpenAI", baseUrl: "https://api.openai.com" },
  { code: "gemini", label: "Gemini", baseUrl: "https://generativelanguage.googleapis.com" },
  { code: "deepseek", label: "DeepSeek", baseUrl: "https://api.deepseek.com" },
  { code: "ark", label: "Ark", baseUrl: "https://ark.cn-beijing.volces.com/api/v3" },
]
const officialProviderCodes = officialProviders.map((vendor) => vendor.code)

export function inferProviderType(providerCode: string): ProviderType {
  if (providerCode === "anthropic") return "anthropic_compatible"
  if (providerCode === "gemini") return "google_genai"
  return "openai_compatible"
}

export function inferProviderKind(draft: ProviderDraft): "official" | "third-party" {
  if (officialProviderCodes.some((code) => isOfficialProviderDraft(draft, code))) return "official"
  return "third-party"
}

export function draftFromAddProviderSubmission(
  data: AddProviderFormSubmission,
  id: string = newProviderId(),
): ProviderDraft {
  return {
    id,
    name: data.name,
    provider_type: "openai_compatible",
    base_url: data.baseUrl,
    api_key: data.apiKey,
    isTesting: false,
  }
}

export function officialProviderDrafts(drafts: ProviderDraft[]): ProviderDraft[] {
  return officialProviders.map((vendor) => {
    const existing = drafts.find((draft) => isOfficialProviderDraft(draft, vendor.code))
    if (existing) return existing
    return {
      id: `${vendor.code}-official`,
      name: `${officialProviderDisplayName(vendor.label)} Official`,
      provider_type: inferProviderType(vendor.code),
      base_url: vendor.baseUrl,
      api_key: "",
      isTesting: false,
    }
  })
}

export function thirdPartyProviderDrafts(drafts: ProviderDraft[]): ProviderDraft[] {
  return drafts.filter((draft) => inferProviderKind(draft) === "third-party")
}

export function notableProviderKeyForDraft(draft: ProviderDraft): string {
  const officialCode = officialProviderCodes.find((code) => isOfficialProviderDraft(draft, code))
  if (officialCode) return officialCode
  return draft.id.split(/[-_]/, 1)[0].toLowerCase()
}

export function shouldShowManualModelPanel(
  draft: ProviderDraft,
  persisted: CredentialsState["providers"][number] | null,
): boolean {
  return (
    inferProviderKind(draft) === "official" ||
    persisted?.last_test_status === "ok" ||
    (persisted?.available_models?.length ?? 0) > 0
  )
}

function isOfficialProviderDraft(draft: ProviderDraft, providerCode: string): boolean {
  const normalizedId = draft.id.toLowerCase()
  const normalizedName = draft.name.toLowerCase()
  const vendor = officialProviders.find((item) => item.code === providerCode)
  const label = vendor ? officialProviderDisplayName(vendor.label).toLowerCase() : providerCode
  return (
    normalizedId === providerCode ||
    normalizedId.startsWith(`${providerCode}-`) ||
    normalizedId.startsWith(`${providerCode}_`) ||
    (normalizedName.includes(label) && normalizedName.includes("official"))
  )
}

function officialProviderDisplayName(label: string): string {
  return label.replace(/\s*\(.+\)\s*$/, "")
}

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

export function SettingsPageContent({
  activeTab,
  credentials,
  credentialsLoading,
  drafts,
  saveStatus,
  rolesData,
  selectedRole,
  rolesDirty,
  rolesError,
  appSettings,
  onClose,
  onTabChange,
  onProviderFieldChange,
  onTestProvider,
  onDeleteProvider,
  onAddProvider,
  onProviderModelsUpdated,
  onSelectedRoleChange,
  onRolesDataChange,
  onSaveRoles,
}: SettingsPageContentProps) {
  return (
    <div className="flex size-full flex-col bg-background">
      <div className="flex h-11 shrink-0 items-center justify-between gap-2 border-b border-border pl-4 pr-2">
        <span className="text-sm font-semibold text-foreground">Settings</span>
        <Button variant="ghost" size="icon" onClick={onClose} aria-label="Close settings" className="size-7">
          <X className="size-4" />
        </Button>
      </div>

      <div className="flex min-h-0 flex-1">
        <nav className="w-56 shrink-0 border-r border-border bg-sidebar/40 px-2 py-4">
          <NavButton active={activeTab === "general"} icon={<Settings />} onClick={() => onTabChange("general")}>
            General
          </NavButton>
          <NavButton active={activeTab === "api_keys"} icon={<KeyRound />} onClick={() => onTabChange("api_keys")}>
            API Keys
          </NavButton>
          <NavButton active={activeTab === "llm_roles"} icon={<Plug />} onClick={() => onTabChange("llm_roles")}>
            LLM Roles
          </NavButton>
        </nav>

        <ScrollArea className="flex-1">
          <div className="max-w-3xl px-10 py-8">
            {activeTab === "general" ? <GeneralTab appSettings={appSettings} /> : null}
            {activeTab === "api_keys" ? (
              <ApiKeysTab
                credentials={credentials}
                credentialsLoading={credentialsLoading}
                drafts={drafts}
                saveStatus={saveStatus}
                onProviderFieldChange={onProviderFieldChange}
                onTestProvider={onTestProvider}
                onDeleteProvider={onDeleteProvider}
                onAddProvider={onAddProvider}
                onProviderModelsUpdated={onProviderModelsUpdated}
              />
            ) : null}
            {activeTab === "llm_roles" ? (
              <LlmRolesTab
                data={rolesData}
                credentials={credentials}
                selectedRole={selectedRole}
                dirty={rolesDirty}
                error={rolesError}
                onSelectedRoleChange={onSelectedRoleChange}
                onChange={onRolesDataChange}
                onSave={onSaveRoles}
              />
            ) : null}
          </div>
        </ScrollArea>
      </div>
    </div>
  )
}

function NavButton({
  active,
  icon,
  children,
  onClick,
}: {
  active: boolean
  icon: ReactNode
  children: ReactNode
  onClick: () => void
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "flex w-full items-center gap-2.5 rounded-sm px-2.5 py-1.5 text-xs transition-colors [&_svg]:size-3.5",
        active ? "bg-sidebar-accent text-foreground" : "text-muted-foreground hover:bg-sidebar-accent/60 hover:text-foreground",
      )}
    >
      {icon}
      {children}
    </button>
  )
}

function SectionTitle({ title, description, trailing }: { title: string; description?: string; trailing?: ReactNode }) {
  return (
    <div className="mb-6 flex items-start justify-between gap-3">
      <div className="min-w-0">
        <h2 className="text-base font-semibold text-foreground">{title}</h2>
        {description ? <p className="mt-1 text-xs text-muted-foreground">{description}</p> : null}
      </div>
      {trailing ? <div className="shrink-0">{trailing}</div> : null}
    </div>
  )
}

function SettingRow({
  label,
  description,
  control,
}: {
  label: string
  description?: string
  control: ReactNode
}) {
  return (
    <div className="flex items-start justify-between gap-6 py-3">
      <div className="min-w-0 flex-1">
        <Label className="text-xs font-medium text-foreground">{label}</Label>
        {description ? <p className="mt-0.5 text-[11px] leading-relaxed text-muted-foreground">{description}</p> : null}
      </div>
      <div className="shrink-0">{control}</div>
    </div>
  )
}

function GeneralTab({ appSettings }: Pick<SettingsPageContentProps, "appSettings">) {
  return (
    <div>
      <SectionTitle title="General" description="Application defaults and collaboration identity." />
      <SettingRow
        label="Studio User ID"
        description="Used as the local Git author and team owner."
        control={
          <div className="flex items-center gap-2">
            <Input
              value={appSettings.userId}
              onChange={(event) => appSettings.setUserId(event.target.value)}
              placeholder="your-username"
              className="h-8 w-56 text-xs"
              aria-label="Studio User ID"
            />
            <Button type="button" size="sm" onClick={() => void appSettings.save()} disabled={appSettings.isLoading} className="h-7 text-xs">
              Save
            </Button>
          </div>
        }
      />
      <SettingRow
        label="Gitea Host"
        description="Private Gitea host used for team collaboration."
        control={
          <div className="flex items-center gap-2">
            <Input
              value={appSettings.giteaHost}
              onChange={(event) => appSettings.setGiteaHost(event.target.value)}
              placeholder="https://gitea.example.com"
              className="h-8 w-56 text-xs"
              aria-label="Gitea Host"
            />
            <Button type="button" size="sm" onClick={() => void appSettings.save()} disabled={appSettings.isLoading} className="h-7 text-xs">
              Save
            </Button>
          </div>
        }
      />
    </div>
  )
}

function SaveStatusBadge({ status }: { status: SaveStatus }) {
  if (status === "idle") return null
  if (status === "pending") {
    return (
      <Badge variant="outline" className="gap-1 text-[10px] font-normal text-muted-foreground">
        <Loader2 className="size-3 animate-spin" />
        Pending
      </Badge>
    )
  }
  if (status === "saving") {
    return (
      <Badge variant="outline" className="gap-1 text-[10px] font-normal text-muted-foreground">
        <Loader2 className="size-3 animate-spin" />
        Saving
      </Badge>
    )
  }
  if (status === "saved") {
    return (
      <Badge variant="outline" className="gap-1 text-[10px] font-normal">
        <Check className="size-3" />
        Saved
      </Badge>
    )
  }
  // error
  return (
    <Badge variant="outline" className="gap-1 text-[10px] font-normal">
      <TriangleAlert className="size-3" />
      Save failed
    </Badge>
  )
}

function ApiKeysTab({
  credentials,
  credentialsLoading,
  drafts,
  saveStatus,
  onProviderFieldChange,
  onTestProvider,
  onDeleteProvider,
  onAddProvider,
  onProviderModelsUpdated,
}: Pick<
  SettingsPageContentProps,
  | "credentials"
  | "credentialsLoading"
  | "drafts"
  | "saveStatus"
  | "onProviderFieldChange"
  | "onTestProvider"
  | "onDeleteProvider"
  | "onAddProvider"
  | "onProviderModelsUpdated"
>) {
  const [showAddForm, setShowAddForm] = useState(false)
  const persistedById = useMemo(
    () => Object.fromEntries(credentials.providers.map((provider) => [provider.id, provider])),
    [credentials.providers],
  )
  const officialDrafts = useMemo(() => officialProviderDrafts(drafts), [drafts])
  const thirdPartyDrafts = useMemo(() => thirdPartyProviderDrafts(drafts), [drafts])

  return (
    <div>
      <SectionTitle
        title="API Keys"
        description="Local LLM provider credentials used by Studio runtime. Changes auto-save."
        trailing={<SaveStatusBadge status={saveStatus} />}
      />
      <div className="space-y-4" data-testid="api-keys-list">
        {credentialsLoading ? (
          <ProviderListSkeleton count={5} />
        ) : (
          <>
            <section className="space-y-3" aria-label="Official Providers">
              <h3 className="text-sm font-medium text-foreground">Official Providers</h3>
              {officialDrafts.map((draft) => {
                const persisted = persistedById[draft.id] ?? null
                return (
                  <ProviderCard
                    key={draft.id}
                    draft={draft}
                    persisted={persisted}
                    onFieldChange={(patch) => onProviderFieldChange(draft.id, { ...draft, ...patch })}
                    onTest={() => onTestProvider(draft.id)}
                    onDelete={() => onDeleteProvider(draft.id)}
                    providerKind="official"
                    showManualModelPanel={shouldShowManualModelPanel(draft, persisted)}
                    notableProviderKey={notableProviderKeyForDraft(draft)}
                    onModelsUpdated={(models) => onProviderModelsUpdated(draft.id, models)}
                  />
                )
              })}
            </section>

            <section className="space-y-3 pt-4" aria-label="Third-party Providers">
              <div className="flex items-center justify-between gap-3">
                <h3 className="text-sm font-medium text-foreground">Third-party Providers</h3>
                {!showAddForm ? (
                  <Button type="button" variant="outline" onClick={() => setShowAddForm(true)} className="gap-1">
                    <Plus className="size-3.5" />
                    Add Provider
                  </Button>
                ) : null}
              </div>
              {thirdPartyDrafts.length > 0 ? (
                thirdPartyDrafts.map((draft) => {
                  const persisted = persistedById[draft.id] ?? null
                  return (
                    <ProviderCard
                      key={draft.id}
                      draft={draft}
                      persisted={persisted}
                      onFieldChange={(patch) => onProviderFieldChange(draft.id, patch)}
                      onTest={() => onTestProvider(draft.id)}
                      onDelete={() => onDeleteProvider(draft.id)}
                      providerKind="third-party"
                      showManualModelPanel={shouldShowManualModelPanel(draft, persisted)}
                      notableProviderKey={notableProviderKeyForDraft(draft)}
                      onModelsUpdated={(models) => onProviderModelsUpdated(draft.id, models)}
                    />
                  )
                })
              ) : !showAddForm ? (
                <div className="flex flex-col items-center gap-3 rounded-md border border-dashed border-border/60 bg-muted/10 px-4 py-8 text-center">
                  <p className="text-xs text-muted-foreground">No third-party providers configured.</p>
                </div>
              ) : null}
              {showAddForm ? (
                <AddProviderForm
                  onSubmit={async (data) => {
                    await onAddProvider(data)
                    setShowAddForm(false)
                  }}
                  onCancel={() => setShowAddForm(false)}
                />
              ) : null}
            </section>
          </>
        )}
      </div>
    </div>
  )
}

export function LlmRolesTab({
  data,
  credentials,
  selectedRole,
  dirty,
  error,
  onSelectedRoleChange,
  onChange,
  onSave,
}: {
  data: RolesData | null
  credentials: CredentialsState
  selectedRole: string
  dirty: boolean
  error: string | null
  onSelectedRoleChange: (roleName: string) => void
  onChange: (next: RolesData) => void
  onSave: () => void
}) {
  const credentialsByCode = useMemo(
    () => Object.fromEntries(credentials.providers.map((provider) => [provider.id, provider])),
    [credentials.providers],
  )

  if (!data) {
    return (
      <div>
        <SectionTitle title="LLM Roles" description="Edit active models and fallback order." />
        <div className="rounded-md border border-border p-6 text-xs text-muted-foreground">
          Loading roles...
        </div>
      </div>
    )
  }

  const roleNames = visibleRoleNames(data)
  const roleName = selectedRole && data.roles[selectedRole] ? selectedRole : roleNames[0] ?? ""
  const role = data.roles[roleName]
  const modelCodes = role ? Object.keys(role.models) : []

  function modelAvailability(modelCode: string): ModelAvailability {
    const providers = data!.roles[roleName].models[modelCode].providers
    return getModelAvailability(providers, credentialsByCode)
  }

  function availabilityPrefix(availability: ModelAvailability): string {
    if (availability === "unavailable") return "Unavailable · "
    if (availability === "key_only") return "Untested · "
    return ""
  }

  return (
    <div>
      <SectionTitle title="LLM Roles" description="Edit active model and fallback order." />
      <div className="mb-4 flex flex-wrap items-end gap-3 rounded-sm border border-border bg-card/40 p-3">
        <div>
          <Label htmlFor="llm-role-select" className="text-[11px] text-muted-foreground">Role</Label>
          <select
            id="llm-role-select"
            value={roleName}
            onChange={(event) => onSelectedRoleChange(event.target.value)}
            className="mt-1 h-8 rounded-md border border-input bg-background px-2 text-xs"
            aria-label="Role"
          >
            {roleNames.map((name) => (
              <option key={name} value={name}>{name}</option>
            ))}
          </select>
        </div>
        {role ? (
          <>
            <div>
              <Label htmlFor="active-model-select" className="text-[11px] text-muted-foreground">active_model</Label>
              <select
                id="active-model-select"
                value={role.active_model}
                onChange={(event) => onChange(updateActiveModel(data, roleName, event.target.value))}
                className="mt-1 h-8 rounded-md border border-input bg-background px-2 text-xs"
                aria-label="Active model"
              >
                {modelCodes.map((modelCode) => {
                  const availability = modelAvailability(modelCode)
                  return (
                    <option
                      key={modelCode}
                      value={modelCode}
                      disabled={availability === "unavailable"}
                      data-availability={availability}
                    >
                      {`${availabilityPrefix(availability)}${modelCode}`}
                    </option>
                  )
                })}
              </select>
            </div>
            <label className="flex h-8 items-center gap-2 text-xs">
              <input
                type="checkbox"
                checked={role.model_fallback}
                onChange={(event) => onChange(toggleModelFallback(data, roleName, event.target.checked))}
                aria-label="Model fallback"
              />
              model_fallback
            </label>
          </>
        ) : null}
        <div className="ml-auto flex items-center gap-2">
          {dirty ? <Badge variant="outline">Dirty</Badge> : null}
          <Button type="button" size="sm" onClick={onSave} disabled={!role || !dirty}>
            Save
          </Button>
        </div>
      </div>
      {error ? <div className="mb-3 text-xs text-destructive">Validation failed: {error}</div> : null}
      {role ? (
        <div className="space-y-3">
          {modelCodes.map((modelCode, modelIndex) => (
            <RoleModelCard
              key={modelCode}
              data={data}
              roleName={roleName}
              modelCode={modelCode}
              modelIndex={modelIndex}
              modelCount={modelCodes.length}
              active={role.active_model === modelCode}
              availability={modelAvailability(modelCode)}
              onChange={onChange}
            />
          ))}
          <TooltipProvider>
            <Tooltip>
              <TooltipTrigger asChild>
                <Button type="button" variant="outline" size="sm" disabled title={DISABLED_ROLE_EDITING}>
                  + Add Model
                </Button>
              </TooltipTrigger>
              <TooltipContent>{DISABLED_ROLE_EDITING}</TooltipContent>
            </Tooltip>
          </TooltipProvider>
        </div>
      ) : null}
    </div>
  )
}

function RoleModelCard({
  data,
  roleName,
  modelCode,
  modelIndex,
  modelCount,
  active,
  availability,
  onChange,
}: {
  data: RolesData
  roleName: string
  modelCode: string
  modelIndex: number
  modelCount: number
  active: boolean
  availability: ModelAvailability
  onChange: (next: RolesData) => void
}) {
  const role = data.roles[roleName]
  const providers = role.models[modelCode].providers
  const modelName = data.models[modelCode]?.name ?? modelCode
  return (
    <div className="rounded-sm border border-border bg-card/40 p-3" data-availability={availability}>
      <div className="mb-3 flex items-start justify-between gap-3">
        <div>
          <div className="flex items-center gap-2 text-xs font-semibold">
            {modelCode}
            {active ? <Badge variant="outline">active</Badge> : null}
            {availability === "unavailable" ? (
              <Badge variant="outline" className="border-red-800/40 bg-red-950/40 text-red-300">
                <TriangleAlert className="size-3" />
                Unavailable
              </Badge>
            ) : null}
            {availability === "key_only" ? (
              <Badge variant="outline" className="text-muted-foreground">
                Untested
              </Badge>
            ) : null}
          </div>
          <div className="mt-0.5 text-[11px] text-muted-foreground">{modelName}</div>
        </div>
        <div className="flex items-center gap-1">
          <Button type="button" variant="ghost" size="sm" disabled={modelIndex === 0} onClick={() => onChange(moveModelInRole(data, roleName, modelCode, -1))}>
            Move Up
          </Button>
          <Button type="button" variant="ghost" size="sm" disabled={modelIndex === modelCount - 1} onClick={() => onChange(moveModelInRole(data, roleName, modelCode, 1))}>
            Move Down
          </Button>
          <Button type="button" variant="ghost" size="sm" onClick={() => onChange(removeModelFromRole(data, roleName, modelCode))}>
            Remove
          </Button>
        </div>
      </div>
      <div className="mb-2 text-[11px] font-medium text-muted-foreground">
        Provider chain
      </div>
      <div className="space-y-1.5">
        {providers.map((providerCode, index) => (
          <div key={`${providerCode}-${index}`} className="flex items-center justify-between gap-2 rounded-sm bg-muted/30 px-2 py-1.5">
            <div className="text-xs">
              <span className="text-muted-foreground">{index + 1}. </span>
              {providerCode}
              <span className="ml-2 text-[11px] text-muted-foreground">{data.providers[providerCode]?.name ?? ""}</span>
            </div>
            <div className="flex items-center gap-1">
              <Button type="button" variant="ghost" size="icon-xs" aria-label={`Move ${providerCode} up`} disabled={index === 0} onClick={() => onChange(moveProviderInRole(data, roleName, modelCode, index, -1))}>
                <ArrowUp className="size-3" />
              </Button>
              <Button type="button" variant="ghost" size="icon-xs" aria-label={`Move ${providerCode} down`} disabled={index === providers.length - 1} onClick={() => onChange(moveProviderInRole(data, roleName, modelCode, index, 1))}>
                <ArrowDown className="size-3" />
              </Button>
              <Button type="button" variant="ghost" size="icon-xs" aria-label={`Remove ${providerCode}`} onClick={() => onChange(removeProviderFromRole(data, roleName, modelCode, index))}>
                <X className="size-3" />
              </Button>
            </div>
          </div>
        ))}
      </div>
      <TooltipProvider>
        <Tooltip>
          <TooltipTrigger asChild>
            <Button type="button" variant="ghost" size="sm" disabled title={DISABLED_ROLE_EDITING} className="mt-2">
              + Add Provider
            </Button>
          </TooltipTrigger>
          <TooltipContent>{DISABLED_ROLE_EDITING}</TooltipContent>
        </Tooltip>
      </TooltipProvider>
    </div>
  )
}
