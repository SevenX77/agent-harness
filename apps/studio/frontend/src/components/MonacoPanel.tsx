import { useEffect, useRef, type ComponentProps } from 'react'
import Editor from '@monaco-editor/react'
import { AlertCircle, Copy } from 'lucide-react'
import type { JsonObject, LintError } from '../api/types'

export type EditorOnMount = NonNullable<ComponentProps<typeof Editor>['onMount']>
export type MonacoEditor = Parameters<EditorOnMount>[0]
export type MonacoApi = Parameters<EditorOnMount>[1]
type MonacoModel = ReturnType<MonacoApi['editor']['createModel']>
type MonacoDisposable = ReturnType<MonacoModel['onDidChangeContent']>
type MonacoMarker = Parameters<MonacoApi['editor']['setModelMarkers']>[2][number]

const modelCache = new Map<string, MonacoModel>()

interface MonacoPanelProps {
  isDarkMode: boolean
  activeFile: string | null
  files: Record<string, string>
  lintErrors: LintError[]
  node_schema_v21?: Record<string, JsonObject>
  io_schema?: Record<string, JsonObject>
  readOnly?: boolean
  onEditorMount?: EditorOnMount
  onContentChange: (path: string, content: string) => void
  onJumpToLine: (line: number | null, file?: string | null) => void
  onCopyErrors: (message: string) => void
}

function languageForPath(path: string): string {
  if (path.endsWith('.json')) {
    return 'json'
  }
  if (path.endsWith('.py')) {
    return 'python'
  }
  return 'markdown'
}

function getOrCreateModel(monaco: MonacoApi, path: string, content: string): MonacoModel {
  const existing = modelCache.get(path)
  if (existing) {
    if (existing.getValue() !== content) {
      existing.setValue(content)
    }
    return existing
  }

  const uri = monaco.Uri.parse(`file:///${path}`)
  const model = monaco.editor.createModel(content, languageForPath(path), uri)
  modelCache.set(path, model)
  return model
}

function configureJsonSchemas(
  monaco: MonacoApi,
  node_schema_v21?: Record<string, JsonObject>,
  io_schema?: Record<string, JsonObject>,
): void {
  monaco.languages.json.jsonDefaults.setDiagnosticsOptions({
    validate: true,
    allowComments: false,
    schemas: [
      {
        uri: 'studio://schemas/io-inputs.json',
        fileMatch: ['file:///io/inputs.json'],
        schema: io_schema?.inputs ?? {},
      },
      {
        uri: 'studio://schemas/io-outputs.json',
        fileMatch: ['file:///io/outputs.json'],
        schema: io_schema?.outputs ?? {},
      },
      ...Object.entries(node_schema_v21 ?? {}).map(([name, schema]) => ({
        uri: `studio://schemas/node_schema_v21/${name}.json`,
        fileMatch: [`file:///schema/${name}.json`],
        schema,
      })),
    ],
  })
}

function lintMarkersForPath(monaco: MonacoApi, path: string, lintErrors: LintError[]): MonacoMarker[] {
  return lintErrors
    .filter((error) => error.file === path)
    .map((error) => ({
      startLineNumber: error.line ?? 1,
      startColumn: error.column ?? 1,
      endLineNumber: error.line ?? 1,
      endColumn: error.column ? error.column + 1 : 120,
      message: error.message,
      severity: error.severity === 'warning' ? monaco.MarkerSeverity.Warning : monaco.MarkerSeverity.Error,
    }))
}

export function disposeMonacoModel(path: string): void {
  const model = modelCache.get(path)
  if (!model) {
    return
  }
  model.dispose()
  modelCache.delete(path)
}

export function MonacoPanel({
  isDarkMode,
  activeFile,
  files,
  lintErrors,
  node_schema_v21,
  io_schema,
  readOnly = false,
  onEditorMount,
  onContentChange,
  onJumpToLine,
  onCopyErrors,
}: MonacoPanelProps) {
  const editorRef = useRef<MonacoEditor | null>(null)
  const monacoRef = useRef<MonacoApi | null>(null)
  const changeSubscriptionRef = useRef<MonacoDisposable | null>(null)

  useEffect(() => {
    const editor = editorRef.current
    const monaco = monacoRef.current
    changeSubscriptionRef.current?.dispose()
    changeSubscriptionRef.current = null

    if (!editor || !monaco || !activeFile) {
      editor?.setModel(null)
      return
    }

    const model = getOrCreateModel(monaco, activeFile, files[activeFile] ?? '')
    editor.setModel(model)
    editor.updateOptions({ readOnly })
    monaco.editor.setModelMarkers(model, 'studio-lint', lintMarkersForPath(monaco, activeFile, lintErrors))
    changeSubscriptionRef.current = model.onDidChangeContent(() => {
      if (readOnly) {
        return
      }
      onContentChange(activeFile, model.getValue())
    })

    return () => {
      changeSubscriptionRef.current?.dispose()
      changeSubscriptionRef.current = null
    }
  }, [activeFile, files, lintErrors, onContentChange, readOnly])

  useEffect(() => {
    const monaco = monacoRef.current
    if (!monaco) {
      return
    }
    configureJsonSchemas(monaco, node_schema_v21, io_schema)
  }, [io_schema, node_schema_v21])

  useEffect(() => {
    const monaco = monacoRef.current
    if (!monaco) {
      return
    }
    for (const [path, model] of modelCache) {
      monaco.editor.setModelMarkers(model, 'studio-lint', lintMarkersForPath(monaco, path, lintErrors))
    }
  }, [lintErrors])

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
                key={`${error.file ?? 'global'}-${error.error_code}-${error.line ?? 'none'}-${index}`}
                type="button"
                onClick={() => onJumpToLine(error.line, error.file)}
                className="block w-full rounded border border-red-200 dark:border-red-900/50 bg-white dark:bg-slate-900 px-2 py-1 text-left hover:bg-red-50 dark:hover:bg-red-900/30"
              >
                <span className="font-mono text-xs text-red-500">
                  {error.file ? `${error.file}:` : ''}{error.line ? `Line ${error.line}` : 'No line'} / {error.error_code}
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
          onMount={(editor, monaco) => {
            editorRef.current = editor
            monacoRef.current = monaco
            configureJsonSchemas(monaco, node_schema_v21, io_schema)
            onEditorMount?.(editor, monaco)
          }}
          options={{
            minimap: { enabled: false },
            fontSize: 13,
            readOnly,
            wordWrap: 'on',
            scrollBeyondLastLine: false,
          }}
        />
      </div>
    </div>
  )
}
