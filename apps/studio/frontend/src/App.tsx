import { useState } from 'react'
import { RuntimeGate } from './components/RuntimeGate'
import { Workspace } from './components/studio/Workspace'
import { Toaster } from './components/ui/sonner'
import { TooltipProvider } from './components/ui/tooltip'
import { useEditablePasteShortcut } from './hooks/useEditablePasteShortcut'
import { useNativeDoubleClickGuard } from './hooks/useNativeDoubleClickGuard'

export function App() {
  const [currentSkillId, setCurrentSkillId] = useState<string | null>(null)
  useNativeDoubleClickGuard()
  useEditablePasteShortcut()

  return (
    <TooltipProvider delayDuration={0}>
      <RuntimeGate>
        <Workspace
          skillId={currentSkillId}
          onSelectSkill={setCurrentSkillId}
          onCloseSkill={() => setCurrentSkillId(null)}
        />
        <Toaster position="bottom-right" />
      </RuntimeGate>
    </TooltipProvider>
  )
}
