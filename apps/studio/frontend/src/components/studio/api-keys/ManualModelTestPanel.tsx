import { useEffect, useMemo, useState } from "react"
import { Loader2, Plus, Trash2 } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { getNotableModels, testProviderModels, type ModelInfo, type ProviderModelTestResult } from "../../../api/llm"

interface Props {
  providerKey: string
  notableProviderKey: string
  onModelsUpdated: (models: ModelInfo[]) => void
}

const exampleModelIdsByProvider: Record<string, string> = {
  anthropic: "claude-opus-4-7",
  openai: "gpt-5",
  gemini: "gemini-3.1-pro-preview",
  deepseek: "deepseek-chat",
  ark: "doubao-seed-1-6",
  openrouter: "openai/gpt-5",
}

function modelIdPlaceholder(
  notableProviderKey: string,
  notableModels: string[],
  index: number,
): string {
  const example =
    notableModels[index] ??
    notableModels[0] ??
    exampleModelIdsByProvider[notableProviderKey.toLowerCase()] ??
    "gpt-5"
  return `model_id: ${example}`
}

export function mergeModelLists(existing: ModelInfo[], incoming: ModelInfo[]): ModelInfo[] {
  const byId = new Map(existing.map((model) => [model.id, model]))
  for (const model of incoming) {
    if (!byId.has(model.id)) byId.set(model.id, model)
  }
  return [...byId.values()]
}

export function ManualModelTestPanel({ providerKey, notableProviderKey, onModelsUpdated }: Props) {
  const [modelIds, setModelIds] = useState([""])
  const [notableModels, setNotableModels] = useState<string[]>([])
  const [results, setResults] = useState<ProviderModelTestResult[]>([])
  const [loadingCandidates, setLoadingCandidates] = useState(false)
  const [testing, setTesting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const trimmedModelIds = useMemo(
    () => Array.from(new Set(modelIds.map((modelId) => modelId.trim()).filter(Boolean))),
    [modelIds],
  )

  useEffect(() => {
    let cancelled = false
    setLoadingCandidates(true)
    getNotableModels(notableProviderKey)
      .then((response) => {
        if (!cancelled) setNotableModels(response.notable_models)
      })
      .catch((candidateError: unknown) => {
        if (!cancelled) {
          const message = candidateError instanceof Error ? candidateError.message : "Failed to load notable models"
          setError(message)
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
    try {
      const response = await testProviderModels({
        provider_id: providerKey,
        model_ids: trimmedModelIds,
      })
      setResults(response.results)
      onModelsUpdated(response.available_models)
    } catch (testError) {
      const message = testError instanceof Error ? testError.message : "Model test failed"
      setError(message)
    } finally {
      setTesting(false)
    }
  }

  return (
    <div className="border-t pt-3 space-y-3 text-xs" data-testid="manual-model-test-panel">
      <div className="flex items-center justify-between gap-3">
        <div>
          <div className="font-medium text-foreground">Manual model probing</div>
          <div className="text-muted-foreground">Add model ids when automatic model listing is unavailable.</div>
        </div>
        {loadingCandidates ? <Loader2 className="size-3.5 animate-spin text-muted-foreground" /> : null}
      </div>
      <div className="space-y-2">
        {modelIds.map((modelId, index) => (
          <div key={index} className="flex items-center gap-2">
            <Input
              value={modelId}
              onChange={(event) => {
                const next = [...modelIds]
                next[index] = event.target.value
                setModelIds(next)
              }}
              placeholder={modelIdPlaceholder(notableProviderKey, notableModels, index)}
              aria-label={`Manual model ${index + 1}`}
              className="h-8 font-mono text-xs"
            />
            <Button
              type="button"
              size="icon"
              variant="ghost"
              aria-label={`Remove model ${index + 1}`}
              disabled={modelIds.length === 1}
              onClick={() => setModelIds((current) => current.filter((_, itemIndex) => itemIndex !== index))}
            >
              <Trash2 className="size-3.5" />
            </Button>
          </div>
        ))}
      </div>
      <div className="flex items-center gap-2">
        <Button type="button" variant="outline" size="sm" className="gap-1" onClick={() => setModelIds((current) => [...current, ""])}>
          <Plus className="size-3.5" />
          Add Model
        </Button>
        <Button type="button" size="sm" onClick={() => void runModelTests()} disabled={testing || trimmedModelIds.length === 0}>
          {testing ? <Loader2 className="size-3.5 animate-spin" /> : null}
          Test Models
        </Button>
      </div>
      {error ? <div className="text-destructive">{error}</div> : null}
      {results.length > 0 ? (
        <div className="flex flex-wrap gap-1">
          {results.map((result) => (
            <Badge key={result.model_id} variant={result.status === "ok" ? "outline" : "destructive"} className="font-mono">
              {result.model_id}: {result.status}
            </Badge>
          ))}
        </div>
      ) : null}
    </div>
  )
}
