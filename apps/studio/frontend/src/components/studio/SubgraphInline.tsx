import { FileCode2 } from 'lucide-react'

interface SubgraphInlineProps {
  path: string
  parentLabel: string
}

export function SubgraphInline({ path, parentLabel }: SubgraphInlineProps) {
  return (
    <div className="mt-3 rounded-md border border-primary/25 bg-primary/5 p-2 text-xs">
      <div className="flex items-center gap-2 font-medium text-primary">
        <FileCode2 className="size-3.5" />
        {parentLabel} subgraph
      </div>
      <div className="mt-2 rounded-md border border-border bg-background px-2 py-1 font-mono text-muted-foreground">
        {path}
      </div>
      <div className="mt-2 grid gap-1 text-muted-foreground">
        <div className="rounded border border-border bg-card px-2 py-1">entry</div>
        <div className="rounded border border-border bg-card px-2 py-1">execute</div>
        <div className="rounded border border-border bg-card px-2 py-1">return</div>
      </div>
    </div>
  )
}
