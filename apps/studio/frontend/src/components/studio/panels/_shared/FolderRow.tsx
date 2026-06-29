import { ChevronDown, ChevronRight, Folder } from "lucide-react"
import { useState, type ReactNode } from "react"
import { cn } from "@/lib/utils"

export function FolderRow({
  name,
  children,
  endAdornment,
  defaultExpanded = false,
  expanded: controlledExpanded,
  onExpandedChange,
  rowClassName,
  buttonClassName,
  labelClassName,
}: {
  name: string
  children: ReactNode
  endAdornment?: ReactNode
  defaultExpanded?: boolean
  /** Controlled expansion. When provided, internal state is bypassed and the
   * caller owns expand/collapse (used by the Assets panel to reveal a node's
   * file). Omit for the default uncontrolled behaviour. */
  expanded?: boolean
  onExpandedChange?: (expanded: boolean) => void
  rowClassName?: string
  buttonClassName?: string
  labelClassName?: string
}) {
  const [internalExpanded, setInternalExpanded] = useState(defaultExpanded)
  const isControlled = controlledExpanded !== undefined
  const expanded = isControlled ? controlledExpanded : internalExpanded
  const toggleExpanded = () => {
    const next = !expanded
    if (!isControlled) {
      setInternalExpanded(next)
    }
    onExpandedChange?.(next)
  }

  return (
    <div className="w-full min-w-0">
      <div className={cn("flex min-w-0 items-center gap-1 rounded-md transition-colors hover:bg-accent", rowClassName)}>
        <button
          type="button"
          onClick={toggleExpanded}
          title={name}
          className={cn(
            "flex min-w-0 flex-1 cursor-pointer items-center gap-2 rounded-md border-0 px-2 py-1 text-left text-xs text-muted-foreground outline-none transition-colors hover:text-foreground focus-visible:ring-1 focus-visible:ring-ring",
            buttonClassName,
          )}
        >
          {expanded ? <ChevronDown className="size-3.5 shrink-0" /> : <ChevronRight className="size-3.5 shrink-0" />}
          <Folder className="size-4 shrink-0" strokeWidth={1.5} />
          <span className={cn("truncate", labelClassName)}>{name}</span>
        </button>
        {endAdornment ? <div className="ml-auto flex shrink-0 items-center justify-end pr-1">{endAdornment}</div> : null}
      </div>
      {expanded ? <div className="pl-4">{children}</div> : null}
    </div>
  )
}
