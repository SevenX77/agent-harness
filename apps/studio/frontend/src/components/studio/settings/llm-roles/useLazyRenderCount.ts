import { useCallback, useEffect, useRef, useState } from "react"

export function useLazyRenderCount({
  total,
  initialCount,
  step,
  resetKey,
}: {
  total: number
  initialCount: number
  step: number
  resetKey: string
}) {
  const [visibleCount, setVisibleCount] = useState(() => Math.min(total, initialCount))
  const sentinelRef = useRef<HTMLDivElement | null>(null)
  const hasMore = visibleCount < total
  const loadMore = useCallback(() => {
    setVisibleCount((current) => Math.min(total, current + step))
  }, [step, total])

  useEffect(() => {
    setVisibleCount(Math.min(total, initialCount))
  }, [initialCount, resetKey, total])

  useEffect(() => {
    if (!hasMore || typeof IntersectionObserver === "undefined") return
    const sentinel = sentinelRef.current
    if (!sentinel) return

    const root = sentinel.closest("[data-radix-scroll-area-viewport]")
    const observer = new IntersectionObserver((entries) => {
      if (entries.some((entry) => entry.isIntersecting)) loadMore()
    }, { root, rootMargin: "240px 0px" })
    observer.observe(sentinel)
    return () => observer.disconnect()
  }, [hasMore, loadMore])

  return { hasMore, loadMore, sentinelRef, visibleCount }
}
