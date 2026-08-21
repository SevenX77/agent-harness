import { useState } from 'react'
import { PencilLine, ShieldCheck } from 'lucide-react'
import type { GoldenNodeState } from '@/components/studio/node-golden'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { useTraceCopy } from "./trace-copy"

/**
 * A node the golden actions apply to: an agent phase that has no golden yet.
 *
 * `mode` is the phase kind as the canvas names it; a logic or subgraph phase has
 * no golden of its own, and a node that already has one has nothing to create.
 */
export function isGoldenlessAgentNode(
  node: { data: { mode?: string; goldenState?: GoldenNodeState } } | null | undefined,
): boolean {
  if (!node) {
    return false
  }
  const mode = node.data.mode
  const isAgent = mode === 'agent' || mode === 'llm' || mode === 'skill'
  if (!isAgent) {
    return false
  }
  return node.data.goldenState !== 'has-golden'
}

export interface FocusedNodeActionsProps {
  node?: { id: string; data: { label?: string; mode?: string; goldenState?: GoldenNodeState } } | null
  /** Whether a run exists to promote FROM. Promoting has no meaning without one. */
  canPromote?: boolean
  onPromoteNode?: (nodeId: string) => Promise<void> | void
  onDesignGolden?: (node: { id: string; label?: string }) => void
}

/**
 * What you can do to the node the trace is focused on.
 *
 * These actions belong to the SELECTED NODE, not to a run, so the trace region
 * renders them above whichever body is showing — the run list or the trace
 * itself. They used to live inside `TracePanel`, which the region only mounts
 * once a run exists; on a skill that had never run, the region showed the run
 * list instead and "write down what this node should produce" — the one action
 * that needs no run at all — was unreachable (ledger CP4).
 *
 * Each action still states its own precondition: designing a golden needs only
 * a golden-less agent node, promoting one needs a run to promote from.
 */
export function FocusedNodeActions({
  node = null,
  canPromote = false,
  onPromoteNode,
  onDesignGolden,
}: FocusedNodeActionsProps) {
  const t = useTraceCopy()
  const [promoting, setPromoting] = useState(false)

  const eligible = isGoldenlessAgentNode(node)
  const canDesign = Boolean(onDesignGolden) && eligible
  const canPromoteNode = Boolean(onPromoteNode) && canPromote && eligible
  if (!node || (!canDesign && !canPromoteNode)) {
    return null
  }

  const label = node.data.label ?? node.id

  const promote = async () => {
    if (!onPromoteNode || promoting) {
      return
    }
    setPromoting(true)
    try {
      await onPromoteNode(node.id)
    } finally {
      setPromoting(false)
    }
  }

  return (
    <div
      data-trace-focused-node-actions={node.id}
      className="flex shrink-0 flex-wrap items-center gap-2 border-b border-border bg-card px-3 py-2 text-xs font-medium text-muted-foreground"
    >
      {canDesign ? (
        <Tooltip>
          <TooltipTrigger asChild>
            <button
              type="button"
              aria-label={t('node.designGoldenAria', { node: label })}
              onClick={() => onDesignGolden?.({ id: node.id, label })}
              className="flex items-center gap-1 rounded-full border border-border px-2 py-0.5 text-xs font-semibold text-foreground hover:bg-accent"
            >
              <PencilLine className="size-3.5" />
              {t('node.designGolden')}
            </button>
          </TooltipTrigger>
          <TooltipContent>{t('node.designGoldenTooltip')}</TooltipContent>
        </Tooltip>
      ) : null}
      {canPromoteNode ? (
        <Tooltip>
          <TooltipTrigger asChild>
            <button
              type="button"
              aria-label={t('node.promoteAria', { node: label })}
              disabled={promoting}
              onClick={() => {
                void promote()
              }}
              className="flex items-center gap-1 rounded-full border border-warning-border px-2 py-0.5 text-xs font-semibold text-warning hover:bg-warning/10 disabled:cursor-not-allowed disabled:opacity-50"
            >
              <ShieldCheck className="size-3.5" />
              {promoting ? t('node.promoting') : t('node.promote')}
            </button>
          </TooltipTrigger>
          <TooltipContent>{t('node.promoteTooltip')}</TooltipContent>
        </Tooltip>
      ) : null}
    </div>
  )
}
