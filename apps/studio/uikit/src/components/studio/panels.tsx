
import { ChevronRight, ChevronDown, FileText, Folder, AlertCircle, CheckCircle2, Check, ChevronsUpDown } from "lucide-react"
import { useState } from "react"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Separator } from "@/components/ui/separator"
import { Input } from "@/components/ui/input"
import { Textarea } from "@/components/ui/textarea"
import { Slider } from "@/components/ui/slider"
import { Label } from "@/components/ui/label"
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover"
import { Command, CommandEmpty, CommandGroup, CommandInput, CommandItem, CommandList } from "@/components/ui/command"
import { cn } from "@/lib/utils"

export type FileMeta = { path: string; content: string; language: string }

export const MOCK_FILES: Record<string, { content: string; language: string }> = {
  "SKILL.md": {
    language: "markdown",
    content: `# Text Generator Skill

A skill that generates text using LLM with configurable model and temperature.

## Inputs
- prompt: string
- system: string (optional)

## Outputs
- text: string
- usage: object
`,
  },
  "scripts/main.py": {
    language: "python",
    content: `import asyncio
from skill import Skill


class TextGenerator(Skill):
    def __init__(self):
        super().__init__()
        self.model = "gpt-4o-mini"

    async def run(self, input_data):
        response = await self.llm.generate(
            prompt=input_data.prompt,
            model=self.model,
            temperature=0.7,
        )
        return response.text
`,
  },
  "scripts/utils.py": {
    language: "python",
    content: `def normalize_prompt(text: str) -> str:
    return text.strip().lower()


def truncate(text: str, max_len: int = 4000) -> str:
    if len(text) <= max_len:
        return text
    return text[:max_len] + "..."
`,
  },
  "data/golden_baseline.json": {
    language: "json",
    content: `{
  "version": "1.0",
  "samples": [
    {
      "input": "Hello, world",
      "expected": "Greeting detected"
    }
  ]
}
`,
  },
  "config.yaml": {
    language: "yaml",
    content: `model: gpt-4o-mini
temperature: 0.7
max_tokens: 2000
system_prompt: "You are a helpful assistant."
`,
  },
  "artifacts/build.json": {
    language: "json",
    content: `{
  "build_id": "build_2026_05_11_001",
  "compiled_at": "2026-05-11T14:30:00Z",
  "nodes": 4,
  "edges": 4
}
`,
  },
  "artifacts/run_142_output.json": {
    language: "json",
    content: `{
  "run_id": 142,
  "status": "success",
  "duration_ms": 2300,
  "output": "Generated text response..."
}
`,
  },
  "input/sample_001.json": {
    language: "json",
    content: `{
  "prompt": "Summarize the key points",
  "system": "You are a helpful assistant.",
  "max_tokens": 500
}
`,
  },
  "input/sample_002.json": {
    language: "json",
    content: `{
  "prompt": "Translate to French",
  "system": "You are a translator.",
  "max_tokens": 200
}
`,
  },
  "input/schema.json": {
    language: "json",
    content: `{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "type": "object",
  "required": ["prompt"],
  "properties": {
    "prompt": { "type": "string" },
    "system": { "type": "string" },
    "max_tokens": { "type": "integer", "minimum": 1, "maximum": 4000 }
  }
}
`,
  },
}

interface AssetsPanelProps {
  onFileOpen: (file: FileMeta) => void
}

interface InputPanelProps {
  onFileOpen: (file: FileMeta) => void
}

function PanelHeader({ title, extra }: { title: string; extra?: React.ReactNode }) {
  return (
    <div className="h-10 flex items-center px-3 shrink-0">
      <div className="flex items-center gap-2">
        <span className="text-xs font-medium text-foreground">{title}</span>
        {extra}
      </div>
    </div>
  )
}

function SectionHeading({ label }: { label: string }) {
  return (
    <div className="px-2 pt-1 pb-0.5 text-[10px] uppercase tracking-wider text-muted-foreground font-medium">
      {label}
    </div>
  )
}

function FileRow({
  path,
  icon: Icon,
  onOpen,
  indent = false,
}: {
  path: string
  icon: typeof FileText
  onOpen: (file: FileMeta) => void
  indent?: boolean
}) {
  const meta = MOCK_FILES[path]
  const filename = path.split("/").pop() ?? path

  return (
    <div
      onClick={() => meta && onOpen({ path, ...meta })}
      className={cn(
        "flex items-center gap-2 px-2 py-1.5 rounded-md hover:bg-accent cursor-pointer text-muted-foreground hover:text-foreground transition-colors",
        indent && "ml-4 border-l border-border pl-3"
      )}
    >
      <Icon className="size-4" strokeWidth={1.5} />
      <span>{filename}</span>
    </div>
  )
}

function FolderRow({
  name,
  children,
  defaultExpanded = false,
}: {
  name: string
  children: React.ReactNode
  defaultExpanded?: boolean
}) {
  const [expanded, setExpanded] = useState(defaultExpanded)

  return (
    <div>
      <button
        onClick={() => setExpanded((v) => !v)}
        className="flex items-center gap-2 px-2 py-1.5 rounded-md hover:bg-accent cursor-pointer text-muted-foreground hover:text-foreground transition-colors w-full text-left"
      >
        {expanded ? <ChevronDown className="size-3.5" /> : <ChevronRight className="size-3.5" />}
        <Folder className="size-4" strokeWidth={1.5} />
        <span>{name}</span>
      </button>
      {expanded && <div>{children}</div>}
    </div>
  )
}

// Assets Panel
export function AssetsPanel({ onFileOpen }: AssetsPanelProps) {
  return (
    <div className="h-full bg-background flex flex-col">
      <PanelHeader title="Assets" />

      <ScrollArea className="flex-1">
        <div className="py-2 px-2 text-xs space-y-3">
          <SectionHeading label="Skill Files" />
          <FileRow path="SKILL.md" icon={FileText} onOpen={onFileOpen} />
          <FolderRow name="scripts" defaultExpanded>
            <FileRow path="scripts/main.py" icon={FileText} onOpen={onFileOpen} indent />
            <FileRow path="scripts/utils.py" icon={FileText} onOpen={onFileOpen} indent />
          </FolderRow>
          <FileRow path="config.yaml" icon={FileText} onOpen={onFileOpen} />

          <SectionHeading label="Artifacts" />
          <FolderRow name="artifacts" defaultExpanded>
            <FileRow path="artifacts/build.json" icon={FileText} onOpen={onFileOpen} indent />
            <FileRow path="artifacts/run_142_output.json" icon={FileText} onOpen={onFileOpen} indent />
          </FolderRow>
          <FolderRow name="data">
            <FileRow path="data/golden_baseline.json" icon={FileText} onOpen={onFileOpen} indent />
          </FolderRow>
        </div>
      </ScrollArea>
    </div>
  )
}

export function InputPanel({ onFileOpen }: InputPanelProps) {
  return (
    <div className="h-full bg-background flex flex-col">
      <PanelHeader title="Input" />

      <ScrollArea className="flex-1">
        <div className="py-2 px-2 text-xs space-y-3">
          <SectionHeading label="Input Files" />
          <FileRow path="input/sample_001.json" icon={FileText} onOpen={onFileOpen} />
          <FileRow path="input/sample_002.json" icon={FileText} onOpen={onFileOpen} />

          <SectionHeading label="Schema" />
          <FileRow path="input/schema.json" icon={FileText} onOpen={onFileOpen} />
        </div>
      </ScrollArea>
    </div>
  )
}

// Timeline Panel
export function TimelinePanel() {
  const traces = [
    { id: 1, name: "Run #142", status: "success", duration: "2.3s", time: "2m ago" },
    { id: 2, name: "Run #141", status: "error", duration: "0.8s", time: "5m ago" },
    { id: 3, name: "Run #140", status: "success", duration: "1.9s", time: "12m ago" },
    { id: 4, name: "Run #139", status: "success", duration: "2.1s", time: "18m ago" },
  ]

  return (
    <div className="h-full bg-background flex flex-col">
      <PanelHeader title="Timeline" />

      <ScrollArea className="flex-1">
        <div className="py-2 px-2">
          {traces.map((trace) => (
            <div
              key={trace.id}
              className="px-2 py-2 rounded-md hover:bg-accent cursor-pointer transition-colors group"
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
              <div className="mt-0.5 flex items-center gap-2 text-xs text-muted-foreground pl-6">
                <span>{trace.duration}</span>
              </div>
            </div>
          ))}
        </div>
      </ScrollArea>
    </div>
  )
}

// Properties Panel
export function PropertiesPanel() {
  const [temperature, setTemperature] = useState([0.7])
  const [modelOpen, setModelOpen] = useState(false)
  const [modelValue, setModelValue] = useState("gpt-4o-mini")
  const models = [
    { value: "gpt-4o-mini", label: "GPT-4o Mini" },
    { value: "gpt-4o", label: "GPT-4o" },
    { value: "claude-3.5", label: "Claude 3.5 Sonnet" },
  ]

  return (
    <div className="h-full bg-background flex flex-col">
      <PanelHeader title="Properties" />

      <ScrollArea className="flex-1">
        <div className="p-4 space-y-5">
          <div className="space-y-2">
            <Label className="text-xs text-muted-foreground">Node ID</Label>
            <Input
              readOnly
              value="node_text_gen_01"
              className="h-7 text-xs bg-muted"
            />
          </div>

          <div className="space-y-2">
            <Label className="text-xs text-muted-foreground">Type</Label>
            <div className="flex items-center gap-2">
              <Badge variant="secondary">Text Generation</Badge>
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
                  {models.find((m) => m.value === modelValue)?.label ?? "Select model..."}
                  <ChevronsUpDown className="ml-2 size-3.5 shrink-0 opacity-50" />
                </Button>
              </PopoverTrigger>
              <PopoverContent className="w-[--radix-popover-trigger-width] p-0" align="start">
                <Command>
                  <CommandInput placeholder="Search model..." className="h-8 text-xs" />
                  <CommandList>
                    <CommandEmpty>No model found.</CommandEmpty>
                    <CommandGroup>
                      {models.map((m) => (
                        <CommandItem
                          key={m.value}
                          value={m.value}
                          onSelect={(currentValue) => {
                            setModelValue(currentValue === modelValue ? "" : currentValue)
                            setModelOpen(false)
                          }}
                          className="text-xs"
                        >
                          <Check className={cn("mr-2 size-3.5", modelValue === m.value ? "opacity-100" : "opacity-0")} />
                          {m.label}
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
              className="text-xs resize-none min-h-[100px]"
              placeholder="Enter system prompt..."
              defaultValue="You are a helpful assistant."
            />
          </div>
        </div>
      </ScrollArea>
    </div>
  )
}

// Editor Panel
export function EditorPanel() {
  const codeLines = [
    { num: 1, content: "# main.py", type: "comment" },
    { num: 2, content: "import asyncio", type: "import" },
    { num: 3, content: "from skill import Skill", type: "import" },
    { num: 4, content: "", type: "blank" },
    { num: 5, content: "class TextGenerator(Skill):", type: "class" },
    { num: 6, content: "    def __init__(self):", type: "def" },
    { num: 7, content: "        super().__init__()", type: "code" },
    { num: 8, content: '        self.model = "gpt-4o-mini"', type: "string" },
    { num: 9, content: "", type: "blank" },
    { num: 10, content: "    async def run(self, input_data):", type: "def" },
    { num: 11, content: "        response = await self.llm.generate(", type: "code" },
    { num: 12, content: "            prompt=input_data.prompt,", type: "code" },
    { num: 13, content: "            model=self.model,", type: "code" },
    { num: 14, content: "            temperature=0.7", type: "number" },
    { num: 15, content: "        )", type: "code" },
    { num: 16, content: "        return response.text", type: "code" },
  ]

  return (
    <div className="h-full bg-background flex flex-col">
      <PanelHeader
        title="Editor"
        extra={<Badge variant="outline" className="text-xs">main.py</Badge>}
      />

      <ScrollArea className="flex-1">
        <div className="flex min-w-max">
          {/* Line numbers */}
          <div className="py-3 px-3 text-right select-none border-r border-border sticky left-0 bg-muted/50">
            {codeLines.map((line) => (
              <div key={line.num} className="text-xs font-mono text-muted-foreground leading-6 h-6">
                {line.num}
              </div>
            ))}
          </div>
          {/* Code */}
          <pre className="py-3 px-4 text-xs font-mono leading-6">
            {codeLines.map((line) => (
              <div key={line.num} className="h-6">
                {line.type === "comment" && <span className="text-muted-foreground">{line.content}</span>}
                {line.type === "import" && (
                  <>
                    <span className="text-foreground">{line.content.split(" ")[0]}</span>
                    <span className="text-foreground">{" " + line.content.slice(line.content.indexOf(" ") + 1)}</span>
                  </>
                )}
                {line.type === "class" && (
                  <>
                    <span className="text-foreground">class</span>
                    <span className="text-foreground"> TextGenerator</span>
                    <span className="text-foreground">(Skill):</span>
                  </>
                )}
                {line.type === "def" && (
                  <>
                    <span className="text-foreground">{line.content.match(/^\s*/)?.[0]}</span>
                    <span className="text-foreground">{line.content.includes("async") ? "async def" : "def"}</span>
                    <span className="text-foreground"> {line.content.match(/def (\w+)/)?.[1]}</span>
                    <span className="text-foreground">{line.content.slice(line.content.indexOf("("))}</span>
                  </>
                )}
                {line.type === "string" && (
                  <>
                    <span className="text-foreground">{line.content.split('"')[0]}</span>
                    <span className="text-foreground">&quot;{line.content.split('"')[1]}&quot;</span>
                  </>
                )}
                {line.type === "number" && (
                  <>
                    <span className="text-foreground">{line.content.split("=")[0]}=</span>
                    <span className="text-foreground">{line.content.split("=")[1]}</span>
                  </>
                )}
                {line.type === "code" && <span className="text-foreground">{line.content}</span>}
                {line.type === "blank" && <span>&nbsp;</span>}
              </div>
            ))}
          </pre>
        </div>
      </ScrollArea>
    </div>
  )
}
