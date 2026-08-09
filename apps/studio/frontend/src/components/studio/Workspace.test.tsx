// @vitest-environment jsdom
import { renderToStaticMarkup } from 'react-dom/server'
import { act, createElement, useEffect, type ReactNode } from 'react'
import { createRoot } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { AxiosError, AxiosHeaders, type InternalAxiosRequestConfig } from 'axios'
import { compareReplayArgsForJudgeResult, hasMiniMapToolSpace, Workspace } from './Workspace'
import { CURRENT_SCHEMA_VERSION } from '@/config/schema'
import type { EventEnvelope, LintError, RunDetail, SerializableGraphPhaseRef, SkillDetail } from '@/api/types'
import { BackendUnavailableError } from '@/utils/errors'
import { INPUT_ID } from '@/components/nodes'

// React 19's act() warns unless the environment opts in.
;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true

const mocks = vi.hoisted(() => ({
  panelsProps: null as null | {
    onPhaseFileSave?: (payload: { path: string; content: string; expectedHash: string }) => Promise<void> | void
    workspaceRoot?: string | null
    onOpenSettings?: (tab?: 'general' | 'api_keys' | 'llm_roles' | 'copilot') => void
    lintErrors?: LintError[] | null
    traceSelectedEventId?: string | null
    onSelectTraceEvent?: (index: number, event: unknown) => void
  },
  graphCanvasProps: null as null | {
    skillId?: string | null
    onCreatePhase?: (kind: 'skill' | 'logic' | 'subgraph', phaseId?: string) => Promise<void> | void
    onDeletePhase?: (phaseId: string) => Promise<void> | void
    onNodeFileOpen?: (fileOrPath: unknown) => void
    hideMiniMap?: boolean
    onPersistConnection?: (connection: { source: string; target: string }) => Promise<void> | void
    onReconnectConnection?: (
      disconnect: { source: string; target: string },
      connect: { source: string; target: string },
    ) => Promise<void> | void
    compileErrorsByNodeId?: Record<string, unknown[]>
    sequentialOverwriteErrorsByNodeId?: Record<string, unknown[]>
  },
  centerActionBarProps: null as null | {
    stage?: string
    onCompile?: () => Promise<void> | void
    onPredict?: () => Promise<void> | void
    onRun?: () => Promise<void> | void
  },
  conflictDialogProps: null as null | {
    conflict?: {
      path: string
      localContent: string
      remoteContent: string
    } | null
    onOverwriteRetry?: () => void
  },
  lazyMonacoProps: [] as Array<{
    value: string
    onChange: (value: string) => void
    onInFlightChange: (inFlight: boolean) => void
  }>,
  webSockets: [] as Array<{
    onmessage: ((event: { data: string }) => void) | null
    close: () => void
  }>,
  copilotProps: [] as Array<{
    skillId: string | null
    workspaceRoot?: string | null
    view?: 'edit' | 'eval'
    judgeRefs?: {
      runResultsRef: string
      baselineRef: string
    } | null
    onJudgePrepared?: (refs: unknown) => void
    onCollapse?: () => void
    copilot?: unknown
  }>,
  useCopilotCalls: [] as Array<{
    skillId: string | null
    workspaceRoot?: string | null
  }>,
  copilotController: {
    messages: [],
    connectionStatus: 'open',
    reconnectInMs: null,
    lastError: null,
    sendMessage: vi.fn(),
    isStreaming: false,
    interrupt: vi.fn(),
    clearMessages: vi.fn(),
    persistenceError: null,
    activeSessionId: null,
    sessions: [],
    newSession: vi.fn(),
    restoreSession: vi.fn(),
    switchSession: vi.fn(),
    closeSession: vi.fn(),
  },
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
  getSkillDetail: vi.fn(),
  fetcher: vi.fn(async () => []),
  getCompareGroup: vi.fn(),
  getRunDetail: vi.fn(),
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
  relintSkillFromDisk: vi.fn(),
  // T-n6hist test#1/#2: the run trace stream + history hooks are driven through
  // mocks so we can flip a run to run_ended and assert the resulting effect wiring.
  runStreamEvents: [] as EventEnvelope[],
  projectRunHistory: vi.fn(),
  refreshLocalHistory: vi.fn(),
  settingsPageProps: null as null | {
    initialTab?: 'general' | 'api_keys' | 'llm_roles' | 'copilot'
    onClose?: () => void
    controller?: unknown
  },
  settingsPageMounts: 0,
  settingsPageUnmounts: 0,
  settingsControllerHookCalls: 0,
  settingsController: { source: 'app-level-settings-controller' } as const,
  studioEventStreamSubscribers: [] as Array<{
    current: {
      onSkillChanged?: (event: { skillId: string; path: string }) => void
      onRuntimeConfigChanged?: (event: { skillId: string; dataset: string; nodeId?: string }) => void
      onSkillGate?: (event: {
        skillId: string
        gate: 'compile' | 'predict' | 'run'
        outcome: 'started' | 'pass' | 'fail' | 'paused' | 'stopped'
        runId?: string | null
        defectCount?: number
      }) => void
    }
  }>,
}))

const toastMocks = vi.hoisted(() => ({
  error: vi.fn(),
  success: vi.fn(),
  warning: vi.fn(),
}))

vi.mock('@tauri-apps/api/core', () => ({
  invoke: mocks.invoke,
}))

vi.mock('@/api/client', () => ({
  compileSkill: mocks.compileSkill,
  fetcher: mocks.fetcher,
  getCompareGroup: mocks.getCompareGroup,
  getRunDetail: mocks.getRunDetail,
  getResumeValidity: mocks.getResumeValidity,
  getSkillDetail: mocks.getSkillDetail,
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

vi.mock('@/hooks/useCopilot', () => ({
  useCopilot: (skillId: string | null, workspaceRoot?: string | null) => {
    mocks.useCopilotCalls.push({ skillId, workspaceRoot })
    return mocks.copilotController
  },
}))

vi.mock('@/hooks/useStudioEventStream', async () => {
  const React = await import('react')
  return {
    useStudioEventStream: (
      callbacks: {
        onSkillChanged?: (event: { skillId: string; path: string }) => void
        onRuntimeConfigChanged?: (event: { skillId: string; dataset: string; nodeId?: string }) => void
        onSkillGate?: (event: {
          skillId: string
          gate: 'compile' | 'predict' | 'run'
          outcome: 'started' | 'pass' | 'fail' | 'paused' | 'stopped'
          runId?: string | null
          defectCount?: number
        }) => void
      },
      options: { enabled?: boolean } = {},
    ) => {
      const callbacksRef = React.useRef(callbacks)
      callbacksRef.current = callbacks
      const enabled = options.enabled ?? true
      React.useEffect(() => {
        if (!enabled) return undefined
        mocks.studioEventStreamSubscribers.push(callbacksRef)
        return () => {
          mocks.studioEventStreamSubscribers = mocks.studioEventStreamSubscribers.filter((item) => item !== callbacksRef)
        }
      }, [callbacksRef, enabled])
      return { connectionLost: false }
    },
  }
})

vi.mock('@/hooks/useDebouncedLint', () => ({
  lintStatusEvent: 'studio-lint-status-changed',
  lintResultEvent: 'studio-lint-result-changed',
  readLintStatus: () => mocks.lintStatus,
  relintSkillFromDisk: (skillId: string, workspaceRoot?: string | null) =>
    mocks.relintSkillFromDisk(skillId, workspaceRoot),
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

// useRunStream is mocked so the run trace is fully controllable (no real WebSocket
// under jsdom) and a run can be flipped to run_ended on demand.
vi.mock('@/hooks/useRunStream', () => ({
  useRunStream: () => ({
    events: mocks.runStreamEvents,
    status: 'open',
    reconnectInMs: null,
    error: null,
    cursor: null,
  }),
}))

// Keep the real pure projections (archiveFeedbackForGitStatus / nextLocalHistoryRefreshKey)
// so the run_ended → toast wording is exercised end-to-end; only the SWR-backed hooks
// (useRunHistory / useLocalHistory) are stubbed with controllable spies.
vi.mock('@/hooks/useRunHistory', async (importActual) => {
  const actual = await importActual<typeof import('@/hooks/useRunHistory')>()
  return {
    ...actual,
    useRunHistory: () => {
      throw new Error('Workspace must not subscribe to the run-history list')
    },
    useRunHistoryProjection: () => ({
      projectRun: mocks.projectRunHistory,
    }),
    useLocalHistory: () => {
      throw new Error('Workspace must not subscribe to the local-history list')
    },
    useLocalHistoryRevalidator: () => ({
      refresh: mocks.refreshLocalHistory,
    }),
  }
})

vi.mock('@/lib/hash', () => ({
  sha256Hex: vi.fn(async () => 'graph-hash'),
}))

vi.mock('@/components/GraphCanvas', () => ({
  GraphCanvas: (props: {
    skillId?: string | null
    onCreatePhase?: (kind: 'skill' | 'logic' | 'subgraph', phaseId?: string) => Promise<void> | void
    onDeletePhase?: (phaseId: string) => Promise<void> | void
    onNodeFileOpen?: (fileOrPath: unknown) => void
    hideMiniMap?: boolean
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
    onCollapse?: () => void
    copilot?: unknown
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
  ResizablePanel: ({
    children,
    className,
    defaultSize,
    id,
    maxSize,
    minSize,
  }: {
    children: ReactNode
    className?: string
    defaultSize?: string
    id?: string
    maxSize?: string
    minSize?: string
  }) => (
    <div
      data-testid="resize-panel"
      data-panel-id={id}
      data-default-size={defaultSize}
      data-max-size={maxSize}
      data-min-size={minSize}
      className={className}
    >
      {children}
    </div>
  ),
  ResizablePanelGroup: ({ children }: { children: ReactNode }) => <div data-testid="resize-group">{children}</div>,
}))

vi.mock('./Header', () => ({
  Header: () => <header data-testid="header" />,
}))

vi.mock('./Panels', () => ({
  Panels: (props: {
    onPhaseFileSave?: (payload: { path: string; content: string; expectedHash: string }) => Promise<void> | void
    workspaceRoot?: string | null
    lintErrors?: LintError[] | null
  }) => {
    mocks.panelsProps = props
    return <aside data-testid="panels" />
  },
}))

vi.mock('./SettingsPage', () => ({
  useSettingsPageController: () => {
    mocks.settingsControllerHookCalls += 1
    return mocks.settingsController
  },
  SettingsPageView: (props: {
    initialTab?: 'general' | 'api_keys' | 'llm_roles' | 'copilot'
    onClose?: () => void
    controller?: unknown
  }) => {
    useEffect(() => {
      mocks.settingsPageMounts += 1
      return () => {
        mocks.settingsPageUnmounts += 1
      }
    }, [])
    mocks.settingsPageProps = props
    return <div data-testid="settings" data-initial-tab={props.initialTab} />
  },
}))

vi.mock('./LazyMonacoPanel', () => ({
  LazyMonacoPanel: (props: {
    value: string
    onChange: (value: string) => void
    onInFlightChange: (inFlight: boolean) => void
  }) => {
    mocks.lazyMonacoProps.push(props)
    return (
      <div data-testid="lazy-monaco-panel">
        {props.value}
      </div>
    )
  }
}))

vi.mock('./Toolbar', () => ({
  Toolbar: (props: {
    settingsOpen: boolean
    onSettingsToggle: () => void
  }) => (
    <button
      type="button"
      data-testid="settings-toggle"
      aria-pressed={props.settingsOpen}
      onClick={props.onSettingsToggle}
    >
      Settings
    </button>
  ),
}))

vi.mock('./ConflictDialog', () => ({
  ConflictDialog: (props: {
    conflict?: {
      path: string
      localContent: string
      remoteContent: string
    } | null
    onOverwriteRetry?: () => void
  }) => {
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
    // Mark the runtime as Tauri without clobbering the jsdom window (createRoot
    // needs the real DOM). isTauriRuntime only checks for this key on window.
    ;(window as unknown as { __TAURI_INTERNALS__?: unknown }).__TAURI_INTERNALS__ = {}
    // jsdom has no WebSocket; the file-change watcher effect opens one. Stub it so
    // effects can run without a real socket.
    vi.stubGlobal(
      'WebSocket',
      class {
        onmessage: ((event: { data: string }) => void) | null = null
        constructor() {
          mocks.webSockets.push(this)
        }
        close() {}
      },
    )
    mocks.webSockets = []
    mocks.studioEventStreamSubscribers = []
    mocks.runStreamEvents = []
    mocks.getRunDetail.mockReset()
    mocks.projectRunHistory.mockReset()
    mocks.projectRunHistory.mockResolvedValue(undefined)
    mocks.refreshLocalHistory.mockReset()
    toastMocks.warning.mockReset()
    mocks.panelsProps = null
    mocks.settingsPageProps = null
    mocks.settingsPageMounts = 0
    mocks.settingsPageUnmounts = 0
    mocks.settingsControllerHookCalls = 0
    mocks.graphCanvasProps = null
    mocks.centerActionBarProps = null
    mocks.conflictDialogProps = null
    mocks.lazyMonacoProps.length = 0
    mocks.copilotProps.length = 0
    mocks.useCopilotCalls.length = 0
    mocks.useSkillsIds.length = 0
    mocks.goldenDiffCalls.length = 0
    mocks.goldenDiffResult = null
    mocks.goldenDiffCompare.mockReset()
    mocks.goldenDiffCompare.mockResolvedValue(null)
    mocks.writeSkillFile.mockReset()
    mocks.writeSkillFile.mockResolvedValue({ path: 'GRAPH.md', hash: 'python-hash' })
    mocks.getSkillDetail.mockReset()
    mocks.getSkillDetail.mockImplementation(async (id: string) => skillDetail(id))
    mocks.fetcher.mockReset()
    mocks.fetcher.mockResolvedValue([])
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
      detail: skillDetail('writer-smoke'),
    })
    mocks.getCompareGroup.mockReset()
    mocks.getCompareGroup.mockResolvedValue({ compare_group_id: 'group-1', runs: [] })
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
    mocks.invoke.mockImplementation(async (command: string, payload: { relativePath?: string; path?: string }) => {
      if (command === 'read_workspace_file') {
        return { path: payload.relativePath ?? payload.path ?? 'GRAPH.md', content: 'serialized graph\n', hash: 'native-hash' }
      }
      if (command === 'list_workspace_dir') {
        return []
      }
      return { path: payload.relativePath ?? payload.path ?? 'GRAPH.md', hash: 'native-hash' }
    })
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
    const connectGraphWrite = mocks.invoke.mock.calls.find(
      ([command, payload]) =>
        command === 'write_workspace_file'
        && (payload as { relativePath?: string }).relativePath === 'GRAPH.md',
    )
    expect(connectGraphWrite?.[1] as Record<string, unknown>).not.toHaveProperty('path')
  })

  it('does not auto-compile after a canvas connection writes GRAPH.md successfully', async () => {
    renderWorkspace()

    await mocks.graphCanvasProps?.onPersistConnection?.({ source: 'draft', target: 'review' })

    expect(mocks.invoke).toHaveBeenCalledWith('write_workspace_file', expect.objectContaining({
      relativePath: 'GRAPH.md',
      content: 'serialized graph\n',
    }))
    expect(mocks.compileSkill).not.toHaveBeenCalled()
    // 03_compile A13: the settled canvas write triggers an immediate on-disk
    // RELINT (replacing the projection) — manual Compile stays a user action.
    expect(mocks.relintSkillFromDisk).toHaveBeenCalledWith('writer-smoke', null)
  })

  it('shows compile success with artifact hash and execution fingerprint', async () => {
    renderWorkspace()

    await mocks.centerActionBarProps?.onCompile?.()

    expect(mocks.compileSkill).toHaveBeenCalledWith('writer-smoke')
    expect(toastMocks.success).toHaveBeenCalledWith(expect.stringContaining('writer-smoke'))
    expect(toastMocks.success).toHaveBeenCalledWith(expect.stringContaining('sha256:11111111'))
    expect(toastMocks.success).toHaveBeenCalledWith(expect.stringContaining('fp sha256:22222222'))
  })

  it('projects compile success detail without broad skill-detail refetch', async () => {
    const compiledDetail = {
      ...skillDetail('writer-smoke'),
      lint_result: {
        status: 'passed' as const,
        errors: [],
        phases_summary: [{ name: 'setup', tier: 'logic', has_validator: false }],
      },
    }
    mocks.compileSkill.mockResolvedValueOnce({
      skill_id: 'writer-smoke',
      status: 'ok',
      phase_count: 2,
      manifest_name: 'writer-smoke',
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
      detail: compiledDetail,
    })

    renderWorkspace()

    await mocks.centerActionBarProps?.onCompile?.()

    expect(mocks.mutateSkillDetail.mock.calls).toEqual([
      [compiledDetail, { revalidate: false }],
    ])
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

  it('keeps first-screen sequential overwrite lint out of the popover-only compile channel', () => {
    renderWorkspace(LINT_SEQUENTIAL_OVERWRITE_FIXTURE_SKILL_ID)

    expect(mocks.graphCanvasProps?.compileErrorsByNodeId?.review).toHaveLength(1)
    expect(mocks.graphCanvasProps?.sequentialOverwriteErrorsByNodeId).toEqual({})
  })

  it('projects first-screen Studio preflight lint onto the Input boundary without pressing Compile', () => {
    renderWorkspace(INPUT_PREFLIGHT_FIXTURE_SKILL_ID)

    expect(mocks.graphCanvasProps?.compileErrorsByNodeId?.[INPUT_ID]).toHaveLength(1)
    expect(mocks.graphCanvasProps?.compileErrorsByNodeId?.[INPUT_ID]?.[0]).toMatchObject({
      file: '.workspace/runtime_config.json',
      field: 'chapter',
      message: expect.stringContaining("runtime input field 'chapter'"),
    })
  })

  it('renders the left workspace panel as an overlay drawer so the canvas is not resized', () => {
    const html = renderToStaticMarkup(
      <Workspace
        skillId="writer-smoke"
        onSelectSkill={vi.fn()}
        onCloseSkill={vi.fn()}
      />,
    )

    expect(html).toContain('data-studio-left-overlay="true"')
    expect(html).toContain('data-studio-canvas-overlay-host="true"')
    expect(html).toContain('studio-left-panel-overlay')
    expect(html).toContain('data-studio-left-panel-content="true"')
    expect(html).toContain('bottom-3 left-3 top-3')
    expect(html).toContain('flex h-full min-h-0 flex-1')
    expect(html).toContain('--studio-canvas-left-safe-area:calc(384px + 1.5rem)')
    expect(html).toContain('--studio-canvas-right-safe-area:calc(352px + 1.5rem)')
    expect(html).toContain('rounded-lg')
    expect(html).toContain('top-3')
    expect(html).not.toContain('h-fit')
    expect(html).toContain('Close panel')
    expect(html).toContain('data-testid="panels"')
    expect(html).toContain('data-panel-id="canvas"')
    expect(html).not.toContain('data-panel-id="left-panel"')
  })

  it('opens files in a canvas overlay editor, keeps GraphCanvas full-size, and hides the minimap', async () => {
    const container = document.createElement('div')
    document.body.appendChild(container)
    const root = createRoot(container)
    try {
      await act(async () => {
        root.render(
          <Workspace
            skillId="writer-smoke"
            onSelectSkill={vi.fn()}
            onCloseSkill={vi.fn()}
          />,
        )
      })

      await act(async () => {
        mocks.graphCanvasProps?.onNodeFileOpen?.({
          path: 'phases/review/SKILL.md',
          content: 'review body\n',
          skillId: 'writer-smoke',
          workspaceRoot: '/Users/sevenx/Projects/writer-smoke',
          language: 'markdown',
          hash: 'hash-1',
        })
        await Promise.resolve()
        await Promise.resolve()
      })

      expect(container.innerHTML).toContain('data-studio-editor-overlay="true"')
      expect(container.innerHTML).toContain('data-testid="lazy-monaco-panel"')
      expect(container.innerHTML).not.toContain('editor-canvas-divider')
      expect(container.innerHTML).toContain('--studio-canvas-editor-safe-area: calc(var(--studio-editor-overlay-height) + 1.5rem)')
      expect(mocks.graphCanvasProps?.hideMiniMap).toBe(true)
      expect(mocks.graphCanvasProps).not.toHaveProperty('viewportInsets')
    } finally {
      act(() => {
        root.unmount()
      })
      container.remove()
    }
  })

  it('shows the minimap only when the fixed action bar leaves enough room before Copilot', () => {
    const actionBar = { right: 900 } as DOMRect

    expect(hasMiniMapToolSpace(actionBar, { left: 1220 } as DOMRect)).toBe(true)
    expect(hasMiniMapToolSpace(actionBar, { left: 1199 } as DOMRect)).toBe(false)
    expect(hasMiniMapToolSpace(actionBar, null)).toBe(true)
  })

  it('hides the minimap until Copilot spacing has been measured', () => {
    renderWorkspace()

    expect(mocks.graphCanvasProps?.hideMiniMap).toBe(true)
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
      copilot: mocks.copilotController,
    })
    expect(mocks.useCopilotCalls.at(-1)).toEqual({
      skillId: 'writer-smoke',
      workspaceRoot: '/abs/path',
    })
  })

  it('keeps the Copilot controller mounted with the skill even after the panel collapses', () => {
    const container = document.createElement('div')
    document.body.appendChild(container)
    const root = createRoot(container)
    try {
      act(() => {
        root.render(
          createElement(Workspace, {
            skillId: 'writer-smoke',
            onSelectSkill: vi.fn(),
            onCloseSkill: vi.fn(),
          }),
        )
      })
      expect(mocks.useCopilotCalls.at(-1)).toEqual({
        skillId: 'writer-smoke',
        workspaceRoot: null,
      })
      const callsBeforeCollapse = mocks.useCopilotCalls.length

      act(() => {
        mocks.copilotProps.at(-1)?.onCollapse?.()
      })

      expect(mocks.useCopilotCalls.length).toBeGreaterThan(callsBeforeCollapse)
      expect(mocks.useCopilotCalls.at(-1)).toEqual({
        skillId: 'writer-smoke',
        workspaceRoot: null,
      })
    } finally {
      act(() => {
        root.unmount()
      })
      container.remove()
    }
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

    expect(mocks.graphCanvasProps?.onCreatePhase).toBeTypeOf('function')
    await mocks.graphCanvasProps?.onCreatePhase?.('logic')

    expect(mocks.writeSkillFile).not.toHaveBeenCalled()
    // The expected hash comes from the on-disk GRAPH.md (single source of truth),
    // so the canvas reads it through native fs before writing.
    expect(mocks.invoke).toHaveBeenCalledWith('read_workspace_file', expect.objectContaining({ path: 'GRAPH.md' }))
    expect(mocks.invoke).toHaveBeenCalledWith('write_workspace_file', expect.objectContaining({
      workspaceRoot: '/Users/sevenx/Projects/writer-smoke',
      relativePath: 'phases/logic/LOGIC.md',
      expectedHash: null,
      createIfAbsent: true,
    }))
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
    expect(mocks.invoke).toHaveBeenCalledWith('write_workspace_file', expect.objectContaining({
      workspaceRoot: '/Users/sevenx/Projects/writer-smoke',
      relativePath: 'GRAPH.md',
      content: 'serialized graph\n',
      expectedHash: 'graph-hash',
    }))
    // The phase file is created before the sidecar serialize, which runs before
    // GRAPH.md is persisted.
    const logicPhaseWriteIndex = mocks.invoke.mock.calls.findIndex(
      ([command, payload]) =>
        command === 'write_workspace_file'
        && (payload as { relativePath?: string }).relativePath === 'phases/logic/LOGIC.md',
    )
    const logicGraphWriteIndex = mocks.invoke.mock.calls.findIndex(
      ([command, payload]) =>
        command === 'write_workspace_file'
        && (payload as { relativePath?: string }).relativePath === 'GRAPH.md',
    )
    expect(logicPhaseWriteIndex).toBeGreaterThanOrEqual(0)
    expect(logicGraphWriteIndex).toBeGreaterThanOrEqual(0)
    expect(mocks.invoke.mock.invocationCallOrder[logicPhaseWriteIndex]).toBeLessThan(
      mocks.serializeSkillGraph.mock.invocationCallOrder[0],
    )
    expect(mocks.serializeSkillGraph.mock.invocationCallOrder[0]).toBeLessThan(
      mocks.invoke.mock.invocationCallOrder[logicGraphWriteIndex],
    )
    expect(mocks.compileSkill).not.toHaveBeenCalled()
  })

  it('opens child subgraph phase files by reading the child workspace root from native fs', async () => {
    renderWorkspace()

    mocks.graphCanvasProps?.onNodeFileOpen?.({
      path: 'phases/review/SKILL.md',
      skillId: 'event-extraction',
      workspaceRoot: '/Users/sevenx/Projects/story-deconstruction-v3/subgraph/event-timeline/subgraph/event-extraction',
      language: 'markdown',
      saveEnabled: true,
    })
    await act(async () => {
      await Promise.resolve()
      await Promise.resolve()
    })

    expect(mocks.invoke).toHaveBeenCalledWith('read_workspace_file', expect.objectContaining({
      workspaceRoot: '/Users/sevenx/Projects/story-deconstruction-v3/subgraph/event-timeline/subgraph/event-extraction',
      path: 'phases/review/SKILL.md',
    }))
  })

  it('uses the shared studio event stream instead of opening a workspace-local events socket', async () => {
    const container = document.createElement('div')
    document.body.appendChild(container)
    const root = createRoot(container)
    try {
      await act(async () => {
        root.render(
          createElement(Workspace, {
            skillId: 'writer-smoke',
            onSelectSkill: vi.fn(),
            onCloseSkill: vi.fn(),
          }),
        )
        await Promise.resolve()
      })

      expect(mocks.studioEventStreamSubscribers).toHaveLength(1)
      expect(mocks.webSockets).toHaveLength(0)

      act(() => {
        mocks.graphCanvasProps?.onNodeFileOpen?.('GRAPH.md')
      })
      await act(async () => {
        await Promise.resolve()
        await Promise.resolve()
      })
      act(() => {
        mocks.lazyMonacoProps.at(-1)?.onChange('local dirty graph\n')
      })
      await act(async () => {
        await Promise.resolve()
      })

      expect(mocks.studioEventStreamSubscribers).toHaveLength(1)
      expect(mocks.webSockets).toHaveLength(0)
    } finally {
      act(() => {
        root.unmount()
      })
      container.remove()
    }
  })

  it('keeps a dirty open editor buffer when a same-file skill_changed event arrives', async () => {
    const container = document.createElement('div')
    document.body.appendChild(container)
    const root = createRoot(container)
    try {
      await act(async () => {
        root.render(
          createElement(Workspace, {
            skillId: 'writer-smoke',
            onSelectSkill: vi.fn(),
            onCloseSkill: vi.fn(),
          }),
        )
        await Promise.resolve()
      })

      act(() => {
        mocks.graphCanvasProps?.onNodeFileOpen?.('GRAPH.md')
      })
      await act(async () => {
        await Promise.resolve()
        await Promise.resolve()
      })

      expect(mocks.lazyMonacoProps.at(-1)?.value).toBe('graph before\n')

      act(() => {
        mocks.lazyMonacoProps.at(-1)?.onChange('local dirty graph\n')
      })
      await act(async () => {
        await Promise.resolve()
      })

      mocks.getSkillDetail.mockResolvedValueOnce({
        ...skillDetail('writer-smoke'),
        files: {
          ...skillDetail('writer-smoke').files,
          'GRAPH.md': 'remote graph\n',
        },
      })

      await act(async () => {
        mocks.studioEventStreamSubscribers.at(-1)?.current.onSkillChanged?.({
          skillId: 'writer-smoke',
          path: 'GRAPH.md',
        })
        await Promise.resolve()
        await Promise.resolve()
        await Promise.resolve()
      })

      expect(mocks.lazyMonacoProps.at(-1)?.value).toBe('local dirty graph\n')
      expect(mocks.conflictDialogProps?.conflict).toMatchObject({
        path: 'GRAPH.md',
        localContent: 'local dirty graph\n',
        remoteContent: 'remote graph\n',
      })
    } finally {
      act(() => {
        root.unmount()
      })
      container.remove()
    }
  })

  it('refreshes skill detail when GRAPH.md changes even if GRAPH.md is not open in the editor', async () => {
    const container = document.createElement('div')
    document.body.appendChild(container)
    const root = createRoot(container)
    try {
      await act(async () => {
        root.render(
          createElement(Workspace, {
            skillId: 'writer-smoke',
            onSelectSkill: vi.fn(),
            onCloseSkill: vi.fn(),
          }),
        )
        await Promise.resolve()
      })

      mocks.getSkillDetail.mockClear()
      mocks.mutateSkillDetail.mockClear()
      const updatedDetail = {
        ...skillDetail('writer-smoke'),
        files: {
          ...skillDetail('writer-smoke').files,
          'GRAPH.md': 'graph with new io frontmatter\n',
        },
      }
      mocks.getSkillDetail.mockResolvedValueOnce(updatedDetail)

      await act(async () => {
        mocks.studioEventStreamSubscribers.at(-1)?.current.onSkillChanged?.({
          skillId: 'writer-smoke',
          path: 'GRAPH.md',
        })
        await Promise.resolve()
        await Promise.resolve()
      })

      expect(mocks.getSkillDetail).toHaveBeenCalledWith('writer-smoke')
      expect(mocks.mutateSkillDetail).toHaveBeenCalledWith(updatedDetail, { revalidate: false })
    } finally {
      act(() => {
        root.unmount()
      })
      container.remove()
    }
  })

  it('refreshes skill detail when a child io document changes outside the editor', async () => {
    const container = document.createElement('div')
    document.body.appendChild(container)
    const root = createRoot(container)
    try {
      await act(async () => {
        root.render(
          createElement(Workspace, {
            skillId: 'writer-smoke',
            onSelectSkill: vi.fn(),
            onCloseSkill: vi.fn(),
          }),
        )
        await Promise.resolve()
      })

      mocks.getSkillDetail.mockClear()
      mocks.mutateSkillDetail.mockClear()
      const updatedDetail = {
        ...skillDetail('writer-smoke'),
        files: {
          ...skillDetail('writer-smoke').files,
          'phases/child/SUBGRAPH.md': 'child io document\n',
        },
      }
      mocks.getSkillDetail.mockResolvedValueOnce(updatedDetail)

      await act(async () => {
        mocks.studioEventStreamSubscribers.at(-1)?.current.onSkillChanged?.({
          skillId: 'writer-smoke',
          path: 'phases/child/SUBGRAPH.md',
        })
        await Promise.resolve()
        await Promise.resolve()
      })

      expect(mocks.getSkillDetail).toHaveBeenCalledWith('writer-smoke')
      expect(mocks.mutateSkillDetail).toHaveBeenCalledWith(updatedDetail, { revalidate: false })
    } finally {
      act(() => {
        root.unmount()
      })
      container.remove()
    }
  })

  it('refreshes a clean open GRAPH.md editor buffer when a same-file skill_changed event arrives', async () => {
    const container = document.createElement('div')
    document.body.appendChild(container)
    const root = createRoot(container)
    try {
      await act(async () => {
        root.render(
          createElement(Workspace, {
            skillId: 'writer-smoke',
            onSelectSkill: vi.fn(),
            onCloseSkill: vi.fn(),
          }),
        )
        await Promise.resolve()
      })

      act(() => {
        mocks.graphCanvasProps?.onNodeFileOpen?.('GRAPH.md')
      })
      await act(async () => {
        await Promise.resolve()
        await Promise.resolve()
      })

      expect(mocks.lazyMonacoProps.at(-1)?.value).toBe('graph before\n')

      const updatedDetail = {
        ...skillDetail('writer-smoke'),
        files: {
          ...skillDetail('writer-smoke').files,
          'GRAPH.md': 'remote graph\n',
        },
      }
      mocks.getSkillDetail.mockResolvedValueOnce(updatedDetail)

      await act(async () => {
        mocks.studioEventStreamSubscribers.at(-1)?.current.onSkillChanged?.({
          skillId: 'writer-smoke',
          path: 'GRAPH.md',
        })
        await Promise.resolve()
        await Promise.resolve()
        await Promise.resolve()
      })

      expect(mocks.lazyMonacoProps.at(-1)?.value).toBe('remote graph\n')
      expect(mocks.conflictDialogProps?.conflict).toBeNull()
      expect(mocks.mutateSkillDetail).toHaveBeenCalledWith(updatedDetail, { revalidate: false })
    } finally {
      act(() => {
        root.unmount()
      })
      container.remove()
    }
  })

  it('handles runtime_config_changed as a scoped runtime-config revalidation', async () => {
    const container = document.createElement('div')
    document.body.appendChild(container)
    const root = createRoot(container)
    try {
      await act(async () => {
        root.render(
          <Workspace
            skillId="writer-smoke"
            onSelectSkill={vi.fn()}
            onCloseSkill={vi.fn()}
          />,
        )
        await Promise.resolve()
        await Promise.resolve()
      })
      mocks.fetcher.mockClear()
      mocks.getSkillDetail.mockClear()

      await act(async () => {
        mocks.studioEventStreamSubscribers.at(-1)?.current.onRuntimeConfigChanged?.({
          skillId: 'writer-smoke',
          dataset: 'node_llm_params',
          nodeId: 'setup',
        })
        await Promise.resolve()
        await Promise.resolve()
        await Promise.resolve()
      })

      expect(mocks.fetcher).toHaveBeenCalledWith('/skills/writer-smoke/runtime-config')
      expect(mocks.getSkillDetail).not.toHaveBeenCalled()
    } finally {
      act(() => {
        root.unmount()
      })
      container.remove()
    }
  })

  it('creates a phase with the submitted node name', async () => {
    renderWorkspace('writer-smoke')

    await mocks.graphCanvasProps?.onCreatePhase?.('logic', 'summarize_events')

    expect(mocks.invoke).toHaveBeenCalledWith('write_workspace_file', expect.objectContaining({
      relativePath: 'phases/summarize_events/LOGIC.md',
      content: expect.stringContaining('name: summarize_events'),
      createIfAbsent: true,
    }))
    const serializedPhases = mocks.serializeSkillGraph.mock.calls[0][1] as SerializableGraphPhaseRef[]
    expect(serializedPhases).toContainEqual(expect.objectContaining({
      id: 'summarize_events',
      src: 'phases/summarize_events',
      depends_on: [],
      mode: 'logic',
    }))
  })

  it('creates a phase without rewriting existing topology dependencies', async () => {
    renderWorkspace(INPUT_SENTINEL_FIXTURE_SKILL_ID)

    await mocks.graphCanvasProps?.onCreatePhase?.('logic')

    const serializedPhases = mocks.serializeSkillGraph.mock.calls[0][1] as SerializableGraphPhaseRef[]
    expect(serializedPhases.find((phase) => phase.id === 'entry')?.depends_on).toEqual(['input'])
    expect(serializedPhases.find((phase) => phase.id === 'logic')?.depends_on).toEqual([])
  })

  it('does not adopt a stale phase directory when creating a new phase', async () => {
    renderWorkspace(STALE_PHASE_DIR_FIXTURE_SKILL_ID)

    await mocks.graphCanvasProps?.onCreatePhase?.('logic')

    const phaseWrites = mocks.invoke.mock.calls.filter(
      ([command, payload]) =>
        command === 'write_workspace_file'
        && String((payload as { relativePath?: string }).relativePath).startsWith('phases/'),
    )
    expect(phaseWrites.map(([, payload]) => (payload as { relativePath?: string }).relativePath)).toEqual([
      'phases/logic-2/LOGIC.md',
    ])
    const serializedPhases = mocks.serializeSkillGraph.mock.calls[0][1] as SerializableGraphPhaseRef[]
    expect(serializedPhases.some((phase) => phase.id === 'logic')).toBe(false)
    expect(serializedPhases.some((phase) => phase.id === 'logic-2')).toBe(true)
    expect(mocks.invoke).toHaveBeenCalledWith('write_workspace_file', expect.objectContaining({
      relativePath: 'GRAPH.md',
      content: 'serialized graph\n',
    }))
    expect(toastMocks.error).not.toHaveBeenCalled()
  })

  it('rolls back a newly-created phase directory when GRAPH serialization fails', async () => {
    mocks.serializeSkillGraph.mockRejectedValueOnce(new Error('serialize failed'))
    renderWorkspace('writer-smoke')

    await mocks.graphCanvasProps?.onCreatePhase?.('logic')

    expect(mocks.invoke).toHaveBeenCalledWith('write_workspace_file', expect.objectContaining({
      relativePath: 'phases/logic/LOGIC.md',
      createIfAbsent: true,
    }))
    expect(mocks.invoke).toHaveBeenCalledWith('delete_workspace_path', {
      workspaceRoot: 'writer-smoke',
      path: 'phases/logic',
    })
    expect(toastMocks.error).toHaveBeenCalledWith('serialize failed')
  })

  it('auto-scaffolds a child skill folder and wires the path when creating a subgraph phase', async () => {
    renderWorkspace('writer-smoke')

    await mocks.graphCanvasProps?.onCreatePhase?.('subgraph', 'producer_review')

    // SUBGRAPH.md carries the default skill-root-relative landing path.
    expect(mocks.invoke).toHaveBeenCalledWith('write_workspace_file', expect.objectContaining({
      relativePath: 'phases/producer_review/SUBGRAPH.md',
      content: expect.stringContaining('path: subgraph/producer_review'),
      createIfAbsent: true,
    }))
    // The child graph is scaffolded as a standard empty skill at that landing.
    expect(mocks.invoke).toHaveBeenCalledWith('write_workspace_file', expect.objectContaining({
      relativePath: 'subgraph/producer_review/GRAPH.md',
      content: expect.stringContaining('name: producer_review'),
      createIfAbsent: true,
    }))
    expect(mocks.invoke).toHaveBeenCalledWith('write_workspace_file', expect.objectContaining({
      relativePath: 'subgraph/producer_review/phases/init/SKILL.md',
      createIfAbsent: true,
    }))
    const serializedPhases = mocks.serializeSkillGraph.mock.calls[0][1] as SerializableGraphPhaseRef[]
    expect(serializedPhases).toContainEqual(expect.objectContaining({
      id: 'producer_review',
      mode: 'subgraph',
    }))
  })

  it('rolls back both the phase and the subgraph child folder when serialization fails', async () => {
    mocks.serializeSkillGraph.mockRejectedValueOnce(new Error('serialize failed'))
    renderWorkspace('writer-smoke')

    await mocks.graphCanvasProps?.onCreatePhase?.('subgraph', 'producer_review')

    const deletedPaths = mocks.invoke.mock.calls
      .filter(([command]) => command === 'delete_workspace_path')
      .map(([, payload]) => (payload as { path?: string }).path)
    expect(deletedPaths).toContain('subgraph/producer_review')
    expect(deletedPaths).toContain('phases/producer_review')
    expect(toastMocks.error).toHaveBeenCalledWith('serialize failed')
  })

  it('deletes the auto-created subgraph child folder when deleting a subgraph phase', async () => {
    renderWorkspace(SUBGRAPH_FIXTURE_SKILL_ID)

    await mocks.graphCanvasProps?.onDeletePhase?.('child_call')

    const deletedPaths = mocks.invoke.mock.calls
      .filter(([command]) => command === 'delete_workspace_path')
      .map(([, payload]) => (payload as { path?: string }).path)
    expect(deletedPaths).toContain('phases/child_call')
    expect(deletedPaths).toContain('subgraph/child_call')
    expect(toastMocks.error).not.toHaveBeenCalled()
  })

  it('leaves a re-pointed external subgraph path untouched when deleting the phase', async () => {
    renderWorkspace(SUBGRAPH_FIXTURE_SKILL_ID)

    await mocks.graphCanvasProps?.onDeletePhase?.('ext_call')

    const deletedPaths = mocks.invoke.mock.calls
      .filter(([command]) => command === 'delete_workspace_path')
      .map(([, payload]) => (payload as { path?: string }).path)
    expect(deletedPaths).toContain('phases/ext_call')
    // The external/shared path Studio did not create must never be deleted.
    expect(deletedPaths).not.toContain('/Users/me/shared-skill')
    expect(deletedPaths.some((path) => path?.includes('shared-skill'))).toBe(false)
  })

  it('surfaces native create-phase write failures instead of a generic toast', async () => {
    mocks.invoke.mockImplementation(async (command: string, payload: { relativePath?: string }) => {
      if (command === 'write_workspace_file' && payload.relativePath === 'GRAPH.md') {
        throw { type: 'WriteFailed', data: { message: 'cannot finalize write: locked' } }
      }
      return { path: payload.relativePath ?? 'GRAPH.md', hash: 'native-hash' }
    })
    renderWorkspace('writer-smoke')

    await mocks.graphCanvasProps?.onCreatePhase?.('logic')

    expect(toastMocks.error).toHaveBeenCalledWith('cannot finalize write: locked')
  })

  it('deletes a phase by persisting GRAPH.md without it before removing its phase directory', async () => {
    renderWorkspace(RECONNECT_FIXTURE_SKILL_ID)

    expect(mocks.graphCanvasProps?.onDeletePhase).toBeTypeOf('function')
    await mocks.graphCanvasProps?.onDeletePhase?.('draft')

    expect(mocks.serializeSkillGraph).toHaveBeenCalledTimes(1)
    const serializedPhases = mocks.serializeSkillGraph.mock.calls[0][1] as SerializableGraphPhaseRef[]
    expect(serializedPhases.some((phase) => phase.id === 'draft')).toBe(false)
    expect(serializedPhases.find((phase) => phase.id === 'review')?.depends_on).toEqual([])
    expect(mocks.invoke).toHaveBeenCalledWith('write_workspace_file', expect.objectContaining({
      relativePath: 'GRAPH.md',
      content: 'serialized graph\n',
      expectedHash: 'graph-hash',
    }))
    expect(mocks.invoke).toHaveBeenCalledWith('delete_workspace_path', {
      workspaceRoot: RECONNECT_FIXTURE_SKILL_ID,
      path: 'phases/draft',
    })
    // GRAPH.md is persisted without the phase before its directory is deleted, so a
    // crash can never orphan the directory.
    const deleteGraphWriteIndex = mocks.invoke.mock.calls.findIndex(
      ([command, payload]) =>
        command === 'write_workspace_file'
        && (payload as { relativePath?: string }).relativePath === 'GRAPH.md',
    )
    const draftDirDeleteIndex = mocks.invoke.mock.calls.findIndex(
      ([command, payload]) =>
        command === 'delete_workspace_path'
        && (payload as { path?: string }).path === 'phases/draft',
    )
    expect(deleteGraphWriteIndex).toBeGreaterThanOrEqual(0)
    expect(draftDirDeleteIndex).toBeGreaterThan(deleteGraphWriteIndex)
    expect(mocks.compileSkill).not.toHaveBeenCalled()
  })

  it('deletes orphaned root phase directories that are absent from the next GRAPH.md', async () => {
    renderWorkspace(STALE_PHASE_DIR_FIXTURE_SKILL_ID)

    await mocks.graphCanvasProps?.onDeletePhase?.('draft')

    expect(mocks.serializeSkillGraph).toHaveBeenCalledTimes(1)
    const serializedPhases = mocks.serializeSkillGraph.mock.calls[0][1] as SerializableGraphPhaseRef[]
    expect(serializedPhases.map((phase) => phase.id)).toEqual(['review'])
    expect(mocks.invoke).toHaveBeenCalledWith('write_workspace_file', expect.objectContaining({
      relativePath: 'GRAPH.md',
      content: 'serialized graph\n',
    }))
    const deletedPaths = mocks.invoke.mock.calls
      .filter(([command]) => command === 'delete_workspace_path')
      .map(([, payload]) => (payload as { path?: string }).path)
    expect(deletedPaths).toEqual(['phases/draft', 'phases/logic'])
    expect(mocks.compileSkill).not.toHaveBeenCalled()
  })

  it('does not report delete success when the phase folder is still present after native delete', async () => {
    mocks.invoke.mockImplementation(async (command: string, payload: { relativePath?: string; path?: string }) => {
      if (command === 'read_workspace_file') {
        return { path: payload.path ?? 'GRAPH.md', content: 'serialized graph\n', hash: 'native-hash' }
      }
      if (command === 'list_workspace_dir') {
        return [{ name: 'draft', kind: 'dir' }]
      }
      return { path: payload.relativePath ?? payload.path ?? 'GRAPH.md', hash: 'native-hash' }
    })
    renderWorkspace(RECONNECT_FIXTURE_SKILL_ID)

    await mocks.graphCanvasProps?.onDeletePhase?.('draft')

    expect(toastMocks.error).toHaveBeenCalledWith('Could not delete phase folder: phases/draft')
    expect(toastMocks.success).not.toHaveBeenCalledWith('Deleted draft')
    expect(mocks.compileSkill).not.toHaveBeenCalled()
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
    expect(mocks.compileSkill).not.toHaveBeenCalled()
  })

  it('wires conflict overwrite retry into the shared conflict dialog', () => {
    renderWorkspace()

    expect(mocks.conflictDialogProps?.onOverwriteRetry).toBeTypeOf('function')
  })

  it('starts the Settings backend controller with the Workspace, before the dialog opens', () => {
    renderWorkspace()

    expect(mocks.settingsControllerHookCalls).toBeGreaterThan(0)
  })

  it('keeps the settings page mounted while the toolbar opens and closes the dialog', () => {
    const container = document.createElement('div')
    document.body.appendChild(container)
    const root = createRoot(container)
    try {
      act(() => {
        root.render(
          createElement(Workspace, {
            skillId: 'writer-smoke',
            onSelectSkill: vi.fn(),
            onCloseSkill: vi.fn(),
          }),
        )
      })

      const toggle = container.querySelector('[data-testid="settings-toggle"]')
      expect(toggle).not.toBeNull()
      const mountedSettings = document.body.querySelector('[data-testid="settings"]')
      expect(mountedSettings).not.toBeNull()
      expect(mocks.settingsPageMounts).toBe(1)
      expect(mocks.settingsPageUnmounts).toBe(0)
      expect(toggle?.getAttribute('aria-pressed')).toBe('false')
      expect(document.body.style.pointerEvents).not.toBe('none')

      act(() => {
        toggle?.dispatchEvent(new MouseEvent('click', { bubbles: true }))
      })
      expect(document.body.querySelector('[data-testid="settings"]')).toBe(mountedSettings)
      expect(mocks.settingsPageProps?.initialTab).toBe('general')
      expect(mocks.settingsPageProps?.controller).toBe(mocks.settingsController)
      expect(mocks.settingsPageMounts).toBe(1)
      expect(toggle?.getAttribute('aria-pressed')).toBe('true')

      act(() => {
        toggle?.dispatchEvent(new MouseEvent('click', { bubbles: true }))
      })
      expect(document.body.querySelector('[data-testid="settings"]')).toBe(mountedSettings)
      expect(mocks.settingsPageMounts).toBe(1)
      expect(mocks.settingsPageUnmounts).toBe(0)
      expect(toggle?.getAttribute('aria-pressed')).toBe('false')
      expect(document.body.style.pointerEvents).not.toBe('none')
    } finally {
      act(() => {
        root.unmount()
      })
      container.remove()
    }
  })

  it('opens Settings modal on the LLM Roles tab when requested by a panel field', () => {
    const container = document.createElement('div')
    document.body.appendChild(container)
    const root = createRoot(container)
    try {
      act(() => {
        root.render(
          createElement(Workspace, {
            skillId: 'writer-smoke',
            onSelectSkill: vi.fn(),
            onCloseSkill: vi.fn(),
          }),
        )
      })

      expect(mocks.panelsProps?.onOpenSettings).toBeTypeOf('function')
      act(() => {
        mocks.panelsProps?.onOpenSettings?.('llm_roles')
      })

      expect(document.body.querySelector('[data-testid="settings"]')).not.toBeNull()
      expect(mocks.settingsPageProps?.initialTab).toBe('llm_roles')
      expect(mocks.settingsPageProps?.controller).toBe(mocks.settingsController)
    } finally {
      act(() => {
        root.unmount()
      })
      container.remove()
    }
  })

  it('does not treat a passing realtime lint as a manual compile pass', () => {
    mocks.lintStatus = 'passed'

    renderWorkspace()

    expect(mocks.centerActionBarProps?.stage).toBe('idle')
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

  it('opens the predict error drawer with path-diff details when predict returns failed status', async () => {
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

    const container = document.createElement('div')
    document.body.appendChild(container)
    const root = createRoot(container)
    try {
      await act(async () => {
        root.render(
          createElement(Workspace, {
            skillId: 'writer-smoke',
            onSelectSkill: vi.fn(),
            onCloseSkill: vi.fn(),
          }),
        )
      })

      await act(async () => {
        await mocks.centerActionBarProps?.onPredict?.()
      })

      const text = document.body.textContent ?? ''
      expect(text).toContain('1 predict error')
      expect(text).toContain('missing: review')
      expect(text).toContain('expected: draft -> review')
      expect(text).toContain('actual: draft')
      expect(document.body.querySelector('[data-slot="predict-drawer-content"]')).not.toBeNull()
    } finally {
      act(() => {
        root.unmount()
      })
      container.remove()
      document.body.innerHTML = ''
    }
  })

  it('opens the predict error drawer with engine diagnostics when predict failed without path diff', async () => {
    mocks.postPredictRun.mockResolvedValue({
      is_predict: true,
      status: 'failed',
      phases: [],
      path_diff: null,
      error: {
        code: '[F-v3-agent-exit-control-failed]',
        level: 'FATAL',
        stage: ['运行期'],
        message: "Phase 'segment' failed: max iterations (2) reached without a valid finish_task marker.",
        doc_link: 'docs/engine/mvp1/02-mechanism/05-run-inner/05-exit-control/mvp1-alignment.md',
        skill_id: null,
        phase_id: 'segment',
        field_path: 'business_data_md',
        source_path: null,
        details: {},
      },
      diagnostics: [],
      diagnostics_truncated: false,
      diagnostic_counts: { total: 1, by_level: { FATAL: 1 }, by_code: { '[F-v3-agent-exit-control-failed]': 1 } },
    })

    const container = document.createElement('div')
    document.body.appendChild(container)
    const root = createRoot(container)
    try {
      await act(async () => {
        root.render(
          createElement(Workspace, {
            skillId: 'writer-smoke',
            onSelectSkill: vi.fn(),
            onCloseSkill: vi.fn(),
          }),
        )
      })

      await act(async () => {
        await mocks.centerActionBarProps?.onPredict?.()
      })

      const text = document.body.textContent ?? ''
      expect(text).toContain('1 predict error')
      expect(text).toContain('[F-v3-agent-exit-control-failed]')
      expect(text).toContain("Phase 'segment' failed: max iterations (2) reached without a valid finish_task marker.")
      expect(text).toContain('phase: segment')
      expect(text).toContain('field: business_data_md')
      expect(text).not.toContain('backend did not return path-diff details')
      expect(document.body.querySelector('[data-slot="predict-drawer-content"]')).not.toBeNull()
    } finally {
      act(() => {
        root.unmount()
      })
      container.remove()
      document.body.innerHTML = ''
    }
  })

  it('opens the predict error drawer when the predict request fails before diagnostics return', async () => {
    const config: InternalAxiosRequestConfig = {
      baseURL: 'http://127.0.0.1:8787/api',
      url: '/skills/writer-smoke/runs/predict',
      method: 'post',
      headers: new AxiosHeaders(),
    }
    mocks.postPredictRun.mockRejectedValue(
      new BackendUnavailableError(new AxiosError('Network Error', 'ERR_NETWORK', config)),
    )

    const container = document.createElement('div')
    document.body.appendChild(container)
    const root = createRoot(container)
    try {
      await act(async () => {
        root.render(
          createElement(Workspace, {
            skillId: 'writer-smoke',
            onSelectSkill: vi.fn(),
            onCloseSkill: vi.fn(),
          }),
        )
      })

      await act(async () => {
        await mocks.centerActionBarProps?.onPredict?.()
      })

      const text = document.body.textContent ?? ''
      expect(text).toContain('1 predict error')
      expect(text).toContain('Backend unavailable')
      expect(text).toContain('Request: POST http://127.0.0.1:8787/api/skills/writer-smoke/runs/predict')
      expect(text).toContain('Axios code: ERR_NETWORK')
      expect(text).toContain('Original error: Network Error')
      expect(document.body.querySelector('[data-slot="predict-drawer-content"]')).not.toBeNull()
      expect(document.body.querySelector('[aria-label="Copy all predict errors"]')).not.toBeNull()
    } finally {
      act(() => {
        root.unmount()
      })
      container.remove()
      document.body.innerHTML = ''
    }
  })

  it('opens the run error drawer when starting run fails before diagnostics return', async () => {
    const config: InternalAxiosRequestConfig = {
      baseURL: 'http://127.0.0.1:8787/api',
      url: '/skills/writer-smoke/runs',
      method: 'post',
      headers: new AxiosHeaders(),
    }
    mocks.startRun.mockRejectedValue(
      new BackendUnavailableError(new AxiosError('connect ECONNREFUSED 127.0.0.1:8787', 'ECONNREFUSED', config)),
    )

    const container = document.createElement('div')
    document.body.appendChild(container)
    const root = createRoot(container)
    try {
      await act(async () => {
        root.render(
          createElement(Workspace, {
            skillId: 'writer-smoke',
            onSelectSkill: vi.fn(),
            onCloseSkill: vi.fn(),
          }),
        )
      })

      await act(async () => {
        await mocks.centerActionBarProps?.onPredict?.()
      })
      await act(async () => {
        await mocks.centerActionBarProps?.onRun?.()
      })

      expect(mocks.startRun).toHaveBeenCalledWith('writer-smoke', { topic: 'mars' })
      const text = document.body.textContent ?? ''
      expect(text).toContain('1 run error')
      expect(text).toContain('Backend unavailable')
      expect(text).toContain('Request: POST http://127.0.0.1:8787/api/skills/writer-smoke/runs')
      expect(text).toContain('Axios code: ECONNREFUSED')
      expect(text).toContain('Original error: connect ECONNREFUSED 127.0.0.1:8787')
      expect(document.body.querySelector('[data-slot="run-drawer-content"]')).not.toBeNull()
      expect(document.body.querySelector('[aria-label="Copy all run errors"]')).not.toBeNull()
      expect(toastMocks.error).toHaveBeenCalledWith('Run failed: Backend unavailable')
    } finally {
      act(() => {
        root.unmount()
      })
      container.remove()
      document.body.innerHTML = ''
    }
  })
})

// T-n6hist test#1/#2 (n6-history): the autocommit-feedback toast and the
// Local-History auto-refresh both live in run_ended useEffects, which SSR never
// runs. These drive a real client render (createRoot + act so effects fire),
// flip the run to run_ended, and assert the wiring end-to-end: getRunDetail →
// archiveFeedbackForGitStatus → toast (test#1), and refreshLocalHistory exactly
// once on the not-ended → ended edge (test#2).
describe('Workspace run_ended history wiring (integration)', () => {
  let container: HTMLDivElement
  let root: ReturnType<typeof createRoot>

  beforeEach(() => {
    ;(window as unknown as { __TAURI_INTERNALS__?: unknown }).__TAURI_INTERNALS__ = {}
    vi.stubGlobal(
      'WebSocket',
      class {
        onmessage: ((event: { data: string }) => void) | null = null
        close() {}
      },
    )
    mocks.runStreamEvents = []
    mocks.getRunDetail.mockReset()
    mocks.projectRunHistory.mockReset()
    mocks.projectRunHistory.mockResolvedValue(undefined)
    mocks.refreshLocalHistory.mockReset()
    mocks.resolveRunInput.mockReset()
    mocks.resolveRunInput.mockResolvedValue({ topic: 'mars' })
    mocks.postPredictRun.mockReset()
    mocks.postPredictRun.mockResolvedValue({
      is_predict: true,
      status: 'success',
      phases: [],
      path_diff: null,
    })
    mocks.startRun.mockReset()
    mocks.startRun.mockResolvedValue({
      run_id: 'run-1',
      status: 'running',
      started_at: '2026-06-17T00:00:00Z',
      metrics: null,
      input_summary: null,
    })
    mocks.lintStatus = 'passed'
    mocks.useSkillsIds.length = 0
    mocks.copilotProps.length = 0
    mocks.useCopilotCalls.length = 0
    mocks.goldenDiffCalls.length = 0
    mocks.goldenDiffResult = null
    mocks.goldenDiffCompare.mockReset()
    mocks.goldenDiffCompare.mockResolvedValue(null)
    toastMocks.success.mockReset()
    toastMocks.error.mockReset()
    toastMocks.warning.mockReset()
    container = document.createElement('div')
    document.body.appendChild(container)
    root = createRoot(container)
  })

  afterEach(() => {
    act(() => {
      root.unmount()
    })
    container.remove()
  })

  function renderWithEffects() {
    act(() => {
      root.render(
        createElement(Workspace, {
          skillId: 'writer-smoke',
          onSelectSkill: vi.fn(),
          onCloseSkill: vi.fn(),
        }),
      )
    })
  }

  // Predict → Run sets runId='run-1' (the run trace stream already carries the
  // run_ended event), flipping completedRunId on the not-ended → ended edge so
  // the history effects fire under a real client render.
  /**
   * Drive a run to the point the ENGINE says it ended — which is NOT the point
   * the run's finished state exists. The studio backend still has to
   * auto-commit, write the run metadata and write `report.md` after that event;
   * only then does it publish the terminal `run` gate. Callers that want the
   * finished-run truth must therefore also call {@link emitTerminalRunGate}.
   */
  async function startRunToEngineEnd(
    gitStatus: RunDetail['metadata']['git_status'],
    status: RunDetail['metadata']['status'] = 'success',
  ) {
    mocks.runStreamEvents = [runEndedEvent('run-1')]
    mocks.getRunDetail.mockResolvedValue(runDetailWithGitStatus('run-1', gitStatus, status))
    renderWithEffects()
    await act(async () => {
      await mocks.centerActionBarProps?.onPredict?.()
    })
    await act(async () => {
      await mocks.centerActionBarProps?.onRun?.()
    })
    await act(async () => {
      await Promise.resolve()
      await Promise.resolve()
    })
  }

  /** The backend's post-finalization signal: everything on disk is now written. */
  async function emitTerminalRunGate(outcome: 'pass' | 'fail' = 'pass') {
    await act(async () => {
      mocks.studioEventStreamSubscribers.at(-1)?.current.onSkillGate?.({
        skillId: 'writer-smoke',
        gate: 'run',
        outcome,
        runId: 'run-1',
      })
      await Promise.resolve()
      await Promise.resolve()
    })
  }

  async function startRunToCompletion(
    gitStatus: RunDetail['metadata']['git_status'],
    status: RunDetail['metadata']['status'] = 'success',
  ) {
    await startRunToEngineEnd(gitStatus, status)
    await emitTerminalRunGate()
  }

  it('does not read the finished run while the backend is still finalizing it', async () => {
    // The engine's run_ended arrives BEFORE the studio backend auto-commits and
    // writes report.md, so reading the run here yields a run with no archive
    // status and no report — the exact stale answer that used to be cached for
    // the rest of the session.
    await startRunToEngineEnd('committed')

    expect(mocks.getRunDetail).not.toHaveBeenCalled()
    expect(toastMocks.success).not.toHaveBeenCalledWith(expect.stringMatching(/Local History/i))
  })

  it('reads the finished run once the backend publishes the terminal run gate', async () => {
    await startRunToEngineEnd('committed')
    await emitTerminalRunGate()

    expect(mocks.getRunDetail).toHaveBeenCalledWith('writer-smoke', 'run-1')
  })

  it('re-fetches the run detail and surfaces a successful, revertable archive toast when committed', async () => {
    await startRunToCompletion('committed')

    expect(mocks.getRunDetail).toHaveBeenCalledWith('writer-smoke', 'run-1')
    expect(toastMocks.success).toHaveBeenCalledWith(expect.stringMatching(/Local History/i))
    expect(toastMocks.warning).not.toHaveBeenCalled()
  })

  it('does not promise a revertable snapshot when the skill has no git repo (no_git)', async () => {
    await startRunToCompletion('no_git')

    expect(mocks.getRunDetail).toHaveBeenCalledWith('writer-smoke', 'run-1')
    const noGitToast = toastMocks.success.mock.calls
      .map((call) => String(call[0]))
      .find((message) => /no git repo/i.test(message))
    expect(noGitToast).toBeDefined()
    expect(noGitToast).not.toMatch(/revert from Local History/i)
  })

  it('warns (never claims success) when the git index was locked', async () => {
    await startRunToCompletion('locked')

    expect(mocks.getRunDetail).toHaveBeenCalledWith('writer-smoke', 'run-1')
    expect(toastMocks.warning).toHaveBeenCalledWith(expect.stringMatching(/not archived/i))
  })

  it('remembers which trace row the user opened', () => {
    renderWithEffects()

    act(() => {
      mocks.panelsProps?.onSelectTraceEvent?.(2, {
        schema_version: '1.0',
        event_type: 'llm_call',
        timestamp: '2026-08-08T00:00:00Z',
        phase_name: 'segment',
      })
    })

    expect(mocks.panelsProps?.traceSelectedEventId).toBe('2026-08-08T00:00:00Z-llm_call-2')
  })

  it('refreshes Local History exactly once on the run_ended edge', async () => {
    await startRunToCompletion('committed')

    expect(mocks.refreshLocalHistory).toHaveBeenCalledTimes(1)
  })

  it('projects the started run metadata into run history without subscribing to the list', async () => {
    await startRunToCompletion('committed')

    expect(mocks.projectRunHistory).toHaveBeenCalledWith(expect.objectContaining({
      run_id: 'run-1',
      status: 'running',
    }))
  })

  // The timeline row prints `run.metrics.wall_time_sec`; a run whose row still
  // carries the STARTED metadata shows "n/a" forever, because a started run has
  // no metrics yet. The terminal projection is what replaces it, so it has to
  // carry the finished numbers.
  // D7 (decision 2026-08-09): a finished run must SAY it finished. The archive
  // toast reports a git snapshot, which is a different fact — so the outcome
  // toast is additive, and asserting both appear is the point of this test.
  it('announces the run outcome alongside — not instead of — the archive toast', async () => {
    await startRunToCompletion('committed')

    const messages = toastMocks.success.mock.calls.map((call) => String(call[0]))
    expect(messages).toContainEqual(expect.stringMatching(/Local History/i))
    const outcome = messages.find((message) => /run succeeded/i.test(message))
    expect(outcome).toBeDefined()
    expect(outcome).toContain('207.6s')
    expect(outcome).toContain('115,117 tokens')
  })

  it('reports a failed run as an error toast, not a success one', async () => {
    await startRunToCompletion(null, 'failed')

    expect(toastMocks.error).toHaveBeenCalledWith(expect.stringMatching(/run failed/i))
    expect(toastMocks.success).not.toHaveBeenCalledWith(expect.stringMatching(/run succeeded/i))
  })

  it('replaces the running row with the finished run, duration and all', async () => {
    await startRunToCompletion('committed')

    expect(mocks.projectRunHistory).toHaveBeenCalledWith(expect.objectContaining({
      run_id: 'run-1',
      status: 'success',
      metrics: expect.objectContaining({ wall_time_sec: 207.566, total_tokens: 115117 }),
    }))
  })
})

function runEndedEvent(runId: string): EventEnvelope {
  return {
    schema_version: 'studio.event.v1',
    stream_id: `${runId}-stream`,
    seq: 1,
    cursor: '1',
    run_id: runId,
    event_type: 'run_ended',
    timestamp: '2026-06-17T00:00:01Z',
    payload: {} as EventEnvelope['payload'],
  }
}

function runDetailWithGitStatus(
  runId: string,
  gitStatus: RunDetail['metadata']['git_status'],
  status: RunDetail['metadata']['status'] = 'success',
): RunDetail {
  return {
    metadata: {
      run_id: runId,
      status,
      started_at: '2026-06-17T00:00:00Z',
      metrics: { input_tokens: 99364, output_tokens: 15753, total_tokens: 115117, cost_estimate: null, wall_time_sec: 207.566 },
      input_summary: null,
      git_status: gitStatus,
    },
    input_data: null,
    events: [],
    final_context: null,
    artifacts: null,
    report_path: null,
  }
}

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
const INPUT_SENTINEL_FIXTURE_SKILL_ID = 'input-sentinel-fixture'
const STALE_PHASE_DIR_FIXTURE_SKILL_ID = 'stale-phase-dir-fixture'
const LINT_SEQUENTIAL_OVERWRITE_FIXTURE_SKILL_ID = 'lint-sequential-overwrite-fixture'
const INPUT_PREFLIGHT_FIXTURE_SKILL_ID = 'input-preflight-fixture'
const SUBGRAPH_FIXTURE_SKILL_ID = 'subgraph-fixture'

function skillDetail(skillId = 'writer-smoke'): SkillDetail {
  if (skillId === LINT_SEQUENTIAL_OVERWRITE_FIXTURE_SKILL_ID) {
    return {
      manifest: {
        schema_version: CURRENT_SCHEMA_VERSION,
        name: skillId,
        description: 'Lint sequential overwrite fixture',
        io: {
          inputs: { type: 'object', properties: {} },
          outputs: { type: 'object', properties: {} },
        },
        phases: ['draft', 'review'],
      },
      graph_topology: [
        { id: 'draft', src: 'phases/draft/SKILL.md', depends_on: [], mode: 'skill' },
        { id: 'review', src: 'phases/review/SKILL.md', depends_on: ['draft'], mode: 'skill' },
      ],
      node_schema_v21: {},
      io_schema: {},
      file_paths: {},
      files: {
        'GRAPH.md': 'graph before\n',
        'phases/draft/SKILL.md': 'draft before\n',
        'phases/review/SKILL.md': 'review before\n',
      },
      manifest_errors: null,
      has_golden: false,
      latest_run_metadata: null,
      lint_result: {
        status: 'failed',
        errors: [{
          file: 'phases/review/SKILL.md',
          line: 1,
          column: 1,
          phase_name: 'review',
          field_path: 'allow_sequential_overwrite',
          severity: 'error',
          error_code: 'F-v3-sequential-overwrite-unauthorized',
          message: "Phase 'review' sequentially overwrites field 'events_raw' outputted by upstream phase 'draft'. Declare 'events_raw' in allow_sequential_overwrite in SKILL.md to allow this.",
        }],
        phases_summary: null,
      },
    }
  }
  if (skillId === INPUT_PREFLIGHT_FIXTURE_SKILL_ID) {
    return {
      manifest: {
        schema_version: CURRENT_SCHEMA_VERSION,
        name: skillId,
        description: 'Input preflight fixture',
        io: {
          inputs: { type: 'object', properties: { chapter: { type: 'string' } } },
          outputs: { type: 'object', properties: {} },
        },
        phases: ['segment'],
      },
      graph_topology: [
        { id: 'segment', src: 'phases/segment/SKILL.md', depends_on: [], mode: 'skill' },
      ],
      node_schema_v21: {},
      io_schema: {
        inputs: { type: 'object', properties: { chapter: { type: 'string' } } },
        outputs: { type: 'object', properties: {} },
      },
      file_paths: {},
      files: {
        'GRAPH.md': 'graph before\n',
        'phases/segment/SKILL.md': 'segment before\n',
      },
      manifest_errors: null,
      has_golden: false,
      latest_run_metadata: null,
      lint_result: {
        status: 'failed',
        errors: [{
          file: '.workspace/runtime_config.json',
          line: null,
          column: null,
          phase_name: null,
          field_path: 'chapter',
          severity: 'error',
          error_code: 'STUDIO_RUNTIME_INPUT_MISSING',
          message: "Graph input schema requires runtime input field 'chapter'",
        }],
        phases_summary: [{ name: 'segment', mode: 'skill', depends_on: [] }],
      },
    }
  }
  if (skillId === STALE_PHASE_DIR_FIXTURE_SKILL_ID) {
    return {
      manifest: {
        schema_version: CURRENT_SCHEMA_VERSION,
        name: skillId,
        description: 'Stale phase directory fixture',
        io: {
          inputs: { type: 'object', properties: {} },
          outputs: { type: 'object', properties: {} },
        },
        phases: ['draft', 'review'],
      },
      graph_topology: [
        { id: 'draft', src: 'phases/draft/SKILL.md', depends_on: [], mode: 'skill' },
        { id: 'review', src: 'phases/review/LOGIC.md', depends_on: ['draft'], mode: 'logic' },
      ],
      node_schema_v21: {},
      io_schema: {},
      file_paths: {},
      files: {
        'GRAPH.md': 'graph before\n',
        'phases/draft/SKILL.md': 'draft before\n',
        'phases/review/LOGIC.md': 'review before\n',
        'phases/logic/LOGIC.md': 'stale logic before\n',
        'subgraph/child/phases/child_logic/LOGIC.md': 'child phase before\n',
      },
      manifest_errors: null,
      has_golden: false,
      latest_run_metadata: null,
      lint_result: null,
    }
  }
  if (skillId === SUBGRAPH_FIXTURE_SKILL_ID) {
    return {
      manifest: {
        schema_version: CURRENT_SCHEMA_VERSION,
        name: skillId,
        description: 'Subgraph delete fixture',
        io: {
          inputs: { type: 'object', properties: {} },
          outputs: { type: 'object', properties: {} },
        },
        phases: ['child_call', 'ext_call', 'review'],
      },
      graph_topology: [
        // Auto-created shape: path is the relative subgraph/<id> default landing.
        { id: 'child_call', src: 'phases/child_call/SUBGRAPH.md', depends_on: [], mode: 'subgraph', path: 'subgraph/child_call' },
        // Re-pointed external/shared path must never be auto-deleted (D7).
        { id: 'ext_call', src: 'phases/ext_call/SUBGRAPH.md', depends_on: [], mode: 'subgraph', path: '/Users/me/shared-skill' },
        { id: 'review', src: 'phases/review/LOGIC.md', depends_on: [], mode: 'logic' },
      ],
      node_schema_v21: {},
      io_schema: {},
      file_paths: {},
      files: {
        'GRAPH.md': 'graph before\n',
        'phases/child_call/SUBGRAPH.md': 'name: child_call\npath: subgraph/child_call\n',
        'phases/ext_call/SUBGRAPH.md': 'name: ext_call\npath: /Users/me/shared-skill\n',
        'phases/review/LOGIC.md': 'review before\n',
        'subgraph/child_call/GRAPH.md': 'child graph before\n',
      },
      manifest_errors: null,
      has_golden: false,
      latest_run_metadata: null,
      lint_result: null,
    }
  }
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
  if (skillId === INPUT_SENTINEL_FIXTURE_SKILL_ID) {
    return {
      manifest: {
        schema_version: CURRENT_SCHEMA_VERSION,
        name: skillId,
        description: 'Input sentinel fixture',
        io: {
          inputs: { type: 'object', properties: {} },
          outputs: { type: 'object', properties: {} },
        },
        phases: ['entry'],
      },
      graph_topology: [
        { id: 'entry', src: 'phases/entry/SKILL.md', depends_on: ['input'], mode: 'skill' },
      ],
      node_schema_v21: {},
      io_schema: {},
      file_paths: {},
      files: {
        'GRAPH.md': 'graph before\n',
        'phases/entry/SKILL.md': 'entry before\n',
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
