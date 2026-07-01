import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type DragEvent,
  type PointerEvent as ReactPointerEvent,
  type RefObject,
} from "react"
import { AVAILABLE_MODEL_DRAG_TYPE } from "./role-utils"

interface AvailableModelPointerDrag {
  dragging: boolean
  previewVisible: boolean
  modelId: string
  startX: number
  startY: number
}

export interface AvailableModelDragPreviewState {
  dragging: true
  modelId: string
  label: string
  x: number
  y: number
}

export function useAvailableModelPointerDrag({
  getPreviewLabel,
  onDrop,
}: {
  getPreviewLabel: (modelId: string) => string
  onDrop: (drop: { modelId: string; target: Element | null }) => void
}) {
  const activeAvailableModelDragRef = useRef<string | null>(null)
  const availableModelPointerDragRef = useRef<AvailableModelPointerDrag | null>(null)
  const availableModelDragPreviewNodeRef = useRef<HTMLDivElement | null>(null)
  const availableModelDragPreviewFrameRef = useRef<number | null>(null)
  const availableModelDragPreviewPointRef = useRef<{ x: number; y: number } | null>(null)
  const suppressAvailableModelDragClickRef = useRef(false)
  const availableModelDragReleaseTimerRef = useRef<number | null>(null)
  const getPreviewLabelRef = useRef(getPreviewLabel)
  const onDropRef = useRef(onDrop)
  const [availableModelDragPreview, setAvailableModelDragPreview] = useState<AvailableModelDragPreviewState | null>(null)

  getPreviewLabelRef.current = getPreviewLabel
  onDropRef.current = onDrop

  const handleAvailableModelPointerDown = useCallback((
    modelId: string,
    event: ReactPointerEvent<HTMLButtonElement>,
  ) => {
    if (event.button !== 0) return
    activeAvailableModelDragRef.current = modelId
    availableModelPointerDragRef.current = {
      dragging: false,
      previewVisible: false,
      modelId,
      startX: event.clientX,
      startY: event.clientY,
    }
    try {
      event.currentTarget.setPointerCapture(event.pointerId)
    } catch {
      // Pointer capture is a progressive enhancement; window listeners handle the fallback.
    }
  }, [])

  const updateAvailableModelDragPreviewPosition = useCallback((x: number, y: number) => {
    availableModelDragPreviewPointRef.current = { x, y }
    if (availableModelDragPreviewFrameRef.current !== null) return

    availableModelDragPreviewFrameRef.current = window.requestAnimationFrame(() => {
      availableModelDragPreviewFrameRef.current = null
      const point = availableModelDragPreviewPointRef.current
      availableModelDragPreviewPointRef.current = null
      const node = availableModelDragPreviewNodeRef.current
      if (!point || !node) return
      node.style.transform = availableModelDragPreviewTransform(point.x, point.y)
    })
  }, [])

  useEffect(() => {
    const movementThreshold = 6

    function clearDragClickSuppression() {
      suppressAvailableModelDragClickRef.current = false
      if (availableModelDragReleaseTimerRef.current !== null) {
        window.clearTimeout(availableModelDragReleaseTimerRef.current)
        availableModelDragReleaseTimerRef.current = null
      }
    }

    function releaseDragUi() {
      document.documentElement.removeAttribute("data-available-model-dragging")
    }

    function releaseDragPreview({ clearState = true }: { clearState?: boolean } = {}) {
      if (clearState) {
        setAvailableModelDragPreview(null)
      }
      availableModelDragPreviewPointRef.current = null
      if (availableModelDragPreviewFrameRef.current !== null) {
        window.cancelAnimationFrame(availableModelDragPreviewFrameRef.current)
        availableModelDragPreviewFrameRef.current = null
      }
    }

    function scheduleDragSuppressionRelease() {
      suppressAvailableModelDragClickRef.current = true
      if (availableModelDragReleaseTimerRef.current !== null) {
        window.clearTimeout(availableModelDragReleaseTimerRef.current)
      }
      availableModelDragReleaseTimerRef.current = window.setTimeout(() => {
        clearDragClickSuppression()
      }, 1000)
    }

    function clearPointerDrag({ suppressClick = false }: { suppressClick?: boolean } = {}) {
      activeAvailableModelDragRef.current = null
      availableModelPointerDragRef.current = null
      releaseDragPreview()
      releaseDragUi()
      if (suppressClick) {
        scheduleDragSuppressionRelease()
      } else {
        clearDragClickSuppression()
      }
    }

    function handlePointerMove(event: PointerEvent) {
      const drag = availableModelPointerDragRef.current
      if (!drag) return
      const distance = Math.hypot(event.clientX - drag.startX, event.clientY - drag.startY)
      if (distance >= movementThreshold) {
        drag.dragging = true
        document.documentElement.dataset.availableModelDragging = "true"
      }
      if (drag.dragging) {
        if (!drag.previewVisible) {
          drag.previewVisible = true
          setAvailableModelDragPreview({
            dragging: true,
            modelId: drag.modelId,
            label: getPreviewLabelRef.current(drag.modelId),
            x: event.clientX,
            y: event.clientY,
          })
        } else {
          updateAvailableModelDragPreviewPosition(event.clientX, event.clientY)
        }
        event.preventDefault()
      }
    }

    function handlePointerUp(event: PointerEvent) {
      const drag = availableModelPointerDragRef.current
      if (!drag?.dragging) {
        clearPointerDrag()
        return
      }

      const target = document.elementFromPoint(event.clientX, event.clientY)
      event.preventDefault()
      event.stopPropagation()
      clearPointerDrag({ suppressClick: true })
      onDropRef.current({
        modelId: drag.modelId,
        target: target instanceof Element ? target : null,
      })
    }

    function handleClickCapture(event: MouseEvent) {
      if (!suppressAvailableModelDragClickRef.current) return
      event.preventDefault()
      event.stopPropagation()
      event.stopImmediatePropagation()
      clearDragClickSuppression()
    }

    function handlePointerCancel() {
      clearPointerDrag()
    }

    window.addEventListener("pointermove", handlePointerMove, { passive: false })
    window.addEventListener("pointerup", handlePointerUp)
    window.addEventListener("pointercancel", handlePointerCancel)
    window.addEventListener("click", handleClickCapture, true)
    return () => {
      window.removeEventListener("pointermove", handlePointerMove)
      window.removeEventListener("pointerup", handlePointerUp)
      window.removeEventListener("pointercancel", handlePointerCancel)
      window.removeEventListener("click", handleClickCapture, true)
      releaseDragUi()
      releaseDragPreview({ clearState: false })
      clearDragClickSuppression()
    }
  }, [updateAvailableModelDragPreviewPosition])

  const getActiveAvailableModelDragId = useCallback(
    () => activeAvailableModelDragRef.current,
    [],
  )

  return {
    availableModelDragPreview,
    availableModelDragPreviewNodeRef,
    getActiveAvailableModelDragId,
    handleAvailableModelPointerDown,
  }
}

export function AvailableModelDragPreview({
  drag,
  nodeRef,
}: {
  drag: AvailableModelDragPreviewState | null
  nodeRef: RefObject<HTMLDivElement | null>
}) {
  if (!drag?.dragging) return null

  return (
    <div
      ref={nodeRef}
      data-available-model-drag-preview="true"
      data-preview-update-mode="imperative-transform"
      aria-hidden="true"
      className="pointer-events-none fixed left-0 top-0 z-50 max-w-72 select-none rounded-md border border-border bg-popover px-3 py-2 text-left shadow-lg ring-2 ring-primary/40"
      style={{
        transform: availableModelDragPreviewTransform(drag.x, drag.y),
      }}
    >
      <div className="truncate text-xs font-medium text-foreground">{drag.label}</div>
    </div>
  )
}

export function availableModelDragPreviewTransform(x: number, y: number): string {
  return `translate3d(${x}px, ${y}px, 0) translate(-50%, -50%)`
}

export function handleAvailableModelDragOver(event: DragEvent<HTMLElement>) {
  event.preventDefault()
  event.stopPropagation()
  event.dataTransfer.dropEffect = "copy"
}

export function readAvailableModelDropId(
  event: DragEvent<HTMLElement>,
  getActiveAvailableModelDragId: () => string | null,
): string | null {
  event.preventDefault()
  event.stopPropagation()
  return event.dataTransfer.getData(AVAILABLE_MODEL_DRAG_TYPE) ||
    event.dataTransfer.getData("text/plain") ||
    getActiveAvailableModelDragId()
}
