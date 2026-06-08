import { FileCode2 } from 'lucide-react'

interface SubgraphInlineProps {
  path: string
  parentLabel: string
  childGraph?: unknown
}

export function SubgraphInline({ path, parentLabel, childGraph }: SubgraphInlineProps) {
  if (childGraph === null) {
    return (
      <div className="mt-3 rounded-md border border-destructive/25 bg-destructive/5 p-2 text-xs">
        <div className="flex items-center gap-2 font-medium text-destructive">
          <FileCode2 className="size-3.5" />
          {parentLabel} subgraph path not found
        </div>
        <div className="mt-2 rounded-md border border-border bg-background px-2 py-1 font-mono text-muted-foreground">
          {path}
        </div>
        <div className="mt-2 text-muted-foreground">
          Please recover or add to workspace assets.
        </div>
      </div>
    )
  }

  return (
    <div className="mt-3 rounded-md border border-primary/25 bg-primary/5 p-2 text-xs">
      <div className="flex items-center gap-2 font-medium text-primary">
        <FileCode2 className="size-3.5" />
        {parentLabel} subgraph
      </div>
      <div className="mt-2 rounded-md border border-border bg-background px-2 py-1 font-mono text-muted-foreground">
        {path}
      </div>
    </div>
  )
}
