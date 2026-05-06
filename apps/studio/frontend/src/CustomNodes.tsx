import { memo } from 'react'
import { Handle, Position } from 'reactflow'
import type { NodeProps } from 'reactflow'
import { ChevronDown, ChevronRight, Cpu, Layers } from 'lucide-react'

export interface StudioNodeData {
  label: string
  mode?: string
  role?: string | null
  subgraphPath?: string | null
  isExpanded?: boolean
  onToggleExpand?: () => void
}

export const SubgraphNode = memo(({ data, isConnectable, selected }: NodeProps<StudioNodeData>) => (
  <div
    role="button"
    tabIndex={0}
    aria-label={`Phase ${data.label}, subgraph node`}
    aria-pressed={selected}
    className={`min-w-[220px] rounded-md border-2 bg-violet-50 px-4 py-3 shadow-sm transition-all cursor-pointer hover:shadow-md focus:outline-none focus:ring-2 focus:ring-violet-500 dark:bg-violet-950/40 ${selected ? 'ring-2 ring-violet-500 shadow-lg border-violet-500 dark:border-violet-500' : data.isExpanded ? 'border-violet-500 dark:border-violet-600' : 'border-violet-200 dark:border-violet-800'}`}
  >
    <Handle type="target" position={Position.Top} isConnectable={isConnectable} className="h-3 w-3 bg-violet-400 dark:bg-violet-500" />

    <div className="flex items-center justify-between gap-3">
      <div className="flex min-w-0 items-center gap-2">
        <div className="rounded-md bg-violet-100 p-1.5 text-violet-600 dark:bg-violet-900/60 dark:text-violet-300">
          <Layers className="h-4 w-4" />
        </div>
        <div className="min-w-0">
          <div className="truncate text-sm font-bold text-gray-800 dark:text-gray-100">{data.label}</div>
          <div className="text-xs font-medium text-violet-600 dark:text-violet-400">Subgraph</div>
        </div>
      </div>

      <button
        type="button"
        aria-label={data.isExpanded ? `Collapse subgraph ${data.label}` : `Expand subgraph ${data.label}`}
        onClick={data.onToggleExpand}
        className="rounded-full p-1 text-violet-500 transition-colors hover:bg-violet-100 dark:text-violet-400 dark:hover:bg-violet-900/60"
        title={data.isExpanded ? 'Collapse subgraph' : 'Expand subgraph'}
      >
        {data.isExpanded ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
      </button>
    </div>

    {data.isExpanded && data.subgraphPath ? (
      <div className="mt-3 border-t border-violet-200 pt-2 text-xs text-gray-500 dark:border-violet-800 dark:text-gray-400">
        <div className="overflow-hidden text-ellipsis rounded border border-violet-100 bg-white px-2 py-1 font-mono dark:border-violet-800 dark:bg-slate-900">
          {data.subgraphPath}
        </div>
      </div>
    ) : null}

    <Handle type="source" position={Position.Bottom} isConnectable={isConnectable} className="h-3 w-3 bg-violet-400 dark:bg-violet-500" />
  </div>
))

export const AgentNode = memo(({ data, isConnectable, selected }: NodeProps<StudioNodeData>) => (
  <div
    role="button"
    tabIndex={0}
    aria-label={`Phase ${data.label}, ${data.mode ?? 'llm'} node`}
    aria-pressed={selected}
    className={`min-w-[220px] rounded-md border bg-sky-50 px-4 py-3 shadow-sm transition-all cursor-pointer hover:shadow-md focus:outline-none focus:ring-2 focus:ring-sky-500 dark:bg-sky-950/40 ${selected ? 'ring-2 ring-sky-500 shadow-lg border-sky-400 dark:border-sky-500' : 'border-sky-200 dark:border-sky-800'}`}
  >
    <Handle type="target" position={Position.Top} isConnectable={isConnectable} className="h-3 w-3 bg-sky-400 dark:bg-sky-500" />

    <div className="flex items-center justify-between gap-3">
      <div className="flex min-w-0 items-center gap-2">
        <div className="rounded-md bg-sky-100 p-1.5 text-sky-600 dark:bg-sky-900/60 dark:text-sky-300">
          <Cpu className="h-4 w-4" />
        </div>
        <div className="min-w-0">
          <div className="truncate text-sm font-bold text-gray-800 dark:text-gray-100">{data.label}</div>
          <div className="text-xs font-medium text-sky-600 dark:text-sky-400">
            {data.mode === 'logic' ? 'Logic' : data.role ?? 'Agent Loop'}
          </div>
        </div>
      </div>
    </div>

    <div className="mt-2 border-t border-sky-100 pt-2 dark:border-sky-800/60">
      <div className="rounded border border-sky-200 bg-white px-2 py-1 text-xs text-gray-600 dark:border-sky-800 dark:bg-slate-900 dark:text-gray-300">
        {data.mode ?? 'llm'}
      </div>
    </div>

    <Handle type="source" position={Position.Bottom} isConnectable={isConnectable} className="h-3 w-3 bg-sky-400 dark:bg-sky-500" />
  </div>
))
