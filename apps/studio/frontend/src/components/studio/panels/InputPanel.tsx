import { useState, type ComponentProps } from "react"
import { AlertTriangle, ChevronDown, ChevronRight, FileText, Files, Settings2 } from "lucide-react"
import type { LintError, SkillDetail } from "@/api/types"
import { Button } from "@/components/ui/button"
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible"
import { Field, FieldDescription, FieldGroup, FieldLabel, FieldSet } from "@/components/ui/field"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"
import { sha256Hex } from "@/lib/hash"
import {
  applyGraphArtifacts,
  applyIoInputChecks,
  declaredInputFieldNames,
  fileFieldsOf,
  graphArtifactsOf,
  reconcileInputFields,
  reconcileOutputFields,
  type ArtifactRow,
  type FileFieldDecl,
  type IoInputChecks,
} from "@/lib/io-config"
import { ioSchemaOf, parseFrontmatter, schemaObject } from "@/lib/io-declarations"
import { errorMessage } from "@/utils/errors"
import { lintErrorsForBoundary } from "../field-compile-errors"
import type { FileOpenInput } from "../file-types"
import { PanelHeader } from "./_shared/PanelHeader"
import { PanelBody, PanelFieldRow } from "./_shared/PanelSection"
import { InputConfigInline, OutputConfigDialog } from "./IoConfigDialog"
import {
  ioPanelScope,
  resolveIoEditTarget,
  resolveIoNodeRole,
  type IoBoundarySelection,
  type IoNodeRole,
  type SelectedNode,
} from "./io-target"
import { TestInputsSection } from "./TestInputsSection"

type SaveIoFile = (payload: { path: string; content: string; expectedHash: string }) => Promise<void> | void

interface InputPanelProps {
  skillId: string
  workspaceRoot?: string | null
  skillDetail?: SkillDetail
  selectedNode?: SelectedNode
  /** Which boundary pseudo-node is selected, so the panel scopes by role. */
  ioBoundary?: IoBoundarySelection
  lintErrors?: LintError[] | null
  // F4: which saved test input feeds Predict/Run (wired through Workspace).
  selectedTestInputId?: string | null
  onSelectTestInput?: (id: string | null) => void
  onFileOpen?: (fileOrPath: FileOpenInput) => void
  // Writes for the config declarations (same optimistic-hash contract
  // PropertiesPanel uses).
  onPhaseFileSave?: SaveIoFile
}

type JsonSchema = Record<string, unknown>

interface IoDocumentView {
  relPath: string
  /** Raw md content of the resolved io document (for edit write-backs). */
  content: string
  inputSchema: JsonSchema | null
  outputSchema: JsonSchema | null
  isGraphLevel: boolean
  label: string
}

const EMPTY_SCHEMA: JsonSchema = {}
const YAML_FIELD_LABEL_CLASS = "!text-sm !font-semibold !leading-5 !text-foreground/70"
const YAML_ICON_BUTTON_CLASS =
  "size-7 rounded-md bg-secondary/70 text-muted-foreground hover:bg-secondary hover:text-foreground"
const EXAMPLE_CODE_CLASS =
  "max-h-72 overflow-auto rounded-md bg-muted/30 px-2 py-2 font-mono text-xs leading-relaxed text-foreground"

/** Panel header title per role — the boundary pseudo-nodes read as Input / Output. */
function headerTitleFor(role: IoNodeRole, phaseLabel: string): string {
  switch (role) {
    case "input-boundary":
      return "Input"
    case "output-boundary":
      return "Output"
    case "phase":
      return phaseLabel
    default:
      return "I/O"
  }
}

function isJsonSerializablePrimitive(value: unknown): value is string | number | boolean | null {
  return value === null || typeof value === "string" || typeof value === "number" || typeof value === "boolean"
}

function jsonExampleFromSchema(schema: unknown): unknown {
  if (!schema || typeof schema !== "object" || Array.isArray(schema)) {
    return null
  }
  const objectSchema = schema as JsonSchema
  const explicitExample = Array.isArray(objectSchema.examples) ? objectSchema.examples[0] : undefined
  if (isJsonSerializablePrimitive(objectSchema.default)) {
    return objectSchema.default
  }
  if (isJsonSerializablePrimitive(objectSchema.const)) {
    return objectSchema.const
  }
  if (isJsonSerializablePrimitive(explicitExample)) {
    return explicitExample
  }
  if (Array.isArray(objectSchema.enum) && isJsonSerializablePrimitive(objectSchema.enum[0])) {
    return objectSchema.enum[0]
  }

  const schemaType = Array.isArray(objectSchema.type)
    ? objectSchema.type.find((candidate) => candidate !== "null")
    : objectSchema.type

  if (schemaType === "object" || schemaObject(objectSchema.properties)) {
    const properties = schemaObject(objectSchema.properties) ?? EMPTY_SCHEMA
    return Object.fromEntries(
      Object.entries(properties).map(([name, propertySchema]) => [name, jsonExampleFromSchema(propertySchema)]),
    )
  }
  if (schemaType === "array") {
    return [jsonExampleFromSchema(objectSchema.items)]
  }
  if (schemaType === "integer" || schemaType === "number") {
    return 0
  }
  if (schemaType === "boolean") {
    return false
  }
  if (schemaType === "string") {
    return ""
  }
  if (Array.isArray(objectSchema.oneOf) && objectSchema.oneOf.length > 0) {
    return jsonExampleFromSchema(objectSchema.oneOf[0])
  }
  if (Array.isArray(objectSchema.anyOf) && objectSchema.anyOf.length > 0) {
    return jsonExampleFromSchema(objectSchema.anyOf[0])
  }
  if (Array.isArray(objectSchema.allOf) && objectSchema.allOf.length > 0) {
    return jsonExampleFromSchema(objectSchema.allOf[0])
  }
  return null
}

function prettyJson(value: unknown): string {
  return JSON.stringify(value, null, 2)
}

function buildIoDocumentView(skillDetail: SkillDetail | undefined, selectedNode: SelectedNode = null): IoDocumentView {
  const target = resolveIoEditTarget(selectedNode, skillDetail)
  const content = target.content ?? ""
  const frontmatter = parseFrontmatter(content)
  return {
    relPath: target.relPath,
    content,
    inputSchema: ioSchemaOf(frontmatter, "inputs"),
    outputSchema: ioSchemaOf(frontmatter, "outputs"),
    isGraphLevel: target.isGraphLevel,
    label: target.label,
  }
}

/**
 * Shared submit path for config write-backs: run the pure mutation against
 * the CURRENT document content, save with the previous content's hash
 * (optimistic concurrency, same contract PropertiesPanel uses), and return
 * the surfaced error message (null = saved).
 */
async function submitIoDocumentEdit({
  relPath,
  content,
  mutate,
  save,
}: {
  relPath: string
  content: string
  mutate: (content: string) => string
  save?: SaveIoFile
}): Promise<string | null> {
  let next: string
  try {
    next = mutate(content)
  } catch (err) {
    return errorMessage(err)
  }
  if (!save) {
    return "Saving is unavailable in this context"
  }
  try {
    await save({ path: relPath, content: next, expectedHash: await sha256Hex(content) })
    return null
  } catch (err) {
    return errorMessage(err)
  }
}

/** Per-item count hint: the batch numbers recorded on the input side, if any. */
function perItemCountOf(declarations: FileFieldDecl[]): number | null {
  for (const decl of declarations) {
    if (decl.numbers && decl.numbers.length > 0) {
      return decl.numbers.length
    }
  }
  return null
}

function YamlFieldLabel({ className, ...props }: ComponentProps<typeof FieldLabel>) {
  return (
    <FieldLabel
      className={`${YAML_FIELD_LABEL_CLASS}${className ? ` ${className}` : ""}`}
      {...props}
    />
  )
}

/** The read-only instance preview for one io side (input / output). */
function ExampleField({
  title,
  schema,
  relPath,
  onEdit,
}: {
  title: string
  schema: JsonSchema | null
  relPath: string
  onEdit?: () => void
}) {
  const example = schema ? jsonExampleFromSchema(schema) : null
  return (
    <PanelFieldRow>
      <Field>
        <YamlFieldLabel>{title.toLowerCase()}</YamlFieldLabel>
        <div className="flex items-center justify-between gap-2">
          <Tooltip>
            <TooltipTrigger asChild>
              <FieldDescription className="min-w-0 flex-1 truncate font-mono">
                {relPath}
              </FieldDescription>
            </TooltipTrigger>
            <TooltipContent>{relPath}</TooltipContent>
          </Tooltip>
          <Button
            type="button"
            size="icon"
            variant="secondary"
            className={YAML_ICON_BUTTON_CLASS}
            onClick={onEdit}
            disabled={!onEdit}
            aria-label={`Edit ${title.toLowerCase()} schema in ${relPath}`}
          >
            <FileText className="size-3.5" aria-hidden />
          </Button>
        </div>
        {schema ? (
          <pre className={EXAMPLE_CODE_CLASS}>{prettyJson(example)}</pre>
        ) : (
          <FieldDescription>No {title.toLowerCase()} example can be generated from this md file.</FieldDescription>
        )}
      </Field>
    </PanelFieldRow>
  )
}

/** Panel list row for a configured output artifact (stem + mode). */
function ArtifactListRow({ row, perItemCount }: { row: ArtifactRow; perItemCount: number | null }) {
  return (
    <div className="flex items-baseline gap-2 rounded-md border border-border px-2 py-1">
      {row.mode === "per-item" ? (
        <Files className="size-3 shrink-0 self-center text-muted-foreground" aria-hidden />
      ) : (
        <FileText className="size-3 shrink-0 self-center text-muted-foreground" aria-hidden />
      )}
      <span className="min-w-0 flex-1 truncate font-mono text-xs text-foreground">{row.stem}</span>
      <span className="shrink-0 text-[11px] text-muted-foreground">
        {row.mode === "per-item" ? `per-item${perItemCount ? ` ×${perItemCount}` : ""}` : "single"}
      </span>
    </div>
  )
}

function boundaryDiagnosticLabel(error: LintError): string {
  const parts = [error.field_path, error.error_code].filter((part): part is string => Boolean(part))
  return parts.length > 0 ? `${parts.join(" - ")} - ${error.message}` : error.message
}

function BoundaryDiagnostics({
  title,
  errors,
}: {
  title: string
  errors: readonly LintError[]
}) {
  if (errors.length === 0) {
    return null
  }
  return (
    <PanelFieldRow>
      <Field>
        <div className="flex items-center gap-1.5 text-destructive">
          <AlertTriangle className="size-3.5 shrink-0" aria-hidden />
          <YamlFieldLabel className="!text-destructive">{title}</YamlFieldLabel>
        </div>
        <div className="space-y-1">
          {errors.map((error, index) => (
            <FieldDescription
              key={`${error.file ?? "boundary"}:${error.field_path ?? "field"}:${index}`}
              className="rounded-md border border-destructive/35 bg-destructive/10 px-2 py-1 font-mono text-[11px] text-destructive"
            >
              {boundaryDiagnosticLabel(error)}
            </FieldDescription>
          ))}
        </div>
      </Field>
    </PanelFieldRow>
  )
}

export function InputPanel({
  skillId,
  workspaceRoot = null,
  skillDetail,
  selectedNode = null,
  ioBoundary = null,
  lintErrors = null,
  selectedTestInputId = null,
  onSelectTestInput,
  onFileOpen,
  onPhaseFileSave,
}: InputPanelProps) {
  const role = resolveIoNodeRole(selectedNode, ioBoundary)
  const scope = ioPanelScope(role)
  const view = buildIoDocumentView(skillDetail, selectedNode)
  const openSource = () => onFileOpen?.(view.relPath)
  const editSource = onFileOpen ? openSource : undefined
  const [inputConfigOpen, setInputConfigOpen] = useState(false)
  const [outputConfigOpen, setOutputConfigOpen] = useState(false)
  const boundaryDiagnostics = role === "input-boundary"
    ? lintErrorsForBoundary(lintErrors, "input")
    : role === "output-boundary"
      ? lintErrorsForBoundary(lintErrors, "output")
      : []

  // Reconciled input fields (matched/available/missing), nested. For an interior
  // node this reconciles io.inputs against the upstream blackboard; for the Input
  // boundary / GRAPH.md it flags declared graph inputs with no source.
  const blackboard = reconcileInputFields(skillDetail, view.isGraphLevel ? "" : selectedNode?.id ?? "")
  const declaredFiles = fileFieldsOf(view.content)
  const artifacts = graphArtifactsOf(skillDetail)
  const graphContent = skillDetail?.files?.["GRAPH.md"] ?? ""
  const perItemCount = perItemCountOf(fileFieldsOf(graphContent))

  const handleInputConfigSave = (checks: IoInputChecks) =>
    submitIoDocumentEdit({
      relPath: view.relPath,
      content: view.content,
      mutate: (content) => applyIoInputChecks(content, checks),
      save: onPhaseFileSave,
    })

  const handleArtifactsSave = (rows: ArtifactRow[]) =>
    submitIoDocumentEdit({
      relPath: "GRAPH.md",
      content: graphContent,
      mutate: (content) => applyGraphArtifacts(content, rows),
      save: onPhaseFileSave,
    })

  return (
    <div className="flex h-full flex-col bg-background">
      <PanelHeader title={headerTitleFor(role, view.label)} />
      <ScrollArea className="flex-1">
        <PanelBody>
          <FieldSet>
            <FieldGroup>
              {scope.showInput ? (
                <>
                  <BoundaryDiagnostics title="Input diagnostics" errors={boundaryDiagnostics} />
                  <ExampleField title="Input" schema={view.inputSchema} relPath={view.relPath} onEdit={editSource} />
                  <PanelFieldRow>
                    <Collapsible open={inputConfigOpen} onOpenChange={setInputConfigOpen}>
                      <CollapsibleTrigger asChild>
                        <Button
                          type="button"
                          size="sm"
                          variant="secondary"
                          className="h-7 gap-1 px-2 text-[11px]"
                          aria-label="Configure input"
                        >
                          {inputConfigOpen ? (
                            <ChevronDown className="size-3" aria-hidden />
                          ) : (
                            <ChevronRight className="size-3" aria-hidden />
                          )}
                          <Settings2 className="size-3" aria-hidden />
                          Configure input
                        </Button>
                      </CollapsibleTrigger>
                      <CollapsibleContent className="pt-2">
                        <InputConfigInline
                          skillId={skillId}
                          blackboard={blackboard}
                          declaredFiles={declaredFiles}
                          declaredInputNames={declaredInputFieldNames(view.content)}
                          onSave={handleInputConfigSave}
                          onFileOpen={onFileOpen}
                          isGraphInput={view.isGraphLevel}
                        />
                      </CollapsibleContent>
                    </Collapsible>
                  </PanelFieldRow>
                </>
              ) : null}

              {scope.showTestInputs ? (
                <PanelFieldRow>
                  <TestInputsSection
                    skillId={skillId}
                    workspaceRoot={workspaceRoot}
                    selectedId={selectedTestInputId}
                    onSelect={onSelectTestInput}
                    onFileOpen={onFileOpen}
                  />
                </PanelFieldRow>
              ) : null}

              {scope.showOutput ? (
                <>
                  <BoundaryDiagnostics title="Output diagnostics" errors={boundaryDiagnostics} />
                  <ExampleField title="Output" schema={view.outputSchema} relPath={view.relPath} onEdit={editSource} />
                </>
              ) : null}

              {scope.showArtifacts ? (
                <PanelFieldRow>
                  <Field>
                    <div className="flex items-center justify-between gap-2">
                      <YamlFieldLabel>output artifacts</YamlFieldLabel>
                      <Button
                        type="button"
                        size="sm"
                        variant="secondary"
                        className="h-6 gap-1 px-2 text-[11px]"
                        onClick={() => setOutputConfigOpen(true)}
                        aria-label="Configure output artifacts"
                      >
                        <Settings2 className="size-3" aria-hidden />
                        Configure
                      </Button>
                    </div>
                    {artifacts.length > 0 ? (
                      <div className="space-y-1">
                        {artifacts.map((row) => (
                          <ArtifactListRow key={row.stem} row={row} perItemCount={perItemCount} />
                        ))}
                      </div>
                    ) : (
                      <FieldDescription>No artifacts configured yet.</FieldDescription>
                    )}
                  </Field>
                </PanelFieldRow>
              ) : null}
            </FieldGroup>
          </FieldSet>
        </PanelBody>
      </ScrollArea>
      <OutputConfigDialog
        open={outputConfigOpen}
        onOpenChange={setOutputConfigOpen}
        universe={reconcileOutputFields(skillDetail)}
        artifacts={artifacts}
        perItemCount={perItemCount}
        onSave={handleArtifactsSave}
      />
    </div>
  )
}

export const __test__ = {
  buildIoDocumentView,
  jsonExampleFromSchema,
  parseFrontmatter,
  submitIoDocumentEdit,
  perItemCountOf,
}
