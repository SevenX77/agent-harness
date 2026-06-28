import { Children, isValidElement, type ReactElement, type ReactNode } from "react"
import { describe, expect, it, vi } from "vitest"
import { ConflictDialog } from "./ConflictDialog"
import type { SaveConflict } from "./WorkspaceContext"

const conflict: SaveConflict = {
  skillId: "writer-smoke",
  path: "phases/draft/SKILL.md",
  side: "left",
  localContent: "local draft\n",
  remoteContent: "remote draft\n",
  remoteHash: "remote-hash",
}

describe("ConflictDialog", () => {
  it("shows Overwrite/Retry Save and wires it to the retry callback", () => {
    const onOverwriteRetry = vi.fn()
    const tree = ConflictDialog({
      conflict,
      onKeepLocal: vi.fn(),
      onUseRemote: vi.fn(),
      onViewDiff: vi.fn(),
      onOverwriteRetry,
    })

    buttonPropsByText(tree, "Overwrite/Retry Save").onClick()

    expect(onOverwriteRetry).toHaveBeenCalledTimes(1)
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
