import type { ComponentProps } from 'react'
import Editor from '@monaco-editor/react'
import { AlertCircle, Copy } from 'lucide-react'
import type { LintError } from '../api/types'

export type EditorOnMount = NonNullable<ComponentProps<typeof Editor>['onMount']>
export type MonacoEditor = Parameters<EditorOnMount>[0]
export type MonacoApi = Parameters<EditorOnMount>[1]

interface MonacoPanelProps {
  isDarkMode: boolean
  skillCode: string
  lintErrors: LintError[]
  onEditorMount: EditorOnMount
  onDraftChange: (code: string) => void
  onJumpToLine: (line: number | null) => void
  onCopyErrors: (message: string) => void
}

export function MonacoPanel({
  isDarkMode,
  skillCode,
  lintErrors,
  onEditorMount,
  onDraftChange,
  onJumpToLine,
  onCopyErrors,
}: MonacoPanelProps) {
  return (
    <div className="flex h-full flex-col">
      {lintErrors.length > 0 ? (
        <div className="shrink-0 border-b border-red-200 dark:border-red-900/50 bg-red-50 dark:bg-red-900/20 p-3 text-sm text-red-700 dark:text-red-400">
          <div className="mb-2 flex items-start gap-2 font-semibold">
            <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
            Manifest validation failed
          </div>
          <div className="max-h-36 space-y-2 overflow-y-auto">
            {lintErrors.map((error, index) => (
              <button
                key={`${error.error_code}-${error.line ?? 'none'}-${index}`}
                type="button"
                onClick={() => onJumpToLine(error.line)}
                className="block w-full rounded border border-red-200 dark:border-red-900/50 bg-white dark:bg-slate-900 px-2 py-1 text-left hover:bg-red-50 dark:hover:bg-red-900/30"
              >
                <span className="font-mono text-xs text-red-500">
                  {error.line ? `Line ${error.line}` : 'No line'} / {error.error_code}
                </span>
                <span className="ml-2">{error.message}</span>
              </button>
            ))}
          </div>
          <button
            type="button"
            onClick={() => onCopyErrors(lintErrors.map((error) => error.message).join('\n'))}
            className="mt-2 flex items-center gap-1 rounded border border-red-200 dark:border-red-900/50 bg-white dark:bg-slate-900 px-2 py-1 text-xs text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-900/30"
          >
            <Copy className="h-3 w-3" />
            Copy
          </button>
        </div>
      ) : null}

      <div className="flex-1">
        <Editor
          height="100%"
          defaultLanguage="markdown"
          theme={isDarkMode ? 'vs-dark' : 'light'}
          value={skillCode}
          onMount={onEditorMount}
          onChange={(value) => onDraftChange(value ?? '')}
          options={{
            minimap: { enabled: false },
            fontSize: 13,
            wordWrap: 'on',
            scrollBeyondLastLine: false,
          }}
        />
      </div>
    </div>
  )
}
