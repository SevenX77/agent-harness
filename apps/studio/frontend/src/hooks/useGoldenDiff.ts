import { useCallback, useState } from 'react'
import { api, saveGoldenBaseline } from '../api/client'
import type { CompareResult } from '../api/types'
import { errorMessage } from '../utils/errors'

interface GoldenDiffState {
  result: CompareResult | null
  loading: boolean
  error: string | null
}

export function useGoldenDiff(
  skillId: string | null,
  runId: string | null,
  workspaceRoot?: string | null,
) {
  const [state, setState] = useState<GoldenDiffState>({
    result: null,
    loading: false,
    error: null,
  })

  const compare = useCallback(async (against?: string | null, runIdOverride?: string | null) => {
    const targetRunId = runIdOverride ?? runId
    if (!skillId || !targetRunId) {
      return null
    }

    setState((current) => ({ ...current, loading: true, error: null }))
    try {
      const response = await api.get<CompareResult>(`/skills/${skillId}/runs/${targetRunId}/compare`, {
        params: against ? { against } : undefined,
      })
      setState({ result: response.data, loading: false, error: null })
      return response.data
    } catch (error) {
      const message = errorMessage(error)
      setState((current) => ({ ...current, loading: false, error: message }))
      return null
    }
  }, [runId, skillId])

  const promote = useCallback(async () => {
    if (!skillId || !runId) {
      return null
    }

    setState((current) => ({ ...current, error: null }))
    try {
      return await saveGoldenBaseline(skillId, runId, false, workspaceRoot)
    } catch (error) {
      const message = errorMessage(error)
      setState((current) => ({ ...current, error: message }))
      return null
    }
  }, [runId, skillId, workspaceRoot])

  const clear = useCallback(() => {
    setState({ result: null, loading: false, error: null })
  }, [])

  return {
    ...state,
    compare,
    promote,
    clear,
  }
}
