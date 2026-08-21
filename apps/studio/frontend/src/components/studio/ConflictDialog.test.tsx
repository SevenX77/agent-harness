import { Children, isValidElement, type ReactElement, type ReactNode } from "react"
import { describe, expect, it, vi } from "vitest"
import { ConflictDialog } from "./ConflictDialog"
import { CONFLICT_TITLE, CONFLICT_VERB } from "./conflict-vocabulary"
import type { SaveConflict } from "./WorkspaceContext"

const conflict: SaveConflict = {
  skillId: "writer-smoke",
  path: "phases/draft/SKILL.md",
  side: "left",
  localContent: "local draft\n",
  remoteContent: "remote draft\n",
  remoteHash: "remote-hash",
}

function renderConflictDialog(overrides: Partial<Parameters<typeof ConflictDialog>[0]> = {}) {
  return ConflictDialog({
    conflict,
    onCancel: vi.fn(),
    onUseRemote: vi.fn(),
    onViewDiff: vi.fn(),
    onOverwriteRetry: vi.fn(),
    ...overrides,
  })
}

describe("ConflictDialog", () => {
  it("wires the overwrite verb to the retry callback", () => {
    const onOverwriteRetry = vi.fn()

    buttonPropsByText(renderConflictDialog({ onOverwriteRetry }), CONFLICT_VERB.overwrite).onClick()

    expect(onOverwriteRetry).toHaveBeenCalledTimes(1)
  })

  it("wires the cancel verb to closing the conflict without writing", () => {
    const onCancel = vi.fn()

    buttonPropsByText(renderConflictDialog({ onCancel }), CONFLICT_VERB.cancel).onClick()

    expect(onCancel).toHaveBeenCalledTimes(1)
  })

  it("spells its actions and its title with the shared conflict vocabulary", () => {
    const tree = renderConflictDialog()

    for (const verb of Object.values(CONFLICT_VERB)) {
      expect(findElementByText(tree, verb)).toBeTruthy()
    }
    expect(textContent(tree)).toContain(CONFLICT_TITLE.fileSave)
  })
})

function buttonPropsByText(
  node: ReactNode,
  label: string,
): { onClick: () => void } {
  const found = findElementByText(node, label)
  expect(found).toBeTruthy()
  expect(found?.props.onClick).toBeTypeOf("function")
  return found?.props as { onClick: () => void }
}

function textContent(node: ReactNode): string {
  if (Array.isArray(node)) return node.map(textContent).join("")
  if (typeof node === "string" || typeof node === "number") return String(node)
  if (isValidElement<{ children?: ReactNode }>(node)) return textContent(node.props.children)
  return ""
}

function findElementByText(node: ReactNode, label: string): ReactElement<{ children?: ReactNode; onClick?: () => void }> | null {
  if (!isValidElement<{ children?: ReactNode }>(node)) {
    return null
  }
  if (node.props.children === label) {
    return node as ReactElement<{ children?: ReactNode; onClick?: () => void }>
  }
  for (const child of Children.toArray(node.props.children)) {
    const found = findElementByText(child, label)
    if (found) {
      return found
    }
  }
  return null
}
