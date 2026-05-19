import { useState } from 'react'
import { Toaster } from 'sonner'
import { RuntimeGate } from './components/RuntimeGate'
import { Workspace } from './components/studio/Workspace'
import { TooltipProvider } from './components/ui/tooltip'

export function App() {
  const [currentSkillId, setCurrentSkillId] = useState<string | null>(null)

  return (
    <TooltipProvider delayDuration={0}>
      <RuntimeGate>
        <Workspace
          skillId={currentSkillId}
          onSelectSkill={setCurrentSkillId}
          onCloseSkill={() => setCurrentSkillId(null)}
        />
        <Toaster position="bottom-right" richColors closeButton />
      </RuntimeGate>
    </TooltipProvider>
  )
}
