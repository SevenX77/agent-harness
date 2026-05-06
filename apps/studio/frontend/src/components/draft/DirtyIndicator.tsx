interface DirtyIndicatorProps {
  dirty: boolean
}

export function DirtyIndicator({ dirty }: DirtyIndicatorProps) {
  if (!dirty) {
    return null
  }

  return (
    <span
      aria-label="Unsaved draft"
      title="Unsaved draft"
      className="inline-flex h-2.5 w-2.5 rounded-full bg-amber-500 shadow-[0_0_0_3px_rgba(245,158,11,0.18)]"
    />
  )
}

