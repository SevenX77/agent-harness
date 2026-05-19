import { renderToStaticMarkup } from 'react-dom/server'
import type { ReactNode } from 'react'
import { describe, expect, it, vi } from 'vitest'
import { WelcomePage } from './WelcomePage'
import type { SkillSummary } from '../../api/types'

const mismatchSkill: SkillSummary = {
  id: 'demo-skill',
  name: 'Demo skill',
  description: 'Checks config drift',
  phase_count: 2,
  has_golden: true,
  last_run_at: null,
  directory_path: '/tmp/demo-skill',
  config_mismatch: {
    actual_remote_url: 'https://gitea.example.test/bob/demo-skill.git',
    expected_remote_url: 'https://gitea.example.test/alice/demo-skill.git',
    recommendation: '建议以 .git/config 为基准 (per design.md 决策 22), 在 Settings 调整 User ID / Gitea Host',
  },
}

vi.mock('../../hooks/useSkills', () => ({
  useSkills: () => ({
    skills: [mismatchSkill],
    skillListError: null,
    mutateSkills: vi.fn(),
  }),
}))

vi.mock('../../hooks/useRecentSkills', () => ({
  useRecentSkills: () => ({
    recentSkills: [],
    rememberSkill: vi.fn(),
  }),
}))

vi.mock('../../api/client', () => ({
  api: {
    post: vi.fn(),
  },
}))

vi.mock('../../lib/tauri', () => ({
  selectSkillDirectory: vi.fn(),
}))

vi.mock('../ui/tooltip', () => ({
  Tooltip: ({ children }: { children: ReactNode }) => <>{children}</>,
  TooltipContent: ({ children }: { children: ReactNode }) => <div>{children}</div>,
  TooltipTrigger: ({ children }: { children: ReactNode }) => <>{children}</>,
}))

describe('WelcomePage', () => {
  it('renders Config drift badge when skill.config_mismatch is present', () => {
    const html = renderToStaticMarkup(<WelcomePage onSelectSkill={vi.fn()} />)

    expect(html).toContain('aria-label="Repo URL mismatch"')
    expect(html).toContain('Config drift')
    expect(html).toContain('https://gitea.example.test/bob/demo-skill.git')
  })
})
