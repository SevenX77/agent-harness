import { ChevronDown, ChevronRight, Folder } from "lucide-react"
import { useState, type ReactNode } from "react"

export function FolderRow({
  name,
  children,
  defaultExpanded = false,
}: {
  name: string
  children: ReactNode
  defaultExpanded?: boolean
}) {
  const [expanded, setExpanded] = useState(defaultExpanded)

  return (
    <div>
      <button
        type="button"
        onClick={() => setExpanded((value) => !value)}
        className="flex w-full cursor-pointer items-center gap-2 rounded-md border-0 px-2 py-1.5 text-left text-xs text-muted-foreground outline-none transition-colors hover:bg-accent hover:text-foreground focus-visible:ring-1 focus-visible:ring-ring"
      >
        {expanded ? <ChevronDown className="size-3.5" /> : <ChevronRight className="size-3.5" />}
        <Folder className="size-4" strokeWidth={1.5} />
        <span>{name}</span>
      </button>
      {expanded ? <div className="pl-4">{children}</div> : null}
    </div>
  )
}
