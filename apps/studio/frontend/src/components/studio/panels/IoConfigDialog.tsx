import { useMemo, useRef, useState, type CSSProperties } from "react"
import {
  AlertTriangle,
  ChevronDown,
  ChevronRight,
  FileText,
  Files,
  FolderOpen,
  Loader2,
  Pencil,
  Plus,
  Trash2,
} from "lucide-react"
import { importIoIntoWorkspace, type IoScanEntry } from "@/api/client"
import { deleteWorkspacePath, openLocalPath, selectImportFile, selectImportFolder } from "@/lib/tauri"
import { Button } from "@/components/ui/button"
import { Checkbox } from "@/components/ui/checkbox"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"
import { Badge } from "@/components/ui/badge"
import type { LintError, RuntimeInputConflict } from "@/api/types"
import type {
  ArtifactRow,
  FileFieldDecl,
  IoInputCheckRow,
  ReconciledFieldRow,
} from "@/lib/io-config"
import { errorMessage } from "@/utils/errors"
import { formatDiagnosticCode } from "../field-compile-errors"

/**
 * Blackboard-first I/O config surfaces (input region F3/F7).
 *
 * Input config is INLINE in the panel (a nested checkbox tree, PM 2026-07-03):
 * blackboard context first (checked = the node's io.inputs slice, expandable to
 * nested sub-fields like `chapter.aa_number`), then per-file field groups added
 * via native Import. Output config is the artifacts manifest (scoped modal — a
 * multi-card editor too wide for the 320px panel): every card offers the full
 * blackboard field universe (nested shown for shape; artifacts carry a whole
 * top-level field, so only top-level fields are checkable).
 */

const ROW_CLASS = "flex items-center gap-2 px-2 py-1.5"
const GROUP_HEAD_CLASS = "flex items-baseline gap-2 border-b border-border bg-muted/40 px-2 py-1.5"
const PATH_CLASS = "min-w-0 flex-1 truncate text-[11px] text-muted-foreground"
const META_CLASS = "text-[11px] text-muted-foreground"
const INDENT_STEP_REM = 1.1

export interface FileFieldCandidate extends FileFieldDecl {
  checked: boolean
  /** true = auto-matched a declared io.inputs field on import (PM 2026-07-03). */
  matched?: boolean
}

export interface FileGroup {
  /** Display label, e.g. the imported file/folder name. */
  label: string
  /** Muted path shown after the label (PM r3b: 一眼认出是文件). */
  pathHint: string
  candidates: FileFieldCandidate[]
  /** Workspace-relative path of the single imported file (edit-in-editor, P5). */
  filePath?: string
}

/** `chapter_{n}.json` / `chapter` stem out of a folded batch entry. */
function batchStem(entry: IoScanEntry): string {
  const pattern = entry.pattern ?? entry.stem ?? entry.name
  return pattern.split(/_?\{n\}/)[0].replace(/\.[^.]+$/, "") || pattern
}

/** Flatten an import/scan response into checkable per-field candidates. */
export function candidatesFromScanEntries(entries: IoScanEntry[]): FileFieldCandidate[] {
  const rows: FileFieldCandidate[] = []
  for (const entry of entries) {
    if (entry.kind === "dir") {
      rows.push(...candidatesFromScanEntries(entry.entries ?? []))
      continue
    }
    if (entry.kind === "batch") {
      // The declared field is the stem (`chapter`), NOT the folder it lives in
      // — so it can auto-match io.inputs and save as the right field name.
      rows.push({
        field: batchStem(entry),
        type: "array",
        dir: entry.dir,
        pattern: entry.pattern,
        numbers: entry.numbers,
        checked: false,
      })
      continue
    }
    for (const field of entry.fields ?? []) {
      rows.push({
        field: field.name,
        type: field.type ?? null,
        path: entry.path,
        checked: false,
      })
    }
  }
  return rows
}

/**
 * Normalize a field/stem for tolerant auto-matching: lowercase and drop a
 * trailing numeric or `{n}` batch segment so `Chapter`, `chapter1`,
 * `chapter_001` and `chapter_{n}.json` all reduce to `chapter`.
 */
export function normalizeFieldName(name: string): string {
  return name
    .trim()
    .toLowerCase()
    .replace(/\.[^.]+$/, "")
    .replace(/_?\{n\}$/, "")
    .replace(/[._-]?\d+$/, "")
}

/**
 * Auto-match imported candidates against the node/GRAPH.md declared io.inputs
 * field names (input region F5, PM 2026-07-02 r2「推断…是否匹配」): a candidate
 * whose normalized name equals a declared input is checked + flagged `matched`
 * so the author doesn't re-tick every field the import already answers.
 */
export function matchCandidatesToInputs(
  candidates: FileFieldCandidate[],
  declaredInputNames: readonly string[],
): FileFieldCandidate[] {
  const declared = new Set(declaredInputNames.map(normalizeFieldName))
  return candidates.map((candidate) => {
    const matched = declared.has(normalizeFieldName(candidate.field))
    return { ...candidate, matched, checked: matched ? true : candidate.checked }
  })
}

/** Group key = the source file (single path, or batch dir+pattern). */
function fileKeyOf(candidate: FileFieldCandidate): string {
  if (candidate.path) {
    return candidate.path
  }
  if (candidate.dir && candidate.pattern) {
    return `${candidate.dir}::${candidate.pattern}`
  }
  return candidate.field
}

/**
 * Group candidate fields by their source FILE so each imported/declared file is
 * one row (name + path + remove + edit-in-editor, P5), with its fields under it
 * — instead of flattening a whole folder's fields into one anonymous list.
 */
export function groupCandidatesByFile(candidates: FileFieldCandidate[]): FileGroup[] {
  const byFile = new Map<string, FileFieldCandidate[]>()
  const order: string[] = []
  for (const candidate of candidates) {
    const key = fileKeyOf(candidate)
    if (!byFile.has(key)) {
      byFile.set(key, [])
      order.push(key)
    }
    byFile.get(key)!.push(candidate)
  }
  return order.map((key) => {
    const members = byFile.get(key)!
    const first = members[0]
    const isBatch = Boolean(first.dir && first.pattern)
    const fileName = first.path ? first.path.split(/[\\/]/).pop() ?? first.path : first.field
    return {
      label: isBatch ? `${first.field} ×${first.numbers?.length ?? "?"}` : fileName,
      pathHint: first.path ?? first.dir ?? "",
      candidates: members,
      // Edit-in-editor only makes sense for a single concrete file, not a batch.
      ...(first.path && !isBatch ? { filePath: first.path } : {}),
    }
  })
}

/** Runtime_config import declarations shown as already-checked per-file groups. */
export function groupsFromDeclarations(
  declarations: FileFieldDecl[],
  declaredInputNames: readonly string[] = [],
): FileGroup[] {
  const declared = new Set(declaredInputNames.map(normalizeFieldName))
  const schemaOrder = new Map(declaredInputNames.map((name, index) => [normalizeFieldName(name), index]))
  return groupCandidatesByFile(declarations.map((decl) => ({
    ...decl,
    checked: declared.has(normalizeFieldName(decl.field)),
  }))).sort((left, right) => {
    const leftIndex = firstSchemaIndex(left, schemaOrder)
    const rightIndex = firstSchemaIndex(right, schemaOrder)
    if (leftIndex !== rightIndex) {
      return leftIndex - rightIndex
    }
    return left.pathHint.localeCompare(right.pathHint)
  })
}

function firstSchemaIndex(group: FileGroup, schemaOrder: Map<string, number>): number {
  let best = Number.POSITIVE_INFINITY
  for (const candidate of group.candidates) {
    const index = schemaOrder.get(normalizeFieldName(candidate.field))
    if (index !== undefined && index < best) {
      best = index
    }
  }
  return best
}

/** `chapter.meta.title` → `[chapter, chapter.meta]` — every ancestor object path. */
function ancestorPrefixes(path: string): string[] {
  const parts = path.split(".")
  const out: string[] = []
  for (let i = 1; i < parts.length; i += 1) {
    out.push(parts.slice(0, i).join("."))
  }
  return out
}

function indentStyle(depth: number): CSSProperties {
  return { paddingLeft: `${0.5 + depth * INDENT_STEP_REM}rem` }
}

function diagnosticMessage(error: LintError): string {
  const code = formatDiagnosticCode(error.error_code)
  return code ? `${code} ${error.message}` : error.message
}

function FieldDiagnosticMarker({ errors }: { errors?: readonly LintError[] | null }) {
  if (!errors || errors.length === 0) {
    return null
  }
  const hasError = errors.some((error) => error.severity === "error")
  const tone = hasError ? "text-destructive" : "text-warning"
  const messages = errors.map(diagnosticMessage)
  const count = errors.length === 1 ? "1 issue" : `${errors.length} issues`
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <span
          role="img"
          aria-label={`Field has ${count}: ${messages.join("; ")}`}
          data-io-field-diagnostic="true"
          className={`inline-flex shrink-0 items-center ${tone}`}
        >
          <AlertTriangle className="size-3.5" aria-hidden />
        </span>
      </TooltipTrigger>
      <TooltipContent side="top">
        <ul className="space-y-0.5">
          {messages.map((message, index) => (
            <li key={`${errors[index]?.error_code ?? "err"}-${index}`}>{message}</li>
          ))}
        </ul>
      </TooltipContent>
    </Tooltip>
  )
}

/**
 * A field the md io declares (required) but the blackboard/universe doesn't
 * supply — muted + danger, non-checkable, with the reason. Mirrors the engine's
 * runtime [F-v3-runtime-state-mapping-failed], now at nested granularity.
 */
function MissingFieldRow({ row, errors }: { row: ReconciledFieldRow; errors?: readonly LintError[] }) {
  return (
    <div className={`${ROW_CLASS} bg-destructive/10`} style={indentStyle(row.depth)}>
      <AlertTriangle className="size-3.5 shrink-0 text-destructive" aria-hidden />
      <span className="font-mono text-xs text-muted-foreground line-through decoration-destructive/40">
        {row.name}
      </span>
      <FieldDiagnosticMarker errors={errors} />
      <span className="text-[11px] text-destructive">{row.reason}</span>
    </div>
  )
}

/** One expandable/checkable field row (indent by depth, caret when it nests). */
function FieldCheckRow({
  row,
  checked,
  selectable,
  onCheckedChange,
  expanded,
  onToggleExpand,
  highlighted,
  errors,
}: {
  row: ReconciledFieldRow
  checked: boolean
  /** false = display-only (a nested output sub-field carried by its parent). */
  selectable: boolean
  onCheckedChange: (next: boolean) => void
  expanded: boolean
  onToggleExpand?: () => void
  highlighted: boolean
  errors?: readonly LintError[]
}) {
  return (
    <div
      className={`${ROW_CLASS} border-l-2 ${highlighted ? "border-l-primary bg-accent" : "border-l-transparent"}`}
      style={indentStyle(row.depth)}
    >
      {row.hasChildren ? (
        <button
          type="button"
          onClick={onToggleExpand}
          aria-label={`${expanded ? "Collapse" : "Expand"} ${row.path}`}
          className="text-muted-foreground transition-colors hover:text-foreground"
        >
          {expanded ? <ChevronDown className="size-3.5" /> : <ChevronRight className="size-3.5" />}
        </button>
      ) : (
        <span className="size-3.5 shrink-0" aria-hidden />
      )}
      {selectable ? (
        <Checkbox
          checked={checked}
          onCheckedChange={(value) => onCheckedChange(value === true)}
          aria-label={`Toggle field ${row.path}`}
        />
      ) : (
        <span className="size-3.5 shrink-0" aria-hidden />
      )}
      <span
        className={`font-mono text-xs ${highlighted ? "text-accent-foreground" : "text-foreground"}`}
      >
        {row.name}
      </span>
      <FieldDiagnosticMarker errors={errors} />
      <span className={META_CLASS}>
        {row.type ?? "any"}
        {row.from ? ` · from ${row.from}` : ""}
      </span>
    </div>
  )
}

/**
 * Reconciled field rows → an expandable nested tree. Missing rows show first
 * (always visible); the rest form a collapsible tree (default fully expanded so
 * nested sub-fields are visible without a click). `selectableMaxDepth` limits
 * which depths are checkable — the input tree checks any depth (nested
 * addressing), the output tree only depth 0 (artifacts carry whole fields).
 */
function FieldCheckTree({
  rows,
  checkOf,
  onToggleCheck,
  selectableMaxDepth = Number.POSITIVE_INFINITY,
  diagnosticsByField = {},
}: {
  rows: ReconciledFieldRow[]
  checkOf: (row: ReconciledFieldRow) => boolean
  onToggleCheck: (row: ReconciledFieldRow, next: boolean) => void
  selectableMaxDepth?: number
  diagnosticsByField?: Record<string, LintError[]>
}) {
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set())
  const toggleExpand = (path: string) => {
    setCollapsed((prev) => {
      const next = new Set(prev)
      if (next.has(path)) {
        next.delete(path)
      } else {
        next.add(path)
      }
      return next
    })
  }
  const missing = rows.filter((row) => row.state === "missing")
  const tree = rows.filter((row) => row.state !== "missing")
  const visible = tree.filter((row) => ancestorPrefixes(row.path).every((ancestor) => !collapsed.has(ancestor)))
  return (
    <div className="divide-y divide-border">
      {missing.map((row) => (
        <MissingFieldRow key={`missing-${row.path}`} row={row} errors={diagnosticsByField[row.path] ?? diagnosticsByField[row.name]} />
      ))}
      {visible.map((row) => (
        <FieldCheckRow
          key={row.path}
          row={row}
          checked={checkOf(row)}
          selectable={row.depth <= selectableMaxDepth}
          onCheckedChange={(next) => onToggleCheck(row, next)}
          expanded={!collapsed.has(row.path)}
          onToggleExpand={() => toggleExpand(row.path)}
          highlighted={row.state === "matched" && checkOf(row)}
          errors={diagnosticsByField[row.path] ?? diagnosticsByField[row.name]}
        />
      ))}
    </div>
  )
}

/**
 * One "Import…" folder picker + the resulting per-file checkable field groups.
 * A folder import scans + folds its files (batches, subfolders); each file
 * becomes one group whose fields auto-match the declared io.inputs (checked +
 * highlighted). Single import entry only — a folder already imports every file
 * under it (PM 2026-07-03), so there is no separate file button.
 */
function FileImportGroups({
  skillId,
  workspaceRoot,
  importNodeId,
  declaredInputNames,
  groups,
  busy,
  setBusy,
  error,
  setError,
  onGroupsChange,
  onRuntimeConfigRefresh,
  onFileOpen,
  diagnosticsByField = {},
}: {
  skillId: string
  workspaceRoot?: string | null
  importNodeId?: string | null
  declaredInputNames: readonly string[]
  groups: FileGroup[]
  busy: boolean
  setBusy: (busy: boolean) => void
  error: string | null
  setError: (error: string | null) => void
  onGroupsChange: (groups: FileGroup[]) => void
  onRuntimeConfigRefresh?: () => Promise<unknown> | unknown
  onFileOpen?: (path: string) => void
  diagnosticsByField?: Record<string, LintError[]>
}) {
  const importPath = async (path: string | null) => {
    if (!path) {
      return
    }
    setBusy(true)
    setError(null)
    try {
      const result = await importIoIntoWorkspace(skillId, path, { nodeId: importNodeId ?? null })
      const imported = groupCandidatesByFile(
        matchCandidatesToInputs(candidatesFromScanEntries(result.entries), declaredInputNames),
      )
      await onRuntimeConfigRefresh?.()
      onGroupsChange([...groups, ...imported])
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }
  const toggleCandidate = (groupIndex: number, candidateIndex: number, next: boolean) => {
    onGroupsChange(
      groups.map((group, gi) =>
        gi === groupIndex
          ? {
              ...group,
              candidates: group.candidates.map((candidate, ci) =>
                ci === candidateIndex ? { ...candidate, checked: next } : candidate,
              ),
            }
          : group,
      ),
    )
  }
  const folderPathFor = (group: FileGroup): string | null => {
    const rel = group.filePath ?? group.pathHint
    if (!rel || !workspaceRoot) {
      return null
    }
    const workspaceRel = rel.split("/").slice(0, -1).join("/")
    const folderRel = group.filePath ? workspaceRel : rel
    return `${workspaceRoot.replace(/[\\/]+$/, "")}/.workspace/${folderRel}`.replaceAll("\\", "/")
  }
  const deleteGroup = async (group: FileGroup, groupIndex: number) => {
    const rel = group.filePath ?? group.pathHint
    if (!rel) {
      return
    }
    setBusy(true)
    setError(null)
    try {
      await deleteWorkspacePath(workspaceRoot ?? skillId, `.workspace/${rel}`)
      await onRuntimeConfigRefresh?.()
      onGroupsChange(groups.filter((_, gi) => gi !== groupIndex))
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }
  return (
    <>
      {groups.map((group, groupIndex) => (
        <div key={`${group.label}-${groupIndex}`} className="rounded-md border border-border">
          <div className={GROUP_HEAD_CLASS}>
            <FileText className="size-3.5 shrink-0 self-center text-muted-foreground" aria-hidden />
            <span className="font-mono text-xs text-foreground">{group.label}</span>
            <Tooltip>
              <TooltipTrigger asChild>
                <span className={PATH_CLASS}>{group.pathHint}</span>
              </TooltipTrigger>
              <TooltipContent side="top" align="start">
                <span className="font-mono text-xs">{group.pathHint}</span>
              </TooltipContent>
            </Tooltip>
            {group.filePath && onFileOpen ? (
              <button
                type="button"
                onClick={() => onFileOpen(`.workspace/${group.filePath}`)}
                aria-label={`Edit file ${group.label}`}
                className="text-muted-foreground transition-colors hover:text-foreground"
              >
                <Pencil className="size-3.5" />
              </button>
            ) : null}
            {folderPathFor(group) ? (
              <button
                type="button"
                onClick={() => {
                  const folder = folderPathFor(group)
                  if (folder) {
                    void openLocalPath(folder)
                  }
                }}
                aria-label={`Open folder ${group.label}`}
                className="text-muted-foreground transition-colors hover:text-foreground"
              >
                <FolderOpen className="size-3.5" />
              </button>
            ) : null}
            <button
              type="button"
              onClick={() => void deleteGroup(group, groupIndex)}
              aria-label={`Remove file group ${group.label}`}
              className="text-muted-foreground transition-colors hover:text-destructive"
            >
              <Trash2 className="size-3.5" />
            </button>
          </div>
          <div className="divide-y divide-border">
            {group.candidates.map((candidate, candidateIndex) => (
              <label
                key={`${candidate.field}-${candidateIndex}`}
                className={`${ROW_CLASS} cursor-pointer ${candidate.matched ? "bg-accent" : ""}`}
                style={indentStyle(1)}
              >
                <Checkbox
                  checked={candidate.checked}
                  onCheckedChange={(value) => toggleCandidate(groupIndex, candidateIndex, value === true)}
                  aria-label={`Toggle file field ${candidate.field}`}
                />
                <span className="font-mono text-xs text-foreground">{candidate.field}</span>
                <FieldDiagnosticMarker errors={diagnosticsByField[candidate.field]} />
                <span className={META_CLASS}>
                  {candidate.dir
                    ? `batch ×${candidate.numbers?.length ?? "?"} · numbers kept`
                    : `${candidate.type ?? "any"} · runtime file`}
                  {candidate.matched ? " · matched io.inputs" : ""}
                </span>
              </label>
            ))}
          </div>
        </div>
      ))}
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button
            type="button"
            size="sm"
            variant="secondary"
            disabled={busy}
            aria-label="Import file or folder"
            className="h-7 gap-1 text-[11px]"
          >
            {busy ? <Loader2 className="size-3.5 animate-spin" aria-hidden /> : <FolderOpen className="size-3.5" aria-hidden />}
            Import…
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="start">
          <DropdownMenuItem onSelect={() => { void selectImportFile().then(importPath) }}>
            Import file
          </DropdownMenuItem>
          <DropdownMenuItem onSelect={() => { void selectImportFolder().then(importPath) }}>
            Import folder
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
      {error ? (
        <p className="rounded-md border border-destructive/30 bg-destructive/10 px-2 py-1 text-xs text-destructive">
          {error}
        </p>
      ) : null}
    </>
  )
}

export interface InputConfigInlineProps {
  skillId: string
  /**
   * Reconciled blackboard context rows (matched/available/missing), nested;
   * empty for the Input pseudo-node / GRAPH.md except declared graph inputs.
   */
  blackboard: ReconciledFieldRow[]
  /** Runtime_config import declarations of the target scope. */
  declaredFiles: FileFieldDecl[]
  /** Null = Input/Test Inputs root import scope; phase id = node-scoped imports. */
  importNodeId?: string | null
  /** Declared io.inputs field names an imported file auto-matches against. */
  declaredInputNames: readonly string[]
  onSave: (checks: { blackboard: IoInputCheckRow[]; files: FileFieldDecl[]; fileFieldNames?: string[] }) => Promise<string | null>
  onRuntimeConfigRefresh?: () => Promise<unknown> | unknown
  workspaceRoot?: string | null
  conflicts?: RuntimeInputConflict[]
  /** Open an imported file in the editor (P5 edit button). */
  onFileOpen?: (path: string) => void
  /** true for the Input pseudo-node / GRAPH.md (declared entry fields, no blackboard). */
  isGraphInput?: boolean
  diagnosticsByField?: Record<string, LintError[]>
}

/**
 * Inline (in-panel) input config: the nested blackboard checkbox tree + file
 * import groups. Replaces the old modal so the config lives with the
 * selected node like the Properties panel (PM 2026-07-03).
 */
export function InputConfigInline({
  skillId,
  blackboard,
  declaredFiles,
  importNodeId = null,
  declaredInputNames,
  onSave,
  onRuntimeConfigRefresh,
  workspaceRoot,
  conflicts = [],
  onFileOpen,
  isGraphInput = false,
  diagnosticsByField = {},
}: InputConfigInlineProps) {
  const [blackboardChecks, setBlackboardChecks] = useState<Record<string, boolean>>({})
  const saveSeq = useRef(0)
  const initialGroups = useMemo(
    () => groupsFromDeclarations(declaredFiles, declaredInputNames),
    [declaredFiles, declaredInputNames],
  )
  const [groups, setGroups] = useState<FileGroup[] | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)

  const effectiveGroups = groups ?? initialGroups
  const isChecked = (row: ReconciledFieldRow) => blackboardChecks[row.path] ?? row.checked

  const persist = async (nextGroups: FileGroup[], nextBlackboardChecks = blackboardChecks) => {
    const seq = saveSeq.current + 1
    saveSeq.current = seq
    setSaving(true)
    setError(null)
    const files = nextGroups.flatMap((group) =>
      group.candidates
        .filter((candidate) => candidate.checked)
        .map((candidate) => {
          // `checked`/`matched` are UI-only — persist just the FileFieldDecl.
          const { checked, matched, ...decl } = candidate
          void checked
          void matched
          return decl
        }),
    )
    const fileFieldNames = Array.from(new Set([
      ...declaredFiles.map((decl) => decl.field),
      ...nextGroups.flatMap((group) => group.candidates.map((candidate) => candidate.field)),
    ]))
    const failure = await onSave({
      // Missing rows have no blackboard supply — never persist them as consumed.
      blackboard: blackboard
        .filter((row) => row.state !== "missing")
        .map((row) => ({ path: row.path, type: row.type, checked: nextBlackboardChecks[row.path] ?? row.checked })),
      files,
      fileFieldNames,
    })
    if (seq === saveSeq.current) {
      setSaving(false)
      setError(failure)
    }
  }
  const updateGroups = (nextGroups: FileGroup[]) => {
    setGroups(nextGroups)
    void persist(nextGroups)
  }

  return (
    <div className="space-y-2">
      <div className="flex justify-end">
        {saving ? <Badge variant="secondary" className="h-5 px-1.5 text-[10px]">saving</Badge> : null}
      </div>
      {conflicts.length > 0 ? (
        <div className="rounded-md border border-destructive/30 bg-destructive/10 px-2 py-1 text-xs text-destructive">
          {conflicts.map((conflict) => (
            <div key={conflict.field}>
              {conflict.field}: multiple runtime file candidates. Lint/compile will fail until only one remains.
            </div>
          ))}
        </div>
      ) : null}
      <div className="overflow-hidden rounded-md border border-border">
        <div className={GROUP_HEAD_CLASS}>
          <span className="text-xs font-medium text-foreground">
            {isGraphInput ? "Graph inputs" : "Blackboard context"}
          </span>
          <span className={META_CLASS}>
            {isGraphInput
              ? "declared entry fields — import a file to source them"
              : "fields on the blackboard when this node runs"}
          </span>
        </div>
        {blackboard.length > 0 ? (
          <FieldCheckTree
            rows={blackboard}
            checkOf={isChecked}
            onToggleCheck={(row, next) => {
              const nextChecks = { ...blackboardChecks, [row.path]: next }
              setBlackboardChecks(nextChecks)
              void persist(effectiveGroups, nextChecks)
            }}
            diagnosticsByField={diagnosticsByField}
          />
        ) : (
          <p className="px-2 py-3 text-xs text-muted-foreground">
            No blackboard fields — import a file below to add input fields.
          </p>
        )}
      </div>
      <FileImportGroups
        skillId={skillId}
        workspaceRoot={workspaceRoot}
        importNodeId={importNodeId}
        declaredInputNames={declaredInputNames}
        groups={effectiveGroups}
        onGroupsChange={updateGroups}
        busy={busy}
        setBusy={setBusy}
        error={error}
        setError={setError}
        onRuntimeConfigRefresh={onRuntimeConfigRefresh}
        onFileOpen={onFileOpen}
        diagnosticsByField={diagnosticsByField}
      />
    </div>
  )
}

export interface OutputConfigDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  /**
   * Reconciled field universe (matched/available/missing), nested. Missing = a
   * required io.outputs field no phase produces (shown once at the top); matched
   * = a declared io.outputs member (highlighted in each card). Nested sub-fields
   * are shown for shape but not independently checkable (artifacts carry a whole
   * top-level field — the engine writer resolves top-level keys only).
   */
  universe: ReconciledFieldRow[]
  artifacts: ArtifactRow[]
  /** Count shown on the per-item toggle (from the input batch numbers), if known. */
  perItemCount?: number | null
  onSave: (artifacts: ArtifactRow[]) => Promise<string | null>
}

export function OutputConfigDialog({
  open,
  onOpenChange,
  universe,
  artifacts,
  perItemCount = null,
  onSave,
}: OutputConfigDialogProps) {
  const [rows, setRows] = useState<ArtifactRow[] | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const effectiveRows = rows ?? artifacts
  const missingOutputs = universe.filter((row) => row.state === "missing")
  const carryableFields = universe.filter((row) => row.state !== "missing")

  const updateRow = (index: number, patch: Partial<ArtifactRow>) => {
    setRows(effectiveRows.map((row, i) => (i === index ? { ...row, ...patch } : row)))
  }

  const toggleField = (index: number, field: string, next: boolean) => {
    const row = effectiveRows[index]
    const fields = next ? [...row.fields, field] : row.fields.filter((name) => name !== field)
    updateRow(index, { fields })
  }

  const handleSave = async () => {
    setBusy(true)
    setError(null)
    const cleaned = effectiveRows.filter((row) => row.stem.trim() !== "")
    const failure = await onSave(cleaned)
    setBusy(false)
    setError(failure)
    if (!failure) {
      onOpenChange(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>Output artifacts — runtime_config</DialogTitle>
          <DialogDescription>
            Each file carries the blackboard fields you check; on-disk naming is fixed.
          </DialogDescription>
        </DialogHeader>
        <div className="max-h-[55vh] space-y-3 overflow-y-auto">
          {missingOutputs.length > 0 ? (
            <div className="overflow-hidden rounded-md border border-destructive/30">
              {missingOutputs.map((row) => (
                <MissingFieldRow key={row.path} row={row} />
              ))}
            </div>
          ) : null}
          {effectiveRows.map((row, index) => (
            <div key={index} className="rounded-md border border-border">
              <div className={GROUP_HEAD_CLASS}>
                {row.mode === "per-item" ? (
                  <Files className="size-3.5 shrink-0 self-center text-muted-foreground" aria-hidden />
                ) : (
                  <FileText className="size-3.5 shrink-0 self-center text-muted-foreground" aria-hidden />
                )}
                <Input
                  value={row.stem}
                  onChange={(event) => updateRow(index, { stem: event.target.value })}
                  aria-label={`Artifact stem ${index + 1}`}
                  className="h-7 w-44 font-mono text-xs"
                />
                <span
                  className="inline-flex overflow-hidden rounded-md border border-border text-[11px]"
                  role="group"
                  aria-label="Artifact mode"
                >
                  <button
                    type="button"
                    onClick={() => updateRow(index, { mode: "single" })}
                    className={`whitespace-nowrap px-2 py-0.5 ${row.mode === "single" ? "bg-foreground text-background" : "text-muted-foreground"}`}
                  >
                    single
                  </button>
                  <button
                    type="button"
                    onClick={() => updateRow(index, { mode: "per-item" })}
                    className={`whitespace-nowrap px-2 py-0.5 ${row.mode === "per-item" ? "bg-foreground text-background" : "text-muted-foreground"}`}
                  >
                    per-item{perItemCount ? ` ×${perItemCount}` : ""}
                  </button>
                </span>
                <span className="flex-1" />
                <button
                  type="button"
                  onClick={() => setRows(effectiveRows.filter((_, i) => i !== index))}
                  aria-label={`Remove artifact ${row.stem || index + 1}`}
                  className="text-muted-foreground transition-colors hover:text-destructive"
                >
                  <Trash2 className="size-3.5" />
                </button>
              </div>
              <FieldCheckTree
                rows={carryableFields}
                checkOf={(field) => field.depth === 0 && row.fields.includes(field.name)}
                onToggleCheck={(field, next) => toggleField(index, field.name, next)}
                selectableMaxDepth={0}
              />
              <p className="border-t border-border px-3 py-1.5 font-mono text-[11px] text-muted-foreground">
                {row.mode === "per-item"
                  ? `${row.stem || "<stem>"}/${row.stem || "<stem>"}_001_latest_<ts>.json …`
                  : `${row.stem || "<stem>"}_latest_<ts>.${row.format === "md" ? "md" : "json"} · history/`}
              </p>
            </div>
          ))}
          <Button
            type="button"
            size="sm"
            variant="secondary"
            onClick={() => setRows([...effectiveRows, { stem: "", mode: "single", fields: [] }])}
            aria-label="Add artifact"
          >
            <Plus className="size-3.5" aria-hidden />
            Add artifact
          </Button>
        </div>
        {error ? (
          <p className="rounded-md border border-destructive/30 bg-destructive/10 px-2 py-1 text-xs text-destructive">
            {error}
          </p>
        ) : null}
        <DialogFooter>
          <Button type="button" variant="ghost" size="sm" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button type="button" size="sm" onClick={() => void handleSave()} disabled={busy}>
            Save
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
