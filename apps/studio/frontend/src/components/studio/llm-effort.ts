import type { CapabilityValue } from "@/api/llm"

/**
 * The draft's marker for "no level chosen", which means the provider's own
 * default — no level of ours stands in for it. A non-empty string because
 * Radix reserves the empty string for clearing a Select and rejects it as an
 * item value.
 */
export const PROVIDER_DEFAULT_EFFORT = "provider_default"

/**
 * Display order, weakest first. Which levels exist is the gateway's answer
 * (`settings_bounds._PROTOCOL_EFFORT_LEVELS` plus whatever probing measured);
 * this list only says how to rank the ones a route reported, so a name it does
 * not know is kept and shown last rather than dropped.
 */
const EFFORT_ORDER = ["none", "minimal", "low", "medium", "high", "xhigh", "max"]

const EFFORT_LABELS: Record<string, string> = {
  none: "None",
  minimal: "Minimal",
  low: "Low",
  medium: "Medium",
  high: "High",
  xhigh: "Extra high",
  max: "Max",
}

/** The effort levels a role can choose: every level any of its routes sells. */
export function effortLevelsFromCapabilities(
  capabilitiesPerRoute: ReadonlyArray<Record<string, CapabilityValue> | undefined>,
): string[] {
  const levels = new Set<string>()
  for (const capabilities of capabilitiesPerRoute) {
    for (const level of routeEffortLevels(capabilities)) levels.add(level)
  }
  return [...levels].sort((left, right) => effortRank(left) - effortRank(right))
}

export function formatEffortLabel(level: string): string {
  return EFFORT_LABELS[level] ?? level
}

function routeEffortLevels(capabilities: Record<string, CapabilityValue> | undefined): string[] {
  const value = capabilities?.reasoning_effort?.value
  if (!value || typeof value !== "object" || Array.isArray(value)) return []
  const levels = (value as { values?: unknown }).values
  if (!Array.isArray(levels)) return []
  return levels.filter((level): level is string => typeof level === "string" && level !== "")
}

function effortRank(level: string): number {
  const rank = EFFORT_ORDER.indexOf(level)
  return rank === -1 ? EFFORT_ORDER.length : rank
}
