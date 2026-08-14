// Shared canvas-card styling (decision 2026-08-13 D8): the base card, the
// capsule shell, and the selection/severity rings are defined ONCE here, and
// every node kind — phase nodes and the Input/Output boundary nodes alike —
// is a consumer. A copied class string is not consistency, it is coincidence:
// it drifts on the next edit (the B9 bare-card copy did exactly that).

/** The card container every canvas node shares; width is the caller's. */
export const NODE_CARD_BASE =
  'group relative cursor-pointer rounded-md border bg-card p-3 text-card-foreground shadow-sm transition-colors'

/**
 * Ring / border states, ordered by precedence at the call site: a conflict or
 * warning outranks plain selection, selection outranks the resting border.
 */
export const NODE_CARD_RING = {
  none: 'border-border',
  selected: 'border-primary ring-2 ring-primary/30',
  warning: 'border-warning ring-2 ring-warning/30',
  destructive: 'border-destructive ring-2 ring-destructive/30',
} as const

export type NodeCardRing = keyof typeof NODE_CARD_RING

export function nodeCardClass(options: {
  minWidth: string
  ring: NodeCardRing
  extra?: ReadonlyArray<string | false | null | undefined>
}): string {
  return [
    NODE_CARD_BASE,
    options.minWidth,
    NODE_CARD_RING[options.ring],
    ...(options.extra ?? []),
  ]
    .filter(Boolean)
    .join(' ')
}

/**
 * The small bordered chip both node kinds put in their top-right corner: the
 * status capsule on phase nodes, the INPUT/OUTPUT kind chip on boundary nodes.
 */
export const NODE_CAPSULE_BASE =
  'inline-flex items-center gap-1 rounded-md border px-1.5 py-0.5 text-[11px] font-medium'
