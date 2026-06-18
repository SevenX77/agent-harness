import { Handle, Position, type NodeProps } from '@xyflow/react'
import { AlertTriangle, Bot, Briefcase, CheckCircle2, Circle, Code, Minus, Network, Pause, Plus, Radio, Workflow } from 'lucide-react'
import { SubgraphInline } from '@/components/studio/SubgraphInline'
import { normalizeAbsoluteSubgraphPath } from '@/components/studio/subgraph-path'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { Popover, PopoverContent, PopoverAnchor } from '@/components/ui/popover'
import { Button } from '@/components/ui/button'
import type { SkillGraphNode, SkillGraphNodeData, SkillNodeStatus } from './types'

type PhaseKind = 'LOGIC' | 'AGENT' | 'SUBGRAPH'

const STATUS_STYLE: Record<SkillNodeStatus, { label: string, className: string, icon: typeof Circle }> = {
  idle: {
    label: 'Idle',
    className: 'border-border bg-card text-muted-foreground',
    icon: Circle,
  },
  running: {
    label: 'Running',
    className: 'animate-pulse-primary border-primary bg-primary/10 text-primary',
    icon: Radio,
  },
  success: {
    label: 'Success',
    className: 'border-emerald-500/45 bg-emerald-500/10 text-emerald-600 dark:text-emerald-400',
    icon: CheckCircle2,
  },
  error: {
    label: 'Error',
    className: 'border-destructive/50 bg-destructive/10 text-destructive',
    icon: AlertTriangle,
  },
  paused: {
    label: 'Paused',
    className: 'border-amber-500/45 bg-amber-500/10 text-amber-700 dark:text-amber-300',
    icon: Pause,
  },
  breakpoint: {
    label: 'Breakpoint',
    className: 'border-fuchsia-500/45 bg-fuchsia-500/10 text-fuchsia-700 dark:text-fuchsia-300',
    icon: Workflow,
  },
}

function phaseKindLabel(data: Pick<SkillGraphNodeData, 'mode' | 'subgraphPath'>): PhaseKind {
  if (data.subgraphPath || data.mode === 'subgraph') return 'SUBGRAPH'
  if (data.mode === 'agent' || data.mode === 'skill' || data.mode === 'llm') return 'AGENT'
  return 'LOGIC'
}

function phaseKindIcon(kind: PhaseKind): typeof Bot {
  if (kind === 'LOGIC') return Code
  if (kind === 'SUBGRAPH') return Network
  return Bot
}

export function SkillNode({ data, selected }: NodeProps<SkillGraphNode>) {
  const style = STATUS_STYLE[data.status]
  const StatusIcon = style.icon
  const kind = phaseKindLabel(data)
  const KindIcon = phaseKindIcon(kind)
  const resolvedSubgraphPath = normalizeAbsoluteSubgraphPath(data.subgraphPath)
  const subagentCount = data.subagents?.length ?? 0
  const compileErrorCount = data.compileErrors?.length ?? 0

  const nodeContent = (
    <div
      className={[
        'group relative min-w-[240px] cursor-pointer rounded-md border bg-card p-3 text-card-foreground shadow-sm transition-colors',
        resolvedSubgraphPath ? 'pb-5' : '',
        data.isConflictCancelled
          ? 'border-destructive ring-2 ring-destructive/30'
          : data.activeConflict
          ? 'border-amber-500 ring-2 ring-amber-500/30'
          : selected
          ? 'border-primary ring-2 ring-primary/30'
          : 'border-border',
      ].join(' ')}
      onDoubleClick={(event) => {
        if (resolvedSubgraphPath) {
          event.stopPropagation()
        }
      }}
    >
      <Handle type="target" position={Position.Top} className="!size-2.5 !border-background !bg-primary opacity-60 group-hover:opacity-100 transition-opacity duration-200" />
      <div className="flex items-start gap-3">
        <div className="flex size-9 shrink-0 items-center justify-center rounded-md bg-secondary text-secondary-foreground">
          <KindIcon className="size-4" />
        </div>
        <div className="min-w-0 flex-1">
          <div className="truncate text-sm font-semibold text-foreground">{data.label}</div>
          <div className="mt-1 flex items-center gap-2 text-xs text-muted-foreground">
            <span>{kind}</span>
            {subagentCount > 0 ? (
              <Tooltip>
                <TooltipTrigger asChild>
                  <span
                    aria-label={`${subagentCount} subagents available`}
                    className="inline-flex size-5 items-center justify-center rounded-md border border-border bg-muted text-muted-foreground"
                  >
                    <Briefcase className="size-3" />
                  </span>
                </TooltipTrigger>
                <TooltipContent side="top">{subagentCount} subagents available</TooltipContent>
              </Tooltip>
            ) : null}
            {compileErrorCount > 0 ? (
              <Tooltip>
                <TooltipTrigger asChild>
                  <span
                    aria-label={`${compileErrorCount} compile errors`}
                    className="inline-flex items-center gap-0.5 rounded-md border border-destructive/40 bg-destructive/10 px-1 font-medium text-destructive"
                  >
                    <AlertTriangle className="size-3" />
                    {compileErrorCount}
                  </span>
                </TooltipTrigger>
                <TooltipContent side="top">{compileErrorCount} compile error(s) on this node</TooltipContent>
              </Tooltip>
            ) : null}
          </div>
        </div>
        <Tooltip>
          <TooltipTrigger asChild>
            <span className={['inline-flex items-center gap-1 rounded-md border px-1.5 py-0.5 text-[11px] font-medium', style.className].join(' ')}>
              <StatusIcon className="size-3" />
              {style.label}
            </span>
          </TooltipTrigger>
          <TooltipContent side="top">{style.label}</TooltipContent>
        </Tooltip>
      </div>
      {resolvedSubgraphPath ? (
        <button
          type="button"
          aria-label={data.isExpanded ? 'Collapse subgraph' : 'Expand subgraph'}
          onClick={(event) => {
            event.stopPropagation()
            data.onToggleSubgraph?.()
          }}
          className="absolute bottom-0 right-3 inline-flex size-5 translate-y-1/2 items-center justify-center rounded-full border border-border bg-card text-foreground shadow-sm transition-colors hover:border-primary"
        >
          {data.isExpanded ? <Minus className="size-3" /> : <Plus className="size-3" />}
        </button>
      ) : null}
      {resolvedSubgraphPath && data.isExpanded ? (
        <SubgraphInline skillId={data.skillId} path={resolvedSubgraphPath} parentLabel={data.label} />
      ) : null}
      <Handle type="source" position={Position.Bottom} className="!size-2.5 !border-background !bg-primary opacity-60 group-hover:opacity-100 transition-opacity duration-200" />
    </div>
  )

  if (data.activeConflict) {
    return (
      <Popover open={true} modal={false}>
        <PopoverAnchor asChild>
          {nodeContent}
        </PopoverAnchor>
        <PopoverContent side="top" align="center" className="w-[280px] p-3 bg-zinc-950 border border-zinc-800 rounded-md text-foreground shadow-xl z-50">
          <div className="flex items-start gap-2.5">
            <AlertTriangle className="size-4 shrink-0 text-amber-500 mt-0.5" />
            <div className="flex-1 min-w-0">
              <h4 className="text-xs font-semibold text-foreground">Sequential Overwrite Detected</h4>
              <p className="mt-1 text-[11px] text-muted-foreground leading-normal">
                Field <code className="text-amber-400 font-mono text-[10px] px-1 py-0.5 bg-zinc-900 rounded">{data.activeConflict.fieldName}</code> is also output by upstream node <span className="font-semibold">{data.activeConflict.ancestorNodeId}</span> and will be overwritten.
              </p>
              <div className="mt-3 flex items-center justify-end gap-2">
                <Button
                  size="sm"
                  variant="ghost"
                  className="h-7 text-[11px] px-2 text-muted-foreground hover:text-foreground"
                  onClick={() => data.onCancelWarning?.(data.activeConflict!.nodeId)}
                >
                  Cancel
                </Button>
                <Button
                  size="sm"
                  variant="default"
                  className="h-7 text-[11px] px-2.5 bg-amber-500 hover:bg-amber-600 text-zinc-950 font-medium rounded-md"
                  onClick={() => data.onAllowSequentialOverwrite?.(data.activeConflict!.nodeId, data.activeConflict!.fieldName)}
                >
                  Allow Overwrite
                </Button>
              </div>
            </div>
          </div>
        </PopoverContent>
      </Popover>
    )
  }

  return nodeContent
}
