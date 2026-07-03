import { renderToStaticMarkup } from "react-dom/server"
import { AxiosError } from "axios"
import type { AxiosResponse, InternalAxiosRequestConfig } from "axios"
import { beforeEach, describe, expect, it, vi } from "vitest"
import { writeSkillFile } from "@/api/client"
import { isTauriRuntime } from "@/config/runtime"
import { sha256Hex } from "@/lib/hash"
import type { LintError, LintResult } from "@/api/types"
import { LazyMonacoPanel, saveMonacoDraft } from "./LazyMonacoPanel"

vi.mock("@/api/client", () => ({
  writeSkillFile: vi.fn(),
}))

vi.mock("@/config/runtime", () => ({
  isTauriRuntime: vi.fn(),
}))

vi.mock("@/lib/hash", () => ({
  sha256Hex: vi.fn(async () => "derived-initial-hash"),
}))

vi.mock("sonner", () => ({
  toast: Object.assign(vi.fn(), {
    dismiss: vi.fn(),
    error: vi.fn(),
    success: vi.fn(),
  }),
}))

const debouncedLintResult = vi.fn<() => LintResult | null>(() => null)

vi.mock("@/hooks/useDebouncedLint", async () => {
  const actual = await vi.importActual<typeof import("@/hooks/useDebouncedLint")>(
    "@/hooks/useDebouncedLint",
  )
  return {
    ...actual,
    useDebouncedLint: () => ({
      status: "idle" as const,
      result: debouncedLintResult(),
      message: null,
      errors: [],
    }),
  }
})

describe("LazyMonacoPanel header controls", () => {
  beforeEach(() => {
    vi.stubGlobal("document", {
      documentElement: {
        classList: {
          contains: () => true,
        },
      },
    })
  })

  it("uses shadcn badge and icon buttons for editor chrome actions", () => {
    const html = renderToStaticMarkup(
      <LazyMonacoPanel
        title="Skill.md"
        skillId="skill-1"
        filePath="SKILL.md"
        value="# Skill"
        onChange={vi.fn()}
        onSaved={vi.fn()}
        onInFlightChange={vi.fn()}
        onConflict={vi.fn()}
        onClose={vi.fn()}
        onSplit={vi.fn()}
      />,
    )

    expect(html).toContain('data-slot="badge"')
    expect(html).toContain('data-slot="button"')
    expect(html).toContain('aria-label="Split editor"')
    expect(html).toContain('aria-label="Close editor"')
    expect(html).not.toContain(">x</button>")
    expect(html).not.toContain("inline-flex size-7")
  })
})

describe("LazyMonacoPanel lint diagnostics strip", () => {
  beforeEach(() => {
    vi.stubGlobal("document", {
      documentElement: {
        classList: {
          contains: () => true,
        },
      },
    })
    debouncedLintResult.mockReset()
  })

  function makeError(overrides: Partial<LintError> = {}): LintError {
    return {
      file: "GRAPH.md",
      line: null,
      column: null,
      error_code: "F-v3-001",
      severity: "error",
      message: "Invalid YAML in frontmatter: found duplicate key \"aa_number\"",
      phase_name: null,
      ...overrides,
    }
  }

  it("renders the line-less-diagnostic strip above the editor instead of dropping it silently", () => {
    // LazyMonacoPanel.tsx already documents this contract in a comment next to
    // applyLintMarkers: "Line-less diagnostics degrade to the strip above,
    // never guess a line." That strip is `LintDiagnosticsPanel` from
    // MonacoPanel.tsx, which exists (and is unit-tested in
    // MonacoPanel.test.tsx) but, before this fix, was never actually mounted
    // anywhere in the app — a GRAPH.md parse failure with no extractable line
    // number (e.g. the raw ruamel YAML error) had nowhere to surface at all.
    debouncedLintResult.mockReturnValue({
      status: "failed",
      errors: [makeError()],
      phases_summary: null,
    })

    const html = renderToStaticMarkup(
      <LazyMonacoPanel
        title="GRAPH.md"
        skillId="skill-1"
        filePath="GRAPH.md"
        value="---\n---\n"
        onChange={vi.fn()}
        onSaved={vi.fn()}
        onInFlightChange={vi.fn()}
        onConflict={vi.fn()}
      />,
    )

    expect(html).toContain('aria-label="Lint diagnostics"')
    expect(html).toContain("Invalid YAML in frontmatter")
    expect(html).toContain("No line")
  })

  it("stays collapsed (renders nothing) when lint has not found any diagnostics", () => {
    debouncedLintResult.mockReturnValue({ status: "passed", errors: [], phases_summary: null })

    const html = renderToStaticMarkup(
      <LazyMonacoPanel
        title="GRAPH.md"
        skillId="skill-1"
        filePath="GRAPH.md"
        value="---\n---\n"
        onChange={vi.fn()}
        onSaved={vi.fn()}
        onInFlightChange={vi.fn()}
        onConflict={vi.fn()}
      />,
    )

    expect(html).not.toContain('aria-label="Lint diagnostics"')
  })
})

describe("saveMonacoDraft", () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(isTauriRuntime).mockReturnValue(true)
    vi.mocked(writeSkillFile).mockResolvedValue({ path: "SKILL.md", hash: "native-hash" })
  })

  it("saves local Tauri workspaces with workspaceRoot and a derived initial hash guard", async () => {
    const onSaved = vi.fn()
    const onConflict = vi.fn()

    await expect(saveMonacoDraft({
      skillId: "writer-smoke",
      workspaceRoot: "/Users/sevenx/Projects/writer-smoke",
      filePath: "SKILL.md",
      content: "# Changed\n",
      savedContent: "# Original\n",
      currentHash: null,
      onSaved,
      onConflict,
    })).resolves.toEqual({
      status: "saved",
      hash: "native-hash",
      savedContent: "# Changed\n",
    })

    expect(sha256Hex).toHaveBeenCalledWith("# Original\n")
    expect(writeSkillFile).toHaveBeenCalledWith(
      "/Users/sevenx/Projects/writer-smoke",
      "SKILL.md",
      "# Changed\n",
      "derived-initial-hash",
    )
    expect(onSaved).toHaveBeenCalledWith("native-hash")
    expect(onConflict).not.toHaveBeenCalled()
  })

  it("uses skillId instead of workspaceRoot when saving outside the Tauri runtime", async () => {
    vi.mocked(isTauriRuntime).mockReturnValue(false)

    await saveMonacoDraft({
      skillId: "writer-smoke",
      workspaceRoot: "/Users/sevenx/Projects/writer-smoke",
      filePath: "SKILL.md",
      content: "# Browser change\n",
      savedContent: "# Original\n",
      currentHash: "browser-current-hash",
      onSaved: vi.fn(),
      onConflict: vi.fn(),
    })

    expect(writeSkillFile).toHaveBeenCalledWith(
      "writer-smoke",
      "SKILL.md",
      "# Browser change\n",
      "browser-current-hash",
    )
  })

  it("uses the latest saved hash after the first Monaco save succeeds", async () => {
    await saveMonacoDraft({
      skillId: "writer-smoke",
      workspaceRoot: "/Users/sevenx/Projects/writer-smoke",
      filePath: "SKILL.md",
      content: "# Second change\n",
      savedContent: "# First change\n",
      currentHash: "current-native-hash",
      onSaved: vi.fn(),
      onConflict: vi.fn(),
    })

    expect(sha256Hex).not.toHaveBeenCalled()
    expect(writeSkillFile).toHaveBeenCalledWith(
      "/Users/sevenx/Projects/writer-smoke",
      "SKILL.md",
      "# Second change\n",
      "current-native-hash",
    )
  })

  it("surfaces a read_only result when the backend refuses a read-only skill (403 SKILL_READ_ONLY)", async () => {
    const onSaved = vi.fn()
    const onConflict = vi.fn()
    vi.mocked(writeSkillFile).mockRejectedValueOnce(readOnlySkillError())

    await expect(saveMonacoDraft({
      skillId: "bundled-skill",
      workspaceRoot: "/Users/sevenx/Projects/bundled-skill",
      filePath: "SKILL.md",
      content: "# Local\n",
      savedContent: "# Original\n",
      currentHash: "original-hash",
      onSaved,
      onConflict,
    })).resolves.toEqual({ status: "read_only" })

    // A read-only refusal is neither a save nor a hash conflict.
    expect(onSaved).not.toHaveBeenCalled()
    expect(onConflict).not.toHaveBeenCalled()
  })

  it("maps hash conflicts into the Monaco conflict payload", async () => {
    const onConflict = vi.fn()
    vi.mocked(writeSkillFile).mockRejectedValueOnce(hashConflictError({
      current_hash: "remote-hash",
      current_markdown_content: "# Remote\n",
    }))

    await expect(saveMonacoDraft({
      skillId: "writer-smoke",
      workspaceRoot: "/Users/sevenx/Projects/writer-smoke",
      filePath: "SKILL.md",
      content: "# Local\n",
      savedContent: "# Original\n",
      currentHash: "original-hash",
      onSaved: vi.fn(),
      onConflict,
    })).resolves.toEqual({ status: "conflict" })

    expect(onConflict).toHaveBeenCalledWith({
      skillId: "writer-smoke",
      path: "SKILL.md",
      localContent: "# Local\n",
      remoteContent: "# Remote\n",
      remoteHash: "remote-hash",
    })
  })
})

function hashConflictError(data: Record<string, unknown>): AxiosError {
  const config = { headers: {} } as InternalAxiosRequestConfig
  const response: AxiosResponse = {
    data,
    status: 409,
    statusText: "Conflict",
    headers: {},
    config,
  }
  return new AxiosError("Hash conflict", "ERR_BAD_RESPONSE", config, null, response)
}

function readOnlySkillError(): AxiosError {
  const config = { headers: {} } as InternalAxiosRequestConfig
  const response: AxiosResponse = {
    data: { error_code: "SKILL_READ_ONLY", message: "Skill is read-only" },
    status: 403,
    statusText: "Forbidden",
    headers: {},
    config,
  }
  return new AxiosError("Read only", "ERR_BAD_REQUEST", config, null, response)
}
