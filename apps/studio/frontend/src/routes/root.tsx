import { isRouteErrorResponse, Outlet, useRouteError } from 'react-router-dom'
import { Toaster } from 'sonner'
import { GlobalShortcutShell } from '../components/studio/GlobalShortcutShell'

export default function Root() {
  return (
    <>
      <Outlet />
      <GlobalShortcutShell />
      <Toaster position="bottom-right" richColors closeButton />
    </>
  )
}

export function RootErrorBoundary() {
  const error = useRouteError()
  const title = isRouteErrorResponse(error)
    ? `${error.status} ${error.statusText}`
    : 'Something went wrong'
  const message = error instanceof Error
    ? error.message
    : isRouteErrorResponse(error)
      ? String(error.data ?? 'Route request failed')
      : 'The current view could not be rendered.'

  return (
    <>
      <main className="min-h-screen bg-background px-6 py-8 text-foreground">
        <section className="mx-auto max-w-xl rounded-md border border-border bg-card p-5 shadow-sm">
          <p className="text-xs font-medium uppercase text-muted-foreground">Studio Frontend</p>
          <h1 className="mt-2 text-lg font-semibold">{title}</h1>
          <p className="mt-2 text-sm text-muted-foreground">{message}</p>
        </section>
      </main>
      <GlobalShortcutShell />
      <Toaster position="bottom-right" richColors closeButton />
    </>
  )
}
