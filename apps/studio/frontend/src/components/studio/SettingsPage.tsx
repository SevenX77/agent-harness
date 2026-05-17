import { useEffect, useMemo, useState, type ReactNode } from "react"
import { ArrowDown, ArrowUp, CheckCircle2, ChevronDown, Eye, EyeOff, KeyRound, Plug, Settings, Trash2, X, XCircle } from "lucide-react"
import { toast } from "sonner"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Spinner } from "@/components/ui/spinner"
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip"
import { useAppSettings } from "@/hooks/useAppSettings"
import { cn } from "@/lib/utils"
import {
  getCredentials,
  getRoles,
  putCredentials,
  putRoles,
  testProvider,
  type CredentialProviderState,
  type CredentialsState,
  type ProviderTestResponse,
  type RolesData,
} from "../../api/llm"

type SettingsTab = "general" | "api_keys" | "llm_roles"
type VendorId = "Anthropic" | "DeepSeek" | "Gemini" | "OpenAI" | "WaveSpeed"
type TestState =
  | { status: "idle" }
  | { status: "testing" }
  | { status: "ok"; result: ProviderTestResponse }
  | { status: "error"; result: ProviderTestResponse }

export interface VendorEntry {
  id: VendorId
  label: string
  officialProviderCode: string | null
  customProviderCodes: string[]
}

export interface CredentialDraft {
  apiKey: string
  visible: boolean
}

type Drafts = Record<string, CredentialDraft>
type TestStates = Record<string, TestState>
type DirtyProviders = Partial<Record<string, boolean>>
type VendorOpenState = Record<VendorId, boolean>

export const VENDORS: VendorEntry[] = [
  { id: "Anthropic", label: "Anthropic", officialProviderCode: null, customProviderCodes: ["OC_CL_ANT", "JK_CL_ANT"] },
  { id: "DeepSeek", label: "DeepSeek", officialProviderCode: "DS", customProviderCodes: ["OC_DS"] },
  { id: "Gemini", label: "Gemini", officialProviderCode: "GM_OFF", customProviderCodes: ["OC_GM"] },
  { id: "OpenAI", label: "OpenAI", officialProviderCode: null, customProviderCodes: [] },
  { id: "WaveSpeed", label: "WaveSpeed", officialProviderCode: "WS_LLM", customProviderCodes: [] },
]

const emptyCredentials: CredentialsState = { providers: [] }
const DISABLED_PROVIDER_EDITING = "Custom provider editing coming in v2.5"
const DISABLED_ROLE_EDITING = "Adding new model/provider coming in v2.5"

interface SettingsPageProps {
  onClose: () => void
}

interface SettingsPageContentProps {
  activeTab: SettingsTab
  credentials: CredentialsState
  drafts: Drafts
  testStates: TestStates
  vendorOpen: VendorOpenState
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
  onDraftChange: (providerCode: string, apiKey: string) => void
  onToggleKeyVisible: (providerCode: string) => void
  onToggleVendor: (vendor: VendorId, open: boolean) => void
  onTestProvider: (providerCode: string) => void
  onSelectedRoleChange: (roleName: string) => void
  onRolesDataChange: (next: RolesData) => void
  onSaveRoles: () => void
}

export function draftsFromCredentials(credentials: CredentialsState): Drafts {
  return Object.fromEntries(
    credentials.providers.map((provider) => [
      provider.provider_code,
      { apiKey: "", visible: false },
    ]),
  )
}

export function initialTestStates(credentials: CredentialsState): TestStates {
  return Object.fromEntries(
    credentials.providers.map((provider) => [provider.provider_code, { status: "idle" as const }]),
  )
}

export function defaultVendorOpen(): VendorOpenState {
  return Object.fromEntries(VENDORS.map((vendor) => [vendor.id, true])) as VendorOpenState
}

export function providerByCode(credentials: CredentialsState): Record<string, CredentialProviderState> {
  return Object.fromEntries(credentials.providers.map((provider) => [provider.provider_code, provider]))
}

export function credentialUpdateFor(providerCode: string, draft: CredentialDraft) {
  return [{ provider_code: providerCode, api_key: draft.apiKey }]
}

export function testRequestFor(
  provider: CredentialProviderState,
  draft: CredentialDraft,
) {
  if (!provider.provider_type) return null
  return {
    provider_code: provider.provider_code,
    provider_type: provider.provider_type,
    api_key: draft.apiKey.trim(),
    base_url: provider.base_url || undefined,
  }
}

export function preserveTestStateOnInputChange(testStates: TestStates): TestStates {
  return testStates
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

export function SettingsPage({ onClose }: SettingsPageProps) {
  const appSettings = useAppSettings()
  const [activeTab, setActiveTab] = useState<SettingsTab>("general")
  const [credentials, setCredentials] = useState<CredentialsState>(emptyCredentials)
  const [drafts, setDrafts] = useState<Drafts>({})
  const [testStates, setTestStates] = useState<TestStates>({})
  const [dirtyProviders, setDirtyProviders] = useState<DirtyProviders>({})
  const [vendorOpen, setVendorOpen] = useState<VendorOpenState>(() => defaultVendorOpen())
  const [rolesData, setRolesData] = useState<RolesData | null>(null)
  const [selectedRole, setSelectedRole] = useState("copilot_chat")
  const [rolesDirty, setRolesDirty] = useState(false)
  const [rolesError, setRolesError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    getCredentials()
      .then((next) => {
        if (cancelled) return
        setCredentials(next)
        setDrafts(draftsFromCredentials(next))
        setTestStates(initialTestStates(next))
      })
      .catch(() => {
        if (!cancelled) setTestStates({ _load: { status: "error", result: { status: "network_error", message: "Credentials unavailable" } } })
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

  function updateDraft(providerCode: string, apiKey: string) {
    setDrafts((current) => ({
      ...current,
      [providerCode]: { apiKey, visible: current[providerCode]?.visible ?? false },
    }))
    setTestStates(preserveTestStateOnInputChange)
    setDirtyProviders((current) => ({ ...current, [providerCode]: true }))
  }

  async function saveProvider(providerCode: string) {
    const draft = drafts[providerCode]
    if (!draft) return
    const next = await putCredentials(credentialUpdateFor(providerCode, draft))
    setCredentials(next)
    setDirtyProviders((current) => ({ ...current, [providerCode]: false }))
  }

  async function runProviderTest(providerCode: string) {
    const provider = providerByCode(credentials)[providerCode]
    const draft = drafts[providerCode]
    if (!provider || !draft) return
    const request = testRequestFor(provider, draft)
    if (!request) return

    setTestStates((current) => ({ ...current, [providerCode]: { status: "testing" } }))
    const result = await testProvider(request)
    setTestStates((current) => ({
      ...current,
      [providerCode]: result.status === "ok" ? { status: "ok", result } : { status: "error", result },
    }))
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

  useEffect(() => {
    const providerCodes = Object.keys(dirtyProviders).filter((providerCode) => dirtyProviders[providerCode])
    if (providerCodes.length === 0) return
    const timer = window.setTimeout(() => {
      providerCodes.forEach((providerCode) => void saveProvider(providerCode))
    }, 650)
    return () => window.clearTimeout(timer)
  }, [dirtyProviders, drafts])

  return (
    <SettingsPageContent
      activeTab={activeTab}
      credentials={credentials}
      drafts={drafts}
      testStates={testStates}
      vendorOpen={vendorOpen}
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
      onDraftChange={updateDraft}
      onToggleKeyVisible={(providerCode) => {
        setDrafts((current) => ({
          ...current,
          [providerCode]: {
            apiKey: current[providerCode]?.apiKey ?? "",
            visible: !current[providerCode]?.visible,
          },
        }))
      }}
      onToggleVendor={(vendor, open) => setVendorOpen((current) => ({ ...current, [vendor]: open }))}
      onTestProvider={(providerCode) => void runProviderTest(providerCode)}
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
  testStates,
  vendorOpen,
  rolesData,
  selectedRole,
  rolesDirty,
  rolesError,
  appSettings,
  onClose,
  onTabChange,
  onDraftChange,
  onToggleKeyVisible,
  onToggleVendor,
  onTestProvider,
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
                testStates={testStates}
                vendorOpen={vendorOpen}
                onDraftChange={onDraftChange}
                onToggleKeyVisible={onToggleKeyVisible}
                onToggleVendor={onToggleVendor}
                onTestProvider={onTestProvider}
              />
            ) : null}
            {activeTab === "llm_roles" ? (
              <LlmRolesTab
                data={rolesData}
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

function SectionTitle({ title, description }: { title: string; description?: string }) {
  return (
    <div className="mb-6">
      <h2 className="text-base font-semibold text-foreground">{title}</h2>
      {description ? <p className="mt-1 text-xs text-muted-foreground">{description}</p> : null}
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

function ApiKeysTab({
  credentials,
  drafts,
  testStates,
  vendorOpen,
  onDraftChange,
  onToggleKeyVisible,
  onToggleVendor,
  onTestProvider,
}: Pick<
  SettingsPageContentProps,
  "credentials" | "drafts" | "testStates" | "vendorOpen" | "onDraftChange" | "onToggleKeyVisible" | "onToggleVendor" | "onTestProvider"
>) {
  const providers = useMemo(() => providerByCode(credentials), [credentials])
  return (
    <div>
      <SectionTitle title="API Keys (Local)" description="Local provider keys used by Studio runtime." />
      <div className="space-y-4">
        {VENDORS.map((vendor) => (
          <VendorGroup
            key={vendor.id}
            vendor={vendor}
            providers={providers}
            drafts={drafts}
            testStates={testStates}
            open={vendorOpen[vendor.id]}
            onOpenChange={(open) => onToggleVendor(vendor.id, open)}
            onDraftChange={onDraftChange}
            onToggleKeyVisible={onToggleKeyVisible}
            onTestProvider={onTestProvider}
          />
        ))}
      </div>
    </div>
  )
}

function VendorGroup({
  vendor,
  providers,
  drafts,
  testStates,
  open,
  onOpenChange,
  onDraftChange,
  onToggleKeyVisible,
  onTestProvider,
}: {
  vendor: VendorEntry
  providers: Record<string, CredentialProviderState>
  drafts: Drafts
  testStates: TestStates
  open: boolean
  onOpenChange: (open: boolean) => void
  onDraftChange: (providerCode: string, apiKey: string) => void
  onToggleKeyVisible: (providerCode: string) => void
  onTestProvider: (providerCode: string) => void
}) {
  const official = vendor.officialProviderCode ? providers[vendor.officialProviderCode] : undefined
  const customProviders = vendor.customProviderCodes.map((code) => providers[code]).filter(Boolean)
  return (
    <Collapsible open={open} onOpenChange={onOpenChange}>
      <div className="border-b border-border pb-3">
        <CollapsibleTrigger asChild>
          <button type="button" className="flex w-full items-center gap-2 py-2 text-left text-sm font-semibold" aria-label={`${vendor.label} vendor group`}>
            <ChevronDown className={cn("size-4 transition-transform", open ? "" : "-rotate-90")} />
            {vendor.label}
          </button>
        </CollapsibleTrigger>
        <CollapsibleContent className="space-y-3 pl-6">
          {official ? (
            <ProviderRow
              provider={official}
              title="Official API"
              isOfficial
              draft={drafts[official.provider_code] ?? { apiKey: "", visible: false }}
              testState={testStates[official.provider_code] ?? { status: "idle" }}
              onDraftChange={onDraftChange}
              onToggleKeyVisible={onToggleKeyVisible}
              onTestProvider={onTestProvider}
            />
          ) : null}
          {customProviders.map((provider) => (
            <ProviderRow
              key={provider.provider_code}
              provider={provider}
              title={`Custom: ${provider.name ?? provider.provider_code}`}
              isOfficial={false}
              draft={drafts[provider.provider_code] ?? { apiKey: "", visible: false }}
              testState={testStates[provider.provider_code] ?? { status: "idle" }}
              onDraftChange={onDraftChange}
              onToggleKeyVisible={onToggleKeyVisible}
              onTestProvider={onTestProvider}
            />
          ))}
          <TooltipProvider>
            <Tooltip>
              <TooltipTrigger asChild>
                <Button type="button" variant="ghost" size="sm" disabled title={DISABLED_PROVIDER_EDITING}>
                  + Add Custom Provider
                </Button>
              </TooltipTrigger>
              <TooltipContent>{DISABLED_PROVIDER_EDITING}</TooltipContent>
            </Tooltip>
          </TooltipProvider>
        </CollapsibleContent>
      </div>
    </Collapsible>
  )
}

export function ProviderRow({
  provider,
  title,
  isOfficial,
  draft,
  testState,
  onDraftChange,
  onToggleKeyVisible,
  onTestProvider,
}: {
  provider: CredentialProviderState
  title: string
  isOfficial: boolean
  draft: CredentialDraft
  testState: TestState
  onDraftChange: (providerCode: string, apiKey: string) => void
  onToggleKeyVisible: (providerCode: string) => void
  onTestProvider: (providerCode: string) => void
}) {
  const canTest = Boolean(draft.apiKey.trim() && provider.provider_type)
  return (
    <div className="rounded-sm border border-border bg-card/40 p-3">
      <div className="mb-2 flex items-center justify-between gap-3">
        <div>
          <div className="text-xs font-medium text-foreground">{title}</div>
          <div className="text-[11px] text-muted-foreground">
            {provider.has_key ? "API key configured" : "No API key configured"}
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Button type="button" variant="outline" size="sm" onClick={() => onTestProvider(provider.provider_code)} disabled={testState.status === "testing" || !canTest} aria-label={`Test ${provider.provider_code}`}>
            {testState.status === "testing" ? <Spinner className="size-3" /> : null}
            Test
          </Button>
          {!isOfficial ? (
            <Button type="button" variant="ghost" size="icon-sm" disabled title={DISABLED_PROVIDER_EDITING} aria-label={`Remove ${provider.provider_code}`}>
              <Trash2 className="size-3.5" />
            </Button>
          ) : null}
        </div>
      </div>
      <div className="grid gap-2">
        <div className="relative">
          <Label htmlFor={`${provider.provider_code}-api-key`} className="text-[11px] text-muted-foreground">
            API Key
          </Label>
          <Input
            id={`${provider.provider_code}-api-key`}
            type={draft.visible ? "text" : "password"}
            autoComplete="new-password"
            value={draft.apiKey}
            onChange={(event) => onDraftChange(provider.provider_code, event.target.value)}
            placeholder={provider.has_key ? "Configured - enter to replace" : "Enter API key"}
            className="mt-1 h-8 pr-9 text-xs"
            aria-label={`${provider.provider_code} API key`}
          />
          <button
            type="button"
            onMouseDown={(event) => event.preventDefault()}
            onClick={() => onToggleKeyVisible(provider.provider_code)}
            aria-label={draft.visible ? `Hide ${provider.provider_code} API key` : `Show ${provider.provider_code} API key`}
            className="absolute right-1.5 top-[23px] flex size-7 items-center justify-center rounded-md text-muted-foreground hover:bg-muted hover:text-foreground"
          >
            {draft.visible ? <EyeOff className="size-4" /> : <Eye className="size-4" />}
          </button>
        </div>
        {!isOfficial && provider.base_url ? (
          <div>
            <Label className="text-[11px] text-muted-foreground">Base URL</Label>
            <Input value={provider.base_url} readOnly className="mt-1 h-8 text-xs" aria-label={`${provider.provider_code} Base URL`} />
          </div>
        ) : null}
        <TestMessage state={testState} />
      </div>
    </div>
  )
}

function TestMessage({ state }: { state: TestState }) {
  if (state.status === "testing") {
    return <span className="text-xs text-muted-foreground">Testing...</span>
  }
  if (state.status === "ok") {
    const latency = state.result.latency_ms ? ` (${state.result.latency_ms}ms)` : ""
    return (
      <span className="inline-flex items-center gap-1 text-xs text-emerald-600">
        <CheckCircle2 className="size-3" />
        Connected{latency}
      </span>
    )
  }
  if (state.status === "error") {
    return (
      <span className="inline-flex items-center gap-1 text-xs text-destructive">
        <XCircle className="size-3" />
        {state.result.message || state.result.status}
      </span>
    )
  }
  return <span className="text-xs text-muted-foreground">Untested</span>
}

export function LlmRolesTab({
  data,
  selectedRole,
  dirty,
  error,
  onSelectedRoleChange,
  onChange,
  onSave,
}: {
  data: RolesData | null
  selectedRole: string
  dirty: boolean
  error: string | null
  onSelectedRoleChange: (roleName: string) => void
  onChange: (next: RolesData) => void
  onSave: () => void
}) {
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
                {modelCodes.map((modelCode) => (
                  <option key={modelCode} value={modelCode}>{modelCode}</option>
                ))}
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
  onChange,
}: {
  data: RolesData
  roleName: string
  modelCode: string
  modelIndex: number
  modelCount: number
  active: boolean
  onChange: (next: RolesData) => void
}) {
  const role = data.roles[roleName]
  const providers = role.models[modelCode].providers
  const modelName = data.models[modelCode]?.name ?? modelCode
  return (
    <div className="rounded-sm border border-border bg-card/40 p-3">
      <div className="mb-3 flex items-start justify-between gap-3">
        <div>
          <div className="flex items-center gap-2 text-xs font-semibold">
            {modelCode}
            {active ? <Badge variant="outline">active</Badge> : null}
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
