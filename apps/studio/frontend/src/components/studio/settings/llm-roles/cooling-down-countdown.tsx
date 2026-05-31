import { useEffect, useMemo, useState } from "react"
import { RotateCw } from "lucide-react"
import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"

interface CoolingDownCountdownProps {
  retryAt: string | Date | null
  now?: Date
  onTestNow: () => void | Promise<void>
  isTesting?: boolean
  disabled?: boolean
  className?: string
}

export function CoolingDownCountdown({
  retryAt,
  now,
  onTestNow,
  isTesting = false,
  disabled = false,
  className,
}: CoolingDownCountdownProps) {
  const [currentTime, setCurrentTime] = useState(() => now ?? new Date())
  const remaining = useMemo(
    () => formatCoolingDownRemaining(retryAt, currentTime),
    [retryAt, currentTime],
  )

  useEffect(() => {
    if (now) {
      setCurrentTime(now)
      return undefined
    }
    const id = window.setInterval(() => setCurrentTime(new Date()), 1000)
    return () => window.clearInterval(id)
  }, [now])

  return (
    <span
      data-cooling-down-countdown="true"
      className={cn("inline-flex items-center gap-2 text-[10px] text-muted-foreground", className)}
    >
      <span>{remaining}</span>
      <Button
        type="button"
        variant="outline"
        size="xs"
        disabled={disabled || isTesting}
        onClick={onTestNow}
      >
        <RotateCw className={cn("size-3", isTesting && "animate-spin")} />
        Test Now
      </Button>
    </span>
  )
}

export function formatCoolingDownRemaining(
  retryAt: string | Date | null,
  now: Date = new Date(),
): string {
  if (!retryAt) return "ready to retry"
  const retryTime = retryAt instanceof Date ? retryAt : new Date(retryAt)
  const remainingMs = retryTime.getTime() - now.getTime()
  if (!Number.isFinite(remainingMs) || remainingMs <= 0) return "ready to retry"
  const totalSeconds = Math.ceil(remainingMs / 1000)
  const minutes = Math.floor(totalSeconds / 60)
  const seconds = totalSeconds % 60
  if (minutes > 0) return `${minutes}m ${seconds}s`
  return `${seconds}s`
}
