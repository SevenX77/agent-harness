/**
 * How a run's numbers read, in the one place that decides it.
 *
 * The run list, the trace's terminal entry and the end-of-run toast all quote
 * the same duration and token total; three copies of the rounding rule is three
 * chances for the same run to look like two different runs.
 *
 * Absence returns null rather than a placeholder — how a surface renders "we
 * don't have this" is the surface's call (the list prints "n/a" in a fixed
 * column, the trace omits the chip entirely).
 */
export function formatRunDuration(seconds: number | null | undefined): string | null {
  if (typeof seconds !== 'number' || !Number.isFinite(seconds)) {
    return null
  }
  return seconds < 1 ? `${(seconds * 1000).toFixed(0)}ms` : `${seconds.toFixed(1)}s`
}

export function formatRunTokens(tokens: number | null | undefined): string | null {
  if (typeof tokens !== 'number' || !Number.isFinite(tokens)) {
    return null
  }
  return `${tokens.toLocaleString('en-US')} tokens`
}
