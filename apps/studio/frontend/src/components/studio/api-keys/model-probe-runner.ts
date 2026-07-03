import type { ModelInfo, ProviderModelTestResponse, ProviderModelTestResult } from "../../../api/llm"

/** Merge discovered model chips, keeping the first-seen metadata per id. */
export function mergeModelLists(existing: ModelInfo[], incoming: ModelInfo[]): ModelInfo[] {
  const byId = new Map(existing.map((model) => [model.id, model]))
  for (const model of incoming) {
    if (!byId.has(model.id)) byId.set(model.id, model)
  }
  return [...byId.values()]
}

// W1-B / R-E5: a manual model test fans out across EVERY configured endpoint of
// the provider (including failed/disabled). Collapse the per-endpoint results to
// one row per model, preferring a success — a model that works on at least one
// base_url is usable.
export function aggregateModelResults(results: ProviderModelTestResult[]): ProviderModelTestResult[] {
  const byModel = new Map<string, ProviderModelTestResult>()
  for (const result of results) {
    const existing = byModel.get(result.model_id)
    if (!existing || (result.status === "ok" && existing.status !== "ok")) {
      byModel.set(result.model_id, result)
    }
  }
  return [...byModel.values()]
}

/**
 * The single atomic unit of an LLM test: prove ONE model on ONE (URL, protocol)
 * endpoint. Everything — the endpoint "Test", the ↻ re-probe, and manual model
 * probing — is built out of this one probe so a single code path owns "who is
 * being tested right now" (which in turn drives per-model animation + toast),
 * instead of every caller deriving it from card-wide flags.
 */
export interface AtomicProbeTask {
  endpointId: string
  modelId: string
}

/** PM 2026-07-03: probe at most this many (endpoint, model) cells at once. */
export const MODEL_PROBE_CONCURRENCY = 3

export interface ProbeRunHooks {
  onStart?: (task: AtomicProbeTask) => void
  onSettle?: (task: AtomicProbeTask, result: ProviderModelTestResult) => void
}

/**
 * Run `worker` over `items` with at most `limit` in flight at once. A true
 * sliding window (not fixed batches): the moment one worker finishes it pulls
 * the next item, so N stay busy until the queue drains. Results keep input order.
 */
export async function runWithConcurrency<T, R>(
  items: readonly T[],
  limit: number,
  worker: (item: T, index: number) => Promise<R>,
): Promise<R[]> {
  const results = new Array<R>(items.length)
  let cursor = 0
  const runOne = async (): Promise<void> => {
    for (;;) {
      const index = cursor
      cursor += 1
      if (index >= items.length) return
      results[index] = await worker(items[index], index)
    }
  }
  const poolSize = Math.max(1, Math.min(limit, items.length))
  await Promise.all(Array.from({ length: poolSize }, () => runOne()))
  return results
}

export function buildAtomicProbeTasks(endpointIds: string[], modelIds: string[]): AtomicProbeTask[] {
  return endpointIds.flatMap((endpointId) => modelIds.map((modelId) => ({ endpointId, modelId })))
}

/**
 * Probe every (endpoint, model) pair atomically — one model per backend call —
 * with a bounded concurrency of `limit` (default 3). Each task fires
 * `hooks.onStart` before its probe and `hooks.onSettle` after, so the caller can
 * light up exactly the model being tested. A single probe throwing records an
 * `error` for that pair and never aborts the rest; results are collapsed to one
 * row per model (a model that works on any endpoint is usable).
 */
export async function probeModelsWithConcurrency(
  endpointIds: string[],
  modelIds: string[],
  probe: (endpointId: string, modelId: string) => Promise<ProviderModelTestResponse>,
  hooks: ProbeRunHooks = {},
  limit: number = MODEL_PROBE_CONCURRENCY,
): Promise<{ results: ProviderModelTestResult[]; models: ModelInfo[] }> {
  const tasks = buildAtomicProbeTasks(endpointIds, modelIds)
  const collected: ProviderModelTestResult[] = []
  let models: ModelInfo[] = []

  await runWithConcurrency(tasks, limit, async (task) => {
    hooks.onStart?.(task)
    let result: ProviderModelTestResult
    try {
      const response = await probe(task.endpointId, task.modelId)
      result =
        response.results.find((item) => item.model_id === task.modelId) ??
        response.results[0] ?? { model_id: task.modelId, status: "error", message: null }
      models = mergeModelLists(models, response.available_models)
    } catch {
      result = { model_id: task.modelId, status: "error", message: null }
    }
    collected.push(result)
    hooks.onSettle?.(task, result)
  })

  return { results: aggregateModelResults(collected), models }
}
