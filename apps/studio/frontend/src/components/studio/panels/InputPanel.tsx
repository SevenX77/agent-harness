import { useMemo, useState, type DragEvent } from "react"
import { Save, Upload } from "lucide-react"
import { writeSkillFile } from "@/api/client"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Textarea } from "@/components/ui/textarea"
import type { SkillDetail } from "@/api/types"
import { applyInputSchemaToGraph, inferJsonSchemaFromText } from "@/lib/schema-infer"
import { errorMessage } from "@/utils/errors"
import type { FileMeta } from "../file-types"
import { resolveWorkspaceIdentity } from "../workspace-identity"
import { FileRow } from "./_shared/FileRow"
import { PanelHeader } from "./_shared/PanelHeader"
import { SectionHeading } from "./_shared/SectionHeading"
import { GoldenSection } from "./GoldenSection"
import { inputFiles } from "./panel-files"
import { TestInputsSection } from "./TestInputsSection"

interface InputPanelProps {
  skillId: string
  skillDetail?: SkillDetail
  onFileOpen: (file: FileMeta) => void
  selectedTestInputId?: string | null
  onSelectTestInput?: (id: string | null) => void
}

interface SchemaInferPanelProps {
  initialJson: string
  skillId: string
  graphMd?: string
  onSaved?: () => void
}

function SchemaInferPanel({ initialJson, skillId, graphMd, onSaved }: SchemaInferPanelProps) {
  const [draft, setDraft] = useState(initialJson)
  const [saving, setSaving] = useState(false)
  const [saveError, setSaveError] = useState<string | null>(null)
  const [saved, setSaved] = useState(false)
  const result = useMemo(() => {
    try {
      return { schema: inferJsonSchemaFromText(draft), error: null as string | null }
    } catch (error) {
      return { schema: null, error: error instanceof Error ? error.message : "Invalid JSON" }
    }
  }, [draft])

  // F2: persist the inferred schema into GRAPH.md's io.inputs (the engine's
  // input contract). The design says inference can be saved; GRAPH.md is git-
  // tracked so this is reversible.
  const handleSave = async () => {
    if (!result.schema || !graphMd) {
      return
    }
    setSaving(true)
    setSaveError(null)
    setSaved(false)
    try {
      const next = applyInputSchemaToGraph(graphMd, result.schema)
      // In the desktop app skill files are written natively by workspace root,
      // not skill id — pass `workspaceRoot ?? skillId` like the Monaco editor
      // (LazyMonacoPanel) so the native write targets the right path. In the
      // browser this resolves to skillId and writeSkillFile takes the HTTP path.
      const target = resolveWorkspaceIdentity(skillId).workspaceRoot ?? skillId
      await writeSkillFile(target, "GRAPH.md", next)
      setSaved(true)
      onSaved?.()
    } catch (error) {
      setSaveError(errorMessage(error))
    } finally {
      setSaving(false)
    }
  }

  const handleDrop = async (event: DragEvent<HTMLTextAreaElement>) => {
    event.preventDefault()
    const file = event.dataTransfer.files.item(0)
    if (file) {
      setDraft(await file.text())
      return
    }

    const text = event.dataTransfer.getData("text/plain")
    if (text) {
      setDraft(text)
    }
  }

  return (
    <section className="space-y-2">
      <div className="flex items-center gap-2 px-2 text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
        <Upload className="size-3.5" />
        Infer input schema
      </div>
      <div className="space-y-3 rounded-md border border-border bg-background p-3">
        <Textarea
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          onDragOver={(event) => event.preventDefault()}
          onDrop={handleDrop}
          className="h-28 resize-none bg-card font-mono text-xs"
          spellCheck={false}
          aria-label="JSON input for schema inference"
        />
        {result.error ? (
          <div className="rounded-md border border-destructive/30 bg-destructive/10 px-2 py-1 text-xs text-destructive">
            {result.error}
          </div>
        ) : (
          <pre className="max-h-52 overflow-auto rounded-md border border-border bg-muted/40 p-2 text-xs text-foreground">
            {JSON.stringify(result.schema, null, 2)}
          </pre>
        )}
        <button
          type="button"
          onClick={() => void handleSave()}
          disabled={saving || !result.schema || !graphMd}
          aria-label="Save inferred schema as input contract"
          className="flex items-center gap-1 rounded-md bg-foreground px-2 py-1 text-xs font-medium text-background transition-opacity hover:opacity-80 disabled:opacity-50"
        >
          <Save className="size-3.5" />
          {saving ? "Saving…" : "Save as input schema"}
        </button>
        {saveError ? (
          <div className="rounded-md border border-destructive/30 bg-destructive/10 px-2 py-1 text-xs text-destructive">
            {saveError}
          </div>
        ) : null}
        {saved && !saveError ? (
          <div className="px-1 text-[11px] text-muted-foreground">
            Saved to GRAPH.md io.inputs.
          </div>
        ) : null}
      </div>
    </section>
  )
}

export function InputPanel({
  skillId,
  skillDetail,
  onFileOpen,
  selectedTestInputId = null,
  onSelectTestInput,
}: InputPanelProps) {
  const files = inputFiles(skillDetail)
  const sample = files.find((file) => file.path === "input/sample.json")?.content ?? "{}"

  return (
    <div className="flex h-full flex-col bg-background">
      <PanelHeader title="I/O" />

      <ScrollArea className="flex-1">
        <div className="space-y-3 px-2 py-2 text-xs">
          <TestInputsSection
            skillId={skillId}
            selectedId={selectedTestInputId}
            onSelect={onSelectTestInput}
          />

          <GoldenSection skillId={skillId} />

          <SectionHeading label="Input Files" />
          <FileRow file={files[1]} onOpen={onFileOpen} />

          <SectionHeading label="Schema" />
          <FileRow file={files[0]} onOpen={onFileOpen} />
          <SchemaInferPanel
            initialJson={sample}
            skillId={skillId}
            graphMd={skillDetail?.files?.["GRAPH.md"]}
          />
        </div>
      </ScrollArea>
    </div>
  )
}
