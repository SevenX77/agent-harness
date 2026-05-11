import { CheckCircle, MessageSquare, X } from 'lucide-react'
import { useState } from 'react'
import type { CallbackEvent } from '../api/types'
import { eventPhase, jsonText } from '../utils/trace'

interface PromptInspectorProps {
  promptEvent: CallbackEvent | null
  onClose: () => void
}

export function PromptInspector({ promptEvent, onClose }: PromptInspectorProps) {
  const [tab, setTab] = useState<'template' | 'variables' | 'rendered'>('template')

  if (!promptEvent) {
    return null
  }

  const tabs = [
    ['template', 'Template'],
    ['variables', 'Variables'],
    ['rendered', 'Rendered'],
  ] as const

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 dark:bg-black/80 p-8">
      <div className="flex h-[80vh] w-full max-w-5xl flex-col overflow-hidden rounded-md bg-white dark:bg-slate-900 shadow-2xl border dark:border-slate-800">
        <div className="flex items-center justify-between border-b border-gray-200 dark:border-slate-800 bg-gray-50 dark:bg-slate-950 px-6 py-4">
          <h3 className="flex items-center gap-2 text-lg font-bold text-gray-800 dark:text-gray-100">
            <MessageSquare className="h-5 w-5 text-violet-600 dark:text-violet-400" />
            Prompt Inspector: {eventPhase(promptEvent)}
          </h3>
          <button type="button" onClick={onClose} className="rounded p-1 text-gray-500 hover:bg-gray-100 dark:hover:bg-slate-800 dark:text-gray-400 hover:text-gray-800 dark:hover:text-gray-100">
            <X className="h-5 w-5" />
          </button>
        </div>

        <div className="flex min-h-0 flex-1 flex-col overflow-hidden p-6">
          <div className="mb-4 flex gap-2">
            {tabs.map(([id, label]) => (
              <button
                key={id}
                type="button"
                onClick={() => setTab(id)}
                className={`h-9 rounded-md border px-3 text-sm font-medium ${
                  tab === id
                    ? 'border-violet-300 bg-violet-50 text-violet-700 dark:border-violet-800 dark:bg-violet-900/30 dark:text-violet-300'
                    : 'border-gray-200 text-gray-600 hover:bg-gray-50 dark:border-slate-800 dark:text-gray-300 dark:hover:bg-slate-800'
                }`}
              >
                {label}
              </button>
            ))}
          </div>
          <pre className="min-h-0 flex-1 overflow-auto rounded-md border border-gray-200 bg-gray-50 p-4 text-sm whitespace-pre-wrap text-gray-800 dark:border-slate-800 dark:bg-slate-950 dark:text-gray-300">
            {tab === 'template' ? (promptEvent.template_source ?? 'inline') : null}
            {tab === 'variables' ? jsonText(promptEvent.variables) : null}
            {tab === 'rendered' ? (
              promptEvent.event_type === 'prompt_captured' ? jsonText(promptEvent.resolved_prompt) : jsonText(promptEvent.messages ?? undefined)
            ) : null}
          </pre>
          {tab === 'rendered' ? (
            <div className="mt-3 flex items-center gap-1 text-xs font-bold text-violet-700 dark:text-violet-400">
              <CheckCircle className="h-3 w-3" />
              Rendered prompt payload
            </div>
          ) : null}
        </div>
      </div>
    </div>
  )
}
