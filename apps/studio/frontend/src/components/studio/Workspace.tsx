import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState, type CSSProperties } from "react"
import type { Connection } from "@xyflow/react"
import { toast } from "sonner"
import useSWR from "swr"
import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog"
import { ResizablePanel, ResizablePanelGroup } from "@/components/ui/resizable"
import { GraphCanvas, type ChildDetailPatch, type SkillGraphNodeData } from "@/components/GraphCanvas"
import { buildNodes } from "@/components/GraphCanvas/build-nodes"
import { CopilotPanel } from "@/components/copilot/copilot-panel"
import type { CliTerminalSession } from "@/components/copilot/cli-terminal-session"
import { CopilotFab } from "@/components/copilot/copilot-fab"
import { CopilotPanelMorph } from "@/components/copilot/copilot-panel-morph"
import { defaultFabPosition, headerLogoTarget, panelRect, type Point, type Rect } from "@/components/copilot/copilot-fab-geometry"
import { copilotFileActionEffects, type CopilotFileAction } from "@/components/copilot/patch-proposed-bubble"
import { PromptInspector } from "@/components/PromptInspector"
import { useCopilot } from "@/hooks/useCopilot"
import { findPromptEvent } from "@/utils/trace"
import { lintResultEvent, lintStatusEvent, readLintStatus, relintSkillFromDisk } from "@/hooks/useDebouncedLint"
import { useRunStream } from "@/hooks/useRunStream"
import { useGoldenDiff } from "@/hooks/useGoldenDiff"
import { STUDIO_TRUTH_SWR_CONFIG } from "@/hooks/studio-swr-policy"
import { archiveFeedbackForGitStatus, nextLocalHistoryRefreshKey, useLocalHistoryRevalidator, useRunHistoryProjection } from "@/hooks/useRunHistory"
import { useSkills } from "@/hooks/useSkills"
import { useStudioEventStream } from "@/hooks/useStudioEventStream"
import { DiffView } from "@/components/diff/DiffView"
import type { CopilotJudgeResponse, ResumeRunOptions } from "@/api/client"
import type { TraceHitlResumeRequest } from "@/components/TracePanel"
import { WelcomePage } from "@/components/welcome/WelcomePage"
import { compileSkill, fetcher, getCompareGroup, getResumeValidity, getRunDetail, getSkillDetail, putRuntimeArtifacts, resolveRunInput, serializeSkillGraph, startNodeCompareRun, writeSkillFile, postPredictRun, startRun, resumeRun } from "@/api/client"
import type { CompareCandidateRun, EngineErrorPayload, GoldenBaseline, GraphTopologyItem, LintResult, PredictDiagnosticExport, ResumeValidityResponse, RuntimeArtifactRow, RuntimeConfig, SerializableGraphPhaseRef, SkillDetail } from "@/api/types"
import { compareTabsFromGroup } from "./run-compare"
import { isTauriRuntime } from "@/config/runtime"
import { CURRENT_SCHEMA_VERSION } from "@/config/schema"
import { deleteWorkspacePath, listWorkspaceDir, moveWorkspacePath, readWorkspaceFile, writeWorkspaceFile } from "@/lib/tauri"
import { errorDiagnosticDetails, errorMessage } from "@/utils/errors"
import type { CompileError } from "@/api/types"
import { connectPhaseRefs, createPhaseDraft, disconnectPhaseRefs, orphanPhaseDirectoryIds, phaseDirectoryPath, phaseFilePath, phaseRefsFromSkillDetail, reconnectPhaseRefs, removePhaseRefs, renamePhaseRefs, type NewPhaseKind } from "@/components/GraphCanvas/canvas-authoring"
import { autoCreatedSubgraphChildDir, defaultSubgraphChildDir, subgraphChildScaffoldFiles } from "@/components/studio/subgraph-scaffold"
import { isReadOnlySkillError, type ChildSaveTarget } from "@/components/GraphCanvas/drill-edit"
import { actionFilePath, actionStubContent, applyActionsList, isValidActionName, readActionsList } from "@/components/studio/panels/phase-actions"
import { applyPhaseValidator } from "@/components/studio/panels/phase-frontmatter"
import { validatorFilePath, validatorStubContent } from "@/components/studio/panels/phase-validator"
import { sha256Hex } from "@/lib/hash"
import { CenterActionBar, type SkillBuildStage } from "./center-action-bar"
import { deriveNodeErrorMessages, deriveNodeStatuses } from "./node-status"
import { dirtyDownstreamFromValidity, nodeResumeCheckpointFromEvents, resumeAnchorNodeId, shouldDeriveDirtyDownstream } from "./node-resume"
import { hitlResumeOptionsFromRequest } from "./resume-options"
import { activeLintErrors, compileErrorsByNode, lintErrorToCompileError, lintErrorsByNode, mergeNodeErrors } from "./node-compile-errors"
import { goldenTriStateByNode, ranAgentNodesFromPredict } from "./node-golden"
import { fieldDiagnosticsForPanels } from "./field-compile-errors"
import { CompileErrorDrawer } from "./CompileErrorDrawer"
import { ConflictDialog } from "./ConflictDialog"
import { Header } from "./Header"
import { Panels } from "./Panels"
import type { IoBoundarySelection } from "./panels/io-target"
import { SettingsPageView, useSettingsPageController, type SettingsTab } from "./SettingsPage"
import { Toolbar, type PanelKind } from "./Toolbar"
import { WorkspaceEditorOverlay } from "./WorkspaceEditorOverlay"
import { WorkspaceLeftPanelOverlay } from "./WorkspaceLeftPanelOverlay"
import {
  RIGHT_PANEL_DEFAULT_RATIO,
  WorkspaceRightPanelOverlay,
  rightPanelRatioFromPx,
  rightPanelWidthPx,
} from "./WorkspaceRightPanelOverlay"
import { applyPhaseName } from "./panels/phase-frontmatter"
import { useSkillSubgraphMembershipTree } from "./panels/use-subgraph-membership-tree"
import { useWorkspaceDirectoryTree } from "./panels/use-workspace-directory-tree"
import type { FileMeta, FileOpenInput } from "./file-types"
import { phaseIdFromFilePath } from "./panels/asset-tree-target"
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

const MINI_MAP_TOOL_SPACE_THRESHOLD_PX = 300

function isIoDocumentPath(path: string) {
  return path === "GRAPH.md" || /^phases\/[^/]+\/SUBGRAPH\.md$/.test(path)
}

function diagnosticError(message: string, details: string[] = []): CompileError {
  return {
    file: null,
    line: null,
    field: null,
    severity: "fatal",
    message,
    ...(details.length > 0 ? { details } : {}),
  }
}

function normalizeDiagnosticError(value: unknown): CompileError | null {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    return null
  }
  const candidate = value as Partial<CompileError>
  if (typeof candidate.message !== "string" || candidate.message.length === 0) {
    return null
  }
  return {
    file: typeof candidate.file === "string" ? candidate.file : null,
    line: typeof candidate.line === "number" ? candidate.line : null,
    field: typeof candidate.field === "string" ? candidate.field : null,
    severity: candidate.severity === "warning" ? "warning" : "fatal",
    message: candidate.message,
    error_code: typeof candidate.error_code === "string" ? candidate.error_code : null,
    details: Array.isArray(candidate.details)
      ? candidate.details.filter((item): item is string => typeof item === "string")
      : undefined,
  }
}

function requestDiagnosticErrors(error: unknown): CompileError[] {
  interface DiagnosticErrorResponse {
    response?: {
      data?: {
        code?: string
        errors?: unknown[]
      }
    }
  }
  const responseData = (error as DiagnosticErrorResponse)?.response?.data
  if (responseData?.code === "compile_failed" && Array.isArray(responseData.errors)) {
    const errors = responseData.errors
      .map((item) => normalizeDiagnosticError(item))
      .filter((item): item is CompileError => item !== null)
    if (errors.length > 0) {
      return errors
    }
  }
  return [diagnosticError(errorMessage(error), errorDiagnosticDetails(error))]
}

function engineDiagnosticDetails(payload: EngineErrorPayload): string[] {
  const details = [
    payload.phase_id ? `phase: ${payload.phase_id}` : null,
    payload.field_path ? `field: ${payload.field_path}` : null,
    payload.skill_id ? `skill: ${payload.skill_id}` : null,
    payload.source_path ? `source: ${payload.source_path}` : null,
    payload.doc_link ? `doc: ${payload.doc_link}` : null,
    Object.keys(payload.details).length > 0 ? `details:\n${JSON.stringify(payload.details, null, 2)}` : null,
  ]
  return details.filter((item): item is string => item !== null)
}

function engineDiagnosticError(payload: EngineErrorPayload): CompileError {
  const details = engineDiagnosticDetails(payload)
  return {
    file: payload.source_path,
    line: null,
    field: payload.field_path,
    severity: payload.level?.toLowerCase() === "warn" || payload.level?.toLowerCase() === "warning" ? "warning" : "fatal",
    message: `${payload.code} - ${payload.message}`,
    error_code: payload.code,
    ...(details.length > 0 ? { details } : {}),
  }
}

function predictEngineDiagnosticErrors(predict: PredictDiagnosticExport): CompileError[] {
  const diagnostics = [predict.error ?? null, ...(predict.diagnostics ?? [])].filter(
    (item): item is EngineErrorPayload => item !== null,
  )
  const seen = new Set<string>()
  const errors: CompileError[] = []
  for (const item of diagnostics) {
    const key = `${item.code}\0${item.message}\0${item.phase_id ?? ""}\0${item.field_path ?? ""}\0${item.source_path ?? ""}`
    if (seen.has(key)) continue
    seen.add(key)
    errors.push(engineDiagnosticError(item))
  }
  if (predict.diagnostics_truncated && errors.length > 0) {
    const first = errors[0]
    first.details = [...(first.details ?? []), "diagnostics were truncated by the backend"]
  }
  return errors
}

function predictStatusFailureErrors(predict: PredictDiagnosticExport): CompileError[] {
  const diagnosticErrors = predictEngineDiagnosticErrors(predict)
  if (diagnosticErrors.length > 0) {
    return diagnosticErrors
  }
  const diff = predict.path_diff
  if (!diff) {
    return [diagnosticError("Predict finished with failed status, but the backend did not return path-diff details.")]
  }
  const details = [
    diff.missing.length > 0 ? `missing: ${diff.missing.join(", ")}` : null,
    diff.extra.length > 0 ? `extra: ${diff.extra.join(", ")}` : null,
    diff.order_mismatch ? "order mismatch" : null,
    `expected: ${diff.expected_path.join(" -> ") || "(empty)"}`,
    `actual: ${diff.actual_path.join(" -> ") || "(empty)"}`,
  ].filter((item): item is string => item !== null)
  return [diagnosticError(`Predicted execution path did not match (${details.join("; ")}).`)]
}

function skillDetailWithFile(detail: SkillDetail, path: string, content: string): SkillDetail {
  return {
    ...detail,
    files: {
      ...(detail.files ?? {}),
      [path]: content,
    },
  }
}

function skillDetailWithRenamedPhase(
  detail: SkillDetail,
  phases: SerializableGraphPhaseRef[],
  options: {
    oldPhaseId: string
    nextPhaseId: string
    oldFilePath: string
    newFilePath: string
    renamedContent: string
    graphContent: string
  },
): SkillDetail {
  const files = { ...(detail.files ?? {}) }
  delete files[options.oldFilePath]
  files[options.newFilePath] = options.renamedContent
  files["GRAPH.md"] = options.graphContent

  const filePaths = { ...detail.file_paths }
  if (options.oldFilePath in filePaths) {
    filePaths[options.newFilePath] = filePaths[options.oldFilePath]
    delete filePaths[options.oldFilePath]
  }

  const existingTopologyById = new Map((detail.graph_topology ?? []).map((phase) => [phase.id, phase]))
  const graphTopology: GraphTopologyItem[] = phases.map((phase) => {
    const existing = existingTopologyById.get(phase.id)
      ?? (phase.id === options.nextPhaseId ? existingTopologyById.get(options.oldPhaseId) : undefined)
    return {
      ...existing,
      id: phase.id,
      src: phase.src,
      depends_on: phase.depends_on,
      mode: phase.mode,
      ...(phase.output === true ? { output: true } : { output: undefined }),
    }
  })

  return {
    ...detail,
    manifest: detail.manifest.schema_version === CURRENT_SCHEMA_VERSION
      ? { ...detail.manifest, phases: phases.map((phase) => phase.id) }
      : detail.manifest,
    graph_topology: graphTopology,
    file_paths: filePaths,
    files,
  }
}

function selectedNodeMatchesTarget(
  node: { id: string; data: SkillGraphNodeData } | null,
  target: ChildSaveTarget,
): node is { id: string; data: SkillGraphNodeData } {
  return Boolean(
    node
    && node.data.skillId === target.skillId
    && (node.data.workspaceRoot ?? null) === target.workspaceRoot,
  )
}

export function hasMiniMapToolSpace(
  centerActionBarRect: Pick<DOMRect, "right"> | null,
  rightOverlayRect: Pick<DOMRect, "left"> | null,
): boolean {
  if (!centerActionBarRect || !rightOverlayRect) {
    return true
  }
  return rightOverlayRect.left - centerActionBarRect.right >= MINI_MAP_TOOL_SPACE_THRESHOLD_PX
}

function useMiniMapToolSpace(copilotOpen: boolean, currentSkillId: string | null, settingsOpen: boolean): boolean {
  const measurementKey = copilotOpen && currentSkillId && !settingsOpen ? currentSkillId : null
  const [measurement, setMeasurement] = useState<{ key: string | null; hasSpace: boolean }>({
    key: null,
    hasSpace: true,
  })

  useLayoutEffect(() => {
    if (!measurementKey) {
      setMeasurement((current) => (
        current.key === null && current.hasSpace
          ? current
          : { key: null, hasSpace: true }
      ))
      return
    }

    let frameId = 0
    const measure = () => {
      frameId = 0
      const actionBar = document.querySelector<HTMLElement>('[data-studio-center-action-bar="true"]')
      const rightOverlay = document.querySelector<HTMLElement>('[data-studio-right-overlay="true"]')
      setMeasurement({
        key: measurementKey,
        hasSpace: hasMiniMapToolSpace(
          actionBar?.getBoundingClientRect() ?? null,
          rightOverlay?.getBoundingClientRect() ?? null,
        ),
      })
    }
    const scheduleMeasure = () => {
      if (frameId === 0) {
        frameId = window.requestAnimationFrame(measure)
      }
    }

    scheduleMeasure()
    window.addEventListener("resize", scheduleMeasure)
    const observer = typeof ResizeObserver === "undefined" ? null : new ResizeObserver(scheduleMeasure)
    const actionBar = document.querySelector<HTMLElement>('[data-studio-center-action-bar="true"]')
    const rightOverlay = document.querySelector<HTMLElement>('[data-studio-right-overlay="true"]')
    if (actionBar) observer?.observe(actionBar)
    if (rightOverlay) observer?.observe(rightOverlay)

    return () => {
      window.removeEventListener("resize", scheduleMeasure)
      observer?.disconnect()
      if (frameId !== 0) {
        window.cancelAnimationFrame(frameId)
      }
    }
  }, [measurementKey])

  if (!measurementKey) {
    return true
  }

  return measurement.key === measurementKey ? measurement.hasSpace : false
}

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

/**
 * Optimistic-concurrency hash for a GRAPH.md snapshot.
 *
 * The backend reads GRAPH.md through a pipeline that normalizes line endings to
 * LF before hashing (verified: serialize's `current_hash` == sha256 of the
 * LF-normalized file). On Windows, git's autocrlf checks the file out as CRLF,
 * so hashing the RAW bytes yields a digest that never matches the backend's —
 * and every canvas save 409s with snapshot_conflict. Normalizing to LF here is
 * the single source of agreement between the two sides.
 */
function graphSnapshotHash(content: string): Promise<string> {
  return sha256Hex(normalizeWorkspaceText(content))
}

export function Workspace({ skillId, onSelectSkill, onCloseSkill }: WorkspaceProps) {
  const [navStack, setNavStack] = useState<string[]>(() => (skillId ? [skillId] : []))
  const [activePanel, setActivePanel] = useState<PanelKind | null>(skillId ? "assets" : null)
  const [copilotOpen, setCopilotOpen] = useState(Boolean(skillId))
  // User-resizable overlay sizes. The editor height is null until first drag
  // so it keeps the responsive CSS default (min(52%, 34rem)) until then. These
  // feed both the overlay sizes and the canvas safe-area vars, so fit-view tracks.
  const [leftPanelWidth, setLeftPanelWidth] = useState(384)
  // P-6: the copilot panel's width truth is a share of the canvas host, so it
  // widens with the window instead of staying a fixed pixel count. Drags from
  // the handle come in as px and are converted back to a ratio against the
  // host width they were made at.
  const [copilotWidthRatio, setCopilotWidthRatio] = useState(RIGHT_PANEL_DEFAULT_RATIO)
  const [hostWidth, setHostWidth] = useState<number | null>(null)
  // FAB position on the canvas; null = default top-right anchor. Persists across
  // open/close within the session (survives the panel collapse animation).
  const [fabPosition, setFabPosition] = useState<Point | null>(null)
  // The CLI session belongs to the workspace, not to the copilot panel: the
  // panel unmounts on every collapse, and a session parked there would take the
  // running CLI down with it (ah-orchestration-design.md §10 D3 — collapsing is
  // a detach at most, never a shutdown).
  const [cliSession, setCliSession] = useState<CliTerminalSession | null>(null)
  const hostRef = useRef<HTMLDivElement>(null)
  // Callback ref, not a mount effect: the host div only exists while a skill is
  // open (the welcome view renders without it), so the observer must attach the
  // moment the node appears — a []-deps effect would run once pre-attach and
  // never observe anything.
  const hostObserverCleanup = useRef<(() => void) | null>(null)
  const observeHost = useCallback((node: HTMLDivElement | null) => {
    hostRef.current = node
    hostObserverCleanup.current?.()
    hostObserverCleanup.current = null
    if (!node || typeof ResizeObserver === "undefined") return
    let frameId = 0
    const measure = () => {
      frameId = 0
      setHostWidth(node.clientWidth)
    }
    const scheduleMeasure = () => {
      if (frameId === 0) {
        frameId = window.requestAnimationFrame(measure)
      }
    }
    measure()
    const observer = new ResizeObserver(scheduleMeasure)
    observer.observe(node)
    hostObserverCleanup.current = () => {
      observer.disconnect()
      if (frameId !== 0) {
        window.cancelAnimationFrame(frameId)
      }
    }
  }, [])
  const copilotWidth = rightPanelWidthPx(copilotWidthRatio, hostWidth)
  // Active FAB↔panel container-transform morph, or null. Exactly one of the
  // FAB / morph / panel renders at a time, gated on this + copilotOpen.
  const [morph, setMorph] = useState<{ mode: "open" | "close"; fab: Point; logo: Point; panel: Rect } | null>(null)
  const [editorHeight, setEditorHeight] = useState<number | null>(null)
  const currentWorkspaceSelection = navStack.at(-1) ?? null
  const currentWorkspaceIdentity = useMemo(
    () => resolveWorkspaceIdentity(currentWorkspaceSelection),
    [currentWorkspaceSelection],
  )
  const currentSkillId = currentWorkspaceIdentity.skillId
  const currentWorkspaceRoot = currentWorkspaceIdentity.workspaceRoot
  useEffect(() => {
    // A session belongs to ONE workspace; leaving that workspace ends the local
    // terminal client (the ah runtime keeps running, §10 D3).
    return () => {
      setCliSession((current) => {
        current?.detach()
        return null
      })
    }
  }, [currentWorkspaceRoot])
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
  const [settingsInitialTab, setSettingsInitialTab] = useState<SettingsTab>("general")
  const settingsController = useSettingsPageController()
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null)
  const [selectedNode, setSelectedNode] = useState<{ id: string; data: SkillGraphNodeData } | null>(null)
  // Which boundary pseudo-node (Input / Output) is selected, so the i/o panel can
  // scope to that role. Mutually exclusive with a phase selection: selecting a
  // boundary clears the phase, and vice-versa (PM 2026-07-03).
  const [ioBoundary, setIoBoundary] = useState<IoBoundarySelection>(null)
  const [childDetailPatch, setChildDetailPatch] = useState<ChildDetailPatch | null>(null)
  const [selectedEdge, setSelectedEdge] = useState<SelectedEdge | null>(null)
  const [inFlight, setInFlight] = useState<Partial<Record<EditorSide, boolean>>>({})
  const inFlightRef = useRef<Partial<Record<EditorSide, boolean>>>({})
  const [conflict, setConflict] = useState<SaveConflict | null>(null)
  const { skillDetail, skillDetailError, mutateSkillDetail } = useSkills(currentSkillId)
  const { data: runtimeConfig, mutate: mutateRuntimeConfig } = useSWR<RuntimeConfig>(
    currentSkillId ? `/skills/${currentSkillId}/runtime-config` : null,
    fetcher,
    STUDIO_TRUTH_SWR_CONFIG,
  )
  const assetDirectoryTree = useWorkspaceDirectoryTree({
    workspaceRoot: currentWorkspaceRoot ?? currentSkillId,
    skillId: currentSkillId,
    skillDetail,
    enabled: Boolean(currentSkillId),
  })
  const assetSubgraphTree = useSkillSubgraphMembershipTree({
    skillDetail,
    workspaceRoot: currentWorkspaceRoot ?? currentSkillId,
    enabled: Boolean(currentSkillId),
  })
  // Read the asset tree through a ref inside the WS file-change handler so live
  // tree refresh doesn't add the (frequently-changing) tree to that effect's deps
  // and thrash the WebSocket connection.
  const assetDirectoryTreeRef = useRef(assetDirectoryTree)
  assetDirectoryTreeRef.current = assetDirectoryTree
  const isLoading = useMemo(() => Boolean(currentSkillId && !skillDetail && !skillDetailError), [skillDetail, skillDetailError, currentSkillId])
  const [compileStages, setCompileStages] = useState<Record<string, SkillBuildStage>>({})
  const [compileErrors, setCompileErrors] = useState<Record<string, CompileError[]>>({})
  const [compileDrawerOpen, setCompileDrawerOpen] = useState(false)
  const [predictErrors, setPredictErrors] = useState<CompileError[]>([])
  const [predictDrawerOpen, setPredictDrawerOpen] = useState(false)
  const [runErrors, setRunErrors] = useState<CompileError[]>([])
  const [runDrawerOpen, setRunDrawerOpen] = useState(false)
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

  const handleRuntimeArtifactsSave = useCallback(async (artifacts: RuntimeArtifactRow[]): Promise<string | null> => {
    if (!currentSkillId) {
      return "No active workspace"
    }
    try {
      const updated = await putRuntimeArtifacts(currentSkillId, artifacts)
      await mutateRuntimeConfig(updated, { revalidate: false })
      return null
    } catch (error) {
      return errorMessage(error)
    }
  }, [currentSkillId, mutateRuntimeConfig])

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
  // consumes; Workspace only holds a revalidator and does not subscribe to the
  // Local History list, so opening a skill does not cold-load `/history`.
  const { refresh: refreshLocalHistory } = useLocalHistoryRevalidator(currentSkillId)
  const { projectRun } = useRunHistoryProjection(currentSkillId)
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
    if (!feedbackKey || !completedRunId || !currentSkillId) {
      return
    }
    const targetSkillId = currentSkillId
    archiveFeedbackRunRef.current = feedbackKey
    let cancelled = false
    const announceArchiveOutcome = async () => {
      try {
        const detail = await getRunDetail(targetSkillId, completedRunId)
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
  }, [completedRunId, currentSkillId])

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
    STUDIO_TRUTH_SWR_CONFIG,
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

  const copilot = useCopilot(currentSkillId, currentWorkspaceRoot)

  useEffect(() => {
    inFlightRef.current = inFlight
  }, [inFlight])

  const handleNodeSelect = (node: { id: string; data: SkillGraphNodeData }) => {
    setSelectedNodeId(node.id)
    setSelectedNode(node)
    setSelectedEdge(null)
    setIoBoundary(null)
  }

  const handleNodeDeselect = () => {
    setSelectedNodeId(null)
    setSelectedNode(null)
    setSelectedEdge(null)
    setIoBoundary(null)
  }

  // Selecting a boundary pseudo-node (Input / Output): drop any phase selection
  // and record which boundary so the i/o panel scopes to input- or output-only.
  const handleBoundarySelect = (which: 'input' | 'output') => {
    setSelectedNodeId(null)
    setSelectedNode(null)
    setSelectedEdge(null)
    setIoBoundary(which)
  }

  // Reverse of the node→file reveal: clicking a node-definition file in the
  // Assets tree selects its canvas node. Only the open skill's own graph is on
  // the root canvas, so files belonging to a child/subgraph skill are skipped.
  // buildNodes is reused (the canvas's own builder) so the selected node's data
  // matches a real click — no hand-rolled node shape that could drift.
  // Center the canvas on a root-graph node when its file is clicked (file-driven
  // only — a nonce-bumped request GraphCanvas pans to, leaving selection alone).
  const focusNodeNonceRef = useRef(0)
  const [focusNodeRequest, setFocusNodeRequest] = useState<{ nodeId: string; nonce: number } | null>(null)
  const handleRevealNodeForFile = useCallback((file: FileMeta) => {
    if (!currentSkillId || !skillDetail) return
    if (file.skillId && file.skillId !== currentSkillId) return
    const phaseId = phaseIdFromFilePath(file.path)
    if (!phaseId) return
    const nodes = buildNodes(currentSkillId, skillDetail, new Set(), () => {}, {}, {}, {}, {}, {}, currentWorkspaceRoot ?? null)
    const match = nodes.find(
      (node) => node.type === "skill" && (node.data as SkillGraphNodeData).phaseId === phaseId,
    )
    if (!match) return
    setSelectedNodeId(phaseId)
    setSelectedNode({ id: phaseId, data: match.data as SkillGraphNodeData })
    setSelectedEdge(null)
    focusNodeNonceRef.current += 1
    setFocusNodeRequest({ nodeId: phaseId, nonce: focusNodeNonceRef.current })
  }, [currentSkillId, currentWorkspaceRoot, skillDetail])

  // Reveal something inside a subgraph's inline canvas topology, driven by an
  // Assets file click. Forwarded to GraphCanvas as a nonce-bumped request so it
  // can expand (+ optionally select) once the (possibly nested) preview node
  // resolves: `select-child` for a child node file, `expand-subgraph` for the
  // subgraph's own GRAPH.md (which also deselects any node).
  const revealNonceRef = useRef(0)
  const [revealRequest, setRevealRequest] = useState<
    { phaseChain: string[]; intent: "select-child" | "expand-subgraph"; nonce: number } | null
  >(null)
  const handleRevealSubgraphChildNode = useCallback((phaseChain: string[]) => {
    if (phaseChain.length < 2) return
    revealNonceRef.current += 1
    setRevealRequest({ phaseChain, intent: "select-child", nonce: revealNonceRef.current })
  }, [])
  const handleRevealSubgraphGraph = useCallback((phaseChain: string[]) => {
    if (phaseChain.length < 1) return
    // Opening a subgraph's GRAPH.md is a graph-level action: drop the node
    // selection so the editor/Properties reflect the graph, not a stale node.
    setSelectedNodeId(null)
    setSelectedNode(null)
    setSelectedEdge(null)
    revealNonceRef.current += 1
    setRevealRequest({ phaseChain, intent: "expand-subgraph", nonce: revealNonceRef.current })
  }, [])

  const toOpenFile = useCallback(async (fileOrPath: FileOpenInput): Promise<OpenFile | null> => {
    if (!currentSkillId) return null
    const currentFiles = skillDetail?.files ?? {}
    const isStringPath = typeof fileOrPath === "string"
    const requestedSkillId = isStringPath ? currentSkillId : fileOrPath.skillId ?? currentSkillId
    const rawPath = isStringPath ? fileOrPath : fileOrPath.path
    const requestedPrefix = `${requestedSkillId}/`
    const currentPrefix = `${currentSkillId}/`
    const path = rawPath.startsWith(requestedPrefix)
      ? rawPath.slice(requestedPrefix.length)
      : rawPath.startsWith(currentPrefix)
        ? rawPath.slice(currentPrefix.length)
        : rawPath
    const fileSkillId = requestedSkillId
    const fileWorkspaceRoot = isStringPath ? currentWorkspaceRoot : fileOrPath.workspaceRoot ?? currentWorkspaceRoot
    const hasCurrentFile = Object.prototype.hasOwnProperty.call(currentFiles, path)
    let content = isStringPath ? (hasCurrentFile ? currentFiles[path] : undefined) : fileOrPath.content
    let hash = isStringPath ? null : fileOrPath.hash ?? null
    if (content === undefined) {
      if (isTauriRuntime()) {
        const nativeFile = await readWorkspaceFile(fileWorkspaceRoot ?? fileSkillId, path)
        content = nativeFile.content
        hash = nativeFile.hash
      } else {
        content = hasCurrentFile ? currentFiles[path] : ""
      }
    }
    const language = isStringPath ? languageForPath(path) : fileOrPath.language ?? languageForPath(path)
    return {
      path,
      language,
      content,
      hash: hash ?? await sha256Hex(content),
      savedContent: content,
      dirty: false,
      skillId: fileSkillId,
      workspaceRoot: fileWorkspaceRoot,
      title: isStringPath ? undefined : fileOrPath.title,
      saveEnabled: isStringPath ? undefined : fileOrPath.saveEnabled,
    }
  }, [currentSkillId, currentWorkspaceRoot, skillDetail?.files])

  const handleFileOpen = useCallback((fileOrPath: FileOpenInput, side?: EditorSide) => {
    setSettingsOpen(false)
    void toOpenFile(fileOrPath)
      .then((file) => {
        if (!file) return
        setActiveFileDetails((current) => {
          const targetSide = side ?? (splitMode && current.left ? "right" : "left")
          return { ...current, [targetSide]: file }
        })
      })
      .catch((error) => {
        toast.error(errorMessage(error))
      })
  }, [splitMode, toOpenFile])

  const openSettings = useCallback((tab: SettingsTab = "general") => {
    setSettingsInitialTab(tab)
    setSettingsOpen(true)
  }, [])

  const handleSettingsToggle = useCallback(() => {
    if (settingsOpen) {
      setSettingsOpen(false)
      return
    }
    openSettings("general")
  }, [openSettings, settingsOpen])

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

  // Close every open file editor (both split sides) — used when clicking empty
  // canvas clears the workspace.
  const closeAllEditors = useCallback(() => {
    setActiveFileDetails({})
    setInFlight({})
    setSplitMode(false)
  }, [])

  // Header title: single-click clears the node selection and shows the
  // graph.md / global panel; double-click opens graph.md in the editor.
  const handleTitleSelect = useCallback(() => {
    setSelectedNodeId(null)
    setSelectedNode(null)
    setSelectedEdge(null)
    setActivePanel("properties")
  }, [])
  const handleTitleEdit = useCallback(() => {
    if (!currentSkillId) return
    handleFileOpen({
      path: "GRAPH.md",
      skillId: currentSkillId,
      workspaceRoot: currentWorkspaceRoot,
      language: "markdown",
      saveEnabled: true,
    })
  }, [currentSkillId, currentWorkspaceRoot, handleFileOpen])

  const updateFileContent = useCallback((side: EditorSide, content: string) => {
    setActiveFileDetails((current) => {
      const file = current[side]
      if (!file) return current
      const savedContent = file.savedContent ?? file.content
      return {
        ...current,
        [side]: {
          ...file,
          content,
          savedContent,
          dirty: content !== savedContent,
        },
      }
    })
  }, [])

  const markFileSaved = useCallback((side: EditorSide, hash: string) => {
    setActiveFileDetails((current) => {
      const file = current[side]
      return file
        ? {
            ...current,
            [side]: {
              ...file,
              hash,
              savedContent: file.content,
              dirty: false,
            },
          }
        : current
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
    options: { createIfAbsent?: boolean } = {},
  ) => {
    const targetSkillId = override?.skillId ?? currentSkillId
    const targetWorkspaceRoot = override ? override.workspaceRoot : currentWorkspaceRoot
    if (!targetSkillId) {
      throw new Error("No active workspace")
    }
    if (isTauriRuntime()) {
      return await writeWorkspaceFile(targetWorkspaceRoot ?? targetSkillId, path, content, expectedHash ?? null, options)
    }
    return await writeSkillFile(targetSkillId, path, content, expectedHash)
  }, [currentSkillId, currentWorkspaceRoot])

  const doDeleteWorkspacePath = useCallback(async (
    path: string,
    override?: { skillId: string; workspaceRoot: string | null },
  ) => {
    const targetSkillId = override?.skillId ?? currentSkillId
    const targetWorkspaceRoot = override ? override.workspaceRoot : currentWorkspaceRoot
    if (!targetSkillId) {
      throw new Error("No active workspace")
    }
    if (!isTauriRuntime()) {
      throw new Error("Deleting phase folders requires the desktop runtime")
    }
    await deleteWorkspacePath(targetWorkspaceRoot ?? targetSkillId, path)
  }, [currentSkillId, currentWorkspaceRoot])

  const doReadWorkspaceFile = useCallback(async (
    path: string,
    override?: { skillId: string; workspaceRoot: string | null },
  ) => {
    const targetSkillId = override?.skillId ?? currentSkillId
    const targetWorkspaceRoot = override ? override.workspaceRoot : currentWorkspaceRoot
    if (!targetSkillId) {
      throw new Error("No active workspace")
    }
    if (!isTauriRuntime()) {
      throw new Error("Reading workspace files requires the desktop runtime")
    }
    return await readWorkspaceFile(targetWorkspaceRoot ?? targetSkillId, path)
  }, [currentSkillId, currentWorkspaceRoot])

  const handlePhaseFileRead = useCallback(async (
    { path }: { path: string },
    target?: { skillId: string; workspaceRoot: string | null },
  ) => {
    return await doReadWorkspaceFile(path, target)
  }, [doReadWorkspaceFile])

  // Optimistic-concurrency hash for canvas serialize/save, read from the ONE
  // source of truth: the GRAPH.md file on disk. native-fs D10/D12 makes the Rust
  // native command the local read authority, so the parent graph and a drilled
  // child read the SAME way — only `override` (which skill) differs, so their
  // behaviour is identical (no "trusted parent / untrusted child" split). Line
  // endings are normalized to LF (via normalizeWorkspaceText) so the hash matches
  // the backend serializer, which reads GRAPH.md through Python text mode → LF.
  // The browser dev/test runtime has no native-fs, so fall back to the fetched
  // in-memory copy (which the backend already served as LF).
  const readGraphHash = useCallback(async (
    editDetail: SkillDetail,
    override?: { skillId: string; workspaceRoot: string | null },
  ): Promise<string | null> => {
    if (isTauriRuntime()) {
      try {
        const graph = await doReadWorkspaceFile("GRAPH.md", override)
        return await graphSnapshotHash(graph.content)
      } catch {
        return null
      }
    }
    const graphContent = editDetail.files?.["GRAPH.md"]
    return graphContent === undefined ? null : await graphSnapshotHash(graphContent)
  }, [doReadWorkspaceFile])

  const doListWorkspaceDir = useCallback(async (
    path: string,
    override?: { skillId: string; workspaceRoot: string | null },
  ) => {
    const targetSkillId = override?.skillId ?? currentSkillId
    const targetWorkspaceRoot = override ? override.workspaceRoot : currentWorkspaceRoot
    if (!targetSkillId) {
      throw new Error("No active workspace")
    }
    if (!isTauriRuntime()) {
      throw new Error("Listing workspace dirs requires the desktop runtime")
    }
    return await listWorkspaceDir(targetWorkspaceRoot ?? targetSkillId, path)
  }, [currentSkillId, currentWorkspaceRoot])

  const doMoveWorkspacePath = useCallback(async (
    from: string,
    to: string,
    override?: { skillId: string; workspaceRoot: string | null },
  ) => {
    const targetSkillId = override?.skillId ?? currentSkillId
    const targetWorkspaceRoot = override ? override.workspaceRoot : currentWorkspaceRoot
    if (!targetSkillId) {
      throw new Error("No active workspace")
    }
    if (!isTauriRuntime()) {
      throw new Error("Renaming phase folders requires the desktop runtime")
    }
    await moveWorkspacePath(targetWorkspaceRoot ?? targetSkillId, from, to)
  }, [currentSkillId, currentWorkspaceRoot])

  const compileSkillById = useCallback(async (targetSkillId: string) => {
    updateStage(targetSkillId, "compiling")
    setCompileErrors((current) => ({ ...current, [targetSkillId]: [] }))
    setPredictErrors([])
    setPredictDrawerOpen(false)
    setRunErrors([])
    setRunDrawerOpen(false)
    try {
      const result = await compileSkill(targetSkillId)
      if ("code" in result) {
        updateStage(targetSkillId, "compile-fail")
        setCompileErrors((current) => ({ ...current, [targetSkillId]: result.errors }))
        setCompileDrawerOpen(true)
        return
      }
      if (result.status === "ok") {
        updateStage(targetSkillId, "compile-pass")
        setCompileErrors((current) => ({ ...current, [targetSkillId]: [] }))
        setCompileDrawerOpen(false)
        toast.success(
          `Compiled ${result.manifest_name} (${shortHash(result.artifact_ref.content_hash)}, fp ${shortHash(result.execution_fingerprint)})`,
        )
        void mutateSkillDetail(result.detail, { revalidate: false })
      }
    } catch (error: unknown) {
      updateStage(targetSkillId, "compile-fail")
      const message = errorMessage(error)
      setCompileErrors((current) => ({
        ...current,
        [targetSkillId]: [diagnosticError(message, errorDiagnosticDetails(error))],
      }))
      setCompileDrawerOpen(true)
      toast.error(message)
    }
  }, [mutateSkillDetail, updateStage])

  const clearStaleCompileProjection = useCallback((targetSkillId: string) => {
    setCompileErrors((current) => ({ ...current, [targetSkillId]: [] }))
    setCompileStages((current) => {
      if (!(targetSkillId in current)) return current
      const next = { ...current }
      delete next[targetSkillId]
      return next
    })
    setCompileDrawerOpen(false)
  }, [])

  // 03_compile A13 / compile-lint F1+F6: a SETTLED source write (canvas topology
  // edit, panel save, phase create/delete/rename) must REPLACE the lint projection
  // with a fresh engine verdict of the on-disk truth — clearing alone leaves a
  // broken graph (e.g. a just-disconnected edge) looking healthier than before.
  const refreshLintAfterSourceWrite = useCallback((targetSkillId: string, workspaceRoot?: string | null) => {
    clearStaleCompileProjection(targetSkillId)
    void relintSkillFromDisk(targetSkillId, workspaceRoot)
  }, [clearStaleCompileProjection])

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
        const result = await doWriteSkillFile(path, content, expectedHash, { skillId: target.skillId, workspaceRoot: target.workspaceRoot })
        const updatedDetail = skillDetailWithFile(target.detail, path, content)
        setActiveFileDetails((current) => {
          const next = { ...current }
          for (const side of ["left", "right"] as const) {
            const file = current[side]
            if (
              file?.skillId === target.skillId
              && file.workspaceRoot === target.workspaceRoot
              && file.path === path
            ) {
              next[side] = { ...file, content, hash: result.hash, savedContent: content, dirty: false, saveEnabled: true }
            }
          }
          return next
        })
        setSelectedNode((current) => (
          selectedNodeMatchesTarget(current, target)
            ? { ...current, data: { ...current.data, resolvedSkillDetail: updatedDetail } }
            : current
        ))
        setChildDetailPatch({
          skillId: target.skillId,
          workspaceRoot: target.workspaceRoot,
          detail: updatedDetail,
          revision: Date.now(),
        })
        toast.success("Saved phase properties")
        refreshLintAfterSourceWrite(target.skillId, target.workspaceRoot)
        if (currentSkillId && currentSkillId !== target.skillId) {
          refreshLintAfterSourceWrite(currentSkillId, currentWorkspaceRoot)
        }
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
          next[side] = { ...file, content, hash: result.hash, savedContent: content, dirty: false, saveEnabled: true, title: undefined }
        }
      }
      return next
    })
    toast.success("Saved phase properties")
    refreshLintAfterSourceWrite(currentSkillId, currentWorkspaceRoot)
    void mutateSkillDetail()
  }, [currentSkillId, currentWorkspaceRoot, doWriteSkillFile, mutateSkillDetail, refreshLintAfterSourceWrite])

  // Add a LOGIC action: scaffold `phases/<id>/actions/<name>.py` (one action per
  // file, function name = action name — project convention, copilot.py), keep the
  // LOGIC.md frontmatter `actions:` and body `<action>` tags in sync (engine
  // requires they match), then open the new file for editing.
  const handleActionCreate = useCallback(async (phaseId: string, name: string, target?: ChildSaveTarget) => {
    const editDetail = target?.detail ?? skillDetail
    const targetSkillId = target?.skillId ?? currentSkillId
    const override = target ? { skillId: target.skillId, workspaceRoot: target.workspaceRoot } : undefined
    if (!targetSkillId || !editDetail) {
      toast.error("Open a skill before adding an action")
      return
    }
    const trimmed = name.trim()
    if (!isValidActionName(trimmed)) {
      toast.error("Action name must be a Python identifier (letters, digits, underscore; not starting with a digit).")
      return
    }
    const logicPath = `phases/${phaseId}/LOGIC.md`
    const logicContent = editDetail.files?.[logicPath]
    if (logicContent === undefined) {
      toast.error(`Phase file is missing: ${logicPath}`)
      return
    }
    const current = readActionsList(logicContent)
    if (current.includes(trimmed)) {
      toast.error(`Action ${trimmed} already exists`)
      return
    }
    const applied = applyActionsList(logicContent, [...current, trimmed])
    if (!applied.ok) {
      toast.error(applied.message)
      return
    }
    const pyPath = actionFilePath(phaseId, trimmed)
    let createdPy = false
    try {
      await doWriteSkillFile(pyPath, actionStubContent(trimmed), null, override, { createIfAbsent: true })
      createdPy = true
      await doWriteSkillFile(logicPath, applied.markdown, await sha256Hex(logicContent), override)
      refreshLintAfterSourceWrite(targetSkillId, override ? override.workspaceRoot : currentWorkspaceRoot)
      toast.success(`Created action ${trimmed}`)
      // Open the new file in the SAME skill the node lives in (child subgraph when
      // drilled) — pass skillId/workspaceRoot so it doesn't resolve against root.
      handleFileOpen({
        path: pyPath,
        skillId: targetSkillId,
        workspaceRoot: override ? override.workspaceRoot : currentWorkspaceRoot,
        language: "python",
        saveEnabled: true,
      })
      if (target) await target.onSettled()
      else await mutateSkillDetail()
    } catch (error) {
      if (createdPy) {
        try {
          await doDeleteWorkspacePath(pyPath, override)
        } catch (rollbackError) {
          toast.warning(`Could not clean up ${pyPath}: ${errorMessage(rollbackError)}`)
        }
      }
      toast.error(isReadOnlySkillError(error) ? "This skill is read-only — fork it into your workspace to edit." : errorMessage(error))
      if (target) void target.onSettled()
      else void mutateSkillDetail()
    }
  }, [currentSkillId, currentWorkspaceRoot, doDeleteWorkspacePath, doWriteSkillFile, handleFileOpen, mutateSkillDetail, refreshLintAfterSourceWrite, skillDetail])

  // Create a phase validator: scaffold the sibling `phases/<id>/validator.py` from a
  // passing stub (engine `def validate(output, state_slice, **kwargs)` contract) AND
  // flip the node file's `validator: true`, then open the file. Shared by all three
  // phase kinds (the flag lives on SKILL/LOGIC/SUBGRAPH.md). Mirrors handleActionCreate's
  // write-then-sync + rollback shape.
  const handleValidatorCreate = useCallback(async (phaseId: string, target?: ChildSaveTarget) => {
    const editDetail = target?.detail ?? skillDetail
    const targetSkillId = target?.skillId ?? currentSkillId
    const override = target ? { skillId: target.skillId, workspaceRoot: target.workspaceRoot } : undefined
    if (!targetSkillId || !editDetail) {
      toast.error("Open a skill before adding a validator")
      return
    }
    const phase = phaseRefsFromSkillDetail(editDetail).find((entry) => entry.id === phaseId)
    if (!phase) {
      toast.error("Phase not found")
      return
    }
    const phasePath = phaseFilePath(phaseId, phase.mode)
    const phaseContent = editDetail.files?.[phasePath]
    if (phaseContent === undefined) {
      toast.error(`Phase file is missing: ${phasePath}`)
      return
    }
    const enabled = applyPhaseValidator(phaseContent, true)
    if (!enabled.ok) {
      toast.error(enabled.message)
      return
    }
    const pyPath = validatorFilePath(phaseId)
    let createdPy = false
    try {
      await doWriteSkillFile(pyPath, validatorStubContent(), null, override, { createIfAbsent: true })
      createdPy = true
      await doWriteSkillFile(phasePath, enabled.markdown, await sha256Hex(phaseContent), override)
      refreshLintAfterSourceWrite(targetSkillId, override ? override.workspaceRoot : currentWorkspaceRoot)
      toast.success("Created validator.py")
      handleFileOpen({
        path: pyPath,
        skillId: targetSkillId,
        workspaceRoot: override ? override.workspaceRoot : currentWorkspaceRoot,
        language: "python",
        saveEnabled: true,
      })
      if (target) await target.onSettled()
      else await mutateSkillDetail()
    } catch (error) {
      if (createdPy) {
        try {
          await doDeleteWorkspacePath(pyPath, override)
        } catch (rollbackError) {
          toast.warning(`Could not clean up ${pyPath}: ${errorMessage(rollbackError)}`)
        }
      }
      toast.error(isReadOnlySkillError(error) ? "This skill is read-only — fork it into your workspace to edit." : errorMessage(error))
      if (target) void target.onSettled()
      else void mutateSkillDetail()
    }
  }, [currentSkillId, currentWorkspaceRoot, doDeleteWorkspacePath, doWriteSkillFile, handleFileOpen, mutateSkillDetail, refreshLintAfterSourceWrite, skillDetail])

  // Delete a LOGIC action: drop it from LOGIC.md frontmatter + body (kept in sync)
  // and remove its `actions/<name>.py` file when present.
  const handleActionDelete = useCallback(async (phaseId: string, name: string, target?: ChildSaveTarget) => {
    const editDetail = target?.detail ?? skillDetail
    const targetSkillId = target?.skillId ?? currentSkillId
    const override = target ? { skillId: target.skillId, workspaceRoot: target.workspaceRoot } : undefined
    if (!targetSkillId || !editDetail) {
      toast.error("Open a skill before deleting an action")
      return
    }
    const logicPath = `phases/${phaseId}/LOGIC.md`
    const logicContent = editDetail.files?.[logicPath]
    if (logicContent === undefined) {
      toast.error(`Phase file is missing: ${logicPath}`)
      return
    }
    const current = readActionsList(logicContent)
    const applied = applyActionsList(logicContent, current.filter((entry) => entry !== name))
    if (!applied.ok) {
      toast.error(applied.message)
      return
    }
    const pyPath = actionFilePath(phaseId, name)
    const hasFile = editDetail.files?.[pyPath] !== undefined
    try {
      await doWriteSkillFile(logicPath, applied.markdown, await sha256Hex(logicContent), override)
      if (hasFile) {
        await doDeleteWorkspacePath(pyPath, override)
      }
      refreshLintAfterSourceWrite(targetSkillId, override ? override.workspaceRoot : currentWorkspaceRoot)
      toast.success(`Deleted action ${name}`)
      if (target) await target.onSettled()
      else await mutateSkillDetail()
    } catch (error) {
      toast.error(isReadOnlySkillError(error) ? "This skill is read-only — fork it into your workspace to edit." : errorMessage(error))
      if (target) void target.onSettled()
      else void mutateSkillDetail()
    }
  }, [currentSkillId, currentWorkspaceRoot, doDeleteWorkspacePath, doWriteSkillFile, mutateSkillDetail, refreshLintAfterSourceWrite, skillDetail])

  const handleCreatePhase = useCallback(async (kind: NewPhaseKind, requestedPhaseId?: string, target?: ChildSaveTarget) => {
    // Drilled-child create mirrors handleDeletePhase: when a child target is given,
    // edit/serialize the CHILD's detail and write through its override so a node
    // created inside a drilled subgraph lands in the child's GRAPH.md, not the root's.
    const editDetail = target?.detail ?? skillDetail
    if (!currentSkillId || !editDetail) {
      toast.error("Open a skill before creating a phase")
      return
    }
    const targetSkillId = target?.skillId ?? currentSkillId
    const override = target ? { skillId: target.skillId, workspaceRoot: target.workspaceRoot } : undefined
    // Optimistic-concurrency hash for serialize, read from the ONE source of
    // truth: the GRAPH.md file on disk. Parent graph and drilled child go through
    // the identical readGraphHash path; only `override` (which skill) differs.
    const graphHash = await readGraphHash(editDetail, override)
    const draft = createPhaseDraft(editDetail, kind, [], requestedPhaseId)
    let createdPhaseDir: string | null = null
    let createdSubgraphChildDir: string | null = null
    try {
      await doWriteSkillFile(draft.filePath, draft.fileContent, null, override, { createIfAbsent: true })
      createdPhaseDir = phaseDirectoryPath(draft.phaseId)
      // A new subgraph phase auto-scaffolds a standard child skill at its default
      // landing (subgraph/<phaseId>) so the SUBGRAPH.md `path:` resolves immediately
      // (graph-authoring F4 / engine FORMAT-GROUND-TRUTH §1/§4). Folder writes go
      // through the native-fs sole writer (D12), so this is desktop-runtime only; the
      // browser fallback keeps the bare reference and lets the author point it later.
      if (kind === "subgraph" && isTauriRuntime()) {
        const childDir = defaultSubgraphChildDir(draft.phaseId)
        for (const file of subgraphChildScaffoldFiles(childDir, draft.phaseId)) {
          await doWriteSkillFile(file.path, file.content, null, override, { createIfAbsent: true })
          // Mark the dir for rollback only once the first create-if-absent write
          // succeeds: that proves the folder did not pre-exist (so it is ours to
          // remove), while a collision on the first file leaves it untouched.
          createdSubgraphChildDir = childDir
        }
      }
      const serialized = override
        ? await serializeSkillGraph(targetSkillId, draft.phases, graphHash, override.workspaceRoot)
        : await serializeSkillGraph(targetSkillId, draft.phases, graphHash)
      await doWriteSkillFile("GRAPH.md", serialized.markdown_content, graphHash, override)
      refreshLintAfterSourceWrite(targetSkillId, override ? override.workspaceRoot : currentWorkspaceRoot)
      toast.success(`Created ${draft.phaseId}`)
      if (target) await target.onSettled()
      else await mutateSkillDetail()
    } catch (error) {
      for (const createdDir of [createdSubgraphChildDir, createdPhaseDir]) {
        if (!createdDir) continue
        try {
          await doDeleteWorkspacePath(createdDir, override)
        } catch (rollbackError) {
          toast.warning(`Could not clean up ${createdDir}: ${errorMessage(rollbackError)}`)
        }
      }
      toast.error(errorMessage(error))
      if (target) void target.onSettled()
      else void mutateSkillDetail()
    }
  }, [currentSkillId, currentWorkspaceRoot, doDeleteWorkspacePath, doWriteSkillFile, mutateSkillDetail, readGraphHash, refreshLintAfterSourceWrite, skillDetail])

  const handleDeletePhase = useCallback(async (phaseId: string, target?: ChildSaveTarget) => {
    const editDetail = target?.detail ?? skillDetail
    if (!currentSkillId || !editDetail) {
      toast.error("Open a skill before deleting a phase")
      return
    }
    const result = removePhaseRefs(editDetail, phaseId)
    if (!result.ok) {
      toast.error(result.message)
      return
    }

    const targetSkillId = target?.skillId ?? currentSkillId
    const override = target ? { skillId: target.skillId, workspaceRoot: target.workspaceRoot } : undefined
    const graphHash = await readGraphHash(editDetail, override)
    const phaseDirsToDelete = [
      phaseId,
      ...orphanPhaseDirectoryIds(editDetail, result.phases).filter((orphanId) => orphanId !== phaseId),
    ]
    // Mirror of create: a subgraph phase auto-scaffolds its child graph at
    // subgraph/<phaseId>, so deleting that phase also removes the child folder —
    // but ONLY when the path is still the auto-created default shape. A re-pointed
    // absolute/external/shared path (D7 "随便放哪里") is left untouched so we never
    // destroy a child graph Studio did not create.
    const deletedRow = editDetail.graph_topology?.find((row) => row.id === phaseId)
    const subgraphChildDirToDelete = deletedRow?.mode === "subgraph"
      ? autoCreatedSubgraphChildDir(deletedRow.path)
      : null
    try {
      const serialized = override
        ? await serializeSkillGraph(targetSkillId, result.phases, graphHash, override.workspaceRoot)
        : await serializeSkillGraph(targetSkillId, result.phases, graphHash)
      await doWriteSkillFile("GRAPH.md", serialized.markdown_content, graphHash, override)
      for (const deletedPhaseId of phaseDirsToDelete) {
        await doDeleteWorkspacePath(phaseDirectoryPath(deletedPhaseId), override)
      }
      if (subgraphChildDirToDelete && isTauriRuntime()) {
        // Best-effort: the phase is already gone from GRAPH.md, so a missing or
        // un-removable child folder must not fail the whole delete. A not-found
        // child (manually removed, or never scaffolded in browser mode) is a no-op.
        try {
          await doDeleteWorkspacePath(subgraphChildDirToDelete, override)
        } catch (childDeleteError) {
          if (!errorMessage(childDeleteError).toLowerCase().includes("not found")) {
            toast.warning(`Could not delete subgraph folder ${subgraphChildDirToDelete}: ${errorMessage(childDeleteError)}`)
          }
        }
      }
      const verifiedGraph = await doReadWorkspaceFile("GRAPH.md", override)
      if (normalizeWorkspaceText(verifiedGraph.content) !== normalizeWorkspaceText(serialized.markdown_content)) {
        throw new Error("Could not verify GRAPH.md after deleting phase")
      }
      const remainingPhaseDirs = await doListWorkspaceDir("phases", override)
      const remainingDeletedIds = phaseDirsToDelete.filter((phaseDir) => (
        remainingPhaseDirs.some((entry) => entry.kind === "dir" && entry.name === phaseDir)
      ))
      if (remainingDeletedIds.length > 0) {
        throw new Error(`Could not delete phase folder: ${remainingDeletedIds.map(phaseDirectoryPath).join(", ")}`)
      }
      setSelectedNodeId((current) => current === phaseId ? null : current)
      setSelectedNode((current) => current?.id === phaseId ? null : current)
      setActiveFileDetails((current) => {
        const next = { ...current }
        const deletedPrefixes = phaseDirsToDelete.map((deletedPhaseId) => `${phaseDirectoryPath(deletedPhaseId)}/`)
        for (const side of ["left", "right"] as const) {
          const file = current[side]
          if (file?.skillId === targetSkillId && deletedPrefixes.some((prefix) => file.path.startsWith(prefix))) {
            delete next[side]
          }
        }
        return next
      })
      refreshLintAfterSourceWrite(targetSkillId, override ? override.workspaceRoot : currentWorkspaceRoot)
      toast.success(`Deleted ${phaseId}`)
      if (target) {
        await target.onSettled()
      } else {
        await mutateSkillDetail()
      }
    } catch (error) {
      if (target) {
        if (isReadOnlySkillError(error)) {
          toast.error("This subgraph is read-only - fork it into your workspace to edit.")
        }
        void target.onSettled()
      } else {
        void mutateSkillDetail()
      }
      toast.error(errorMessage(error))
    }
  }, [currentSkillId, currentWorkspaceRoot, doDeleteWorkspacePath, doListWorkspaceDir, doReadWorkspaceFile, doWriteSkillFile, mutateSkillDetail, readGraphHash, refreshLintAfterSourceWrite, skillDetail])

  const handleRenamePhase = useCallback(async (phaseId: string, nextPhaseId: string, target?: ChildSaveTarget) => {
    const editDetail = target?.detail ?? skillDetail
    const targetSkillId = target?.skillId ?? currentSkillId
    const override = target ? { skillId: target.skillId, workspaceRoot: target.workspaceRoot } : undefined
    if (!targetSkillId || !editDetail) {
      toast.error("Open a skill before renaming a phase")
      return
    }
    const result = renamePhaseRefs(editDetail, phaseId, nextPhaseId)
    if (!result.ok) {
      toast.error(result.message)
      return
    }

    const nextId = nextPhaseId.trim()
    const phase = phaseRefsFromSkillDetail(editDetail).find((entry) => entry.id === phaseId)
    if (!phase) {
      toast.error("Phase not found")
      return
    }
    const oldFilePath = phaseFilePath(phaseId, phase.mode)
    const newFilePath = phaseFilePath(nextId, phase.mode)
    const oldContent = editDetail.files?.[oldFilePath]
    if (oldContent === undefined) {
      toast.error(`Phase file is missing: ${oldFilePath}`)
      return
    }
    const renamedContent = applyPhaseName(oldContent, nextId)
    if (!renamedContent.ok) {
      toast.error(renamedContent.message)
      return
    }

    const graphHash = await readGraphHash(editDetail, override)
    const oldDir = phaseDirectoryPath(phaseId)
    const newDir = phaseDirectoryPath(nextId)
    let moved = false
    let phaseWriteHash: string | null = null

    try {
      const serialized = override
        ? await serializeSkillGraph(targetSkillId, result.phases, graphHash, override.workspaceRoot)
        : await serializeSkillGraph(targetSkillId, result.phases, graphHash)
      await doMoveWorkspacePath(oldDir, newDir, override)
      moved = true
      const phaseWrite = await doWriteSkillFile(newFilePath, renamedContent.markdown, await sha256Hex(oldContent), override)
      phaseWriteHash = phaseWrite.hash
      const graphWrite = await doWriteSkillFile("GRAPH.md", serialized.markdown_content, graphHash, override)
      const updatedDetail = target
        ? skillDetailWithRenamedPhase(editDetail, result.phases, {
            oldPhaseId: phaseId,
            nextPhaseId: nextId,
            oldFilePath,
            newFilePath,
            renamedContent: renamedContent.markdown,
            graphContent: serialized.markdown_content,
          })
        : null
      setSelectedNodeId((current) => current === phaseId ? nextId : current)
      setSelectedNode((current) => (
        current?.id === phaseId
          ? {
            id: nextId,
            data: {
              ...current.data,
              phaseId: nextId,
              label: nextId,
              filePath: newFilePath,
              ...(updatedDetail ? { resolvedSkillDetail: updatedDetail } : {}),
            },
          }
          : current
      ))
      setActiveFileDetails((current) => {
        const next = { ...current }
        const oldPrefix = `${oldDir}/`
        const newPrefix = `${newDir}/`
        for (const side of ["left", "right"] as const) {
          const file = current[side]
          if (
            !file
            || file.skillId !== targetSkillId
            || (target && file.workspaceRoot !== target.workspaceRoot)
          ) {
            continue
          }
          if (file.path === "GRAPH.md") {
            next[side] = {
              ...file,
              content: serialized.markdown_content,
              hash: graphWrite.hash,
              savedContent: serialized.markdown_content,
              dirty: false,
              saveEnabled: true,
              title: undefined,
            }
          } else if (file.path === oldFilePath) {
            next[side] = {
              ...file,
              path: newFilePath,
              content: renamedContent.markdown,
              hash: phaseWrite.hash,
              savedContent: renamedContent.markdown,
              dirty: false,
              saveEnabled: true,
              title: undefined,
            }
          } else if (file.path.startsWith(oldPrefix)) {
            next[side] = { ...file, path: `${newPrefix}${file.path.slice(oldPrefix.length)}` }
          }
        }
        return next
      })
      if (target && updatedDetail) {
        setChildDetailPatch({
          skillId: target.skillId,
          workspaceRoot: target.workspaceRoot,
          detail: updatedDetail,
          revision: Date.now(),
        })
      }
      toast.success(`Renamed ${phaseId} to ${nextId}`)
      refreshLintAfterSourceWrite(targetSkillId, override ? override.workspaceRoot : currentWorkspaceRoot)
      if (target) {
        await target.onSettled()
      } else {
        await mutateSkillDetail()
      }
    } catch (error) {
      if (moved) {
        try {
          if (phaseWriteHash) {
            await doWriteSkillFile(newFilePath, oldContent, phaseWriteHash, override)
          }
          await doMoveWorkspacePath(newDir, oldDir, override)
        } catch (rollbackError) {
          toast.warning(`Could not roll back phase folder rename: ${errorMessage(rollbackError)}`)
        }
      }
      if (target && isReadOnlySkillError(error)) {
        toast.error("This subgraph is read-only - fork it into your workspace to edit.")
      }
      toast.error(errorMessage(error))
      if (target) {
        void target.onSettled()
      } else {
        void mutateSkillDetail()
      }
    }
  }, [currentSkillId, currentWorkspaceRoot, doMoveWorkspacePath, doWriteSkillFile, mutateSkillDetail, readGraphHash, refreshLintAfterSourceWrite, skillDetail])

  // Shared serialize -> write GRAPH.md -> settle tail for graph-structure edits
  // (connect / disconnect / reconnect). Compile stays an explicit user action so
  // the authoring surfaces can temporarily hold invalid source while the user edits.
  const writeGraphEdit = useCallback(async (
    parentSkillId: string,
    editDetail: SkillDetail,
    phases: SerializableGraphPhaseRef[],
    target?: ChildSaveTarget,
  ) => {
    const targetSkillId = target?.skillId ?? parentSkillId
    const override = target ? { skillId: target.skillId, workspaceRoot: target.workspaceRoot } : undefined
    const graphHash = await readGraphHash(editDetail, override)
    try {
      const serialized = override
        ? await serializeSkillGraph(targetSkillId, phases, graphHash, override.workspaceRoot)
        : await serializeSkillGraph(targetSkillId, phases, graphHash)
      await doWriteSkillFile("GRAPH.md", serialized.markdown_content, graphHash, override)
      refreshLintAfterSourceWrite(targetSkillId, override ? override.workspaceRoot : currentWorkspaceRoot)
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
  }, [currentWorkspaceRoot, doWriteSkillFile, mutateSkillDetail, readGraphHash, refreshLintAfterSourceWrite])

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
    if (file.dirty || inFlightRef.current[side]) {
      setConflict({
        skillId: file.skillId,
        path: file.path,
        side,
        localContent: file.content,
        remoteContent: content,
        remoteHash: hash,
      })
      return
    }
    setActiveFileDetails((current) => ({
      ...current,
      [side]: { ...file, content, hash, savedContent: content, dirty: false, saveEnabled: true, title: undefined },
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
          savedContent: conflict.remoteContent,
          dirty: false,
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
        savedContent: conflict.remoteContent,
        dirty: false,
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
            savedContent: payload.content,
            dirty: false,
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

  const ignoreStudioEvent = useCallback(() => {}, [])

  const handleRuntimeConfigChangedEvent = useCallback((event: { skillId: string; dataset: string }) => {
    if (event.skillId === currentSkillId && event.dataset) {
      void mutateRuntimeConfig()
    }
  }, [currentSkillId, mutateRuntimeConfig])

  const handleSkillChangedEvent = useCallback((event: { skillId: string; path: string }) => {
    try {
      if (event.skillId !== currentSkillId || !event.path) return
      const normalizedChangedPath = event.path.replace(/\\/g, "/")
      if (
        normalizedChangedPath.startsWith(".workspace/import_files/")
        || normalizedChangedPath === ".workspace/runtime_config.json"
      ) {
        void mutateRuntimeConfig()
      }
      const isIoDocumentChange = isIoDocumentPath(normalizedChangedPath)
      const skillDetailPromise = isIoDocumentChange ? getSkillDetail(currentSkillId) : null
      if (skillDetailPromise) {
        void skillDetailPromise.then((detail) => {
          void mutateSkillDetail(detail, { revalidate: false })
        })
      }
      // Keep the file tree live like a native explorer's watcher: refresh every
      // already-loaded ancestor folder of the changed path so external edits AND
      // Studio's own native-fs create/delete/rename show up without a manual
      // re-expand. Reloading ancestors also surfaces a brand-new nested folder.
      const changedParts = normalizedChangedPath.split("/").filter(Boolean)
      const tree = assetDirectoryTreeRef.current
      for (let depth = 0; depth < changedParts.length; depth += 1) {
        const dir = changedParts.slice(0, depth).join("/")
        if (tree.getDirectory(dir).status !== "idle") {
          tree.reloadDirectory(dir)
        }
      }
      const entries = (["left", "right"] as const).filter(
        (side) => activeFileDetails[side]?.path.replace(/\\/g, "/") === normalizedChangedPath,
      )
      for (const side of entries) {
        const file = activeFileDetails[side]
        if (!file) continue
        void (skillDetailPromise ?? getSkillDetail(currentSkillId)).then(async (detail) => {
          const remoteContent = detail.files?.[normalizedChangedPath]
          if (remoteContent === undefined) return
          const remoteHash = await sha256Hex(remoteContent)
          if (file.dirty || inFlightRef.current[side]) {
            setConflict({
              skillId: currentSkillId,
              path: normalizedChangedPath,
              side,
              localContent: file.content,
              remoteContent,
              remoteHash,
            })
          } else {
            setActiveFileDetails((current) => ({
              ...current,
              [side]: {
                ...file,
                content: remoteContent,
                hash: remoteHash,
                savedContent: remoteContent,
                dirty: false,
              },
            }))
            if (!isIoDocumentChange) {
              void mutateSkillDetail(detail, { revalidate: false })
            }
          }
        })
      }
    } catch {
      toast.error("Could not process file change event")
    }
  }, [activeFileDetails, currentSkillId, mutateRuntimeConfig, mutateSkillDetail])

  useStudioEventStream({
    onRegistryChanged: ignoreStudioEvent,
    onRolesChanged: ignoreStudioEvent,
    onRuntimeConfigChanged: handleRuntimeConfigChangedEvent,
    onSkillChanged: handleSkillChangedEvent,
  }, { enabled: Boolean(currentSkillId) })


  const activeLint = useMemo(
    () => activeLintErrors({
      firstScreenLint: skillDetail?.lint_result?.errors,
      manifestErrors: skillDetail?.manifest_errors,
      realtime: realtimeLint?.errors,
    }),
    [skillDetail?.lint_result, skillDetail?.manifest_errors, realtimeLint],
  )

  const editorLintResult = useMemo<LintResult | null>(() => {
    if (!currentSkillId) return null
    if (realtimeLint != null) return realtimeLint
    return {
      status: activeLint.length > 0 ? "failed" : "passed",
      errors: activeLint,
      phases_summary: skillDetail?.lint_result?.phases_summary ?? null,
    }
  }, [activeLint, currentSkillId, realtimeLint, skillDetail?.lint_result?.phases_summary])

  const contextValue = useMemo<WorkspaceContextValue>(() => ({
    currentSkillId,
    navStack: displayNavStack,
    activeFiles: {
      left: activeFileDetails.left?.path,
      right: activeFileDetails.right?.path,
    },
    activeFileDetails,
    editorLintResult,
    splitMode,
    onFileOpen: handleFileOpen,
    onRevealNodeForFile: handleRevealNodeForFile,
    onRevealSubgraphChildNode: handleRevealSubgraphChildNode,
    onRevealSubgraphGraph: handleRevealSubgraphGraph,
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
    editorLintResult,
    handleFileOpen,
    handleRevealNodeForFile,
    handleRevealSubgraphChildNode,
    handleRevealSubgraphGraph,
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
    if (lint === "passed") return "idle"
    return "idle"
  }, [compileStages, lintTick])

  const handlePredict = useCallback(async () => {
    if (!currentSkillId) return
    const targetSkillId = currentSkillId
    updateStage(targetSkillId, "predicting")
    setPredictErrors([])
    setPredictDrawerOpen(false)
    setRunErrors([])
    setRunDrawerOpen(false)
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
        const errors = predictStatusFailureErrors(predict)
        setPredictErrors(errors)
        setPredictDrawerOpen(true)
        toast.error(`Predict failed: ${errors[0]?.message ?? "see predicted execution path"}`)
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
      setPredictErrors([])
      setPredictDrawerOpen(false)
      setRunErrors([])
      setRunDrawerOpen(false)
      toast.success("Predict run completed successfully")
    } catch (error: unknown) {
      setRanAgentNodesBySkill((prev) => ({ ...prev, [targetSkillId]: new Set<string>() }))
      updateStage(targetSkillId, "predict-fail")
      const errors = requestDiagnosticErrors(error)
      setPredictErrors(errors)
      setPredictDrawerOpen(true)
      toast.error(`Predict failed: ${errors[0]?.message ?? "Predict request failed"}`)
    }
  }, [clearCopilotJudgeResult, currentSkillId, selectedTestInputId, updateStage])

  const handleRun = useCallback(async () => {
    if (!currentSkillId) return
    const stage = deriveBuildStage(currentSkillId)
    if (stage !== "predict-pass") {
      return
    }
    const targetSkillId = currentSkillId
    updateStage(targetSkillId, "running")
    setRunErrors([])
    setRunDrawerOpen(false)
    try {
      const inputData = await resolveRunInput(targetSkillId, selectedTestInputId)
      const result = await startRun(targetSkillId, inputData)
      clearCopilotJudgeResult()
      await projectRun(result)
      setRunId(result.run_id)
      setRunErrors([])
      setRunDrawerOpen(false)
      // F1: starting a run opens the timeline region to stream live trace events.
      setActivePanel("timeline")
      toast.success("Run started successfully")
    } catch (error: unknown) {
      updateStage(targetSkillId, "predict-pass")
      const errors = requestDiagnosticErrors(error)
      setRunErrors(errors)
      setRunDrawerOpen(true)
      toast.error(`Run failed: ${errors[0]?.message ?? "Run request failed"}`)
    }
  }, [clearCopilotJudgeResult, currentSkillId, deriveBuildStage, selectedTestInputId, updateStage, setRunId, projectRun])

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

  // Launch the node's Compare LLMs: off the current base run, spawn one isolated
  // single-node side-run per persisted candidate (each fed the node's real input,
  // only the model swapped). The returned group drives the Trace top tabs.
  const handleStartNodeCompare = useCallback(
    async (nodeId: string) => {
      if (!currentSkillId) return
      if (!runId) {
        toast.error("Run the skill first, then compare this node's models.")
        return
      }
      try {
        const group = await startNodeCompareRun(currentSkillId, runId, nodeId)
        setCompareGroupId(group.compare_group_id)
        setCompareRuns(group.runs)
        setCompareCandidateId(group.runs[0]?.candidate_id ?? null)
      } catch (error) {
        toast.error(`Could not start model compare: ${errorMessage(error)}`)
      }
    },
    [currentSkillId, runId],
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
      await projectRun(result)
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
  }, [clearCopilotJudgeResult, currentSkillId, runId, setRunId, projectRun])

  const handleSubmitHitlResponse = useCallback(async (request: TraceHitlResumeRequest) => {
    if (!currentSkillId || !runId) return
    setResumeLoading(true)
    try {
      const result = await resumeRun(currentSkillId, runId, hitlResumeOptionsFromRequest(request))
      setActivePanel("timeline")
      clearCopilotJudgeResult()
      await projectRun(result)
      setRunId(null)
      setRunId(result.run_id)
      toast.success("Run resumed with human input")
    } catch (error) {
      toast.error(`Resume failed: ${errorMessage(error)}`)
    } finally {
      setResumeLoading(false)
    }
  }, [clearCopilotJudgeResult, currentSkillId, runId, setRunId, projectRun])

  const handleResumeEdgeDownstream = useCallback(async (options: ResumeRunOptions) => {
    if (!currentSkillId || !runId) return
    setResumeLoading(true)
    try {
      const result = await resumeRun(currentSkillId, runId, options)
      setActivePanel("timeline")
      clearCopilotJudgeResult()
      await projectRun(result)
      setRunId(null)
      setRunId(result.run_id)
      toast.success("Run resumed from tampered edge context")
    } catch (error) {
      toast.error(`Resume failed: ${errorMessage(error)}`)
    } finally {
      setResumeLoading(false)
    }
  }, [clearCopilotJudgeResult, currentSkillId, runId, setRunId, projectRun])

  const handleResumeNode = useCallback(async (options: ResumeRunOptions) => {
    if (!currentSkillId || !runId) return
    setResumeLoading(true)
    try {
      const result = await resumeRun(currentSkillId, runId, options)
      setActivePanel("timeline")
      clearCopilotJudgeResult()
      await projectRun(result)
      setRunId(null)
      setRunId(result.run_id)
      toast.success("Run resumed from selected node")
    } catch (error) {
      toast.error(`Resume failed: ${errorMessage(error)}`)
    } finally {
      setResumeLoading(false)
    }
  }, [clearCopilotJudgeResult, currentSkillId, runId, setRunId, projectRun])

  const handleHome = useCallback(() => {
    setSettingsOpen(false)
    onCloseSkill()
  }, [onCloseSkill])

  const currentCompileErrors = currentSkillId ? compileErrors[currentSkillId] ?? [] : []
  // N3 atom #4: feed the canvas node channel from BOTH manual Compile AND lint — the lint
  // diagnostics are adapted onto the CompileError shape the node tooltip renders, grouped by
  // node, and merged with the compile errors (neither dropped). Previously fed by Compile only.
  const compileErrorsByNodeId = useMemo(() => {
    const compileByNode = compileErrorsByNode(currentSkillId ? compileErrors[currentSkillId] : [])
    const lintByNode = lintErrorsByNode(activeLint)
    const lintAsCompileByNode: Record<string, CompileError[]> = {}
    for (const [nodeId, errors] of Object.entries(lintByNode)) {
      lintAsCompileByNode[nodeId] = errors.map(lintErrorToCompileError)
    }
    return mergeNodeErrors(compileByNode, lintAsCompileByNode)
  }, [activeLint, compileErrors, currentSkillId])
  const manualCompileErrorsByNodeId = useMemo(
    () => compileErrorsByNode(currentSkillId ? compileErrors[currentSkillId] : []),
    [compileErrors, currentSkillId],
  )
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
  // Field-axis source for the Properties/Input panels (N3 atom #5): manual Compile and
  // first-screen/realtime lint are both engine-owned diagnostics. Project both onto the
  // same LintError field_path axis so a clean realtime lint pass cannot erase manual
  // Compile failures from the side panels while the drawer still shows them.
  const propertiesFieldErrors = useMemo(() => {
    return fieldDiagnosticsForPanels(currentSkillId ? compileErrors[currentSkillId] : [], activeLint)
  }, [activeLint, compileErrors, currentSkillId])

  const leftPanelOverlay = activePanel ? (
    <WorkspaceLeftPanelOverlay
      onClose={() => setActivePanel(null)}
      width={leftPanelWidth}
      onResize={setLeftPanelWidth}
    >
      <Panels
        activePanel={activePanel}
        skillId={currentSkillId}
        workspaceRoot={currentWorkspaceRoot}
        skillDetail={skillDetail}
        runtimeConfig={runtimeConfig ?? null}
        assetDirectoryTree={assetDirectoryTree}
        assetSubgraphTree={assetSubgraphTree}
        selectedNode={selectedNode}
        ioBoundary={ioBoundary}
        selectedNodeStatus={selectedNodeStatus}
        selectedTestInputId={selectedTestInputId}
        onSelectTestInput={setSelectedTestInputId}
        onRuntimeArtifactsSave={handleRuntimeArtifactsSave}
        onRuntimeConfigRefresh={mutateRuntimeConfig}
        onPhaseFileSave={handlePhaseFileSave}
        onPhaseRename={handleRenamePhase}
        onActionCreate={handleActionCreate}
        onActionDelete={handleActionDelete}
        onValidatorCreate={handleValidatorCreate}
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
        onStartNodeCompare={handleStartNodeCompare}
        onOpenSettings={openSettings}
        onSelectGraph={handleNodeDeselect}
      />
    </WorkspaceLeftPanelOverlay>
  ) : null
  const editorOpen = Boolean(activeFileDetails.left || activeFileDetails.right)
  const hasMiniMapSpace = useMiniMapToolSpace(copilotOpen, currentSkillId, settingsOpen)
  // Safe areas = overlay size + its 1.5rem outer margin (0.75rem each side).
  const workspaceOverlayStyle = {
    "--studio-canvas-left-safe-area": activePanel ? `calc(${leftPanelWidth}px + 1.5rem)` : "0px",
    "--studio-canvas-right-safe-area": copilotOpen || morph?.mode === "open" ? `calc(${copilotWidth}px + 1.5rem)` : "0px",
    "--studio-canvas-editor-safe-area": editorOpen ? "calc(var(--studio-editor-overlay-height) + 1.5rem)" : "0px",
    "--studio-editor-overlay-height": editorHeight != null ? `${editorHeight}px` : "min(52%, 34rem)",
  } as CSSProperties
  // FAB ↔ panel container-transform: measure the canvas host, then hand the morph
  // the FAB spot + the header-logo landing + the full panel rect. Exactly one of
  // { FAB, morph, panel } renders at a time (gated on copilotOpen + morph).
  const startMorph = (mode: "open" | "close", from: Point | null) => {
    const host = hostRef.current
    if (!host) {
      setCopilotOpen(mode === "open")
      return
    }
    const bounds = { width: host.clientWidth, height: host.clientHeight }
    setMorph({
      mode,
      fab: from ?? defaultFabPosition(bounds),
      logo: headerLogoTarget(bounds, copilotWidth),
      panel: panelRect(bounds, copilotWidth),
    })
    if (mode === "close") setCopilotOpen(false)
  }
  const rightPanelOverlay = copilotOpen && !morph ? (
    <WorkspaceRightPanelOverlay
      width={copilotWidth}
      onResize={(widthPx) => setCopilotWidthRatio(rightPanelRatioFromPx(widthPx, hostWidth))}
    >
      <CopilotPanel
        skillId={currentSkillId}
        workspaceRoot={currentWorkspaceRoot}
        cliSession={cliSession}
        onCliSessionChange={setCliSession}
        copilot={copilot}
        view={copilotJudgeRefs ? "eval" : "edit"}
        judgeRefs={copilotJudgeRefs}
        completedRunId={completedRunId}
        onJudgePrepared={setCopilotJudgeResult}
        onFileChanged={handleCopilotFileChanged}
        onCollapse={() => startMorph("close", fabPosition)}
      />
    </WorkspaceRightPanelOverlay>
  ) : null
  // Collapsed → the draggable MoirAI FAB (default top-right). Tap → open morph.
  const copilotFab = currentSkillId && !copilotOpen && !morph ? (
    <CopilotFab position={fabPosition} onPositionChange={setFabPosition} onOpen={(from) => startMorph("open", from)} />
  ) : null
  const copilotMorph = morph ? (
    <CopilotPanelMorph
      mode={morph.mode}
      fab={morph.fab}
      logo={morph.logo}
      panel={morph.panel}
      onFinish={() => {
        if (morph.mode === "open") setCopilotOpen(true)
        setMorph(null)
      }}
    />
  ) : null

  return (
    <WorkspaceProvider value={contextValue}>
    <div className="flex h-screen w-screen flex-col overflow-hidden bg-background text-foreground">
      <Header
        skillId={currentSkillId}
        workspaceRoot={currentWorkspaceRoot}
        navStack={displayNavStack}
        onBreadcrumbClick={popNavTo}
        onTitleSelect={handleTitleSelect}
        onTitleEdit={handleTitleEdit}
        onHome={handleHome}
        onSyncSuccess={() => {
          void mutateSkillDetail()
        }}
        onOpenSettings={() => openSettings("general")}
      />

      <div className="relative flex min-h-0 flex-1">
        <Toolbar
          activePanel={activePanel}
          onPanelChange={setActivePanel}
          settingsOpen={settingsOpen}
          onSettingsToggle={handleSettingsToggle}
        />

        <ResizablePanelGroup
          id="studio-workspace-h"
          orientation="horizontal"
          className="min-w-0 flex-1"
        >
          <ResizablePanel id="canvas" defaultSize="100%" minSize="30%">
            <div className="relative size-full" style={currentSkillId ? workspaceOverlayStyle : undefined}>
              {currentSkillId === null ? (
                <WelcomePage onSelectSkill={onSelectSkill} />
              ) : (
                <>
                  <div
                    ref={observeHost}
                    data-studio-canvas-overlay-host="true"
                    className="relative size-full"
                  >
                    <GraphCanvas
                      key={currentSkillId}
                      skillId={currentSkillId}
                      workspaceRoot={currentWorkspaceRoot}
                      skillDetail={skillDetail}
                      runtimeConfig={runtimeConfig ?? null}
                      childDetailPatch={childDetailPatch}
                      isLoading={isLoading}
                      error={skillDetailError}
                      selectedNodeId={selectedNodeId}
                      onNodeSelect={handleNodeSelect}
                      onNodeDeselect={handleNodeDeselect}
                      onBoundarySelect={handleBoundarySelect}
                      revealRequest={revealRequest}
                      focusNodeRequest={focusNodeRequest}
                      onNodeFileOpen={handleFileOpen}
                      onPanelChange={setActivePanel}
                      onCloseEditors={closeAllEditors}
                      onCreatePhase={handleCreatePhase}
                      onDeletePhase={handleDeletePhase}
                      onPersistConnection={handlePersistConnection}
                      onDisconnectConnection={handleDisconnectConnection}
                      onReconnectConnection={handleReconnectConnection}
                      onPhaseFileSave={handlePhaseFileSave}
                      onPhaseFileRead={handlePhaseFileRead}
                      statusByNodeId={statusByNodeId}
                      sequentialOverwriteErrorsByNodeId={manualCompileErrorsByNodeId}
                      compileErrorsByNodeId={compileErrorsByNodeId}
                      goldenStateByNodeId={goldenStateByNodeId}
                      errorMessageByNodeId={errorMessageByNodeId}
                      dirtyDownstreamNodeIds={dirtyDownstreamNodeIds}
                      hideMiniMap={editorOpen || !hasMiniMapSpace}
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
                    {leftPanelOverlay}
                    <WorkspaceEditorOverlay onResizeHeight={setEditorHeight} />
                    {rightPanelOverlay}
                    {copilotFab}
                    {copilotMorph}
                  </div>
                </>
              )}
              {currentSkillId && !settingsOpen ? (
                <>
                  <CompileErrorDrawer
                    errors={currentCompileErrors}
                    open={compileDrawerOpen && currentCompileErrors.length > 0}
                    onOpenChange={setCompileDrawerOpen}
                  />
                  <CompileErrorDrawer
                    errors={predictErrors}
                    open={predictDrawerOpen && predictErrors.length > 0}
                    onOpenChange={setPredictDrawerOpen}
                    kind="predict"
                  />
                  <CompileErrorDrawer
                    errors={runErrors}
                    open={runDrawerOpen && runErrors.length > 0}
                    onOpenChange={setRunDrawerOpen}
                    kind="run"
                  />
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

        </ResizablePanelGroup>
        <Dialog open={settingsOpen} onOpenChange={setSettingsOpen} modal={false}>
          <DialogContent
            // grid-rows-[minmax(0,1fr)]: DialogContent is display:grid with a fixed
            // height; without a constrained row the implicit `auto` row grows to the
            // content height and the size-full child (SettingsPage) grows with it, so
            // the inner ScrollArea never gets a bounded height and can't scroll. Pin
            // the single row to the container height so the child is bounded.
            className="grid-rows-[minmax(0,1fr)] h-[min(92vh,56rem)] w-[min(96vw,88rem)] max-w-none overflow-hidden p-0 data-closed:hidden sm:max-w-none"
            aria-describedby={undefined}
            forceMount
            showCloseButton={false}
          >
            <DialogTitle className="sr-only">Settings</DialogTitle>
            <SettingsPageView
              controller={settingsController}
              initialTab={settingsInitialTab}
              onClose={() => setSettingsOpen(false)}
            />
          </DialogContent>
        </Dialog>
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

function normalizeWorkspaceText(value: string): string {
  return value.replace(/\r\n?/g, "\n")
}

function shortHash(value: string): string {
  const [algorithm, digest] = value.split(":", 2)
  if (!algorithm || !digest) return value
  return `${algorithm}:${digest.slice(0, 8)}`
}
