import { Handle, Position, type Node, type NodeProps } from '@xyflow/react'
import { NodeCompileErrorBadge } from './NodeCompileErrorBadge'
import { GLOBAL_INPUT_SOURCE_HANDLE_ID, GLOBAL_OUTPUT_TARGET_HANDLE_ID } from './subgraph-bridge-handles'
import type { GlobalNodeData } from './types'

export type { GlobalNodeData } from './types'

type GlobalNode = Node<GlobalNodeData>

export function GlobalInputOutputNode({ data, selected }: NodeProps<GlobalNode>) {
  const isInput = data.type === 'global-input'
  const compileErrors = data.compileErrors ?? []

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
        </div>
        <div className="flex shrink-0 items-center gap-1">
          <NodeCompileErrorBadge errors={compileErrors} scope="boundary" />
          <span className="inline-flex items-center rounded-md border border-border bg-card px-1.5 py-0.5 text-[11px] font-medium text-muted-foreground">
            {isInput ? 'INPUT' : 'OUTPUT'}
          </span>
        </div>
      </div>
    </div>
  )
}

export const GlobalInputNode = GlobalInputOutputNode
export const GlobalOutputNode = GlobalInputOutputNode
