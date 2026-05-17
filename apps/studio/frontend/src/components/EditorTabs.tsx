import { X } from 'lucide-react'
import { disposeMonacoModel } from './MonacoPanel'

interface EditorTabsProps {
  openTabs: string[]
  activeFile: string | null
  dirty: Record<string, boolean>
  onSwitch: (path: string) => void
  onClose: (path: string) => void
}

function basename(path: string): string {
  return path.split('/').at(-1) ?? path
}

export function EditorTabs({ openTabs, activeFile, dirty, onSwitch, onClose }: EditorTabsProps) {
  if (openTabs.length === 0) {
    return null
  }

  return (
    <div className="flex min-h-10 overflow-x-auto border-b border-gray-200 bg-slate-50 dark:border-slate-800 dark:bg-slate-950">
      {openTabs.map((path) => {
        const isActive = path === activeFile
        const isDirty = dirty[path] === true
        return (
          <div
            key={path}
            role="button"
            tabIndex={0}
            title={path}
            className={`group flex max-w-52 shrink-0 items-center gap-2 border-r border-gray-200 px-3 text-sm dark:border-slate-800 ${
              isActive ? 'bg-white text-sky-700 dark:bg-slate-900 dark:text-sky-300' : 'text-slate-600 hover:bg-white dark:text-slate-300 dark:hover:bg-slate-900'
            }`}
            onClick={() => onSwitch(path)}
            onKeyDown={(event) => {
              if (event.key === 'Enter' || event.key === ' ') {
                event.preventDefault()
                onSwitch(path)
              }
            }}
          >
            <span className="truncate">{basename(path)}</span>
            {isDirty ? <span aria-label="dirty" className="text-red-500">•</span> : null}
            <button
              type="button"
              aria-label={`Close ${path}`}
              className="rounded p-0.5 text-slate-400 hover:bg-slate-200 hover:text-slate-700 dark:hover:bg-slate-800 dark:hover:text-slate-100"
              onClick={(event) => {
                event.stopPropagation()
                if (dirty[path] && !window.confirm(`Unsaved changes in ${path}, close anyway?`)) {
                  return
                }
                disposeMonacoModel(path)
                onClose(path)
              }}
            >
              <X className="h-3 w-3" />
            </button>
          </div>
        )
      })}
    </div>
  )
}
