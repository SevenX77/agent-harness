import { X } from 'lucide-react'
import { Button } from '@/components/ui/button'
import type { SelectedNodeForProperties } from './WorkspaceContext'

interface NodePropertiesPanelProps {
  node: SelectedNodeForProperties | null
  onClose: () => void
}

function FieldList({ fields }: { fields: SelectedNodeForProperties['fields'] }) {
  if (!fields || fields.length === 0) {
    return <div className="text-xs text-muted-foreground">No schema fields</div>
  }

  return (
    <div className="overflow-hidden rounded-md border border-border">
      {fields.map((field) => (
        <div key={field.name} className="grid grid-cols-[1fr_auto] gap-3 border-b border-border px-3 py-2 text-xs last:border-b-0">
          <span className="truncate font-mono text-foreground">{field.name}</span>
          <span className="font-mono text-muted-foreground">{field.type ?? 'unknown'}</span>
        </div>
      ))}
    </div>
  )
}

function DetailRow({ label, value }: { label: string; value?: string | string[] | null }) {
  const values = Array.isArray(value) ? value : value ? [value] : []
  return (
    <div>
      <dt className="text-[10px] font-medium uppercase tracking-wider text-muted-foreground">{label}</dt>
      <dd className="mt-1 text-sm text-foreground">
        {values.length > 0 ? values.join(', ') : <span className="text-muted-foreground">None</span>}
      </dd>
    </div>
  )
}

export function NodePropertiesPanel({ node, onClose }: NodePropertiesPanelProps) {
  if (!node) return null
  const title = node.kind === 'phase' ? 'Phase Properties' : node.kind === 'input' ? 'Input Schema' : 'Output Schema'

  return (
    <aside className="absolute bottom-16 right-3 top-3 z-40 flex w-80 flex-col overflow-hidden rounded-md border border-border bg-card shadow-xl">
      <div className="flex h-10 shrink-0 items-center justify-between border-b border-border px-3">
        <div className="min-w-0">
          <div className="truncate text-sm font-semibold text-foreground">{title}</div>
          <div className="truncate text-xs text-muted-foreground">{node.label}</div>
        </div>
        <Button variant="ghost" size="icon" className="size-7" onClick={onClose} aria-label="Close properties panel">
          <X className="size-4" />
        </Button>
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto p-3">
        {node.kind === 'phase' ? (
          <dl className="space-y-4">
            <DetailRow label="Phase ID" value={node.id} />
            <DetailRow label="Mode" value={node.modeLabel} />
            <DetailRow label="Depends On" value={node.dependsOn} />
            <DetailRow label="Role" value={node.role} />
            <DetailRow label="Tools" value={node.tools} />
            <DetailRow label="File" value={node.filePath} />
          </dl>
        ) : (
          <div className="space-y-3">
            <DetailRow label="File" value={node.filePath} />
            <FieldList fields={node.fields} />
          </div>
        )}
      </div>
    </aside>
  )
}
