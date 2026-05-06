import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { addEdge, MarkerType, useEdgesState, useNodesState } from 'reactflow'
import type { Connection } from 'reactflow'
import 'reactflow/dist/style.css'
import { GraphCanvas } from './components/GraphCanvas'
import { HeaderBar } from './components/HeaderBar'
import { PromptInspector } from './components/PromptInspector'
import { RightPanel } from './components/RightPanel'
import { SkillSidebar } from './components/SkillSidebar'
import { SkillCreatorWizard } from './components/creator/SkillCreatorWizard'
import { InputPlayground } from './components/playground/InputPlayground'
import { ToastStack } from './components/ToastStack'
import { WelcomeScreen } from './components/WelcomeScreen'
import type { EditorOnMount, MonacoApi, MonacoEditor } from './components/MonacoPanel'
import { api, wsUrl } from './api/client'
import type {
  CallbackEvent,
  JsonObject,
  RunDetail,
  LintResult,
  RunMetadata,
  RunRequest,
  SkillDetail,
  SkillManifest,
  TerminalSession,
} from './api/types'
import { useRecentSkills } from './hooks/useRecentSkills'
import { useSkills } from './hooks/useSkills'
import { useTheme } from './hooks/useTheme'
import { useToasts } from './hooks/useToasts'
import { useTraceSelection } from './hooks/useTraceSelection'
import type {
  ActiveTab,
  ApiKeyName,
  ApiKeys,
  EditorDraft,
  LintOverride,
  RunStatus,
  TerminalStatus,
  VisualPhase,
} from './types/studio'
import { errorMessage, isRecord, lintErrorsFromError } from './utils/errors'
import { buildGraph, graphSkill, subgraphSkillId } from './utils/graph'
import { manifestToSkillMarkdown } from './utils/skillMarkdown'
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
  const [editorDraft, setEditorDraft] = useState<EditorDraft>({ skillId: null, code: '', dirty: false })
  const [lintOverride, setLintOverride] = useState<LintOverride | null>(null)
  const [runStatus, setRunStatus] = useState<RunStatus>('idle')
  const [activeTab, setActiveTab] = useState<ActiveTab>('code')
  const [playgroundPayload, setPlaygroundPayload] = useState<JsonObject>({})
  const [playgroundValid, setPlaygroundValid] = useState(true)
  const [isArtifactsMenuOpen, setIsArtifactsMenuOpen] = useState(false)
  const [apiKeys, setApiKeys] = useState<ApiKeys>({ openai: '', anthropic: '', gemini: '' })
  const [traceLogs, setTraceLogs] = useState<CallbackEvent[]>([])
  const [expandedSubgraphs, setExpandedSubgraphs] = useState<Set<string>>(new Set())
  const [nestedManifests, setNestedManifests] = useState<Record<string, SkillManifest>>({})
  const [selectedPromptIndex, setSelectedPromptIndex] = useState<number | null>(null)
  const [terminalSession, setTerminalSession] = useState<TerminalSession | null>(null)
  const [terminalStatus, setTerminalStatus] = useState<TerminalStatus>('idle')
  const [creatorOpen, setCreatorOpen] = useState(false)
  const [pendingJumpLine, setPendingJumpLine] = useState<number | null>(null)
  const editorRef = useRef<MonacoEditor | null>(null)
  const monacoRef = useRef<MonacoApi | null>(null)
  const runWsRef = useRef<WebSocket | null>(null)

  const canonicalSkillCode = skillDetail ? manifestToSkillMarkdown(skillDetail.manifest) : ''
  const editorOwnsSelectedSkill = editorDraft.skillId === selectedSkillId
  const skillCode = editorOwnsSelectedSkill ? editorDraft.code : canonicalSkillCode
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

  useEffect(() => {
    const handler = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'n') {
        event.preventDefault()
        setCreatorOpen(true)
      }
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [])

  const onConnect = useCallback((params: Connection) => {
    setEdges((current) => addEdge({
      ...params,
      animated: true,
      markerEnd: { type: MarkerType.ArrowClosed },
      style: { stroke: '#94a3b8', strokeWidth: 2 },
    }, current))
  }, [setEdges])

  const handleSelectSkill = useCallback((skillId: string) => {
    setActiveSkillId(skillId)
    setExpandedSubgraphs(new Set())
    setNestedManifests({})
    setLintOverride(null)
    setRunStatus('idle')
    setTraceLogs([])
    setSelectedPromptIndex(null)
    setActiveTab('code')
    rememberSkill(skillId)
  }, [rememberSkill])

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
      const response = await api.put<SkillDetail>(`/skills/${selectedSkillId}`, { content: skillCode })
      await mutateSkillDetail(response.data, { revalidate: false })
      setLintOverride({
        skillId: selectedSkillId,
        status: response.data.lint_result?.status ?? 'passed',
        errors: response.data.lint_result?.errors ?? [],
      })
      setEditorDraft({ skillId: selectedSkillId, code: manifestToSkillMarkdown(response.data.manifest), dirty: false })
      pushToast('Saved and linted successfully', 'success')
    } catch (error) {
      const errors = lintErrorsFromError(error)
      setLintOverride({ skillId: selectedSkillId, status: 'failed', errors })
      pushToast(errorMessage(error), 'error')
    }
  }, [mutateSkillDetail, pushToast, selectedSkillId, skillCode])

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
    setSelectedPromptIndex(null)
    runWsRef.current?.close()

    const request: RunRequest = {
      input_data: values ?? playgroundPayload,
      paste_json: null,
    }

    try {
      const response = await api.post<RunMetadata>(`/skills/${selectedSkillId}/runs`, request)
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
  }, [playgroundPayload, pushToast, selectedSkillId])

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

  const handleGraphPhaseSelect = useCallback((phaseId: string) => {
    if (!traceSelection.linkEnabled) {
      return
    }
    traceSelection.selectPhase(phaseId)
    setActiveTab('trace')
  }, [traceSelection])

  const handleTraceEventSelect = useCallback((index: number, event: CallbackEvent) => {
    traceSelection.selectEvent(event, index)
    if (!traceSelection.linkEnabled || !isErrorTraceEvent(event)) {
      return
    }
    const line = phaseLineFor(skillCode, eventPhase(event))
    if (line !== null) {
      setPendingJumpLine(line)
      setActiveTab('code')
    }
  }, [skillCode, traceSelection])

  const promptEvent = selectedPromptIndex === null ? null : findPromptEvent(traceLogs, selectedPromptIndex)
  const currentGraphSkill = currentManifest ? graphSkill(currentManifest) : null
  const currentSkill = skills.find((skill) => skill.id === selectedSkillId)
  const inputSummary = currentManifest
    ? manifestInputs.length > 0 ? `${manifestInputs.length} fields` : 'raw JSON'
    : 'loading'
  const canRun = Boolean(selectedSkillId && currentManifest && playgroundValid)
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
              onToggleArtifactsMenu={() => setIsArtifactsMenuOpen((open) => !open)}
              onLint={() => void handleLint()}
              onSave={() => void handleSave()}
              onOpenTerminal={() => void openTerminal()}
              onRun={() => void handleRun()}
            />
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
              />
              <RightPanel
                activeTab={activeTab}
                isDarkMode={isDarkMode}
                skillCode={skillCode}
                lintErrors={lintErrors}
                traceLogs={traceLogs}
                terminalSession={terminalSession}
                terminalStatus={terminalStatus}
                currentGraphSkill={currentGraphSkill}
                apiKeys={apiKeys}
                onActiveTabChange={setActiveTab}
                onEditorMount={handleEditorMount}
                onDraftChange={(code) => {
                  setEditorDraft({ skillId: selectedSkillId, code, dirty: true })
                }}
                onJumpToLine={jumpToLine}
                onCopyErrors={copyErrorToClipboard}
                onSelectPrompt={setSelectedPromptIndex}
                selectedTracePhaseId={traceSelection.selectedPhaseId}
                selectedTraceEventId={traceSelection.selectedEventId}
                traceLinkEnabled={traceSelection.linkEnabled}
                onTraceLinkEnabledChange={traceSelection.setLinkEnabled}
                onTraceEventSelect={handleTraceEventSelect}
                onTerminalStatusChange={setTerminalStatus}
                onApiKeyChange={handleApiKeyChange}
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
      <ToastStack toasts={toasts} />
    </div>
  )
}
