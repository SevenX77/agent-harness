import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { addEdge, MarkerType, useEdgesState, useNodesState } from 'reactflow'
import type { Connection } from 'reactflow'
import 'reactflow/dist/style.css'
import { GraphCanvas } from './components/GraphCanvas'
import { HeaderBar } from './components/HeaderBar'
import { DirtyBar } from './components/DirtyBar'
import { PromptInspector } from './components/PromptInspector'
import { RightPanel } from './components/RightPanel'
import { SkillSidebar } from './components/SkillSidebar'
import { SkillCreatorWizard } from './components/creator/SkillCreatorWizard'
import { DraftRestoreModal } from './components/draft/DraftRestoreModal'
import { InputPlayground } from './components/playground/InputPlayground'
import { PhaseDrawer } from './components/phaseform/PhaseDrawer'
import { CommandPalette } from './components/shortcuts/CommandPalette'
import type { CommandAction } from './components/shortcuts/CommandPalette'
import { ShortcutsCheatSheet } from './components/shortcuts/ShortcutsCheatSheet'
import { SkillPalette } from './components/shortcuts/SkillPalette'
import { ToastStack } from './components/ToastStack'
import { WelcomeScreen } from './components/WelcomeScreen'
import type { EditorOnMount, MonacoApi, MonacoEditor } from './components/MonacoPanel'
import { api, fetchSkillFiles, saveSkillFiles, wsUrl } from './api/client'
import type {
  CallbackEvent,
  JsonObject,
  RunDetail,
  LintResult,
  RunMetadata,
  RunRequest,
  SkillDetail,
  SkillManifest,
  SkillSummary,
  TerminalSession,
} from './api/types'
import { useBatchRun } from './hooks/useBatchRun'
import { useRecentSkills } from './hooks/useRecentSkills'
import { useGoldenDiff } from './hooks/useGoldenDiff'
import { useDraftPersist } from './hooks/useDraftPersist'
import { usePhaseForm } from './hooks/usePhaseForm'
import { usePhaseSync } from './hooks/usePhaseSync'
import { useSkills } from './hooks/useSkills'
import { useTheme } from './hooks/useTheme'
import { useToasts } from './hooks/useToasts'
import { useTraceSelection } from './hooks/useTraceSelection'
import { useGlobalShortcuts } from './hooks/useGlobalShortcuts'
import { useWorkspaceStore } from './stores/workspace'
import type {
  ActiveTab,
  ApiKeyName,
  ApiKeys,
  LintOverride,
  RunStatus,
  TerminalStatus,
  VisualPhase,
} from './types/studio'
import { errorMessage, isRecord, lintErrorsFromError } from './utils/errors'
import { buildGraph, graphSkill, subgraphSkillId } from './utils/graph'
import { manifestToSkillMarkdown } from './utils/skillMarkdown'
import { verifyTauriWindowIpc } from './utils/tauriIpc'
import { eventPhase, findPromptEvent } from './utils/trace'

function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}

function phaseLineFor(source: string, phaseName: string): number | null {
  if (!phaseName || phaseName === 'system') {
    return null
  }
  const pattern = new RegExp(`^\\s*(?:-\\s*)?name:\\s*['"]?${escapeRegExp(phaseName)}['"]?\\s*$`)
  const lines = source.split('\n')
  const index = lines.findIndex((line) => pattern.test(line))
  return index >= 0 ? index + 1 : null
}

function isErrorTraceEvent(event: CallbackEvent): boolean {
  return event.event_type === 'internal_error' || event.event_type === 'validation_fail'
}

export default function App() {
  const [activeSkillId, setActiveSkillId] = useState<string | null>(null)
  const selectedSkillId = activeSkillId
  const { isDarkMode, setIsDarkMode } = useTheme()
  const { toasts, pushToast } = useToasts()
  const { register } = useGlobalShortcuts()
  const traceSelection = useTraceSelection()
  const { recentSkills, rememberSkill } = useRecentSkills()
  const {
    skills,
    skillListError,
    mutateSkills,
    skillDetail,
    skillDetailError,
    mutateSkillDetail,
  } = useSkills(selectedSkillId)

  const [nodes, setNodes, onNodesChange] = useNodesState([])
  const [edges, setEdges, onEdgesChange] = useEdgesState([])
  const [lintOverride, setLintOverride] = useState<LintOverride | null>(null)
  const [runStatus, setRunStatus] = useState<RunStatus>('idle')
  const [activeTab, setActiveTab] = useState<ActiveTab>('code')
  const [playgroundPayload, setPlaygroundPayload] = useState<JsonObject>({})
  const [playgroundValid, setPlaygroundValid] = useState(true)
  const [isArtifactsMenuOpen, setIsArtifactsMenuOpen] = useState(false)
  const [apiKeys, setApiKeys] = useState<ApiKeys>({ openai: '', anthropic: '', gemini: '' })
  const [traceLogs, setTraceLogs] = useState<CallbackEvent[]>([])
  const [lastRunId, setLastRunId] = useState<string | null>(null)
  const [expandedSubgraphs, setExpandedSubgraphs] = useState<Set<string>>(new Set())
  const [nestedManifests, setNestedManifests] = useState<Record<string, SkillManifest>>({})
  const [selectedPromptIndex, setSelectedPromptIndex] = useState<number | null>(null)
  const [terminalSession, setTerminalSession] = useState<TerminalSession | null>(null)
  const [terminalStatus, setTerminalStatus] = useState<TerminalStatus>('idle')
  const [creatorOpen, setCreatorOpen] = useState(false)
  const [phaseDrawerPhaseId, setPhaseDrawerPhaseId] = useState<string | null>(null)
  const [commandPaletteOpen, setCommandPaletteOpen] = useState(false)
  const [skillPaletteOpen, setSkillPaletteOpen] = useState(false)
  const [cheatSheetOpen, setCheatSheetOpen] = useState(false)
  const [restorePromptSkillId, setRestorePromptSkillId] = useState<string | null>(null)
  const [dismissedDraftSkillId, setDismissedDraftSkillId] = useState<string | null>(null)
  const [pendingJumpLine, setPendingJumpLine] = useState<number | null>(null)
  const editorRef = useRef<MonacoEditor | null>(null)
  const monacoRef = useRef<MonacoApi | null>(null)
  const runWsRef = useRef<WebSocket | null>(null)
  const goldenDiff = useGoldenDiff(selectedSkillId, lastRunId)
  const batchRun = useBatchRun(selectedSkillId)
  const workspaceFiles = useWorkspaceStore((state) => state.files)
  const workspaceActiveFile = useWorkspaceStore((state) => state.activeFile)
  const workspaceDirty = useWorkspaceStore((state) => state.dirty)
  const workspaceIsDirty = useWorkspaceStore((state) => state.isDirty)
  const setWorkspaceFiles = useWorkspaceStore((state) => state.setFiles)
  const setWorkspaceActiveFile = useWorkspaceStore((state) => state.setActive)
  const updateWorkspaceFile = useWorkspaceStore((state) => state.updateFile)
  const loadedWorkspaceSkillIdRef = useRef<string | null>(null)

  useEffect(() => {
    let cancelled = false
    void verifyTauriWindowIpc()
      .then((connected) => {
        if (!cancelled && connected) {
          console.info('[studio] Tauri IPC verified via window.setTitle')
        }
      })
      .catch((error: unknown) => {
        console.debug('[studio] Tauri IPC unavailable', error)
      })
    return () => {
      cancelled = true
    }
  }, [])

  useEffect(() => {
    if (!selectedSkillId || !skillDetail) {
      setWorkspaceFiles({})
      loadedWorkspaceSkillIdRef.current = null
      return
    }
    if (loadedWorkspaceSkillIdRef.current === selectedSkillId) {
      return
    }

    const files = Object.keys(skillDetail.files).length > 0
      ? skillDetail.files
      : { 'SKILL.md': manifestToSkillMarkdown(skillDetail.manifest) }
    setWorkspaceFiles(files)
    loadedWorkspaceSkillIdRef.current = selectedSkillId
  }, [selectedSkillId, setWorkspaceFiles, skillDetail])

  const canonicalSkillMarkdown = skillDetail ? manifestToSkillMarkdown(skillDetail.manifest) : ''
  const skillMarkdown = workspaceFiles['SKILL.md'] ?? canonicalSkillMarkdown
  const {
    draft: storedDraft,
    baseHash: draftBaseHash,
    restoreDraft,
    clearDraft,
  } = useDraftPersist({
    skillId: selectedSkillId,
    content: skillMarkdown,
    baseContent: canonicalSkillMarkdown,
    dirty: workspaceDirty['SKILL.md'] === true,
  })
  const activeLintOverride = lintOverride?.skillId === selectedSkillId ? lintOverride : null
  const lintStatus = activeLintOverride?.status ?? skillDetail?.lint_result?.status ?? 'idle'
  const detailLintErrors = skillDetail?.lint_result?.errors
  const lintErrors = useMemo(
    () => activeLintOverride?.errors ?? detailLintErrors ?? [],
    [activeLintOverride, detailLintErrors],
  )
  const currentManifest = skillDetail?.manifest
  const manifestInputs = useMemo(
    () => currentManifest?.type === 'graph' ? currentManifest.io.inputs : [],
    [currentManifest],
  )
  const handlePhaseMarkdownChange = useCallback((code: string) => {
    if (!selectedSkillId) {
      return
    }
    updateWorkspaceFile('SKILL.md', code)
  }, [selectedSkillId, updateWorkspaceFile])
  const phaseForm = usePhaseForm(skillMarkdown, phaseDrawerPhaseId)
  const phaseSync = usePhaseSync({
    markdown: skillMarkdown,
    phaseId: phaseDrawerPhaseId,
    editor: editorRef.current,
    monaco: monacoRef.current,
    enabled: phaseDrawerPhaseId !== null,
    onMarkdownChange: handlePhaseMarkdownChange,
  })

  const toggleSubgraph = useCallback(async (phase: VisualPhase) => {
    const shouldExpand = !expandedSubgraphs.has(phase.id)
    setExpandedSubgraphs(shouldExpand ? new Set([phase.id]) : new Set())

    const nestedId = subgraphSkillId(phase.subgraph)
    if (!shouldExpand || !nestedId || nestedManifests[nestedId]) {
      return
    }

    try {
      const response = await api.get<SkillDetail>(`/skills/${nestedId}`)
      setNestedManifests((current) => ({ ...current, [nestedId]: response.data.manifest }))
    } catch (error) {
      pushToast(`Failed to load subgraph ${nestedId}: ${errorMessage(error)}`, 'error')
    }
  }, [expandedSubgraphs, nestedManifests, pushToast])

  const graph = useMemo(() => (
    skillDetail
      ? buildGraph(skillDetail.manifest, expandedSubgraphs, nestedManifests, toggleSubgraph, isDarkMode)
      : { nodes: [], edges: [] }
  ), [expandedSubgraphs, nestedManifests, skillDetail, toggleSubgraph, isDarkMode])

  useEffect(() => {
    setNodes(graph.nodes)
    setEdges(graph.edges)
  }, [graph, setEdges, setNodes])

  useEffect(() => {
    const model = editorRef.current?.getModel()
    const monaco = monacoRef.current
    if (!model || !monaco) {
      return
    }

    monaco.editor.setModelMarkers(model, 'studio-lint', lintErrors.map((error) => ({
      startLineNumber: error.line ?? 1,
      startColumn: error.column ?? 1,
      endLineNumber: error.line ?? 1,
      endColumn: 120,
      message: error.message,
      severity: error.severity === 'warning' ? monaco.MarkerSeverity.Warning : monaco.MarkerSeverity.Error,
    })))
  }, [lintErrors])

  useEffect(() => {
    if (!selectedSkillId || !skillDetail || !storedDraft || workspaceIsDirty) {
      return
    }
    if (dismissedDraftSkillId === selectedSkillId) {
      return
    }
    if (storedDraft.content === canonicalSkillMarkdown) {
      clearDraft()
      return
    }
    setRestorePromptSkillId(selectedSkillId)
  }, [
    canonicalSkillMarkdown,
    clearDraft,
    dismissedDraftSkillId,
    selectedSkillId,
    skillDetail,
    storedDraft,
    workspaceIsDirty,
  ])

  useEffect(() => {
    const handleBeforeUnload = (event: BeforeUnloadEvent) => {
      if (!workspaceIsDirty) {
        return
      }
      event.preventDefault()
      event.returnValue = ''
    }
    window.addEventListener('beforeunload', handleBeforeUnload)
    return () => window.removeEventListener('beforeunload', handleBeforeUnload)
  }, [workspaceIsDirty])

  useEffect(() => {
    const socket = new WebSocket(wsUrl('/ws/events'))
    socket.onmessage = (message) => {
      const parsed: unknown = JSON.parse(String(message.data))
      if (!isRecord(parsed) || parsed.type !== 'skill_changed' || typeof parsed.skill_id !== 'string') {
        return
      }

      pushToast(`Skill changed: ${parsed.skill_id}`, 'info')
      if (parsed.skill_id === selectedSkillId) {
        void mutateSkillDetail()
      }
    }
    socket.onerror = () => pushToast('Studio event stream disconnected', 'error')
    return () => socket.close()
  }, [mutateSkillDetail, pushToast, selectedSkillId])

  useEffect(() => () => runWsRef.current?.close(), [])

  const onConnect = useCallback((params: Connection) => {
    setEdges((current) => addEdge({
      ...params,
      animated: true,
      markerEnd: { type: MarkerType.ArrowClosed },
      style: { stroke: '#94a3b8', strokeWidth: 2 },
    }, current))
  }, [setEdges])

  const handleSelectSkill = useCallback(async (skillId: string) => {
    if (skillId === selectedSkillId) {
      return
    }
    if (workspaceIsDirty && selectedSkillId && !window.confirm('Unsaved changes in current skill, switch anyway?')) {
      return
    }
    try {
      const detail = await fetchSkillFiles(skillId)
      const files = Object.keys(detail.files).length > 0
        ? detail.files
        : { 'SKILL.md': manifestToSkillMarkdown(detail.manifest) }
      setWorkspaceFiles(files)
      loadedWorkspaceSkillIdRef.current = skillId
    } catch (error) {
      pushToast(errorMessage(error), 'error')
      return
    }
    setActiveSkillId(skillId)
    setExpandedSubgraphs(new Set())
    setNestedManifests({})
    setLintOverride(null)
    setRunStatus('idle')
    setTraceLogs([])
    setLastRunId(null)
    goldenDiff.clear()
    setPhaseDrawerPhaseId(null)
    setSelectedPromptIndex(null)
    setActiveTab('code')
    rememberSkill(skillId)
  }, [goldenDiff, pushToast, rememberSkill, selectedSkillId, setWorkspaceFiles, workspaceIsDirty])

  const handleLint = useCallback(async () => {
    if (!selectedSkillId) {
      return
    }

    setLintOverride({ skillId: selectedSkillId, status: 'checking', errors: [] })
    try {
      const response = await api.post<LintResult>(`/skills/${selectedSkillId}/lint`)
      setLintOverride({ skillId: selectedSkillId, status: response.data.status, errors: response.data.errors })
      pushToast(response.data.status === 'passed' ? 'Lint passed' : 'Lint failed', response.data.status === 'passed' ? 'success' : 'error')
    } catch (error) {
      setLintOverride({ skillId: selectedSkillId, status: 'failed', errors: lintErrorsFromError(error) })
      pushToast(errorMessage(error), 'error')
    }
  }, [pushToast, selectedSkillId])

  const handleSave = useCallback(async () => {
    if (!selectedSkillId) {
      return
    }

    setLintOverride({ skillId: selectedSkillId, status: 'checking', errors: [] })
    try {
      const { files } = useWorkspaceStore.getState()
      const response = await saveSkillFiles(selectedSkillId, files)
      await mutateSkillDetail(response, { revalidate: false })
      useWorkspaceStore.getState().markSaved()
      setLintOverride({
        skillId: selectedSkillId,
        status: response.lint_result?.status ?? 'passed',
        errors: response.lint_result?.errors ?? [],
      })
      clearDraft()
      pushToast('Saved and linted successfully', 'success')
    } catch (error) {
      const errors = lintErrorsFromError(error)
      setLintOverride({ skillId: selectedSkillId, status: 'failed', errors })
      pushToast(errorMessage(error), 'error')
    }
  }, [clearDraft, mutateSkillDetail, pushToast, selectedSkillId])

  const handleEditorMount: EditorOnMount = useCallback((editor, monaco) => {
    editorRef.current = editor
    monacoRef.current = monaco
    editor.addCommand(monaco.KeyMod.CtrlCmd | monaco.KeyCode.KeyS, () => {
      void handleSave()
    })
  }, [handleSave])

  const jumpToLine = useCallback((line: number | null) => {
    if (!line || !editorRef.current) {
      return
    }
    editorRef.current.revealLineInCenter(line)
    editorRef.current.setPosition({ lineNumber: line, column: 1 })
    editorRef.current.focus()
  }, [])

  useEffect(() => {
    if (activeTab !== 'code' || pendingJumpLine === null) {
      return
    }
    const timeout = window.setTimeout(() => {
      jumpToLine(pendingJumpLine)
      setPendingJumpLine(null)
    }, 0)
    return () => window.clearTimeout(timeout)
  }, [activeTab, jumpToLine, pendingJumpLine])

  const handleRun = useCallback(async (values?: JsonObject) => {
    if (!selectedSkillId) {
      return
    }

    setRunStatus('running')
    setActiveTab('trace')
    setIsArtifactsMenuOpen(false)
    setTraceLogs([])
    setLastRunId(null)
    goldenDiff.clear()
    setSelectedPromptIndex(null)
    runWsRef.current?.close()

    const request: RunRequest = {
      input_data: values ?? playgroundPayload,
      paste_json: null,
    }

    try {
      const response = await api.post<RunMetadata>(`/skills/${selectedSkillId}/runs`, request)
      setLastRunId(response.data.run_id)
      const hydrateRunTrace = async () => {
        try {
          const detail = await api.get<RunDetail>(`/skills/${selectedSkillId}/runs/${response.data.run_id}`)
          setTraceLogs(detail.data.events)
          if (detail.data.metadata.status !== 'running') {
            setRunStatus(detail.data.metadata.status === 'success' ? 'success' : 'error')
          }
        } catch {
          // WebSocket events remain the primary live path; detail hydration is best-effort.
        }
      }
      const socket = new WebSocket(wsUrl(`/ws/runs/${response.data.run_id}`))
      runWsRef.current = socket
      socket.onmessage = (message) => {
        const parsed: unknown = JSON.parse(String(message.data))
        if (!isRecord(parsed) || typeof parsed.event_type !== 'string') {
          return
        }
        const event = parsed as CallbackEvent
        setTraceLogs((current) => [...current, event])
        if (event.event_type === 'run_ended') {
          setRunStatus(event.status === 'crashed' ? 'error' : 'success')
          socket.close()
        }
      }
      socket.onclose = () => {
        void hydrateRunTrace()
      }
      socket.onerror = () => {
        setRunStatus('error')
        pushToast('Run WebSocket disconnected', 'error')
      }
    } catch (error) {
      setRunStatus('error')
      pushToast(errorMessage(error), 'error')
    }
  }, [goldenDiff, playgroundPayload, pushToast, selectedSkillId])

  const openTerminal = useCallback(async () => {
    if (!selectedSkillId) {
      return
    }
    setTerminalStatus('connecting')
    setActiveTab('terminal')
    try {
      const response = await api.post<TerminalSession>(`/skills/${selectedSkillId}/terminal`)
      setTerminalSession(response.data)
      pushToast('CLI session opened', 'success')
    } catch (error) {
      setTerminalStatus('error')
      pushToast(errorMessage(error), 'error')
    }
  }, [pushToast, selectedSkillId])

  const copyErrorToClipboard = useCallback((message: string) => {
    void navigator.clipboard.writeText(message)
    pushToast('Copied error details', 'success')
  }, [pushToast])

  const handleImportSkill = useCallback(() => {
    const path = prompt('Enter skill path to import:')
    if (path) {
      pushToast('Importing skills from path is not implemented in the backend yet.', 'info')
    }
  }, [pushToast])

  const handleApiKeyChange = useCallback((key: ApiKeyName, value: string) => {
    setApiKeys((current) => ({ ...current, [key]: value }))
  }, [])

  const handlePlaygroundPayloadChange = useCallback((values: JsonObject, isValid: boolean) => {
    setPlaygroundPayload(values)
    setPlaygroundValid(isValid)
  }, [])

  const handleSkillCreated = useCallback(async (skillId: string) => {
    await mutateSkills()
    handleSelectSkill(skillId)
  }, [handleSelectSkill, mutateSkills])

  const handleRestoreDraft = useCallback(() => {
    if (!selectedSkillId) {
      return
    }
    const draft = restoreDraft()
    if (!draft) {
      setRestorePromptSkillId(null)
      return
    }
    updateWorkspaceFile('SKILL.md', draft.content)
    setDismissedDraftSkillId(selectedSkillId)
    setRestorePromptSkillId(null)
    setActiveTab('code')
    pushToast('Restored local draft', 'success')
  }, [pushToast, restoreDraft, selectedSkillId, updateWorkspaceFile])

  const handleDiscardDraft = useCallback(() => {
    if (selectedSkillId) {
      setDismissedDraftSkillId(selectedSkillId)
    }
    clearDraft()
    setRestorePromptSkillId(null)
    pushToast('Discarded local draft', 'info')
  }, [clearDraft, pushToast, selectedSkillId])

  const handleForkSkill = useCallback(async (sourceSkillId: string, newSkillId: string) => {
    const response = await api.post<SkillSummary>(`/skills/${sourceSkillId}/fork`, {
      new_skill_id: newSkillId,
    })
    await mutateSkills()
    handleSelectSkill(response.data.id)
    pushToast(`Forked ${sourceSkillId} to ${response.data.id}`, 'success')
  }, [handleSelectSkill, mutateSkills, pushToast])

  const handleGraphPhaseSelect = useCallback((phaseId: string) => {
    if (!traceSelection.linkEnabled) {
      return
    }
    traceSelection.selectPhase(phaseId)
    setActiveTab('trace')
  }, [traceSelection])

  const handleOpenPhaseDrawer = useCallback((phaseId: string) => {
    setPhaseDrawerPhaseId(phaseId)
    if (traceSelection.linkEnabled) {
      traceSelection.selectPhase(phaseId)
    }
    setActiveTab('code')
  }, [traceSelection])

  const handleTraceEventSelect = useCallback((index: number, event: CallbackEvent) => {
    traceSelection.selectEvent(event, index)
    if (!traceSelection.linkEnabled || !isErrorTraceEvent(event)) {
      return
    }
    const line = phaseLineFor(skillMarkdown, eventPhase(event))
    if (line !== null) {
      setPendingJumpLine(line)
      setActiveTab('code')
    }
  }, [skillMarkdown, traceSelection])

  const handleCompareToGolden = useCallback(async () => {
    if (!selectedSkillId || !lastRunId) {
      pushToast('Run a skill before comparing to golden.', 'info')
      return
    }
    setActiveTab('diff')
    const result = await goldenDiff.compare()
    if (result) {
      pushToast('Golden diff loaded', 'success')
    }
  }, [goldenDiff, lastRunId, pushToast, selectedSkillId])

  const handlePromoteToGolden = useCallback(async () => {
    if (!selectedSkillId || !lastRunId) {
      pushToast('Run a skill before promoting a golden baseline.', 'info')
      return
    }
    const baseline = await goldenDiff.promote()
    if (baseline) {
      await mutateSkills()
      await mutateSkillDetail()
      pushToast(`Promoted ${baseline.id} to golden`, 'success')
    }
  }, [goldenDiff, lastRunId, mutateSkillDetail, mutateSkills, pushToast, selectedSkillId])

  const handleReplayHistoryRun = useCallback((detail: RunDetail) => {
    if (!detail.input_data) {
      pushToast('This run has no saved input data to replay.', 'error')
      return
    }
    setPlaygroundPayload(detail.input_data)
    void handleRun(detail.input_data)
    pushToast(`Replaying ${detail.metadata.run_id}`, 'info')
  }, [handleRun, pushToast])

  const handleCompareHistoryRun = useCallback(async (runId: string) => {
    if (!selectedSkillId) {
      return
    }
    setLastRunId(runId)
    setActiveTab('diff')
    const result = await goldenDiff.compare(null, runId)
    if (result) {
      pushToast(`Loaded diff for ${runId}`, 'success')
    }
  }, [goldenDiff, pushToast, selectedSkillId])

  const handleApplyPhaseForm = useCallback(() => {
    const yamlBlock = phaseForm.buildYamlBlock()
    if (!phaseForm.phase || !yamlBlock) {
      pushToast('Phase block is not available for this node.', 'error')
      return
    }
    phaseSync.applyPhaseBlock(phaseForm.phase.phaseId, yamlBlock)
    setPhaseDrawerPhaseId(phaseForm.data.name)
    pushToast(`Applied phase ${phaseForm.data.name}`, 'success')
  }, [phaseForm, phaseSync, pushToast])

  const handleOpenBatchRun = useCallback(async (runId: string) => {
    if (!selectedSkillId) {
      return
    }
    try {
      const detail = await api.get<RunDetail>(`/skills/${selectedSkillId}/runs/${runId}`)
      setTraceLogs(detail.data.events)
      setRunStatus(
        detail.data.metadata.status === 'success'
          ? 'success'
          : detail.data.metadata.status === 'failed' ? 'error' : 'running',
      )
      setLastRunId(runId)
      setActiveTab('trace')
    } catch (error) {
      pushToast(errorMessage(error), 'error')
    }
  }, [pushToast, selectedSkillId])

  const canRun = Boolean(selectedSkillId && currentManifest && playgroundValid)

  const commandActions = useMemo<CommandAction[]>(() => [
    {
      id: 'save',
      label: 'Save and lint',
      description: 'Persist SKILL.md and run backend lint validation.',
      hotkey: 'mod+s',
      disabled: !selectedSkillId,
      run: () => void handleSave(),
    },
    {
      id: 'run',
      label: 'Run skill',
      description: 'Start a run with the current playground input.',
      hotkey: 'mod+enter',
      disabled: !canRun || runStatus === 'running',
      run: () => void handleRun(),
    },
    {
      id: 'new-skill',
      label: 'New skill',
      description: 'Open the Skill Creator wizard.',
      hotkey: 'mod+n',
      run: () => setCreatorOpen(true),
    },
    {
      id: 'switch-skill',
      label: 'Switch skill',
      description: 'Open quick skill search.',
      hotkey: 'mod+p',
      run: () => setSkillPaletteOpen(true),
    },
    {
      id: 'toggle-dark-mode',
      label: 'Toggle dark mode',
      description: 'Switch Studio between light and dark themes.',
      run: () => setIsDarkMode((current) => !current),
    },
    {
      id: 'open-cli',
      label: 'Open CLI',
      description: 'Start an embedded CLI session for the selected skill.',
      disabled: !selectedSkillId,
      run: () => void openTerminal(),
    },
    {
      id: 'show-history',
      label: 'Show run history',
      description: 'Open the History tab for previous runs.',
      disabled: !selectedSkillId,
      run: () => setActiveTab('history'),
    },
    {
      id: 'show-shortcuts',
      label: 'Show keyboard shortcuts',
      description: 'Open the shortcut cheat sheet.',
      hotkey: '?',
      run: () => setCheatSheetOpen(true),
    },
  ], [canRun, handleRun, handleSave, openTerminal, runStatus, selectedSkillId, setIsDarkMode])

  const closeTopLayer = useCallback(() => {
    if (cheatSheetOpen) {
      setCheatSheetOpen(false)
      return
    }
    if (commandPaletteOpen) {
      setCommandPaletteOpen(false)
      return
    }
    if (skillPaletteOpen) {
      setSkillPaletteOpen(false)
      return
    }
    if (creatorOpen) {
      setCreatorOpen(false)
      return
    }
    if (phaseDrawerPhaseId !== null) {
      setPhaseDrawerPhaseId(null)
      return
    }
    if (selectedPromptIndex !== null) {
      setSelectedPromptIndex(null)
    }
  }, [
    cheatSheetOpen,
    commandPaletteOpen,
    creatorOpen,
    phaseDrawerPhaseId,
    selectedPromptIndex,
    skillPaletteOpen,
  ])

  useEffect(() => {
    const unregister = [
      register('mod+s', () => void handleSave()),
      register('mod+enter', () => {
        if (canRun && runStatus !== 'running') {
          void handleRun()
        }
      }),
      register('mod+n', () => setCreatorOpen(true)),
      register('mod+k', () => setCommandPaletteOpen(true)),
      register('mod+p', () => setSkillPaletteOpen(true)),
      register('?', () => setCheatSheetOpen(true)),
      register('escape', closeTopLayer, { allowInInputs: true }),
    ]
    return () => unregister.forEach((item) => item())
  }, [canRun, closeTopLayer, handleRun, handleSave, register, runStatus])

  const promptEvent = selectedPromptIndex === null ? null : findPromptEvent(traceLogs, selectedPromptIndex)
  const currentGraphSkill = currentManifest ? graphSkill(currentManifest) : null
  const currentSkill = skills.find((skill) => skill.id === selectedSkillId)
  const inputSummary = currentManifest
    ? manifestInputs.length > 0 ? `${manifestInputs.length} fields` : 'raw JSON'
    : 'loading'
  const canDiffRun = Boolean(selectedSkillId && lastRunId && runStatus !== 'running')
  return (
    <div className="flex h-screen w-full bg-gray-50 dark:bg-slate-950 font-sans text-slate-800 dark:text-slate-200">
      <SkillSidebar
        skills={skills}
        selectedSkillId={selectedSkillId}
        activeTab={activeTab}
        skillListError={skillListError}
        isDarkMode={isDarkMode}
        onSelectSkill={handleSelectSkill}
        onToggleDarkMode={() => setIsDarkMode((current) => !current)}
        onOpenCreator={() => setCreatorOpen(true)}
        onOpenSettings={() => setActiveTab('settings')}
        onForkSkill={handleForkSkill}
      />
      <div className="flex h-full flex-1 flex-col overflow-hidden">
        {!selectedSkillId ? (
          <WelcomeScreen
            skills={skills}
            recentSkills={recentSkills}
            onSelectSkill={handleSelectSkill}
            onImportSkill={handleImportSkill}
          />
        ) : (
          <>
            <HeaderBar
              selectedSkillId={selectedSkillId}
              inputSummary={inputSummary}
              inputPanel={currentManifest ? (
                <InputPlayground
                  skillId={selectedSkillId}
                  inputs={manifestInputs}
                  runStatus={runStatus}
                  onRun={(values) => void handleRun(values)}
                  onPayloadChange={handlePlaygroundPayloadChange}
                  pushToast={pushToast}
                />
              ) : (
                <div className="rounded-md border border-gray-200 bg-white p-4 text-sm text-gray-500 shadow-xl dark:border-slate-800 dark:bg-slate-900 dark:text-gray-400">
                  Loading inputs...
                </div>
              )}
              canRun={canRun}
              isArtifactsMenuOpen={isArtifactsMenuOpen}
              lintStatus={lintStatus}
              runStatus={runStatus}
              dirty={workspaceIsDirty}
              onToggleArtifactsMenu={() => setIsArtifactsMenuOpen((open) => !open)}
              onLint={() => void handleLint()}
              onSave={() => void handleSave()}
              onOpenTerminal={() => void openTerminal()}
              onRun={() => void handleRun()}
            />
            <DirtyBar onSave={() => void handleSave()} />
            <div className="flex flex-1 overflow-hidden">
              <GraphCanvas
                currentSkillName={currentSkill?.name ?? 'Graph'}
                skillDetailError={skillDetailError}
                nodes={nodes}
                edges={edges}
                isDarkMode={isDarkMode}
                selectedPhaseId={traceSelection.linkEnabled ? traceSelection.selectedPhaseId : null}
                onNodesChange={onNodesChange}
                onEdgesChange={onEdgesChange}
                onConnect={onConnect}
                onPhaseSelect={handleGraphPhaseSelect}
                onPhaseDoubleClick={handleOpenPhaseDrawer}
              />
              <RightPanel
                activeTab={activeTab}
                isDarkMode={isDarkMode}
                activeFile={workspaceActiveFile}
                files={workspaceFiles}
                dirty={workspaceDirty}
                selectedSkillId={selectedSkillId}
                lintErrors={lintErrors}
                traceLogs={traceLogs}
                diffResult={goldenDiff.result}
                diffLoading={goldenDiff.loading}
                diffError={goldenDiff.error}
                canDiffRun={canDiffRun}
                batchInputs={batchRun.inputs}
                selectedBatchInputIds={batchRun.selectedInputIds}
                batchStatus={batchRun.batchStatus}
                batchInputsLoading={batchRun.inputsLoading}
                batchRunning={batchRun.batchRunning}
                batchError={batchRun.batchError}
                terminalSession={terminalSession}
                terminalStatus={terminalStatus}
                currentGraphSkill={currentGraphSkill}
                apiKeys={apiKeys}
                onActiveTabChange={setActiveTab}
                onEditorMount={handleEditorMount}
                onActiveFileChange={setWorkspaceActiveFile}
                onFileChange={updateWorkspaceFile}
                onJumpToLine={jumpToLine}
                onCopyErrors={copyErrorToClipboard}
                onSelectPrompt={setSelectedPromptIndex}
                onCompareToGolden={handleCompareToGolden}
                onPromoteToGolden={handlePromoteToGolden}
                onReplayRun={handleReplayHistoryRun}
                onCompareHistoryRun={handleCompareHistoryRun}
                onToggleBatchInput={batchRun.toggleInput}
                onRunBatch={() => void batchRun.runBatch()}
                onRefreshBatchInputs={() => void batchRun.refreshInputs()}
                onOpenBatchRun={(runId) => void handleOpenBatchRun(runId)}
                selectedTracePhaseId={traceSelection.selectedPhaseId}
                selectedTraceEventId={traceSelection.selectedEventId}
                traceLinkEnabled={traceSelection.linkEnabled}
                onTraceLinkEnabledChange={traceSelection.setLinkEnabled}
                onTraceEventSelect={handleTraceEventSelect}
                onTerminalStatusChange={setTerminalStatus}
                onApiKeyChange={handleApiKeyChange}
                pushToast={pushToast}
              />
            </div>
          </>
        )}
      </div>
      <PromptInspector promptEvent={promptEvent} onClose={() => setSelectedPromptIndex(null)} />
      <SkillCreatorWizard
        open={creatorOpen}
        onClose={() => setCreatorOpen(false)}
        onCreated={handleSkillCreated}
        pushToast={pushToast}
      />
      <DraftRestoreModal
        open={restorePromptSkillId === selectedSkillId}
        skillId={selectedSkillId}
        draft={storedDraft}
        baseHash={draftBaseHash}
        onRestore={handleRestoreDraft}
        onDiscard={handleDiscardDraft}
        onCancel={() => {
          if (selectedSkillId) {
            setDismissedDraftSkillId(selectedSkillId)
          }
          setRestorePromptSkillId(null)
        }}
      />
      <PhaseDrawer
        open={phaseDrawerPhaseId !== null && phaseForm.phase !== null}
        phaseId={phaseDrawerPhaseId}
        data={phaseForm.data}
        availableTools={phaseForm.availableTools}
        dirty={phaseForm.dirty}
        onChange={phaseForm.setField}
        onApply={handleApplyPhaseForm}
        onReset={phaseForm.reset}
        onClose={() => setPhaseDrawerPhaseId(null)}
      />
      <CommandPalette
        open={commandPaletteOpen}
        actions={commandActions}
        onClose={() => setCommandPaletteOpen(false)}
      />
      <SkillPalette
        open={skillPaletteOpen}
        skills={skills}
        selectedSkillId={selectedSkillId}
        onSelect={handleSelectSkill}
        onClose={() => setSkillPaletteOpen(false)}
      />
      <ShortcutsCheatSheet
        open={cheatSheetOpen}
        onClose={() => setCheatSheetOpen(false)}
      />
      <ToastStack toasts={toasts} />
    </div>
  )
}
