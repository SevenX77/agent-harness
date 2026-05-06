import { useEffect, useMemo, useState } from 'react'
import type { RefObject } from 'react'

interface VirtualScrollConfig {
  itemCount: number
  itemHeight: number
  overscan?: number
}

interface VirtualScrollWindow {
  startIdx: number
  endIdx: number
  totalHeight: number
  offsetTop: number
}

export function useVirtualScroll(
  viewportRef: RefObject<HTMLElement | null>,
  { itemCount, itemHeight, overscan = 8 }: VirtualScrollConfig,
): VirtualScrollWindow {
  const [viewportHeight, setViewportHeight] = useState(0)
  const [scrollTop, setScrollTop] = useState(0)

  useEffect(() => {
    const viewport = viewportRef.current
    if (!viewport) {
      return
    }

    const updateViewport = () => {
      setViewportHeight(viewport.clientHeight)
      setScrollTop(viewport.scrollTop)
    }

    updateViewport()
    viewport.addEventListener('scroll', updateViewport, { passive: true })
    window.addEventListener('resize', updateViewport)
    return () => {
      viewport.removeEventListener('scroll', updateViewport)
      window.removeEventListener('resize', updateViewport)
    }
  }, [viewportRef])

  return useMemo(() => {
    const safeItemHeight = Math.max(1, itemHeight)
    const totalHeight = itemCount * safeItemHeight
    const visibleCount = Math.ceil(viewportHeight / safeItemHeight)
    const firstVisible = Math.floor(scrollTop / safeItemHeight)
    const startIdx = Math.max(0, firstVisible - overscan)
    const endIdx = Math.min(itemCount, firstVisible + visibleCount + overscan + 1)

    return {
      startIdx,
      endIdx,
      totalHeight,
      offsetTop: startIdx * safeItemHeight,
    }
  }, [itemCount, itemHeight, overscan, scrollTop, viewportHeight])
}
