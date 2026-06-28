import type { SkillDetail } from "@/api/types"
import type { SkillGraphNodeData } from "@/components/GraphCanvas"
import type { FileMeta } from "../file-types"
import { CURRENT_SCHEMA_VERSION } from "@/config/schema"

export function languageForPath(path: string): string {
  if (path.endsWith(".json")) return "json"
  if (path.endsWith(".py")) return "python"
  return "markdown"
}

export function fileFromDetail(skillDetail: SkillDetail | undefined, path: string): FileMeta {
  return {
    path,
    language: languageForPath(path),
    content: skillDetail?.files?.[path] ?? "",
  }
}

export function phaseIds(skillDetail?: SkillDetail): string[] {
  const fromTopology = skillDetail?.graph_topology?.map((phase) => phase.id) ?? []
  if (fromTopology.length > 0) return fromTopology
  const version = skillDetail?.manifest?.schema_version
  if (version === CURRENT_SCHEMA_VERSION) {
    return (skillDetail?.manifest?.phases ?? []) as unknown as string[]
  }
  return []
}

export function actionFiles(skillDetail: SkillDetail | undefined, phaseId: string): FileMeta[] {
  return Object.keys(skillDetail?.files ?? {})
    .filter((path) => path.startsWith(`phases/${phaseId}/actions/`) && path.endsWith(".py"))
    .sort((a, b) => a.localeCompare(b))
    .map((path) => fileFromDetail(skillDetail, path))
}

export function manifestFiles(skillDetail?: SkillDetail, selectedNode?: { id: string; data: SkillGraphNodeData } | null): FileMeta[] {
  const manifest = skillDetail?.manifest
  if (skillDetail?.files) {
    return Object.keys(skillDetail.files)
      .sort((a, b) => a.localeCompare(b))
      .map((path) => fileFromDetail(skillDetail, path))
  }
  const files: FileMeta[] = [
    {
      path: "SKILL.md",
      language: "markdown",
      content: manifest
        ? `# ${manifest.name}\n\n${manifest.description ?? "No description."}\n`
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

/**
 * Read-only projection of the skill's declared io contract for DISPLAY/SEEDING
 * only. The authoritative io contract lives in GRAPH.md `io.inputs`/`io.outputs`
 * frontmatter; the manifest's `io` is a derived copy. This used to project two
 * FAKE editable files (`input/schema.json` + `input/sample.json`) into the
 * editor — but those paths do not exist on disk, so edits autosaved to dead
 * paths = silent data loss. The projection is gone: callers now get the parsed
 * io maps and a sample seed string, and edit the real contract via the GRAPH.md
 * field editor instead.
 */
export interface IoContractView {
  inputs: Record<string, unknown>
  outputs: Record<string, unknown>
  /** A `{field: ""}` skeleton from the input fields, to seed the schema-infer textarea. */
  inputSampleJson: string
}

export function inputContractView(skillDetail?: SkillDetail): IoContractView {
  const manifest = skillDetail?.manifest as unknown as {
    io?: {
      inputs?: { properties?: Record<string, unknown> } | Record<string, unknown>
      outputs?: { properties?: Record<string, unknown> } | Record<string, unknown>
    }
  }
  const io = manifest?.io
  const inputs = (io?.inputs && typeof io.inputs === "object" && "properties" in io.inputs)
    ? (io.inputs.properties as Record<string, unknown>)
    : (io?.inputs as Record<string, unknown>) ?? {}
  const outputs = (io?.outputs && typeof io.outputs === "object" && "properties" in io.outputs)
    ? (io.outputs.properties as Record<string, unknown>)
    : (io?.outputs as Record<string, unknown>) ?? {}

  return {
    inputs,
    outputs,
    inputSampleJson: JSON.stringify(
      Object.fromEntries(Object.keys(inputs).map((name) => [name, ""])),
      null,
      2,
    ),
  }
}
