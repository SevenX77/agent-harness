import { Eye } from 'lucide-react'
import { Handle, Position, type Node, type NodeProps } from '@xyflow/react'
import type { IoDeclaration, IoInput, IoOutput } from '../../api/types'
import { Badge } from '../ui/badge'

export interface GlobalNodeData extends Record<string, unknown> {
  type: 'global-input' | 'global-output'
  schema: IoDeclaration
}

type GlobalNode = Node<GlobalNodeData>
type SchemaField = Pick<IoInput | IoOutput, 'name' | 'type'>

function fieldsFor(data: GlobalNodeData): SchemaField[] {
  return data.type === 'global-input' ? data.schema.inputs : data.schema.outputs
}

export function GlobalInputOutputNode({ data }: NodeProps<GlobalNode>) {
  const isInput = data.type === 'global-input'
  const fields = fieldsFor(data)

  return (
    <div
      className={[
        'relative min-w-[220px] rounded-md border border-border bg-card p-3 text-sm text-card-foreground shadow-sm',
        isInput ? 'border-t-2 border-t-primary' : 'border-t-2 border-t-muted-foreground',
      ].join(' ')}
    >
      {isInput ? (
        <Handle type="source" position={Position.Right} className="!size-2.5 !border-background !bg-primary" />
      ) : (
        <Handle type="target" position={Position.Left} className="!size-2.5 !border-background !bg-primary" />
      )}

      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
            {isInput ? 'Input' : 'Output'}
          </div>
          <div className="mt-2 grid gap-1.5">
            {fields.length > 0 ? (
              fields.map((field) => (
                <div key={field.name} className="flex min-w-0 items-center justify-between gap-3 text-xs">
                  <span className="truncate font-mono text-foreground">{field.name}</span>
                  <Badge variant="secondary" className="shrink-0 font-mono">
                    {field.type ?? 'unknown'}
                  </Badge>
                </div>
              ))
            ) : (
              <div className="text-xs text-muted-foreground">(no fields)</div>
            )}
          </div>
        </div>
        <button
          type="button"
          aria-label="查看完整 schema"
          className="inline-flex size-7 shrink-0 items-center justify-center rounded-md border border-border bg-background text-muted-foreground hover:bg-accent"
          onClick={(event) => {
            event.stopPropagation()
          }}
        >
          <Eye className="size-3.5" />
        </button>
      </div>
    </div>
  )
}

export const GlobalInputNode = GlobalInputOutputNode
export const GlobalOutputNode = GlobalInputOutputNode
