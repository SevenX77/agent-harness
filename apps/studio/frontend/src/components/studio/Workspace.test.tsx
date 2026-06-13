import { renderToStaticMarkup } from 'react-dom/server'
import type { ReactNode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { Workspace } from './Workspace'
import { CURRENT_SCHEMA_VERSION } from '@/config/schema'
import type { SkillDetail } from '@/api/types'

const mocks = vi.hoisted(() => ({
  panelsProps: null as null | {
    onPhaseFileSave?: (payload: { path: string; content: string; expectedHash: string }) => Promise<void> | void
  },
  graphCanvasProps: null as null | {
    skillId?: string | null
    onPersistConnection?: (connection: { source: string; target: string }) => Promise<void> | void
  },
  copilotProps: [] as Array<{ skillId: string | null }>,
  useSkillsIds: [] as Array<string | null>,
  writeSkillFile: vi.fn(),
  serializeSkillGraph: vi.fn(),
  mutateSkillDetail: vi.fn(),
  invoke: vi.fn(),
}))

vi.mock('@tauri-apps/api/core', () => ({
  invoke: mocks.invoke,
}))

vi.mock('@/api/client', () => ({
  compileSkill: vi.fn(),
  getSkillDetail: vi.fn(),
  serializeSkillGraph: mocks.serializeSkillGraph,
  writeSkillFile: mocks.writeSkillFile,
  wsUrl: () => 'ws://127.0.0.1:8787/ws/events',
}))

vi.mock('@/hooks/useSkills', () => ({
  useSkills: (skillId: string | null) => {
    mocks.useSkillsIds.push(skillId)
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
  GraphCanvas: (props: { skillId?: string | null, onPersistConnection?: (connection: { source: string; target: string }) => Promise<void> | void }) => {
    mocks.graphCanvasProps = props
    return <div data-testid="graph-canvas" />
  },
}))

vi.mock('@/components/copilot/copilot-panel', () => ({
  CopilotPanel: (props: { skillId: string | null }) => {
    mocks.copilotProps.push(props)
    return <aside data-testid="copilot-panel" />
  },
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
  Panels: (props: { onPhaseFileSave?: (payload: { path: string; content: string; expectedHash: string }) => Promise<void> | void }) => {
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
  CenterActionBar: () => <div data-testid="center-action-bar" />,
}))

vi.mock('sonner', () => ({
  toast: {
    error: vi.fn(),
    success: vi.fn(),
  },
}))

describe('Workspace WS-1 local writer contracts', () => {
  beforeEach(() => {
    vi.stubGlobal('window', { __TAURI_INTERNALS__: {} })
    mocks.panelsProps = null
    mocks.graphCanvasProps = null
    mocks.copilotProps.length = 0
    mocks.useSkillsIds.length = 0
    mocks.writeSkillFile.mockReset()
    mocks.writeSkillFile.mockResolvedValue({ path: 'GRAPH.md', hash: 'python-hash' })
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
      path: 'phases/draft/SKILL.md',
      content: 'updated phase\n',
      expectedHash: 'phase-hash',
    }))
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
      path: 'GRAPH.md',
      content: 'serialized graph\n',
      expectedHash: 'graph-hash',
    }))
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
      path: 'phases/draft/SKILL.md',
      content: 'updated phase\n',
    }))
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
