import type { ReactNode } from "react"
import { renderToStaticMarkup } from "react-dom/server"
import { beforeEach, describe, expect, it, vi } from "vitest"
import type { SkillDetail } from "@/api/types"
import type { SkillGraphNodeData } from "@/components/GraphCanvas"
import { writeSkillFile } from "@/api/client"
import { isTauriRuntime } from "@/config/runtime"
import { sha256Hex } from "@/lib/hash"
import { InputPanel } from "./InputPanel"

const buttonProps = vi.hoisted((): Array<Record<string, unknown>> => [])
const testInputsSectionProps = vi.hoisted((): Array<Record<string, unknown>> => [])

vi.mock("@/api/client", () => ({
  writeSkillFile: vi.fn(async () => ({ path: "GRAPH.md", hash: "next-hash" })),
}))

vi.mock("@/config/runtime", () => ({
  isTauriRuntime: vi.fn(),
}))

vi.mock("@/lib/hash", () => ({
  sha256Hex: vi.fn(async () => "current-graph-hash"),
}))

vi.mock("@/components/ui/button", () => ({
  Button: (props: Record<string, unknown> & { children?: ReactNode }) => {
    buttonProps.push(props)
    return <button aria-label={props["aria-label"] as string | undefined}>{props.children}</button>
  },
}))

vi.mock("@/components/ui/input", () => ({
  Input: (props: Record<string, unknown>) => (
    <input aria-label={props["aria-label"] as string | undefined} value={props.value as string | undefined} readOnly />
  ),
}))

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

vi.mock("@/components/ui/textarea", () => ({
  Textarea: (props: Record<string, unknown>) => (
    <textarea aria-label={props["aria-label"] as string | undefined} value={props.value as string | undefined} readOnly />
  ),
}))

vi.mock("./GoldenSection", () => ({
  GoldenSection: () => null,
}))

vi.mock("./TestInputsSection", () => ({
  TestInputsSection: (props: Record<string, unknown>) => {
    testInputsSectionProps.push(props)
    return null
  },
}))

const graphMd = [
  "---",
  "io:",
  "  inputs:",
  "    type: object",
  "    properties:",
  "      title:",
  "        type: string",
  "  outputs:",
  "    type: object",
  "    properties:",
  "      result:",
  "        type: string",
  "---",
  "input:",
  "  kind: input",
].join("\n")

function skillDetailWithGraph(content: string): SkillDetail {
  return {
    files: {
      "GRAPH.md": content,
    },
  } as unknown as SkillDetail
}

// A phase file (phases/<id>/SKILL.md) with its OWN frontmatter io, distinct from
// the graph-level io, so a per-node edit can be verified to land on the phase
// file's io.inputs (not GRAPH.md's). Field name `phase_field` is unique to the
// phase so the remove-button lookup is unambiguous.
const phaseSkillMd = [
  "---",
  "llm_role: analyst",
  "io:",
  "  inputs:",
  "    type: object",
  "    properties:",
  "      phase_field:",
  "        type: string",
  "  outputs:",
  "    type: object",
  "    properties:",
  "      phase_result:",
  "        type: string",
  "---",
  "<role>phase</role>",
].join("\n")

const PHASE_FILE_PATH = "phases/analyze/SKILL.md"

function skillDetailWithPhase(graphContent: string, phaseContent: string): SkillDetail {
  return {
    files: {
      "GRAPH.md": graphContent,
      [PHASE_FILE_PATH]: phaseContent,
    },
  } as unknown as SkillDetail
}

function selectedPhaseNode(): { id: string; data: SkillGraphNodeData } {
  return {
    id: "analyze",
    data: {
      skillId: "demo-skill",
      label: "analyze",
      mode: "agent",
      status: "idle",
      dependsOn: [],
      filePath: PHASE_FILE_PATH,
    },
  }
}

async function flushPromises(): Promise<void> {
  await Promise.resolve()
  await Promise.resolve()
}

describe("InputPanel GRAPH.md writes", () => {
  beforeEach(() => {
    buttonProps.length = 0
    testInputsSectionProps.length = 0
    vi.mocked(writeSkillFile).mockClear()
    vi.mocked(isTauriRuntime).mockReturnValue(true)
    vi.mocked(sha256Hex).mockClear()
  })

  it("passes the current GRAPH.md hash when removing an input field", async () => {
    renderToStaticMarkup(
      <InputPanel skillId="demo-skill" skillDetail={skillDetailWithGraph(graphMd)} />,
    )

    const removeButton = buttonProps.find(
      (props) => props["aria-label"] === "Remove inputs field title",
    )
    expect(removeButton).toBeTruthy()

    ;(removeButton?.onClick as () => void)()
    await flushPromises()

    expect(writeSkillFile).toHaveBeenCalledTimes(1)
    expect(writeSkillFile).toHaveBeenCalledWith(
      "demo-skill",
      "GRAPH.md",
      expect.any(String),
      "current-graph-hash",
    )
    expect(sha256Hex).toHaveBeenCalledWith(graphMd)
  })

  it("uses the imported workspace root and current GRAPH.md hash in the Tauri runtime", async () => {
    vi.mocked(isTauriRuntime).mockReturnValue(true)

    renderToStaticMarkup(
      <InputPanel
        skillId="demo-skill"
        workspaceRoot="/Users/sevenx/Projects/imported-skill"
        skillDetail={skillDetailWithGraph(graphMd)}
      />,
    )

    const removeButton = buttonProps.find(
      (props) => props["aria-label"] === "Remove inputs field title",
    )
    expect(removeButton).toBeTruthy()

    ;(removeButton?.onClick as () => void)()
    await flushPromises()

    expect(writeSkillFile).toHaveBeenCalledTimes(1)
    expect(writeSkillFile).toHaveBeenCalledWith(
      "/Users/sevenx/Projects/imported-skill",
      "GRAPH.md",
      expect.any(String),
      "current-graph-hash",
    )
    expect(sha256Hex).toHaveBeenCalledWith(graphMd)
  })

  it("uses the backend skill id instead of imported workspace root outside the Tauri runtime", async () => {
    vi.mocked(isTauriRuntime).mockReturnValue(false)

    renderToStaticMarkup(
      <InputPanel
        skillId="demo-skill"
        workspaceRoot="/Users/sevenx/Projects/imported-skill"
        skillDetail={skillDetailWithGraph(graphMd)}
      />,
    )

    const removeButton = buttonProps.find(
      (props) => props["aria-label"] === "Remove inputs field title",
    )
    expect(removeButton).toBeTruthy()

    ;(removeButton?.onClick as () => void)()
    await flushPromises()

    expect(writeSkillFile).toHaveBeenCalledTimes(1)
    expect(writeSkillFile).toHaveBeenCalledWith(
      "demo-skill",
      "GRAPH.md",
      expect.any(String),
      "current-graph-hash",
    )
    expect(writeSkillFile).not.toHaveBeenCalledWith(
      "/Users/sevenx/Projects/imported-skill",
      expect.anything(),
      expect.anything(),
      expect.anything(),
    )
    expect(sha256Hex).toHaveBeenCalledWith(graphMd)
  })

  it("passes the imported workspace root to TestInputsSection", () => {
    renderToStaticMarkup(
      <InputPanel
        skillId="demo-skill"
        workspaceRoot="/Users/sevenx/Projects/imported-skill"
        skillDetail={skillDetailWithGraph(graphMd)}
      />,
    )

    expect(testInputsSectionProps[0]).toMatchObject({
      skillId: "demo-skill",
      workspaceRoot: "/Users/sevenx/Projects/imported-skill",
    })
  })

  // Atom #27 (per-node i/o): selecting a phase node makes the panel edit THAT
  // phase file's frontmatter io, writing back to phases/<id>/SKILL.md (not
  // GRAPH.md), hashed over the phase file's own content.
  it("writes a selected phase node's io edit back to the phase file, not GRAPH.md", async () => {
    renderToStaticMarkup(
      <InputPanel
        skillId="demo-skill"
        skillDetail={skillDetailWithPhase(graphMd, phaseSkillMd)}
        selectedNode={selectedPhaseNode()}
      />,
    )

    // The row exists because the panel read the PHASE file's io.inputs, whose
    // field is `phase_field` (GRAPH.md's input field is `title`).
    const removeButton = buttonProps.find(
      (props) => props["aria-label"] === "Remove inputs field phase_field",
    )
    expect(removeButton).toBeTruthy()
    expect(
      buttonProps.find((props) => props["aria-label"] === "Remove inputs field title"),
    ).toBeFalsy()

    ;(removeButton?.onClick as () => void)()
    await flushPromises()

    expect(writeSkillFile).toHaveBeenCalledTimes(1)
    expect(writeSkillFile).toHaveBeenCalledWith(
      "demo-skill",
      PHASE_FILE_PATH,
      expect.any(String),
      "current-graph-hash",
    )
    // Optimistic-lock hash is over the PHASE file's current content.
    expect(sha256Hex).toHaveBeenCalledWith(phaseSkillMd)
    expect(sha256Hex).not.toHaveBeenCalledWith(graphMd)
    // The written content drops the removed field from the phase io.inputs.
    const writtenContent = vi.mocked(writeSkillFile).mock.calls[0][2] as string
    expect(writtenContent).not.toContain("phase_field")
  })

  it("targets a selected phase node's artifact-path save to the phase file", async () => {
    const phaseWithArtifact = phaseSkillMd.replace(
      "      phase_result:\n        type: string",
      "      phase_result:\n        type: string\n        path: out.json",
    )

    renderToStaticMarkup(
      <InputPanel
        skillId="demo-skill"
        skillDetail={skillDetailWithPhase(graphMd, phaseWithArtifact)}
        selectedNode={selectedPhaseNode()}
      />,
    )

    const saveButton = buttonProps.find(
      (props) => props["aria-label"] === "Save artifact path for output phase_result",
    )
    expect(saveButton).toBeTruthy()

    ;(saveButton?.onClick as () => void)()
    await flushPromises()

    expect(writeSkillFile).toHaveBeenCalledTimes(1)
    expect(writeSkillFile).toHaveBeenCalledWith(
      "demo-skill",
      PHASE_FILE_PATH,
      expect.any(String),
      "current-graph-hash",
    )
    expect(sha256Hex).toHaveBeenCalledWith(phaseWithArtifact)
  })

  // Regression guard: with no node selected the panel still edits GRAPH.md's
  // graph-level io (the global input/output node selection is handled the same
  // way inside resolveIoEditTarget).
  it("still writes graph-level io to GRAPH.md when no node is selected", async () => {
    renderToStaticMarkup(
      <InputPanel
        skillId="demo-skill"
        skillDetail={skillDetailWithPhase(graphMd, phaseSkillMd)}
        selectedNode={null}
      />,
    )

    const removeButton = buttonProps.find(
      (props) => props["aria-label"] === "Remove inputs field title",
    )
    expect(removeButton).toBeTruthy()

    ;(removeButton?.onClick as () => void)()
    await flushPromises()

    expect(writeSkillFile).toHaveBeenCalledWith(
      "demo-skill",
      "GRAPH.md",
      expect.any(String),
      "current-graph-hash",
    )
    expect(sha256Hex).toHaveBeenCalledWith(graphMd)
  })
})
