import { useCallback, useEffect, useRef, useState } from "react"
import { TriangleAlert } from "lucide-react"
import { useTranslation } from "react-i18next"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { SaveStatusBadge } from "@/components/ui/save-status-badge"
import type { SaveStatus } from "@/hooks/useDebouncedCredentialsSave"
import {
  fetchMediaRegistry,
  patchMediaModelSettings,
  probeMediaProvider,
  putMediaCredential,
  revealMediaCredential,
  type MediaRegistry,
} from "@/api/media"
import { SectionTitle } from "../shared"
import { MediaProviderCard } from "./MediaProviderCard"

const PROVIDER_ID = "runninghub"

function errorText(error: unknown): string {
  if (typeof error === "object" && error !== null) {
    const axiosMessage = (error as { response?: { data?: { message?: string } } }).response?.data
      ?.message
    if (axiosMessage) return axiosMessage
    const plain = (error as { message?: string }).message
    if (plain) return plain
  }
  return String(error)
}

export function MediaGenerationTab() {
  const { t } = useTranslation("settings")
  const [registry, setRegistry] = useState<MediaRegistry | null>(null)
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [saveStatus, setSaveStatus] = useState<SaveStatus>("idle")
  const [keyDraft, setKeyDraft] = useState<string | null>(null)
  const [baseUrlDraft, setBaseUrlDraft] = useState<string | null>(null)
  const [revealedKey, setRevealedKey] = useState<string | null>(null)
  const [probing, setProbing] = useState(false)
  const [savingModelIds, setSavingModelIds] = useState<ReadonlySet<string>>(new Set())
  const [expandedModelIds, setExpandedModelIds] = useState<ReadonlySet<string>>(new Set())
  // Autosave concurrency discipline: every commit takes a ticket; a response
  // whose ticket is stale must not overwrite newer local state or flip the
  // save badge (project rule: superseded requests never report saved/error).
  const saveTicket = useRef(0)

  useEffect(() => {
    let cancelled = false
    fetchMediaRegistry()
      .then((data) => {
        if (cancelled) return
        setRegistry(data)
        setLoadError(null)
      })
      .catch((error: unknown) => {
        if (!cancelled) setLoadError(errorText(error))
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [])

  const runProbe = useCallback(async () => {
    setProbing(true)
    try {
      setRegistry(await probeMediaProvider(PROVIDER_ID))
    } catch (error: unknown) {
      setLoadError(errorText(error))
    } finally {
      setProbing(false)
    }
  }, [])

  const commitCredential = useCallback(
    async (patch: { api_key?: string; base_url?: string }) => {
      const ticket = ++saveTicket.current
      setSaveStatus("saving")
      try {
        const snapshot = await putMediaCredential(PROVIDER_ID, patch)
        if (ticket !== saveTicket.current) return
        setRegistry(snapshot)
        setSaveStatus("saved")
        if (patch.api_key) {
          setRevealedKey(null)
          void runProbe()
        }
      } catch (error: unknown) {
        if (ticket !== saveTicket.current) return
        setSaveStatus("error")
        setLoadError(errorText(error))
      }
    },
    [runProbe],
  )

  const handleKeyCommit = useCallback(() => {
    if (keyDraft == null) return
    const trimmed = keyDraft.trim()
    setKeyDraft(null)
    if (trimmed) void commitCredential({ api_key: trimmed })
  }, [keyDraft, commitCredential])

  const handleBaseUrlCommit = useCallback(() => {
    if (baseUrlDraft == null || registry == null) return
    const trimmed = baseUrlDraft.trim()
    setBaseUrlDraft(null)
    const current = registry.providers[0]?.base_url
    if (trimmed && trimmed !== current) void commitCredential({ base_url: trimmed })
  }, [baseUrlDraft, registry, commitCredential])

  const handleToggleReveal = useCallback(() => {
    if (revealedKey != null) {
      setRevealedKey(null)
      return
    }
    revealMediaCredential(PROVIDER_ID)
      .then(setRevealedKey)
      .catch((error: unknown) => setLoadError(errorText(error)))
  }, [revealedKey])

  const handleToggleExpand = useCallback((modelId: string) => {
    setExpandedModelIds((current) => {
      const next = new Set(current)
      if (next.has(modelId)) next.delete(modelId)
      else next.add(modelId)
      return next
    })
  }, [])

  const applyModelPatch = useCallback(
    async (modelId: string, patch: { enabled?: boolean; defaults?: Record<string, string | number> }) => {
      setSavingModelIds((current) => new Set(current).add(modelId))
      setSaveStatus("saving")
      const ticket = ++saveTicket.current
      try {
        const snapshot = await patchMediaModelSettings(modelId, patch)
        if (ticket === saveTicket.current) {
          setRegistry(snapshot)
          setSaveStatus("saved")
        }
      } catch (error: unknown) {
        if (ticket === saveTicket.current) {
          setSaveStatus("error")
          setLoadError(errorText(error))
        }
      } finally {
        setSavingModelIds((current) => {
          const next = new Set(current)
          next.delete(modelId)
          return next
        })
      }
    },
    [],
  )

  const handleToggleEnabled = useCallback(
    (modelId: string, enabled: boolean) => {
      void applyModelPatch(modelId, { enabled })
    },
    [applyModelPatch],
  )

  const handleDefaultChange = useCallback(
    (modelId: string, param: string, value: string | number | null) => {
      const model = registry?.models.find((entry) => entry.id === modelId)
      if (!model) return
      const defaults: Record<string, string | number> = { ...model.settings.defaults }
      if (value == null) delete defaults[param]
      else defaults[param] = value
      void applyModelPatch(modelId, { defaults })
    },
    [registry, applyModelPatch],
  )

  return (
    <div className="max-w-3xl">
      <SectionTitle
        title={t("mediaGen.title")}
        description={t("mediaGen.description")}
        trailing={<SaveStatusBadge status={saveStatus} />}
      />
      {loading ? (
        <p className="text-xs text-muted-foreground">{t("mediaGen.loading")}</p>
      ) : loadError && registry == null ? (
        <Alert variant="destructive">
          <TriangleAlert className="size-3.5" />
          <AlertTitle>{t("mediaGen.loadFailedTitle")}</AlertTitle>
          <AlertDescription>{loadError}</AlertDescription>
        </Alert>
      ) : registry ? (
        <>
          {loadError ? (
            <p className="mb-2 text-xs text-destructive" data-testid="media-inline-error">
              {loadError}
            </p>
          ) : null}
          <MediaProviderCard
            provider={registry.providers[0]}
            models={registry.models}
            keyDraft={keyDraft}
            baseUrlDraft={baseUrlDraft}
            revealedKey={revealedKey}
            probing={probing}
            savingModelIds={savingModelIds}
            expandedModelIds={expandedModelIds}
            onKeyDraftChange={(value) => {
              setKeyDraft(value)
              setLoadError(null)
            }}
            onKeyCommit={handleKeyCommit}
            onBaseUrlDraftChange={setBaseUrlDraft}
            onBaseUrlCommit={handleBaseUrlCommit}
            onToggleReveal={handleToggleReveal}
            onProbe={() => void runProbe()}
            onToggleExpand={handleToggleExpand}
            onToggleEnabled={handleToggleEnabled}
            onDefaultChange={handleDefaultChange}
          />
        </>
      ) : null}
    </div>
  )
}
