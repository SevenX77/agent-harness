import { useCallback, useState } from 'react'
import type { Toast, ToastKind } from '../types/studio'

let toastIdFallbackCounter = 0

function newToastId(): string {
  if (typeof crypto !== 'undefined' && 'randomUUID' in crypto) {
    return crypto.randomUUID()
  }
  toastIdFallbackCounter += 1
  return `${Date.now()}-${toastIdFallbackCounter}`
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
