import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { LintError, LintResult } from '../api/types'
import type { DebouncedLintTarget } from './useDebouncedLint'

// ── Business-logic layer ────────────────────────────────────────────────────
// Pure projections of the backend lint payload. These cover edit → debounce →
// diagnostics WITHOUT React: they are the single-source-of-truth mappers the panel
// renders, so a regression here is a regression in what the user sees.

import { deriveLintDiagnostics, formatLintDiagnostic } from './useDebouncedLint'

function makeError(overrides: Partial<LintError> = {}): LintError {
  return {
    file: 'phases/draft/SKILL.md',
    line: 12,
    column: null,
    error_code: 'F-v3-001',
    severity: 'error',
    message: 'Unknown model alias',
    phase_name: 'draft',
    ...overrides,
  }
}

describe('deriveLintDiagnostics', () => {
  it('returns the engine error list verbatim (single source of truth)', () => {
    const errors = [makeError(), makeError({ error_code: 'F-v3-002', severity: 'warning' })]
    const result: LintResult = { status: 'failed', errors, phases_summary: null }
    expect(deriveLintDiagnostics(result)).toBe(errors)
  })

  it('returns an empty list for a passed lint with no errors', () => {
    const result: LintResult = { status: 'passed', errors: [], phases_summary: null }
    expect(deriveLintDiagnostics(result)).toEqual([])
  })

  it('returns an empty list for a null / undefined payload (in-flight or idle)', () => {
    expect(deriveLintDiagnostics(null)).toEqual([])
    expect(deriveLintDiagnostics(undefined)).toEqual([])
  })

  it('returns an empty list when the payload lacks a usable errors array', () => {
    const malformed = { status: 'failed', phases_summary: null } as unknown as LintResult
    expect(deriveLintDiagnostics(malformed)).toEqual([])
  })
})

describe('formatLintDiagnostic', () => {
  it('renders file:line - code - message when all parts present', () => {
    expect(formatLintDiagnostic(makeError())).toBe(
      'phases/draft/SKILL.md:12 - F-v3-001 - Unknown model alias',
    )
  })

  it('drops the line segment when there is no line', () => {
    expect(formatLintDiagnostic(makeError({ line: null }))).toBe(
      'phases/draft/SKILL.md - F-v3-001 - Unknown model alias',
    )
  })

  it('falls back to "unknown file" and drops the line when file is missing', () => {
    expect(
      formatLintDiagnostic(makeError({ file: null, line: null, message: 'boom' })),
    ).toBe('unknown file - F-v3-001 - boom')
  })

  it('omits the code segment when the engine returned no error_code', () => {
    expect(formatLintDiagnostic(makeError({ error_code: '' }))).toBe(
      'phases/draft/SKILL.md:12 - Unknown model alias',
    )
  })
})

// ── Real hook path ──────────────────────────────────────────────────────────
// Drive the actual useDebouncedLint effect: an edit schedules a debounced POST
// /lint, and the response becomes published status + rendered diagnostics. React is
// mocked with an indexed useState harness (the hook has status/result/message state);
// api.post is mocked so no real network call happens.

const reactHarness = vi.hoisted(() => ({
  states: [] as unknown[],
  setters: [] as Array<(next: unknown) => void>,
  cursor: 0,
  cleanup: undefined as undefined | (() => void),
  rerun: undefined as undefined | (() => void),
}))

vi.mock('react', () => ({
  useState<T>(initial: T) {
    const index = reactHarness.cursor
    reactHarness.cursor += 1
    if (reactHarness.states.length <= index) {
      reactHarness.states[index] = initial
      reactHarness.setters[index] = (next: unknown) => {
        const current = reactHarness.states[index]
        reactHarness.states[index] =
          typeof next === 'function' ? (next as (value: unknown) => unknown)(current) : next
      }
    }
    return [reactHarness.states[index], reactHarness.setters[index]] as [T, (next: T) => void]
  },
  useEffect(effect: () => void | (() => void)) {
    reactHarness.cleanup?.()
    reactHarness.cleanup = effect() || undefined
  },
}))

const apiHarness = vi.hoisted(() => ({
  post: vi.fn(),
}))

vi.mock('../api/client', () => ({
  api: { post: apiHarness.post },
}))

const { useDebouncedLint, relintSkillFromDisk, lintStatusStorageKey, lintStatusEvent, lintResultEvent, LINT_DEBOUNCE_MS } = await import(
  './useDebouncedLint'
)

/** Shared window/sessionStorage/CustomEvent stubs for both lint suites. */
function installLintDom() {
  const store = new Map<string, string>()
  const dispatched: Array<{ type: string; detail: unknown }> = []
  vi.stubGlobal('window', {
    setTimeout: globalThis.setTimeout,
    clearTimeout: globalThis.clearTimeout,
    dispatchEvent: (event: { type: string; detail: unknown }) => {
      dispatched.push(event)
      return true
    },
  })
  vi.stubGlobal('CustomEvent', class {
    type: string
    detail: unknown
    constructor(type: string, init?: { detail?: unknown }) {
      this.type = type
      this.detail = init?.detail
    }
  })
  vi.stubGlobal('sessionStorage', {
    getItem: (key: string) => store.get(key) ?? null,
    setItem: (key: string, value: string) => store.set(key, value),
  })
  Reflect.set(globalThis, '__lintStore', store)
  Reflect.set(globalThis, '__lintDispatched', dispatched)
  return { store, dispatched }
}

function run(skillId: string, markdown: string, target?: DebouncedLintTarget) {
  reactHarness.cursor = 0
  // eslint-disable-next-line react-hooks/rules-of-hooks -- test harness drives the hook through a mocked React runtime
  useDebouncedLint(skillId, markdown, target)
}

function hookState() {
  return {
    status: reactHarness.states[0],
    result: reactHarness.states[1],
    message: reactHarness.states[2],
  }
}

describe('useDebouncedLint real hook path', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    reactHarness.states = []
    reactHarness.setters = []
    reactHarness.cursor = 0
    reactHarness.cleanup = undefined
    apiHarness.post.mockReset()
    installLintDom()
  })

  afterEach(() => {
    reactHarness.cleanup?.()
    vi.unstubAllGlobals()
    vi.useRealTimers()
  })

  it('empty content stays idle and never calls /lint', () => {
    run('skill-1', '   ')
    expect(hookState().status).toBe('idle')
    const store = Reflect.get(globalThis, '__lintStore') as Map<string, string>
    expect(store.get(lintStatusStorageKey('skill-1'))).toBe('idle')
    vi.advanceTimersByTime(LINT_DEBOUNCE_MS + 50)
    expect(apiHarness.post).not.toHaveBeenCalled()
  })

  it('an edit publishes checking immediately, then POSTs /lint after the debounce', async () => {
    const payload: LintResult = {
      status: 'failed',
      errors: [makeError()],
      phases_summary: null,
    }
    apiHarness.post.mockResolvedValue({ data: payload })

    run('skill-1', '# Draft\nmodel: bogus')
    expect(hookState().status).toBe('checking')
    expect(apiHarness.post).not.toHaveBeenCalled()

    vi.advanceTimersByTime(LINT_DEBOUNCE_MS)
    expect(apiHarness.post).toHaveBeenCalledWith('/skills/skill-1/lint', {
      markdown: '# Draft\nmodel: bogus',
    })

    await vi.waitFor(() => {
      expect(hookState().status).toBe('failed')
    })
    const result = hookState().result as LintResult
    expect(deriveLintDiagnostics(result)).toHaveLength(1)
    const store = Reflect.get(globalThis, '__lintStore') as Map<string, string>
    expect(store.get(lintStatusStorageKey('skill-1'))).toBe('failed')
    const dispatched = Reflect.get(globalThis, '__lintDispatched') as Array<{ type: string; detail: unknown }>
    expect(dispatched.some((event) => event.type === lintStatusEvent)).toBe(true)
    // N3 atom #4: the full LintResult is lifted on a sibling event so the workspace can
    // overlay these errors onto the canvas-node / properties projection.
    const resultEvent = dispatched.find(
      (event) => event.type === lintResultEvent && (event.detail as { result?: unknown }).result,
    )
    expect(resultEvent).toBeDefined()
    expect((resultEvent!.detail as { skillId: string }).skillId).toBe('skill-1')
    expect((resultEvent!.detail as { result: LintResult }).result.errors).toHaveLength(1)
  })

  it('sends the edited file path and workspace root with phase-file lint requests', async () => {
    const payload: LintResult = { status: 'passed', errors: [], phases_summary: null }
    apiHarness.post.mockResolvedValue({ data: payload })

    run('skill-1', '---\nname: review\n---\n', {
      filePath: 'phases/review/SKILL.md',
      workspaceRoot: 'D:/repo/skills/story-deconstruction-v3',
    })
    vi.advanceTimersByTime(LINT_DEBOUNCE_MS)

    expect(apiHarness.post).toHaveBeenCalledWith('/skills/skill-1/lint', {
      markdown: '---\nname: review\n---\n',
      file_path: 'phases/review/SKILL.md',
      workspace_root: 'D:/repo/skills/story-deconstruction-v3',
    })
  })

  it('a passed lint publishes passed with no diagnostics', async () => {
    const payload: LintResult = { status: 'passed', errors: [], phases_summary: null }
    apiHarness.post.mockResolvedValue({ data: payload })

    run('skill-1', '# Clean')
    vi.advanceTimersByTime(LINT_DEBOUNCE_MS)

    await vi.waitFor(() => {
      expect(hookState().status).toBe('passed')
    })
    expect(deriveLintDiagnostics(hookState().result as LintResult)).toEqual([])
  })

  it('a failed /lint request degrades to failed with a message and no stale diagnostics', async () => {
    apiHarness.post.mockRejectedValue(new Error('network down'))

    run('skill-1', '# Draft')
    vi.advanceTimersByTime(LINT_DEBOUNCE_MS)

    await vi.waitFor(() => {
      expect(hookState().status).toBe('failed')
    })
    expect(hookState().message).toBe('network down')
    expect(hookState().result).toBeNull()
    expect(deriveLintDiagnostics(hookState().result as LintResult | null)).toEqual([])
  })
})

// ── Canvas source-truth mutation relint (03_compile A13 / compile-lint F1+F6) ──
// A canvas topology write (connect / disconnect / delete phase) rewrites GRAPH.md
// without the editor. The write settles to disk BEFORE the relint fires, so
// relintSkillFromDisk POSTs with NO markdown body (the disk tree is the truth) and
// broadcasts on the SAME status/result channels, so all three projections replace
// their stale state instead of merely being cleared.

describe('relintSkillFromDisk', () => {
  beforeEach(() => {
    apiHarness.post.mockReset()
    installLintDom()
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('POSTs immediately with no markdown body and broadcasts status + result', async () => {
    const payload: LintResult = { status: 'failed', errors: [makeError()], phases_summary: null }
    apiHarness.post.mockResolvedValue({ data: payload })

    const result = await relintSkillFromDisk('skill-1')

    expect(apiHarness.post).toHaveBeenCalledWith('/skills/skill-1/lint', {})
    expect(result).toEqual(payload)
    const store = Reflect.get(globalThis, '__lintStore') as Map<string, string>
    expect(store.get(lintStatusStorageKey('skill-1'))).toBe('failed')
    const dispatched = Reflect.get(globalThis, '__lintDispatched') as Array<{ type: string; detail: unknown }>
    const resultEvent = dispatched.find(
      (event) => event.type === lintResultEvent && (event.detail as { result?: unknown }).result,
    )
    expect(resultEvent).toBeDefined()
    expect((resultEvent!.detail as { skillId: string; result: LintResult }).result.errors).toHaveLength(1)
  })

  it('forwards workspace_root for workspace-based skills', async () => {
    const payload: LintResult = { status: 'passed', errors: [], phases_summary: null }
    apiHarness.post.mockResolvedValue({ data: payload })

    await relintSkillFromDisk('skill-1', 'D:/repo/skills/demo')

    expect(apiHarness.post).toHaveBeenCalledWith('/skills/skill-1/lint', {
      workspace_root: 'D:/repo/skills/demo',
    })
  })

  it('a failed request publishes failed and a null result (no stale projection)', async () => {
    apiHarness.post.mockRejectedValue(new Error('network down'))

    const result = await relintSkillFromDisk('skill-1')

    expect(result).toBeNull()
    const store = Reflect.get(globalThis, '__lintStore') as Map<string, string>
    expect(store.get(lintStatusStorageKey('skill-1'))).toBe('failed')
    const dispatched = Reflect.get(globalThis, '__lintDispatched') as Array<{ type: string; detail: unknown }>
    const lastResultEvent = [...dispatched].reverse().find((event) => event.type === lintResultEvent)
    expect((lastResultEvent!.detail as { result: unknown }).result).toBeNull()
  })
})
