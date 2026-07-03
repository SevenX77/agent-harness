import { useLayoutEffect, useRef, useState, type PointerEvent as ReactPointerEvent } from 'react'
import { cn } from '@/lib/utils'
import { MoiraiMark } from './moirai-mark'
import {
  clampFabPosition,
  defaultFabPosition,
  FAB_SIZE,
  isTapGesture,
  type Point,
  type Size,
} from './copilot-fab-geometry'

interface CopilotFabProps {
  /** Persisted position (canvas-host coords); null = default top-right anchor. */
  position: Point | null
  onPositionChange: (p: Point) => void
  /** Tap → open. Reports the FAB's current top-left so the morph starts there. */
  onOpen: (from: Point) => void
}

/**
 * Draggable canvas button that opens the collapsed copilot panel. It looks like
 * the panel's header logo detached onto the canvas (same surface + accent) and
 * can be dragged anywhere inside the canvas. On tap it hands its position to the
 * container-transform morph (see copilot-panel-morph.tsx), which grows the circle
 * into the panel — so this component owns drag + hit-testing, not the animation.
 */
export function CopilotFab({ position, onPositionChange, onOpen }: CopilotFabProps) {
  const rootRef = useRef<HTMLDivElement>(null)
  const [bounds, setBounds] = useState<Size | null>(null)
  const dragRef = useRef<{ pointer: Point; origin: Point; moved: boolean } | null>(null)
  const justDraggedRef = useRef(false)

  // Track the canvas-host size (the positioned offsetParent) for the default
  // anchor and drag clamping.
  useLayoutEffect(() => {
    const host = rootRef.current?.offsetParent as HTMLElement | null
    if (!host) return
    const measure = () => setBounds({ width: host.clientWidth, height: host.clientHeight })
    measure()
    if (typeof ResizeObserver === 'undefined') return
    const ro = new ResizeObserver(measure)
    ro.observe(host)
    return () => ro.disconnect()
  }, [])

  const effective = position ?? (bounds ? defaultFabPosition(bounds) : { x: 0, y: 0 })

  const onPointerDown = (e: ReactPointerEvent<HTMLButtonElement>) => {
    dragRef.current = { pointer: { x: e.clientX, y: e.clientY }, origin: effective, moved: false }
    e.currentTarget.setPointerCapture(e.pointerId)
  }

  const onPointerMove = (e: ReactPointerEvent<HTMLButtonElement>) => {
    const d = dragRef.current
    if (!d || !bounds) return
    const dx = e.clientX - d.pointer.x
    const dy = e.clientY - d.pointer.y
    if (!d.moved && isTapGesture(d.pointer, { x: e.clientX, y: e.clientY })) return
    d.moved = true
    onPositionChange(clampFabPosition({ x: d.origin.x + dx, y: d.origin.y + dy }, bounds))
  }

  const onPointerUp = (e: ReactPointerEvent<HTMLButtonElement>) => {
    const d = dragRef.current
    dragRef.current = null
    e.currentTarget.releasePointerCapture?.(e.pointerId)
    // A drag just happened → suppress the click that follows so it doesn't open.
    justDraggedRef.current = Boolean(d?.moved)
  }

  const onClick = () => {
    if (justDraggedRef.current) {
      justDraggedRef.current = false
      return
    }
    onOpen(effective)
  }

  return (
    <div
      ref={rootRef}
      className="absolute z-30 touch-none"
      style={{ left: effective.x, top: effective.y, visibility: bounds ? 'visible' : 'hidden' }}
    >
      <button
        type="button"
        aria-label="打开 MoirAI"
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        onClick={onClick}
        style={{ width: FAB_SIZE, height: FAB_SIZE, background: 'var(--studio-canvas-surface)' }}
        className={cn(
          'flex cursor-grab items-center justify-center rounded-full border-0 shadow-md',
          'transition-shadow hover:shadow-lg active:cursor-grabbing',
          'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[color:var(--studio-canvas-accent)]',
        )}
      >
        <MoiraiMark className="size-5 text-[color:var(--studio-canvas-accent-strong)]" title="打开 MoirAI" />
      </button>
    </div>
  )
}
