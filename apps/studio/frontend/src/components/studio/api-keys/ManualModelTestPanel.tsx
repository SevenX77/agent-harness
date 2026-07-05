import { useEffect, useMemo, useState } from "react"
import { useTranslation } from "react-i18next"
import { toast } from "sonner"
import { Loader2, Plus, Trash2 } from "lucide-react"
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from "@/components/ui/accordion"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import i18n from "@/i18n"
import { composeRequestErrorMessage } from "@/lib/llm-error-messages"
import { getNotableModels, testProviderModels, type ModelInfo, type ProviderModelTestResult, type ProviderUiState } from "../../../api/llm"
import { ProviderStateBadge } from "../settings/llm-roles/provider-state-badge"
import { probeModelsWithConcurrency } from "./model-probe-runner"

export interface ManualProbeEndpointTarget {
  id: string
  testable: boolean
}

export type ActiveProbeModelIdsByEndpoint = Record<string, string[]>

interface Props {
  providerKey: string
  // W1-B: every testable configured endpoint of this provider, so a manual
  // model test fans out by endpoint. protocol_unsupported/disabled targets are
  // not routine Manual Test targets; explicit Re-probe owns that path.
  endpointTargets?: ManualProbeEndpointTarget[]
  notableProviderKey: string
  onModelsUpdated: (models: ModelInfo[]) => void
  // P1a: report the exact endpoint/model atoms currently in flight so the
  // provider card can pulse only those endpoint tags and model chips.
  onActiveProbeModelIdsByEndpointChange?: (active: ActiveProbeModelIdsByEndpoint) => void
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
      return i18n.t("apiKeys.manualTest.status.ok")
    case "invalid_model":
      return i18n.t("apiKeys.manualTest.status.invalidModel")
    case "invalid_key":
      return i18n.t("apiKeys.manualTest.status.invalidKey")
    case "rate_limited":
      return i18n.t("apiKeys.manualTest.status.rateLimited")
    case "quota_exceeded":
      return i18n.t("apiKeys.manualTest.status.quotaExceeded")
    case "network_error":
      return i18n.t("apiKeys.manualTest.status.networkError")
    case "timeout":
      return i18n.t("apiKeys.manualTest.status.timeout")
    case "error":
      return i18n.t("apiKeys.manualTest.status.failed")
    default:
      return i18n.t("apiKeys.manualTest.status.failed")
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
  notableModels: string[] | undefined | null,
  index: number,
): string {
  const normalizedProviderKey = notableProviderKey.toLowerCase()
  const modelOptions = Array.isArray(notableModels) ? notableModels : []
  const example =
    modelOptions[index] ??
    modelOptions[0] ??
    exampleModelIdsByProvider[normalizedProviderKey] ??
    "gpt-5"
  const display = vendorPrefixedModelProviders.has(normalizedProviderKey)
    ? example
    : example.replace(/^[^/]+\//, "")
  return i18n.t("apiKeys.manualTest.placeholderExample", { example: display })
}

export function manualModelCandidateErrorMessage(error: unknown): string {
  return composeRequestErrorMessage(error, i18n.t("apiKeys.manualTest.candidateLoadError"))
}

export function manualModelToastSummary(results: ProviderModelTestResult[]): {
  kind: ManualModelToastKind
  title: string
  description?: string
} {
  if (results.length === 0) {
    return { kind: "info", title: i18n.t("apiKeys.manualTest.noResults"), description: undefined }
  }
  const failed = results.filter((result) => result.status !== "ok")
  if (failed.length === 0) {
    return {
      kind: "success",
      title:
        results.length === 1
          ? i18n.t("apiKeys.manualTest.oneAvailable")
          : i18n.t("apiKeys.manualTest.manyAvailable", { n: results.length }),
      description: undefined,
    }
  }
  return {
    kind: "error",
    title: i18n.t("apiKeys.manualTest.someFailed", { failed: failed.length, total: results.length }),
    description: failed.slice(0, 3).map((result) => (
      i18n.t("apiKeys.manualTest.failedItem", { modelId: result.model_id, status: manualModelStatusLabel(result.status) })
    )).join(", "),
  }
}

function uniqueStrings(values: string[]): string[] {
  return Array.from(new Set(values))
}

export function ManualModelResultList({ results }: { results: ProviderModelTestResult[] }) {
  const { t } = useTranslation("settings")
  if (results.length === 0) {
    return <div className="text-xs text-muted-foreground">{t("apiKeys.manualTest.noResults")}</div>
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

export function ManualModelTestPanel({ providerKey, endpointTargets, notableProviderKey, onModelsUpdated, onActiveProbeModelIdsByEndpointChange, defaultExpanded = false }: Props) {
  const { t } = useTranslation("settings")
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
  const targetEndpointIds = useMemo(() => {
    const targets =
      endpointTargets && endpointTargets.length > 0
        ? endpointTargets
        : [{ id: providerKey, testable: true }]
    return targets.filter((target) => target.testable).map((target) => target.id)
  }, [endpointTargets, providerKey])

  useEffect(() => {
    setExpanded(defaultExpanded)
  }, [defaultExpanded])

  useEffect(() => {
    let cancelled = false
    setLoadingCandidates(true)
    getNotableModels(notableProviderKey)
      .then((response) => {
        if (!cancelled) setNotableModels(Array.isArray(response.notable_models) ? response.notable_models : [])
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
    if (trimmedModelIds.length === 0 || targetEndpointIds.length === 0) return
    setTesting(true)
    setError(null)
    setResults([])
    setHasTested(true)
    const toastId = `manual-model-test-${providerKey}`
    // Track how many atomic probes are in flight per endpoint/model. The same
    // model can be probed on several endpoints at once, so endpoint tags and
    // model chips must be driven by this endpoint-scoped atom map.
    const inFlightByEndpoint = new Map<string, Map<string, number>>()
    const inFlightIds = () => uniqueStrings(
      [...inFlightByEndpoint.values()].flatMap((endpointModels) => [...endpointModels.keys()]),
    )
    const activeByEndpoint = (): ActiveProbeModelIdsByEndpoint => {
      const active: ActiveProbeModelIdsByEndpoint = {}
      for (const [endpointId, endpointModels] of inFlightByEndpoint) {
        const activeModelIds = [...endpointModels.keys()]
        if (activeModelIds.length > 0) active[endpointId] = activeModelIds
      }
      return active
    }
    const publish = () => onActiveProbeModelIdsByEndpointChange?.(activeByEndpoint())
    const startAtom = (endpointId: string, modelId: string) => {
      const endpointModels = inFlightByEndpoint.get(endpointId) ?? new Map<string, number>()
      endpointModels.set(modelId, (endpointModels.get(modelId) ?? 0) + 1)
      inFlightByEndpoint.set(endpointId, endpointModels)
    }
    const settleAtom = (endpointId: string, modelId: string) => {
      const endpointModels = inFlightByEndpoint.get(endpointId)
      if (!endpointModels) return
      const remaining = (endpointModels.get(modelId) ?? 1) - 1
      if (remaining <= 0) endpointModels.delete(modelId)
      else endpointModels.set(modelId, remaining)
      if (endpointModels.size === 0) inFlightByEndpoint.delete(endpointId)
    }
    // Always pass `description` (never omit it) so a new run REPLACES the
    // previous run's leftover subtitle instead of showing a stale model id
    // under the fresh "Testing…" title (PM 2026-07-03 toast-staleness bug).
    const refreshLoadingToast = () => {
      const active = inFlightIds()
      toast.loading(t("apiKeys.manualTest.testingLoading"), {
        id: toastId,
        description: (active.length > 0 ? active : trimmedModelIds).join(", "),
      })
    }
    refreshLoadingToast()
    try {
      const { results, models } = await probeModelsWithConcurrency(
        targetEndpointIds,
        trimmedModelIds,
        (endpointId, modelId) => testProviderModels({ provider_id: endpointId, model_ids: [modelId] }),
        {
          onStart: (task) => {
            startAtom(task.endpointId, task.modelId)
            publish()
            refreshLoadingToast()
          },
          onSettle: (task) => {
            settleAtom(task.endpointId, task.modelId)
            publish()
            refreshLoadingToast()
          },
        },
      )
      setResults(results)
      onModelsUpdated(models)
      const summary = manualModelToastSummary(results)
      toast[summary.kind](summary.title, { id: toastId, description: summary.description })
    } catch (testError) {
      setResults([])
      const message = composeRequestErrorMessage(testError, t("apiKeys.manualTest.testFailedFallback"))
      setError(message)
      toast.error(message, { id: toastId })
    } finally {
      inFlightByEndpoint.clear()
      publish()
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
            <div className="font-medium text-foreground">{t("apiKeys.manualTest.title")}</div>
            <div className="text-muted-foreground">{t("apiKeys.manualTest.description")}</div>
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
                  aria-label={t("apiKeys.manualTest.modelInputLabel", { index: index + 1 })}
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
                  aria-label={t("apiKeys.manualTest.removeModelLabel", { index: index + 1 })}
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
              {t("apiKeys.manualTest.addModel")}
            </Button>
            <Button type="button" size="sm" onClick={() => void runModelTests()} disabled={testing || trimmedModelIds.length === 0 || targetEndpointIds.length === 0}>
              {testing ? <Loader2 className="size-3.5 animate-spin" /> : null}
              {t("apiKeys.manualTest.testModels")}
            </Button>
          </div>
          {error ? <div className="text-destructive">{error}</div> : null}
          {hasTested && !testing && !error ? <ManualModelResultList results={results} /> : null}
        </AccordionContent>
      </AccordionItem>
    </Accordion>
  )
}
