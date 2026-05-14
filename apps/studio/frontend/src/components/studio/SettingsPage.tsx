import { useEffect, useState, type ReactNode } from "react"
import { CheckCircle2, ChevronDown, Plug, Settings, Sparkles, X, XCircle } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Spinner } from "@/components/ui/spinner"
import { useAppSettings } from "@/hooks/useAppSettings"
import { cn } from "@/lib/utils"
import {
  getCopilotCredentials,
  testCopilotCredentials,
  updateCopilotCredentials,
  type TestCredentialsResponse,
} from "../../api/copilot"
import type { CopilotBackend, CopilotCredentials } from "../../types/copilot"

const BACKENDS: Array<{ id: CopilotBackend; label: string; defaultBaseUrl: string }> = [
  { id: "claude", label: "Claude", defaultBaseUrl: "https://api.anthropic.com" },
  { id: "openai", label: "OpenAI", defaultBaseUrl: "https://api.openai.com" },
  { id: "deepseek", label: "DeepSeek", defaultBaseUrl: "https://api.deepseek.com" },
  { id: "gemini", label: "Gemini", defaultBaseUrl: "https://generativelanguage.googleapis.com" },
]

type SettingsTab = "general" | "copilot" | "advanced"
type TestState =
  | { status: "idle" }
  | { status: "testing" }
  | { status: "ok"; result: TestCredentialsResponse }
  | { status: "error"; result: TestCredentialsResponse }

export interface BackendDraft {
  apiKey: string
  baseUrl: string
  advancedOpen: boolean
}

type Drafts = Record<CopilotBackend, BackendDraft>
type TestStates = Record<CopilotBackend, TestState>

const emptyCredentials: CopilotCredentials = {
  active_backend: "claude",
  backends: {
    claude: { has_key: false, last4: null, base_url: "" },
    openai: { has_key: false, last4: null, base_url: "" },
    deepseek: { has_key: false, last4: null, base_url: "" },
    gemini: { has_key: false, last4: null, base_url: "" },
  },
}

interface SettingsPageProps {
  onClose: () => void
}

interface SettingsPageContentProps {
  activeTab: SettingsTab
  credentials: CopilotCredentials
  drafts: Drafts
  testStates: TestStates
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
  onDraftChange: (backend: CopilotBackend, patch: Partial<BackendDraft>) => void
  onSetActiveBackend: (backend: CopilotBackend) => void
  onTestBackend: (backend: CopilotBackend) => void
  onSaveBackend: (backend: CopilotBackend) => void
}

const initialTestStates = (): TestStates => ({
  claude: { status: "idle" },
  openai: { status: "idle" },
  deepseek: { status: "idle" },
  gemini: { status: "idle" },
})

export function draftsFromCredentials(credentials: CopilotCredentials): Drafts {
  return {
    claude: { apiKey: "", baseUrl: credentials.backends.claude.base_url, advancedOpen: false },
    openai: { apiKey: "", baseUrl: credentials.backends.openai.base_url, advancedOpen: false },
    deepseek: { apiKey: "", baseUrl: credentials.backends.deepseek.base_url, advancedOpen: false },
    gemini: { apiKey: "", baseUrl: credentials.backends.gemini.base_url, advancedOpen: false },
  }
}

export function SettingsPage({ onClose }: SettingsPageProps) {
  const appSettings = useAppSettings()
  const [activeTab, setActiveTab] = useState<SettingsTab>("general")
  const [credentials, setCredentials] = useState<CopilotCredentials>(emptyCredentials)
  const [drafts, setDrafts] = useState<Drafts>(() => draftsFromCredentials(emptyCredentials))
  const [testStates, setTestStates] = useState<TestStates>(() => initialTestStates())

  useEffect(() => {
    let cancelled = false
    getCopilotCredentials()
      .then((next) => {
        if (cancelled) return
        setCredentials(next)
        setDrafts(draftsFromCredentials(next))
      })
      .catch(() => {
        if (!cancelled) {
          setTestStates((current) => ({
            ...current,
            claude: {
              status: "error",
              result: { status: "network_error", message: "Credentials unavailable" },
            },
          }))
        }
      })
    return () => {
      cancelled = true
    }
  }, [])

  function updateDraft(backend: CopilotBackend, patch: Partial<BackendDraft>) {
    setDrafts((current) => ({
      ...current,
      [backend]: { ...current[backend], ...patch },
    }))
    setTestStates((current) => ({ ...current, [backend]: { status: "idle" } }))
  }

  async function setActiveBackend(backend: CopilotBackend) {
    setCredentials((current) => ({ ...current, active_backend: backend }))
    const next = await updateCopilotCredentials(backend, undefined, true)
    setCredentials(next)
    setDrafts(draftsFromCredentials(next))
  }

  async function testBackend(backend: CopilotBackend) {
    const draft = drafts[backend]
    setTestStates((current) => ({ ...current, [backend]: { status: "testing" } }))
    const result = await testCopilotCredentials({
      backend,
      api_key: draft.apiKey.trim(),
      base_url: draft.baseUrl.trim(),
    })
    setTestStates((current) => ({
      ...current,
      [backend]: result.status === "ok" ? { status: "ok", result } : { status: "error", result },
    }))
  }

  async function saveBackend(backend: CopilotBackend) {
    const draft = drafts[backend]
    const status = credentials.backends[backend]
    const next = await updateCopilotCredentials(
      backend,
      draft.apiKey.trim() ? draft.apiKey.trim() : undefined,
      credentials.active_backend === backend,
      draft.baseUrl === status.base_url ? undefined : draft.baseUrl,
    )
    setCredentials(next)
    setDrafts(draftsFromCredentials(next))
  }

  return (
    <SettingsPageContent
      activeTab={activeTab}
      credentials={credentials}
      drafts={drafts}
      testStates={testStates}
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
      onSetActiveBackend={(backend) => void setActiveBackend(backend)}
      onTestBackend={(backend) => void testBackend(backend)}
      onSaveBackend={(backend) => void saveBackend(backend)}
    />
  )
}

export function SettingsPageContent({
  activeTab,
  credentials,
  drafts,
  testStates,
  appSettings,
  onClose,
  onTabChange,
  onDraftChange,
  onSetActiveBackend,
  onTestBackend,
  onSaveBackend,
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
          <NavButton active={activeTab === "copilot"} icon={<Sparkles />} onClick={() => onTabChange("copilot")}>
            AI & Copilot
          </NavButton>
          <NavButton active={activeTab === "advanced"} icon={<Plug />} onClick={() => onTabChange("advanced")}>
            Advanced
          </NavButton>
        </nav>

        <ScrollArea className="flex-1">
          <div className="max-w-3xl px-10 py-8">
            {activeTab === "general" ? <GeneralTab appSettings={appSettings} /> : null}
            {activeTab === "copilot" ? (
              <CopilotTab
                credentials={credentials}
                drafts={drafts}
                testStates={testStates}
                onDraftChange={onDraftChange}
                onSetActiveBackend={onSetActiveBackend}
                onTestBackend={onTestBackend}
                onSaveBackend={onSaveBackend}
              />
            ) : null}
            {activeTab === "advanced" ? <AdvancedTab /> : null}
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
        active
          ? "bg-sidebar-accent text-foreground"
          : "text-muted-foreground hover:bg-sidebar-accent/60 hover:text-foreground",
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
            <Button
              type="button"
              size="sm"
              onClick={() => void appSettings.save()}
              disabled={appSettings.isLoading}
              className="h-7 text-xs"
            >
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
            <Button
              type="button"
              size="sm"
              onClick={() => void appSettings.save()}
              disabled={appSettings.isLoading}
              className="h-7 text-xs"
            >
              Save
            </Button>
          </div>
        }
      />
    </div>
  )
}

function CopilotTab({
  credentials,
  drafts,
  testStates,
  onDraftChange,
  onSetActiveBackend,
  onTestBackend,
  onSaveBackend,
}: Omit<
  SettingsPageContentProps,
  "activeTab" | "appSettings" | "onClose" | "onTabChange"
>) {
  return (
    <div>
      <SectionTitle
        title="AI & Copilot"
        description="Manage provider API keys, custom endpoints, and the active Copilot backend."
      />
      <div className="mb-5 rounded-md border border-border bg-card p-4">
        <Label className="mb-3 block text-xs font-medium text-foreground">Active Backend</Label>
        <RadioGroup
          value={credentials.active_backend}
          onValueChange={(value) => onSetActiveBackend(value as CopilotBackend)}
          className="grid grid-cols-2 gap-2 md:grid-cols-4"
        >
          {BACKENDS.map((backend) => (
            <label
              key={backend.id}
              className="flex h-8 items-center gap-2 rounded-md border border-border px-2 text-xs text-foreground"
            >
              <RadioGroupItem value={backend.id} />
              {backend.label}
            </label>
          ))}
        </RadioGroup>
      </div>

      <div className="space-y-3">
        {BACKENDS.map((backend) => (
          <BackendCredentialCard
            key={backend.id}
            backend={backend}
            active={credentials.active_backend === backend.id}
            status={credentials.backends[backend.id]}
            draft={drafts[backend.id]}
            testState={testStates[backend.id]}
            onDraftChange={(patch) => onDraftChange(backend.id, patch)}
            onTest={() => onTestBackend(backend.id)}
            onSave={() => onSaveBackend(backend.id)}
          />
        ))}
      </div>
    </div>
  )
}

export function BackendCredentialCard({
  backend,
  active,
  status,
  draft,
  testState,
  onDraftChange,
  onTest,
  onSave,
}: {
  backend: (typeof BACKENDS)[number]
  active: boolean
  status: CopilotCredentials["backends"][CopilotBackend]
  draft: BackendDraft
  testState: TestState
  onDraftChange: (patch: Partial<BackendDraft>) => void
  onTest: () => void
  onSave: () => void
}) {
  const keyMask = status.last4 ? `••••${status.last4}` : ""
  const keyDirty = draft.apiKey.trim().length > 0
  const baseUrlDirty = draft.baseUrl !== status.base_url
  const dirty = keyDirty || baseUrlDirty

  return (
    <Card size="sm" className={cn(active ? "ring-primary/50" : "")}>
      <CardHeader className="flex-row items-start justify-between gap-3">
        <div>
          <CardTitle className="flex items-center gap-2">
            {backend.label}
            {active ? <Badge>Active</Badge> : null}
          </CardTitle>
          <p className="mt-1 text-[11px] text-muted-foreground">
            {status.has_key ? "API key configured" : "No API key configured"}
          </p>
        </div>
        <TestBadge state={testState} />
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="grid gap-2 md:grid-cols-[1fr_auto]">
          <div>
            <Label htmlFor={`${backend.id}-api-key`} className="text-[11px] text-muted-foreground">
              API Key
            </Label>
            <Input
              id={`${backend.id}-api-key`}
              name={`${backend.id}-api-key`}
              type="password"
              autoComplete="off"
              value={draft.apiKey}
              onChange={(event) => onDraftChange({ apiKey: event.target.value })}
              placeholder={keyMask || "Enter API key"}
              className="mt-1 h-8 text-xs"
              aria-label={`${backend.label} API key`}
            />
            {keyMask ? <p className="mt-1 text-[11px] text-muted-foreground">{keyMask}</p> : null}
          </div>
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={onTest}
            disabled={testState.status === "testing" || !draft.apiKey.trim()}
            className="mt-5 h-8"
            aria-label={`Test ${backend.label} credentials`}
          >
            {testState.status === "testing" ? <Spinner className="size-3.5" /> : null}
            Test
          </Button>
        </div>

        <Collapsible
          open={draft.advancedOpen}
          onOpenChange={(open) => onDraftChange({ advancedOpen: open })}
        >
          <CollapsibleTrigger asChild>
            <Button type="button" variant="ghost" size="sm" className="h-7 px-0 text-xs">
              <ChevronDown className="size-3.5" />
              Advanced
            </Button>
          </CollapsibleTrigger>
          <CollapsibleContent>
            <div className="rounded-md border border-border bg-muted/20 p-3">
              <Label htmlFor={`${backend.id}-base-url`} className="text-[11px] text-muted-foreground">
                Custom Base URL
              </Label>
              <Input
                id={`${backend.id}-base-url`}
                value={draft.baseUrl}
                onChange={(event) => onDraftChange({ baseUrl: event.target.value })}
                placeholder={backend.defaultBaseUrl}
                className="mt-1 h-8 text-xs"
                aria-label={`${backend.label} Base URL`}
              />
            </div>
          </CollapsibleContent>
        </Collapsible>

        <div className="flex min-h-7 items-center justify-between gap-3">
          <TestMessage state={testState} />
          {dirty ? (
            <Button
              type="button"
              size="sm"
              onClick={onSave}
              className="h-7 text-xs"
              aria-label={`Save ${backend.label} credentials`}
            >
              Save
            </Button>
          ) : null}
        </div>
      </CardContent>
    </Card>
  )
}

function TestBadge({ state }: { state: TestState }) {
  if (state.status === "testing") {
    return (
      <Badge variant="outline">
        <Spinner className="size-3" />
        Testing
      </Badge>
    )
  }
  if (state.status === "ok") {
    return (
      <Badge className="bg-emerald-600 text-white">
        <CheckCircle2 className="size-3" />
        OK
      </Badge>
    )
  }
  if (state.status === "error") {
    return (
      <Badge variant="destructive">
        <XCircle className="size-3" />
        Error
      </Badge>
    )
  }
  return <Badge variant="outline">Idle</Badge>
}

function TestMessage({ state }: { state: TestState }) {
  if (state.status === "ok") {
    const details = [state.result.model_seen, state.result.latency_ms ? `${state.result.latency_ms}ms` : null]
      .filter(Boolean)
      .join(" · ")
    return <span className="text-xs text-emerald-600">OK{details ? ` · ${details}` : ""}</span>
  }
  if (state.status === "error") {
    const message = state.result.status === "invalid_key" ? "Invalid API key" : state.result.message || state.result.status
    return <span className="text-xs text-destructive">{message}</span>
  }
  return <span className="text-xs text-muted-foreground"> </span>
}

function AdvancedTab() {
  return (
    <div>
      <SectionTitle title="Advanced" description="More settings coming soon." />
      <div className="rounded-md border border-dashed border-border p-6 text-xs text-muted-foreground">
        More settings coming soon
      </div>
    </div>
  )
}

export { BACKENDS }
