import { useLayoutEffect, useRef, useState, type PointerEvent as ReactPointerEvent } from 'react'
import { cn } from '@/lib/utils'
import { MoiraiMark } from './moirai-mark'
import {
  clampFabPosition,
  defaultFabPosition,
  FAB_SIZE,
  headerLogoTarget,
  isTapGesture,
  travelSteps,
  type Point,
  type Size,
} from './copilot-fab-geometry'

interface CopilotFabProps {
  /** Persisted position (canvas-host coords); null = default top-right anchor. */
  position: Point | null
  onPositionChange: (p: Point) => void
  /** Open panel width — the FAB flies to that panel's header-logo spot. */
  panelWidth: number
  /** Called once the open-travel animation lands on the header logo. */
  onOpen: () => void
}

function prefersReducedMotion(): boolean {
  return (
    typeof window !== 'undefined' &&
    typeof window.matchMedia === 'function' &&
    window.matchMedia('(prefers-reduced-motion: reduce)').matches
  )
}

/**
 * Draggable canvas button that opens the collapsed copilot panel. It looks like
 * the panel's header logo detached onto the canvas (same surface + accent), can
 * be dragged anywhere inside the canvas, and on tap flies up-then-across to the
 * header-logo spot before the panel unfolds from there.
 */
export function CopilotFab({ position, onPositionChange, panelWidth, onOpen }: CopilotFabProps) {
  const rootRef = useRef<HTMLDivElement>(null)
  const [bounds, setBounds] = useState<Size | null>(null)
  const [traveling, setTraveling] = useState(false)
  const dragRef = useRef<{ pointer: Point; origin: Point; moved: boolean } | null>(null)
  const justDraggedRef = useRef(false)

  // Track the canvas-host size (the positioned offsetParent) for default anchor,
  // drag clamping, and the fly-to-logo target.
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
    if (traveling) return
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

  const openWithTravel = () => {
    if (justDraggedRef.current) {
      justDraggedRef.current = false
      return
    }
    const el = rootRef.current
    if (!bounds || !el || prefersReducedMotion() || typeof el.animate !== 'function') {
      onOpen()
      return
    }
    const from = effective
    const to = headerLogoTarget(bounds, panelWidth)
    const frames = travelSteps(from, to).map((s) => ({
      transform: `translate(${s.x - from.x}px, ${s.y - from.y}px)`,
    }))
    setTraveling(true)
    const anim = el.animate(frames, { duration: 440, easing: 'cubic-bezier(0.4, 0, 0.2, 1)', fill: 'forwards' })
    anim.onfinish = () => onOpen()
    anim.oncancel = () => setTraveling(false)
  }

  return (
    <div
      ref={rootRef}
      className={cn('absolute z-30 touch-none', traveling && 'pointer-events-none')}
      style={{ left: effective.x, top: effective.y, visibility: bounds ? 'visible' : 'hidden' }}
    >
      <button
        type="button"
        aria-label="打开 MoirAI"
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        onClick={openWithTravel}
        style={{ width: FAB_SIZE, height: FAB_SIZE, background: 'var(--studio-canvas-surface)' }}
        className={cn(
          'flex cursor-grab items-center justify-center rounded-full border-0 shadow-md',
          'transition-shadow hover:shadow-lg active:cursor-grabbing',
          'motion-safe:animate-in motion-safe:fade-in-0 motion-safe:zoom-in-90 motion-safe:duration-200',
          'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[color:var(--studio-canvas-accent)]',
        )}
      >
        <MoiraiMark className="size-5 text-[color:var(--studio-canvas-accent)]" title="打开 MoirAI" />
      </button>
    </div>
  )
}
