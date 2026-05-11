import { useMemo } from "react"
import { Badge } from "@/components/ui/badge"
import { ScrollArea } from "@/components/ui/scroll-area"
import type { FileMeta } from "./panels"

interface CodeEditorProps {
  file: FileMeta
}

export function CodeEditor({ file }: CodeEditorProps) {
  const lines = useMemo(() => file.content.split("\n"), [file.content])

  return (
    <div className="h-full bg-background flex flex-col">
      <div className="h-9 flex items-center gap-2 px-3 border-b border-border shrink-0 bg-muted/30">
        <span className="text-xs text-muted-foreground font-mono">{file.path}</span>
        <Badge variant="outline" className="text-xs">{file.language}</Badge>
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
