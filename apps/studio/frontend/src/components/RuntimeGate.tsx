import { useEffect, useState } from 'react'
import { RouterProvider } from 'react-router-dom'
import { initializeRuntimeConfig } from '../config/runtime'
import { router } from '../routes/router'

export function RuntimeGate() {
  const [runtimeState, setRuntimeState] = useState<'loading' | 'ready' | 'error'>('loading')
  const [message, setMessage] = useState('')

  useEffect(() => {
    let cancelled = false
    initializeRuntimeConfig()
      .then(() => {
        if (!cancelled) {
          setRuntimeState('ready')
        }
      })
      .catch((error: unknown) => {
        if (!cancelled) {
          setMessage(error instanceof Error ? error.message : String(error))
          setRuntimeState('error')
        }
      })
    return () => {
      cancelled = true
    }
  }, [])

  if (runtimeState === 'loading') {
    return <div className="runtime-splash">Starting Skill Studio</div>
  }

  if (runtimeState === 'error') {
    return (
      <div className="runtime-splash runtime-splash-error">
        <span>Backend startup failed</span>
        <code>{message}</code>
      </div>
    )
  }

  return <RouterProvider router={router} />
}
