
import { ChevronRight, ChevronDown, FileText, Folder, X, Play, AlertCircle, CheckCircle2 } from "lucide-react"
import { useState } from "react"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Separator } from "@/components/ui/separator"
import { Input } from "@/components/ui/input"
import { Textarea } from "@/components/ui/textarea"
import { Select, SelectContent, SelectGroup, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Slider } from "@/components/ui/slider"
import { Label } from "@/components/ui/label"
import {
  SidebarContent,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarMenuSub,
  SidebarMenuSubButton,
  SidebarMenuSubItem,
} from "@/components/ui/sidebar"

interface PanelProps {
  onClose: () => void
}

// Panel Header Component
function PanelHeader({ title, onClose, extra }: { title: string; onClose: () => void; extra?: React.ReactNode }) {
  return (
    <div className="h-10 flex items-center justify-between px-3 border-b border-border shrink-0 bg-muted/30">
      <div className="flex items-center gap-2">
        <span className="text-sm font-medium text-foreground">{title}</span>
        {extra}
      </div>
      <Button variant="ghost" size="icon" className="size-6" onClick={onClose}>
        <X className="size-3.5" />
      </Button>
    </div>
  )
}

// Assets Panel
export function AssetsPanel({ onClose }: PanelProps) {
  const [expanded, setExpanded] = useState<Record<string, boolean>>({
    scripts: true,
    data: false,
  })

  const toggleFolder = (folder: string) => {
    setExpanded((prev) => ({ ...prev, [folder]: !prev[folder] }))
  }

  return (
    <div className="h-full bg-background flex flex-col">
      <PanelHeader title="Assets" onClose={onClose} />

      <SidebarContent>
        <SidebarGroup>
          <SidebarGroupLabel>Project files</SidebarGroupLabel>
          <SidebarGroupContent>
            <SidebarMenu>
              <SidebarMenuItem>
                <SidebarMenuButton className="text-sm font-medium">
                  <FileText className="text-primary" strokeWidth={1.5} />
                  <span>SKILL.md</span>
                </SidebarMenuButton>
              </SidebarMenuItem>

              <SidebarMenuItem>
                <SidebarMenuButton
                  onClick={() => toggleFolder("scripts")}
                  className="text-sm font-medium"
                >
                  {expanded.scripts ? <ChevronDown /> : <ChevronRight />}
                  <Folder strokeWidth={1.5} />
                  <span>scripts</span>
                </SidebarMenuButton>
                {expanded.scripts && (
                  <SidebarMenuSub>
                    <SidebarMenuSubItem>
                      <SidebarMenuSubButton className="text-xs">
                        <FileText strokeWidth={1.5} />
                        <span>main.py</span>
                      </SidebarMenuSubButton>
                    </SidebarMenuSubItem>
                    <SidebarMenuSubItem>
                      <SidebarMenuSubButton className="text-xs">
                        <FileText strokeWidth={1.5} />
                        <span>utils.py</span>
                      </SidebarMenuSubButton>
                    </SidebarMenuSubItem>
                  </SidebarMenuSub>
                )}
              </SidebarMenuItem>

              <SidebarMenuItem>
                <SidebarMenuButton
                  onClick={() => toggleFolder("data")}
                  className="text-sm font-medium"
                >
                  {expanded.data ? <ChevronDown /> : <ChevronRight />}
                  <Folder strokeWidth={1.5} />
                  <span>data</span>
                </SidebarMenuButton>
                {expanded.data && (
                  <SidebarMenuSub>
                    <SidebarMenuSubItem>
                      <SidebarMenuSubButton className="text-xs">
                        <FileText strokeWidth={1.5} />
                        <span>golden_baseline.json</span>
                      </SidebarMenuSubButton>
                    </SidebarMenuSubItem>
                  </SidebarMenuSub>
                )}
              </SidebarMenuItem>

              <SidebarMenuItem>
                <SidebarMenuButton className="text-sm font-medium">
                  <FileText strokeWidth={1.5} />
                  <span>config.yaml</span>
                </SidebarMenuButton>
              </SidebarMenuItem>
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>
      </SidebarContent>
    </div>
  )
}

// Timeline Panel
export function TimelinePanel({ onClose }: PanelProps) {
  const traces = [
    { id: 1, name: "Run #142", status: "success", duration: "2.3s", time: "2m ago" },
    { id: 2, name: "Run #141", status: "error", duration: "0.8s", time: "5m ago" },
    { id: 3, name: "Run #140", status: "success", duration: "1.9s", time: "12m ago" },
    { id: 4, name: "Run #139", status: "success", duration: "2.1s", time: "18m ago" },
  ]

  return (
    <div className="h-full bg-background flex flex-col">
      <PanelHeader title="Timeline" onClose={onClose} />

      <SidebarContent>
        <SidebarGroup>
          <SidebarGroupLabel>Recent runs</SidebarGroupLabel>
          <SidebarGroupContent>
            <SidebarMenu>
          {traces.map((trace) => (
            <SidebarMenuItem key={trace.id}>
              <SidebarMenuButton className="h-auto items-start py-2 text-sm font-medium">
                {trace.status === "success" ? (
                  <CheckCircle2 className="mt-0.5 text-emerald-500" />
                ) : (
                  <AlertCircle className="mt-0.5 text-destructive" />
                )}
                <span className="flex min-w-0 flex-1 flex-col gap-0.5">
                  <span className="flex items-center justify-between gap-2">
                    <span className="truncate">{trace.name}</span>
                    <span className="text-xs font-normal text-muted-foreground">
                      {trace.time}
                    </span>
                  </span>
                  <span className="text-xs font-normal text-muted-foreground">
                    {trace.duration}
                  </span>
                </span>
              </SidebarMenuButton>
            </SidebarMenuItem>
          ))}
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>
      </SidebarContent>

      <Separator />
      <div className="p-2">
        <Button variant="secondary" size="sm" className="w-full gap-2">
          <Play className="size-3.5" />
          New Run
        </Button>
      </div>
    </div>
  )
}

// Properties Panel
export function PropertiesPanel({ onClose }: PanelProps) {
  const [temperature, setTemperature] = useState([0.7])

  return (
    <div className="h-full bg-background flex flex-col">
      <PanelHeader title="Properties" onClose={onClose} />

      <ScrollArea className="flex-1">
        <div className="p-4 space-y-5">
          <div className="space-y-2">
            <Label className="text-xs text-muted-foreground">Node ID</Label>
            <Input
              readOnly
              value="node_text_gen_01"
              className="h-8 text-sm font-mono bg-muted"
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
            <Select defaultValue="gpt-4o-mini">
              <SelectTrigger className="h-8 text-sm">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectGroup>
                  <SelectItem value="gpt-4o-mini">GPT-4o Mini</SelectItem>
                  <SelectItem value="gpt-4o">GPT-4o</SelectItem>
                  <SelectItem value="claude-3.5">Claude 3.5 Sonnet</SelectItem>
                </SelectGroup>
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <Label className="text-xs text-muted-foreground">Temperature</Label>
              <span className="text-sm font-mono text-foreground">{temperature[0]}</span>
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
              className="text-sm resize-none min-h-[100px]"
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
export function EditorPanel({ onClose }: PanelProps) {
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
        onClose={onClose}
        extra={<Badge variant="outline" className="text-xs font-mono">main.py</Badge>}
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
          <pre className="py-3 px-4 text-sm font-mono leading-6">
            {codeLines.map((line) => (
              <div key={line.num} className="h-6">
                {line.type === "comment" && <span className="text-muted-foreground">{line.content}</span>}
                {line.type === "import" && (
                  <>
                    <span className="text-blue-400">{line.content.split(" ")[0]}</span>
                    <span className="text-foreground">{" " + line.content.slice(line.content.indexOf(" ") + 1)}</span>
                  </>
                )}
                {line.type === "class" && (
                  <>
                    <span className="text-blue-400">class</span>
                    <span className="text-yellow-400"> TextGenerator</span>
                    <span className="text-foreground">(Skill):</span>
                  </>
                )}
                {line.type === "def" && (
                  <>
                    <span className="text-foreground">{line.content.match(/^\s*/)?.[0]}</span>
                    <span className="text-blue-400">{line.content.includes("async") ? "async def" : "def"}</span>
                    <span className="text-green-400"> {line.content.match(/def (\w+)/)?.[1]}</span>
                    <span className="text-foreground">{line.content.slice(line.content.indexOf("("))}</span>
                  </>
                )}
                {line.type === "string" && (
                  <>
                    <span className="text-foreground">{line.content.split('"')[0]}</span>
                    <span className="text-amber-400">&quot;{line.content.split('"')[1]}&quot;</span>
                  </>
                )}
                {line.type === "number" && (
                  <>
                    <span className="text-foreground">{line.content.split("=")[0]}=</span>
                    <span className="text-amber-400">{line.content.split("=")[1]}</span>
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
