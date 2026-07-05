import { describe, expect, it, vi } from "vitest"
import type { ProviderModelTestResponse } from "../../../api/llm"
import {
  MODEL_PROBE_CONCURRENCY,
  buildAtomicProbeTasks,
  hasActiveAtomicProbeSignal,
  probeModelsWithConcurrency,
  runWithConcurrency,
} from "./model-probe-runner"

function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>((r) => { resolve = r })
  return { promise, resolve }
}

describe("runWithConcurrency — bounded-concurrency pool", () => {
  it("never runs more than `limit` workers at once and completes every item", async () => {
    let inFlight = 0
    let peak = 0
    const gates = Array.from({ length: 9 }, () => deferred<void>())
    const started: number[] = []

    const promise = runWithConcurrency([0, 1, 2, 3, 4, 5, 6, 7, 8], 3, async (item) => {
      inFlight += 1
      peak = Math.max(peak, inFlight)
      started.push(item)
      await gates[item].promise
      inFlight -= 1
      return item * 10
    })

    // Let the pool fill; only the first 3 should be running with limit=3.
    await Promise.resolve()
    await Promise.resolve()
    expect(started).toEqual([0, 1, 2])

    // Release one; exactly one more should start (sliding window, not batch).
    gates[0].resolve()
    await Promise.resolve()
    await Promise.resolve()
    expect(started).toEqual([0, 1, 2, 3])

    for (const gate of gates) gate.resolve()
    const results = await promise
    expect(peak).toBe(3)
    expect(results).toEqual([0, 10, 20, 30, 40, 50, 60, 70, 80]) // order preserved
  })

  it("treats limit larger than the item count as run-all-at-once", async () => {
    let peak = 0
    let inFlight = 0
    const results = await runWithConcurrency([1, 2], 10, async (item) => {
      inFlight += 1
      peak = Math.max(peak, inFlight)
      await Promise.resolve()
      inFlight -= 1
      return item
    })
    expect(peak).toBeLessThanOrEqual(2)
    expect(results).toEqual([1, 2])
  })
})

describe("buildAtomicProbeTasks", () => {
  it("expands endpoints × models into one atomic (endpoint, model) task each", () => {
    expect(buildAtomicProbeTasks(["e1", "e2"], ["m1", "m2"])).toEqual([
      { endpointId: "e1", modelId: "m1" },
      { endpointId: "e1", modelId: "m2" },
      { endpointId: "e2", modelId: "m1" },
      { endpointId: "e2", modelId: "m2" },
    ])
  })
})

describe("hasActiveAtomicProbeSignal", () => {
  it("treats only a live route testing state as an animated model signal", () => {
    expect(hasActiveAtomicProbeSignal({ status: "testing" })).toBe(true)
    expect(hasActiveAtomicProbeSignal({
      modelId: "anthropic/claude-opus-4.8",
      activeModelIds: ["anthropic/claude-opus-4.8"],
      status: "verified",
    })).toBe(true)

    expect(hasActiveAtomicProbeSignal({ status: "unverified_manual" })).toBe(false)
    expect(hasActiveAtomicProbeSignal({ status: "verified" })).toBe(false)
    expect(hasActiveAtomicProbeSignal({
      modelId: "openai/gpt-5.5",
      activeModelIds: ["anthropic/claude-opus-4.8"],
      status: "verified",
    })).toBe(false)
    expect(hasActiveAtomicProbeSignal({ probeAttemptStatuses: ["ok"] })).toBe(false)
    expect(hasActiveAtomicProbeSignal({ reasonCode: "ok" })).toBe(false)
    expect(hasActiveAtomicProbeSignal({ probeAttemptStatuses: [] })).toBe(false)
  })
})

describe("probeModelsWithConcurrency — atomic per-(endpoint,model) probes", () => {
  const okResponse = (modelId: string): ProviderModelTestResponse => ({
    results: [{ model_id: modelId, status: "ok", message: null }],
    available_models: [{ id: modelId, status: "verified", ui_state: "ready" }],
  })
  const failResponse = (modelId: string): ProviderModelTestResponse => ({
    results: [{ model_id: modelId, status: "quota_exceeded", message: "no quota" }],
    available_models: [],
  })

  it("probes each (endpoint, model) atomically — one model per call, never a batch", async () => {
    const calls: Array<{ endpointId: string; modelIds: string[] }> = []
    const probe = vi.fn(async (endpointId: string, modelId: string) => {
      calls.push({ endpointId, modelIds: [modelId] })
      return okResponse(modelId)
    })

    await probeModelsWithConcurrency(["e1", "e2"], ["m1", "m2"], probe)

    expect(probe).toHaveBeenCalledTimes(4)
    // every call carries exactly ONE model id (atomic), never a multi-model batch
    expect(calls.every((call) => call.modelIds.length === 1)).toBe(true)
  })

  it("keeps the best result per model across endpoints (ok on any endpoint wins)", async () => {
    const probe = vi.fn(async (endpointId: string, modelId: string) =>
      endpointId === "e2" ? okResponse(modelId) : failResponse(modelId),
    )
    const { results } = await probeModelsWithConcurrency(["e1", "e2"], ["m1"], probe)
    expect(results).toHaveLength(1)
    expect(results[0]).toMatchObject({ model_id: "m1", status: "ok" })
  })

  it("fires onStart before and onSettle after each atomic probe (drives per-model UI)", async () => {
    const events: string[] = []
    const probe = async (_endpointId: string, modelId: string) => okResponse(modelId)
    await probeModelsWithConcurrency(["e1"], ["m1", "m2"], probe, {
      onStart: (task) => events.push(`start:${task.modelId}`),
      onSettle: (task) => events.push(`settle:${task.modelId}`),
    }, 1)
    expect(events).toEqual(["start:m1", "settle:m1", "start:m2", "settle:m2"])
  })

  it("records a failure for a model when its endpoint probe throws, without aborting the rest", async () => {
    const probe = async (_endpointId: string, modelId: string) => {
      if (modelId === "m1") throw new Error("boom")
      return okResponse(modelId)
    }
    const settled: string[] = []
    const { results } = await probeModelsWithConcurrency(["e1"], ["m1", "m2"], probe, {
      onSettle: (task) => settled.push(task.modelId),
    }, 1)
    expect(settled).toEqual(["m1", "m2"]) // both settled despite m1 throwing
    const m1 = results.find((r) => r.model_id === "m1")
    const m2 = results.find((r) => r.model_id === "m2")
    expect(m1?.status).toBe("error")
    expect(m2?.status).toBe("ok")
  })

  it("defaults to a concurrency of 3", () => {
    expect(MODEL_PROBE_CONCURRENCY).toBe(3)
  })
})
