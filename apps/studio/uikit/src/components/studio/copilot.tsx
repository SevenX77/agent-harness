
import { useState } from "react"
import { X, Sparkles, ChevronRight, Plus, Paperclip, ArrowUp } from "lucide-react"
import { Button } from "@/components/ui/button"
import { ScrollArea } from "@/components/ui/scroll-area"
import { cn } from "@/lib/utils"

interface CopilotProps {
  onClose: () => void
}

const suggestions = [
  "Add error handling",
  "Optimize this node",
  "Explain the flow",
  "Generate tests",
]

export function Copilot({ onClose }: CopilotProps) {
  const [message, setMessage] = useState("")

  return (
    <div className="h-full w-full bg-sidebar border-l border-sidebar-border flex flex-col">
      {/* Header */}
      <div className="flex items-center justify-between px-3 h-11 border-b border-sidebar-border shrink-0">
        <div className="flex items-center gap-1.5">
          <span className="text-xs font-medium text-foreground">New Chat</span>
          <ChevronRight className="size-3 text-muted-foreground" />
        </div>
        <div className="flex items-center gap-0.5">
          <Button variant="ghost" size="icon-xs">
            <Plus />
          </Button>
          <Button variant="ghost" size="icon-xs" onClick={onClose}>
            <X />
          </Button>
        </div>
      </div>

      {/* Content */}
      <ScrollArea className="flex-1">
        <div className="p-4">
          {/* Welcome */}
          <div className="mb-6">
            <h2 className="text-sm font-medium text-foreground mb-1">
              Good afternoon.
            </h2>
            <p className="text-xs text-muted-foreground">
              How can I help you today?
            </p>
          </div>

          {/* Suggestions */}
          <div className="space-y-1">
            {suggestions.map((suggestion, i) => (
              <button
                key={i}
                className="w-full flex items-center gap-2.5 px-2.5 py-2 text-left text-xs text-muted-foreground hover:text-foreground hover:bg-sidebar-accent rounded-sm transition-colors group"
              >
                <Sparkles className="size-3.5 text-muted-foreground group-hover:text-foreground transition-colors" strokeWidth={1.5} />
                {suggestion}
              </button>
            ))}
          </div>
        </div>
      </ScrollArea>

      {/* Input */}
      <div className="p-3 border-t border-sidebar-border shrink-0">
        <div className="flex flex-col gap-2 bg-secondary border border-border rounded-md px-2.5 py-2 focus-within:ring-1 focus-within:ring-ring transition-colors">
          <textarea
            value={message}
            onChange={(e) => setMessage(e.target.value)}
            placeholder="Use '@' to mention nodes..."
            rows={1}
            className="w-full resize-none bg-transparent text-xs leading-relaxed outline-none placeholder:text-muted-foreground field-sizing-content min-h-[20px] max-h-[160px] overflow-y-auto"
          />
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-0.5">
              <Button variant="ghost" className="h-7 w-7 p-0">
                <Paperclip className="size-3.5" />
              </Button>
              <Button variant="ghost" className="h-7 w-7 p-0">
                <Plus className="size-3.5" />
              </Button>
            </div>
            <Button
              className="h-7 w-7 p-0"
              variant={message ? "default" : "secondary"}
            >
              <ArrowUp className={cn("size-3.5", !message && "text-muted-foreground")} />
            </Button>
          </div>
        </div>
      </div>
    </div>
  )
}

export function CopilotButton({ onClick }: { onClick: () => void }) {
  return (
    <Button
      onClick={onClick}
      size="icon"
      className="fixed right-5 bottom-5 size-10 rounded-full shadow-lg z-40"
    >
      <Sparkles strokeWidth={1.5} />
    </Button>
  )
}
