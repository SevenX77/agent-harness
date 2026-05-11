import { lazy, Suspense } from 'react'
import { X } from 'lucide-react'

const MonacoEditor = lazy(async () => {
  const module = await import('@monaco-editor/react')
  return { default: module.default }
})

interface EdgeContextViewerProps {
  title: string
  value: unknown
  open: boolean
  onClose: () => void
  editable?: boolean
  onChange?: (value: string) => void
}

export function EdgeContextViewer({ title, value, open, onClose, editable = false, onChange }: EdgeContextViewerProps) {
  if (!open) {
    return null
  }

  const text = typeof value === 'string' ? value : JSON.stringify(value ?? {}, null, 2)

  return (
    <div className="fixed inset-0 z-modal grid place-items-center bg-background/70 p-4 backdrop-blur-sm">
      <section className="flex h-[80vh] w-full max-w-5xl flex-col overflow-hidden rounded-md border border-border bg-card shadow-xl">
        <header className="flex items-center justify-between border-b border-border px-4 py-3">
          <div>
            <h2 className="text-sm font-semibold text-foreground">{title}</h2>
            <p className="mt-1 text-xs text-muted-foreground">{editable ? 'Editable local JSON draft' : 'Readonly edge context JSON'}</p>
          </div>
          <button type="button" onClick={onClose} aria-label="Close edge context viewer" className="rounded-md p-1 text-muted-foreground hover:bg-accent hover:text-foreground">
            <X className="size-4" />
          </button>
        </header>
        <div className="min-h-0 flex-1">
          <Suspense fallback={<div className="grid h-full place-items-center text-sm text-muted-foreground">Loading JSON viewer...</div>}>
            <MonacoEditor
              height="100%"
              language="json"
              theme={document.documentElement.classList.contains('dark') ? 'vs-dark' : 'light'}
              value={text}
              options={{
                readOnly: !editable,
                minimap: { enabled: false },
                fontSize: 13,
                wordWrap: 'on',
                scrollBeyondLastLine: false,
                automaticLayout: true,
              }}
              onChange={(nextValue) => onChange?.(nextValue ?? '')}
            />
          </Suspense>
        </div>
      </section>
    </div>
  )
}
