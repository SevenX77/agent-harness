import { lazy, Suspense } from 'react'

const MonacoEditor = lazy(async () => {
  const module = await import('@monaco-editor/react')
  return { default: module.default }
})

interface LazyMonacoPanelProps {
  title: string
  value: string
  onChange: (value: string) => void
  language?: string
  onClose?: () => void
}

function MonacoSkeleton() {
  return (
    <div className="grid h-full place-items-center bg-muted/30 text-sm text-muted-foreground">
      Loading editor...
    </div>
  )
}

export function LazyMonacoPanel({ title, value, onChange, language = 'markdown', onClose }: LazyMonacoPanelProps) {
  return (
    <section className="flex h-full min-h-0 flex-col bg-card">
      <div className="flex h-10 shrink-0 items-center justify-between border-b border-border px-3">
        <h2 className="text-sm font-semibold text-foreground">{title}</h2>
        <div className="flex items-center gap-2">
          <span className="rounded-md bg-secondary px-2 py-0.5 text-xs text-secondary-foreground">{language}</span>
          {onClose ? (
            <button
              type="button"
              onClick={onClose}
              aria-label="Close editor"
              className="inline-flex size-7 items-center justify-center rounded-md text-muted-foreground hover:bg-accent hover:text-foreground"
            >
              x
            </button>
          ) : null}
        </div>
      </div>
      <div className="min-h-0 flex-1">
        <Suspense fallback={<MonacoSkeleton />}>
          <MonacoEditor
            height="100%"
            defaultLanguage={language}
            theme={document.documentElement.classList.contains('dark') ? 'vs-dark' : 'light'}
            value={value}
            options={{
              minimap: { enabled: false },
              fontSize: 13,
              wordWrap: 'on',
              scrollBeyondLastLine: false,
              automaticLayout: true,
            }}
            onChange={(nextValue) => onChange(nextValue ?? '')}
          />
        </Suspense>
      </div>
    </section>
  )
}
