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
  REMOVE_ACTION_LABEL,
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
  recentError: null as string | null,
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
}

const recentEntry: RecentWorkspaceEntry = {
  absolutePath: '/tmp/demo-skill',
  displayName: 'Demo skill',
  identity: 'local:/tmp/demo-skill',
  lastOpenedAt: '2026-06-18T10:00:00.000Z',
}

vi.mock('../../hooks/useRecentSkills', () => ({
  useRecentSkills: () => ({
    recentWorkspaces: recentMocks.recentWorkspaces,
    rememberWorkspace: vi.fn(),
    removeWorkspace: vi.fn(),
    isHydrating: recentMocks.isHydrating,
    recentError: recentMocks.recentError,
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
  createSkillWorkspace: vi.fn(),
  openSkillWorkspace: vi.fn(),
}))

afterEach(() => {
  recentMocks.recentWorkspaces = []
  recentMocks.isHydrating = false
  recentMocks.recentError = null
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

  it('offers an MRU-only "Remove from recent" in the Recent card action menu (R1 follow-up)', () => {
    recentMocks.recentWorkspaces = [recentEntry]
    const html = renderHome()

    // The Recent card carries a ⋮ action-menu trigger. Radix portals the menu
    // content only once it is opened, so the closed SSR markup shows the trigger
    // but not the item labels — the item itself is contract-locked via the
    // exported label below and exercised interactively by the home Playwright
    // e2e, per the repo's "static render + e2e for interaction" convention.
    expect(html).toContain('aria-label="More actions for Demo skill"')

    // The remove action is MRU-only: the wording says "from recent", and it is
    // wired to the recent-store `removeWorkspace` hook (see handleRemove), NOT
    // to skill deletion. The destructive `DELETE /api/skills` action that #163
    // retired stays retired — removing a card never deletes the skill on disk.
    expect(REMOVE_ACTION_LABEL).toBe('Remove from recent')
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

  it('renders a local red error box when the Recent MRU read/path check fails (atom #9)', () => {
    recentMocks.recentError = 'Could not read recent skills'
    const html = renderHome()

    // The failure退路 is local: a destructive shadcn Alert in the Recent region
    // carrying the read/path-validation reason.
    expect(html).toContain('role="alert"')
    expect(html).toContain('text-destructive')
    expect(html).toContain('Could not read recent skills')
  })

  it('keeps the New skill and Open folder entries usable when Recent fails (不阻塞入口)', () => {
    recentMocks.recentError = 'Could not read recent skills'
    const html = renderHome()

    // Both top-level entries stay present and enabled — a Recent read failure
    // must never block creating or opening a workspace (D11). The buttons carry
    // a `disabled:` Tailwind utility either way, so assert on the rendered HTML
    // attribute (`disabled=""`), which only appears when actually disabled.
    expect(html).toContain('New skill')
    expect(html).toContain('Open folder')
    expect(html).not.toContain('disabled=""')
  })

  it('does not render the Recent error box when the MRU read succeeds', () => {
    recentMocks.recentWorkspaces = [recentEntry]
    recentMocks.recentError = null
    const html = renderHome()

    expect(html).not.toContain('role="alert"')
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
    // D2: Open folder runs through the Rust native-fs writer (openSkillWorkspace),
    // which never rejects for a missing manifest — only OS-level failures bubble
    // up, as a plain Rust string. So no manifest-rejection copy can ever surface.
    const osError = 'Selected path is not a directory: /tmp/not-a-skill'

    expect(formatImportSkillError(osError)).toBe(osError)
    expect(formatImportSkillError(osError)).not.toContain('missing GRAPH.md or SKILL.md')
  })

  it('surfaces the raw OS-level reason from a Rust open-folder error string', () => {
    // The open path rejects with a plain Rust string (no structured error_code),
    // so formatImportSkillError must surface it verbatim via errorMessage.
    const osError = 'Permission denied: /private/var/root'

    expect(formatImportSkillError(osError)).toBe(osError)
  })

  it('no longer produces manifest/lint rejection copy for Open folder', () => {
    // Even handed the retired structured MANIFEST payload, the dead "Cannot import
    // this folder" / lint branches are gone, so that copy is never generated.
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
    expect(formatImportSkillError(error)).not.toContain('python_callable validator')
  })

  it('surfaces the raw OS-level reason from a Rust create error string (no manifest/lint copy)', () => {
    // D2 (不卡导入): native-fs create rejects with a plain Rust string and emits
    // no structured error_code, so formatCreateSkillError must fall through to the
    // raw message and never produce manifest/lint validation copy.
    const error = 'Cannot create a new skill in a non-empty folder: /tmp/existing'

    expect(formatCreateSkillError(error, 'new-skill')).toBe(
      'Cannot create a new skill in a non-empty folder: /tmp/existing',
    )
  })

  it('does not emit MVP1 lint drift copy on the create path for a manifest payload', () => {
    // A structured MANIFEST_VALIDATION_FAILED payload no longer maps to lint copy
    // on create; it is unreachable for Rust string errors and the create branch
    // was removed, so the fallback errorMessage is used.
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

    const message = formatCreateSkillError(error, 'new-skill')
    expect(message).not.toContain('python_callable validator')
    expect(message).not.toContain('phases/init/LOGIC.md:1')
  })

  it('does not show stale /skills import validation copy for Open folder', () => {
    // The retired POST /skills import contract no longer drives Open folder, so
    // the "/skills API contract" / "Cannot import this folder" copy is unreachable
    // — even a structured request-validation payload falls through to errorMessage.
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
