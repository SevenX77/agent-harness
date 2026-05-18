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
  type ProviderType,
  type RolesData,
} from "../../api/llm"
import { ProviderRow, type ProviderRowDraft } from "./ProviderRow"

type SettingsTab = "general" | "api_keys" | "llm_roles"

const emptyCredentials: CredentialsState = { providers: [] }
const DISABLED_ROLE_EDITING = "Adding new model/provider coming in v2.5"

/**
 * A provider is "YAML-owned" iff the backend supplied a `name` for it. Backend
 * fills `name` only when the provider exists in `llm_roles.yaml` (the path
 * `include_metadata=true` hits in `_credential_metadata_view`). YAML-owned
 * providers can edit api_key + base_url but not title / provider_type /
 * vendor_hint, and the row hides its Delete button.
 */
export function isYamlOwned(persisted: { name?: string } | null | undefined): boolean {
  return Boolean(persisted?.name)
}

/** What the LLM Roles tab knows about a single provider. */
interface ProviderAvailabilityInput {
  has_key: boolean
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
    if (!credential?.has_key) continue
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
  drafts: ProviderRowDraft[]
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
  onProviderFieldChange: (providerCode: string, patch: Partial<ProviderRowDraft>) => void
  onTestProvider: (providerCode: string) => void
  onDeleteProvider: (providerCode: string) => void
  onAddProvider: () => void
  onSelectedRoleChange: (roleName: string) => void
  onRolesDataChange: (next: RolesData) => void
  onSaveRoles: () => void
}

/** Build a draft list from the server `CredentialsState` snapshot. */
export function draftsFromCredentials(credentials: CredentialsState): ProviderRowDraft[] {
  return credentials.providers.map((provider) => ({
    provider_code: provider.provider_code,
    title: provider.title ?? "",
    provider_type: (provider.provider_type ?? "openai_compatible") as ProviderType,
    base_url: provider.base_url ?? "",
    vendor_hint: provider.vendor_hint ?? "",
    api_key: "",
    hasSavedKey: provider.has_key,
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

function newProviderCode(): string {
  // crypto.randomUUID short-form: first segment + last segment → stable in JSDOM.
  const uuid = (globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random().toString(36).slice(2)}`).toString()
  return `CUSTOM_${uuid.replace(/-/g, "").slice(0, 8).toUpperCase()}`
}

export function SettingsPage({ onClose }: SettingsPageProps) {
  const appSettings = useAppSettings()
  const [activeTab, setActiveTab] = useState<SettingsTab>("general")
  const [credentials, setCredentials] = useState<CredentialsState>(emptyCredentials)
  const [drafts, setDrafts] = useState<ProviderRowDraft[]>([])
  const [rolesData, setRolesData] = useState<RolesData | null>(null)
  const [selectedRole, setSelectedRole] = useState("copilot_chat")
  const [rolesDirty, setRolesDirty] = useState(false)
  const [rolesError, setRolesError] = useState<string | null>(null)

  // Keep a ref of the most recent draft list so the debounced save can read it
  // at fire time (avoids re-binding the timer on every keystroke).
  const draftsRef = useRef<ProviderRowDraft[]>(drafts)
  draftsRef.current = drafts

  const handleSaved = useCallback((next: CredentialsState) => {
    setCredentials(next)
    // Re-sync `hasSavedKey` per provider, but preserve any unsent typed key
    // (user might still be editing while a previous batch flushed).
    setDrafts((current) => current.map((draft) => {
      const persisted = next.providers.find((provider) => provider.provider_code === draft.provider_code)
      if (!persisted) return draft
      return {
        ...draft,
        hasSavedKey: persisted.has_key,
        // After a successful save the typed key is now on the server — clear
        // it locally so the placeholder shows "saved" again.
        api_key: "",
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
      })
      .catch((error) => {
        if (cancelled) return
        const message = error instanceof Error ? error.message : "凭据加载失败"
        toast.error(`API Keys 加载失败：${message}`)
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

  function updateProviderField(providerCode: string, patch: Partial<ProviderRowDraft>) {
    setDrafts((current) => current.map((draft) => (
      draft.provider_code === providerCode ? { ...draft, ...patch } : draft
    )))
    scheduleSave()
  }

  function setProviderTesting(providerCode: string, isTesting: boolean) {
    setDrafts((current) => current.map((draft) => (
      draft.provider_code === providerCode ? { ...draft, isTesting } : draft
    )))
  }

  function addProvider() {
    const provider_code = newProviderCode()
    const draft: ProviderRowDraft = {
      provider_code,
      title: "",
      provider_type: "openai_compatible",
      base_url: "",
      vendor_hint: "",
      api_key: "",
      hasSavedKey: false,
      isTesting: false,
    }
    setDrafts((current) => [...current, draft])
    scheduleSave()
  }

  function deleteProvider(providerCode: string) {
    // YAML-owned providers cannot be deleted from the UI; their identity is
    // pinned by llm_roles.yaml.
    const persisted = credentials.providers.find((p) => p.provider_code === providerCode)
    if (isYamlOwned(persisted)) return
    setDrafts((current) => current.filter((draft) => draft.provider_code !== providerCode))
    scheduleSave()
  }

  async function runProviderTest(providerCode: string) {
    const draft = draftsRef.current.find((d) => d.provider_code === providerCode)
    if (!draft) return

    setProviderTesting(providerCode, true)
    const toastId = `test-${providerCode}`
    toast.loading(`正在测试 ${draft.title || providerCode}…`, { id: toastId })

    try {
      const response = await testProvider({
        provider_code: draft.provider_code,
        provider_type: draft.provider_type,
        api_key: draft.api_key.trim(),
        base_url: draft.base_url || undefined,
      })

      // F5: splice the persisted Test outcome into local credentials so the
      // ProviderRow's `persisted` prop reflects it without a GET round-trip.
      setCredentials((current) => ({
        providers: current.providers.map((provider) => {
          if (provider.provider_code !== providerCode) return provider
          return {
            ...provider,
            last_test_status: response.status === "missing_api_key" ? "untested" : response.status,
            last_test_at: new Date().toISOString(),
            last_test_message: response.message ?? "",
            last_error_code: response.error_code ?? "",
            available_models: response.available_models ?? provider.available_models ?? [],
          }
        }),
      }))

      if (response.status === "ok") {
        const latency = response.latency_ms ? `${response.latency_ms}ms` : ""
        const modelCount = response.available_models?.length ?? 0
        const detail = [latency, modelCount > 0 ? `${modelCount} 个模型` : ""].filter(Boolean).join(" · ")
        toast.success(detail ? `连接正常（${detail}）` : "连接正常", { id: toastId })
      } else {
        toast.error(composeTestErrorMessage(response.status, response.error_code, response.message), { id: toastId })
      }
    } catch (error) {
      const message = error instanceof Error ? error.message : "未知错误"
      toast.error(`测试调用失败：${message}`, { id: toastId })
    } finally {
      setProviderTesting(providerCode, false)
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
      onAddProvider={addProvider}
      onSelectedRoleChange={setSelectedRole}
      onRolesDataChange={updateRolesData}
      onSaveRoles={() => void saveRoles()}
    />
  )
}

export function SettingsPageContent({
  activeTab,
  credentials,
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
                drafts={drafts}
                saveStatus={saveStatus}
                onProviderFieldChange={onProviderFieldChange}
                onTestProvider={onTestProvider}
                onDeleteProvider={onDeleteProvider}
                onAddProvider={onAddProvider}
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
        准备保存…
      </Badge>
    )
  }
  if (status === "saving") {
    return (
      <Badge variant="outline" className="gap-1 text-[10px] font-normal text-muted-foreground">
        <Loader2 className="size-3 animate-spin" />
        保存中
      </Badge>
    )
  }
  if (status === "saved") {
    return (
      <Badge variant="outline" className="gap-1 text-[10px] font-normal text-emerald-300">
        <Check className="size-3" />
        已保存
      </Badge>
    )
  }
  // error
  return (
    <Badge variant="outline" className="gap-1 text-[10px] font-normal text-red-300">
      <TriangleAlert className="size-3" />
      保存失败
    </Badge>
  )
}

function ApiKeysTab({
  credentials,
  drafts,
  saveStatus,
  onProviderFieldChange,
  onTestProvider,
  onDeleteProvider,
  onAddProvider,
}: Pick<
  SettingsPageContentProps,
  "credentials" | "drafts" | "saveStatus" | "onProviderFieldChange" | "onTestProvider" | "onDeleteProvider" | "onAddProvider"
>) {
  const persistedByCode = useMemo(
    () => Object.fromEntries(credentials.providers.map((provider) => [provider.provider_code, provider])),
    [credentials.providers],
  )

  return (
    <div>
      <SectionTitle
        title="API Keys（本地）"
        description="Studio runtime 使用的 LLM 服务商凭据。改动会在 300ms 内自动保存。"
        trailing={<SaveStatusBadge status={saveStatus} />}
      />
      <div className="space-y-3" data-testid="api-keys-list">
        {drafts.map((draft) => {
          const persisted = persistedByCode[draft.provider_code] ?? null
          return (
            <ProviderRow
              key={draft.provider_code}
              draft={draft}
              persisted={persisted}
              identityEditable={!isYamlOwned(persisted)}
              onFieldChange={(patch) => onProviderFieldChange(draft.provider_code, patch)}
              onTest={() => onTestProvider(draft.provider_code)}
              onDelete={() => onDeleteProvider(draft.provider_code)}
            />
          )
        })}
        {drafts.length === 0 ? (
          <div className="flex flex-col items-center gap-3 rounded-md border border-dashed border-border/60 bg-muted/10 px-4 py-10 text-center">
            <div className="text-xs text-muted-foreground">尚未添加任何 Provider</div>
            <Button type="button" variant="default" onClick={onAddProvider} className="gap-1">
              <Plus className="size-3.5" />
              新增第一个 Provider
            </Button>
          </div>
        ) : null}
      </div>
      {drafts.length === 0 ? null : (
        <div className="mt-4 flex justify-start">
          <Button type="button" variant="outline" onClick={onAddProvider} className="gap-1">
            <Plus className="size-3.5" />
            新增 Provider
          </Button>
        </div>
      )}
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
    () => Object.fromEntries(credentials.providers.map((provider) => [provider.provider_code, provider])),
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
    if (availability === "unavailable") return "⚠️ 不可用 · "
    if (availability === "key_only") return "● 未测试 · "
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
                不可用
              </Badge>
            ) : null}
            {availability === "key_only" ? (
              <Badge variant="outline" className="text-muted-foreground">
                未测试
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
