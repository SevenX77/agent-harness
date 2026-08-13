import { Eye, EyeOff, PlugZap } from "lucide-react"
import { useTranslation } from "react-i18next"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import type { MediaModel, MediaProviderView } from "@/api/media"
import { MediaModelRow } from "./MediaModelRow"
import { groupModelsByModality, probeBadgeVariant, probeStatusLabelKey } from "./helpers"

export interface MediaProviderCardProps {
  provider: MediaProviderView
  models: MediaModel[]
  keyDraft: string | null
  baseUrlDraft: string | null
  revealedKey: string | null
  probing: boolean
  savingModelIds: ReadonlySet<string>
  expandedModelIds: ReadonlySet<string>
  onKeyDraftChange: (value: string) => void
  onKeyCommit: () => void
  onBaseUrlDraftChange: (value: string) => void
  onBaseUrlCommit: () => void
  onToggleReveal: () => void
  onProbe: () => void
  onToggleExpand: (modelId: string) => void
  onToggleEnabled: (modelId: string, enabled: boolean) => void
  onDefaultChange: (modelId: string, param: string, value: string | number | null) => void
}

export function MediaProviderCard({
  provider,
  models,
  keyDraft,
  baseUrlDraft,
  revealedKey,
  probing,
  savingModelIds,
  expandedModelIds,
  onKeyDraftChange,
  onKeyCommit,
  onBaseUrlDraftChange,
  onBaseUrlCommit,
  onToggleReveal,
  onProbe,
  onToggleExpand,
  onToggleEnabled,
  onDefaultChange,
}: MediaProviderCardProps) {
  const { t } = useTranslation("settings")
  const groups = groupModelsByModality(models)
  const probe = provider.last_probe
  const keyValue = keyDraft ?? revealedKey ?? (provider.api_key_set ? "••••••••••" : "")

  return (
    <div className="rounded-md border border-border/60 bg-card p-4" data-testid="media-provider-card">
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <span className="text-sm font-medium">{t("mediaGen.providerRunninghub")}</span>
        {probe ? (
          <Badge variant={probeBadgeVariant(probe)} data-testid="media-probe-status">
            {t(probeStatusLabelKey(probe))}
          </Badge>
        ) : (
          <Badge variant="secondary" data-testid="media-probe-status">
            {t("mediaGen.untested")}
          </Badge>
        )}
        {probe?.status === "ok" && probe.remain_coins != null ? (
          <Badge variant="secondary" data-testid="media-balance">
            {t("mediaGen.balanceCoins", { coins: probe.remain_coins })}
            {probe.remain_money != null
              ? ` · ${t("mediaGen.balanceMoney", { money: probe.remain_money })}`
              : null}
          </Badge>
        ) : null}
        <span className="flex-1" />
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={onProbe}
          disabled={probing || !provider.api_key_set}
          title={provider.api_key_set ? undefined : t("mediaGen.keyNotSet")}
          data-testid="media-probe-button"
        >
          <PlugZap className="size-3.5" />
          {probing ? t("mediaGen.probing") : t("mediaGen.testConnection")}
        </Button>
      </div>

      <div className="mb-2 grid gap-3 sm:grid-cols-2">
        <div className="space-y-1">
          <Label className="text-xs text-muted-foreground" htmlFor="media-api-key">
            {t("mediaGen.apiKeyLabel")}
          </Label>
          <div className="flex items-center gap-1">
            <Input
              id="media-api-key"
              type={revealedKey != null || keyDraft != null ? "text" : "password"}
              value={keyValue}
              placeholder={t("mediaGen.apiKeyPlaceholder")}
              onChange={(event) => onKeyDraftChange(event.target.value)}
              onBlur={onKeyCommit}
              onKeyDown={(event) => {
                if (event.key === "Enter") event.currentTarget.blur()
              }}
              className="h-8 text-xs"
              data-testid="media-api-key-input"
            />
            <Button
              type="button"
              variant="ghost"
              size="icon"
              className="size-8"
              onClick={onToggleReveal}
              disabled={!provider.api_key_set && keyDraft == null}
              aria-label={t("mediaGen.revealKey")}
            >
              {revealedKey != null ? <EyeOff className="size-3.5" /> : <Eye className="size-3.5" />}
            </Button>
          </div>
        </div>
        <div className="space-y-1">
          <Label className="text-xs text-muted-foreground" htmlFor="media-base-url">
            {t("mediaGen.baseUrlLabel")}
          </Label>
          <Input
            id="media-base-url"
            value={baseUrlDraft ?? provider.base_url}
            onChange={(event) => onBaseUrlDraftChange(event.target.value)}
            onBlur={onBaseUrlCommit}
            onKeyDown={(event) => {
              if (event.key === "Enter") event.currentTarget.blur()
            }}
            className="h-8 text-xs"
            data-testid="media-base-url-input"
          />
        </div>
      </div>

      {probe && probe.status !== "ok" && probe.message ? (
        <p className="mb-3 text-xs text-destructive" data-testid="media-probe-error">
          {probe.message}
        </p>
      ) : null}
      {probe ? (
        <p className="mb-3 text-xs text-muted-foreground">
          {t("mediaGen.lastChecked", { time: probe.checked_at })}
          {probe.latency_ms != null ? ` · ${probe.latency_ms}ms` : null}
        </p>
      ) : null}

      <p className="mb-1 text-xs font-medium text-muted-foreground">
        {t("mediaGen.imageModels")} · {groups.image.length}
      </p>
      <div className="mb-4 rounded-md border border-border/60" data-testid="media-image-models">
        {groups.image.map((model) => (
          <MediaModelRow
            key={model.id}
            model={model}
            expanded={expandedModelIds.has(model.id)}
            saving={savingModelIds.has(model.id)}
            onToggleExpand={onToggleExpand}
            onToggleEnabled={onToggleEnabled}
            onDefaultChange={onDefaultChange}
          />
        ))}
      </div>

      <p className="mb-1 text-xs font-medium text-muted-foreground">
        {t("mediaGen.videoModels")} · {groups.video.length}
      </p>
      <div className="rounded-md border border-border/60" data-testid="media-video-models">
        {groups.video.map((model) => (
          <MediaModelRow
            key={model.id}
            model={model}
            expanded={expandedModelIds.has(model.id)}
            saving={savingModelIds.has(model.id)}
            onToggleExpand={onToggleExpand}
            onToggleEnabled={onToggleEnabled}
            onDefaultChange={onDefaultChange}
          />
        ))}
      </div>
    </div>
  )
}
