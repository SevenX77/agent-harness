import { useEffect, useRef, useState } from "react"
import { CheckCircle2, ChevronDown, ChevronRight, Eye, EyeOff, Plus, Trash2, X, XCircle } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Spinner } from "@/components/ui/spinner"
import { cn } from "@/lib/utils"
import {
  getCopilotCredentials,
  putCopilotCredentials,
  testCopilotProvider,
  type CopilotCredentials,
  type ProviderConfig,
  type ProviderKind,
  type TestProviderResponse,
} from "../../api/copilot"

const AUTOSAVE_DELAY_MS = 650

export const DEFAULT_CREDENTIALS: CopilotCredentials = {
  active_provider_id: "default-claude",
  providers: [
    defaultProvider("default-claude", "Claude", "anthropic"),
    defaultProvider("default-openai", "OpenAI", "openai-compat"),
    defaultProvider("default-deepseek", "DeepSeek", "openai-compat"),
    defaultProvider("default-gemini", "Gemini", "google"),
  ],
}

interface SettingsPageProps {
  onClose: () => void
}

type Drafts = Record<string, ProviderConfig>
type TestResults = Record<string, TestProviderResponse | null>

interface SettingsPageContentProps {
  credentials: CopilotCredentials
  drafts: Drafts
  expandedIds: Set<string>
  visibleKeyIds: Set<string>
  testingIds: Set<string>
  testResults: TestResults
  addDialogOpen: boolean
  newProvider: { name: string; kind: ProviderKind }
  onClose: () => void
  onActiveProviderChange: (providerId: string) => void
  onDraftChange: (providerId: string, patch: Partial<ProviderConfig>) => void
  onToggleExpanded: (providerId: string) => void
  onToggleKeyVisible: (providerId: string) => void
  onTestProvider: (providerId: string) => void
  onDeleteProvider: (providerId: string) => void
  onAddDialogOpenChange: (open: boolean) => void
  onNewProviderChange: (patch: Partial<{ name: string; kind: ProviderKind }>) => void
  onConfirmAddProvider: () => void
}

export function SettingsPage({ onClose }: SettingsPageProps) {
  const [credentials, setCredentials] = useState<CopilotCredentials>(DEFAULT_CREDENTIALS)
  const [drafts, setDrafts] = useState<Drafts>(() => draftsFromCredentials(DEFAULT_CREDENTIALS))
  const [dirtyIds, setDirtyIds] = useState<Set<string>>(new Set())
  const [expandedIds, setExpandedIds] = useState<Set<string>>(new Set())
  const [visibleKeyIds, setVisibleKeyIds] = useState<Set<string>>(new Set())
  const [testingIds, setTestingIds] = useState<Set<string>>(new Set())
  const [testResults, setTestResults] = useState<TestResults>({})
  const [addDialogOpen, setAddDialogOpen] = useState(false)
  const [newProvider, setNewProvider] = useState<{ name: string; kind: ProviderKind }>({
    name: "",
    kind: "openai-compat",
  })
  const credentialsRef = useRef(credentials)
  const draftsRef = useRef(drafts)
  const dirtyIdsRef = useRef(dirtyIds)

  useEffect(() => {
    credentialsRef.current = credentials
  }, [credentials])

  useEffect(() => {
    draftsRef.current = drafts
  }, [drafts])

  useEffect(() => {
    dirtyIdsRef.current = dirtyIds
  }, [dirtyIds])

  useEffect(() => {
    let cancelled = false
    getCopilotCredentials()
      .then((next: CopilotCredentials) => {
        if (cancelled) return
        setCredentials(next)
        setDrafts(draftsFromCredentials(next))
      })
      .catch(() => {
        if (!cancelled) {
          setCredentials(DEFAULT_CREDENTIALS)
          setDrafts(draftsFromCredentials(DEFAULT_CREDENTIALS))
        }
      })
    return () => {
      cancelled = true
    }
  }, [])

  useEffect(() => {
    if (dirtyIds.size === 0) return
    const timer = window.setTimeout(() => {
      void flushCredentials()
    }, AUTOSAVE_DELAY_MS)
    return () => window.clearTimeout(timer)
  }, [dirtyIds, credentials, drafts])

  async function flushCredentials() {
    const next = buildCredentialsFromDrafts(credentialsRef.current, draftsRef.current)
    await putCopilotCredentials(next)
    setCredentials(next)
    setDirtyIds(new Set())
  }

  function markDirty(providerId: string) {
    setDirtyIds((current) => new Set(current).add(providerId))
  }

  function updateDraft(providerId: string, patch: Partial<ProviderConfig>) {
    setDrafts((current) => ({
      ...current,
      [providerId]: { ...current[providerId], ...patch },
    }))
    setTestResults((current) => ({ ...current, [providerId]: null }))
    markDirty(providerId)
  }

  function setActiveProvider(providerId: string) {
    setCredentials((current) => ({ ...current, active_provider_id: providerId }))
    markDirty("__root__")
  }

  async function runProviderTest(providerId: string) {
    const draft = draftsRef.current[providerId]
    if (!draft) return
    setTestingIds((current) => new Set(current).add(providerId))
    setTestResults((current) => ({ ...current, [providerId]: null }))
    try {
      const next = buildCredentialsFromDrafts(credentialsRef.current, draftsRef.current)
      await putCopilotCredentials(next)
      setCredentials(next)
      setDirtyIds((current) => {
        const copy = new Set(current)
        copy.delete(providerId)
        return copy
      })
      const result = await testCopilotProvider({
        id: draft.id,
        name: draft.name,
        kind: draft.kind,
        api_key: draft.api_key.trim(),
        base_url: draft.base_url.trim(),
      })
      setTestResults((current) => ({ ...current, [providerId]: result }))
    } finally {
      setTestingIds((current) => {
        const copy = new Set(current)
        copy.delete(providerId)
        return copy
      })
    }
  }

  function addProvider() {
    const name = newProvider.name.trim()
    if (!name) return
    const provider = customProvider(name, newProvider.kind)
    setCredentials((current) => appendProvider(current, provider))
    setDrafts((current) => ({ ...current, [provider.id]: provider }))
    markDirty(provider.id)
    setNewProvider({ name: "", kind: "openai-compat" })
    setAddDialogOpen(false)
  }

  function deleteProvider(providerId: string) {
    if (isDefaultProvider(providerId) || !window.confirm("Delete this provider?")) return
    setCredentials((current) => removeProvider(current, providerId))
    setDrafts((current) => {
      const next = { ...current }
      delete next[providerId]
      return next
    })
    setTestResults((current) => ({ ...current, [providerId]: null }))
    markDirty("__root__")
  }

  return (
    <SettingsPageContent
      credentials={credentials}
      drafts={drafts}
      expandedIds={expandedIds}
      visibleKeyIds={visibleKeyIds}
      testingIds={testingIds}
      testResults={testResults}
      addDialogOpen={addDialogOpen}
      newProvider={newProvider}
      onClose={onClose}
      onActiveProviderChange={setActiveProvider}
      onDraftChange={updateDraft}
      onToggleExpanded={(providerId) =>
        setExpandedIds((current) => toggleSetValue(current, providerId))
      }
      onToggleKeyVisible={(providerId) =>
        setVisibleKeyIds((current) => toggleSetValue(current, providerId))
      }
      onTestProvider={(providerId) => void runProviderTest(providerId)}
      onDeleteProvider={deleteProvider}
      onAddDialogOpenChange={setAddDialogOpen}
      onNewProviderChange={(patch) => setNewProvider((current) => ({ ...current, ...patch }))}
      onConfirmAddProvider={addProvider}
    />
  )
}

export function SettingsPageContent({
  credentials,
  drafts,
  expandedIds,
  visibleKeyIds,
  testingIds,
  testResults,
  addDialogOpen,
  newProvider,
  onClose,
  onActiveProviderChange,
  onDraftChange,
  onToggleExpanded,
  onToggleKeyVisible,
  onTestProvider,
  onDeleteProvider,
  onAddDialogOpenChange,
  onNewProviderChange,
  onConfirmAddProvider,
}: SettingsPageContentProps) {
  return (
    <div className="flex size-full flex-col bg-background">
      <div className="flex h-11 shrink-0 items-center justify-between border-b border-border pl-4 pr-2">
        <span className="text-sm font-semibold text-foreground">Settings</span>
        <Button variant="ghost" size="icon" onClick={onClose} aria-label="Close settings" className="size-7">
          <X className="size-4" />
        </Button>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto px-8 py-7">
        <div className="mx-auto max-w-4xl space-y-5">
          <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border pb-4">
            <div>
              <h2 className="text-xl font-semibold tracking-tight text-foreground">AI & Copilot</h2>
              <p className="mt-1 text-xs text-muted-foreground">Changes are saved automatically.</p>
            </div>
            <div className="flex items-center gap-2">
              <Label className="text-xs text-muted-foreground">Active Provider</Label>
              <Select value={credentials.active_provider_id} onValueChange={onActiveProviderChange}>
                <SelectTrigger className="h-8 w-48 text-xs" aria-label="Active Provider">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {credentials.providers.map((provider) => (
                    <SelectItem key={provider.id} value={provider.id}>
                      {provider.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <Button type="button" size="sm" onClick={() => onAddDialogOpenChange(true)} className="h-8 text-xs">
                <Plus className="size-3.5" />
                Add Custom Provider
              </Button>
            </div>
          </div>

          <div className="space-y-3">
            {credentials.providers.map((provider) => {
              const draft = drafts[provider.id] ?? provider
              return (
                <ProviderCard
                  key={provider.id}
                  provider={provider}
                  draft={draft}
                  active={credentials.active_provider_id === provider.id}
                  expanded={expandedIds.has(provider.id)}
                  keyVisible={visibleKeyIds.has(provider.id)}
                  testing={testingIds.has(provider.id)}
                  testResult={testResults[provider.id] ?? null}
                  onDraftChange={(patch) => onDraftChange(provider.id, patch)}
                  onToggleExpanded={() => onToggleExpanded(provider.id)}
                  onToggleKeyVisible={() => onToggleKeyVisible(provider.id)}
                  onTest={() => onTestProvider(provider.id)}
                  onDelete={() => onDeleteProvider(provider.id)}
                />
              )
            })}
          </div>
        </div>
      </div>

      <Dialog open={addDialogOpen} onOpenChange={onAddDialogOpenChange}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Add Custom Provider</DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            <div className="space-y-2">
              <Label className="text-xs">Name</Label>
              <Input
                value={newProvider.name}
                onChange={(event) => onNewProviderChange({ name: event.target.value })}
                placeholder="Ollama Local"
                aria-label="New provider name"
              />
            </div>
            <div className="space-y-2">
              <Label className="text-xs">Kind</Label>
              <Select
                value={newProvider.kind}
                onValueChange={(kind) => onNewProviderChange({ kind: kind as ProviderKind })}
              >
                <SelectTrigger aria-label="New provider kind">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="anthropic">anthropic</SelectItem>
                  <SelectItem value="openai-compat">openai-compat</SelectItem>
                  <SelectItem value="google">google</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>
          <DialogFooter>
            <Button type="button" onClick={onConfirmAddProvider} disabled={!newProvider.name.trim()}>
              Add Provider
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}

export function ProviderCard({
  provider,
  draft,
  active,
  expanded,
  keyVisible,
  testing,
  testResult,
  onDraftChange,
  onToggleExpanded,
  onToggleKeyVisible,
  onTest,
  onDelete,
}: {
  provider: ProviderConfig
  draft: ProviderConfig
  active: boolean
  expanded: boolean
  keyVisible: boolean
  testing: boolean
  testResult: TestProviderResponse | null
  onDraftChange: (patch: Partial<ProviderConfig>) => void
  onToggleExpanded: () => void
  onToggleKeyVisible: () => void
  onTest: () => void
  onDelete: () => void
}) {
  const models = testResult?.status === "ok" ? testResult.models : []

  return (
    <Card size="sm" className={cn(active ? "ring-1 ring-primary/50" : "")}>
      <CardHeader className="flex-row items-start justify-between gap-3">
        <div>
          <CardTitle className="flex flex-wrap items-center gap-2 text-sm">
            <Input
              value={draft.name}
              onChange={(event) => onDraftChange({ name: event.target.value })}
              className="h-7 w-44 border-transparent bg-transparent px-0 text-sm font-semibold shadow-none"
              aria-label={`${provider.name} provider name`}
            />
            <Badge variant="outline">{draft.kind}</Badge>
            {active ? <Badge>Active</Badge> : null}
          </CardTitle>
        </div>
        <Button
          type="button"
          size="icon"
          variant="ghost"
          onClick={onDelete}
          disabled={isDefaultProvider(provider.id)}
          aria-label={`Delete ${provider.name} provider`}
          className="size-7"
        >
          <Trash2 className="size-3.5" />
        </Button>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="space-y-2">
          <Label className="text-xs text-muted-foreground">API Key</Label>
          <div className="flex gap-2">
            <div className="relative flex-1">
              <Input
                type={keyVisible ? "text" : "password"}
                value={draft.api_key}
                onChange={(event) => onDraftChange({ api_key: event.target.value })}
                placeholder="Enter API key"
                autoComplete="new-password"
                className="pr-10"
                aria-label={`${provider.name} API key`}
              />
              <button
                type="button"
                onMouseDown={(event) => event.preventDefault()}
                onClick={onToggleKeyVisible}
                aria-label={keyVisible ? `Hide ${provider.name} API key` : `Show ${provider.name} API key`}
                className="absolute right-1.5 top-1/2 flex size-7 -translate-y-1/2 items-center justify-center rounded-md text-muted-foreground hover:bg-muted hover:text-foreground"
              >
                {keyVisible ? <EyeOff className="size-4" /> : <Eye className="size-4" />}
              </button>
            </div>
            <Button type="button" variant="secondary" onClick={onTest} disabled={testing} className="shrink-0">
              {testing ? <Spinner className="size-3.5" /> : null}
              Test Connection
            </Button>
          </div>
        </div>

        <Button type="button" variant="ghost" onClick={onToggleExpanded} className="h-7 px-0 text-xs">
          {expanded ? <ChevronDown className="size-3.5" /> : <ChevronRight className="size-3.5" />}
          Advanced Options
        </Button>

        {expanded ? (
          <div className="space-y-2">
            <Label className="text-xs text-muted-foreground">Base URL</Label>
            <Input
              value={draft.base_url}
              onChange={(event) => onDraftChange({ base_url: event.target.value })}
              placeholder={defaultBaseUrl(draft.kind)}
              aria-label={`${provider.name} Base URL`}
            />
          </div>
        ) : null}

        <ProviderStatus result={testResult} />

        {models.length > 0 ? (
          <div className="space-y-3">
            <div>
              <div className="mb-2 text-xs font-medium text-foreground">Available Models ({models.length})</div>
              <div className="flex flex-wrap gap-2">
                {models.map((model) => (
                  <Badge key={model.id} variant="outline">
                    {model.id}
                    {model.supports_thinking ? " 🧠" : ""}
                  </Badge>
                ))}
              </div>
            </div>
            <div className="space-y-2">
              <Label className="text-xs text-muted-foreground">Default Model</Label>
              <Select
                value={draft.active_model_id ?? ""}
                onValueChange={(active_model_id) => onDraftChange({ active_model_id })}
              >
                <SelectTrigger aria-label={`Default model for ${provider.name}`} className="w-72">
                  <SelectValue placeholder="Select model" />
                </SelectTrigger>
                <SelectContent>
                  {models.map((model) => (
                    <SelectItem key={model.id} value={model.id}>
                      {model.id}
                      {model.supports_thinking ? " 🧠" : ""}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>
        ) : null}
      </CardContent>
    </Card>
  )
}

function ProviderStatus({ result }: { result: TestProviderResponse | null }) {
  if (!result) return null
  if (result.status === "ok") {
    return (
      <div className="flex items-center gap-2 rounded-md border border-emerald-500/20 bg-emerald-500/10 p-3 text-xs text-emerald-600">
        <CheckCircle2 className="size-4" />
        Connected{result.latency_ms != null ? `, latency_ms=${result.latency_ms}` : ""}
      </div>
    )
  }
  return (
    <div className="flex items-center gap-2 rounded-md border border-destructive/20 bg-destructive/10 p-3 text-xs text-destructive">
      <XCircle className="size-4" />
      {result.message || result.status}
    </div>
  )
}

export function draftsFromCredentials(credentials: CopilotCredentials): Drafts {
  return Object.fromEntries(credentials.providers.map((provider) => [provider.id, { ...provider }]))
}

export function buildCredentialsFromDrafts(
  credentials: CopilotCredentials,
  drafts: Drafts,
): CopilotCredentials {
  return {
    ...credentials,
    providers: credentials.providers.map((provider) => drafts[provider.id] ?? provider),
  }
}

export function appendProvider(credentials: CopilotCredentials, provider: ProviderConfig): CopilotCredentials {
  return {
    ...credentials,
    providers: [...credentials.providers, provider],
  }
}

export function removeProvider(credentials: CopilotCredentials, providerId: string): CopilotCredentials {
  const providers = credentials.providers.filter((provider) => provider.id !== providerId)
  return {
    active_provider_id:
      credentials.active_provider_id === providerId ? "default-claude" : credentials.active_provider_id,
    providers,
  }
}

export function createDebouncedSaver<T>(save: (snapshot: T) => void | Promise<void>, delayMs = AUTOSAVE_DELAY_MS) {
  let timer: ReturnType<typeof setTimeout> | null = null
  return {
    schedule(snapshot: T) {
      if (timer) clearTimeout(timer)
      timer = setTimeout(() => {
        timer = null
        void save(snapshot)
      }, delayMs)
    },
    cancel() {
      if (timer) clearTimeout(timer)
      timer = null
    },
  }
}

export function isDefaultProvider(providerId: string) {
  return providerId.startsWith("default-")
}

export function customProvider(name: string, kind: ProviderKind): ProviderConfig {
  return {
    id: `custom-${createId(8)}`,
    name,
    kind,
    api_key: "",
    base_url: "",
    active_model_id: null,
  }
}

function defaultProvider(id: string, name: string, kind: ProviderKind): ProviderConfig {
  return { id, name, kind, api_key: "", base_url: "", active_model_id: null }
}

function defaultBaseUrl(kind: ProviderKind) {
  if (kind === "anthropic") return "https://api.anthropic.com"
  if (kind === "google") return "https://generativelanguage.googleapis.com/v1beta"
  return "https://api.openai.com/v1"
}

function toggleSetValue<T>(set: Set<T>, value: T) {
  const next = new Set(set)
  if (next.has(value)) {
    next.delete(value)
  } else {
    next.add(value)
  }
  return next
}

function createId(size: number) {
  const chars = "0123456789abcdefghijklmnopqrstuvwxyz"
  let id = ""
  for (let index = 0; index < size; index += 1) {
    id += chars[Math.floor(Math.random() * chars.length)]
  }
  return id
}
