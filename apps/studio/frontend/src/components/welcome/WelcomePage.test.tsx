import { renderToStaticMarkup } from 'react-dom/server'
import { afterEach, describe, expect, it, vi } from 'vitest'
import {
  ACTION_MENU_CLASSNAME,
  buildSkillCreatePayload,
  buildSkillImportPayload,
  defaultSkillsDirectory,
  formatCreateSkillError,
  formatImportSkillError,
  RecentSkeleton,
  registeredSkillIdForImport,
  REVEAL_ACTION_LABEL,
  WelcomePage,
} from './WelcomePage'
import type { RecentWorkspaceEntry } from '../../hooks/useRecentSkills'
import type { SkillSummary } from '../../api/types'

const toastMock = vi.hoisted(() => Object.assign(vi.fn(), {
  dismiss: vi.fn(),
  error: vi.fn(),
  success: vi.fn(),
}))

const recentMocks = vi.hoisted(() => ({
  recentWorkspaces: [] as RecentWorkspaceEntry[],
  isHydrating: false,
}))

// A registry skill carrying derived fields. After the N1 MRU rewrite Home no
// longer projects these onto cards, so they must NOT surface in the render.
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

const recentEntry: RecentWorkspaceEntry = {
  absolutePath: '/tmp/demo-skill',
  displayName: 'Demo skill',
  identity: 'local:/tmp/demo-skill',
  lastOpenedAt: '2026-06-18T10:00:00.000Z',
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
    recentWorkspaces: recentMocks.recentWorkspaces,
    rememberWorkspace: vi.fn(),
    removeWorkspace: vi.fn(),
    isHydrating: recentMocks.isHydrating,
  }),
}))

vi.mock('../../api/client', () => ({
  api: {
    delete: vi.fn(),
    post: vi.fn(),
  },
}))

vi.mock('sonner', () => ({
  toast: toastMock,
}))

vi.mock('../../config/runtime', () => ({
  getRuntimeConfig: vi.fn(() => ({
    resourceDir: '/studio/resources',
    configDir: '/studio/config',
  })),
}))

vi.mock('../../lib/tauri', () => ({
  revealInFileManager: vi.fn(),
  selectSkillDirectory: vi.fn(),
  addRecentWorkspace: vi.fn(),
  ensureWorkspaceSupportDirs: vi.fn(),
}))

afterEach(() => {
  recentMocks.recentWorkspaces = []
  recentMocks.isHydrating = false
})

function renderHome() {
  return renderToStaticMarkup(<WelcomePage onSelectSkill={vi.fn()} />)
}

describe('WelcomePage', () => {
  it('drops the decorative "Desktop workspace" label and registry wording from the Recent header', () => {
    const html = renderHome()

    expect(html).not.toContain('Desktop workspace')
    expect(html).not.toContain('Recent skills')
    expect(html).toContain('>Recent<')
  })

  it('renders Recent cards purely from the MRU store', () => {
    recentMocks.recentWorkspaces = [recentEntry]
    const html = renderHome()

    expect(html).toContain('Demo skill')
    expect(html).toContain('/tmp/demo-skill')
  })

  it('does not project registry-derived phase / Golden / Config drift fields onto Recent cards', () => {
    recentMocks.recentWorkspaces = [recentEntry]
    const html = renderHome()

    expect(html).not.toContain('phases')
    expect(html).not.toContain('Golden')
    expect(html).not.toContain('Config drift')
    expect(html).not.toContain('aria-label="Repo URL mismatch"')
    expect(html).not.toContain('https://gitea.example.test/bob/demo-skill.git')
  })

  it('removes the Remove entry from the Recent card action menu (R1)', () => {
    recentMocks.recentWorkspaces = [recentEntry]
    const html = renderHome()

    // Radix renders menu content into a portal only once opened, so the closed
    // SSR markup shows the trigger but no item labels. The destructive Remove
    // action and its DELETE /api/skills wiring are gone from the source, so
    // "Remove" must not appear anywhere in the static render.
    expect(html).toContain('aria-label="More actions for Demo skill"')
    expect(html).not.toContain('Remove')
  })

  it('renders Open folder as the local workspace entry point', () => {
    const html = renderHome()

    expect(html).toContain('Open folder')
    expect(html).not.toContain('Import skill')
    expect(html).not.toContain('Importing')
  })

  it('renders compact skill cards with the real folder path subtitle', () => {
    recentMocks.recentWorkspaces = [recentEntry]
    const html = renderHome()

    expect(html).not.toContain('min-h-32')
    expect(html).toContain('/tmp/demo-skill')
  })

  it('keeps selectable skill cards on the local shadcn Card default surface', () => {
    recentMocks.recentWorkspaces = [recentEntry]
    const html = renderHome()

    expect(html).toContain('ring-1 ring-foreground/10')
    expect(html).toContain('data-size="sm"')
    expect(html).not.toContain('border-2')
    expect(html).not.toContain('ring-border/80')
    expect(html).not.toContain('[box-shadow:none]')
  })

  it('fixes skill card actions while allowing two lines for the folder path', () => {
    recentMocks.recentWorkspaces = [recentEntry]
    const html = renderHome()

    expect(html).toContain('absolute right-2 top-2 z-10')
    expect(html).toContain('min-w-0 flex-1 pr-12')
    expect(html).toContain('line-clamp-2 min-h-10 break-all')
    expect(html).toContain('hover:ring-2')
    expect(html).toContain('hover:ring-primary/70')
  })

  it('shows an IDE-start empty state without "import" wording when the MRU is empty', () => {
    recentMocks.recentWorkspaces = []
    const html = renderHome()

    expect(html).toContain('No recent skills')
    expect(html).toContain('open a folder')
    expect(html).not.toContain('import')
    expect(html).not.toContain('Create or import')
  })

  it('renders a Recent skeleton placeholder during the cold-start hydration window', () => {
    recentMocks.isHydrating = true
    const html = renderHome()

    expect(html).toContain('data-recent-skeleton="true"')
    expect(html).toContain('animate-pulse')
    expect(html).not.toContain('No recent skills')
  })

  it('renders the standalone RecentSkeleton from the shared shadcn Skeleton primitive', () => {
    const html = renderToStaticMarkup(<RecentSkeleton />)

    expect(html).toContain('data-recent-skeleton="true"')
    expect(html).toContain('animate-pulse')
    expect(html).toContain('data-slot="skeleton"')
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

  it('builds an import-existing payload so Open folder creates a backend identity for local paths', () => {
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
    const html = renderHome()

    expect(html).toContain('Default: /studio/config/Skills')
  })

  it('does not require a registered skill match before opening a selected folder path', () => {
    expect(registeredSkillIdForImport('/workspace/demo-skill/', [mismatchSkill])).toBeNull()
  })

  it('does not infer workspace identity from a normalized folder name collision', () => {
    expect(registeredSkillIdForImport('/other/place/Demo Skill', [mismatchSkill])).toBeNull()
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

  it('does not present missing GRAPH.md or SKILL.md as a Home/Open folder blocker', () => {
    const error = studioApiError({
      error_code: 'INVALID_DIRECTORY_PATH',
      message: 'Selected folder is not a Studio skill directory: missing GRAPH.md or SKILL.md.',
      details: { directory_path: '/tmp/not-a-skill', required_entry: 'GRAPH.md or SKILL.md' },
    })

    expect(formatImportSkillError(error)).not.toContain('missing GRAPH.md or SKILL.md')
  })

  it('does not use import-time manifest lint failures to block Open folder', () => {
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

    expect(formatImportSkillError(error)).not.toContain('Cannot import this folder')
    expect(formatCreateSkillError(error, 'new-skill')).toBe(
      'Cannot create "new-skill": phases/init/LOGIC.md:1 LOGIC.md hit a legacy python_callable validator. MVP1 logic phases use actions/<phase>.py, not LOGIC.md python callable blocks.',
    )
  })

  it('turns old scaffold python_callable validation into MVP1 drift copy', () => {
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

    const message = formatCreateSkillError(error, 'new-skill')
    expect(message).toBe(
      'Cannot create "new-skill": phases/init/LOGIC.md:1 LOGIC.md hit a legacy python_callable validator. MVP1 logic phases use actions/<phase>.py, not LOGIC.md python callable blocks.',
    )
    expect(message).not.toContain('Add a <python_callable>')
  })

  it('does not show stale /skills import validation copy for Open folder', () => {
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

    expect(formatImportSkillError(error)).not.toContain('/skills API contract')
    expect(formatImportSkillError(error)).not.toContain('Cannot import this folder')
  })
})

function studioApiError(data: Record<string, unknown>) {
  return { response: { data } }
}
