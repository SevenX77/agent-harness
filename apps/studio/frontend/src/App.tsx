import { useState } from 'react'
import { Toaster } from 'sonner'
import { RuntimeGate } from './components/RuntimeGate'
import { Workspace } from './components/studio/Workspace'

export function App() {
  const [currentSkillId, setCurrentSkillId] = useState<string | null>(null)

  return (
    <RuntimeGate>
      <Workspace
        skillId={currentSkillId}
        onSelectSkill={setCurrentSkillId}
        onCloseSkill={() => setCurrentSkillId(null)}
      />
      <Toaster position="bottom-right" richColors closeButton />
    </RuntimeGate>
  )
}
