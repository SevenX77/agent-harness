import { ChevronRight, Hash, MessageSquare } from 'lucide-react'
import type { CallbackEvent } from '../api/types'
import { eventColor, eventMessage, eventPhase, tokenText } from '../utils/trace'

interface TracePanelProps {
  traceLogs: CallbackEvent[]
  onSelectPrompt: (index: number) => void
}

export function TracePanel({ traceLogs, onSelectPrompt }: TracePanelProps) {
  if (traceLogs.length === 0) {
    return (
      <div className="flex h-full items-center justify-center text-sm font-medium text-slate-400 dark:text-slate-500">
        Waiting for run events
      </div>
    )
  }

  return (
    <div>
      <h3 className="mb-4 border-b border-gray-200 dark:border-slate-800 pb-2 font-bold text-gray-700 dark:text-gray-300">Trace Timeline</h3>
      <div className="relative ml-3 space-y-5 border-l-2 border-gray-200 dark:border-slate-800">
        {traceLogs.map((event, index) => {
          const tokens = tokenText(event)
          const inspectable = event.event_type === 'prompt_captured' || event.event_type === 'llm_call'
          return (
            <div key={`${event.timestamp}-${index}`} className="relative pl-6">
              <div className={`absolute -left-[9px] top-1 h-4 w-4 rounded-full border-2 border-white dark:border-slate-900 ${eventColor(event.event_type)}`} />
              <button
                type="button"
                onClick={() => inspectable && onSelectPrompt(index)}
                className={`block w-full rounded-md border p-3 text-left shadow-sm ${
                  inspectable
                    ? 'cursor-pointer border-violet-200 dark:border-violet-800 bg-white dark:bg-slate-900 hover:border-violet-400 dark:hover:border-violet-600'
                    : 'cursor-default border-gray-200 dark:border-slate-800 bg-white dark:bg-slate-900'
                }`}
              >
                <div className="mb-1 flex items-center justify-between gap-3">
                  <span className="flex items-center gap-1 text-sm font-bold text-gray-800 dark:text-gray-200">
                    {inspectable ? <MessageSquare className="h-3.5 w-3.5 text-violet-600 dark:text-violet-400" /> : null}
                    {event.event_type}
                  </span>
                  {tokens ? (
                    <span className="flex items-center gap-1 rounded-full bg-violet-100 dark:bg-violet-900/40 px-2 py-0.5 text-xs font-medium text-violet-600 dark:text-violet-300">
                      <Hash className="h-3 w-3" />
                      {tokens}
                    </span>
                  ) : null}
                </div>
                <div className="text-xs font-medium uppercase text-gray-400 dark:text-gray-500">{eventPhase(event)}</div>
                <p className="mt-1 text-sm text-gray-600 dark:text-gray-400">{eventMessage(event)}</p>
                {inspectable ? (
                  <div className="mt-2 flex items-center gap-1 text-xs font-medium text-violet-500 dark:text-violet-400">
                    Inspect prompt <ChevronRight className="h-3 w-3" />
                  </div>
                ) : null}
              </button>
            </div>
          )
        })}
      </div>
    </div>
  )
}
