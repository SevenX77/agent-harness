import { useEffect, useState } from "react"
import { GitCompareArrows } from "lucide-react"
import { getRoles } from "@/api/llm"
import { Button } from "@/components/ui/button"
import { Checkbox } from "@/components/ui/checkbox"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog"
import { errorMessage } from "@/utils/errors"

/**
 * n4-trace#23 (P8 model-compare): launcher for a compare run. The candidates come
 * from the roles ALREADY built in Settings (llm_roles.yaml) — this dialog reads
 * the role names off `getRoles()` (the KEEP-MAIN roles read API), lets the user
 * multi-select, and hands the picked role names to Workspace's `onStartCompare`
 * (which turns them into `RunCandidate[]` for the real `POST /runs/compare`).
 * No role is created here; we only reference existing settings entities.
 */
interface CompareRunDialogProps {
  disabled?: boolean
  starting?: boolean
  onStartCompare: (roleNames: string[]) => Promise<void> | void
}

export function CompareRunDialog({ disabled = false, starting = false, onStartCompare }: CompareRunDialogProps) {
  const [open, setOpen] = useState(false)
  const [roleNames, setRoleNames] = useState<string[]>([])
  const [selected, setSelected] = useState<Set<string>>(() => new Set())
  const [loading, setLoading] = useState(false)
  const [loadError, setLoadError] = useState<string | null>(null)

  useEffect(() => {
    if (!open) return undefined
    let cancelled = false
    setLoading(true)
    setLoadError(null)
    void getRoles()
      .then((data) => {
        if (cancelled) return
        setRoleNames(Object.keys(data.roles ?? {}))
      })
      .catch((error) => {
        if (cancelled) return
        setLoadError(errorMessage(error))
      })
      .finally(() => {
        if (cancelled) return
        setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [open])

  const toggle = (roleName: string) => {
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(roleName)) {
        next.delete(roleName)
      } else {
        next.add(roleName)
      }
      return next
    })
  }

  const handleConfirm = async () => {
    await onStartCompare([...selected])
    setOpen(false)
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button
          type="button"
          variant="outline"
          size="sm"
          disabled={disabled}
          aria-label="Compare models"
          title="Run this skill across multiple Settings roles and compare results"
        >
          <GitCompareArrows className="size-4" />
          Compare models
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Compare models</DialogTitle>
          <DialogDescription>
            Pick the roles to compare. Each runs this skill once; switch between them in the Trace tabs.
          </DialogDescription>
        </DialogHeader>
        <div className="max-h-72 space-y-2 overflow-y-auto py-1">
          {loading ? <p className="text-sm text-muted-foreground">Loading roles…</p> : null}
          {loadError ? (
            <p className="rounded-md border border-destructive/20 bg-destructive/10 p-2 text-sm text-destructive">
              {loadError}
            </p>
          ) : null}
          {!loading && !loadError && roleNames.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              No roles in Settings yet. Create a role to compare against.
            </p>
          ) : null}
          {roleNames.map((roleName) => (
            <label
              key={roleName}
              className="flex cursor-pointer items-center gap-2 rounded-md px-2 py-1.5 text-sm hover:bg-accent"
            >
              <Checkbox
                checked={selected.has(roleName)}
                onCheckedChange={() => toggle(roleName)}
                aria-label={`Compare role ${roleName}`}
              />
              <span className="truncate">{roleName}</span>
            </label>
          ))}
        </div>
        <DialogFooter>
          <Button
            type="button"
            disabled={selected.size === 0 || starting}
            onClick={() => {
              void handleConfirm()
            }}
          >
            {starting ? "Starting…" : `Compare ${selected.size} role${selected.size === 1 ? "" : "s"}`}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
