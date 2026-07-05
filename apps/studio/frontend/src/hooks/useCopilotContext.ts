import { useEffect, useMemo } from 'react'
import { api } from '../api/client'
import type { JsonValue } from '../api/types'
import type { CopilotView } from '../types/copilot'

const CONTEXT_THRESHOLD_BYTES = 65536
const lastPostedContextByScope = new Map<string, string>()

interface UseCopilotContextConfig {
  skillId: string | null
  view: CopilotView
  context: Record<string, JsonValue>
  debounceMs?: number
}

export function fingerprintText(value: string): string {
  let hash = 2166136261
  for (let index = 0; index < value.length; index += 1) {
    hash ^= value.charCodeAt(index)
    hash = Math.imul(hash, 16777619)
  }
  return (hash >>> 0).toString(16)
}

export function compactCopilotContext(context: Record<string, JsonValue>) {
  const raw = JSON.stringify(context)
  const bytes = new TextEncoder().encode(raw).byteLength
  if (bytes <= CONTEXT_THRESHOLD_BYTES) {
    return context
  }

  return {
    summary: `Context exceeds ${CONTEXT_THRESHOLD_BYTES} bytes; full payload omitted.`,
    fingerprint: fingerprintText(raw),
    byte_length: bytes,
    keys: Object.keys(context),
  } satisfies Record<string, JsonValue>
}

export function resetCopilotContextPostCacheForTests(): void {
  lastPostedContextByScope.clear()
}

export function useCopilotContext({
  skillId,
  view,
  context,
  debounceMs = 800,
}: UseCopilotContextConfig) {
  const compactContext = useMemo(() => compactCopilotContext(context), [context])
  const serialized = useMemo(() => JSON.stringify(compactContext), [compactContext])

  useEffect(() => {
    if (!skillId) {
      return undefined
    }
    const scopeKey = `${skillId}\0${view}`
    if (lastPostedContextByScope.get(scopeKey) === serialized) {
      return undefined
    }

    const timeout = window.setTimeout(() => {
      lastPostedContextByScope.set(scopeKey, serialized)
      void api.post(`/skills/${skillId}/copilot/context`, {
        view,
        context: compactContext,
        timestamp: Date.now(),
      })
    }, debounceMs)

    return () => window.clearTimeout(timeout)
  }, [compactContext, debounceMs, serialized, skillId, view])

  return {
    context: compactContext,
    fingerprint: fingerprintText(serialized),
  }
}
