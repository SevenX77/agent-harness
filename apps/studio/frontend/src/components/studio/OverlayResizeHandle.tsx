import { useCallback, type PointerEvent as ReactPointerEvent } from "react"

type ResizeSide = "left" | "right" | "bottom"

interface OverlayResizeHandleProps {
  /** Which edge of the parent overlay this handle sits on (and resizes). */
  side: ResizeSide
  min: number
  max: number
  /** Called with the new size (px) of the resized dimension during the drag. */
  onResize: (sizePx: number) => void
  ariaLabel: string
}

/**
 * A thin drag handle for resizing a positioned overlay (left panel / copilot /
 * editor). It measures its parent element's current size on drag start, so the
 * first drag works whether the size comes from CSS defaults or React state. The
 * size value is owned by the host; this only reports the clamped pixel size.
 */
export function OverlayResizeHandle({ side, min, max, onResize, ariaLabel }: OverlayResizeHandleProps) {
  const onPointerDown = useCallback(
    (event: ReactPointerEvent<HTMLDivElement>) => {
      if (event.button !== 0) return
      const host = event.currentTarget.parentElement
      if (!host) return
      event.preventDefault()
      event.stopPropagation()
      const horizontal = side !== "bottom"
      const rect = host.getBoundingClientRect()
      const startSize = horizontal ? rect.width : rect.height
      const startPos = horizontal ? event.clientX : event.clientY
      // Right/bottom edges grow as the pointer moves +; the left edge grows as it moves −.
      const direction = side === "left" ? -1 : 1
      const clamp = (value: number) => Math.min(max, Math.max(min, value))
      const onMove = (moveEvent: globalThis.PointerEvent) => {
        const current = horizontal ? moveEvent.clientX : moveEvent.clientY
        onResize(clamp(startSize + direction * (current - startPos)))
      }
      const onUp = () => {
        window.removeEventListener("pointermove", onMove)
        window.removeEventListener("pointerup", onUp)
        document.body.style.removeProperty("user-select")
        document.body.style.removeProperty("cursor")
      }
      document.body.style.userSelect = "none"
      document.body.style.cursor = horizontal ? "ew-resize" : "ns-resize"
      window.addEventListener("pointermove", onMove)
      window.addEventListener("pointerup", onUp)
    },
    [max, min, onResize, side],
  )

  const positionClass = {
    right: "right-0 top-0 h-full w-1.5 cursor-ew-resize",
    left: "left-0 top-0 h-full w-1.5 cursor-ew-resize",
    bottom: "bottom-0 left-0 h-1.5 w-full cursor-ns-resize",
  }[side]

  return (
    <div
      role="separator"
      aria-label={ariaLabel}
      aria-orientation={side === "bottom" ? "horizontal" : "vertical"}
      onPointerDown={onPointerDown}
      // z-50 so the handle stays grabbable above overlay content that creates its
      // own stacking context (e.g. the Copilot panel's z-copilot/40 <aside>).
      className={`absolute z-50 touch-none bg-transparent transition-colors hover:bg-primary/40 ${positionClass}`}
    />
  )
}
