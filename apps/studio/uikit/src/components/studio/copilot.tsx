
import { useState } from "react"
import { X, Sparkles, ChevronRight, Plus, Paperclip, ArrowUp } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { ScrollArea } from "@/components/ui/scroll-area"
import { cn } from "@/lib/utils"

interface CopilotProps {
  isOpen: boolean
  onClose: () => void
}

const suggestions = [
  "Add error handling",
  "Optimize this node",
  "Explain the flow",
  "Generate tests",
]

export function Copilot({ isOpen, onClose }: CopilotProps) {
  const [message, setMessage] = useState("")

  if (!isOpen) return null

  return (
    <div className="fixed right-0 top-0 h-full w-[340px] bg-sidebar border-l border-sidebar-border flex flex-col z-50 animate-in slide-in-from-right duration-200">
      {/* Header */}
      <div className="flex items-center justify-between px-3 h-11 border-b border-sidebar-border shrink-0">
        <div className="flex items-center gap-1.5">
          <span className="text-sm font-medium text-foreground">New Chat</span>
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
            <h2 className="text-xl font-semibold text-foreground mb-1">
              Good afternoon.
            </h2>
            <p className="text-sm text-muted-foreground">
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
                <Sparkles className="size-3.5 text-muted-foreground group-hover:text-primary transition-colors" strokeWidth={1.5} />
                {suggestion}
              </button>
            ))}
          </div>
        </div>
      </ScrollArea>

      {/* Input */}
      <div className="p-3 border-t border-sidebar-border shrink-0">
        <div className="flex items-center gap-2 bg-secondary border border-border rounded-md px-2.5 py-2 focus-within:ring-1 focus-within:ring-ring transition-colors">
          <Input
            value={message}
            onChange={(e) => setMessage(e.target.value)}
            placeholder="Use '@' to mention nodes..."
            className="flex-1 border-0 bg-transparent h-auto p-0 text-xs focus-visible:ring-0"
          />
          <div className="flex items-center gap-0.5">
            <Button variant="ghost" size="icon-xs">
              <Paperclip />
            </Button>
            <Button variant="ghost" size="icon-xs">
              <Plus />
            </Button>
            <Button
              size="icon-xs"
              variant={message ? "default" : "secondary"}
              className={cn(!message && "text-muted-foreground")}
            >
              <ArrowUp />
            </Button>
          </div>
        </div>
      </div>
    </div>
  )
}

// Floating Copilot Button
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
