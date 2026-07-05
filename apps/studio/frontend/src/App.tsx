import { useState } from 'react'
import { SWRConfig } from 'swr'
import { RuntimeGate } from './components/RuntimeGate'
import { Workspace } from './components/studio/Workspace'
import { Toaster } from './components/ui/sonner'
import { TooltipProvider } from './components/ui/tooltip'
import { useEditablePasteShortcut } from './hooks/useEditablePasteShortcut'
import { useNativeDoubleClickGuard } from './hooks/useNativeDoubleClickGuard'
import { STUDIO_TRUTH_SWR_CONFIG } from './hooks/studio-swr-policy'

export function App() {
  const [currentSkillId, setCurrentSkillId] = useState<string | null>(null)
  useNativeDoubleClickGuard()
  useEditablePasteShortcut()

  return (
    <SWRConfig value={STUDIO_TRUTH_SWR_CONFIG}>
      <TooltipProvider>
        <RuntimeGate>
          <Workspace
            skillId={currentSkillId}
            onSelectSkill={setCurrentSkillId}
            onCloseSkill={() => setCurrentSkillId(null)}
          />
          <Toaster position="bottom-right" />
        </RuntimeGate>
      </TooltipProvider>
    </SWRConfig>
  )
}
