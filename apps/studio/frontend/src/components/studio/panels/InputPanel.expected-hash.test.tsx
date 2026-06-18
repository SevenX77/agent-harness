import type { ReactNode } from "react"
import { renderToStaticMarkup } from "react-dom/server"
import { beforeEach, describe, expect, it, vi } from "vitest"
import type { SkillDetail } from "@/api/types"
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
})
