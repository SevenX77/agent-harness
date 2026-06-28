import { useCallback, useEffect, useState } from 'react'
import useSWR from 'swr'
import { api, fetcher } from '../api/client'
import type {
  BatchRunRequest,
  BatchRunResponse,
  BatchRunStatus,
  TestInputMetadata,
} from '../api/types'
import { errorMessage } from '../utils/errors'

export function useBatchRun(skillId: string | null) {
  const {
    data: inputs,
    error: inputsError,
    isLoading: inputsLoading,
    mutate: refreshInputs,
  } = useSWR<TestInputMetadata[]>(skillId ? `/skills/${skillId}/test_inputs` : null, fetcher)
  const [selectedInputIds, setSelectedInputIds] = useState<string[]>([])
  const [batchId, setBatchId] = useState<string | null>(null)
  const [batchStatus, setBatchStatus] = useState<BatchRunStatus | null>(null)
  const [batchRunning, setBatchRunning] = useState(false)
  const [batchError, setBatchError] = useState<string | null>(null)

  useEffect(() => {
    setSelectedInputIds([])
    setBatchId(null)
    setBatchStatus(null)
    setBatchRunning(false)
    setBatchError(null)
  }, [skillId])

  useEffect(() => {
    if (!batchId || !batchRunning) {
      return
    }

    let cancelled = false
    const poll = async () => {
      try {
        const response = await api.get<BatchRunStatus>(`/batch/${batchId}`)
        if (cancelled) {
          return
        }
        setBatchStatus(response.data)
        setBatchRunning(response.data.status === 'running')
      } catch (error) {
        if (!cancelled) {
          setBatchError(errorMessage(error))
          setBatchRunning(false)
        }
      }
    }

    void poll()
    const interval = window.setInterval(() => {
      void poll()
    }, 1000)
    return () => {
      cancelled = true
      window.clearInterval(interval)
    }
  }, [batchId, batchRunning])

  const toggleInput = useCallback((inputId: string) => {
    setSelectedInputIds((current) => (
      current.includes(inputId)
        ? current.filter((item) => item !== inputId)
        : [...current, inputId]
    ))
  }, [])

  // `inputIds` lets a caller run an explicit set in the same tick (e.g. the C10
  // naming-sequence suggestion), bypassing the async setState of the selection.
  const runBatch = useCallback(async (inputIds?: readonly string[]) => {
    const targetIds = inputIds && inputIds.length > 0 ? Array.from(inputIds) : selectedInputIds
    if (!skillId || targetIds.length === 0) {
      return null
    }
    if (inputIds && inputIds.length > 0) {
      setSelectedInputIds(targetIds)
    }

    setBatchError(null)
    setBatchRunning(true)
    try {
      const payload: BatchRunRequest = { input_ids: targetIds }
      const response = await api.post<BatchRunResponse>(`/skills/${skillId}/runs/batch-run`, payload)
      setBatchId(response.data.batch_id)
      return response.data
    } catch (error) {
      setBatchError(errorMessage(error))
      setBatchRunning(false)
      return null
    }
  }, [selectedInputIds, skillId])

  return {
    inputs: inputs ?? [],
    selectedInputIds,
    batchStatus,
    inputsLoading,
    batchRunning,
    batchError: batchError ?? (inputsError ? errorMessage(inputsError) : null),
    refreshInputs,
    toggleInput,
    runBatch,
  }
}
