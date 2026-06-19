import { useEffect, useState } from 'react'
import { api } from '../api/client'
import type { LintError, LintResult } from '../api/types'
import type { LintStatus } from '../types/studio'

export const lintStatusEvent = 'studio-lint-status-changed'

/** Realtime-lint debounce window: edit → wait → POST /lint (workflow 03_compile A1: 800ms). */
export const LINT_DEBOUNCE_MS = 800

export function lintStatusStorageKey(skillId: string) {
  return `studio-lint-status-${skillId}`
}

function publishLintStatus(skillId: string, status: LintStatus) {
  if (typeof window === 'undefined' || !skillId) {
    return
  }

  sessionStorage.setItem(lintStatusStorageKey(skillId), status)
  window.dispatchEvent(new CustomEvent(lintStatusEvent, { detail: { skillId, status } }))
}

export function readLintStatus(skillId: string): LintStatus {
  if (typeof window === 'undefined' || !skillId) {
    return 'idle'
  }

  const status = sessionStorage.getItem(lintStatusStorageKey(skillId))
  return status === 'checking' || status === 'passed' || status === 'failed' ? status : 'idle'
}

/**
 * Project the backend lint payload to the diagnostics the lint panel renders.
 *
 * Single source of truth = the engine's `LintResult.errors` (workflow 03_compile A10
 * keeps compile/lint checks engine-owned; the panel must not invent a second list).
 * A passed lint, a null payload, or a payload with no `errors` array all map to an
 * empty diagnostics list so the panel collapses while the edit is clean / in-flight.
 */
export function deriveLintDiagnostics(result: LintResult | null | undefined): LintError[] {
  if (!result || !Array.isArray(result.errors)) {
    return []
  }
  return result.errors
}

/**
 * One-line `file:line - code - message` projection of a single diagnostic, shared by
 * the panel rows and the copy-to-clipboard digest. Mirrors the compile drawer's
 * `formatCompileErrorLine` so lint and compile read identically. Falls back to
 * "unknown file" (dropping the line) when the engine could not attribute a file, and
 * carries the engine error code (F-v3-*) as the middle segment so a copied diagnostic
 * stays actionable when pasted to Copilot.
 */
export function formatLintDiagnostic(error: LintError): string {
  const locator = error.file ? `${error.file}${error.line ? `:${error.line}` : ''}` : 'unknown file'
  const code = error.error_code || null
  const segments = code ? [locator, code, error.message] : [locator, error.message]
  return segments.join(' - ')
}

export function useDebouncedLint(skillId: string, markdown: string) {
  const [status, setStatus] = useState<LintStatus>('idle')
  const [result, setResult] = useState<LintResult | null>(null)
  const [message, setMessage] = useState<string | null>(null)

  useEffect(() => {
    if (!skillId || markdown.trim().length === 0) {
      setStatus('idle')
      setResult(null)
      setMessage(null)
      publishLintStatus(skillId, 'idle')
      return undefined
    }

    setStatus('checking')
    setMessage(null)
    publishLintStatus(skillId, 'checking')

    const timeout = window.setTimeout(() => {
      api.post<LintResult>(`/skills/${skillId}/lint`, { markdown })
        .then((response) => {
          const nextStatus = response.data.status === 'passed' ? 'passed' : 'failed'
          setResult(response.data)
          setStatus(nextStatus)
          publishLintStatus(skillId, nextStatus)
        })
        .catch((error: unknown) => {
          setResult(null)
          setStatus('failed')
          setMessage(error instanceof Error ? error.message : 'Lint request failed')
          publishLintStatus(skillId, 'failed')
        })
    }, LINT_DEBOUNCE_MS)

    return () => window.clearTimeout(timeout)
  }, [markdown, skillId])

  return { status, result, message, errors: deriveLintDiagnostics(result) }
}
