// The one barrel for `@/components/GraphCanvas`. An `index.ts` inside the
// folder next door would look like the obvious place to add an export and be
// dead on arrival: TypeScript resolves the module specifier to this FILE before
// it looks at the directory of the same name, so the folder's barrel is
// unreachable and nothing reports it. One lived there until 2026-08-23,
// exporting a strict subset — every export it was missing was already being
// imported from here, which is how it stayed invisible.
export { CanvasContextMenuContent, GraphCanvas } from "./GraphCanvas/GraphCanvas"
export type { ChildDetailPatch } from "./GraphCanvas/GraphCanvas"
export { buildEdges, SkillNode } from "./nodes"
export type {
  GraphCanvasNode,
  NodeActivity,
  NodeRuntime,
  SkillGraphNode,
  SkillGraphNodeData,
  SkillNodeStatus,
  SubagentRef,
} from "./nodes"
