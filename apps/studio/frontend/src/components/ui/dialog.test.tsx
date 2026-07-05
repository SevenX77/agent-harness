// @vitest-environment jsdom
import { act } from "react"
import { createRoot } from "react-dom/client"
import { afterEach, describe, expect, it } from "vitest"
import { Dialog, DialogContent, DialogTitle } from "./dialog"

;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true

describe("DialogContent", () => {
  afterEach(() => {
    document.body.replaceChildren()
  })

  it("hides force-mounted closed content so inactive dialogs cannot block the app", () => {
    const container = document.createElement("div")
    document.body.appendChild(container)
    const root = createRoot(container)

    act(() => {
      root.render(
        <Dialog open={false}>
          <DialogContent forceMount>
            <DialogTitle>Hidden dialog</DialogTitle>
          </DialogContent>
        </Dialog>,
      )
    })

    const content = document.querySelector('[data-slot="dialog-content"]')
    expect(content).not.toBeNull()
    expect(content?.className).toContain("data-closed:hidden")

    act(() => {
      root.unmount()
    })
  })
})
