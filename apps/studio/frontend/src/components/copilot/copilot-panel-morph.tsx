import { useLayoutEffect, useRef, type CSSProperties } from 'react'
import { FAB_SIZE, travelSteps, type Point, type Rect } from './copilot-fab-geometry'
import { MoiraiMark } from './moirai-mark'

interface CopilotPanelMorphProps {
  mode: 'open' | 'close'
  /** FAB circle top-left (canvas-host coords) — where the circle sits/returns. */
  fab: Point
  /** Header-logo landing spot (top-left) — the corner the box grows from. */
  logo: Point
  /** The fully-expanded panel rect the circle grows into. */
  panel: Rect
  onFinish: () => void
}

const DURATION = 560
// Decelerate into place — the grow settles softly at the end.
const EASING = 'cubic-bezier(0.33, 0, 0.15, 1)'
const RADIUS = FAB_SIZE / 2

function prefersReducedMotion(): boolean {
  return (
    typeof window !== 'undefined' &&
    typeof window.matchMedia === 'function' &&
    window.matchMedia('(prefers-reduced-motion: reduce)').matches
  )
}

/**
 * The container-transform between the canvas FAB and the copilot panel. A single
 * empty panel-surface box travels the FAB's L-path to the header-logo spot and
 * then GROWS (left/top/width/height/border-radius, one continuous WAAPI motion)
 * into the full panel rect — so the circle literally becomes the panel instead
 * of the FAB fading out while a separate panel fades in. Reversed for `close`.
 */
export function CopilotPanelMorph({ mode, fab, logo, panel, onFinish }: CopilotPanelMorphProps) {
  const boxRef = useRef<HTMLDivElement>(null)
  const markRef = useRef<HTMLDivElement>(null)

  useLayoutEffect(() => {
    const el = boxRef.current
    if (!el || typeof el.animate !== 'function' || prefersReducedMotion()) {
      onFinish()
      return
    }
    const [p0, p1, p2] = travelSteps(fab, logo) // fab → straight up → across to logo
    const boxFrames: Keyframe[] = [
      { left: `${p0.x}px`, top: `${p0.y}px`, width: `${FAB_SIZE}px`, height: `${FAB_SIZE}px`, borderRadius: `${RADIUS}px`, offset: 0 },
      { left: `${p1.x}px`, top: `${p1.y}px`, width: `${FAB_SIZE}px`, height: `${FAB_SIZE}px`, borderRadius: `${RADIUS}px`, offset: 0.28 },
      { left: `${p2.x}px`, top: `${p2.y}px`, width: `${FAB_SIZE}px`, height: `${FAB_SIZE}px`, borderRadius: `${RADIUS}px`, offset: 0.5 },
      { left: `${panel.left}px`, top: `${panel.top}px`, width: `${panel.width}px`, height: `${panel.height}px`, borderRadius: '10px', offset: 1 },
    ]
    // The mark rides the circle, then fades as the box begins to grow.
    const markFrames: Keyframe[] = [
      { opacity: 1, offset: 0 },
      { opacity: 1, offset: 0.5 },
      { opacity: 0, offset: 0.66 },
      { opacity: 0, offset: 1 },
    ]
    const options: KeyframeAnimationOptions = {
      duration: DURATION,
      easing: EASING,
      fill: 'forwards',
      direction: mode === 'close' ? 'reverse' : 'normal',
    }
    const boxAnim = el.animate(boxFrames, options)
    const markAnim = markRef.current?.animate(markFrames, options)
    boxAnim.onfinish = onFinish
    return () => {
      // A dev/StrictMode remount cancels this first run. Cancel SILENTLY — do
      // NOT route cancel to onFinish, or the panel would open before the box
      // finishes growing (the remounted run drives the real onFinish).
      boxAnim.cancel()
      markAnim?.cancel()
    }
    // Run once for this morph instance; a new morph gets a fresh mount.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // Start style matches the animation's first applied frame so there is no flash
  // before WAAPI takes over: the circle for open, the full panel for close.
  const startStyle: CSSProperties =
    mode === 'open'
      ? { left: fab.x, top: fab.y, width: FAB_SIZE, height: FAB_SIZE, borderRadius: RADIUS }
      : { left: panel.left, top: panel.top, width: panel.width, height: panel.height, borderRadius: 10 }

  return (
    <div
      ref={boxRef}
      aria-hidden
      className="studio-right-panel-overlay pointer-events-none absolute z-30 flex items-center justify-center overflow-hidden"
      style={startStyle}
    >
      <div ref={markRef} className="flex size-9 shrink-0 items-center justify-center">
        <MoiraiMark className="size-5 text-[color:var(--studio-canvas-accent)]" />
      </div>
    </div>
  )
}
