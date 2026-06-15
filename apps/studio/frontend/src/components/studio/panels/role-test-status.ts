import type { RoleTestStatus } from "@/api/llm"

// Maps the node Properties role-test runner state (running / last result / error)
// to a single status badge. Reuses the same overall RoleTestStatus vocabulary
// the settings RoleTestResultPanel uses, projected to the badge variants the
// shadcn Badge component exposes. Pure + framework-free so it can be unit tested
// without a DOM (renderToStaticMarkup / element-walk convention).

export type RoleTestBadgeVariant = "secondary" | "success" | "warning" | "destructive"

export interface RoleTestStatusBadge {
  label: string
  variant: RoleTestBadgeVariant
  // "running" suppresses click + drives the spinner; informational for the UI.
  running: boolean
}

export interface RoleTestStatusInput {
  running: boolean
  status?: RoleTestStatus | null
  error?: string | null
}

export function roleTestStatusBadge(input: RoleTestStatusInput): RoleTestStatusBadge {
  if (input.running) {
    return { label: "Testing", variant: "secondary", running: true }
  }
  if (input.error) {
    return { label: "Failed", variant: "destructive", running: false }
  }
  return { ...roleTestResultBadge(input.status ?? null), running: false }
}

function roleTestResultBadge(status: RoleTestStatus | null): Omit<RoleTestStatusBadge, "running"> {
  if (status === "ok") {
    return { label: "Passed", variant: "success" }
  }
  if (status === "warning") {
    return { label: "Needs Attention", variant: "warning" }
  }
  if (status === "blocked" || status === "failed") {
    return { label: "Failed", variant: "destructive" }
  }
  return { label: "Untested", variant: "secondary" }
}
