export const AUTHORED_TEMPERATURE_MAX = 2
export const TEMPERATURE_DEBOUNCE_MS = 300
export const TEMPERATURE_EMPTY_READOUT = "\u2014"

export const TEMPERATURE_SCALE_HELP =
  "Studio shows temperature as 0-100%. OpenAI-compatible, Gemini, and Ark keep the authored 0-2 scale; Anthropic is remapped to 0-1 at runtime."

export function formatTemperaturePercent(value: string | number | null | undefined): string {
  if (value == null || value === "") return TEMPERATURE_EMPTY_READOUT
  const numeric = typeof value === "number" ? value : Number(value)
  if (!Number.isFinite(numeric)) return TEMPERATURE_EMPTY_READOUT
  return `${Math.round((numeric / AUTHORED_TEMPERATURE_MAX) * 100)}%`
}
