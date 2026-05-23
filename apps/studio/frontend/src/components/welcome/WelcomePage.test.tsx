import { renderToStaticMarkup } from 'react-dom/server'
import type { ReactNode } from 'react'
import { describe, expect, it, vi } from 'vitest'
import {
  ACTION_MENU_CLASSNAME,
  buildSkillCreatePayload,
  buildSkillImportPayload,
  defaultSkillsDirectory,
  formatCreateSkillError,
  formatImportSkillError,
  registeredSkillIdForImport,
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

vi.mock('../../config/runtime', () => ({
  getRuntimeConfig: vi.fn(() => ({
    resourceDir: '/studio/resources',
    configDir: '/studio/config',
  })),
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

  it('keeps selectable skill cards on the local shadcn Card default surface', () => {
    const html = renderToStaticMarkup(<WelcomePage onSelectSkill={vi.fn()} />)

    expect(html).toContain('ring-1 ring-foreground/10')
    expect(html).toContain('data-size="sm"')
    expect(html).not.toContain('border-2')
    expect(html).not.toContain('ring-border/80')
    expect(html).not.toContain('[box-shadow:none]')
  })

  it('fixes skill card actions while allowing two lines for the folder path', () => {
    const html = renderToStaticMarkup(<WelcomePage onSelectSkill={vi.fn()} />)

    expect(html).toContain('absolute right-2 top-2 z-10')
    expect(html).toContain('min-w-0 flex-1 pr-12')
    expect(html).toContain('line-clamp-2 min-h-10 break-all')
    expect(html).toContain('hover:ring-2')
    expect(html).toContain('hover:ring-primary/70')
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

  it('derives the default skill parent from the Tauri resource dir', () => {
    expect(defaultSkillsDirectory()).toBe('/studio/config/Skills')
  })

  it('uses the configured default skill parent when app settings provide one', () => {
    expect(defaultSkillsDirectory('/Users/sevenx/graph_skills')).toBe('/Users/sevenx/graph_skills')
  })

  it('renders the concrete default skill parent path', () => {
    const html = renderToStaticMarkup(<WelcomePage onSelectSkill={vi.fn()} />)

    expect(html).toContain('Default: /studio/config/Skills')
  })

  it('finds an already registered skill by selected import directory path', () => {
    expect(registeredSkillIdForImport('/tmp/demo-skill/', [mismatchSkill])).toBe('demo-skill')
  })

  it('falls back to matching an already registered skill by normalized selected folder name', () => {
    expect(registeredSkillIdForImport('/other/place/Demo Skill', [mismatchSkill])).toBe('demo-skill')
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
      'Cannot import this folder: phases/init/LOGIC.md:1 LOGIC.md is missing <python_callable>. Add a <python_callable> block that names a Python function in phases/<phase>/actions/.',
    )
    expect(formatCreateSkillError(error, 'new-skill')).toBe(
      'Cannot create "new-skill": phases/init/LOGIC.md:1 LOGIC.md is missing <python_callable>. Add a <python_callable> block that names a Python function in phases/<phase>/actions/.',
    )
  })

  it('turns old scaffold python_callable validation into actionable copy', () => {
    const error = studioApiError({
      error_code: 'MANIFEST_VALIDATION_FAILED',
      message: 'Manifest validation failed',
      details: {
        errors: [{
          file: 'phases/init/LOGIC.md',
          line: 1,
          message: '[F-v21-route] /tmp/.new-skill.tmp/phases/init/LOGIC.md:1 LOGIC.md AST validation failed: 1 validation error for LogicNodeAST\npython_callable\n  Input should be a valid string [type=string_type, input_value=None, input_type=None]\n    For further information visit https://errors.pydantic.dev/2.13/v/string_type',
        }],
      },
    })

    expect(formatCreateSkillError(error, 'new-skill')).toBe(
      'Cannot create "new-skill": phases/init/LOGIC.md:1 LOGIC.md is missing <python_callable>. Add a <python_callable> block that names a Python function in phases/<phase>/actions/.',
    )
  })

  it('explains stale sidecar request validation on import', () => {
    const error = studioApiError({
      error_code: 'MANIFEST_VALIDATION_FAILED',
      message: 'Request validation failed',
      details: {
        errors: [{
          type: 'extra_forbidden',
          loc: ['body', 'import_existing'],
          msg: 'Extra inputs are not permitted',
        }],
      },
    })

    expect(formatImportSkillError(error)).toBe(
      'Cannot import this folder: the running backend does not support folder import yet. Quit and restart Studio so the updated sidecar is loaded.',
    )
  })
})

function studioApiError(data: Record<string, unknown>) {
  return { response: { data } }
}
