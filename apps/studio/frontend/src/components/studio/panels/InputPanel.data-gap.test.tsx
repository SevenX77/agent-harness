import type { ReactNode } from "react"
import { renderToStaticMarkup } from "react-dom/server"
import { describe, expect, it, vi } from "vitest"
import type { GraphTopologyItem, SkillDetail } from "@/api/types"
import type { SkillGraphNodeData } from "@/components/GraphCanvas"
import { InputPanel } from "./InputPanel"

// n2-canvas#10 (data-gap-viz): the i/o panel renders a data-gap marker on each
// input field the backend reports as unsupplied, and names the producer of
// supplied ones. The marker data is the REAL new backend field
// graph_topology[].field_supply (services/skills.py _topology_row ->
// services/canvas_data_gap.py compute_field_supply); the panel joins it to the
// phase's input fields by field name. This render-contract test proves the
// producer->consumer wiring: a phase whose SKILL.md declares three inputs, with a
// field_supply row marking one as unsupplied, renders exactly one gap warning and
// the two producers. If the panel stopped reading field_supply, all three markers
// would vanish — so the markers are driven, not dead.

vi.mock("@/api/client", () => ({
  writeSkillFile: vi.fn(async () => ({ path: "GRAPH.md", hash: "next-hash" })),
}))
vi.mock("@/config/runtime", () => ({ isTauriRuntime: vi.fn(() => false) }))
vi.mock("@/lib/hash", () => ({ sha256Hex: vi.fn(async () => "h") }))
vi.mock("@/components/ui/scroll-area", () => ({
  ScrollArea: ({ children }: { children?: ReactNode }) => <div>{children}</div>,
}))
vi.mock("@/components/ui/select", () => ({
  Select: ({ children }: { children?: ReactNode }) => <div>{children}</div>,
  SelectContent: ({ children }: { children?: ReactNode }) => <div>{children}</div>,
  SelectItem: ({ children }: { children?: ReactNode }) => <div>{children}</div>,
  SelectTrigger: ({ children }: { children?: ReactNode }) => <button>{children}</button>,
  SelectValue: ({ placeholder }: { placeholder?: ReactNode }) => <span>{placeholder}</span>,
}))
vi.mock("./GoldenSection", () => ({ GoldenSection: () => null }))
vi.mock("./TestInputsSection", () => ({ TestInputsSection: () => null }))

// A phase file whose io.inputs declares the three fields the backend field_supply
// reports on — the panel must list these (from the phase frontmatter) AND join
// each to its supply entry by name.
const PHASE_FILE_PATH = "phases/enrich/LOGIC.md"
const phaseMd = [
  "---",
  "io:",
  "  inputs:",
  "    type: object",
  "    properties:",
  "      doc:",
  "        type: string",
  "      topic:",
  "        type: string",
  "      orphan:",
  "        type: string",
  "---",
  "body",
].join("\n")

// The REAL backend payload shape: graph_topology row for the selected phase,
// carrying field_supply for its three inputs (one upstream-phase-fed, one graph
// input, one data gap).
const topology: GraphTopologyItem[] = [
  {
    id: "enrich",
    src: "phases/enrich",
    depends_on: ["fetch"],
    mode: "logic",
    io_fields: {
      inputs: { doc: { type: "string" }, topic: { type: "string" }, orphan: { type: "string" } },
      outputs: {},
    },
    field_supply: [
      { field: "doc", supplied: true, source: "phase", producer_phase: "fetch" },
      { field: "topic", supplied: true, source: "graph_input", producer_phase: null },
      { field: "orphan", supplied: false, source: "none", producer_phase: null },
    ],
  },
]

function detail(): SkillDetail {
  return {
    files: { "GRAPH.md": "---\nio:\n  inputs:\n    properties: {}\n---\n", [PHASE_FILE_PATH]: phaseMd },
    graph_topology: topology,
  } as unknown as SkillDetail
}

function selectedNode(): { id: string; data: SkillGraphNodeData } {
  return {
    id: "enrich",
    data: {
      skillId: "demo",
      label: "enrich",
      mode: "logic",
      status: "idle",
      dependsOn: ["fetch"],
      filePath: PHASE_FILE_PATH,
    },
  }
}

describe("InputPanel — data-gap markers (n2-canvas#10)", () => {
  it("renders a data-gap warning for the unsupplied field and producers for supplied ones", () => {
    const html = renderToStaticMarkup(
      <InputPanel skillId="demo" skillDetail={detail()} selectedNode={selectedNode()} />,
    )

    // The data gap: the unsupplied input field gets a warning marker.
    expect(html).toContain(
      "Data gap: input field orphan is not supplied by any upstream phase or graph input",
    )
    // The supplied fields name their producer (upstream phase / graph input).
    expect(html).toContain("Input field doc supplied by fetch")
    expect(html).toContain("Input field topic supplied by Graph input")
    // Exactly one gap marker (orphan), not the two supplied fields.
    expect(html.match(/Data gap: input field/g)?.length).toBe(1)
  })

  it("does not render data-gap markers for graph-level io (no node selected)", () => {
    // With no per-node selection the panel edits GRAPH.md graph-level io, which has
    // no upstream producers to chart — fieldSupplyByField returns empty, so no
    // markers render even though graph_topology carries field_supply for phases.
    const html = renderToStaticMarkup(<InputPanel skillId="demo" skillDetail={detail()} selectedNode={null} />)

    expect(html).not.toContain("Data gap: input field")
    expect(html).not.toContain("supplied by")
  })
})
