import { renderToStaticMarkup } from "react-dom/server"
import { describe, expect, it, vi } from "vitest"
import { DeleteConfirmDialog } from "./delete-confirm-dialog"

// R6-2: the delete confirmation is a controlled Radix AlertDialog rendered
// inside the component tree (never a body-level toast that dismissed the parent
// Settings modal). These SSR checks lock the closed/open request contract.
describe("DeleteConfirmDialog", () => {
  it("renders nothing when there is no pending request", () => {
    const html = renderToStaticMarkup(
      <DeleteConfirmDialog request={null} onOpenChange={() => undefined} />,
    )

    expect(html).toBe("")
  })

  // NB: the open dialog body renders through a Radix Portal, which SSR
  // (renderToStaticMarkup) does not emit — the open title/description/actions
  // are verified live (Phase 4), not here. This file only locks the pure
  // closed / no-side-effect contract.
  it("does not run onConfirm just by rendering", () => {
    const onConfirm = vi.fn()

    renderToStaticMarkup(
      <DeleteConfirmDialog
        request={{ title: "Delete?", description: "Gone forever.", onConfirm }}
        onOpenChange={() => undefined}
      />,
    )

    expect(onConfirm).not.toHaveBeenCalled()
  })
})
