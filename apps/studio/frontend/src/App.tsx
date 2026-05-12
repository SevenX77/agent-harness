import { useState } from 'react'
import { Toaster } from 'sonner'
import { RuntimeGate } from './components/RuntimeGate'
import { Workspace } from './components/studio/Workspace'
import { WelcomeOverlay } from './components/welcome/WelcomeOverlay'

export function App() {
  const [currentSkillId, setCurrentSkillId] = useState<string | null>(null)

  return (
    <RuntimeGate>
      <Workspace skillId={currentSkillId} onCloseSkill={() => setCurrentSkillId(null)} />
      {currentSkillId === null ? <WelcomeOverlay onSelect={setCurrentSkillId} /> : null}
      <Toaster position="bottom-right" richColors closeButton />
    </RuntimeGate>
  )
}
