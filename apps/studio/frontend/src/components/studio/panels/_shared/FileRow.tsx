import { FileText, type LucideIcon } from "lucide-react"
import type { FileMeta } from "../../file-types"

export function FileRow({
  file,
  icon: Icon = FileText,
  onOpen,
}: {
  file: FileMeta
  icon?: LucideIcon
  onOpen: (file: FileMeta) => void
}) {
  const filename = file.path.split("/").pop() ?? file.path

  return (
    <button
      type="button"
      onClick={() => onOpen(file)}
      title={file.path}
      className="flex w-full min-w-0 cursor-pointer items-center gap-2 rounded-md border-0 px-2 py-1 text-left text-xs text-muted-foreground outline-none transition-colors hover:bg-accent hover:text-foreground focus-visible:ring-1 focus-visible:ring-ring"
    >
      <Icon className="size-4 shrink-0" strokeWidth={1.5} />
      <span className="truncate">{filename}</span>
    </button>
  )
}
