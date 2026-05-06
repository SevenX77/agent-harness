import { useCallback, useState } from 'react'
import type { Toast, ToastKind } from '../types/studio'

function newToastId(): string {
  return typeof crypto !== 'undefined' && 'randomUUID' in crypto
    ? crypto.randomUUID()
    : `${Date.now()}-${Math.random()}`
}

export function useToasts() {
  const [toasts, setToasts] = useState<Toast[]>([])

  const pushToast = useCallback((message: string, kind: ToastKind = 'info') => {
    const id = newToastId()
    setToasts((items) => [...items, { id, kind, message }])
    window.setTimeout(() => {
      setToasts((items) => items.filter((item) => item.id !== id))
    }, 4500)
  }, [])

  return { toasts, pushToast }
}
