import { Upload } from 'lucide-react'
import { useMemo, useState, type DragEvent } from 'react'
import { inferJsonSchemaFromText } from '../../lib/schema-infer'

const SAMPLE_JSON = '{\n  "topic": "pricing",\n  "priority": 2,\n  "include_sources": true\n}'

export function InputSchemaPanel() {
  const [draft, setDraft] = useState(SAMPLE_JSON)

  const result = useMemo(() => {
    try {
      return { schema: inferJsonSchemaFromText(draft), error: null as string | null }
    } catch (error) {
      return { schema: null, error: error instanceof Error ? error.message : 'Invalid JSON' }
    }
  }, [draft])

  const handleDrop = async (event: DragEvent<HTMLTextAreaElement>) => {
    event.preventDefault()
    const file = event.dataTransfer.files.item(0)
    if (file) {
      setDraft(await file.text())
      return
    }

    const text = event.dataTransfer.getData('text/plain')
    if (text) {
      setDraft(text)
    }
  }

  return (
    <section>
      <div className="mb-2 flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
        <Upload className="size-3.5" />
        Infer input schema
      </div>
      <div className="space-y-3 rounded-md border border-border bg-background p-3">
        <textarea
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          onDragOver={(event) => event.preventDefault()}
          onDrop={handleDrop}
          className="h-28 w-full resize-none rounded-md border border-input bg-card p-2 font-mono text-xs text-foreground outline-none focus:ring-2 focus:ring-ring"
          spellCheck={false}
          aria-label="JSON input for schema inference"
        />
        {result.error ? (
          <div className="rounded-md border border-destructive/30 bg-destructive/10 px-2 py-1 text-xs text-destructive">
            {result.error}
          </div>
        ) : (
          <pre className="max-h-52 overflow-auto rounded-md border border-border bg-muted/40 p-2 text-xs text-foreground">
            {JSON.stringify(result.schema, null, 2)}
          </pre>
        )}
      </div>
    </section>
  )
}
