import { lazy, Suspense } from 'react'

const MonacoEditor = lazy(async () => {
  const module = await import('@monaco-editor/react')
  return { default: module.default }
})

interface LazyMonacoPanelProps {
  title: string
  value: string
  onChange: (value: string) => void
}

function MonacoSkeleton() {
  return (
    <div className="grid h-full place-items-center bg-muted/30 text-sm text-muted-foreground">
      Loading editor...
    </div>
  )
}

export function LazyMonacoPanel({ title, value, onChange }: LazyMonacoPanelProps) {
  return (
    <section className="flex h-full min-h-0 flex-col border-t border-border bg-card">
      <div className="flex h-10 shrink-0 items-center justify-between border-b border-border px-3">
        <h2 className="text-sm font-semibold text-foreground">{title}</h2>
        <span className="text-xs text-muted-foreground">Agent prompt</span>
      </div>
      <div className="min-h-0 flex-1">
        <Suspense fallback={<MonacoSkeleton />}>
          <MonacoEditor
            height="100%"
            defaultLanguage="markdown"
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
