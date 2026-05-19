import { useMemo } from "react"
import { X } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { ScrollArea } from "@/components/ui/scroll-area"
import type { FileMeta } from "./panels"

interface CodeEditorProps {
  file: FileMeta
  onClose?: () => void
}

export function CodeEditor({ file, onClose }: CodeEditorProps) {
  const lines = useMemo(() => file.content.split("\n"), [file.content])

  return (
    <div className="h-full bg-background flex flex-col">
      <div className="h-9 flex items-center justify-between gap-2 pl-3 pr-1 border-b border-border shrink-0 bg-muted/30">
        <div className="flex items-center gap-2 min-w-0">
          <span className="text-xs text-muted-foreground font-mono truncate">
            {file.path}
          </span>
          <Badge variant="outline" className="text-xs">
            {file.language}
          </Badge>
        </div>
        {onClose && (
          <Button
            variant="ghost"
            size="icon"
            onClick={onClose}
            aria-label="Close file"
            className="size-7"
          >
            <X className="size-4" />
          </Button>
        )}
      </div>
      <ScrollArea className="flex-1">
        <div className="flex min-w-max">
          <div className="py-3 px-3 text-right select-none border-r border-border sticky left-0 bg-muted/30">
            {lines.map((_, i) => (
              <div key={i} className="text-xs font-mono text-muted-foreground leading-6 h-6">
                {i + 1}
              </div>
            ))}
          </div>
          <pre className="py-3 px-4 text-xs font-mono leading-6 text-foreground whitespace-pre">
            {file.content || " "}
          </pre>
        </div>
      </ScrollArea>
    </div>
  )
}
