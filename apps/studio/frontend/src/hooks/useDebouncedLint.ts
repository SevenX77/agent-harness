import { useEffect, useState } from 'react'
import { api } from '../api/client'
import type { LintResult } from '../api/types'
import type { LintStatus } from '../types/studio'

export const lintStatusEvent = 'studio-lint-status-changed'

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
    }, 800)

    return () => window.clearTimeout(timeout)
  }, [markdown, skillId])

  return { status, result, message }
}
