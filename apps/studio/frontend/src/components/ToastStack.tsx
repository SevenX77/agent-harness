import type { Toast } from '../types/studio'

interface ToastStackProps {
  toasts: Toast[]
}

export function ToastStack({ toasts }: ToastStackProps) {
  return (
    <div className="fixed bottom-4 right-4 z-50 space-y-2">
      {toasts.map((toast) => (
        <div
          key={toast.id}
          className={`rounded-md border px-4 py-3 text-sm shadow-lg ${
            toast.kind === 'success'
              ? 'border-green-200 dark:border-green-900/50 bg-green-50 dark:bg-green-900/20 text-green-800 dark:text-green-400'
              : toast.kind === 'error'
                ? 'border-red-200 dark:border-red-900/50 bg-red-50 dark:bg-red-900/20 text-red-800 dark:text-red-400'
                : 'border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 text-slate-700 dark:text-slate-300'
          }`}
        >
          {toast.message}
        </div>
      ))}
    </div>
  )
}
