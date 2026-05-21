import { renderToStaticMarkup } from 'react-dom/server'
import type { ReactNode } from 'react'
import { describe, expect, it, vi } from 'vitest'
import {
  ACTION_MENU_CLASSNAME,
  buildSkillCreatePayload,
  buildSkillImportPayload,
  formatCreateSkillError,
  formatImportSkillError,
  REVEAL_ACTION_LABEL,
  WelcomePage,
} from './WelcomePage'
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
    recommendation: 'Use .git/config as the source of truth, then adjust User ID / Gitea Host in Settings.',
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

  it('renders compact skill cards with the real folder path subtitle', () => {
    const html = renderToStaticMarkup(<WelcomePage onSelectSkill={vi.fn()} />)

    expect(html).not.toContain('min-h-32')
    expect(html).toContain('/tmp/demo-skill')
  })

  it('uses a short reveal action label in wider action menus', () => {
    expect(REVEAL_ACTION_LABEL).toBe('Show in folder')
    expect(ACTION_MENU_CLASSNAME).toBe('w-48')
  })

  it('builds create payload using the current /skills API contract', () => {
    expect(buildSkillCreatePayload('My Skill')).toEqual({
      skill_id: 'my-skill',
    })
  })

  it('builds create payload for a selected parent folder', () => {
    expect(buildSkillCreatePayload('My Skill', '/Users/sevenx/AgentStudio/Skills')).toEqual({
      skill_id: 'my-skill',
      directory_path: '/Users/sevenx/AgentStudio/Skills/my-skill',
    })
  })

  it('builds import payload for an existing selected directory', () => {
    expect(buildSkillImportPayload('/Users/sevenx/AgentStudio/Skills/My Skill')).toEqual({
      skill_id: 'my-skill',
      directory_path: '/Users/sevenx/AgentStudio/Skills/My Skill',
      import_existing: true,
    })
  })

  it('explains duplicate skill create failures', () => {
    const error = studioApiError({
      error_code: 'SKILL_ALREADY_EXISTS',
      message: 'Skill already exists: new-skill',
      details: { skill_id: 'new-skill' },
    })

    expect(formatCreateSkillError(error, 'new-skill')).toBe(
      'Cannot create "new-skill": a skill with this name already exists. Choose a different name.',
    )
  })

  it('explains invalid import folder failures', () => {
    const error = studioApiError({
      error_code: 'INVALID_DIRECTORY_PATH',
      message: 'Selected folder is not a Studio skill directory: missing GRAPH.md or SKILL.md.',
      details: { directory_path: '/tmp/not-a-skill', required_entry: 'GRAPH.md or SKILL.md' },
    })

    expect(formatImportSkillError(error)).toBe(
      'Cannot import this folder: selected folder is not a Studio skill directory: missing GRAPH.md or SKILL.md.',
    )
  })

  it('explains manifest validation failures with the first lint detail', () => {
    const error = studioApiError({
      error_code: 'MANIFEST_VALIDATION_FAILED',
      message: 'Manifest validation failed',
      details: {
        errors: [{
          file: 'phases/init/LOGIC.md',
          line: 1,
          message: 'LOGIC.md AST validation failed: python_callable is required',
        }],
      },
    })

    expect(formatImportSkillError(error)).toBe(
      'Cannot import this folder: phases/init/LOGIC.md:1 LOGIC.md AST validation failed: python_callable is required',
    )
    expect(formatCreateSkillError(error, 'new-skill')).toBe(
      'Cannot create "new-skill": phases/init/LOGIC.md:1 LOGIC.md AST validation failed: python_callable is required',
    )
  })
})

function studioApiError(data: Record<string, unknown>) {
  return { response: { data } }
}
