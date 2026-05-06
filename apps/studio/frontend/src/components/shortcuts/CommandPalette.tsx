import { Search, X } from 'lucide-react'
import { useEffect, useMemo, useRef, useState } from 'react'
import { hotkeyLabel } from '../../utils/hotkeys'

export interface CommandAction {
  id: string
  label: string
  description: string
  hotkey?: string
  disabled?: boolean
  run: () => void
}

interface CommandPaletteProps {
  open: boolean
  actions: CommandAction[]
  onClose: () => void
}

function scoreAction(action: CommandAction, query: string): number {
  const haystack = `${action.label} ${action.description}`.toLowerCase()
  const index = haystack.indexOf(query.toLowerCase())
  return index < 0 ? Number.POSITIVE_INFINITY : index
}

export function CommandPalette({ open, actions, onClose }: CommandPaletteProps) {
  const [query, setQuery] = useState('')
  const [activeIndex, setActiveIndex] = useState(0)
  const inputRef = useRef<HTMLInputElement | null>(null)

  const filteredActions = useMemo(() => {
    const trimmed = query.trim()
    const candidates = trimmed
      ? actions.filter((action) => scoreAction(action, trimmed) < Number.POSITIVE_INFINITY)
      : actions
    return [...candidates].sort((left, right) => scoreAction(left, trimmed) - scoreAction(right, trimmed))
  }, [actions, query])

  useEffect(() => {
    if (!open) {
      return
    }
    setQuery('')
    setActiveIndex(0)
    window.setTimeout(() => inputRef.current?.focus(), 0)
  }, [open])

  useEffect(() => {
    setActiveIndex(0)
  }, [query])

  if (!open) {
    return null
  }

  const activeAction = filteredActions[activeIndex]

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center bg-slate-950/40 px-4 pt-[14vh]">
      <div className="w-full max-w-2xl overflow-hidden rounded-md border border-slate-200 bg-white shadow-2xl dark:border-slate-800 dark:bg-slate-950">
        <div className="flex items-center gap-3 border-b border-slate-200 px-4 py-3 dark:border-slate-800">
          <Search className="h-4 w-4 text-slate-400" />
          <input
            ref={inputRef}
            data-shortcut-input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === 'Escape') {
                onClose()
              } else if (event.key === 'ArrowDown') {
                event.preventDefault()
                setActiveIndex((index) => Math.min(filteredActions.length - 1, index + 1))
              } else if (event.key === 'ArrowUp') {
                event.preventDefault()
                setActiveIndex((index) => Math.max(0, index - 1))
              } else if (event.key === 'Enter' && activeAction && !activeAction.disabled) {
                activeAction.run()
                onClose()
              }
            }}
            placeholder="Search commands"
            className="min-w-0 flex-1 bg-transparent text-sm outline-none placeholder:text-slate-400 dark:text-slate-100"
          />
          <button
            type="button"
            onClick={onClose}
            className="rounded-md p-1.5 text-slate-500 hover:bg-slate-100 dark:text-slate-400 dark:hover:bg-slate-800"
            title="Close command palette"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
        <div className="max-h-[24rem] overflow-y-auto p-2">
          {filteredActions.length === 0 ? (
            <div className="px-3 py-8 text-center text-sm text-slate-500 dark:text-slate-400">
              No commands found.
            </div>
          ) : null}
          {filteredActions.map((action, index) => (
            <button
              key={action.id}
              type="button"
              disabled={action.disabled}
              onMouseEnter={() => setActiveIndex(index)}
              onClick={() => {
                action.run()
                onClose()
              }}
              className={`flex w-full items-center justify-between gap-3 rounded-md px-3 py-2 text-left disabled:cursor-not-allowed disabled:opacity-50 ${
                index === activeIndex
                  ? 'bg-sky-50 dark:bg-sky-950/40'
                  : 'hover:bg-slate-50 dark:hover:bg-slate-900'
              }`}
            >
              <span className="min-w-0">
                <span className="block text-sm font-semibold text-slate-800 dark:text-slate-100">
                  {action.label}
                </span>
                <span className="block truncate text-xs text-slate-500 dark:text-slate-400">
                  {action.description}
                </span>
              </span>
              {action.hotkey ? (
                <kbd className="shrink-0 rounded border border-slate-300 px-2 py-1 text-xs font-semibold text-slate-500 dark:border-slate-700 dark:text-slate-400">
                  {hotkeyLabel(action.hotkey)}
                </kbd>
              ) : null}
            </button>
          ))}
        </div>
      </div>
    </div>
  )
}
