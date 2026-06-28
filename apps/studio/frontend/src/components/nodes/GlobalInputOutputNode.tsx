import { Handle, Position, type Node, type NodeProps } from '@xyflow/react'
import type { IoInput, IoOutput } from '../../api/types'
import { Badge } from '../ui/badge'
import { GLOBAL_INPUT_SOURCE_HANDLE_ID, GLOBAL_OUTPUT_TARGET_HANDLE_ID } from './subgraph-bridge-handles'
import type { GlobalNodeData } from './types'

export type { GlobalNodeData } from './types'

type GlobalNode = Node<GlobalNodeData>
type SchemaField = Pick<IoInput | IoOutput, 'name' | 'type'>

function fieldsFor(data: GlobalNodeData): SchemaField[] {
  return data.type === 'global-input' ? data.schema.inputs : data.schema.outputs
}

export function GlobalInputOutputNode({ data, selected }: NodeProps<GlobalNode>) {
  const isInput = data.type === 'global-input'
  const fields = fieldsFor(data)

  return (
    <div
      className={[
        'group relative min-w-[220px] cursor-pointer rounded-md border bg-card p-3 text-sm text-card-foreground shadow-sm transition-colors',
        selected ? 'border-primary ring-2 ring-primary/30' : 'border-border',
      ].join(' ')}
    >
      {isInput ? (
        <Handle
          id={GLOBAL_INPUT_SOURCE_HANDLE_ID}
          type="source"
          position={Position.Bottom}
          className="global-input-source-handle !size-2.5 !border-background !bg-primary opacity-60 transition-opacity duration-200 group-hover:opacity-100"
        />
      ) : (
        <Handle
          id={GLOBAL_OUTPUT_TARGET_HANDLE_ID}
          type="target"
          position={Position.Top}
          className="global-output-target-handle !size-2.5 !border-background !bg-primary opacity-60 transition-opacity duration-200 group-hover:opacity-100"
        />
      )}

      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="truncate text-sm font-semibold text-foreground">
            {isInput ? 'Input' : 'Output'}
          </div>
          {fields.length > 0 ? (
            <div className="mt-2 grid gap-1.5">
              {fields.map((field) => (
                <div key={field.name} className="flex min-w-0 items-center justify-between gap-3 text-xs">
                  <span className="truncate font-mono text-foreground">{field.name}</span>
                  <Badge variant="secondary" className="shrink-0 font-mono">
                    {field.type ?? 'unknown'}
                  </Badge>
                </div>
              ))}
            </div>
          ) : null}
        </div>
        <span className="inline-flex items-center rounded-md border border-border bg-card px-1.5 py-0.5 text-[11px] font-medium text-muted-foreground">
          {isInput ? 'INPUT' : 'OUTPUT'}
        </span>
      </div>
    </div>
  )
}

export const GlobalInputNode = GlobalInputOutputNode
export const GlobalOutputNode = GlobalInputOutputNode
