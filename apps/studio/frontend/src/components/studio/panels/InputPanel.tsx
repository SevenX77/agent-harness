import { useMemo, useState, type DragEvent } from "react"
import { Upload } from "lucide-react"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Textarea } from "@/components/ui/textarea"
import type { SkillDetail } from "@/api/types"
import { inferJsonSchemaFromText } from "@/lib/schema-infer"
import type { FileMeta } from "../file-types"
import { FileRow } from "./_shared/FileRow"
import { PanelHeader } from "./_shared/PanelHeader"
import { SectionHeading } from "./_shared/SectionHeading"
import { inputFiles } from "./panel-files"

interface InputPanelProps {
  skillDetail?: SkillDetail
  onFileOpen: (file: FileMeta) => void
}

function SchemaInferPanel({ initialJson }: { initialJson: string }) {
  const [draft, setDraft] = useState(initialJson)
  const result = useMemo(() => {
    try {
      return { schema: inferJsonSchemaFromText(draft), error: null as string | null }
    } catch (error) {
      return { schema: null, error: error instanceof Error ? error.message : "Invalid JSON" }
    }
  }, [draft])

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
      </div>
    </section>
  )
}

export function InputPanel({ skillDetail, onFileOpen }: InputPanelProps) {
  const files = inputFiles(skillDetail)
  const sample = files.find((file) => file.path === "input/sample.json")?.content ?? "{}"

  const schemaFile = files.find((file) => file.path === "input/schema.json")
  const inputDataFiles = files.filter((file) => file.path !== "input/schema.json")

  return (
    <div className="flex h-full flex-col bg-background">
      <PanelHeader title="Input" />

      <ScrollArea className="flex-1">
        <div className="space-y-3 px-2 py-2 text-xs">
          <SectionHeading label="Input Files" />
          {inputDataFiles.map((file) => (
            <FileRow key={file.path} file={file} onOpen={onFileOpen} />
          ))}
          {inputDataFiles.length === 0 && (
            <div className="text-muted-foreground p-2 text-center text-xs">No input files found.</div>
          )}

          {schemaFile && (
            <>
              <SectionHeading label="Schema" />
              <FileRow file={schemaFile} onOpen={onFileOpen} />
            </>
          )}
          <SchemaInferPanel initialJson={sample} />
        </div>
      </ScrollArea>
    </div>
  )
}
