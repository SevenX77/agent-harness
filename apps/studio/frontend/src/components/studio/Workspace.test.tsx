import { renderToStaticMarkup } from 'react-dom/server'
import type { ReactNode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { compareReplayArgsForJudgeResult, Workspace } from './Workspace'
import { CURRENT_SCHEMA_VERSION } from '@/config/schema'
import type { SkillDetail } from '@/api/types'

const mocks = vi.hoisted(() => ({
  panelsProps: null as null | {
    onPhaseFileSave?: (payload: { path: string; content: string; expectedHash: string }) => Promise<void> | void
    workspaceRoot?: string | null
  },
  graphCanvasProps: null as null | {
    skillId?: string | null
    onPersistConnection?: (connection: { source: string; target: string }) => Promise<void> | void
    onReconnectConnection?: (
      disconnect: { source: string; target: string },
      connect: { source: string; target: string },
    ) => Promise<void> | void
  },
  centerActionBarProps: null as null | {
    stage?: string
    onCompile?: () => Promise<void> | void
    onPredict?: () => Promise<void> | void
    onRun?: () => Promise<void> | void
    onCreatePhase?: (kind: 'skill' | 'logic' | 'subgraph') => Promise<void> | void
  },
  conflictDialogProps: null as null | { onOverwriteRetry?: () => void },
  copilotProps: [] as Array<{
    skillId: string | null
    workspaceRoot?: string | null
    view?: 'edit' | 'eval'
    judgeRefs?: {
      runResultsRef: string
      baselineRef: string
    } | null
    onJudgePrepared?: (refs: unknown) => void
  }>,
  useSkillsIds: [] as Array<string | null>,
  goldenDiffCalls: [] as Array<{
    skillId: string | null
    runId: string | null
    workspaceRoot?: string | null
  }>,
  goldenDiffResult: null as null | {
    baseline_ref: string
    run_results_ref: string
  },
  goldenDiffCompare: vi.fn(),
  compileSkill: vi.fn(),
  getResumeValidity: vi.fn(),
  postPredictRun: vi.fn(),
  resolveRunInput: vi.fn(),
  resumeRun: vi.fn(),
  startRun: vi.fn(),
  writeSkillFile: vi.fn(),
  serializeSkillGraph: vi.fn(),
  mutateSkillDetail: vi.fn(),
  invoke: vi.fn(),
  lintStatus: 'idle' as 'idle' | 'checking' | 'passed' | 'failed',
}))

const toastMocks = vi.hoisted(() => ({
  error: vi.fn(),
  success: vi.fn(),
}))

vi.mock('@tauri-apps/api/core', () => ({
  invoke: mocks.invoke,
}))

vi.mock('@/api/client', () => ({
  compileSkill: mocks.compileSkill,
  fetcher: vi.fn(async () => []),
  getResumeValidity: mocks.getResumeValidity,
  getSkillDetail: vi.fn(),
  postPredictRun: mocks.postPredictRun,
  resolveRunInput: mocks.resolveRunInput,
  resumeRun: mocks.resumeRun,
  serializeSkillGraph: mocks.serializeSkillGraph,
  startRun: mocks.startRun,
  writeSkillFile: mocks.writeSkillFile,
  wsUrl: () => 'ws://127.0.0.1:8787/ws/events',
}))

vi.mock('@/hooks/useSkills', () => ({
  useSkills: (skillId: string | null) => {
    mocks.useSkillsIds.push(skillId)
    return {
      skillDetail: skillId ? skillDetail(skillId) : undefined,
      skillDetailError: null,
      mutateSkillDetail: mocks.mutateSkillDetail,
    }
  },
}))

vi.mock('@/hooks/useCopilotContext', () => ({
  useCopilotContext: vi.fn(),
}))

vi.mock('@/hooks/useDebouncedLint', () => ({
  lintStatusEvent: 'studio-lint-status-changed',
  readLintStatus: () => mocks.lintStatus,
}))

vi.mock('@/hooks/useGoldenDiff', () => ({
  useGoldenDiff: (
    skillId: string | null,
    runId: string | null,
    workspaceRoot?: string | null,
  ) => {
    mocks.goldenDiffCalls.push({ skillId, runId, workspaceRoot })
    return {
      result: mocks.goldenDiffResult,
      loading: false,
      error: null,
      compare: mocks.goldenDiffCompare,
      promote: vi.fn(async () => null),
      clear: vi.fn(),
    }
  },
}))

vi.mock('@/lib/hash', () => ({
  sha256Hex: vi.fn(async () => 'graph-hash'),
}))

vi.mock('@/components/GraphCanvas', () => ({
  GraphCanvas: (props: {
    skillId?: string | null
    onPersistConnection?: (connection: { source: string; target: string }) => Promise<void> | void
    onReconnectConnection?: (
      disconnect: { source: string; target: string },
      connect: { source: string; target: string },
    ) => Promise<void> | void
  }) => {
    mocks.graphCanvasProps = props
    return <div data-testid="graph-canvas" />
  },
}))

vi.mock('@/components/copilot/copilot-panel', () => ({
  CopilotPanel: (props: {
    skillId: string | null
    workspaceRoot?: string | null
    view?: 'edit' | 'eval'
    judgeRefs?: {
      runResultsRef: string
      baselineRef: string
    } | null
    onJudgePrepared?: (refs: unknown) => void
  }) => {
    mocks.copilotProps.push(props)
    return <aside data-testid="copilot-panel" />
  },
}))

vi.mock('@/components/diff/DiffView', () => ({
  DiffView: () => <div data-testid="diff-view" />,
}))

vi.mock('@/components/ui/resizable', () => ({
  ResizableHandle: () => <div data-testid="resize-handle" />,
  ResizablePanel: ({ children }: { children: ReactNode }) => <div data-testid="resize-panel">{children}</div>,
  ResizablePanelGroup: ({ children }: { children: ReactNode }) => <div data-testid="resize-group">{children}</div>,
}))

vi.mock('./Header', () => ({
  Header: () => <header data-testid="header" />,
}))

vi.mock('./Panels', () => ({
  Panels: (props: {
    onPhaseFileSave?: (payload: { path: string; content: string; expectedHash: string }) => Promise<void> | void
    workspaceRoot?: string | null
  }) => {
    mocks.panelsProps = props
    return <aside data-testid="panels" />
  },
}))

vi.mock('./SettingsPage', () => ({
  SettingsPage: () => <div data-testid="settings" />,
}))

vi.mock('./SplitEditor', () => ({
  SplitEditor: () => <div data-testid="split-editor" />,
}))

vi.mock('./Toolbar', () => ({
  Toolbar: () => <nav data-testid="toolbar" />,
}))

vi.mock('./ConflictDialog', () => ({
  ConflictDialog: (props: { onOverwriteRetry?: () => void }) => {
    mocks.conflictDialogProps = props
    return <div data-testid="conflict-dialog" />
  },
}))

vi.mock('./center-action-bar', () => ({
  CenterActionBar: (props: {
    stage?: string
    onCompile?: () => Promise<void> | void
    onPredict?: () => Promise<void> | void
    onRun?: () => Promise<void> | void
    onCreatePhase?: (kind: 'skill' | 'logic' | 'subgraph') => Promise<void> | void
  }) => {
    mocks.centerActionBarProps = props
    return <div data-testid="center-action-bar" />
  },
}))

vi.mock('sonner', () => ({
  toast: toastMocks,
}))

describe('Workspace WS-1 local writer contracts', () => {
  beforeEach(() => {
    vi.stubGlobal('window', { __TAURI_INTERNALS__: {} })
    mocks.panelsProps = null
    mocks.graphCanvasProps = null
    mocks.centerActionBarProps = null
    mocks.conflictDialogProps = null
    mocks.copilotProps.length = 0
    mocks.useSkillsIds.length = 0
    mocks.goldenDiffCalls.length = 0
    mocks.goldenDiffResult = null
    mocks.goldenDiffCompare.mockReset()
    mocks.goldenDiffCompare.mockResolvedValue(null)
    mocks.writeSkillFile.mockReset()
    mocks.writeSkillFile.mockResolvedValue({ path: 'GRAPH.md', hash: 'python-hash' })
    mocks.compileSkill.mockReset()
    mocks.compileSkill.mockResolvedValue({
      status: 'ok',
      manifest_name: 'writer-smoke',
      phase_count: 2,
      skill_id: 'writer-smoke',
      artifact_ref: {
        artifact_id: 'writer-smoke',
        content_hash: `sha256:${'1'.repeat(64)}`,
        store: 'ephemeral',
        version: null,
        manifest_ref: 'file:///tmp/manifest.json',
        source_map_ref: 'file:///tmp/source_map.json',
      },
      source_map_ref: 'file:///tmp/source_map.json',
      execution_fingerprint: `sha256:${'2'.repeat(64)}`,
    })
    mocks.getResumeValidity.mockReset()
    mocks.getResumeValidity.mockResolvedValue({
      run_id: 'run-1',
      resume_allowed: true,
      reason: 'ok',
      checkpoint_id: 'checkpoint-review',
      checkpoint_ns: 'agent:review',
      resume_from_node_id: 'review',
      resume_to_node_id: null,
      dirty_fields: [],
      snapshot_content_hash: `sha256:${'1'.repeat(64)}`,
      current_content_hash: `sha256:${'1'.repeat(64)}`,
      snapshot_execution_fingerprint: `sha256:${'2'.repeat(64)}`,
      current_execution_fingerprint: `sha256:${'2'.repeat(64)}`,
    })
    mocks.postPredictRun.mockReset()
    mocks.postPredictRun.mockResolvedValue({
      is_predict: true,
      status: 'success',
      phases: [],
      path_diff: null,
    })
    mocks.resolveRunInput.mockReset()
    mocks.resolveRunInput.mockResolvedValue({ topic: 'mars' })
    mocks.resumeRun.mockReset()
    mocks.startRun.mockReset()
    mocks.startRun.mockResolvedValue({
      run_id: 'run-1',
      status: 'running',
      started_at: '2026-06-17T00:00:00Z',
      metrics: null,
      input_summary: null,
    })
    mocks.serializeSkillGraph.mockReset()
    mocks.serializeSkillGraph.mockResolvedValue({
      markdown_content: 'serialized graph\n',
      phase_count: 2,
      elapsed_ms: 1,
      current_hash: 'graph-hash',
    })
    mocks.mutateSkillDetail.mockReset()
    mocks.invoke.mockReset()
    mocks.invoke.mockResolvedValue({ path: 'GRAPH.md', hash: 'native-hash' })
    mocks.lintStatus = 'idle'
    toastMocks.error.mockReset()
    toastMocks.success.mockReset()
  })

  it('saves phase property edits through the Tauri native writer instead of FastAPI file write', async () => {
    renderWorkspace()

    await mocks.panelsProps?.onPhaseFileSave?.({
      path: 'phases/draft/SKILL.md',
      content: 'updated phase\n',
      expectedHash: 'phase-hash',
    })

    expect(mocks.writeSkillFile).not.toHaveBeenCalled()
    expect(mocks.invoke).toHaveBeenCalledWith('write_workspace_file', expect.objectContaining({
      relativePath: 'phases/draft/SKILL.md',
      content: 'updated phase\n',
      expectedHash: 'phase-hash',
    }))
    expect((mocks.invoke.mock.calls[0][1] as Record<string, unknown>)).not.toHaveProperty('path')
  })

  it('uses the sidecar graph serializer only for compute and persists GRAPH.md through Tauri', async () => {
    renderWorkspace()

    await mocks.graphCanvasProps?.onPersistConnection?.({ source: 'draft', target: 'review' })

    expect(mocks.serializeSkillGraph).toHaveBeenCalledWith(
      'writer-smoke',
      expect.arrayContaining([
        expect.objectContaining({ id: 'review', depends_on: ['draft'] }),
      ]),
      'graph-hash',
    )
    expect(mocks.writeSkillFile).not.toHaveBeenCalled()
    expect(mocks.invoke).toHaveBeenCalledWith('write_workspace_file', expect.objectContaining({
      relativePath: 'GRAPH.md',
      content: 'serialized graph\n',
      expectedHash: 'graph-hash',
    }))
    expect((mocks.invoke.mock.calls[0][1] as Record<string, unknown>)).not.toHaveProperty('path')
  })

  it('compiles after a canvas connection writes GRAPH.md successfully', async () => {
    renderWorkspace()

    await mocks.graphCanvasProps?.onPersistConnection?.({ source: 'draft', target: 'review' })

    expect(mocks.invoke).toHaveBeenCalledWith('write_workspace_file', expect.objectContaining({
      relativePath: 'GRAPH.md',
      content: 'serialized graph\n',
    }))
    expect(mocks.compileSkill).toHaveBeenCalledWith('writer-smoke')
  })

  it('shows compile success with artifact hash and execution fingerprint', async () => {
    renderWorkspace()

    await mocks.centerActionBarProps?.onCompile?.()

    expect(mocks.compileSkill).toHaveBeenCalledWith('writer-smoke')
    expect(toastMocks.success).toHaveBeenCalledWith(expect.stringContaining('writer-smoke'))
    expect(toastMocks.success).toHaveBeenCalledWith(expect.stringContaining('sha256:11111111'))
    expect(toastMocks.success).toHaveBeenCalledWith(expect.stringContaining('fp sha256:22222222'))
  })

  it('predict button resolves selected input and calls the predict API without source paths', async () => {
    renderWorkspace()

    await mocks.centerActionBarProps?.onPredict?.()

    expect(mocks.resolveRunInput).toHaveBeenCalledWith('writer-smoke', null)
    expect(mocks.postPredictRun).toHaveBeenCalledWith('writer-smoke', { topic: 'mars' })
    expect(JSON.stringify(mocks.postPredictRun.mock.calls)).not.toContain('skill_path')
    expect(JSON.stringify(mocks.postPredictRun.mock.calls)).not.toContain('source_path')
  })

  it('keeps path-backed workspaces on their backend skill id while using the path as the native writer root', async () => {
    const selection = `local-workspace:${encodeURIComponent('writer-smoke')}:${encodeURIComponent('/Users/sevenx/Projects/writer-smoke')}`
    renderWorkspace(selection)

    await mocks.panelsProps?.onPhaseFileSave?.({
      path: 'phases/draft/SKILL.md',
      content: 'updated phase\n',
      expectedHash: 'phase-hash',
    })

    await mocks.graphCanvasProps?.onPersistConnection?.({ source: 'draft', target: 'review' })

    expect(mocks.useSkillsIds).toContain('writer-smoke')
    expect(mocks.useSkillsIds).not.toContain('/Users/sevenx/Projects/writer-smoke')
    expect(mocks.graphCanvasProps?.skillId).toBe('writer-smoke')
    expect(mocks.serializeSkillGraph).toHaveBeenCalledWith(
      'writer-smoke',
      expect.any(Array),
      'graph-hash',
    )
    expect(mocks.invoke).toHaveBeenCalledWith('write_workspace_file', expect.objectContaining({
      workspaceRoot: '/Users/sevenx/Projects/writer-smoke',
      relativePath: 'phases/draft/SKILL.md',
      content: 'updated phase\n',
    }))
    expect((mocks.invoke.mock.calls[0][1] as Record<string, unknown>)).not.toHaveProperty('path')
  })

  it('passes imported workspace roots down to the panels for native test input writes', () => {
    const selection = `local-workspace:${encodeURIComponent('writer-smoke')}:${encodeURIComponent('/Users/sevenx/Projects/writer-smoke')}`

    renderWorkspace(selection)

    expect(mocks.panelsProps?.workspaceRoot).toBe('/Users/sevenx/Projects/writer-smoke')
  })

  it('passes imported workspace roots into golden diff promotion without changing the API skill id', () => {
    const selection = `local-workspace:${encodeURIComponent('writer-smoke')}:${encodeURIComponent('/abs/path')}`

    renderWorkspace(selection)

    expect(mocks.goldenDiffCalls).toContainEqual({
      skillId: 'writer-smoke',
      runId: null,
      workspaceRoot: '/abs/path',
    })
  })

  it('passes imported workspace roots into the copilot analysis bar path', () => {
    const selection = `local-workspace:${encodeURIComponent('writer-smoke')}:${encodeURIComponent('/abs/path')}`

    renderWorkspace(selection)

    expect(mocks.copilotProps.at(-1)).toMatchObject({
      skillId: 'writer-smoke',
      workspaceRoot: '/abs/path',
    })
  })

  it('wires golden diff refs into the Copilot Judge eval path', () => {
    mocks.goldenDiffResult = {
      baseline_ref: 'writer-smoke/golden/golden-run/baseline.json',
      run_results_ref: 'writer-smoke/runs/run-1/result.json',
    }

    renderWorkspace()

    expect(mocks.copilotProps.at(-1)).toMatchObject({
      skillId: 'writer-smoke',
      view: 'eval',
      judgeRefs: {
        runResultsRef: 'writer-smoke/runs/run-1/result.json',
        baselineRef: 'writer-smoke/golden/golden-run/baseline.json',
      },
    })
  })

  it('replays a Copilot Judge compare with the judged baseline instead of latest', () => {
    expect(compareReplayArgsForJudgeResult({
      compare_result_ref: 'writer-smoke/golden/baseline-old/compare/run-judged/compare_result.json',
      judge_context_ref: 'writer-smoke/runs/run-judged/copilot_judge/baseline-old/judge_context.json',
      baseline_ref: 'writer-smoke/golden/baseline-old/baseline.json',
      diff_summary: {
        baseline_id: 'baseline-old',
        run_results_ref: 'writer-smoke/runs/run-judged/result.json',
        total_score: 42,
        node_group_count: 3,
        failed_node_count: 2,
      },
    })).toEqual({
      against: 'baseline-old',
      runId: 'run-judged',
    })
  })

  it('does not replay stale judged refs after switching to a different skill', () => {
    expect(compareReplayArgsForJudgeResult({
      compare_result_ref: 'writer-smoke/golden/baseline-old/compare/run-judged/compare_result.json',
      judge_context_ref: 'writer-smoke/runs/run-judged/copilot_judge/baseline-old/judge_context.json',
      baseline_ref: 'writer-smoke/golden/baseline-old/baseline.json',
      diff_summary: {
        baseline_id: 'baseline-old',
        run_results_ref: 'writer-smoke/runs/run-judged/result.json',
        total_score: 42,
        node_group_count: 3,
        failed_node_count: 2,
      },
    }, {
      skillId: 'other-skill',
      runId: 'run-judged',
    })).toEqual({
      against: null,
      runId: null,
    })
  })

  it('does not replay stale judged refs after a newer run becomes active', () => {
    expect(compareReplayArgsForJudgeResult({
      compare_result_ref: 'writer-smoke/golden/baseline-old/compare/run-judged/compare_result.json',
      judge_context_ref: 'writer-smoke/runs/run-judged/copilot_judge/baseline-old/judge_context.json',
      baseline_ref: 'writer-smoke/golden/baseline-old/baseline.json',
      diff_summary: {
        baseline_id: 'baseline-old',
        run_results_ref: 'writer-smoke/runs/run-judged/result.json',
        total_score: 42,
        node_group_count: 3,
        failed_node_count: 2,
      },
    }, {
      skillId: 'writer-smoke',
      runId: 'run-newer',
    })).toEqual({
      against: null,
      runId: null,
    })
  })

  it('creates a logic phase through the native writer before serializing and persisting GRAPH.md', async () => {
    const selection = `local-workspace:${encodeURIComponent('writer-smoke')}:${encodeURIComponent('/Users/sevenx/Projects/writer-smoke')}`
    renderWorkspace(selection)

    expect(mocks.centerActionBarProps?.onCreatePhase).toBeTypeOf('function')
    await mocks.centerActionBarProps?.onCreatePhase?.('logic')

    expect(mocks.writeSkillFile).not.toHaveBeenCalled()
    expect(mocks.serializeSkillGraph).toHaveBeenCalledWith(
      'writer-smoke',
      expect.arrayContaining([
        expect.objectContaining({
          id: 'logic',
          src: 'phases/logic',
          depends_on: [],
          mode: 'logic',
        }),
      ]),
      'graph-hash',
    )
    expect(mocks.invoke).toHaveBeenCalledTimes(2)
    expect(mocks.invoke).toHaveBeenNthCalledWith(1, 'write_workspace_file', expect.objectContaining({
      workspaceRoot: '/Users/sevenx/Projects/writer-smoke',
      relativePath: 'phases/logic/LOGIC.md',
      expectedHash: null,
    }))
    expect(mocks.invoke).toHaveBeenNthCalledWith(2, 'write_workspace_file', expect.objectContaining({
      workspaceRoot: '/Users/sevenx/Projects/writer-smoke',
      relativePath: 'GRAPH.md',
      content: 'serialized graph\n',
      expectedHash: 'graph-hash',
    }))
    expect(mocks.compileSkill).toHaveBeenCalledWith('writer-smoke')
  })

  // n2-canvas #8 lost-update regression: an edge reconnect (drag the draft→review
  // target over to publish) must serialize + write GRAPH.md EXACTLY ONCE with the
  // combined phases — review loses the draft dependency AND publish gains it — and
  // a SINGLE expected_hash. The old disconnect-then-persist chain issued TWO
  // sequential serialize round-trips; the second held the pre-disconnect phases
  // with a now-stale expected_hash and the backend hash guard rejected it (409),
  // leaving the graph half-mutated. Asserting call count === 1 with the combined
  // depends_on is the contract that would have caught that.
  it('reconnects a dependency edge as a single atomic serialize/write with the combined phases', async () => {
    renderWorkspace(RECONNECT_FIXTURE_SKILL_ID)

    expect(mocks.graphCanvasProps?.onReconnectConnection).toBeTypeOf('function')
    await mocks.graphCanvasProps?.onReconnectConnection?.(
      { source: 'draft', target: 'review' },
      { source: 'draft', target: 'publish' },
    )

    // Exactly one serialize round-trip, carrying the combined phases: review's
    // draft dependency removed, publish's draft dependency added.
    expect(mocks.serializeSkillGraph).toHaveBeenCalledTimes(1)
    expect(mocks.serializeSkillGraph).toHaveBeenCalledWith(
      RECONNECT_FIXTURE_SKILL_ID,
      expect.arrayContaining([
        expect.objectContaining({ id: 'review', depends_on: [] }),
        expect.objectContaining({ id: 'publish', depends_on: ['draft'] }),
      ]),
      'graph-hash',
    )

    // Exactly one GRAPH.md write, with a single expected_hash — not two writes.
    const graphWrites = mocks.invoke.mock.calls.filter(
      ([command, payload]) =>
        command === 'write_workspace_file'
        && (payload as { relativePath?: string }).relativePath === 'GRAPH.md',
    )
    expect(graphWrites).toHaveLength(1)
    expect(graphWrites[0][1]).toMatchObject({
      relativePath: 'GRAPH.md',
      content: 'serialized graph\n',
      expectedHash: 'graph-hash',
    })
    expect(toastMocks.error).not.toHaveBeenCalled()
  })

  it('wires conflict overwrite retry into the shared conflict dialog', () => {
    renderWorkspace()

    expect(mocks.conflictDialogProps?.onOverwriteRetry).toBeTypeOf('function')
  })

  // N3 #12: a passing realtime lint must drive the build stage to 'compile-pass' (which
  // is what unlocks Predict in the CenterActionBar) without the user clicking Compile.
  // deriveBuildStage is the design atom — it reads readLintStatus and maps passed →
  // compile-pass; Workspace subscribes to lintStatusEvent so the bar re-renders when it
  // changes.
  it('drives the build stage to compile-pass from a passing realtime lint', () => {
    mocks.lintStatus = 'passed'

    renderWorkspace()

    expect(mocks.centerActionBarProps?.stage).toBe('compile-pass')
  })

  it('keeps the build stage idle while no lint has passed', () => {
    mocks.lintStatus = 'idle'

    renderWorkspace()

    expect(mocks.centerActionBarProps?.stage).toBe('idle')
  })

  // N4 #4: a 2xx predict response carries PredictDiagnosticExport.status. A 'failed'
  // status means the predicted path did not match — Run must stay locked. The handler
  // must take the predict-fail branch: a diagnostic error toast naming the mismatched
  // path, and NO "completed successfully" success toast (which is the predict-pass branch
  // that would unlock Run). The success toast is the observable marker that the stage was
  // advanced to predict-pass in this static-render harness.
  it('takes the predict-fail branch and never unlocks Run when status is failed', async () => {
    mocks.postPredictRun.mockResolvedValue({
      is_predict: true,
      status: 'failed',
      phases: [],
      path_diff: {
        expected_path: ['draft', 'review'],
        actual_path: ['draft'],
        missing: ['review'],
        extra: [],
        order_mismatch: false,
      },
    })

    renderWorkspace()
    await mocks.centerActionBarProps?.onPredict?.()

    expect(toastMocks.error).toHaveBeenCalledWith(expect.stringContaining('review'))
    expect(toastMocks.success).not.toHaveBeenCalledWith(
      expect.stringContaining('Predict run completed'),
    )
  })

  it('takes the predict-pass branch only when status is success', async () => {
    mocks.postPredictRun.mockResolvedValue({
      is_predict: true,
      status: 'success',
      phases: [],
      path_diff: null,
    })

    renderWorkspace()
    await mocks.centerActionBarProps?.onPredict?.()

    expect(toastMocks.success).toHaveBeenCalledWith(
      expect.stringContaining('Predict run completed'),
    )
    expect(toastMocks.error).not.toHaveBeenCalled()
  })
})

function renderWorkspace(skillId = 'writer-smoke') {
  renderToStaticMarkup(
    <Workspace
      skillId={skillId}
      onSelectSkill={vi.fn()}
      onCloseSkill={vi.fn()}
    />,
  )
}

// Reconnect-fixture skill id: a three-phase graph where review already depends
// on draft and publish exists with no deps, so an edge reconnect (drag the
// draft→review target over to publish) has a real old dependency to remove and a
// real new one to add. Keyed by skill id so the shared writer-smoke fixture (and
// every test that asserts review.depends_on starts empty) is untouched.
const RECONNECT_FIXTURE_SKILL_ID = 'reconnect-fixture'

function skillDetail(skillId = 'writer-smoke'): SkillDetail {
  if (skillId === RECONNECT_FIXTURE_SKILL_ID) {
    return {
      manifest: {
        schema_version: CURRENT_SCHEMA_VERSION,
        name: skillId,
        description: 'Reconnect fixture',
        io: {
          inputs: { type: 'object', properties: {} },
          outputs: { type: 'object', properties: {} },
        },
        phases: ['draft', 'review', 'publish'],
      },
      graph_topology: [
        { id: 'draft', src: 'phases/draft/SKILL.md', depends_on: [], mode: 'skill' },
        { id: 'review', src: 'phases/review/LOGIC.md', depends_on: ['draft'], mode: 'logic' },
        { id: 'publish', src: 'phases/publish/SKILL.md', depends_on: [], mode: 'skill' },
      ],
      node_schema_v21: {},
      io_schema: {},
      file_paths: {},
      files: {
        'GRAPH.md': 'graph before\n',
        'phases/draft/SKILL.md': 'draft before\n',
        'phases/review/LOGIC.md': 'review before\n',
        'phases/publish/SKILL.md': 'publish before\n',
      },
      manifest_errors: null,
      has_golden: false,
      latest_run_metadata: null,
      lint_result: null,
    }
  }
  return {
    manifest: {
      schema_version: CURRENT_SCHEMA_VERSION,
      name: skillId,
      description: 'Writer smoke',
      io: {
        inputs: { type: 'object', properties: {} },
        outputs: { type: 'object', properties: {} },
      },
      phases: ['draft', 'review'],
    },
    graph_topology: [
      { id: 'draft', src: 'phases/draft/SKILL.md', depends_on: [], mode: 'skill' },
      { id: 'review', src: 'phases/review/LOGIC.md', depends_on: [], mode: 'logic' },
    ],
    node_schema_v21: {},
    io_schema: {},
    file_paths: {},
    files: {
      'GRAPH.md': 'graph before\n',
      'phases/draft/SKILL.md': 'draft before\n',
      'phases/review/LOGIC.md': 'review before\n',
    },
    manifest_errors: null,
    has_golden: false,
    latest_run_metadata: null,
    lint_result: null,
  }
}
