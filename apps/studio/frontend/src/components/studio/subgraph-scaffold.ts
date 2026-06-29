// Auto-scaffolding for subgraph child graphs.
//
// Design source: engine skill-spec `00-FORMAT-GROUND-TRUTH.md` §1 (the standard
// skill tree nests child graphs under `subgraph/<child_skill_name>/`) and §4
// (`SUBGRAPH.md path` points at that child root, "推荐写相对 skill 根目录的路径,
// 例如 subgraph/producer_reviewer"). Studio MVP1 `graph-authoring` owns the
// "新建子图/默认落点 UI" unit and locks the default landing to a skill-root
// relative `subgraph/<name>` (docs/studio/mvp1/02_capabilities/graph-authoring/
// mvp1-alignment.md F4 + PM 2026-06-05 "文件夹名统一 subgraph/").
//
// When a subgraph phase is created we therefore (a) default its SUBGRAPH.md
// `path:` to `subgraph/<phaseId>` and (b) scaffold a standard empty child skill
// there so the reference resolves immediately. The scaffold is byte-for-byte the
// canonical empty-skill scaffold the sole writer emits for a brand-new skill
// (apps/studio/tauri/src/native_fs.rs `scaffold_files_for` ==
// apps/studio/backend/app/services/skills.py `_SCAFFOLD_FILES`).

/** Root container directory for nested child graphs (PM 2026-06-05: unified name). */
export const SUBGRAPH_CONTAINER_DIR = "subgraph"

const SAFE_CHILD_DIR_PATTERN = /^[A-Za-z0-9_][A-Za-z0-9_-]*$/

/** The skill-root-relative default landing directory for a subgraph phase's child graph. */
export function defaultSubgraphChildDir(phaseId: string): string {
  return `${SUBGRAPH_CONTAINER_DIR}/${phaseId}`
}

/**
 * The standard empty-skill scaffold files for a child graph at `childDir`,
 * returned as skill-root-relative (path, content) pairs. `childName` becomes the
 * child GRAPH.md `name:`. Kept byte-for-byte identical to the sole-writer
 * scaffold (`scaffold_files_for` / `_SCAFFOLD_FILES`) so an auto-created child is
 * indistinguishable from one made via "New skill".
 */
export function subgraphChildScaffoldFiles(
  childDir: string,
  childName: string,
): { path: string; content: string }[] {
  return [
    { path: `${childDir}/GRAPH.md`, content: childGraphMarkdown(childName) },
    { path: `${childDir}/phases/init/SKILL.md`, content: CHILD_INIT_SKILL_MARKDOWN },
  ]
}

/**
 * Classify a SUBGRAPH.md `path` value for safe auto-deletion. Returns the
 * skill-root-relative `subgraph/<safe-id>` directory ONLY when the path is the
 * exact auto-created default shape — a relative, single-segment child under the
 * `subgraph/` container with a safe name. Returns null for everything else
 * (empty, absolute, traversal, nested, or a re-pointed external/shared path) so
 * deleting a subgraph phase never destroys a child graph Studio did not create.
 * D7 ("subgraph 随便放哪里") makes arbitrary paths legal, so we must not delete
 * them on the author's behalf.
 */
export function autoCreatedSubgraphChildDir(path: string | null | undefined): string | null {
  if (typeof path !== "string") {
    return null
  }
  const normalized = path.trim().replace(/\\/g, "/").replace(/\/+$/, "")
  if (!normalized) {
    return null
  }
  const segments = normalized.split("/")
  if (segments.length !== 2 || segments[0] !== SUBGRAPH_CONTAINER_DIR) {
    return null
  }
  const childName = segments[1]
  if (!SAFE_CHILD_DIR_PATTERN.test(childName) || childName.length > 100) {
    return null
  }
  return `${SUBGRAPH_CONTAINER_DIR}/${childName}`
}

function childGraphMarkdown(childName: string): string {
  return [
    "---",
    'schema_version: "v0.3.0"',
    `name: ${childName}`,
    'description: "New Studio skill"',
    "io:",
    "  inputs:",
    "    type: object",
    "    properties: {}",
    "  outputs:",
    "    type: object",
    "    properties: {}",
    "phases:",
    "  - init",
    "---",
    '<phase depends_on="input" output>init</phase>',
    "",
  ].join("\n")
}

const CHILD_INIT_SKILL_MARKDOWN = [
  "---",
  "io:",
  "  inputs:",
  "    type: object",
  "    properties: {}",
  "  outputs:",
  "    type: object",
  "    properties: {}",
  "tools: []",
  "max_iterations: 10",
  "---",
  "<role>TODO: describe who this agent is.</role>",
  "<goal>TODO: describe what this agent should produce.</goal>",
  "",
  '<step id="S1" name="todo">TODO: describe the first step.</step>',
  "",
  '<protocol id="P1">TODO: describe a rule the agent must follow.</protocol>',
  "",
].join("\n")
