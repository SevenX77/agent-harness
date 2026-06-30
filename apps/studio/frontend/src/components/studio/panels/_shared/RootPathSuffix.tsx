import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"
import { cn } from "@/lib/utils"

export function RootPathSuffix({ path, className }: { path: string; className?: string }) {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <span className={cn("inline-flex min-w-0 max-w-full items-baseline text-[11px] text-muted-foreground", className)}>
          <span className="shrink-0">(</span>
          <span className="min-w-0 flex-1 truncate">{path}</span>
          <span className="shrink-0">)</span>
        </span>
      </TooltipTrigger>
      <TooltipContent side="top" align="center" sideOffset={6} className="max-w-80 break-all">
        {path}
      </TooltipContent>
    </Tooltip>
  )
}
