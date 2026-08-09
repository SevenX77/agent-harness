import { describe, expect, it } from "vitest"
import { isRunListing, latestRunDirectory, orderRunDirectories } from "./run-directory-order"
import type { AssetTreeEntry } from "./use-workspace-directory-tree"

function dir(name: string, modifiedMs?: number): AssetTreeEntry {
  return { name, path: `.workspace/runs/${name}`, kind: "dir", modifiedMs }
}

// Decision 2026-08-09 D13: "删除 `latest/` ... 「最新一次」改由 UI 表达:运行目录
// 按修改时间倒序,最新一条带 `latest` 小徽章。"
describe("isRunListing", () => {
  it("covers both run roots and nothing else", () => {
    expect(isRunListing(".workspace/runs")).toBe(true)
    expect(isRunListing(".workspace/predicts")).toBe(true)
    expect(isRunListing("phases")).toBe(false)
    expect(isRunListing(".workspace")).toBe(false)
    // A run's own contents are ordinary files and stay alphabetical.
    expect(isRunListing(".workspace/runs/2026-08-09T14-32-07_9f3ac1de")).toBe(false)
  })
})

describe("orderRunDirectories", () => {
  it("puts the most recently modified run at the top", () => {
    const ordered = orderRunDirectories([
      dir("2026-08-09T10-00-00_aaaaaaaa", 1_000),
      dir("2026-08-09T12-00-00_cccccccc", 3_000),
      dir("2026-08-09T11-00-00_bbbbbbbb", 2_000),
    ])

    expect(ordered.map((entry) => entry.name)).toEqual([
      "2026-08-09T12-00-00_cccccccc",
      "2026-08-09T11-00-00_bbbbbbbb",
      "2026-08-09T10-00-00_aaaaaaaa",
    ])
  })

  it("falls back to reverse name order when the filesystem reports no mtime", () => {
    // Run ids start with a sortable local timestamp, so this is still newest-first.
    const ordered = orderRunDirectories([
      dir("2026-08-09T10-00-00_aaaaaaaa"),
      dir("2026-08-09T12-00-00_cccccccc"),
      dir("2026-08-09T11-00-00_bbbbbbbb"),
    ])

    expect(ordered[0].name).toBe("2026-08-09T12-00-00_cccccccc")
    expect(ordered[2].name).toBe("2026-08-09T10-00-00_aaaaaaaa")
  })

  it("keeps directories above files, as the rest of the tree does", () => {
    const ordered = orderRunDirectories([
      { name: "index.json", path: ".workspace/runs/index.json", kind: "file", modifiedMs: 9_000 },
      dir("2026-08-09T10-00-00_aaaaaaaa", 1_000),
    ])

    expect(ordered.map((entry) => entry.kind)).toEqual(["dir", "file"])
  })
})

describe("latestRunDirectory", () => {
  it("names the newest run, which is what the deleted latest/ folder used to be", () => {
    const ordered = orderRunDirectories([
      dir("2026-08-09T10-00-00_aaaaaaaa", 1_000),
      dir("2026-08-09T12-00-00_cccccccc", 3_000),
    ])

    expect(latestRunDirectory(".workspace/runs", ordered))
      .toBe(".workspace/runs/2026-08-09T12-00-00_cccccccc")
  })

  it("badges nothing outside a run listing — no other folder has a 'latest'", () => {
    const ordered = [
      { name: "review", path: "phases/review", kind: "dir" as const, modifiedMs: 3_000 },
      { name: "draft", path: "phases/draft", kind: "dir" as const, modifiedMs: 1_000 },
    ]

    expect(latestRunDirectory("phases", ordered)).toBeNull()
  })

  it("never names a file — a stray file in the runs root is not a run", () => {
    const ordered = orderRunDirectories([
      { name: "index.json", path: ".workspace/runs/index.json", kind: "file", modifiedMs: 9_000 },
    ])

    expect(latestRunDirectory(".workspace/runs", ordered)).toBeNull()
  })

  it("names nothing when no run has happened yet", () => {
    expect(latestRunDirectory(".workspace/runs", [])).toBeNull()
  })
})
