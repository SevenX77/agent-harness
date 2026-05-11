import { AlertTriangle, Loader2, Wifi } from 'lucide-react'
import type { WebSocketStatus } from '../../lib/websocket'

interface NetworkBannerProps {
  status: WebSocketStatus
  reconnectInMs: number | null
  error: string | null
}

export function NetworkBanner({ status, reconnectInMs, error }: NetworkBannerProps) {
  if (status === 'idle' || status === 'open') {
    return null
  }

  const reconnecting = status === 'connecting' || status === 'reconnecting'

  return (
    <div className="flex items-center justify-between gap-3 border-b border-border bg-amber-500/10 px-4 py-2 text-sm text-amber-700 dark:text-amber-300">
      <div className="flex items-center gap-2">
        {reconnecting ? <Loader2 className="size-4 animate-spin" /> : <AlertTriangle className="size-4" />}
        <span>
          Run stream {status}
          {reconnectInMs ? `, retry in ${Math.round(reconnectInMs / 1000)}s` : ''}
          {error ? `: ${error}` : ''}
        </span>
      </div>
      <Wifi className="size-4" />
    </div>
  )
}
