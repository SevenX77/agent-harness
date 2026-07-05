import { useCallback, useEffect, useMemo, useRef } from "react"

export interface DebouncedCallback<TArgs extends unknown[]> {
  schedule: (...args: TArgs) => void
  flush: () => void
  cancel: () => void
}

export function useDebouncedCallback<TArgs extends unknown[]>(
  callback: (...args: TArgs) => void,
  delayMs: number,
): DebouncedCallback<TArgs> {
  const callbackRef = useRef(callback)
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const pendingArgsRef = useRef<TArgs | null>(null)

  callbackRef.current = callback

  const cancel = useCallback(() => {
    if (timerRef.current) {
      clearTimeout(timerRef.current)
      timerRef.current = null
    }
    pendingArgsRef.current = null
  }, [])

  const flush = useCallback(() => {
    if (timerRef.current) {
      clearTimeout(timerRef.current)
      timerRef.current = null
    }
    const args = pendingArgsRef.current
    pendingArgsRef.current = null
    if (args) {
      callbackRef.current(...args)
    }
  }, [])

  const schedule = useCallback(
    (...args: TArgs) => {
      if (timerRef.current) clearTimeout(timerRef.current)
      pendingArgsRef.current = args
      timerRef.current = setTimeout(() => {
        timerRef.current = null
        flush()
      }, delayMs)
    },
    [delayMs, flush],
  )

  useEffect(() => cancel, [cancel])

  return useMemo(() => ({ schedule, flush, cancel }), [cancel, flush, schedule])
}
