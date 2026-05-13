import {
  AlertCircle,
  Check,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  ChevronsUpDown,
  FileText,
  Folder,
  Upload,
  type LucideIcon,
} from "lucide-react"
import { useMemo, useState, type DragEvent, type ReactNode } from "react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Command, CommandEmpty, CommandGroup, CommandInput, CommandItem, CommandList } from "@/components/ui/command"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Separator } from "@/components/ui/separator"
import { Slider } from "@/components/ui/slider"
import { Textarea } from "@/components/ui/textarea"
import type { SkillDetail } from "@/api/types"
import { HistoryPanel } from "@/components/history/HistoryPanel"
import { inferJsonSchemaFromText } from "@/lib/schema-infer"
import { cn } from "@/lib/utils"
import type { SkillGraphNodeData } from "@/components/GraphCanvas"
import type { PanelKind } from "./Toolbar"

export interface FileMeta {
  path: string
  language: string
  content: string
}

interface PanelsProps {
  activePanel: PanelKind
  skillId: string | null
  skillDetail?: SkillDetail
  selectedNode: { id: string; data: SkillGraphNodeData } | null
  onFileOpen: (file: FileMeta) => void
}

interface AssetsPanelProps {
  skillDetail?: SkillDetail
  selectedNode: { id: string; data: SkillGraphNodeData } | null
  onFileOpen: (file: FileMeta) => void
}

interface InputPanelProps {
  skillDetail?: SkillDetail
  onFileOpen: (file: FileMeta) => void
}

function PanelHeader({ title, extra }: { title: string; extra?: ReactNode }) {
  return (
    <div className="flex h-10 shrink-0 items-center px-3">
      <div className="flex items-center gap-2">
        <span className="text-xs font-medium text-foreground">{title}</span>
        {extra}
      </div>
    </div>
  )
}

function SectionHeading({ label }: { label: string }) {
  return (
    <div className="px-2 pb-0.5 pt-1 text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
      {label}
    </div>
  )
}

function FileRow({
  file,
  icon: Icon = FileText,
  onOpen,
  indent = false,
}: {
  file: FileMeta
  icon?: LucideIcon
  onOpen: (file: FileMeta) => void
  indent?: boolean
}) {
  const filename = file.path.split("/").pop() ?? file.path

  return (
    <button
      type="button"
      onClick={() => onOpen(file)}
      className={cn(
        "flex w-full cursor-pointer items-center gap-2 rounded-md px-2 py-1.5 text-left text-xs text-muted-foreground transition-colors hover:bg-accent hover:text-foreground",
        indent && "ml-4 border-l border-border pl-3",
      )}
    >
      <Icon className="size-4" strokeWidth={1.5} />
      <span className="truncate">{filename}</span>
    </button>
  )
}

function FolderRow({
  name,
  children,
  defaultExpanded = false,
}: {
  name: string
  children: ReactNode
  defaultExpanded?: boolean
}) {
  const [expanded, setExpanded] = useState(defaultExpanded)

  return (
    <div>
      <button
        type="button"
        onClick={() => setExpanded((value) => !value)}
        className="flex w-full cursor-pointer items-center gap-2 rounded-md px-2 py-1.5 text-left text-xs text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
      >
        {expanded ? <ChevronDown className="size-3.5" /> : <ChevronRight className="size-3.5" />}
        <Folder className="size-4" strokeWidth={1.5} />
        <span>{name}</span>
      </button>
      {expanded ? <div>{children}</div> : null}
    </div>
  )
}

function manifestFiles(skillDetail?: SkillDetail, selectedNode?: { id: string; data: SkillGraphNodeData } | null): FileMeta[] {
  const manifest = skillDetail?.manifest
  const files: FileMeta[] = [
    {
      path: "SKILL.md",
      language: "markdown",
      content: manifest
        ? `# ${manifest.name}\n\n${manifest.description ?? "No description."}\n\nType: ${manifest.type}\n`
        : "# Skill\n\nLoading skill metadata...\n",
    },
    {
      path: "skill-manifest.json",
      language: "json",
      content: JSON.stringify(manifest ?? {}, null, 2),
    },
  ]

  if (selectedNode) {
    files.push({
      path: `nodes/${selectedNode.id}.md`,
      language: "markdown",
      content: `# ${selectedNode.data.label}\n\nMode: ${selectedNode.data.mode}\nStatus: ${selectedNode.data.status}\n`,
    })
  }

  return files
}

function inputFiles(skillDetail?: SkillDetail): FileMeta[] {
  const manifest = skillDetail?.manifest
  const io = manifest?.type === "graph" ? manifest.io : null

  return [
    {
      path: "input/schema.json",
      language: "json",
      content: JSON.stringify({ inputs: io?.inputs ?? [], outputs: io?.outputs ?? [] }, null, 2),
    },
    {
      path: "input/sample.json",
      language: "json",
      content: JSON.stringify(Object.fromEntries((io?.inputs ?? []).map((input) => [input.name, ""])), null, 2),
    },
  ]
}

export function AssetsPanel({ skillDetail, selectedNode, onFileOpen }: AssetsPanelProps) {
  const files = manifestFiles(skillDetail, selectedNode)

  return (
    <div className="flex h-full flex-col bg-background">
      <PanelHeader title="Assets" />

      <ScrollArea className="flex-1">
        <div className="space-y-3 px-2 py-2 text-xs">
          <SectionHeading label="Skill Files" />
          <FileRow file={files[0]} onOpen={onFileOpen} />
          <FileRow file={files[1]} onOpen={onFileOpen} />
          {files[2] ? (
            <FolderRow name="nodes" defaultExpanded>
              <FileRow file={files[2]} onOpen={onFileOpen} indent />
            </FolderRow>
          ) : null}
        </div>
      </ScrollArea>
    </div>
  )
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

  return (
    <div className="flex h-full flex-col bg-background">
      <PanelHeader title="Input" />

      <ScrollArea className="flex-1">
        <div className="space-y-3 px-2 py-2 text-xs">
          <SectionHeading label="Input Files" />
          <FileRow file={files[1]} onOpen={onFileOpen} />

          <SectionHeading label="Schema" />
          <FileRow file={files[0]} onOpen={onFileOpen} />
          <SchemaInferPanel initialJson={sample} />
        </div>
      </ScrollArea>
    </div>
  )
}

export function TimelinePanel() {
  const traces = [
    { id: 1, name: "Latest run", status: "success", duration: "2.3s", time: "2m ago" },
    { id: 2, name: "Previous run", status: "error", duration: "0.8s", time: "5m ago" },
  ]

  return (
    <div className="flex h-full flex-col bg-background">
      <PanelHeader title="Timeline" />

      <ScrollArea className="flex-1">
        <div className="px-2 py-2">
          {traces.map((trace) => (
            <div
              key={trace.id}
              className="group cursor-pointer rounded-md px-2 py-2 transition-colors hover:bg-accent"
            >
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  {trace.status === "success" ? (
                    <CheckCircle2 className="size-4 text-foreground" />
                  ) : (
                    <AlertCircle className="size-4 text-destructive" />
                  )}
                  <span className="text-xs text-muted-foreground group-hover:text-foreground">{trace.name}</span>
                </div>
                <span className="text-xs text-muted-foreground">{trace.time}</span>
              </div>
              <div className="mt-0.5 flex items-center gap-2 pl-6 text-xs text-muted-foreground">
                <span>{trace.duration}</span>
              </div>
            </div>
          ))}
        </div>
      </ScrollArea>
    </div>
  )
}

export function PropertiesPanel({ skillDetail, selectedNode }: Pick<PanelsProps, "skillDetail" | "selectedNode">) {
  const manifest = skillDetail?.manifest
  const selectedType = selectedNode?.data.mode ?? manifest?.type ?? "Skill"
  const [temperature, setTemperature] = useState([0.7])
  const [modelOpen, setModelOpen] = useState(false)
  const [modelValue, setModelValue] = useState(selectedNode?.data.role ?? "default")
  const models = [
    { value: "default", label: "Default model" },
    { value: "gpt-4o-mini", label: "GPT-4o Mini" },
    { value: "gpt-4o", label: "GPT-4o" },
    { value: "claude-3.5", label: "Claude 3.5 Sonnet" },
  ]

  return (
    <div className="flex h-full flex-col bg-background">
      <PanelHeader title="Properties" />

      <ScrollArea className="flex-1">
        <div className="space-y-5 p-4">
          <div className="space-y-2">
            <Label className="text-xs text-muted-foreground">Node ID</Label>
            <Input
              readOnly
              value={selectedNode?.id ?? manifest?.name ?? "No node selected"}
              className="h-7 bg-muted text-xs"
            />
          </div>

          <div className="space-y-2">
            <Label className="text-xs text-muted-foreground">Type</Label>
            <div className="flex items-center gap-2">
              <Badge variant="secondary">{selectedType}</Badge>
            </div>
          </div>

          <Separator />

          <div className="space-y-2">
            <Label className="text-xs text-muted-foreground">Model</Label>
            <Popover open={modelOpen} onOpenChange={setModelOpen}>
              <PopoverTrigger asChild>
                <Button
                  variant="outline"
                  role="combobox"
                  aria-expanded={modelOpen}
                  className="h-7 w-full justify-between text-xs font-normal"
                >
                  {models.find((model) => model.value === modelValue)?.label ?? selectedNode?.data.role ?? "Select model..."}
                  <ChevronsUpDown className="ml-2 size-3.5 shrink-0 opacity-50" />
                </Button>
              </PopoverTrigger>
              <PopoverContent className="w-[--radix-popover-trigger-width] p-0" align="start">
                <Command>
                  <CommandInput placeholder="Search model..." className="h-8 text-xs" />
                  <CommandList>
                    <CommandEmpty>No model found.</CommandEmpty>
                    <CommandGroup>
                      {models.map((model) => (
                        <CommandItem
                          key={model.value}
                          value={model.value}
                          onSelect={(currentValue) => {
                            setModelValue(currentValue === modelValue ? "" : currentValue)
                            setModelOpen(false)
                          }}
                          className="text-xs"
                        >
                          <Check className={cn("mr-2 size-3.5", modelValue === model.value ? "opacity-100" : "opacity-0")} />
                          {model.label}
                        </CommandItem>
                      ))}
                    </CommandGroup>
                  </CommandList>
                </Command>
              </PopoverContent>
            </Popover>
          </div>

          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <Label className="text-xs text-muted-foreground">Temperature</Label>
              <span className="text-xs text-foreground">{temperature[0]}</span>
            </div>
            <Slider
              value={temperature}
              onValueChange={setTemperature}
              min={0}
              max={1}
              step={0.1}
              className="w-full"
            />
          </div>

          <Separator />

          <div className="space-y-2">
            <Label className="text-xs text-muted-foreground">System Prompt</Label>
            <Textarea
              readOnly
              value={selectedNode ? `${selectedNode.data.label}\n\nDepends on: ${selectedNode.data.dependsOn.join(", ") || "None"}` : "Select a node on the canvas."}
              className="min-h-[100px] resize-none text-xs"
            />
          </div>
        </div>
      </ScrollArea>
    </div>
  )
}

export function Panels({ activePanel, skillId, skillDetail, selectedNode, onFileOpen }: PanelsProps) {
  if (!skillId) {
    return (
      <div className="flex h-full w-full flex-col bg-sidebar">
        <PanelHeader title="Workspace" />
        <div className="p-4 text-xs text-muted-foreground">Open a skill to populate this panel.</div>
      </div>
    )
  }

  if (activePanel === "assets") {
    return <AssetsPanel skillDetail={skillDetail} selectedNode={selectedNode} onFileOpen={onFileOpen} />
  }
  if (activePanel === "input") {
    return <InputPanel skillDetail={skillDetail} onFileOpen={onFileOpen} />
  }
  if (activePanel === "timeline") {
    return <TimelinePanel />
  }
  if (activePanel === "local-history") {
    return <HistoryPanel skillId={skillId} />
  }
  return <PropertiesPanel skillDetail={skillDetail} selectedNode={selectedNode} />
}
