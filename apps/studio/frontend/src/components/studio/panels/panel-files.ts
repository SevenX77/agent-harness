import type { SkillDetail } from "@/api/types"
import type { SkillGraphNodeData } from "@/components/GraphCanvas"
import type { FileMeta } from "../file-types"
import { CURRENT_SCHEMA_VERSION } from "@/config/schema"

function languageForPath(path: string): string {
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
    .sort()
    .map((path) => fileFromDetail(skillDetail, path))
}

export function manifestFiles(skillDetail?: SkillDetail, selectedNode?: { id: string; data: SkillGraphNodeData } | null): FileMeta[] {
  const manifest = skillDetail?.manifest
  if (skillDetail?.files) {
    return Object.keys(skillDetail.files)
      .sort()
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

export function inputFiles(skillDetail?: SkillDetail): FileMeta[] {
  if (!skillDetail?.files) {
    return []
  }
  return Object.keys(skillDetail.files)
    .filter((path) => {
      return (
        path === "input/schema.json" ||
        path === "input/sample.json" ||
        path.startsWith(".workspace/test_inputs/")
      )
    })
    .sort()
    .map((path) => fileFromDetail(skillDetail, path))
}
