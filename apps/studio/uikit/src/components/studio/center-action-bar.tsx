import { Hammer, Play, Zap } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Separator } from "@/components/ui/separator"

export function CenterActionBar() {
  return (
    <div className="absolute bottom-6 left-1/2 -translate-x-1/2 z-30 inline-flex items-center gap-1 bg-card border border-border rounded-full px-1.5 py-1 shadow-lg">
      <Button variant="ghost" size="lg" className="gap-1.5 rounded-full h-10 px-4">
        <Hammer className="size-4" />
        Compile
      </Button>
      <Separator orientation="vertical" className="h-5 mx-0.5" />
      <Button variant="ghost" size="lg" className="gap-1.5 rounded-full h-10 px-4">
        <Zap className="size-4" />
        Predict
      </Button>
      <Button size="lg" className="gap-1.5 rounded-full h-10 px-4">
        <Play fill="currentColor" className="size-4" />
        Run
      </Button>
    </div>
  )
}
