import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import type { ComponentProps } from 'react'
import useSWR from 'swr'
import { AxiosError } from 'axios'
import { ReactFlow, MiniMap, Controls, Background, useNodesState, useEdgesState, addEdge, MarkerType } from 'reactflow'
import type { Connection, Edge, Node, NodeTypes } from 'reactflow'
import 'reactflow/dist/style.css'
import Editor from '@monaco-editor/react'
import yaml from 'js-yaml'
import { FitAddon } from 'xterm-addon-fit'
import { Terminal as XTermTerminal } from 'xterm'
import 'xterm/css/xterm.css'
import {
  AlertCircle,
  CheckCircle,
  ChevronRight,
  Copy,
  FileText,
  FolderOpen,
  Hash,
  HardDrive,
  MessageSquare,
  Play,
  Save,
  Settings,
  Terminal as TerminalIcon,
  X,
} from 'lucide-react'
import { AgentNode, SubgraphNode } from './CustomNodes'
import type { StudioNodeData } from './CustomNodes'
import { api, fetcher, wsUrl } from './api/client'
import type {
  CallbackEvent,
  ErrorResponse,
  GraphSkillDef,
  JsonObject,
  JsonValue,
  LintError,
  LintResult,
  RunMetadata,
  RunRequest,
  SkillDetail,
  SkillManifest,
  SkillSummary,
  StudioGlobalEvent,
  TerminalSession,
} from './api/types'

const nodeTypes = {
  subgraph: SubgraphNode,
  agent: AgentNode,
} satisfies NodeTypes

type ActiveTab = 'code' | 'trace' | 'terminal' | 'settings'
type LintStatus = 'idle' | 'checking' | 'passed' | 'failed'
type RunStatus = 'idle' | 'running' | 'success' | 'error'
type ToastKind = 'info' | 'success' | 'error'
type EditorOnMount = NonNullable<ComponentProps<typeof Editor>['onMount']>
type MonacoEditor = Parameters<EditorOnMount>[0]
type MonacoApi = Parameters<EditorOnMount>[1]
type TerminalStatus = 'idle' | 'connecting' | 'open' | 'closed' | 'error'

interface Toast {
  id: string
  kind: ToastKind
  message: string
}

interface EditorDraft {
  skillId: string | null
  code: string
  dirty: boolean
}

interface LintOverride {
  skillId: string
  status: LintStatus
  errors: LintError[]
}

interface GraphBuildResult {
  nodes: Node<StudioNodeData>[]
  edges: Edge[]
}

interface VisualPhase {
  id: string
  name: string
  mode: string
  role: string | null
  dependsOn: string[]
  subgraph: string | null
}

interface TerminalPanelProps {
  session: TerminalSession
  onStatusChange: (status: TerminalStatus) => void
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function isJsonObject(value: unknown): value is JsonObject {
  if (!isRecord(value)) {
    return false
  }
  return Object.values(value).every(isJsonValue)
}

function isJsonValue(value: unknown): value is JsonValue {
  if (value === null) {
    return true
  }
  if (['string', 'number', 'boolean'].includes(typeof value)) {
    return true
  }
  if (Array.isArray(value)) {
    return value.every(isJsonValue)
  }
  return isJsonObject(value)
}

function asLintErrors(value: unknown): LintError[] {
  if (!Array.isArray(value)) {
    return []
  }

  return value.flatMap((item) => {
    if (!isRecord(item) || typeof item.message !== 'string' || typeof item.error_code !== 'string') {
      return []
    }
    return [{
      line: typeof item.line === 'number' ? item.line : null,
      column: typeof item.column === 'number' ? item.column : null,
      error_code: item.error_code,
      severity: item.severity === 'warning' ? 'warning' : 'error',
      message: item.message,
      phase_name: typeof item.phase_name === 'string' ? item.phase_name : null,
    }]
  })
}

function lintErrorsFromError(error: unknown): LintError[] {
  if (!(error instanceof AxiosError)) {
    return []
  }

  const payload = error.response?.data as ErrorResponse | undefined
  const details = payload?.details
  if (!details || !isRecord(details)) {
    return []
  }
  return asLintErrors(details.errors)
}

function errorMessage(error: unknown): string {
  if (error instanceof AxiosError) {
    const payload = error.response?.data as Partial<ErrorResponse> | undefined
    return payload?.message ?? error.message
  }
  return error instanceof Error ? error.message : String(error)
}

function manifestToSkillMarkdown(manifest: SkillManifest): string {
  const frontmatter = yaml.dump(manifest, {
    lineWidth: 120,
    noRefs: true,
    sortKeys: false,
  })
  return `---\n${frontmatter}---\n\n# ${manifest.name}\n\n${manifest.description}\n`
}

function jsonText(value: JsonValue | undefined): string {
  if (value === undefined) {
    return ''
  }
  return JSON.stringify(value, null, 2)
}

function normalizeDependency(value: string | string[] | undefined): string[] {
  if (Array.isArray(value)) {
    return value
  }
  return typeof value === 'string' && value.length > 0 ? [value] : []
}

function subgraphSkillId(path: string | null): string | null {
  if (!path) {
    return null
  }
  const parts = path.split('/').filter(Boolean)
  const last = parts.at(-1)
  if (!last) {
    return null
  }
  return last.endsWith('.md') ? last.slice(0, -3) : last
}

function phasesFromManifest(manifest: SkillManifest): VisualPhase[] {
  if (manifest.type === 'graph') {
    return manifest.phases.map((phase) => ({
      id: phase.name,
      name: phase.name,
      mode: phase.mode,
      role: phase.mode === 'llm' ? phase.llm_role : null,
      dependsOn: normalizeDependency(phase.depends_on),
      subgraph: phase.subgraph ?? null,
    }))
  }

  if (manifest.type === 'agent') {
    return [{
      id: manifest.name,
      name: manifest.name,
      mode: 'llm',
      role: manifest.agent_profile.llm_role,
      dependsOn: [],
      subgraph: null,
    }]
  }

  return [{
    id: manifest.name,
    name: manifest.name,
    mode: 'persona',
    role: 'Persona',
    dependsOn: [],
    subgraph: null,
  }]
}

function inputLabel(manifest: SkillManifest): string {
  if (manifest.type !== 'graph') {
    return 'Input: runtime'
  }
  const names = manifest.io.inputs.map((input) => input.name)
  return `Input: ${names.length > 0 ? names.join(', ') : 'None'}`
}

function outputLabel(manifest: SkillManifest): string {
  if (manifest.type !== 'graph') {
    return 'Output: result'
  }
  const names = manifest.io.outputs.map((output) => output.name)
  return `Output: ${names.length > 0 ? names.join(', ') : 'None'}`
}

function graphSkill(manifest: SkillManifest): GraphSkillDef | null {
  return manifest.type === 'graph' ? manifest : null
}

function buildGraph(
  manifest: SkillManifest,
  expandedSubgraphs: Set<string>,
  nestedManifests: Record<string, SkillManifest>,
  onToggleSubgraph: (phase: VisualPhase) => void,
): GraphBuildResult {
  const nodes: Node<StudioNodeData>[] = [{
    id: 'input',
    type: 'input',
    data: { label: inputLabel(manifest) },
    position: { x: 240, y: 40 },
    style: {
      background: '#f8fafc',
      border: '1px solid #cbd5e1',
      borderRadius: 8,
      color: '#475569',
      fontWeight: 700,
      minWidth: 220,
      padding: 10,
      textAlign: 'center',
    },
  }]
  const edges: Edge[] = []
  const phases = phasesFromManifest(manifest)
  const leafNodes = new Set<string>()
  let y = 150

  phases.forEach((phase, index) => {
    const isSubgraph = Boolean(phase.subgraph)
    const isExpanded = expandedSubgraphs.has(phase.id)
    nodes.push({
      id: phase.id,
      type: isSubgraph ? 'subgraph' : 'agent',
      data: {
        label: phase.name,
        mode: phase.mode,
        role: phase.role,
        subgraphPath: phase.subgraph,
        isExpanded,
        onToggleExpand: isSubgraph ? () => onToggleSubgraph(phase) : undefined,
      },
      position: { x: 240, y },
    })

    const dependencies = phase.dependsOn.length > 0
      ? phase.dependsOn
      : index === 0
        ? ['input']
        : [phases[index - 1].id]

    dependencies.forEach((dependency) => {
      edges.push({
        id: `e-${dependency}-${phase.id}`,
        source: dependency,
        target: phase.id,
        animated: true,
        markerEnd: { type: MarkerType.ArrowClosed },
        style: { stroke: '#94a3b8', strokeWidth: 2 },
      })
    })

    leafNodes.add(phase.id)
    dependencies.forEach((dependency) => leafNodes.delete(dependency))

    if (isExpanded && phase.subgraph) {
      const nestedId = subgraphSkillId(phase.subgraph)
      const nested = nestedId ? nestedManifests[nestedId] : undefined
      const nestedPhases = nested ? phasesFromManifest(nested) : []
      let childY = y + 105
      let previousChild = phase.id

      nestedPhases.forEach((child) => {
        const childId = `${phase.id}::${child.id}`
        nodes.push({
          id: childId,
          type: 'agent',
          data: {
            label: child.name,
            mode: child.mode,
            role: child.role,
          },
          position: { x: 560, y: childY },
          style: { opacity: 0.9 },
        })
        edges.push({
          id: `e-${previousChild}-${childId}`,
          source: previousChild,
          target: childId,
          animated: true,
          markerEnd: { type: MarkerType.ArrowClosed },
          style: { stroke: '#a78bfa', strokeDasharray: '5 5' },
        })
        previousChild = childId
        childY += 115
      })

      if (nestedPhases.length > 0) {
        leafNodes.delete(phase.id)
        leafNodes.add(previousChild)
      }
    }

    y += isExpanded ? 230 : 140
  })

  nodes.push({
    id: 'output',
    type: 'output',
    data: { label: outputLabel(manifest) },
    position: { x: 240, y },
    style: {
      background: '#f0fdf4',
      border: '1px solid #bbf7d0',
      borderRadius: 8,
      color: '#166534',
      fontWeight: 700,
      minWidth: 220,
      padding: 10,
      textAlign: 'center',
    },
  })

  const outputSources = leafNodes.size > 0 ? [...leafNodes] : ['input']
  outputSources.forEach((source) => {
    edges.push({
      id: `e-${source}-output`,
      source,
      target: 'output',
      animated: true,
      markerEnd: { type: MarkerType.ArrowClosed },
      style: { stroke: '#94a3b8', strokeWidth: 2 },
    })
  })

  return { nodes, edges }
}

function eventPhase(event: CallbackEvent): string {
  return event.phase_name ?? event.current_phase ?? event.run_id ?? 'system'
}

function tokenText(event: CallbackEvent): string | null {
  if (typeof event.input_tokens === 'number' || typeof event.output_tokens === 'number') {
    return `${event.input_tokens ?? 0}/${event.output_tokens ?? 0}`
  }
  return null
}

function eventMessage(event: CallbackEvent): string {
  switch (event.event_type) {
    case 'phase_start':
      return `Phase started: ${eventPhase(event)}`
    case 'phase_end':
      return `Phase finished: ${eventPhase(event)}`
    case 'prompt_captured':
      return `Prompt captured${typeof event.template_source === 'string' ? ` from ${event.template_source}` : ''}`
    case 'llm_call':
      return 'LLM call completed'
    case 'finish_task':
      return typeof event.reasoning === 'string' ? event.reasoning : 'Task finished'
    case 'run_ended':
      return `Run ended: ${event.status ?? 'completed'}`
    case 'internal_error':
      return typeof event.error_message === 'string' ? event.error_message : 'Internal error'
    default:
      return event.event_type
  }
}

function eventColor(eventType: string): string {
  if (eventType === 'phase_start') {
    return 'bg-blue-500'
  }
  if (eventType === 'phase_end' || eventType === 'run_ended') {
    return 'bg-green-500'
  }
  if (eventType === 'llm_call' || eventType === 'prompt_captured') {
    return 'bg-violet-500'
  }
  if (eventType === 'internal_error' || eventType === 'validation_fail') {
    return 'bg-red-500'
  }
  return 'bg-slate-400'
}

function findPromptEvent(events: CallbackEvent[], selectedIndex: number): CallbackEvent | null {
  const selected = events[selectedIndex]
  if (!selected) {
    return null
  }
  if (selected.event_type === 'prompt_captured') {
    return selected
  }

  for (let index = selectedIndex; index >= 0; index -= 1) {
    const candidate = events[index]
    if (candidate.event_type === 'prompt_captured' && eventPhase(candidate) === eventPhase(selected)) {
      return candidate
    }
  }
  return selected.event_type === 'llm_call' ? selected : null
}

function newToastId(): string {
  return typeof crypto !== 'undefined' && 'randomUUID' in crypto
    ? crypto.randomUUID()
    : `${Date.now()}-${Math.random()}`
}

function TerminalPanel({ session, onStatusChange }: TerminalPanelProps) {
  const containerRef = useRef<HTMLDivElement | null>(null)

  useEffect(() => {
    if (!containerRef.current) {
      return undefined
    }

    const terminal = new XTermTerminal({
      cursorBlink: true,
      fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace',
      fontSize: 13,
      theme: {
        background: '#0f172a',
        foreground: '#e2e8f0',
      },
    })
    const fitAddon = new FitAddon()
    terminal.loadAddon(fitAddon)
    terminal.open(containerRef.current)
    fitAddon.fit()
    terminal.focus()

    const socket = new WebSocket(wsUrl(session.ws_url))
    socket.binaryType = 'arraybuffer'
    onStatusChange('connecting')

    socket.onopen = () => {
      onStatusChange('open')
      terminal.focus()
    }
    socket.onmessage = (message) => {
      if (typeof message.data === 'string') {
        terminal.write(message.data)
      } else if (message.data instanceof ArrayBuffer) {
        terminal.write(new Uint8Array(message.data))
      }
    }
    socket.onerror = () => onStatusChange('error')
    socket.onclose = () => onStatusChange('closed')

    const dataDisposable = terminal.onData((data) => {
      if (socket.readyState === WebSocket.OPEN) {
        socket.send(data)
      }
    })
    const resize = () => fitAddon.fit()
    window.addEventListener('resize', resize)

    return () => {
      window.removeEventListener('resize', resize)
      dataDisposable.dispose()
      socket.close()
      terminal.dispose()
    }
  }, [onStatusChange, session.ws_url])

  return <div ref={containerRef} className="h-full w-full bg-slate-950 p-2" />
}

export default function App() {
  const { data: skillList, error: skillListError } = useSWR<SkillSummary[]>('/skills', fetcher)
  const skills = useMemo(() => skillList ?? [], [skillList])
  const [activeSkillId, setActiveSkillId] = useState<string | null>(null)
  const defaultSkillId = useMemo(() => {
    if (skills.length === 0) {
      return null
    }
    return (skills.find((skill) => skill.id === 'text-segmentation') ?? skills[0]).id
  }, [skills])
  const selectedSkillId = activeSkillId ?? defaultSkillId
  const {
    data: skillDetail,
    error: skillDetailError,
    mutate: mutateSkillDetail,
  } = useSWR<SkillDetail>(selectedSkillId ? `/skills/${selectedSkillId}` : null, fetcher)

  const [nodes, setNodes, onNodesChange] = useNodesState<StudioNodeData>([])
  const [edges, setEdges, onEdgesChange] = useEdgesState([])
  const [editorDraft, setEditorDraft] = useState<EditorDraft>({ skillId: null, code: '', dirty: false })
  const [lintOverride, setLintOverride] = useState<LintOverride | null>(null)
  const [runStatus, setRunStatus] = useState<RunStatus>('idle')
  const [activeTab, setActiveTab] = useState<ActiveTab>('code')
  const [inputPath, setInputPath] = useState('workspaces/default/inputs/test.json')
  const [outputPath, setOutputPath] = useState('workspaces/default/outputs/result.md')
  const [pasteJson, setPasteJson] = useState('')
  const [isArtifactsMenuOpen, setIsArtifactsMenuOpen] = useState(false)
  const [apiKeys, setApiKeys] = useState({ openai: '', anthropic: '', gemini: '' })
  const [traceLogs, setTraceLogs] = useState<CallbackEvent[]>([])
  const [expandedSubgraphs, setExpandedSubgraphs] = useState<Set<string>>(new Set())
  const [nestedManifests, setNestedManifests] = useState<Record<string, SkillManifest>>({})
  const [selectedPromptIndex, setSelectedPromptIndex] = useState<number | null>(null)
  const [terminalSession, setTerminalSession] = useState<TerminalSession | null>(null)
  const [terminalStatus, setTerminalStatus] = useState<TerminalStatus>('idle')
  const [toasts, setToasts] = useState<Toast[]>([])
  const editorRef = useRef<MonacoEditor | null>(null)
  const monacoRef = useRef<MonacoApi | null>(null)
  const runWsRef = useRef<WebSocket | null>(null)

  const pushToast = useCallback((message: string, kind: ToastKind = 'info') => {
    const id = newToastId()
    setToasts((items) => [...items, { id, kind, message }])
    window.setTimeout(() => {
      setToasts((items) => items.filter((item) => item.id !== id))
    }, 4500)
  }, [])

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
      ? buildGraph(skillDetail.manifest, expandedSubgraphs, nestedManifests, toggleSubgraph)
      : { nodes: [], edges: [] }
  ), [expandedSubgraphs, nestedManifests, skillDetail, toggleSubgraph])

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

      const event: StudioGlobalEvent = { type: 'skill_changed', skill_id: parsed.skill_id }
      pushToast(`Skill changed: ${event.skill_id}`, 'info')
      if (event.skill_id === selectedSkillId) {
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

  const handleSelectSkill = useCallback((skillId: string) => {
    setActiveSkillId(skillId)
    setExpandedSubgraphs(new Set())
    setNestedManifests({})
    setLintOverride(null)
    setRunStatus('idle')
    setTraceLogs([])
    setSelectedPromptIndex(null)
    setActiveTab('code')
  }, [])

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

  const handleRun = useCallback(async () => {
    if (!selectedSkillId) {
      return
    }

    if (pasteJson.trim().length > 0) {
      try {
        const parsed: unknown = JSON.parse(pasteJson)
        if (!isJsonObject(parsed)) {
          pushToast('Run JSON must be an object', 'error')
          return
        }
      } catch {
        pushToast('Run JSON is invalid', 'error')
        return
      }
    }

    setRunStatus('running')
    setActiveTab('trace')
    setTraceLogs([])
    setSelectedPromptIndex(null)
    runWsRef.current?.close()

    const request: RunRequest = {
      input_data: pasteJson.trim().length > 0 ? null : {},
      paste_json: pasteJson.trim().length > 0 ? pasteJson : null,
    }

    try {
      const response = await api.post<RunMetadata>(`/skills/${selectedSkillId}/runs`, request)
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
      socket.onerror = () => {
        setRunStatus('error')
        pushToast('Run WebSocket disconnected', 'error')
      }
    } catch (error) {
      setRunStatus('error')
      pushToast(errorMessage(error), 'error')
    }
  }, [pasteJson, pushToast, selectedSkillId])

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

  const promptEvent = selectedPromptIndex === null ? null : findPromptEvent(traceLogs, selectedPromptIndex)
  const currentManifest = skillDetail?.manifest
  const currentGraphSkill = currentManifest ? graphSkill(currentManifest) : null
  const currentSkill = skills.find((skill) => skill.id === selectedSkillId)

  return (
    <div className="flex h-screen w-full bg-gray-50 font-sans text-slate-800">
      <div className="z-10 flex w-64 shrink-0 flex-col border-r border-gray-200 bg-white">
        <div className="flex items-center gap-2 border-b border-gray-200 p-4 text-lg font-bold">
          <Settings className="h-5 w-5 text-sky-600" />
          Skill Studio
        </div>

        <div className="flex-1 overflow-y-auto p-4">
          <h3 className="mb-3 text-xs font-semibold uppercase text-gray-400">Skills</h3>
          {skillListError ? (
            <div className="rounded border border-red-200 bg-red-50 p-3 text-sm text-red-700">{errorMessage(skillListError)}</div>
          ) : (
            <ul className="space-y-2">
              {skills.map((skill) => (
                <li key={skill.id}>
                  <button
                    type="button"
                    onClick={() => handleSelectSkill(skill.id)}
                    className={`flex w-full items-center gap-2 rounded-md border p-2 text-left text-sm font-medium transition-colors ${
                      selectedSkillId === skill.id
                        ? 'border-sky-100 bg-sky-50 text-sky-700'
                        : 'border-transparent text-gray-600 hover:bg-gray-100'
                    }`}
                  >
                    <FileText className="h-4 w-4 shrink-0" />
                    <span className="truncate">{skill.name}</span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>

        <div className="border-t border-gray-200 p-4">
          <button
            type="button"
            onClick={() => setActiveTab('settings')}
            className={`flex w-full items-center justify-center gap-2 rounded-md p-2 font-medium transition-colors ${
              activeTab === 'settings' ? 'bg-gray-200 text-gray-800' : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
            }`}
          >
            <Settings className="h-4 w-4" />
            Settings
          </button>
        </div>
      </div>

      <div className="flex h-full flex-1 flex-col overflow-hidden">
        <div className="z-20 flex h-16 shrink-0 items-center justify-between border-b border-gray-200 bg-white px-6">
          <div className="relative flex items-center gap-5 text-sm">
            <button
              type="button"
              onClick={() => setIsArtifactsMenuOpen((open) => !open)}
              className="flex items-center gap-2 rounded-md border border-indigo-200 bg-indigo-50 px-3 py-1.5 font-medium text-indigo-700 transition-colors hover:bg-indigo-100"
            >
              <HardDrive className="h-4 w-4" />
              Artifacts
            </button>

            {isArtifactsMenuOpen ? (
              <div className="absolute left-0 top-10 z-50 w-[26rem] rounded-md border border-gray-200 bg-white p-4 shadow-xl">
                <h4 className="mb-3 border-b pb-2 font-bold text-gray-800">Run Input</h4>
                <div className="space-y-4">
                  <label className="block">
                    <span className="mb-1 block text-xs font-medium uppercase text-gray-500">Input Source</span>
                    <div className="flex items-center gap-2">
                      <FolderOpen className="h-4 w-4 shrink-0 text-gray-400" />
                      <input
                        type="text"
                        value={inputPath}
                        onChange={(event) => setInputPath(event.target.value)}
                        className="flex-1 rounded border border-gray-300 px-2 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
                      />
                    </div>
                  </label>

                  <label className="block">
                    <span className="mb-1 block text-xs font-medium uppercase text-gray-500">Output Destination</span>
                    <div className="flex items-center gap-2">
                      <Save className="h-4 w-4 shrink-0 text-gray-400" />
                      <input
                        type="text"
                        value={outputPath}
                        onChange={(event) => setOutputPath(event.target.value)}
                        className="flex-1 rounded border border-gray-300 px-2 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
                      />
                    </div>
                  </label>

                  <label className="block">
                    <span className="mb-1 block text-xs font-medium uppercase text-gray-500">Paste JSON</span>
                    <textarea
                      value={pasteJson}
                      onChange={(event) => setPasteJson(event.target.value)}
                      className="h-28 w-full resize-none rounded border border-gray-300 px-2 py-1.5 font-mono text-xs focus:outline-none focus:ring-2 focus:ring-indigo-500"
                      placeholder='{"chapter": "..."}'
                    />
                  </label>
                </div>
              </div>
            ) : null}

            <div className="flex flex-col text-xs text-gray-500">
              <span><span className="font-semibold">In:</span> {inputPath.split('/').at(-1)}</span>
              <span><span className="font-semibold">Out:</span> {outputPath.split('/').at(-1)}</span>
            </div>
          </div>

          <div className="flex items-center gap-3">
            <button
              type="button"
              onClick={handleLint}
              disabled={!selectedSkillId || lintStatus === 'checking'}
              className="flex items-center gap-2 rounded-md border border-gray-300 bg-white px-4 py-1.5 font-medium text-gray-700 transition-colors hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {lintStatus === 'checking' ? 'Linting...' : 'Lint'}
              {lintStatus === 'passed' ? <CheckCircle className="h-4 w-4 text-green-500" /> : null}
              {lintStatus === 'failed' ? <AlertCircle className="h-4 w-4 text-red-500" /> : null}
            </button>

            <button
              type="button"
              onClick={() => void handleSave()}
              disabled={!selectedSkillId || lintStatus === 'checking'}
              className="flex items-center gap-2 rounded-md border border-gray-300 bg-white px-4 py-1.5 font-medium text-gray-700 transition-colors hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-60"
            >
              <Save className="h-4 w-4" />
              Save
            </button>

            <button
              type="button"
              onClick={() => void openTerminal()}
              disabled={!selectedSkillId}
              className="flex items-center gap-2 rounded-md border border-emerald-200 bg-emerald-50 px-4 py-1.5 font-medium text-emerald-700 transition-colors hover:bg-emerald-100 disabled:cursor-not-allowed disabled:opacity-60"
            >
              <TerminalIcon className="h-4 w-4" />
              Open CLI
            </button>

            <button
              type="button"
              onClick={() => void handleRun()}
              disabled={!selectedSkillId || runStatus === 'running'}
              className="flex items-center gap-2 rounded-md bg-sky-600 px-4 py-1.5 font-medium text-white transition-colors hover:bg-sky-700 disabled:cursor-not-allowed disabled:bg-sky-300"
            >
              <Play className="h-4 w-4" />
              {runStatus === 'running' ? 'Running...' : 'Run'}
            </button>
          </div>
        </div>

        <div className="flex flex-1 overflow-hidden">
          <div className="relative flex-1 border-r border-gray-200 bg-slate-50">
            <div className="absolute left-4 top-4 z-10 rounded-md border border-gray-200 bg-white px-3 py-1.5 text-sm font-semibold text-gray-700 shadow-sm">
              {currentSkill?.name ?? 'Graph'}
            </div>
            {skillDetailError ? (
              <div className="absolute inset-0 flex items-center justify-center p-8">
                <div className="rounded-md border border-red-200 bg-red-50 p-4 text-sm text-red-700">{errorMessage(skillDetailError)}</div>
              </div>
            ) : (
              <ReactFlow
                nodes={nodes}
                edges={edges}
                nodeTypes={nodeTypes}
                onNodesChange={onNodesChange}
                onEdgesChange={onEdgesChange}
                onConnect={onConnect}
                fitView
                minZoom={0.4}
              >
                <Controls />
                <MiniMap />
                <Background gap={12} size={1} />
              </ReactFlow>
            )}
          </div>

          <div className="z-10 flex w-[520px] flex-col bg-white">
            <div className="flex shrink-0 border-b border-gray-200">
              {([
                ['code', FileText, 'SKILL.md'],
                ['trace', MessageSquare, 'Trace'],
                ['terminal', TerminalIcon, 'CLI'],
              ] as const).map(([tab, Icon, label]) => (
                <button
                  key={tab}
                  type="button"
                  className={`flex flex-1 items-center justify-center gap-2 py-3 text-sm font-medium ${
                    activeTab === tab ? 'border-b-2 border-sky-600 text-sky-600' : 'text-gray-500 hover:text-gray-700'
                  }`}
                  onClick={() => setActiveTab(tab)}
                >
                  <Icon className="h-4 w-4" />
                  {label}
                </button>
              ))}
            </div>

            <div className="flex-1 overflow-hidden">
              {activeTab === 'settings' ? (
                <div className="h-full overflow-y-auto bg-gray-50 p-6">
                  <h2 className="mb-6 text-xl font-bold text-gray-800">Settings</h2>
                  <div className="rounded-md border border-gray-200 bg-white p-5 shadow-sm">
                    <h3 className="mb-4 border-b pb-2 text-sm font-bold uppercase text-gray-700">LLM API Keys</h3>
                    <div className="space-y-4">
                      {([
                        ['openai', 'OpenAI API Key', 'sk-...'],
                        ['anthropic', 'Anthropic API Key', 'sk-ant-...'],
                        ['gemini', 'Google Gemini API Key', 'AIza...'],
                      ] as const).map(([key, label, placeholder]) => (
                        <label key={key} className="block">
                          <span className="mb-1 block text-sm font-medium text-gray-700">{label}</span>
                          <input
                            type="password"
                            value={apiKeys[key]}
                            onChange={(event) => setApiKeys((current) => ({ ...current, [key]: event.target.value }))}
                            className="w-full rounded-md border border-gray-300 px-3 py-2 focus:outline-none focus:ring-2 focus:ring-sky-500"
                            placeholder={placeholder}
                          />
                        </label>
                      ))}
                    </div>
                  </div>
                </div>
              ) : null}

              {activeTab === 'code' ? (
                <div className="flex h-full flex-col">
                  {lintErrors.length > 0 ? (
                    <div className="shrink-0 border-b border-red-200 bg-red-50 p-3 text-sm text-red-700">
                      <div className="mb-2 flex items-start gap-2 font-semibold">
                        <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
                        Manifest validation failed
                      </div>
                      <div className="max-h-36 space-y-2 overflow-y-auto">
                        {lintErrors.map((error, index) => (
                          <button
                            key={`${error.error_code}-${error.line ?? 'none'}-${index}`}
                            type="button"
                            onClick={() => jumpToLine(error.line)}
                            className="block w-full rounded border border-red-200 bg-white px-2 py-1 text-left hover:bg-red-50"
                          >
                            <span className="font-mono text-xs text-red-500">
                              {error.line ? `Line ${error.line}` : 'No line'} / {error.error_code}
                            </span>
                            <span className="ml-2">{error.message}</span>
                          </button>
                        ))}
                      </div>
                      <button
                        type="button"
                        onClick={() => copyErrorToClipboard(lintErrors.map((error) => error.message).join('\n'))}
                        className="mt-2 flex items-center gap-1 rounded border border-red-200 bg-white px-2 py-1 text-xs text-red-600 hover:bg-red-50"
                      >
                        <Copy className="h-3 w-3" />
                        Copy
                      </button>
                    </div>
                  ) : null}

                  <div className="flex-1">
                    <Editor
                      height="100%"
                      defaultLanguage="markdown"
                      value={skillCode}
                      onMount={handleEditorMount}
                      onChange={(value) => {
                        setEditorDraft({ skillId: selectedSkillId, code: value ?? '', dirty: true })
                      }}
                      options={{
                        minimap: { enabled: false },
                        fontSize: 13,
                        wordWrap: 'on',
                        scrollBeyondLastLine: false,
                      }}
                    />
                  </div>
                </div>
              ) : null}

              {activeTab === 'trace' ? (
                <div className="h-full overflow-y-auto bg-slate-50 p-4">
                  {traceLogs.length === 0 ? (
                    <div className="flex h-full items-center justify-center text-sm font-medium text-slate-400">
                      Waiting for run events
                    </div>
                  ) : (
                    <div>
                      <h3 className="mb-4 border-b border-gray-200 pb-2 font-bold text-gray-700">Trace Timeline</h3>
                      <div className="relative ml-3 space-y-5 border-l-2 border-gray-200">
                        {traceLogs.map((event, index) => {
                          const tokens = tokenText(event)
                          const inspectable = event.event_type === 'prompt_captured' || event.event_type === 'llm_call'
                          return (
                            <div key={`${event.timestamp}-${index}`} className="relative pl-6">
                              <div className={`absolute -left-[9px] top-1 h-4 w-4 rounded-full border-2 border-white ${eventColor(event.event_type)}`} />
                              <button
                                type="button"
                                onClick={() => inspectable && setSelectedPromptIndex(index)}
                                className={`block w-full rounded-md border p-3 text-left shadow-sm ${
                                  inspectable
                                    ? 'cursor-pointer border-violet-200 bg-white hover:border-violet-400'
                                    : 'cursor-default border-gray-200 bg-white'
                                }`}
                              >
                                <div className="mb-1 flex items-center justify-between gap-3">
                                  <span className="flex items-center gap-1 text-sm font-bold text-gray-800">
                                    {inspectable ? <MessageSquare className="h-3.5 w-3.5 text-violet-600" /> : null}
                                    {event.event_type}
                                  </span>
                                  {tokens ? (
                                    <span className="flex items-center gap-1 rounded-full bg-violet-100 px-2 py-0.5 text-xs font-medium text-violet-600">
                                      <Hash className="h-3 w-3" />
                                      {tokens}
                                    </span>
                                  ) : null}
                                </div>
                                <div className="text-xs font-medium uppercase text-gray-400">{eventPhase(event)}</div>
                                <p className="mt-1 text-sm text-gray-600">{eventMessage(event)}</p>
                                {inspectable ? (
                                  <div className="mt-2 flex items-center gap-1 text-xs font-medium text-violet-500">
                                    Inspect prompt <ChevronRight className="h-3 w-3" />
                                  </div>
                                ) : null}
                              </button>
                            </div>
                          )
                        })}
                      </div>
                    </div>
                  )}
                </div>
              ) : null}

              {activeTab === 'terminal' ? (
                <div className="flex h-full flex-col">
                  <div className="flex shrink-0 items-center justify-between border-b border-gray-200 bg-gray-50 px-3 py-2 text-xs text-gray-600">
                    <span>{terminalSession ? terminalSession.cwd : 'No CLI session'}</span>
                    <span className="font-medium">{terminalStatus}</span>
                  </div>
                  <div className="flex-1 overflow-hidden">
                    {terminalSession ? (
                      <TerminalPanel session={terminalSession} onStatusChange={setTerminalStatus} />
                    ) : (
                      <div className="flex h-full items-center justify-center text-sm text-gray-400">
                        Open a CLI session for the active skill
                      </div>
                    )}
                  </div>
                </div>
              ) : null}
            </div>

            {currentGraphSkill ? (
              <div className="shrink-0 border-t border-gray-200 bg-gray-50 px-4 py-2 text-xs text-gray-500">
                {currentGraphSkill.phases.length} phases / {currentGraphSkill.io.inputs.length} inputs / {currentGraphSkill.io.outputs.length} outputs
              </div>
            ) : null}
          </div>
        </div>
      </div>

      {promptEvent ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-8">
          <div className="flex h-[80vh] w-full max-w-5xl flex-col overflow-hidden rounded-md bg-white shadow-2xl">
            <div className="flex items-center justify-between border-b border-gray-200 bg-gray-50 px-6 py-4">
              <h3 className="flex items-center gap-2 text-lg font-bold text-gray-800">
                <MessageSquare className="h-5 w-5 text-violet-600" />
                Prompt Inspector: {eventPhase(promptEvent)}
              </h3>
              <button type="button" onClick={() => setSelectedPromptIndex(null)} className="rounded p-1 text-gray-500 hover:bg-gray-100 hover:text-gray-800">
                <X className="h-5 w-5" />
              </button>
            </div>

            <div className="grid flex-1 grid-cols-3 gap-4 overflow-hidden p-6">
              <div className="flex flex-col overflow-hidden rounded-md border border-gray-200">
                <div className="border-b border-gray-200 bg-gray-100 px-3 py-2 text-xs font-bold text-gray-600">Template Source</div>
                <pre className="flex-1 overflow-y-auto bg-gray-50 p-3 text-sm whitespace-pre-wrap">{promptEvent.template_source ?? 'inline'}</pre>
              </div>
              <div className="flex flex-col overflow-hidden rounded-md border border-gray-200">
                <div className="border-b border-gray-200 bg-gray-100 px-3 py-2 text-xs font-bold text-gray-600">Variables</div>
                <pre className="flex-1 overflow-y-auto bg-gray-50 p-3 text-sm whitespace-pre-wrap text-sky-700">{jsonText(promptEvent.variables)}</pre>
              </div>
              <div className="flex flex-col overflow-hidden rounded-md border border-violet-200">
                <div className="flex items-center gap-1 border-b border-violet-200 bg-violet-50 px-3 py-2 text-xs font-bold text-violet-700">
                  <CheckCircle className="h-3 w-3" />
                  Final Prompt
                </div>
                <pre className="flex-1 overflow-y-auto bg-white p-3 text-sm whitespace-pre-wrap text-gray-800">
                  {promptEvent.event_type === 'prompt_captured' ? jsonText(promptEvent.resolved_prompt) : jsonText(promptEvent.messages ?? undefined)}
                </pre>
              </div>
            </div>
          </div>
        </div>
      ) : null}

      <div className="fixed bottom-4 right-4 z-50 space-y-2">
        {toasts.map((toast) => (
          <div
            key={toast.id}
            className={`rounded-md border px-4 py-3 text-sm shadow-lg ${
              toast.kind === 'success'
                ? 'border-green-200 bg-green-50 text-green-800'
                : toast.kind === 'error'
                  ? 'border-red-200 bg-red-50 text-red-800'
                  : 'border-slate-200 bg-white text-slate-700'
            }`}
          >
            {toast.message}
          </div>
        ))}
      </div>
    </div>
  )
}
