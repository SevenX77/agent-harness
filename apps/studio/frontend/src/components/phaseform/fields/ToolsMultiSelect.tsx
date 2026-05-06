import { Check, Plus, X } from 'lucide-react'
import { useState } from 'react'

interface ToolsMultiSelectProps {
  selected: string[]
  options: string[]
  onChange: (tools: string[]) => void
}

export function ToolsMultiSelect({ selected, options, onChange }: ToolsMultiSelectProps) {
  const [customTool, setCustomTool] = useState('')
  const allOptions = Array.from(new Set([...selected, ...options])).sort()

  const toggle = (tool: string) => {
    onChange(selected.includes(tool) ? selected.filter((item) => item !== tool) : [...selected, tool])
  }

  return (
    <section className="space-y-2">
      <div className="text-xs font-semibold uppercase text-slate-500 dark:text-slate-400">Tools</div>
      <div className="flex flex-wrap gap-2">
        {allOptions.length === 0 ? (
          <span className="text-xs text-slate-500 dark:text-slate-400">No tools discovered in this skill.</span>
        ) : null}
        {allOptions.map((tool) => {
          const active = selected.includes(tool)
          return (
            <button
              key={tool}
              type="button"
              onClick={() => toggle(tool)}
              className={`inline-flex items-center gap-1 rounded-full border px-2.5 py-1 text-xs font-medium ${
                active
                  ? 'border-sky-400 bg-sky-50 text-sky-700 dark:border-sky-700 dark:bg-sky-950/40 dark:text-sky-300'
                  : 'border-slate-300 text-slate-600 hover:bg-slate-50 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800'
              }`}
            >
              {active ? <Check className="h-3 w-3" /> : null}
              {tool}
            </button>
          )
        })}
      </div>
      {selected.length > 0 ? (
        <div className="flex flex-wrap gap-1.5">
          {selected.map((tool) => (
            <span
              key={`selected-${tool}`}
              className="inline-flex items-center gap-1 rounded bg-slate-100 px-2 py-1 text-xs font-mono text-slate-600 dark:bg-slate-800 dark:text-slate-300"
            >
              {tool}
              <button type="button" onClick={() => toggle(tool)} title={`Remove ${tool}`}>
                <X className="h-3 w-3" />
              </button>
            </span>
          ))}
        </div>
      ) : null}
      <div className="flex gap-2">
        <input
          value={customTool}
          onChange={(event) => setCustomTool(event.target.value)}
          placeholder="script.module.tool"
          className="min-w-0 flex-1 rounded-md border border-slate-300 bg-white px-3 py-2 text-xs font-mono text-slate-800 outline-none focus:ring-2 focus:ring-sky-500 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100"
        />
        <button
          type="button"
          onClick={() => {
            const next = customTool.trim()
            if (!next || selected.includes(next)) {
              return
            }
            onChange([...selected, next])
            setCustomTool('')
          }}
          className="inline-flex items-center gap-1 rounded-md border border-slate-300 px-3 py-2 text-xs font-medium text-slate-700 hover:bg-slate-50 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800"
        >
          <Plus className="h-3.5 w-3.5" />
          Add
        </button>
      </div>
    </section>
  )
}
