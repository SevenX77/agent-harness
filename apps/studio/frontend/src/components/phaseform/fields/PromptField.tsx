import { ChevronDown, ChevronRight } from 'lucide-react'
import { useState } from 'react'
import { PhaseTokenCounter } from './PhaseTokenCounter'

interface PromptFieldProps {
  label: string
  value: string
  error?: string
  onChange: (value: string) => void
}

export function PromptField({ label, value, error, onChange }: PromptFieldProps) {
  const [collapsed, setCollapsed] = useState(false)

  return (
    <section className="rounded-md border border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900">
      <button
        type="button"
        onClick={() => setCollapsed((current) => !current)}
        className="flex w-full items-center justify-between px-3 py-2 text-start"
      >
        <span className="text-xs font-semibold uppercase text-slate-500 dark:text-slate-400">{label}</span>
        {collapsed ? <ChevronRight className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
      </button>
      {!collapsed ? (
        <div className="space-y-2 border-t border-slate-200 p-3 dark:border-slate-800">
          <textarea
            value={value}
            onChange={(event) => onChange(event.target.value)}
            rows={Math.min(18, Math.max(6, value.split('\n').length + 2))}
            className="w-full resize-y rounded-md border border-slate-300 bg-white px-3 py-2 font-mono text-xs leading-5 text-slate-800 outline-none focus:ring-2 focus:ring-sky-500 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-100"
          />
          <div className="flex items-center justify-between gap-3">
            <PhaseTokenCounter text={value} />
            {error ? <span className="text-xs text-red-600 dark:text-red-400">{error}</span> : null}
          </div>
        </div>
      ) : null}
    </section>
  )
}
