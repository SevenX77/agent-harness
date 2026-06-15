import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import type { Connection } from "@xyflow/react"
import { toast } from "sonner"
import { ResizableHandle, ResizablePanel, ResizablePanelGroup } from "@/components/ui/resizable"
import { GraphCanvas, type SkillGraphNodeData, type SkillNodeStatus } from "@/components/GraphCanvas"
import { CopilotPanel } from "@/components/copilot/copilot-panel"
import { copilotFileActionEffects, type CopilotFileAction } from "@/components/copilot/patch-proposed-bubble"
import { PromptInspector } from "@/components/PromptInspector"
import { useCopilotContext } from "@/hooks/useCopilotContext"
import { readLintStatus } from "@/hooks/useDebouncedLint"
import { useRunStream } from "@/hooks/useRunStream"
import { useGoldenDiff } from "@/hooks/useGoldenDiff"
import { useSkills } from "@/hooks/useSkills"
import { DiffView } from "@/components/diff/DiffView"
import { WelcomePage } from "@/components/welcome/WelcomePage"
import { compileSkill, getSkillDetail, resolveRunInput, serializeSkillGraph, writeSkillFile, wsUrl, postPredictRun, startRun, resumeRun } from "@/api/client"
import { isTauriRuntime } from "@/config/runtime"
import { writeWorkspaceFile } from "@/lib/tauri"
import { errorMessage } from "@/utils/errors"
import type { CompileError } from "@/api/types"
import { connectPhaseRefs, createPhaseDraft, disconnectPhaseRefs, type NewPhaseKind } from "@/components/GraphCanvas/canvas-authoring"
import { sha256Hex } from "@/lib/hash"
import { CenterActionBar, type SkillBuildStage } from "./center-action-bar"
import { ConflictDialog } from "./ConflictDialog"
import { Header } from "./Header"
import { Panels } from "./Panels"
import { SettingsPage } from "./SettingsPage"
import { SplitEditor } from "./SplitEditor"
import { Toolbar, type PanelKind } from "./Toolbar"
import type { FileMeta } from "./file-types"
import {
  WorkspaceProvider,
  type EditorSide,
  type OpenFile,
  type SaveConflict,
  type SelectedEdge,
  type WorkspaceContextValue,
} from "./WorkspaceContext"
import { resolveWorkspaceIdentity } from "./workspace-identity"

interface WorkspaceProps {
  skillId: string | null
  onSelectSkill: (skillId: string) => void
  onCloseSkill: () => void
}

export function Workspace({ skillId, onSelectSkill, onCloseSkill }: WorkspaceProps) {
  const [navStack, setNavStack] = useState<string[]>(() => (skillId ? [skillId] : []))
  const [activePanel, setActivePanel] = useState<PanelKind | null>(skillId ? "assets" : null)
  const [copilotOpen, setCopilotOpen] = useState(Boolean(skillId))
  const currentWorkspaceSelection = navStack.at(-1) ?? null
  const currentWorkspaceIdentity = useMemo(
    () => resolveWorkspaceIdentity(currentWorkspaceSelection),
    [currentWorkspaceSelection],
  )
  const currentSkillId = currentWorkspaceIdentity.skillId
  const currentWorkspaceRoot = currentWorkspaceIdentity.workspaceRoot
  const displayNavStack = useMemo(
    () => navStack.map((item) => resolveWorkspaceIdentity(item).skillId).filter((item): item is string => Boolean(item)),
    [navStack],
  )

  useEffect(() => {
    if (skillId === null) {
      setNavStack([])
      setActivePanel(null)
      setCopilotOpen(false)
    } else {
      setNavStack([skillId])
      setActivePanel("assets")
      setCopilotOpen(true)
    }
  }, [skillId])
  const [activeFileDetails, setActiveFileDetails] = useState<Partial<Record<EditorSide, OpenFile>>>({})
  const [splitMode, setSplitMode] = useState(false)
  const [settingsOpen, setSettingsOpen] = useState(false)
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null)
  const [selectedNode, setSelectedNode] = useState<{ id: string; data: SkillGraphNodeData } | null>(null)
  const [selectedEdge, setSelectedEdge] = useState<SelectedEdge | null>(null)
  const [inFlight, setInFlight] = useState<Partial<Record<EditorSide, boolean>>>({})
  const inFlightRef = useRef<Partial<Record<EditorSide, boolean>>>({})
  const [conflict, setConflict] = useState<SaveConflict | null>(null)
  const { skillDetail, skillDetailError, mutateSkillDetail } = useSkills(currentSkillId)
  const isLoading = useMemo(() => Boolean(currentSkillId && !skillDetail && !skillDetailError), [skillDetail, skillDetailError, currentSkillId])
  const [compileStages, setCompileStages] = useState<Record<string, SkillBuildStage>>({})
  const [compileErrors, setCompileErrors] = useState<Record<string, CompileError[]>>({})
  const [runId, setRunId] = useState<string | null>(null)
  // F4: the test input selected in the i/o panel feeds Predict/Run (null = the
  // prior empty-payload behaviour). Reset when the active skill changes.
  const [selectedTestInputId, setSelectedTestInputId] = useState<string | null>(null)

  useEffect(() => {
    setRunId(null)
    setSelectedTestInputId(null)
  }, [currentSkillId])

  const updateStage = useCallback((id: string, stage: SkillBuildStage) => {
    setCompileStages((current) => ({ ...current, [id]: stage }))
  }, [])

  // F5 (trace): index of the trace event whose prompt is open in the inspector.
  const [promptIndex, setPromptIndex] = useState<number | null>(null)
  const runStream = useRunStream(runId)
  // F7: a finished run (run_ended in the stream) drives the copilot analysis bar.
  const completedRunId = runStream.events.some((event) => event.event_type === "run_ended")
    ? runId
    : null

  const statusByNodeId = useMemo(() => {
    const statuses: Record<string, SkillNodeStatus> = {}
    if (!runStream.events) return statuses
    for (const event of runStream.events) {
      const phaseName = event.phase_name || event.current_phase
      if (!phaseName) continue
      const type = event.event_type || ""
      const isError = type.includes("error") || event.status === "failed" || event.status === "error"
      if (isError) {
        statuses[phaseName] = "error"
      } else if (type === "phase_start") {
        statuses[phaseName] = "running"
      } else if (type === "phase_end") {
        statuses[phaseName] = "success"
      }
    }
    return statuses
  }, [runStream.events])

  // The currently-running phase, used to highlight/link the live trace stream.
  const activeTracePhase = useMemo(() => {
    const running = Object.entries(statusByNodeId).find(([, status]) => status === "running")
    return running?.[0] ?? null
  }, [statusByNodeId])

  // Golden compare/promote for the active run (per-node diff surfaced as an overlay).
  const goldenDiff = useGoldenDiff(currentSkillId, runId)
  const handleCompareToGolden = useCallback(() => {
    void goldenDiff.compare()
  }, [goldenDiff])
  const handlePromoteToGolden = useCallback(() => {
    void goldenDiff.promote().then((baseline) => {
      if (baseline) {
        toast.success("Promoted run to golden baseline")
      }
    })
  }, [goldenDiff])

  useCopilotContext({
    skillId: currentSkillId,
    view: "Edit",
    context: {
      selected_node_id: selectedNodeId,
      selected_node: selectedNode
        ? {
            id: selectedNode.id,
            label: selectedNode.data.label,
            status: selectedNode.data.status,
            summary: typeof selectedNode.data.summary === "string" ? selectedNode.data.summary : null,
          }
        : null,
      selected_edge: selectedEdge
        ? {
            source: selectedEdge.source,
            target: selectedEdge.target,
            context_json: selectedEdge.contextJson as unknown as { [key: string]: string | number | boolean | null },
          }
        : null,
      lint_status: currentSkillId ? readLintStatus(currentSkillId) : "idle",
    },
  })

  useEffect(() => {
    inFlightRef.current = inFlight
  }, [inFlight])

  const handleNodeSelect = (node: { id: string; data: SkillGraphNodeData }) => {
    setSelectedNodeId(node.id)
    setSelectedNode(node)
    setSelectedEdge(null)
  }

  const toOpenFile = useCallback(async (fileOrPath: FileMeta | string): Promise<OpenFile | null> => {
    if (!currentSkillId) return null
    const currentFiles = skillDetail?.files ?? {}
    const rawPath = typeof fileOrPath === "string" ? fileOrPath : fileOrPath.path
    const prefix = `${currentSkillId}/`
    const path = rawPath.startsWith(prefix) ? rawPath.slice(prefix.length) : rawPath
    const content = typeof fileOrPath === "string" ? currentFiles[path] ?? "" : fileOrPath.content
    const language = typeof fileOrPath === "string" ? languageForPath(path) : fileOrPath.language
    return {
      path,
      language,
      content,
      hash: await sha256Hex(content),
      skillId: currentSkillId,
      workspaceRoot: currentWorkspaceRoot,
    }
  }, [currentSkillId, currentWorkspaceRoot, skillDetail?.files])

  const handleFileOpen = useCallback((fileOrPath: FileMeta | string, side?: EditorSide) => {
    setSettingsOpen(false)
    void toOpenFile(fileOrPath).then((file) => {
      if (!file) return
      setActiveFileDetails((current) => {
        const targetSide = side ?? (splitMode && current.left ? "right" : "left")
        return { ...current, [targetSide]: file }
      })
    })
  }, [splitMode, toOpenFile])

  const closeFile = useCallback((side: EditorSide) => {
    setActiveFileDetails((current) => {
      const remainingSide: EditorSide = side === "left" ? "right" : "left"
      const remaining = current[remainingSide]
      setSplitMode(false)
      return remaining ? { left: remaining } : {}
    })
    setInFlight((current) => {
      const remainingSide: EditorSide = side === "left" ? "right" : "left"
      return current[remainingSide] ? { left: current[remainingSide] } : {}
    })
  }, [])

  const updateFileContent = useCallback((side: EditorSide, content: string) => {
    setActiveFileDetails((current) => {
      const file = current[side]
      return file ? { ...current, [side]: { ...file, content } } : current
    })
  }, [])

  const markFileSaved = useCallback((side: EditorSide, hash: string) => {
    setActiveFileDetails((current) => {
      const file = current[side]
      return file ? { ...current, [side]: { ...file, hash } } : current
    })
    void mutateSkillDetail()
  }, [mutateSkillDetail])

  const doWriteSkillFile = useCallback(async (
    path: string,
    content: string,
    expectedHash?: string | null,
  ) => {
    if (!currentSkillId) {
      throw new Error("No active workspace")
    }
    if (isTauriRuntime()) {
      return await writeWorkspaceFile(currentWorkspaceRoot ?? currentSkillId, path, content, expectedHash ?? null)
    }
    return await writeSkillFile(currentSkillId, path, content, expectedHash)
  }, [currentSkillId, currentWorkspaceRoot])

  const handlePhaseFileSave = useCallback(async ({
    path,
    content,
    expectedHash,
  }: {
    path: string
    content: string
    expectedHash: string
  }) => {
    if (!currentSkillId) {
      throw new Error("Open a skill before saving phase properties")
    }
    const result = await doWriteSkillFile(path, content, expectedHash)
    setActiveFileDetails((current) => {
      const next = { ...current }
      for (const side of ["left", "right"] as const) {
        const file = current[side]
        if (file?.skillId === currentSkillId && file.path === path) {
          next[side] = { ...file, content, hash: result.hash, saveEnabled: true, title: undefined }
        }
      }
      return next
    })
    toast.success("Saved phase properties")
    void mutateSkillDetail()
  }, [currentSkillId, doWriteSkillFile, mutateSkillDetail])

  const handleCreatePhase = useCallback(async (kind: NewPhaseKind) => {
    if (!currentSkillId || !skillDetail) {
      toast.error("Open a skill before creating a phase")
      return
    }
    const draft = createPhaseDraft(skillDetail, kind, currentSkillId)
    const graphContent = skillDetail.files?.["GRAPH.md"]
    const graphHash = graphContent === undefined ? null : await sha256Hex(graphContent)
    try {
      await doWriteSkillFile(draft.filePath, draft.fileContent)
      const serialized = await serializeSkillGraph(currentSkillId, draft.phases, graphHash)
      await doWriteSkillFile("GRAPH.md", serialized.markdown_content, graphHash)
      toast.success(`Created ${draft.phaseId}`)
      await mutateSkillDetail()
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Could not create phase")
      void mutateSkillDetail()
    }
  }, [currentSkillId, doWriteSkillFile, mutateSkillDetail, skillDetail])

  const handlePersistConnection = useCallback(async (connection: Connection) => {
    if (!currentSkillId || !skillDetail) {
      throw new Error("Open a skill before connecting phases")
    }
    const result = connectPhaseRefs(skillDetail, connection.source, connection.target)
    if (!result.ok) {
      throw new Error(result.message)
    }
    const graphContent = skillDetail.files?.["GRAPH.md"]
    const graphHash = graphContent === undefined ? null : await sha256Hex(graphContent)
    try {
      const serialized = await serializeSkillGraph(currentSkillId, result.phases, graphHash)
      await doWriteSkillFile("GRAPH.md", serialized.markdown_content, graphHash)
      await mutateSkillDetail()
    } catch (error) {
      void mutateSkillDetail()
      throw error
    }
  }, [currentSkillId, doWriteSkillFile, mutateSkillDetail, skillDetail])

  const handleDisconnectConnection = useCallback(async (connection: { source: string; target: string }) => {
    if (!currentSkillId || !skillDetail) {
      throw new Error("Open a skill before disconnecting phases")
    }
    const result = disconnectPhaseRefs(skillDetail, connection.source, connection.target)
    if (!result.ok) {
      throw new Error(result.message)
    }
    const graphContent = skillDetail.files?.["GRAPH.md"]
    const graphHash = graphContent === undefined ? null : await sha256Hex(graphContent)
    try {
      const serialized = await serializeSkillGraph(currentSkillId, result.phases, graphHash)
      await doWriteSkillFile("GRAPH.md", serialized.markdown_content, graphHash)
      await mutateSkillDetail()
    } catch (error) {
      void mutateSkillDetail()
      throw error
    }
  }, [currentSkillId, doWriteSkillFile, mutateSkillDetail, skillDetail])

  const setFileInFlight = useCallback((side: EditorSide, active: boolean) => {
    setInFlight((current) => ({ ...current, [side]: active }))
  }, [])

  const reloadOpenFile = useCallback(async (side: EditorSide) => {
    const file = activeFileDetails[side]
    if (!file) return
    const detail = await getSkillDetail(file.skillId)
    const content = detail.files?.[file.path]
    if (content === undefined) return
    const hash = await sha256Hex(content)
    setActiveFileDetails((current) => ({
      ...current,
      [side]: { ...file, content, hash, saveEnabled: true, title: undefined },
    }))
    void mutateSkillDetail(detail, { revalidate: false })
  }, [activeFileDetails, mutateSkillDetail])

  const handleUseRemote = useCallback(() => {
    if (!conflict) return
    setActiveFileDetails((current) => {
      const currentFile = current[conflict.side]
      if (!currentFile) return current
      return {
        ...current,
        [conflict.side]: {
          ...currentFile,
          content: conflict.remoteContent,
          hash: conflict.remoteHash,
          saveEnabled: true,
          title: undefined,
        },
      }
    })
    setConflict(null)
  }, [conflict])

  const handleViewDiff = useCallback(() => {
    if (!conflict) return
    setSplitMode(true)
    setActiveFileDetails((current) => ({
      ...current,
      right: {
        path: conflict.path,
        title: `${conflict.path} remote`,
        language: languageForPath(conflict.path),
        content: conflict.remoteContent,
        hash: conflict.remoteHash,
        skillId: conflict.skillId,
        workspaceRoot: currentWorkspaceRoot,
        saveEnabled: false,
      },
    }))
    setConflict(null)
  }, [conflict, currentWorkspaceRoot])

  const pushNavSkill = useCallback((nextSkillId: string) => {
    setNavStack((current) => [...current, nextSkillId])
    setActiveFileDetails({})
    setSplitMode(false)
    setSelectedNode(null)
    setSelectedNodeId(null)
  }, [])

  const popNavTo = useCallback((index: number) => {
    setNavStack((current) => current.slice(0, index + 1))
    setActiveFileDetails({})
    setSplitMode(false)
    setSelectedNode(null)
    setSelectedNodeId(null)
  }, [])

  useEffect(() => {
    if (!currentSkillId) return
    const socket = new WebSocket(wsUrl("/ws/events"))
    socket.onmessage = (message) => {
      try {
        const event = JSON.parse(String(message.data)) as { type?: string, skill_id?: string, path?: string }
        if (event.type !== "skill_changed" || event.skill_id !== currentSkillId || !event.path) return
        const entries = (["left", "right"] as const).filter((side) => activeFileDetails[side]?.path === event.path)
        for (const side of entries) {
          const file = activeFileDetails[side]
          if (!file) continue
          void getSkillDetail(currentSkillId).then(async (detail) => {
            const remoteContent = detail.files?.[event.path ?? ""]
            if (remoteContent === undefined) return
            const remoteHash = await sha256Hex(remoteContent)
            if (inFlightRef.current[side]) {
              setConflict({
                skillId: currentSkillId,
                path: event.path ?? file.path,
                side,
                localContent: file.content,
                remoteContent,
                remoteHash,
              })
            } else {
              setActiveFileDetails((current) => ({
                ...current,
                [side]: { ...file, content: remoteContent, hash: remoteHash },
              }))
              void mutateSkillDetail(detail, { revalidate: false })
            }
          })
        }
      } catch {
        toast.error("Could not process file change event")
      }
    }
    return () => socket.close()
  }, [activeFileDetails, currentSkillId, mutateSkillDetail])

  const contextValue = useMemo<WorkspaceContextValue>(() => ({
    currentSkillId,
    navStack: displayNavStack,
    activeFiles: {
      left: activeFileDetails.left?.path,
      right: activeFileDetails.right?.path,
    },
    activeFileDetails,
    splitMode,
    onFileOpen: handleFileOpen,
    openSplitEditor: () => setSplitMode(true),
    closeFile,
    updateFileContent,
    markFileSaved,
    setFileInFlight,
    onSaveConflict: setConflict,
    reloadOpenFile,
    pushNavSkill,
    popNavTo,
    selectedEdge,
    setSelectedEdge,
    onPanelChange: setActivePanel,
    traceEvents: runStream.events,
  }), [
    activeFileDetails,
    closeFile,
    currentSkillId,
    handleFileOpen,
    markFileSaved,
    displayNavStack,
    popNavTo,
    pushNavSkill,
    reloadOpenFile,
    setFileInFlight,
    splitMode,
    updateFileContent,
    selectedEdge,
    setSelectedEdge,
    setActivePanel,
    runStream.events,
  ])

  const handleCompile = useCallback(() => {
    if (!currentSkillId) return
    const targetSkillId = currentSkillId
    updateStage(targetSkillId, "compiling")
    setCompileErrors((current) => ({ ...current, [targetSkillId]: [] }))
    void compileSkill(targetSkillId)
      .then((result) => {
        if ("code" in result) {
          updateStage(targetSkillId, "compile-fail")
          setCompileErrors((current) => ({ ...current, [targetSkillId]: result.errors }))
          const firstMessage = result.errors[0]?.message ?? result.detail
          toast.error(`${result.errors.length} compile error${result.errors.length === 1 ? "" : "s"}: ${firstMessage}`)
          return
        }
        if (result.status === "ok") {
          updateStage(targetSkillId, "compile-pass")
          setCompileErrors((current) => ({ ...current, [targetSkillId]: [] }))
          toast.success(`Compiled ${result.manifest_name}`)
          void mutateSkillDetail()
        }
      })
      .catch((error: unknown) => {
        updateStage(targetSkillId, "compile-fail")
        const message = error instanceof Error ? error.message : "Compile request failed"
        setCompileErrors((current) => ({
          ...current,
          [targetSkillId]: [{ file: null, line: null, field: null, severity: "fatal", message }],
        }))
        toast.error(message)
      })
  }, [currentSkillId, mutateSkillDetail, updateStage])

  // F5/DEF-025: a copilot edit (Write/Edit / Accept / Reject) hit disk. Reflect it
  // in the open editor buffer, and on a settled review recompile so predict/run
  // use the reviewed code ("改动即时进编辑器 buffer + 改后自动 compile 回灌").
  const reloadFileIfOpen = useCallback(
    (path: string) => {
      ;(["left", "right"] as EditorSide[]).forEach((side) => {
        const file = activeFileDetails[side]
        if (file && file.skillId === currentSkillId && file.path === path) {
          void reloadOpenFile(side)
        }
      })
    },
    [activeFileDetails, currentSkillId, reloadOpenFile],
  )

  const handleCopilotFileChanged = useCallback(
    (path: string, action: CopilotFileAction) => {
      const { reload, recompile } = copilotFileActionEffects(action)
      if (reload) reloadFileIfOpen(path)
      if (recompile) handleCompile()
    },
    [reloadFileIfOpen, handleCompile],
  )

  const deriveBuildStage = useCallback((id: string): SkillBuildStage => {
    const compileStage = compileStages[id]
    if (compileStage) return compileStage
    const lint = readLintStatus(id)
    if (lint === "checking") return "compiling"
    if (lint === "failed") return "compile-fail"
    if (lint === "passed") return "compile-pass"
    return "idle"
  }, [compileStages])

  const handlePredict = useCallback(async () => {
    if (!currentSkillId) return
    const targetSkillId = currentSkillId
    updateStage(targetSkillId, "predicting")
    try {
      const inputData = await resolveRunInput(targetSkillId, selectedTestInputId)
      await postPredictRun(targetSkillId, inputData)
      updateStage(targetSkillId, "predict-pass")
      toast.success("Predict run completed successfully")
    } catch (error: unknown) {
      updateStage(targetSkillId, "predict-fail")
      interface PredictErrorResponse {
        response?: {
          data?: {
            code?: string
            errors?: Array<{
              file?: string | null
              line?: number | null
              field?: string | null
              message?: string
            }>
          }
        }
      }
      const err = error as PredictErrorResponse
      const responseData = err?.response?.data
      if (responseData?.code === "compile_failed" && Array.isArray(responseData?.errors)) {
        const firstError = responseData.errors[0]
        const detailMsg = firstError?.message || "Unknown compile/predict error"
        toast.error(`Predict failed: ${detailMsg}`)
      } else {
        const fallbackMsg = error instanceof Error ? error.message : "Predict request failed"
        toast.error(`Predict failed: ${fallbackMsg}`)
      }
    }
  }, [currentSkillId, selectedTestInputId, updateStage])

  const handleRun = useCallback(async () => {
    if (!currentSkillId) return
    const stage = deriveBuildStage(currentSkillId)
    if (stage !== "predict-pass") {
      return
    }
    const targetSkillId = currentSkillId
    updateStage(targetSkillId, "running")
    try {
      const inputData = await resolveRunInput(targetSkillId, selectedTestInputId)
      const result = await startRun(targetSkillId, inputData)
      setRunId(result.run_id)
      // F1: starting a run opens the timeline region to stream live trace events.
      setActivePanel("timeline")
      toast.success("Run started successfully")
    } catch (error) {
      updateStage(targetSkillId, "predict-pass")
      toast.error(error instanceof Error ? error.message : "Failed to start run")
    }
  }, [currentSkillId, deriveBuildStage, selectedTestInputId, updateStage, setRunId])

  // Headline lifecycle "resume": continue the active run from its last
  // checkpoint. The backend reports RESUME_CHECKPOINT_NOT_FOUND when a run has
  // nothing to continue (e.g. it already finished) — surfaced as a clear toast.
  const [resumeLoading, setResumeLoading] = useState(false)
  const handleResume = useCallback(async () => {
    if (!currentSkillId || !runId) return
    setResumeLoading(true)
    try {
      const result = await resumeRun(currentSkillId, runId)
      setActivePanel("timeline")
      // Re-subscribe the trace stream to the resumed run (new id, or re-attach).
      setRunId(null)
      setRunId(result.run_id)
      toast.success("Run resumed from checkpoint")
    } catch (error) {
      // Surface the backend's typed reason (e.g. RESUME_CHECKPOINT_NOT_FOUND for
      // a run that already finished) instead of the raw "status code 404".
      toast.error(`Resume failed: ${errorMessage(error)}`)
    } finally {
      setResumeLoading(false)
    }
  }, [currentSkillId, runId, setRunId])

  const handleHome = useCallback(() => {
    setSettingsOpen(false)
    onCloseSkill()
  }, [onCloseSkill])

  const hasOpenFile = Boolean(activeFileDetails.left || activeFileDetails.right)
  const currentCompileErrors = currentSkillId ? compileErrors[currentSkillId] ?? [] : []

  return (
    <WorkspaceProvider value={contextValue}>
    <div className="flex h-screen w-screen flex-col overflow-hidden bg-background text-foreground">
      <Header
        skillId={currentSkillId}
        navStack={displayNavStack}
        onBreadcrumbClick={popNavTo}
        copilotOpen={copilotOpen}
        onCopilotToggle={() => setCopilotOpen((open) => !open)}
        onHome={handleHome}
        onSyncSuccess={() => {
          void mutateSkillDetail()
        }}
        onOpenSettings={() => setSettingsOpen(true)}
      />

      <div className="relative flex min-h-0 flex-1">
        <Toolbar
          activePanel={activePanel}
          onPanelChange={setActivePanel}
          onSettingsOpen={() => setSettingsOpen(true)}
        />

        <ResizablePanelGroup
          id="studio-workspace-h"
          orientation="horizontal"
          className="min-w-0 flex-1"
        >
          {activePanel ? (
            <>
              <ResizablePanel
                id="left-panel"
                defaultSize="20%"
                minSize="14%"
                maxSize="35%"
              >
                <Panels
                  activePanel={activePanel}
                  skillId={currentSkillId}
                  skillDetail={skillDetail}
                  selectedNode={selectedNode}
                  selectedTestInputId={selectedTestInputId}
                  onSelectTestInput={setSelectedTestInputId}
                  onPhaseFileSave={handlePhaseFileSave}
                  runId={runId}
                  traceEvents={runStream.events}
                  activeTracePhase={activeTracePhase}
                  onSelectTracePrompt={setPromptIndex}
                  traceCanCompare={Boolean(runId)}
                  traceCompareLoading={goldenDiff.loading}
                  onCompareToGolden={handleCompareToGolden}
                  onPromoteToGolden={handlePromoteToGolden}
                  traceCanResume={Boolean(runId)}
                  traceResumeLoading={resumeLoading}
                  onResumeRun={handleResume}
                />
              </ResizablePanel>
              <ResizableHandle />
            </>
          ) : null}

          <ResizablePanel id="canvas" defaultSize={copilotOpen ? "60%" : "80%"} minSize="30%">
            <div className="relative size-full">
              {settingsOpen ? (
                <SettingsPage onClose={() => setSettingsOpen(false)} />
              ) : currentSkillId && hasOpenFile ? (
                <SplitEditor
                  skillId={currentSkillId}
                  skillDetail={skillDetail}
                  isLoading={isLoading}
                  error={skillDetailError}
                  selectedNodeId={selectedNodeId}
                  onNodeSelect={handleNodeSelect}
                  onPanelChange={setActivePanel}
                  onCreatePhase={handleCreatePhase}
                  onPersistConnection={handlePersistConnection}
                  onDisconnectConnection={handleDisconnectConnection}
                  onPhaseFileSave={handlePhaseFileSave}
                  statusByNodeId={statusByNodeId}
                />
              ) : currentSkillId === null ? (
                <WelcomePage onSelectSkill={onSelectSkill} />
              ) : (
                <GraphCanvas
                  skillId={currentSkillId}
                  skillDetail={skillDetail}
                  isLoading={isLoading}
                  error={skillDetailError}
                  selectedNodeId={selectedNodeId}
                  onNodeSelect={handleNodeSelect}
                  onPanelChange={setActivePanel}
                  onCreatePhase={handleCreatePhase}
                  onPersistConnection={handlePersistConnection}
                  onDisconnectConnection={handleDisconnectConnection}
                  onPhaseFileSave={handlePhaseFileSave}
                  statusByNodeId={statusByNodeId}
                />
              )}
              {currentSkillId && !settingsOpen ? (
                <>
                  {currentCompileErrors.length > 0 ? (
                    <CompileErrorPanel errors={currentCompileErrors} />
                  ) : null}
                  <CenterActionBar
                    stage={deriveBuildStage(currentSkillId)}
                    onCompile={handleCompile}
                    onPredict={handlePredict}
                    onRun={handleRun}
                  />
                </>
              ) : null}
              {goldenDiff.result && !settingsOpen ? (
                <div className="absolute inset-0 z-40 flex flex-col bg-background">
                  <div className="flex shrink-0 items-center justify-between border-b border-border px-4 py-2">
                    <span className="text-sm font-semibold text-foreground">Golden Diff</span>
                    <button
                      type="button"
                      onClick={goldenDiff.clear}
                      aria-label="Close golden diff"
                      className="rounded-md px-2 py-1 text-xs text-muted-foreground hover:bg-accent hover:text-foreground"
                    >
                      Close
                    </button>
                  </div>
                  <div className="min-h-0 flex-1">
                    <DiffView
                      result={goldenDiff.result}
                      skillId={currentSkillId}
                      runId={runId}
                      loading={goldenDiff.loading}
                      error={goldenDiff.error}
                      canCompare={Boolean(runId)}
                      canPromote={Boolean(runId)}
                      onCompare={handleCompareToGolden}
                      onPromote={handlePromoteToGolden}
                    />
                  </div>
                </div>
              ) : null}
              <PromptInspector
                promptEvent={promptIndex != null ? runStream.events[promptIndex] ?? null : null}
                onClose={() => setPromptIndex(null)}
              />
            </div>
          </ResizablePanel>

          {copilotOpen ? (
            <>
              <ResizableHandle />
              <ResizablePanel
                id="copilot"
                defaultSize="20%"
                minSize="18%"
                maxSize="35%"
              >
                <CopilotPanel
                  skillId={currentSkillId}
                  completedRunId={completedRunId}
                  onFileChanged={handleCopilotFileChanged}
                />
              </ResizablePanel>
            </>
          ) : null}
        </ResizablePanelGroup>
      </div>
      <ConflictDialog
        conflict={conflict}
        onKeepLocal={() => setConflict(null)}
        onUseRemote={handleUseRemote}
        onViewDiff={handleViewDiff}
      />
    </div>
    </WorkspaceProvider>
  )
}

function CompileErrorPanel({ errors }: { errors: CompileError[] }) {
  const first = errors[0]
  return (
    <div className="absolute bottom-20 left-1/2 z-30 w-[min(560px,calc(100%-2rem))] -translate-x-1/2 rounded-md border border-destructive/40 bg-background/95 p-3 text-sm shadow-lg backdrop-blur">
      <div className="font-medium text-destructive">
        {errors.length} compile error{errors.length === 1 ? "" : "s"}: {first?.message ?? "Compilation failed"}
      </div>
      <div className="mt-2 max-h-36 space-y-2 overflow-auto">
        {errors.map((error, index) => (
          <div key={`${error.file ?? "compile"}-${error.line ?? "x"}-${index}`} className="text-xs text-muted-foreground">
            <span className="font-medium text-foreground">
              {error.file ?? "unknown file"}
              {error.line ? `:${error.line}` : ""}
            </span>
            {error.field ? <span> - {error.field}</span> : null}
            <span> - {error.message}</span>
          </div>
        ))}
      </div>
    </div>
  )
}

function languageForPath(path: string): string {
  if (path.endsWith(".json")) return "json"
  if (path.endsWith(".py")) return "python"
  return "markdown"
}
