import { useSyncExternalStore } from "react"

const emptyModelIds: readonly string[] = Object.freeze([])
const activeModelIdsByEndpoint = new Map<string, readonly string[]>()
const endpointListeners = new Map<string, Set<() => void>>()
const atomListeners = new Map<string, Set<() => void>>()

function atomKey(endpointId: string, modelId: string): string {
  return `${endpointId}\u0000${modelId}`
}

export function probeAtomDomKey(endpointId: string, modelId: string): string {
  return `${encodeURIComponent(endpointId)}:${encodeURIComponent(modelId)}`
}

function cssString(value: string): string {
  if (typeof CSS !== "undefined" && typeof CSS.escape === "function") {
    return CSS.escape(value)
  }
  return value.replace(/\\/g, "\\\\").replace(/"/g, "\\\"")
}

function uniqueModelIds(modelIds: readonly string[]): readonly string[] {
  return Array.from(new Set(modelIds.filter(Boolean)))
}

function modelIdListsEqual(left: readonly string[], right: readonly string[]): boolean {
  return left.length === right.length && left.every((value, index) => value === right[index])
}

function notify(listeners: Map<string, Set<() => void>>, key: string): void {
  for (const listener of listeners.get(key) ?? []) listener()
}

function changedModelIds(previous: readonly string[], next: readonly string[]): string[] {
  return Array.from(new Set([...previous, ...next]))
}

function applyEndpointAnimation(endpointId: string, active: boolean): void {
  if (typeof document === "undefined") return
  const selector = `[data-probe-endpoint-id="${cssString(endpointId)}"]`
  for (const element of document.querySelectorAll<HTMLElement>(selector)) {
    element.classList.toggle("api-route-tag-border-flow", active)
    if (active) element.dataset.probeActive = "true"
    else delete element.dataset.probeActive
    for (const spinner of element.querySelectorAll<HTMLElement>("[data-probe-spinner]")) {
      spinner.classList.toggle("hidden", !active)
    }
  }
}

function modelElementHasActiveAtom(element: HTMLElement, modelId: string): boolean {
  const keys = new Set((element.dataset.probeModelKeys ?? "").split(/\s+/).filter(Boolean))
  if (keys.size === 0) return false
  for (const [endpointId, activeModelIds] of activeModelIdsByEndpoint) {
    if (activeModelIds.includes(modelId) && keys.has(probeAtomDomKey(endpointId, modelId))) {
      return true
    }
  }
  return false
}

function applyModelAnimation(endpointId: string, modelId: string, active: boolean): void {
  if (typeof document === "undefined") return
  const key = probeAtomDomKey(endpointId, modelId)
  const selector = `[data-probe-model-keys~="${cssString(key)}"]`
  for (const element of document.querySelectorAll<HTMLElement>(selector)) {
    const shouldAnimate = active || modelElementHasActiveAtom(element, modelId)
    element.classList.toggle("api-route-tag-border-flow", shouldAnimate)
    if (shouldAnimate) element.dataset.probeActive = "true"
    else delete element.dataset.probeActive
  }
}

export function updateActiveProbeEndpoint(endpointId: string, modelIds: readonly string[]): void {
  const previous = activeModelIdsByEndpoint.get(endpointId) ?? emptyModelIds
  const next = uniqueModelIds(modelIds)
  if (modelIdListsEqual(previous, next)) return

  if (next.length > 0) activeModelIdsByEndpoint.set(endpointId, next)
  else activeModelIdsByEndpoint.delete(endpointId)

  notify(endpointListeners, endpointId)
  applyEndpointAnimation(endpointId, next.length > 0)
  for (const modelId of changedModelIds(previous, next)) {
    applyModelAnimation(endpointId, modelId, next.includes(modelId))
    notify(atomListeners, atomKey(endpointId, modelId))
  }
}

export function clearActiveProbeEndpoint(endpointId: string): void {
  updateActiveProbeEndpoint(endpointId, emptyModelIds)
}

export function clearActiveProbeEndpoints(endpointIds: readonly string[]): void {
  for (const endpointId of endpointIds) clearActiveProbeEndpoint(endpointId)
}

export function getActiveProbeModelIds(endpointId: string): readonly string[] {
  return activeModelIdsByEndpoint.get(endpointId) ?? emptyModelIds
}

export function hasActiveProbeEndpoint(endpointId: string): boolean {
  return getActiveProbeModelIds(endpointId).length > 0
}

export function hasActiveProbeAtom(endpointId: string, modelId: string): boolean {
  return getActiveProbeModelIds(endpointId).includes(modelId)
}

export function subscribeActiveProbeEndpoint(endpointId: string, listener: () => void): () => void {
  const listeners = endpointListeners.get(endpointId) ?? new Set<() => void>()
  listeners.add(listener)
  endpointListeners.set(endpointId, listeners)
  return () => {
    listeners.delete(listener)
    if (listeners.size === 0) endpointListeners.delete(endpointId)
  }
}

export function subscribeActiveProbeAtom(endpointId: string, modelId: string, listener: () => void): () => void {
  const key = atomKey(endpointId, modelId)
  const listeners = atomListeners.get(key) ?? new Set<() => void>()
  listeners.add(listener)
  atomListeners.set(key, listeners)
  return () => {
    listeners.delete(listener)
    if (listeners.size === 0) atomListeners.delete(key)
  }
}

export function useActiveProbeEndpoint(endpointId: string): boolean {
  return useSyncExternalStore(
    (listener) => subscribeActiveProbeEndpoint(endpointId, listener),
    () => hasActiveProbeEndpoint(endpointId),
    () => hasActiveProbeEndpoint(endpointId),
  )
}

export function useActiveProbeModel(endpointIds: readonly string[], modelId: string): boolean {
  return useSyncExternalStore(
    (listener) => {
      const unsubscribers = endpointIds.map((endpointId) => (
        subscribeActiveProbeAtom(endpointId, modelId, listener)
      ))
      return () => {
        for (const unsubscribe of unsubscribers) unsubscribe()
      }
    },
    () => endpointIds.some((endpointId) => hasActiveProbeAtom(endpointId, modelId)),
    () => endpointIds.some((endpointId) => hasActiveProbeAtom(endpointId, modelId)),
  )
}
