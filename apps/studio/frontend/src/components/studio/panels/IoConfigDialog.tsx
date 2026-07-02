import { useMemo, useState } from "react"
import { AlertTriangle, FileText, Files, Loader2, Plus, Trash2 } from "lucide-react"
import { importIoIntoWorkspace, type IoScanEntry } from "@/api/client"
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
  ReconciledFieldRow,
} from "@/lib/io-config"
import { errorMessage } from "@/utils/errors"

/**
 * Blackboard-first I/O config dialogs (input region F3/F7, PM 2026-07-02 r3).
 *
 * Input: a checkbox tree — the blackboard context is ALWAYS the first group
 * (checked = the node's io.inputs slice); Add file imports an external
 * file/folder into `.workspace/imports/` and appends its recognized fields
 * (checked = `source:'file'` additions). The Input pseudo-node has no
 * blackboard group — its checked file fields become the graph entry fields.
 *
 * Output: the artifacts manifest — Add artifact adds a file card; every card
 * offers the SAME full blackboard field list (only the checks differ);
 * single/per-item is a compact segmented toggle; the fixed on-disk naming is
 * previewed per card and owned by the engine writer.
 */

const ROW_CLASS = "flex items-center gap-2 border-b border-border px-3 py-1.5 last:border-b-0"
const GROUP_HEAD_CLASS = "flex items-baseline gap-2 border-b border-border bg-muted/40 px-3 py-2"
const PATH_CLASS = "min-w-0 flex-1 truncate text-[11px] text-muted-foreground"
const META_CLASS = "text-[11px] text-muted-foreground"

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

function FieldCheckRow({
  checked,
  onCheckedChange,
  name,
  meta,
  indent = false,
  highlighted = false,
}: {
  checked: boolean
  onCheckedChange: (next: boolean) => void
  name: string
  meta: string
  indent?: boolean
  /** r4: whole-row accent highlight when the field matches the md io declaration. */
  highlighted?: boolean
}) {
  return (
    <label
      className={`${ROW_CLASS} ${indent ? "pl-7" : ""} cursor-pointer border-l-2 ${highlighted ? "border-l-primary bg-accent" : "border-l-transparent"}`}
    >
      <Checkbox
        checked={checked}
        onCheckedChange={(value) => onCheckedChange(value === true)}
        aria-label={`Toggle field ${name}`}
      />
      <span className={`font-mono text-xs ${highlighted ? "text-accent-foreground" : "text-foreground"}`}>
        {name}
      </span>
      <span className={META_CLASS}>{meta}</span>
    </label>
  )
}

/**
 * r4: a field the md io declares (required) but the actual blackboard/universe
 * doesn't supply — shown at the TOP, muted + danger, non-checkable, with the
 * reason. Mirrors the engine's runtime [F-v3-runtime-state-mapping-failed].
 */
function MissingFieldRow({ name, reason }: { name: string; reason?: string }) {
  return (
    <div className={`${ROW_CLASS} pl-7 bg-destructive/10`}>
      <AlertTriangle className="size-3.5 shrink-0 text-destructive" aria-hidden />
      <span className="font-mono text-xs text-muted-foreground line-through decoration-destructive/40">
        {name}
      </span>
      <span className="text-[11px] text-destructive">{reason}</span>
    </div>
  )
}

export interface InputConfigDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  skillId: string
  /** Node label for the title ("Input — event_timeline" / "Input — GRAPH.md io.inputs"). */
  targetLabel: string
  /**
   * Reconciled blackboard context rows (matched/available/missing); empty for
   * the Input pseudo-node / GRAPH.md. Missing rows are shown at the top.
   */
  blackboard: ReconciledFieldRow[]
  /** Existing source:'file' declarations of the target document. */
  declaredFiles: FileFieldDecl[]
  onSave: (checks: {
    blackboard: Array<{ name: string; type: string | null; checked: boolean }>
    files: FileFieldDecl[]
  }) => Promise<string | null>
}

export function InputConfigDialog({
  open,
  onOpenChange,
  skillId,
  targetLabel,
  blackboard,
  declaredFiles,
  onSave,
}: InputConfigDialogProps) {
  const [blackboardChecks, setBlackboardChecks] = useState<Record<string, boolean>>({})
  const initialGroup = useMemo(() => groupFromDeclarations(declaredFiles), [declaredFiles])
  const [groups, setGroups] = useState<FileGroup[] | null>(null)
  const [addPath, setAddPath] = useState("")
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const effectiveGroups = groups ?? (initialGroup ? [initialGroup] : [])

  const isChecked = (row: ReconciledFieldRow) => blackboardChecks[row.name] ?? row.checked

  const handleAddFile = async () => {
    const path = addPath.trim()
    if (!path) {
      setError("Enter a file or folder path to import")
      return
    }
    setBusy(true)
    setError(null)
    try {
      const result = await importIoIntoWorkspace(skillId, path)
      const candidates = candidatesFromScanEntries(result.entries)
      const label = path.replace(/[\\/]+$/, "").split(/[\\/]/).pop() ?? path
      setGroups([...effectiveGroups, { label, pathHint: path, candidates }])
      setAddPath("")
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  const toggleCandidate = (groupIndex: number, candidateIndex: number, next: boolean) => {
    setGroups(
      effectiveGroups.map((group, gi) =>
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

  const removeGroup = (groupIndex: number) => {
    setGroups(effectiveGroups.filter((_, gi) => gi !== groupIndex))
  }

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
        .map((row) => ({
          name: row.name,
          type: row.type,
          checked: isChecked(row),
        })),
      files,
    })
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
          <DialogTitle>Input — {targetLabel}</DialogTitle>
          <DialogDescription>
            Blackboard fields are the primary input; imported files only add fields.
          </DialogDescription>
        </DialogHeader>
        <div className="max-h-[55vh] overflow-y-auto rounded-md border border-border">
          {blackboard.length > 0 ? (
            <>
              <div className={GROUP_HEAD_CLASS}>
                <span className="text-xs font-medium text-foreground">Blackboard context</span>
                <span className={META_CLASS}>fields on the blackboard when this node runs</span>
              </div>
              {blackboard.map((row) =>
                row.state === "missing" ? (
                  <MissingFieldRow key={row.name} name={row.name} reason={row.reason} />
                ) : (
                  <FieldCheckRow
                    key={row.name}
                    checked={isChecked(row)}
                    onCheckedChange={(next) =>
                      setBlackboardChecks((prev) => ({ ...prev, [row.name]: next }))
                    }
                    name={row.name}
                    meta={`${row.type ?? "any"} · from ${row.from}`}
                    indent
                    highlighted={row.state === "matched" && isChecked(row)}
                  />
                ),
              )}
            </>
          ) : null}
          {effectiveGroups.map((group, groupIndex) => (
            <div key={`${group.label}-${groupIndex}`}>
              <div className={GROUP_HEAD_CLASS}>
                <FileText className="size-3.5 shrink-0 self-center text-muted-foreground" aria-hidden />
                <span className="font-mono text-xs text-foreground">{group.label}</span>
                <span className={PATH_CLASS}>{group.pathHint}</span>
                <button
                  type="button"
                  onClick={() => removeGroup(groupIndex)}
                  aria-label={`Remove file group ${group.label}`}
                  className="text-muted-foreground transition-colors hover:text-destructive"
                >
                  <Trash2 className="size-3.5" />
                </button>
              </div>
              {group.candidates.map((candidate, candidateIndex) => (
                <FieldCheckRow
                  key={`${candidate.field}-${candidateIndex}`}
                  checked={candidate.checked}
                  onCheckedChange={(next) => toggleCandidate(groupIndex, candidateIndex, next)}
                  name={candidate.field}
                  meta={
                    candidate.dir
                      ? `batch ×${candidate.numbers?.length ?? "?"} · numbers kept`
                      : (candidate.type ?? "any") + " · source: file"
                  }
                  indent
                />
              ))}
            </div>
          ))}
          {blackboard.length === 0 && effectiveGroups.length === 0 ? (
            <p className="px-3 py-4 text-xs text-muted-foreground">
              No fields yet — import a file or folder below.
            </p>
          ) : null}
        </div>
        <div className="flex items-center gap-2">
          <Input
            value={addPath}
            onChange={(event) => setAddPath(event.target.value)}
            placeholder="File or folder path to import"
            aria-label="Path to import"
            className="h-8 flex-1 text-xs"
          />
          <Button
            type="button"
            size="sm"
            variant="secondary"
            onClick={() => void handleAddFile()}
            disabled={busy}
            aria-label="Add file"
          >
            {busy ? <Loader2 className="size-3.5 animate-spin" aria-hidden /> : <Plus className="size-3.5" aria-hidden />}
            Add file
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

export interface OutputConfigDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  /**
   * Reconciled field universe (matched/available/missing) — identical under
   * every artifact card. Missing = a required io.outputs field no phase
   * produces (shown once at the dialog top); matched = a declared io.outputs
   * member (highlighted in each card).
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
    const fields = next
      ? [...row.fields, field]
      : row.fields.filter((name) => name !== field)
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
                <MissingFieldRow key={row.name} name={row.name} reason={row.reason} />
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
              {carryableFields.map((field) => (
                <FieldCheckRow
                  key={field.name}
                  checked={row.fields.includes(field.name)}
                  onCheckedChange={(next) => toggleField(index, field.name, next)}
                  name={field.name}
                  meta={`${field.type ?? "any"} · from ${field.from}`}
                  indent
                  highlighted={field.state === "matched"}
                />
              ))}
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
            onClick={() =>
              setRows([...effectiveRows, { stem: "", mode: "single", fields: [] }])
            }
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
