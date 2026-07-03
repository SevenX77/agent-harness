import { useLayoutEffect, useRef, type CSSProperties } from 'react'
import { FAB_SIZE, travelSteps, type Point, type Rect } from './copilot-fab-geometry'
import { MoiraiMark } from './moirai-mark'

interface CopilotPanelMorphProps {
  mode: 'open' | 'close'
  /** FAB circle top-left (canvas-host coords) — where the circle sits/returns. */
  fab: Point
  /** Header-logo landing spot (top-left) — the corner the open box grows from. */
  logo: Point
  /** The fully-expanded panel rect the circle grows into. */
  panel: Rect
  onFinish: () => void
}

// PM r4 tuning:
//  · OPEN — the L-path travel felt too fast and the grow-into-panel too slow, so
//    the split sits LATE (travel owns ~0.64 of the timeline, grow the rest) and
//    the grow uses a quick-settle ease. The circle still becomes the panel.
//  · CLOSE — no L-path detour: the panel shrinks STRAIGHT back to the FAB
//    (PM「收直接收到 button，不用像打开那样走一圈」), and shorter + ease-in so it
//    feels crisp (PM「收的动画再利落一点」).
const OPEN_DURATION = 560
const CLOSE_DURATION = 300
const TRAVEL_EASING = 'cubic-bezier(0.4, 0, 0.2, 1)'
// Snappy decelerate — the grow leaps then settles softly into the panel.
const GROW_EASING = 'cubic-bezier(0.2, 0, 0, 1)'
// Ease-in — the panel accelerates away into the circle, reads as decisive.
const CLOSE_EASING = 'cubic-bezier(0.4, 0, 1, 1)'
const RADIUS = FAB_SIZE / 2
const PANEL_RADIUS = 10

function prefersReducedMotion(): boolean {
  return (
    typeof window !== 'undefined' &&
    typeof window.matchMedia === 'function' &&
    window.matchMedia('(prefers-reduced-motion: reduce)').matches
  )
}

function circleFrame(p: Point, offset: number, easing?: string): Keyframe {
  const frame: Keyframe = {
    left: `${p.x}px`,
    top: `${p.y}px`,
    width: `${FAB_SIZE}px`,
    height: `${FAB_SIZE}px`,
    borderRadius: `${RADIUS}px`,
    offset,
  }
  if (easing) frame.easing = easing
  return frame
}

function panelFrame(panel: Rect, offset: number, easing?: string): Keyframe {
  const frame: Keyframe = {
    left: `${panel.left}px`,
    top: `${panel.top}px`,
    width: `${panel.width}px`,
    height: `${panel.height}px`,
    borderRadius: `${PANEL_RADIUS}px`,
    offset,
  }
  if (easing) frame.easing = easing
  return frame
}

/**
 * The container-transform between the canvas FAB and the copilot panel. A single
 * empty panel-surface box carries the morph:
 *  · open  — fly the FAB's L-path to the header-logo spot, then GROW into the
 *    full panel rect (one continuous WAAPI motion), so the circle literally
 *    becomes the panel instead of the FAB fading out while a panel fades in.
 *  · close — shrink STRAIGHT from the panel rect back to the FAB circle (no
 *    L-path), shorter and ease-in so it feels crisp.
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
    let boxFrames: Keyframe[]
    let markFrames: Keyframe[]
    let duration: number
    if (mode === 'open') {
      const [p0, p1, p2] = travelSteps(fab, logo) // fab → straight up → across to logo
      boxFrames = [
        circleFrame(p0, 0, TRAVEL_EASING),
        circleFrame(p1, 0.34, TRAVEL_EASING),
        circleFrame(p2, 0.64, GROW_EASING),
        panelFrame(panel, 1),
      ]
      // The mark rides the circle through the travel, then fades as the grow starts.
      markFrames = [
        { opacity: 1, offset: 0 },
        { opacity: 1, offset: 0.64 },
        { opacity: 0, offset: 0.76 },
        { opacity: 0, offset: 1 },
      ]
      duration = OPEN_DURATION
    } else {
      // Straight diagonal shrink: panel → FAB, no logo waypoint, no L-path.
      boxFrames = [panelFrame(panel, 0, CLOSE_EASING), circleFrame(fab, 1)]
      // The mark fades back in only once the box is nearly circle-sized again.
      markFrames = [
        { opacity: 0, offset: 0 },
        { opacity: 0, offset: 0.55 },
        { opacity: 1, offset: 1 },
      ]
      duration = CLOSE_DURATION
    }
    const options: KeyframeAnimationOptions = { duration, fill: 'forwards' }
    const boxAnim = el.animate(boxFrames, options)
    const markAnim = markRef.current?.animate(markFrames, options)
    boxAnim.onfinish = onFinish
    return () => {
      // A dev/StrictMode remount cancels this first run. Cancel SILENTLY — do
      // NOT route cancel to onFinish, or the panel would flip before the box
      // finishes (the remounted run drives the real onFinish).
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
      : { left: panel.left, top: panel.top, width: panel.width, height: panel.height, borderRadius: PANEL_RADIUS }

  return (
    <div
      ref={boxRef}
      aria-hidden
      className="studio-right-panel-overlay pointer-events-none absolute z-30 flex items-center justify-center overflow-hidden"
      style={startStyle}
    >
      <div
        ref={markRef}
        className="flex size-9 shrink-0 items-center justify-center"
        style={{ opacity: mode === 'open' ? 1 : 0 }}
      >
        <MoiraiMark className="size-5 text-[color:var(--studio-canvas-accent-strong)]" />
      </div>
    </div>
  )
}
