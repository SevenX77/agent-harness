import { AlertCircle, CheckCircle2 } from "lucide-react"
import { ScrollArea } from "@/components/ui/scroll-area"
import { PanelHeader } from "./_shared/PanelHeader"

export function TimelinePanel() {
  const traces = [
    { id: 1, name: "Latest run", status: "success", duration: "2.3s", time: "2m ago" },
    { id: 2, name: "Previous run", status: "error", duration: "0.8s", time: "5m ago" },
  ]

  return (
    <div className="flex h-full flex-col bg-background">
      <PanelHeader title="Timeline" />

      <ScrollArea className="flex-1">
        <div className="px-2 py-2">
          {traces.map((trace) => (
            <div
              key={trace.id}
              className="group cursor-pointer rounded-md px-2 py-2 transition-colors hover:bg-accent"
            >
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  {trace.status === "success" ? (
                    <CheckCircle2 className="size-4 text-foreground" />
                  ) : (
                    <AlertCircle className="size-4 text-destructive" />
                  )}
                  <span className="text-xs text-muted-foreground group-hover:text-foreground">{trace.name}</span>
                </div>
                <span className="text-xs text-muted-foreground">{trace.time}</span>
              </div>
              <div className="mt-0.5 flex items-center gap-2 pl-6 text-xs text-muted-foreground">
                <span>{trace.duration}</span>
              </div>
            </div>
          ))}
        </div>
      </ScrollArea>
    </div>
  )
}
