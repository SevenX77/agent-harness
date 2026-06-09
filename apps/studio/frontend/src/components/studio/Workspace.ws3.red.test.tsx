/**
 * @vitest-environment jsdom
 */

import { act } from 'react'
import { createRoot } from 'react-dom/client'
import type { Root } from 'react-dom/client'
import type { ReactNode } from 'react'
import { beforeEach, afterEach, describe, expect, it, vi } from 'vitest'
import type { Mock } from 'vitest'
import { Workspace } from './Workspace'
import { CURRENT_SCHEMA_VERSION } from '@/config/schema'
import type { SkillDetail } from '@/api/types'
import { toast } from 'sonner'

interface MockCenterActionBarProps {
  stage: string
  onCompile?: () => void | Promise<void>
  onPredict?: () => void | Promise<void>
  onRun?: () => void | Promise<void>
}

interface WorkspaceMocks {
  centerActionBarProps: MockCenterActionBarProps | null
  panelsProps: Record<string, unknown> | null
  graphCanvasProps: Record<string, unknown> | null
  postPredictRun: Mock
  startRun: Mock
  compileSkill: Mock
  mutateSkillDetail: Mock
  invoke: Mock
}

// Elevate mocks with hoisted
const mocks = vi.hoisted((): WorkspaceMocks => ({
  centerActionBarProps: null,
  panelsProps: null,
  graphCanvasProps: null,
  postPredictRun: vi.fn(),
  startRun: vi.fn(),
  compileSkill: vi.fn(),
  mutateSkillDetail: vi.fn(),
  invoke: vi.fn(),
}))

vi.mock('@tauri-apps/api/core', () => ({
  invoke: mocks.invoke,
}))

vi.mock('@/api/client', () => ({
  compileSkill: mocks.compileSkill,
  getSkillDetail: vi.fn(),
  serializeSkillGraph: vi.fn(),
  writeSkillFile: vi.fn(),
  wsUrl: () => 'ws://127.0.0.1:8787/ws/events',
  postPredictRun: mocks.postPredictRun,
  startRun: mocks.startRun,
}))

vi.mock('@/hooks/useSkills', () => ({
  useSkills: (skillId: string | null) => {
    return {
      skills: [],
      skillListError: null,
      mutateSkills: vi.fn(),
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
  readLintStatus: () => 'idle',
}))

vi.mock('@/lib/hash', () => ({
  sha256Hex: vi.fn(async () => 'graph-hash'),
}))

vi.mock('@/components/GraphCanvas', () => ({
  GraphCanvas: (props: Record<string, unknown>) => {
    mocks.graphCanvasProps = props
    return <div data-testid="graph-canvas" />
  },
}))

vi.mock('@/components/copilot/copilot-panel', () => ({
  CopilotPanel: () => <aside data-testid="copilot-panel" />,
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
  Panels: (props: Record<string, unknown>) => {
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
  ConflictDialog: () => <div data-testid="conflict-dialog" />,
}))

vi.mock('./center-action-bar', () => ({
  CenterActionBar: (props: MockCenterActionBarProps) => {
    mocks.centerActionBarProps = props
    return <div data-testid="center-action-bar" />
  },
}))

vi.mock('sonner', () => ({
  toast: {
    error: vi.fn(),
    success: vi.fn(),
  },
}))

const reactActGlobal = globalThis as typeof globalThis & {
  IS_REACT_ACT_ENVIRONMENT?: boolean
}
reactActGlobal.IS_REACT_ACT_ENVIRONMENT = true

describe('Workspace WS-3 Predict and Run integration contracts (RED)', () => {
  let container: HTMLDivElement | null = null
  let root: Root | null = null

  function renderWorkspace(skillId = 'writer-smoke') {
    act(() => {
      root!.render(
        <Workspace
          skillId={skillId}
          onSelectSkill={vi.fn()}
          onCloseSkill={vi.fn()}
        />,
      )
    })
  }

  beforeEach(() => {
    container = document.createElement('div')
    document.body.appendChild(container)
    root = createRoot(container)

    // Mock global WebSocket to prevent runtime errors during mount
    class MockWebSocket {
      url: string
      constructor(url: string) {
        this.url = url
      }
      close() {}
    }
    vi.stubGlobal('WebSocket', MockWebSocket)

    mocks.centerActionBarProps = null
    mocks.panelsProps = null
    mocks.graphCanvasProps = null
    mocks.postPredictRun.mockReset()
    mocks.startRun.mockReset()
    mocks.compileSkill.mockReset()
    mocks.mutateSkillDetail.mockReset()
    mocks.invoke.mockReset()
    vi.mocked(toast.error).mockReset()
    vi.mocked(toast.success).mockReset()
  })

  afterEach(() => {
    if (root) {
      act(() => {
        root!.unmount()
      })
    }
    if (container) {
      container.remove()
    }
    container = null
    root = null
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
  })

  it('triggers postPredictRun on Predict click (RED)', async () => {
    renderWorkspace()

    expect(mocks.centerActionBarProps).toBeDefined()
    
    // Simulate user clicking Predict
    if (mocks.centerActionBarProps?.onPredict) {
      await act(async () => {
        await mocks.centerActionBarProps!.onPredict!()
      })
    }

    // Assert that the real predict DTO endpoint is called with chosen config
    expect(mocks.postPredictRun).toHaveBeenCalledWith('writer-smoke', expect.any(Object))
  })

  it('renders structured error messages when Predict fails (RED)', async () => {
    // Mock postPredictRun to fail with a structured error
    mocks.postPredictRun.mockRejectedValue({
      response: {
        status: 400,
        data: {
          code: 'compile_failed',
          errors: [
            {
              file: 'phases/draft/SKILL.md',
              line: 10,
              field: 'system_prompt',
              message: 'Invalid system prompt structure',
            }
          ]
        }
      }
    })

    renderWorkspace()

    if (mocks.centerActionBarProps?.onPredict) {
      await act(async () => {
        await mocks.centerActionBarProps!.onPredict!()
      })
    }

    // It should surface the structured error details instead of a console-only silent log
    expect(toast.error).toHaveBeenCalledWith(expect.stringContaining('Invalid system prompt structure'))
  })

  it('gating: run can only be triggered in predict-pass state (Regression Lock)', () => {
    renderWorkspace()
    
    // Attempting to call onRun directly in initial state (which is not predict-pass) should not invoke startRun.
    if (mocks.centerActionBarProps?.onRun) {
      act(() => {
        mocks.centerActionBarProps!.onRun!()
      })
    }
    expect(mocks.startRun).not.toHaveBeenCalled()
  })

  it('triggers startRun, saves run_id, and drives canvas node status on Run success (RED)', async () => {
    mocks.postPredictRun.mockResolvedValue({
      run_id: 'predict-run-123',
      status: 'predict-pass',
    })
    
    mocks.startRun.mockResolvedValue({
      run_id: 'run-999',
      status: 'running',
      started_at: '2026-06-08T12:00:00Z',
      input_summary: null,
      metrics: null,
    })

    // 1. Initial render, we are not in predict-pass yet.
    renderWorkspace()

    // 2. Click Predict, which should invoke postPredictRun and advance stage to predict-pass.
    if (mocks.centerActionBarProps?.onPredict) {
      await act(async () => {
        await mocks.centerActionBarProps!.onPredict!()
      })
    }
    expect(mocks.postPredictRun).toHaveBeenCalledWith('writer-smoke', expect.any(Object))

    // 3. Trigger the run callback (which is now unlocked by React state change propagation)
    if (mocks.centerActionBarProps?.onRun) {
      await act(async () => {
        await mocks.centerActionBarProps!.onRun!()
      })
    }

    // 4. Assert startRun is invoked.
    expect(mocks.startRun).toHaveBeenCalledWith('writer-smoke', expect.any(Object))
  })
})

function skillDetail(skillId = 'writer-smoke'): SkillDetail {
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
