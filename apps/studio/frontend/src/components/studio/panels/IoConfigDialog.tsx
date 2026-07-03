import { useMemo, useState, type CSSProperties } from "react"
import {
  AlertTriangle,
  ChevronDown,
  ChevronRight,
  FileText,
  Files,
  FolderOpen,
  Loader2,
  Plus,
  Trash2,
} from "lucide-react"
import { importIoIntoWorkspace, type IoScanEntry } from "@/api/client"
import { selectImportFile, selectImportFolder } from "@/lib/tauri"
import { Button } from "@/components/ui/button"
import { Checkbox } from "@/components/ui/checkbox"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import type {
  ArtifactRow,
  FileFieldDecl,
  IoInputCheckRow,
  ReconciledFieldRow,
} from "@/lib/io-config"
import { errorMessage } from "@/utils/errors"

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
}

export interface FileGroup {
  /** Display label, e.g. the imported file/folder name. */
  label: string
  /** Muted path shown after the label (PM r3b: 一眼认出是文件). */
  pathHint: string
  candidates: FileFieldCandidate[]
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
      rows.push({
        field: (entry.dir ?? entry.name).split("/").pop() ?? entry.name,
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

/** Existing `source:'file'` declarations shown as an already-checked group. */
export function groupFromDeclarations(declarations: FileFieldDecl[]): FileGroup | null {
  if (declarations.length === 0) {
    return null
  }
  return {
    label: "Declared files",
    pathHint: "",
    candidates: declarations.map((decl) => ({ ...decl, checked: true })),
  }
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

/**
 * A field the md io declares (required) but the blackboard/universe doesn't
 * supply — muted + danger, non-checkable, with the reason. Mirrors the engine's
 * runtime [F-v3-runtime-state-mapping-failed], now at nested granularity.
 */
function MissingFieldRow({ row }: { row: ReconciledFieldRow }) {
  return (
    <div className={`${ROW_CLASS} bg-destructive/10`} style={indentStyle(row.depth)}>
      <AlertTriangle className="size-3.5 shrink-0 text-destructive" aria-hidden />
      <span className="font-mono text-xs text-muted-foreground line-through decoration-destructive/40">
        {row.name}
      </span>
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
}: {
  row: ReconciledFieldRow
  checked: boolean
  /** false = display-only (a nested output sub-field carried by its parent). */
  selectable: boolean
  onCheckedChange: (next: boolean) => void
  expanded: boolean
  onToggleExpand?: () => void
  highlighted: boolean
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
}: {
  rows: ReconciledFieldRow[]
  checkOf: (row: ReconciledFieldRow) => boolean
  onToggleCheck: (row: ReconciledFieldRow, next: boolean) => void
  selectableMaxDepth?: number
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
        <MissingFieldRow key={`missing-${row.path}`} row={row} />
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
        />
      ))}
    </div>
  )
}

/** Import file/folder buttons + the resulting per-file checkable field groups. */
function FileImportGroups({
  skillId,
  groups,
  setGroups,
  busy,
  setBusy,
  error,
  setError,
}: {
  skillId: string
  groups: FileGroup[]
  setGroups: (groups: FileGroup[]) => void
  busy: boolean
  setBusy: (busy: boolean) => void
  error: string | null
  setError: (error: string | null) => void
}) {
  const importPath = async (path: string | null) => {
    if (!path) {
      return
    }
    setBusy(true)
    setError(null)
    try {
      const result = await importIoIntoWorkspace(skillId, path)
      const candidates = candidatesFromScanEntries(result.entries)
      const label = path.replace(/[\\/]+$/, "").split(/[\\/]/).pop() ?? path
      setGroups([...groups, { label, pathHint: path, candidates }])
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }
  const toggleCandidate = (groupIndex: number, candidateIndex: number, next: boolean) => {
    setGroups(
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
  return (
    <>
      {groups.map((group, groupIndex) => (
        <div key={`${group.label}-${groupIndex}`} className="rounded-md border border-border">
          <div className={GROUP_HEAD_CLASS}>
            <FileText className="size-3.5 shrink-0 self-center text-muted-foreground" aria-hidden />
            <span className="font-mono text-xs text-foreground">{group.label}</span>
            <span className={PATH_CLASS}>{group.pathHint}</span>
            <button
              type="button"
              onClick={() => setGroups(groups.filter((_, gi) => gi !== groupIndex))}
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
                className={`${ROW_CLASS} cursor-pointer`}
                style={indentStyle(1)}
              >
                <Checkbox
                  checked={candidate.checked}
                  onCheckedChange={(value) => toggleCandidate(groupIndex, candidateIndex, value === true)}
                  aria-label={`Toggle file field ${candidate.field}`}
                />
                <span className="font-mono text-xs text-foreground">{candidate.field}</span>
                <span className={META_CLASS}>
                  {candidate.dir
                    ? `batch ×${candidate.numbers?.length ?? "?"} · numbers kept`
                    : `${candidate.type ?? "any"} · source: file`}
                </span>
              </label>
            ))}
          </div>
        </div>
      ))}
      <div className="flex items-center gap-2">
        <Button
          type="button"
          size="sm"
          variant="secondary"
          onClick={() => void selectImportFile().then(importPath)}
          disabled={busy}
          aria-label="Import file"
          className="h-7 gap-1 text-[11px]"
        >
          {busy ? <Loader2 className="size-3.5 animate-spin" aria-hidden /> : <FileText className="size-3.5" aria-hidden />}
          Import file…
        </Button>
        <Button
          type="button"
          size="sm"
          variant="secondary"
          onClick={() => void selectImportFolder().then(importPath)}
          disabled={busy}
          aria-label="Import folder"
          className="h-7 gap-1 text-[11px]"
        >
          <FolderOpen className="size-3.5" aria-hidden />
          Import folder…
        </Button>
      </div>
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
  /** Existing source:'file' declarations of the target document. */
  declaredFiles: FileFieldDecl[]
  onSave: (checks: { blackboard: IoInputCheckRow[]; files: FileFieldDecl[] }) => Promise<string | null>
  /** true for the Input pseudo-node / GRAPH.md (declared entry fields, no blackboard). */
  isGraphInput?: boolean
}

/**
 * Inline (in-panel) input config: the nested blackboard checkbox tree + file
 * import groups + Save. Replaces the old modal so the config lives with the
 * selected node like the Properties panel (PM 2026-07-03).
 */
export function InputConfigInline({
  skillId,
  blackboard,
  declaredFiles,
  onSave,
  isGraphInput = false,
}: InputConfigInlineProps) {
  const [blackboardChecks, setBlackboardChecks] = useState<Record<string, boolean>>({})
  const initialGroup = useMemo(() => groupFromDeclarations(declaredFiles), [declaredFiles])
  const [groups, setGroups] = useState<FileGroup[] | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const effectiveGroups = groups ?? (initialGroup ? [initialGroup] : [])
  const isChecked = (row: ReconciledFieldRow) => blackboardChecks[row.path] ?? row.checked

  const handleSave = async () => {
    setBusy(true)
    setError(null)
    const files = effectiveGroups.flatMap((group) =>
      group.candidates
        .filter((candidate) => candidate.checked)
        .map((candidate) => {
          const { checked, ...decl } = candidate
          void checked
          return decl
        }),
    )
    const failure = await onSave({
      // Missing rows have no blackboard supply — never persist them as consumed.
      blackboard: blackboard
        .filter((row) => row.state !== "missing")
        .map((row) => ({ path: row.path, type: row.type, checked: isChecked(row) })),
      files,
    })
    setBusy(false)
    setError(failure)
  }

  return (
    <div className="space-y-2">
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
            onToggleCheck={(row, next) => setBlackboardChecks((prev) => ({ ...prev, [row.path]: next }))}
          />
        ) : (
          <p className="px-2 py-3 text-xs text-muted-foreground">
            No blackboard fields — import a file below to add input fields.
          </p>
        )}
      </div>
      <FileImportGroups
        skillId={skillId}
        groups={effectiveGroups}
        setGroups={setGroups}
        busy={busy}
        setBusy={setBusy}
        error={error}
        setError={setError}
      />
      <Button type="button" size="sm" onClick={() => void handleSave()} disabled={busy} className="h-7 text-[11px]">
        Save input config
      </Button>
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
          <DialogTitle>Output artifacts — GRAPH.md io</DialogTitle>
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
