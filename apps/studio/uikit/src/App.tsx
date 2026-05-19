import { Workspace } from "@/components/studio/workspace"
import { TooltipProvider } from "@/components/ui/tooltip"

export function App() {
  return (
    <TooltipProvider delayDuration={0}>
      <Workspace />
    </TooltipProvider>
  )
}

export default App
