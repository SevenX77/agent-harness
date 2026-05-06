import { CheckCircle, MessageSquare, X } from 'lucide-react'
import type { CallbackEvent } from '../api/types'
import { eventPhase, jsonText } from '../utils/trace'

interface PromptInspectorProps {
  promptEvent: CallbackEvent | null
  onClose: () => void
}

export function PromptInspector({ promptEvent, onClose }: PromptInspectorProps) {
  if (!promptEvent) {
    return null
  }

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

        <div className="grid flex-1 grid-cols-3 gap-4 overflow-hidden p-6">
          <div className="flex flex-col overflow-hidden rounded-md border border-gray-200 dark:border-slate-800">
            <div className="border-b border-gray-200 dark:border-slate-800 bg-gray-100 dark:bg-slate-800 px-3 py-2 text-xs font-bold text-gray-600 dark:text-gray-400">Template Source</div>
            <pre className="flex-1 overflow-y-auto bg-gray-50 dark:bg-slate-950 p-3 text-sm whitespace-pre-wrap dark:text-gray-300">{promptEvent.template_source ?? 'inline'}</pre>
          </div>
          <div className="flex flex-col overflow-hidden rounded-md border border-gray-200 dark:border-slate-800">
            <div className="border-b border-gray-200 dark:border-slate-800 bg-gray-100 dark:bg-slate-800 px-3 py-2 text-xs font-bold text-gray-600 dark:text-gray-400">Variables</div>
            <pre className="flex-1 overflow-y-auto bg-gray-50 dark:bg-slate-950 p-3 text-sm whitespace-pre-wrap text-sky-700 dark:text-sky-400">{jsonText(promptEvent.variables)}</pre>
          </div>
          <div className="flex flex-col overflow-hidden rounded-md border border-violet-200 dark:border-violet-800/50">
            <div className="flex items-center gap-1 border-b border-violet-200 dark:border-violet-800/50 bg-violet-50 dark:bg-violet-900/20 px-3 py-2 text-xs font-bold text-violet-700 dark:text-violet-400">
              <CheckCircle className="h-3 w-3" />
              Final Prompt
            </div>
            <pre className="flex-1 overflow-y-auto bg-white dark:bg-slate-900 p-3 text-sm whitespace-pre-wrap text-gray-800 dark:text-gray-300">
              {promptEvent.event_type === 'prompt_captured' ? jsonText(promptEvent.resolved_prompt) : jsonText(promptEvent.messages ?? undefined)}
            </pre>
          </div>
        </div>
      </div>
    </div>
  )
}
