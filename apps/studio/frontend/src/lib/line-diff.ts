export type LineDiffKind = 'same' | 'add' | 'del'

export interface LineDiffRow {
  kind: LineDiffKind
  text: string
}

/**
 * Minimal line-level diff (LCS) for the copilot inline diff bubble. Not a full
 * Myers diff — good enough to colour added/removed lines green/red for a
 * human-scale skill file. Equal lines are shown once as context.
 */
export function computeLineDiff(before: string, after: string): LineDiffRow[] {
  const a = before.length === 0 ? [] : before.split('\n')
  const b = after.length === 0 ? [] : after.split('\n')

  // LCS table over lines.
  const n = a.length
  const m = b.length
  const lcs: number[][] = Array.from({ length: n + 1 }, () => new Array<number>(m + 1).fill(0))
  for (let i = n - 1; i >= 0; i -= 1) {
    for (let j = m - 1; j >= 0; j -= 1) {
      lcs[i][j] = a[i] === b[j] ? lcs[i + 1][j + 1] + 1 : Math.max(lcs[i + 1][j], lcs[i][j + 1])
    }
  }

  const rows: LineDiffRow[] = []
  let i = 0
  let j = 0
  while (i < n && j < m) {
    if (a[i] === b[j]) {
      rows.push({ kind: 'same', text: a[i] })
      i += 1
      j += 1
    } else if (lcs[i + 1][j] >= lcs[i][j + 1]) {
      rows.push({ kind: 'del', text: a[i] })
      i += 1
    } else {
      rows.push({ kind: 'add', text: b[j] })
      j += 1
    }
  }
  while (i < n) {
    rows.push({ kind: 'del', text: a[i] })
    i += 1
  }
  while (j < m) {
    rows.push({ kind: 'add', text: b[j] })
    j += 1
  }
  return rows
}

export interface LineDiffStats {
  added: number
  removed: number
}

export function lineDiffStats(rows: LineDiffRow[]): LineDiffStats {
  return rows.reduce<LineDiffStats>(
    (acc, row) => {
      if (row.kind === 'add') acc.added += 1
      if (row.kind === 'del') acc.removed += 1
      return acc
    },
    { added: 0, removed: 0 },
  )
}
