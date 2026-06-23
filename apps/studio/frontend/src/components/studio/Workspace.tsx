import { useCallback, useEffect, useMemo, useRef, useState, type ComponentProps } from "react"
import type { Connection } from "@xyflow/react"
import { toast } from "sonner"
import useSWR from "swr"
import { ResizableHandle, ResizablePanel, ResizablePanelGroup } from "@/components/ui/resizable"
import { GraphCanvas, type SkillGraphNodeData } from "@/components/GraphCanvas"
import { CopilotPanel } from "@/components/copilot/copilot-panel"
import { copilotFileActionEffects, type CopilotFileAction } from "@/components/copilot/patch-proposed-bubble"
import { PromptInspector } from "@/components/PromptInspector"
import { findPromptEvent } from "@/utils/trace"
import { useCopilotContext } from "@/hooks/useCopilotContext"
import { lintResultEvent, lintStatusEvent, readLintStatus } from "@/hooks/useDebouncedLint"
import { useRunStream } from "@/hooks/useRunStream"
import { useGoldenDiff } from "@/hooks/useGoldenDiff"
import { archiveFeedbackForGitStatus, nextLocalHistoryRefreshKey, useLocalHistory, useRunHistory } from "@/hooks/useRunHistory"
import { useSkills } from "@/hooks/useSkills"
import { DiffView } from "@/components/diff/DiffView"
import type { CopilotJudgeResponse, ResumeRunOptions } from "@/api/client"
import type { TraceHitlResumeRequest } from "@/components/TracePanel"
import { WelcomePage } from "@/components/welcome/WelcomePage"
import { compileSkill, fetcher, getCompareGroup, getResumeValidity, getSkillDetail, resolveRunInput, serializeSkillGraph, startCompareRun, writeSkillFile, wsUrl, postPredictRun, startRun, resumeRun } from "@/api/client"
import type { CompareCandidateRun, GoldenBaseline, LintResult, ResumeValidityResponse, SerializableGraphPhaseRef, SkillDetail } from "@/api/types"
import { candidatesFromRoleNames, compareTabsFromGroup } from "./run-compare"
import { isTauriRuntime } from "@/config/runtime"
import { writeWorkspaceFile } from "@/lib/tauri"
import { errorMessage } from "@/utils/errors"
import type { CompileError } from "@/api/types"
import { connectPhaseRefs, createPhaseDraft, disconnectPhaseRefs, reconnectPhaseRefs, type NewPhaseKind } from "@/components/GraphCanvas/canvas-authoring"
import { isReadOnlySkillError, type ChildSaveTarget } from "@/components/GraphCanvas/drill-edit"
import { sha256Hex } from "@/lib/hash"
import { CenterActionBar, type SkillBuildStage } from "./center-action-bar"
import { deriveNodeErrorMessages, deriveNodeStatuses } from "./node-status"
import { dirtyDownstreamFromValidity, nodeResumeCheckpointFromEvents, resumeAnchorNodeId, shouldDeriveDirtyDownstream } from "./node-resume"
import { hitlResumeOptionsFromRequest } from "./resume-options"
import { activeLintErrors, compileErrorsByNode, dataGapErrorsByNode, lintErrorToCompileError, lintErrorsByNode, mergeNodeErrors } from "./node-compile-errors"
import { goldenTriStateByNode, ranAgentNodesFromPredict } from "./node-golden"
import { compileErrorsToFieldLintErrors } from "./field-compile-errors"
import { CompareRunDialog } from "./CompareRunDialog"
import { CompileErrorDrawer } from "./CompileErrorDrawer"
import { ConflictDialog } from "./ConflictDialog"
import { Header } from "./Header"
import { Panels } from "./Panels"
import { SettingsPage } from "./SettingsPage"
import { SplitEditor } from "./SplitEditor"
import { Toolbar, type PanelKind } from "./Toolbar"
import type { FileMeta } from "./file-types"
import { conflictFromSaveError, isSameSaveConflict, overwriteRetryPayload } from "./save-conflicts"
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

type CenterActionBarCreateProps = ComponentProps<typeof CenterActionBar> & {
  onCreatePhase?: (kind: NewPhaseKind) => Promise<void> | void
}

const CenterActionBarWithCreate = CenterActionBar as (props: CenterActionBarCreateProps) => ReturnType<typeof CenterActionBar>

interface CopilotJudgeReplayContext {
  skillId: string | null
  runId: string | null
}

function skillIdFromArtifactRef(ref: string | null | undefined): string | null {
  if (!ref) {
    return null
  }
  const [skillId] = ref.split("/", 1)
  return skillId || null
}

function runIdFromRunResultsRef(ref: string | null | undefined): string | null {
  if (!ref) {
    return null
  }
  const runMatch = ref.match(/^[^/]+\/runs\/([^/]+)\/result\.json$/)
  return runMatch?.[1] ?? null
}

export function isCopilotJudgeResultReplayable(
  result: CopilotJudgeResponse | null,
  context?: CopilotJudgeReplayContext,
): boolean {
  if (!result) {
    return false
  }

  const runResultsRef = result.diff_summary.run_results_ref
  const runSkillId = skillIdFromArtifactRef(runResultsRef)
  const baselineSkillId = skillIdFromArtifactRef(result.baseline_ref)
  const compareSkillId = skillIdFromArtifactRef(result.compare_result_ref)
  const judgeContextSkillId = skillIdFromArtifactRef(result.judge_context_ref)
  const judgedRunId = runIdFromRunResultsRef(runResultsRef)

  if (!result.diff_summary.baseline_id || !judgedRunId) {
    return false
  }
  if (!runSkillId || runSkillId !== baselineSkillId || runSkillId !== compareSkillId || runSkillId !== judgeContextSkillId) {
    return false
  }
  if (!context) {
    return true
  }
  return Boolean(context.skillId && context.runId && runSkillId === context.skillId && judgedRunId === context.runId)
}

export function compareReplayArgsForJudgeResult(
  result: CopilotJudgeResponse | null,
  context?: CopilotJudgeReplayContext,
): { against: string | null; runId: string | null } {
  if (!result || !isCopilotJudgeResultReplayable(result, context)) {
    return { against: null, runId: null }
  }
  return {
    against: result.diff_summary.baseline_id || null,
    runId: runIdFromRunResultsRef(result.diff_summary.run_results_ref),
  }
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
  const [compileDrawerOpen, setCompileDrawerOpen] = useState(false)
  const [runId, setRunId] = useState<string | null>(null)
  // n4-trace#23 (P8 model-compare): the active compare group + its per-candidate
  // runs (from the real compare endpoints) and which candidate tab is selected.
  // Selecting a candidate points `runId` at that candidate's spawned run so the
  // trace stream re-subscribes to it. Null when no compare run is active.
  const [compareGroupId, setCompareGroupId] = useState<string | null>(null)
  const [compareRuns, setCompareRuns] = useState<CompareCandidateRun[]>([])
  const [compareCandidateId, setCompareCandidateId] = useState<string | null>(null)
  // N3 #12: realtime lint runs in the editor (useDebouncedLint) and publishes status to
  // sessionStorage + a window event. deriveBuildStage reads that status, but Workspace
  // does not otherwise re-render when it changes, so a clean edit never flipped Predict
  // on until something else (e.g. Compile) re-rendered. This tick is bumped by the lint
  // event subscriber below to force deriveBuildStage to re-read the latest lint status.
  const [lintTick, setLintTick] = useState(0)
  // N3 atom #4: the realtime LintResult lifted from the editor (LazyMonacoPanel's
  // useDebouncedLint publishes it on the `lintResultEvent` window event). Null until the
  // first realtime lint resolves for the active skill; once present it overlays the
  // first-screen SkillDetail lint onto the canvas-node / properties projection.
  const [realtimeLint, setRealtimeLint] = useState<LintResult | null>(null)
  // F4: the test input selected in the i/o panel feeds Predict/Run (null = the
  // prior empty-payload behaviour). Reset when the active skill changes.
  const [selectedTestInputId, setSelectedTestInputId] = useState<string | null>(null)

  useEffect(() => {
    setRunId(null)
    setSelectedTestInputId(null)
    setCompareGroupId(null)
    setCompareRuns([])
    setCompareCandidateId(null)
  }, [currentSkillId])

  // N3 #12: subscribe to realtime-lint status changes (published by useDebouncedLint as
  // the `lintStatusEvent` window event). A matching skillId bumps lintTick so the
  // CenterActionBar's stage (deriveBuildStage) re-reads readLintStatus and lights Predict
  // the moment lint passes — without the user clicking Compile first.
  useEffect(() => {
    if (typeof window === "undefined" || !currentSkillId) return undefined
    const handler = (event: Event) => {
      const detail = (event as CustomEvent<{ skillId?: string; status?: string }>).detail
      if (detail?.skillId === currentSkillId) {
        setLintTick((tick) => tick + 1)
      }
    }
    window.addEventListener(lintStatusEvent, handler)
    return () => window.removeEventListener(lintStatusEvent, handler)
  }, [currentSkillId])

  // N3 atom #4: subscribe to the full realtime LintResult (published alongside the status
  // event by useDebouncedLint). A matching skillId stores the result so the node/properties
  // projection overlays the editor's live diagnostics on top of the first-screen SkillDetail
  // lint. Reset to null when the active skill changes (the new skill has no realtime lint yet).
  useEffect(() => {
    setRealtimeLint(null)
    if (typeof window === "undefined" || !currentSkillId) return undefined
    const handler = (event: Event) => {
      const detail = (event as CustomEvent<{ skillId?: string; result?: LintResult | null }>).detail
      if (detail?.skillId === currentSkillId) {
        setRealtimeLint(detail.result ?? null)
      }
    }
    window.addEventListener(lintResultEvent, handler)
    return () => window.removeEventListener(lintResultEvent, handler)
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

  // N6 #2 (history-auto-refresh): a successful run autocommits a new "Auto run"
  // snapshot on the backend (GET /skills/{id}/history). Revalidate the Local
  // History SWR cache when this run reaches run_ended so the snapshot appears
  // without the user clicking Refresh. We only project the single backend truth —
  // refresh asks SWR to re-fetch the same `/skills/{id}/history` key the panel
  // consumes; we never build a snapshot locally.
  const localHistory = useLocalHistory(currentSkillId)
  const refreshLocalHistory = localHistory.refresh
  const { fetchRunDetail } = useRunHistory(currentSkillId)
  // Track which (skill, run) pair has already triggered a refresh so the effect
  // fires once on the not-ended → ended edge, not on every subsequent re-render
  // while the terminated run keeps replaying its log. nextLocalHistoryRefreshKey
  // owns the de-dupe rule (unit-tested); this effect is a thin wrapper that
  // persists the key and asks SWR to revalidate the same `/skills/{id}/history`
  // key the Local History panel consumes.
  const refreshedRunRef = useRef<string | null>(null)
  useEffect(() => {
    const refreshKey = nextLocalHistoryRefreshKey({
      skillId: currentSkillId,
      completedRunId,
      lastRefreshedKey: refreshedRunRef.current,
    })
    if (!refreshKey) {
      return
    }
    refreshedRunRef.current = refreshKey
    void refreshLocalHistory()
  }, [completedRunId, currentSkillId, refreshLocalHistory])

  // N6 #1 (autocommit-feedback): on the not-ended → ended edge, the run is done
  // but the `run_ended` stream event carries no metadata, so we re-fetch the run
  // detail (GET /skills/{id}/runs/{run_id}) to read the backend-recorded
  // `git_status` and surface a one-shot archive toast (committed/no_git → success;
  // locked/failed → warning, never pretending the archive happened). We reuse the
  // same (skill, run) de-dupe key as the history refresh and guard the async race:
  // if the run changes while the fetch is in flight, the stale result is dropped.
  const archiveFeedbackRunRef = useRef<string | null>(null)
  useEffect(() => {
    const feedbackKey = nextLocalHistoryRefreshKey({
      skillId: currentSkillId,
      completedRunId,
      lastRefreshedKey: archiveFeedbackRunRef.current,
    })
    if (!feedbackKey || !completedRunId) {
      return
    }
    archiveFeedbackRunRef.current = feedbackKey
    let cancelled = false
    const announceArchiveOutcome = async () => {
      try {
        const detail = await fetchRunDetail(completedRunId)
        if (cancelled || !detail) {
          return
        }
        const feedback = archiveFeedbackForGitStatus(detail.metadata.git_status)
        if (!feedback) {
          return
        }
        if (feedback.variant === "success") {
          toast.success(feedback.message)
        } else {
          toast.warning(feedback.message)
        }
      } catch (error) {
        if (!cancelled) {
          toast.error(`Could not read archive status: ${errorMessage(error)}`)
        }
      }
    }
    void announceArchiveOutcome()
    return () => {
      cancelled = true
    }
  }, [completedRunId, currentSkillId, fetchRunDetail])

  const statusByNodeId = useMemo(
    () => deriveNodeStatuses(runStream.events, runId),
    [runId, runStream.events],
  )
  const errorMessageByNodeId = useMemo(
    () => deriveNodeErrorMessages(runStream.events, runId),
    [runId, runStream.events],
  )
  const selectedNodeStatus = useMemo(
    () => selectedNodeId
      ? statusByNodeId[selectedNodeId] ?? selectedNode?.data.status ?? null
      : null,
    [selectedNodeId, selectedNode?.data.status, statusByNodeId],
  )
  // The currently-running phase, used to highlight/link the live trace stream.
  const activeTracePhase = useMemo(() => {
    const running = Object.entries(statusByNodeId).find(([, status]) => status === "running")
    return running?.[0] ?? null
  }, [statusByNodeId])

  // N4 atom #30: per-node golden state badge. Fetch the skill's golden baselines
  // (same SWR key the I/O panel's GoldenSection uses, so the request dedupes) and
  // project their per-node `cases` into a has-golden map for the canvas.
  const { data: goldenBaselines, mutate: mutateGoldenBaselines } = useSWR<GoldenBaseline[]>(
    currentSkillId ? `/skills/${currentSkillId}/golden` : null,
    fetcher,
  )

  // N4 atom #30 🟡 logic-OK source: the AGENT nodes that ran in the most-recent predict
  // (read from PredictDiagnosticExport.phases). Session-memory only — keyed by skill,
  // set on predict-pass, cleared on predict-fail; never persisted across sessions
  // (design: "most recent predict response").
  const [ranAgentNodesBySkill, setRanAgentNodesBySkill] = useState<Record<string, Set<string>>>({})

  // Golden compare/promote for the active run (per-node diff surfaced as an overlay).
  const goldenDiff = useGoldenDiff(currentSkillId, runId, currentWorkspaceRoot)
  const [copilotJudgeResult, setCopilotJudgeResult] = useState<CopilotJudgeResponse | null>(null)
  const clearCopilotJudgeResult = useCallback(() => {
    setCopilotJudgeResult(null)
  }, [])
  const replayContext = useMemo<CopilotJudgeReplayContext>(() => ({
    skillId: currentSkillId,
    runId,
  }), [currentSkillId, runId])
  const replayableCopilotJudgeResult = useMemo(
    () => isCopilotJudgeResultReplayable(copilotJudgeResult, replayContext) ? copilotJudgeResult : null,
    [copilotJudgeResult, replayContext],
  )

  useEffect(() => {
    if (copilotJudgeResult && !replayableCopilotJudgeResult) {
      clearCopilotJudgeResult()
    }
  }, [clearCopilotJudgeResult, copilotJudgeResult, replayableCopilotJudgeResult])

  const copilotJudgeRefs = useMemo(
    () => goldenDiff.result
      ? {
          runResultsRef: goldenDiff.result.run_results_ref,
          baselineRef: goldenDiff.result.baseline_ref,
        }
      : replayableCopilotJudgeResult
        ? {
            runResultsRef: replayableCopilotJudgeResult.diff_summary.run_results_ref,
            baselineRef: replayableCopilotJudgeResult.baseline_ref,
          }
      : null,
    [goldenDiff.result, replayableCopilotJudgeResult],
  )
  const handleCompareToGolden = useCallback(() => {
    const replay = compareReplayArgsForJudgeResult(copilotJudgeResult, replayContext)
    if (replay.against && replay.runId) {
      void goldenDiff.compare(replay.against, replay.runId)
      return
    }
    clearCopilotJudgeResult()
    void goldenDiff.compare()
  }, [clearCopilotJudgeResult, copilotJudgeResult, goldenDiff, replayContext])
  const handleCloseGoldenDiff = useCallback(() => {
    clearCopilotJudgeResult()
    goldenDiff.clear()
  }, [clearCopilotJudgeResult, goldenDiff])
  const handlePromoteToGolden = useCallback(() => {
    void goldenDiff.promote().then((baseline) => {
      if (baseline) {
        toast.success("Promoted run to golden baseline")
      }
    })
  }, [goldenDiff])
  // Per-node golden promote (atom #32): write golden for one agent node, then
  // revalidate the baseline list so the canvas + properties badge flip to 🟢.
  const handlePromoteNode = useCallback(
    async (nodeId: string) => {
      const baseline = await goldenDiff.promote(nodeId)
      if (baseline) {
        toast.success(`Promoted "${nodeId}" to golden`)
        void mutateGoldenBaselines()
      } else if (goldenDiff.error) {
        toast.error(`Promote failed: ${goldenDiff.error}`)
      }
    },
    [goldenDiff, mutateGoldenBaselines],
  )

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
    const fileSkillId = typeof fileOrPath === "string" ? currentSkillId : fileOrPath.skillId ?? currentSkillId
    const fileWorkspaceRoot = typeof fileOrPath === "string" ? currentWorkspaceRoot : fileOrPath.workspaceRoot ?? currentWorkspaceRoot
    return {
      path,
      language,
      content,
      hash: typeof fileOrPath === "string" ? await sha256Hex(content) : fileOrPath.hash ?? await sha256Hex(content),
      skillId: fileSkillId,
      workspaceRoot: fileWorkspaceRoot,
      title: typeof fileOrPath === "string" ? undefined : fileOrPath.title,
      saveEnabled: typeof fileOrPath === "string" ? undefined : fileOrPath.saveEnabled,
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

  // n2-canvas #14 (drilled-subgraph edit-writeback): an optional identity override
  // routes the write to a DRILLED CHILD skill instead of the parent. When absent
  // the behaviour is byte-identical to the pre-drill path (parent identity). The
  // child override carries the child's own skillId (browser write target) and
  // workspaceRoot (Tauri native write target), so a drilled-child edit lands on the
  // child's own files, never the parent's file map / workspace root.
  const doWriteSkillFile = useCallback(async (
    path: string,
    content: string,
    expectedHash?: string | null,
    override?: { skillId: string; workspaceRoot: string | null },
  ) => {
    const targetSkillId = override?.skillId ?? currentSkillId
    const targetWorkspaceRoot = override ? override.workspaceRoot : currentWorkspaceRoot
    if (!targetSkillId) {
      throw new Error("No active workspace")
    }
    if (isTauriRuntime()) {
      return await writeWorkspaceFile(targetWorkspaceRoot ?? targetSkillId, path, content, expectedHash ?? null)
    }
    return await writeSkillFile(targetSkillId, path, content, expectedHash)
  }, [currentSkillId, currentWorkspaceRoot])

  const compileSkillById = useCallback(async (targetSkillId: string) => {
    updateStage(targetSkillId, "compiling")
    setCompileErrors((current) => ({ ...current, [targetSkillId]: [] }))
    try {
      const result = await compileSkill(targetSkillId)
      if ("code" in result) {
        updateStage(targetSkillId, "compile-fail")
        setCompileErrors((current) => ({ ...current, [targetSkillId]: result.errors }))
        setCompileDrawerOpen(true)
        const firstMessage = result.errors[0]?.message ?? result.detail
        toast.error(`${result.errors.length} compile error${result.errors.length === 1 ? "" : "s"}: ${firstMessage}`)
        return
      }
      if (result.status === "ok") {
        updateStage(targetSkillId, "compile-pass")
        setCompileErrors((current) => ({ ...current, [targetSkillId]: [] }))
        setCompileDrawerOpen(false)
        toast.success(
          `Compiled ${result.manifest_name} (${shortHash(result.artifact_ref.content_hash)}, fp ${shortHash(result.execution_fingerprint)})`,
        )
        void mutateSkillDetail()
      }
    } catch (error: unknown) {
      updateStage(targetSkillId, "compile-fail")
      const message = error instanceof Error ? error.message : "Compile request failed"
      setCompileErrors((current) => ({
        ...current,
        [targetSkillId]: [{ file: null, line: null, field: null, severity: "fatal", message }],
      }))
      setCompileDrawerOpen(true)
      toast.error(message)
    }
  }, [mutateSkillDetail, updateStage])

  const handlePhaseFileSave = useCallback(async ({
    path,
    content,
    expectedHash,
  }: {
    path: string
    content: string
    expectedHash: string
  }, target?: ChildSaveTarget) => {
    // n2-canvas #14: with a drilled-child `target`, the agent-body / phase-file
    // save routes to the CHILD skill (its own files), refetching the child on
    // settle. Without a target the parent/root behaviour below is unchanged.
    if (target) {
      try {
        await doWriteSkillFile(path, content, expectedHash, { skillId: target.skillId, workspaceRoot: target.workspaceRoot })
        toast.success("Saved phase properties")
      } catch (error) {
        if (isReadOnlySkillError(error)) {
          toast.error("This subgraph is read-only — fork it into your workspace to edit.")
        }
        throw error
      } finally {
        void target.onSettled()
      }
      return
    }
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
    const draft = createPhaseDraft(skillDetail, kind)
    const graphContent = skillDetail.files?.["GRAPH.md"]
    const graphHash = graphContent === undefined ? null : await sha256Hex(graphContent)
    try {
      const serialized = await serializeSkillGraph(currentSkillId, draft.phases, graphHash)
      await doWriteSkillFile(draft.filePath, draft.fileContent)
      await doWriteSkillFile("GRAPH.md", serialized.markdown_content, graphHash)
      await compileSkillById(currentSkillId)
      toast.success(`Created ${draft.phaseId}`)
      await mutateSkillDetail()
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Could not create phase")
      void mutateSkillDetail()
    }
  }, [compileSkillById, currentSkillId, doWriteSkillFile, mutateSkillDetail, skillDetail])

  // n2-canvas #14: the shared serialize → write GRAPH.md → compile → settle tail of
  // every graph-structure edit (connect / disconnect / reconnect). `editDetail` is
  // the snapshot the refs were computed from (parent skillDetail, or the drilled
  // child's detail). With a `target` the whole write routes to the CHILD skill and
  // re-fetches the child on settle; without it the PARENT path is byte-identical to
  // before (serialize/write/compile against currentSkillId, revalidate via
  // mutateSkillDetail). `parentSkillId` is asserted non-null by the callers' guard.
  const writeGraphEdit = useCallback(async (
    parentSkillId: string,
    editDetail: SkillDetail,
    phases: SerializableGraphPhaseRef[],
    target?: ChildSaveTarget,
  ) => {
    const targetSkillId = target?.skillId ?? parentSkillId
    const override = target ? { skillId: target.skillId, workspaceRoot: target.workspaceRoot } : undefined
    const graphContent = editDetail.files?.["GRAPH.md"]
    const graphHash = graphContent === undefined ? null : await sha256Hex(graphContent)
    try {
      const serialized = await serializeSkillGraph(targetSkillId, phases, graphHash)
      await doWriteSkillFile("GRAPH.md", serialized.markdown_content, graphHash, override)
      await compileSkillById(targetSkillId)
      if (target) {
        await target.onSettled()
      } else {
        await mutateSkillDetail()
      }
    } catch (error) {
      if (target) {
        if (isReadOnlySkillError(error)) {
          toast.error("This subgraph is read-only — fork it into your workspace to edit.")
        }
        void target.onSettled()
      } else {
        void mutateSkillDetail()
      }
      throw error
    }
  }, [compileSkillById, doWriteSkillFile, mutateSkillDetail])

  const handlePersistConnection = useCallback(async (connection: Connection, target?: ChildSaveTarget) => {
    const editDetail = target?.detail ?? skillDetail
    if (!currentSkillId || !editDetail) {
      throw new Error("Open a skill before connecting phases")
    }
    const result = connectPhaseRefs(editDetail, connection.source, connection.target)
    if (!result.ok) {
      throw new Error(result.message)
    }
    await writeGraphEdit(currentSkillId, editDetail, result.phases, target)
  }, [currentSkillId, skillDetail, writeGraphEdit])

  const handleDisconnectConnection = useCallback(async (connection: { source: string; target: string }, target?: ChildSaveTarget) => {
    const editDetail = target?.detail ?? skillDetail
    if (!currentSkillId || !editDetail) {
      throw new Error("Open a skill before disconnecting phases")
    }
    const result = disconnectPhaseRefs(editDetail, connection.source, connection.target)
    if (!result.ok) {
      throw new Error(result.message)
    }
    await writeGraphEdit(currentSkillId, editDetail, result.phases, target)
  }, [currentSkillId, skillDetail, writeGraphEdit])

  // n2-canvas #8 (atomic reconnect): dragging an edge endpoint to a new node is
  // BOTH a disconnect (drop the old depends_on) AND a connect (add the new one).
  // The old canvas path chained onDisconnectConnection().then(onPersistConnection),
  // i.e. TWO serialize round-trips against the SAME captured skillDetail closure;
  // the disconnect wrote GRAPH.md + revalidated, then the queued persist
  // serialized the PRE-disconnect phases with a now-stale expected_hash and the
  // backend hash guard rejected it with 409, leaving the graph half-mutated.
  // reconnectPhaseRefs folds both depends_on edits into ONE phases list off a
  // single skillDetail snapshot, so we serialize + write GRAPH.md exactly once
  // with a single expected_hash derived from the current GRAPH.md.
  const handleReconnectConnection = useCallback(async (
    disconnect: { source: string; target: string },
    connect: { source: string; target: string },
    target?: ChildSaveTarget,
  ) => {
    const editDetail = target?.detail ?? skillDetail
    if (!currentSkillId || !editDetail) {
      throw new Error("Open a skill before reconnecting phases")
    }
    const result = reconnectPhaseRefs(editDetail, disconnect, connect)
    if (!result.ok) {
      throw new Error(result.message)
    }
    await writeGraphEdit(currentSkillId, editDetail, result.phases, target)
  }, [currentSkillId, skillDetail, writeGraphEdit])

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

  const handleOverwriteRetry = useCallback(async () => {
    if (!conflict) return
    try {
      const payload = overwriteRetryPayload(conflict)
      const result = await doWriteSkillFile(payload.path, payload.content, payload.expectedHash)
      setActiveFileDetails((current) => {
        const currentFile = current[conflict.side]
        if (!currentFile || currentFile.path !== conflict.path) return current
        return {
          ...current,
          [conflict.side]: {
            ...currentFile,
            content: payload.content,
            hash: result.hash,
            saveEnabled: true,
            title: undefined,
          },
        }
      })
      setConflict((current) => isSameSaveConflict(current, conflict) ? null : current)
      toast.success("Saved local changes")
      void mutateSkillDetail()
    } catch (error) {
      const nextConflict = conflictFromSaveError(error, conflict)
      if (nextConflict) {
        setConflict((current) => isSameSaveConflict(current, conflict) ? nextConflict : current)
        return
      }
      toast.error(errorMessage(error))
    }
  }, [conflict, doWriteSkillFile, mutateSkillDetail])

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
    void compileSkillById(currentSkillId)
  }, [compileSkillById, currentSkillId])

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
    // lintTick: bumped by the lint-event subscriber so a passed realtime lint re-derives
    // the stage. readLintStatus reads sessionStorage (not React state), so this read is
    // the dependency that re-runs the derivation when lint status changes.
    void lintTick
    const lint = readLintStatus(id)
    if (lint === "checking") return "compiling"
    if (lint === "failed") return "compile-fail"
    if (lint === "passed") return "compile-pass"
    return "idle"
  }, [compileStages, lintTick])

  const handlePredict = useCallback(async () => {
    if (!currentSkillId) return
    const targetSkillId = currentSkillId
    updateStage(targetSkillId, "predicting")
    try {
      const inputData = await resolveRunInput(targetSkillId, selectedTestInputId)
      const predict = await postPredictRun(targetSkillId, inputData)
      // N4 #4: the backend projects business success into PredictDiagnosticExport.status
      // ('success' | 'failed'); a 2xx response only means "predict ran", not "predict
      // passed". Gate Run on status — a `failed` predict must keep Run locked (the backend
      // also enforces this with 409 RUN_REQUIRES_PREDICT) and surface its diagnostics.
      if (predict.status !== "success") {
        // predict-fail: clear stale 🟡 logic-OK and show why the prediction failed.
        setRanAgentNodesBySkill((prev) => ({ ...prev, [targetSkillId]: new Set<string>() }))
        updateStage(targetSkillId, "predict-fail")
        const mismatchedPaths = predict.path_diff
          ? [...predict.path_diff.missing, ...predict.path_diff.extra]
          : []
        const detail = mismatchedPaths.length > 0
          ? `path diff: ${mismatchedPaths.join(", ")}`
          : "see predicted execution path"
        toast.error(`Predict failed: ${detail}`)
        return
      }
      // N4 atom #30: cache the AGENT nodes that ran so the canvas can show 🟡 logic-OK.
      // Only on predict-pass; predict-fail clears it (above) so stale 🟡 never lingers.
      setRanAgentNodesBySkill((prev) => ({
        ...prev,
        [targetSkillId]: ranAgentNodesFromPredict(predict),
      }))
      clearCopilotJudgeResult()
      updateStage(targetSkillId, "predict-pass")
      toast.success("Predict run completed successfully")
    } catch (error: unknown) {
      setRanAgentNodesBySkill((prev) => ({ ...prev, [targetSkillId]: new Set<string>() }))
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
      clearCopilotJudgeResult()
      setRunId(result.run_id)
      // F1: starting a run opens the timeline region to stream live trace events.
      setActivePanel("timeline")
      toast.success("Run started successfully")
    } catch (error) {
      updateStage(targetSkillId, "predict-pass")
      toast.error(error instanceof Error ? error.message : "Failed to start run")
    }
  }, [currentSkillId, deriveBuildStage, selectedTestInputId, updateStage, setRunId])

  // n4-trace#23 (P8 model-compare): fan a run out across the picked Settings roles.
  // Builds candidates from existing role names (candidatesFromRoleNames), calls the
  // real compare endpoint, then points the trace at the first candidate's spawned
  // run so the user immediately sees a candidate's stream while the others fill in.
  const [compareStarting, setCompareStarting] = useState(false)
  const handleStartCompare = useCallback(
    async (roleNames: string[]) => {
      if (!currentSkillId) return
      const candidates = candidatesFromRoleNames(roleNames)
      if (candidates.length === 0) {
        toast.error("Pick at least one role to compare")
        return
      }
      const targetSkillId = currentSkillId
      setCompareStarting(true)
      try {
        const inputData = await resolveRunInput(targetSkillId, selectedTestInputId)
        const group = await startCompareRun(targetSkillId, inputData, candidates)
        clearCopilotJudgeResult()
        setCompareGroupId(group.compare_group_id)
        setCompareRuns(group.runs)
        const first = group.runs[0] ?? null
        setCompareCandidateId(first?.candidate_id ?? null)
        setRunId(first?.metadata.run_id ?? null)
        setActivePanel("timeline")
        toast.success(`Comparing ${candidates.length} candidate${candidates.length === 1 ? "" : "s"}`)
      } catch (error) {
        toast.error(`Compare failed: ${errorMessage(error)}`)
      } finally {
        setCompareStarting(false)
      }
    },
    [currentSkillId, selectedTestInputId, setRunId],
  )

  // Switch the visible candidate: re-point the trace stream at that candidate's
  // spawned run (the per-candidate run id from the real compare group).
  const handleSelectCandidate = useCallback(
    (candidateId: string) => {
      const target = compareRuns.find((run) => run.candidate_id === candidateId)
      if (!target) return
      setCompareCandidateId(candidateId)
      clearCopilotJudgeResult()
      setRunId(target.metadata.run_id)
    },
    [compareRuns, clearCopilotJudgeResult],
  )

  // Poll the compare group while any candidate is still running so the tabs reflect
  // per-candidate completion / failure (metadata.status). Stops once all candidates
  // settle or the group is cleared.
  useEffect(() => {
    if (!currentSkillId || !compareGroupId) return undefined
    const anyRunning = compareRuns.some((run) => run.metadata.status === "running")
    if (!anyRunning) return undefined
    let cancelled = false
    const timer = window.setTimeout(() => {
      void getCompareGroup(currentSkillId, compareGroupId)
        .then((group) => {
          if (cancelled) return
          setCompareRuns(group.runs)
        })
        .catch((error) => {
          if (cancelled) return
          toast.error(`Could not refresh compare results: ${errorMessage(error)}`)
        })
    }, 2000)
    return () => {
      cancelled = true
      window.clearTimeout(timer)
    }
  }, [currentSkillId, compareGroupId, compareRuns])

  // The per-candidate Trace tabs (one per candidate_id, failure from metadata.status).
  const compareTabs = useMemo(() => compareTabsFromGroup(compareRuns), [compareRuns])

  // Headline lifecycle "resume": continue the active run from its last
  // checkpoint. The backend reports RESUME_CHECKPOINT_NOT_FOUND when a run has
  // nothing to continue (e.g. it already finished) — surfaced as a clear toast.
  const [resumeLoading, setResumeLoading] = useState(false)
  const [resumeValidity, setResumeValidity] = useState<ResumeValidityResponse | null>(null)
  const [resumeValidityLoading, setResumeValidityLoading] = useState(false)
  const [resumeValidityError, setResumeValidityError] = useState<string | null>(null)

  // N5 atom #3 (dirty-downstream-graying, spec F3): AUTO edit-watcher. The affected-downstream
  // graying must NOT wait for the user to select the failed node — it should follow an upstream
  // edit on its own. We anchor the resume-validity probe on the run's failed node (the natural
  // resume target) and re-run it whenever the skill content changes (skillDetail.files flips on
  // SWR revalidation after a save). The backend per-node slice (B1) keeps unrelated side-branches
  // out of `affected_downstream`, so graying stays scoped to nodes the edit actually reaches.
  const resumeAnchorId = useMemo(() => resumeAnchorNodeId(statusByNodeId), [statusByNodeId])
  const resumeAnchorCheckpoint = useMemo(
    () => (resumeAnchorId ? nodeResumeCheckpointFromEvents(runStream.events, resumeAnchorId, runId) : null),
    [resumeAnchorId, runStream.events, runId],
  )
  const skillContentSignature = skillDetail?.files
  useEffect(() => {
    let cancelled = false
    if (!shouldDeriveDirtyDownstream({ skillId: currentSkillId, runId, anchorNodeId: resumeAnchorId })) {
      setResumeValidity(null)
      setResumeValidityLoading(false)
      setResumeValidityError(null)
      return () => {
        cancelled = true
      }
    }
    setResumeValidityLoading(true)
    setResumeValidityError(null)
    // Non-null asserted: shouldDeriveDirtyDownstream guards skillId/runId/resumeAnchorId above.
    void getResumeValidity(currentSkillId!, runId!, {
      checkpointId: resumeAnchorCheckpoint?.checkpointId,
      checkpointNs: resumeAnchorCheckpoint?.checkpointNs,
      resumeFromNodeId: resumeAnchorId!,
    }).then((result) => {
      if (cancelled) return
      setResumeValidity(result)
    }).catch((error) => {
      if (cancelled) return
      setResumeValidity(null)
      setResumeValidityError(errorMessage(error))
    }).finally(() => {
      if (cancelled) return
      setResumeValidityLoading(false)
    })
    return () => {
      cancelled = true
    }
  }, [
    currentSkillId,
    runId,
    resumeAnchorId,
    resumeAnchorCheckpoint?.checkpointId,
    resumeAnchorCheckpoint?.checkpointNs,
    // Upstream-edit signal: SWR returns a fresh files object when the on-disk skill changes.
    skillContentSignature,
  ])

  const handleResume = useCallback(async () => {
    if (!currentSkillId || !runId) return
    setResumeLoading(true)
    try {
      const result = await resumeRun(currentSkillId, runId)
      setActivePanel("timeline")
      // Re-subscribe the trace stream to the resumed run (new id, or re-attach).
      clearCopilotJudgeResult()
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

  const handleSubmitHitlResponse = useCallback(async (request: TraceHitlResumeRequest) => {
    if (!currentSkillId || !runId) return
    setResumeLoading(true)
    try {
      const result = await resumeRun(currentSkillId, runId, hitlResumeOptionsFromRequest(request))
      setActivePanel("timeline")
      clearCopilotJudgeResult()
      setRunId(null)
      setRunId(result.run_id)
      toast.success("Run resumed with human input")
    } catch (error) {
      toast.error(`Resume failed: ${errorMessage(error)}`)
    } finally {
      setResumeLoading(false)
    }
  }, [clearCopilotJudgeResult, currentSkillId, runId, setRunId])

  const handleResumeEdgeDownstream = useCallback(async (options: ResumeRunOptions) => {
    if (!currentSkillId || !runId) return
    setResumeLoading(true)
    try {
      const result = await resumeRun(currentSkillId, runId, options)
      setActivePanel("timeline")
      clearCopilotJudgeResult()
      setRunId(null)
      setRunId(result.run_id)
      toast.success("Run resumed from tampered edge context")
    } catch (error) {
      toast.error(`Resume failed: ${errorMessage(error)}`)
    } finally {
      setResumeLoading(false)
    }
  }, [clearCopilotJudgeResult, currentSkillId, runId, setRunId])

  const handleResumeNode = useCallback(async (options: ResumeRunOptions) => {
    if (!currentSkillId || !runId) return
    setResumeLoading(true)
    try {
      const result = await resumeRun(currentSkillId, runId, options)
      setActivePanel("timeline")
      clearCopilotJudgeResult()
      setRunId(null)
      setRunId(result.run_id)
      toast.success("Run resumed from selected node")
    } catch (error) {
      toast.error(`Resume failed: ${errorMessage(error)}`)
    } finally {
      setResumeLoading(false)
    }
  }, [clearCopilotJudgeResult, currentSkillId, runId, setRunId])

  const handleHome = useCallback(() => {
    setSettingsOpen(false)
    onCloseSkill()
  }, [onCloseSkill])

  const hasOpenFile = Boolean(activeFileDetails.left || activeFileDetails.right)
  const currentCompileErrors = currentSkillId ? compileErrors[currentSkillId] ?? [] : []
  // N3 atom #4: the active lint diagnostics for the canvas/properties projection — the
  // first-screen SkillDetail sources (lint_result + manifest_errors) seed the initial badges,
  // and the realtime LintResult (lifted from the editor) overlays them once it resolves.
  const activeLint = useMemo(
    () => activeLintErrors({
      firstScreenLint: skillDetail?.lint_result?.errors,
      manifestErrors: skillDetail?.manifest_errors,
      realtime: realtimeLint?.errors,
    }),
    [skillDetail?.lint_result, skillDetail?.manifest_errors, realtimeLint],
  )
  // N3 atom #4: feed the canvas node channel from BOTH manual Compile AND lint — the lint
  // diagnostics are adapted onto the CompileError shape the node tooltip renders, grouped by
  // node, and merged with the compile errors (neither dropped). Previously fed by Compile only.
  // n2-canvas#10 (data-gap-viz, PM 2026-06-20): also fold in the data-gap channel — each phase
  // input field the backend flagged `supplied=false` (graph_topology[].field_supply) becomes a
  // node conflict error, so a missing-blackboard-supply gap shows on the canvas node exactly like
  // a compile conflict (no checkbox UI, no red-X — selection stays in the i/o panel).
  const compileErrorsByNodeId = useMemo(() => {
    const compileByNode = compileErrorsByNode(currentSkillId ? compileErrors[currentSkillId] : [])
    const lintByNode = lintErrorsByNode(activeLint)
    const lintAsCompileByNode: Record<string, CompileError[]> = {}
    for (const [nodeId, errors] of Object.entries(lintByNode)) {
      lintAsCompileByNode[nodeId] = errors.map(lintErrorToCompileError)
    }
    const compileWithLint = mergeNodeErrors(compileByNode, lintAsCompileByNode)
    const dataGapByNode = dataGapErrorsByNode(skillDetail?.graph_topology)
    return mergeNodeErrors(compileWithLint, dataGapByNode)
  }, [activeLint, compileErrors, currentSkillId, skillDetail?.graph_topology])
  const goldenStateByNodeId = useMemo(
    () => goldenTriStateByNode(
      goldenBaselines,
      (currentSkillId ? ranAgentNodesBySkill[currentSkillId] : undefined) ?? new Set<string>(),
    ),
    [goldenBaselines, ranAgentNodesBySkill, currentSkillId],
  )
  // N5 atom #3 (dirty-downstream-graying, spec F3): the downstream node ids the
  // current resume-validity response says an upstream edit invalidated. Read
  // straight from the real `affected_downstream` slice the backend computed for
  // the node being resumed from, projected into a Set the canvas grays. Empty when
  // resume is clean / no node is being resumed (the validity effect nulls it then),
  // so unrelated branches stay normal.
  const dirtyDownstreamNodeIds = useMemo(
    () => dirtyDownstreamFromValidity(resumeValidity),
    [resumeValidity],
  )
  // Field-axis source for the Properties panel (N3 atom #5): the realtime lint diagnostics
  // carry the engine's nearest-field locator (field_path), so they are the field source the
  // moment a realtime lint has resolved; before that (or when lint is clean) we fall back to
  // the field-bearing manual-Compile errors mapped onto the same LintError shape. Either way
  // the panel reads one DTO with a field_path axis — no client-side field re-derivation.
  const propertiesFieldErrors = useMemo(() => {
    if (realtimeLint != null) {
      return realtimeLint.errors
    }
    return compileErrorsToFieldLintErrors(currentSkillId ? compileErrors[currentSkillId] : [])
  }, [compileErrors, currentSkillId, realtimeLint])

  return (
    <WorkspaceProvider value={contextValue}>
    <div className="flex h-screen w-screen flex-col overflow-hidden bg-background text-foreground">
      <Header
        skillId={currentSkillId}
        workspaceRoot={currentWorkspaceRoot}
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
          settingsOpen={settingsOpen}
          onSettingsToggle={() => setSettingsOpen((open) => !open)}
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
                className="min-w-[300px]"
              >
                <Panels
                  activePanel={activePanel}
                  skillId={currentSkillId}
                  workspaceRoot={currentWorkspaceRoot}
                  skillDetail={skillDetail}
                  selectedNode={selectedNode}
                  selectedNodeStatus={selectedNodeStatus}
                  selectedTestInputId={selectedTestInputId}
                  onSelectTestInput={setSelectedTestInputId}
                  onPhaseFileSave={handlePhaseFileSave}
                  runId={runId}
                  lintErrors={propertiesFieldErrors}
                  resumeValidity={resumeValidity}
                  resumeValidityLoading={resumeValidityLoading}
                  resumeValidityError={resumeValidityError}
                  traceEvents={runStream.events}
                  activeTracePhase={activeTracePhase}
                  onSelectTracePrompt={setPromptIndex}
                  traceCanCompare={Boolean(runId)}
                  traceCompareLoading={goldenDiff.loading}
                  onCompareToGolden={handleCompareToGolden}
                  onPromoteToGolden={handlePromoteToGolden}
                  onPromoteNode={handlePromoteNode}
                  traceCanResume={Boolean(runId)}
                  traceResumeLoading={resumeLoading}
                  onResumeRun={handleResume}
                  onResumeNode={runId ? handleResumeNode : undefined}
                  onSubmitHitlResponse={handleSubmitHitlResponse}
                  onResumeEdgeDownstream={runId ? handleResumeEdgeDownstream : undefined}
                  compareTabs={compareTabs}
                  activeCandidateId={compareCandidateId}
                  onSelectCandidate={handleSelectCandidate}
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
                  statusByNodeId={statusByNodeId}
                  compileErrorsByNodeId={compileErrorsByNodeId}
                  goldenStateByNodeId={goldenStateByNodeId}
                  errorMessageByNodeId={errorMessageByNodeId}
                  activeTracePhase={activeTracePhase}
                />
              ) : currentSkillId === null ? (
                <WelcomePage onSelectSkill={onSelectSkill} />
              ) : (
                <GraphCanvas
                  skillId={currentSkillId}
                  workspaceRoot={currentWorkspaceRoot}
                  skillDetail={skillDetail}
                  isLoading={isLoading}
                  error={skillDetailError}
                  selectedNodeId={selectedNodeId}
                  onNodeSelect={handleNodeSelect}
                  onPanelChange={setActivePanel}
                  onCreatePhase={handleCreatePhase}
                  onPersistConnection={handlePersistConnection}
                  onDisconnectConnection={handleDisconnectConnection}
                  onReconnectConnection={handleReconnectConnection}
                  onPhaseFileSave={handlePhaseFileSave}
                  statusByNodeId={statusByNodeId}
                  compileErrorsByNodeId={compileErrorsByNodeId}
                  goldenStateByNodeId={goldenStateByNodeId}
                  errorMessageByNodeId={errorMessageByNodeId}
                  dirtyDownstreamNodeIds={dirtyDownstreamNodeIds}
                  activeTracePhase={activeTracePhase}
                  runId={runId}
                  resumeNodeStatus={selectedNodeStatus}
                  resumeValidity={resumeValidity}
                  resumeValidityLoading={resumeValidityLoading}
                  resumeValidityError={resumeValidityError}
                  resumeLoading={resumeLoading}
                  onResumeNode={runId ? handleResumeNode : undefined}
                  onSubmitHitlResponse={handleSubmitHitlResponse}
                  hitlSubmitting={resumeLoading}
                />
              )}
              {currentSkillId && !settingsOpen ? (
                <>
                  <CompileErrorDrawer
                    errors={currentCompileErrors}
                    open={compileDrawerOpen && currentCompileErrors.length > 0}
                    onOpenChange={setCompileDrawerOpen}
                  />
                  <CenterActionBarWithCreate
                    stage={deriveBuildStage(currentSkillId)}
                    onCompile={handleCompile}
                    onPredict={handlePredict}
                    onRun={handleRun}
                    onCreatePhase={handleCreatePhase}
                  />
                  {/* n4-trace#23: launch a P8 model-compare run against Settings roles.
                      Same readiness gate as Run (needs a predict-passed skill). */}
                  <div className="absolute bottom-4 left-4 z-30">
                    <CompareRunDialog
                      disabled={deriveBuildStage(currentSkillId) !== "predict-pass" || compareStarting}
                      starting={compareStarting}
                      onStartCompare={handleStartCompare}
                    />
                  </div>
                </>
              ) : null}
              {goldenDiff.result && !settingsOpen ? (
                <div className="absolute inset-0 z-40 flex flex-col bg-background">
                  <div className="flex shrink-0 items-center justify-between border-b border-border px-4 py-2">
                    <span className="text-sm font-semibold text-foreground">Golden Diff</span>
                    <button
                      type="button"
                      onClick={handleCloseGoldenDiff}
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
                promptEvent={promptIndex != null
                  ? findPromptEvent(runStream.events.map((envelope) => envelope.payload), promptIndex)
                  : null}
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
                className="min-w-[340px]"
              >
                <CopilotPanel
                  skillId={currentSkillId}
                  workspaceRoot={currentWorkspaceRoot}
                  view={copilotJudgeRefs ? "eval" : "edit"}
                  judgeRefs={copilotJudgeRefs}
                  completedRunId={completedRunId}
                  onJudgePrepared={setCopilotJudgeResult}
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
        onOverwriteRetry={handleOverwriteRetry}
      />
    </div>
    </WorkspaceProvider>
  )
}

function languageForPath(path: string): string {
  if (path.endsWith(".json")) return "json"
  if (path.endsWith(".py")) return "python"
  return "markdown"
}

function shortHash(value: string): string {
  const [algorithm, digest] = value.split(":", 2)
  if (!algorithm || !digest) return value
  return `${algorithm}:${digest.slice(0, 8)}`
}
