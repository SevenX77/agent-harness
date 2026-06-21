import { useEffect, useMemo, useState } from "react"
import { toast } from "sonner"
import { Loader2, Plus, Trash2 } from "lucide-react"
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from "@/components/ui/accordion"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { composeRequestErrorMessage } from "@/lib/llm-error-messages"
import { getNotableModels, testProviderModels, type ModelInfo, type ProviderModelTestResult, type ProviderUiState } from "../../../api/llm"
import { ProviderStateBadge } from "../settings/llm-roles/provider-state-badge"

interface Props {
  providerKey: string
  notableProviderKey: string
  onModelsUpdated: (models: ModelInfo[]) => void
  defaultExpanded?: boolean
}

const exampleModelIdsByProvider: Record<string, string> = {
  anthropic: "claude-opus-4-7",
  openai: "gpt-5",
  gemini: "gemini-3.1-pro-preview",
  deepseek: "deepseek-chat",
  ark: "doubao-seed-1-6",
  openrouter: "openai/gpt-5",
  qiniu: "deepseek-r1",
  wavespeed: "openai/gpt-5",
}
const vendorPrefixedModelProviders = new Set(["openrouter", "wavespeed"])
const manualModelPanelValue = "manual-model-probing"
type ManualModelToastKind = "success" | "error" | "info"

export function manualModelStatusLabel(status: ProviderModelTestResult["status"]): string {
  switch (status) {
    case "ok":
      return "Available"
    case "invalid_model":
      return "Model not found"
    case "invalid_key":
      return "Invalid API key"
    case "rate_limited":
      return "Rate limited"
    case "quota_exceeded":
      return "Quota exceeded"
    case "network_error":
      return "Network error"
    case "timeout":
      return "Request timed out"
    case "error":
      return "Test failed"
    default:
      return "Test failed"
  }
}

// apikeys#27: manual probe results render through the SAME 6-state
// ProviderStateBadge used across LLM Roles / API Keys, replacing the old
// ad-hoc 2-state success/destructive Badge. A manual probe only resolves to a
// reachable model (ready) or a failure (failed); the badge component carries the
// full 6-state map so colors stay consistent with the rest of the status system.
export function manualModelResultUiState(status: ProviderModelTestResult["status"]): ProviderUiState {
  return status === "ok" ? "ready" : "failed"
}

export function manualModelResultReasonCode(status: ProviderModelTestResult["status"]): string | null {
  switch (status) {
    case "invalid_model":
      return "invalid_model"
    case "invalid_key":
      return "invalid_key"
    case "rate_limited":
    case "quota_exceeded":
      return "rate_limited"
    default:
      return null
  }
}

export function manualModelAccordionValue(expanded: boolean): string {
  return expanded ? manualModelPanelValue : ""
}

export function modelIdPlaceholder(
  notableProviderKey: string,
  notableModels: string[],
  index: number,
): string {
  const normalizedProviderKey = notableProviderKey.toLowerCase()
  const example =
    notableModels[index] ??
    notableModels[0] ??
    exampleModelIdsByProvider[normalizedProviderKey] ??
    "gpt-5"
  if (vendorPrefixedModelProviders.has(normalizedProviderKey)) {
    return `e.g. ${example}`
  }
  return `e.g. ${example.replace(/^[^/]+\//, "")}`
}

export function mergeModelLists(existing: ModelInfo[], incoming: ModelInfo[]): ModelInfo[] {
  const byId = new Map(existing.map((model) => [model.id, model]))
  for (const model of incoming) {
    if (!byId.has(model.id)) byId.set(model.id, model)
  }
  return [...byId.values()]
}

export function manualModelCandidateErrorMessage(error: unknown): string {
  return composeRequestErrorMessage(error, "Failed to load notable models")
}

export function manualModelToastSummary(results: ProviderModelTestResult[]): {
  kind: ManualModelToastKind
  title: string
  description?: string
} {
  if (results.length === 0) {
    return { kind: "info", title: "No model results were returned.", description: undefined }
  }
  const failed = results.filter((result) => result.status !== "ok")
  if (failed.length === 0) {
    return {
      kind: "success",
      title: results.length === 1 ? "Model is available." : `${results.length} models are available.`,
      description: undefined,
    }
  }
  return {
    kind: "error",
    title: `${failed.length} of ${results.length} model tests failed.`,
    description: failed.slice(0, 3).map((result) => (
      `${result.model_id}: ${manualModelStatusLabel(result.status)}`
    )).join(", "),
  }
}

export function ManualModelResultList({ results }: { results: ProviderModelTestResult[] }) {
  if (results.length === 0) {
    return <div className="text-xs text-muted-foreground">No model results were returned.</div>
  }

  return (
    <div className="flex flex-col gap-1.5">
      {results.map((result) => (
        <div key={result.model_id} className="flex items-center gap-2">
          <span className="font-mono text-[11px] text-foreground">{result.model_id}</span>
          <ProviderStateBadge
            state={manualModelResultUiState(result.status)}
            reasonCode={manualModelResultReasonCode(result.status)}
            detail={result.message ?? manualModelStatusLabel(result.status)}
          />
          <span className="text-[11px] text-muted-foreground">{manualModelStatusLabel(result.status)}</span>
        </div>
      ))}
    </div>
  )
}

export function ManualModelTestPanel({ providerKey, notableProviderKey, onModelsUpdated, defaultExpanded = false }: Props) {
  const [expanded, setExpanded] = useState(defaultExpanded)
  const [modelIds, setModelIds] = useState([""])
  const [notableModels, setNotableModels] = useState<string[]>([])
  const [results, setResults] = useState<ProviderModelTestResult[]>([])
  const [hasTested, setHasTested] = useState(false)
  const [loadingCandidates, setLoadingCandidates] = useState(false)
  const [testing, setTesting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const trimmedModelIds = useMemo(
    () => Array.from(new Set(modelIds.map((modelId) => modelId.trim()).filter(Boolean))),
    [modelIds],
  )

  useEffect(() => {
    setExpanded(defaultExpanded)
  }, [defaultExpanded])

  useEffect(() => {
    let cancelled = false
    setLoadingCandidates(true)
    getNotableModels(notableProviderKey)
      .then((response) => {
        if (!cancelled) setNotableModels(response.notable_models)
      })
      .catch((candidateError: unknown) => {
        if (!cancelled) {
          setError(manualModelCandidateErrorMessage(candidateError))
        }
      })
      .finally(() => {
        if (!cancelled) setLoadingCandidates(false)
      })
    return () => {
      cancelled = true
    }
  }, [notableProviderKey])

  async function runModelTests() {
    if (trimmedModelIds.length === 0) return
    setTesting(true)
    setError(null)
    setResults([])
    setHasTested(true)
    const toastId = `manual-model-test-${providerKey}`
    toast.loading("Testing models...", { id: toastId })
    try {
      const response = await testProviderModels({
        provider_id: providerKey,
        model_ids: trimmedModelIds,
      })
      setResults(response.results)
      onModelsUpdated(response.available_models)
      const summary = manualModelToastSummary(response.results)
      toast[summary.kind](summary.title, { id: toastId, description: summary.description })
    } catch (testError) {
      setResults([])
      const message = composeRequestErrorMessage(testError, "Model test failed")
      setError(message)
      toast.error(message, { id: toastId })
    } finally {
      setTesting(false)
    }
  }

  return (
    <Accordion
      type="single"
      collapsible
      value={manualModelAccordionValue(expanded)}
      onValueChange={(value) => setExpanded(value === manualModelPanelValue)}
      className="border-x-0 border-b-0 rounded-none bg-transparent text-xs"
      data-testid="manual-model-test-panel"
    >
      <AccordionItem value={manualModelPanelValue} className="border-0 data-open:bg-transparent">
        <AccordionTrigger className="px-0 py-3 hover:no-underline">
          <div className="min-w-0">
            <div className="font-medium text-foreground">Manual model probing</div>
            <div className="text-muted-foreground">Add model ids when automatic model listing is unavailable.</div>
          </div>
          {loadingCandidates && expanded ? <Loader2 className="size-3.5 animate-spin text-muted-foreground" /> : null}
        </AccordionTrigger>
        <AccordionContent className="space-y-3 px-0 pb-0">
          <div className="space-y-2">
            {modelIds.map((modelId, index) => (
              <div key={index} className="flex items-center gap-2">
                <Input
                  value={modelId}
                  onChange={(event) => {
                    const next = [...modelIds]
                    next[index] = event.target.value
                    setModelIds(next)
                    setResults([])
                    setHasTested(false)
                    setError(null)
                  }}
                  placeholder={modelIdPlaceholder(notableProviderKey, notableModels, index)}
                  aria-label={`Manual model ${index + 1}`}
                  autoComplete="off"
                  autoCorrect="off"
                  autoCapitalize="none"
                  spellCheck={false}
                  className="h-8 font-mono text-xs"
                />
                <Button
                  type="button"
                  size="icon"
                  variant="ghost"
                  aria-label={`Remove model ${index + 1}`}
                  disabled={modelIds.length === 1}
                  onClick={() => {
                    setModelIds((current) => current.filter((_, itemIndex) => itemIndex !== index))
                    setResults([])
                    setHasTested(false)
                    setError(null)
                  }}
                >
                  <Trash2 className="size-3.5" />
                </Button>
              </div>
            ))}
          </div>
          <div className="flex items-center gap-2">
            <Button
              type="button"
              variant="outline"
              size="sm"
              className="gap-1"
              onClick={() => {
                setModelIds((current) => [...current, ""])
                setResults([])
                setHasTested(false)
                setError(null)
              }}
            >
              <Plus className="size-3.5" />
              Add Model
            </Button>
            <Button type="button" size="sm" onClick={() => void runModelTests()} disabled={testing || trimmedModelIds.length === 0}>
              {testing ? <Loader2 className="size-3.5 animate-spin" /> : null}
              Test Models
            </Button>
          </div>
          {error ? <div className="text-destructive">{error}</div> : null}
          {hasTested && !testing && !error ? <ManualModelResultList results={results} /> : null}
        </AccordionContent>
      </AccordionItem>
    </Accordion>
  )
}
