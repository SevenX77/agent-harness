import { ChevronDown, ChevronRight, Folder } from "lucide-react"
import { useState, type ReactNode } from "react"

export function FolderRow({
  name,
  children,
  endAdornment,
  defaultExpanded = false,
}: {
  name: string
  children: ReactNode
  endAdornment?: ReactNode
  defaultExpanded?: boolean
}) {
  const [expanded, setExpanded] = useState(defaultExpanded)

  return (
    <div>
      <div className="flex min-w-0 items-center gap-1 rounded-md transition-colors hover:bg-accent">
        <button
          type="button"
          onClick={() => setExpanded((value) => !value)}
          title={name}
          className="flex min-w-0 flex-1 cursor-pointer items-center gap-2 rounded-md border-0 px-2 py-1.5 text-left text-xs text-muted-foreground outline-none transition-colors hover:text-foreground focus-visible:ring-1 focus-visible:ring-ring"
        >
          {expanded ? <ChevronDown className="size-3.5 shrink-0" /> : <ChevronRight className="size-3.5 shrink-0" />}
          <Folder className="size-4 shrink-0" strokeWidth={1.5} />
          <span className="truncate">{name}</span>
        </button>
        {endAdornment ? <div className="shrink-0 pr-1">{endAdornment}</div> : null}
      </div>
      {expanded ? <div className="pl-4">{children}</div> : null}
    </div>
  )
}
