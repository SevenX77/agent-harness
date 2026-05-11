
import { useCallback, useMemo } from "react"
import {
  ReactFlow,
  Background,
  BackgroundVariant,
  Controls,
  MiniMap,
  useNodesState,
  useEdgesState,
  addEdge,
  type Connection,
  type Node,
  type Edge,
  Handle,
  Position,
} from "@xyflow/react"
import "@xyflow/react/dist/style.css"
import { MoreHorizontal } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { cn } from "@/lib/utils"
import { useTheme } from "@/hooks/use-theme"

// Custom Node Component
function SkillNode({ data, selected }: { data: { label: string; type: string; status?: string; id: string }; selected: boolean }) {
  return (
    <div
      className={cn(
        "relative bg-card border rounded-md min-w-[180px] shadow-sm transition-all duration-150",
        selected ? "border-primary shadow-[0_0_0_1px_var(--primary)]" : "border-border hover:border-muted-foreground"
      )}
    >
      {/* Header */}
      <div className="flex items-center justify-between px-2.5 py-1.5 border-b border-border">
        <div className="flex items-center gap-2">
          <div className={cn(
            "size-1.5 rounded-full",
            data.status === "active" ? "bg-primary" : "bg-muted-foreground"
          )} />
          <span className="text-xs font-medium text-foreground">{data.label}</span>
        </div>
        <Button variant="ghost" size="icon-xs">
          <MoreHorizontal />
        </Button>
      </div>

      {/* Content */}
      <div className="px-2.5 py-1.5">
        <div className="flex items-center justify-between">
          <span className="text-xs text-muted-foreground">{data.id}</span>
          <Badge variant="secondary">{data.type}</Badge>
        </div>
      </div>

      {/* Handles */}
      <Handle
        type="target"
        position={Position.Left}
        className="!size-2 !bg-foreground !border !border-foreground hover:!ring-2 hover:!ring-primary/30 !transition-all !rounded-full"
      />
      <Handle
        type="source"
        position={Position.Right}
        className="!size-2 !bg-foreground !border !border-foreground hover:!ring-2 hover:!ring-primary/30 !transition-all !rounded-full"
      />
    </div>
  )
}

// Initial nodes
const initialNodes: Node[] = [
  {
    id: "1",
    type: "skillNode",
    position: { x: 100, y: 200 },
    data: { label: "Input Parser", type: "parser", status: "active", id: "node_001" },
  },
  {
    id: "2",
    type: "skillNode",
    position: { x: 380, y: 150 },
    data: { label: "LLM Processor", type: "llm", status: "active", id: "node_002" },
  },
  {
    id: "3",
    type: "skillNode",
    position: { x: 380, y: 280 },
    data: { label: "Tool Executor", type: "tool", id: "node_003" },
  },
  {
    id: "4",
    type: "skillNode",
    position: { x: 660, y: 200 },
    data: { label: "Output Handler", type: "output", id: "node_004" },
  },
]

// Initial edges
const initialEdges: Edge[] = [
  {
    id: "e1-2",
    source: "1",
    target: "2",
    animated: true,
    style: { stroke: "var(--primary)", strokeWidth: 1 },
  },
  {
    id: "e1-3",
    source: "1",
    target: "3",
    style: { stroke: "var(--muted-foreground)", strokeWidth: 1, opacity: 0.5 },
  },
  {
    id: "e2-4",
    source: "2",
    target: "4",
    animated: true,
    style: { stroke: "var(--primary)", strokeWidth: 1 },
  },
  {
    id: "e3-4",
    source: "3",
    target: "4",
    style: { stroke: "var(--muted-foreground)", strokeWidth: 1, opacity: 0.5 },
  },
]

export function Canvas() {
  const { theme } = useTheme()
  const nodeTypes = useMemo(() => ({ skillNode: SkillNode }), [])
  const [nodes, , onNodesChange] = useNodesState(initialNodes)
  const [edges, setEdges, onEdgesChange] = useEdgesState(initialEdges)

  const onConnect = useCallback(
    (params: Connection) =>
      setEdges((eds) =>
        addEdge(
          { ...params, style: { stroke: "var(--muted-foreground)" } },
          eds,
        ),
      ),
    [setEdges],
  )

  return (
    <div className="relative size-full">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onConnect={onConnect}
        nodeTypes={nodeTypes}
        fitView
        fitViewOptions={{ padding: 0.3 }}
        colorMode={theme}
        className="bg-background"
        defaultEdgeOptions={{ type: "smoothstep" }}
      >
        <Background
          variant={BackgroundVariant.Dots}
          gap={12}
          size={1}
          color="var(--muted-foreground)"
          style={{ opacity: 0.4 }}
          className="!bg-background"
        />
        <Controls showInteractive={false} />
        <MiniMap
          nodeColor="var(--muted-foreground)"
          nodeStrokeWidth={0}
          maskColor={
            theme === "dark"
              ? "rgba(0, 0, 0, 0.5)"
              : "rgba(255, 255, 255, 0.6)"
          }
          pannable
          zoomable
          className="!rounded-md"
        />
      </ReactFlow>
    </div>
  )
}
