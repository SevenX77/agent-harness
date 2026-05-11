import { Rocket, X } from 'lucide-react'

interface PublishModalProps {
  open: boolean
  onClose: () => void
}

export function PublishModal({ open, onClose }: PublishModalProps) {
  if (!open) {
    return null
  }

  return (
    <div className="fixed inset-0 z-modal grid place-items-center bg-background/70 p-4 backdrop-blur-sm">
      <section className="w-full max-w-lg rounded-md border border-border bg-card shadow-xl">
        <header className="flex items-center justify-between border-b border-border px-4 py-3">
          <div>
            <h2 className="flex items-center gap-2 text-sm font-semibold text-foreground">
              <Rocket className="size-4" />
              Publish skill
            </h2>
            <p className="mt-1 text-xs text-muted-foreground">Backend publish API is not available in V2.</p>
          </div>
          <button type="button" onClick={onClose} aria-label="Close publish modal" className="rounded-md p-1 text-muted-foreground hover:bg-accent hover:text-foreground">
            <X className="size-4" />
          </button>
        </header>
        <div className="space-y-4 p-4">
          <label className="block">
            <span className="mb-1 block text-xs font-medium text-muted-foreground">Commit message</span>
            <input
              value="Publish evaluated skill"
              readOnly
              className="h-9 w-full rounded-md border border-input bg-muted/40 px-3 text-sm text-muted-foreground"
            />
          </label>
          <div className="rounded-md border border-amber-400/40 bg-amber-500/10 px-3 py-2 text-sm text-amber-700 dark:text-amber-300">
            Publish backend pending. No network request will be sent from this V2 UI.
          </div>
        </div>
        <footer className="flex justify-end gap-2 border-t border-border px-4 py-3">
          <button type="button" onClick={onClose} className="h-9 rounded-md border border-border bg-background px-3 text-sm font-medium text-foreground hover:bg-accent">
            Close
          </button>
          <button type="button" disabled className="h-9 rounded-md bg-primary px-3 text-sm font-medium text-primary-foreground opacity-45">
            Publish pending
          </button>
        </footer>
      </section>
    </div>
  )
}
