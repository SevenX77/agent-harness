// DEV-ONLY verification harness for n3.1 lint near-projection (atoms #4/#5/#6).
// Mounts the REAL Workspace with a fixed skillId so Playwright can drive the real
// canvas / properties / editor render tree in a real browser. The API is mocked at
// the network layer by the Playwright spec (page.route), so this file fakes nothing.
import { StrictMode, useState } from 'react'
import { createRoot } from 'react-dom/client'
import '../src/index.css'
import '../src/store/themeStore'
import { Workspace } from '../src/components/studio/Workspace'
import { Toaster } from '../src/components/ui/sonner'
import { TooltipProvider } from '../src/components/ui/tooltip'
import { i18nReady } from '../src/i18n'

const INITIAL_SKILL_ID = new URLSearchParams(window.location.search).get('skill') ?? 'lint-projection-smoke'

function HarnessApp() {
  const [skillId, setSkillId] = useState<string | null>(INITIAL_SKILL_ID)
  return (
    <TooltipProvider delayDuration={0}>
      <Workspace skillId={skillId} onSelectSkill={setSkillId} onCloseSkill={() => setSkillId(null)} />
      <Toaster position="top-right" />
    </TooltipProvider>
  )
}

await i18nReady
createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <HarnessApp />
  </StrictMode>,
)
