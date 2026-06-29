import { useEffect, useRef } from "react"
import { FileText, type LucideIcon } from "lucide-react"
import { cn } from "@/lib/utils"
import type { FileMeta } from "../../file-types"

export function FileRow({
  file,
  icon: Icon = FileText,
  onOpen,
  active = false,
}: {
  file: FileMeta
  icon?: LucideIcon
  onOpen: (file: FileMeta) => void
  /** Highlight + scroll into view — the file for the canvas-selected node. */
  active?: boolean
}) {
  const filename = file.path.split("/").pop() ?? file.path
  const ref = useRef<HTMLButtonElement>(null)

  useEffect(() => {
    if (active) {
      ref.current?.scrollIntoView({ block: "nearest" })
    }
  }, [active])

  return (
    <button
      ref={ref}
      type="button"
      onClick={() => onOpen(file)}
      title={file.path}
      aria-current={active ? "true" : undefined}
      className={cn(
        "flex w-full min-w-0 cursor-pointer items-center gap-2 rounded-md border-0 px-2 py-1 text-left text-xs outline-none transition-colors hover:bg-accent hover:text-foreground focus-visible:ring-1 focus-visible:ring-ring",
        active ? "bg-accent font-medium text-foreground" : "text-muted-foreground",
      )}
    >
      <Icon className="size-4 shrink-0" strokeWidth={1.5} />
      <span className="truncate">{filename}</span>
    </button>
  )
}
