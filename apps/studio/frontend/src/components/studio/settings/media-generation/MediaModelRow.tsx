import { ChevronDown, ChevronRight } from "lucide-react"
import { useTranslation } from "react-i18next"
import { Badge } from "@/components/ui/badge"
import { Input } from "@/components/ui/input"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Switch } from "@/components/ui/switch"
import type { MediaModel } from "@/api/media"
import { capabilityChips, defaultableParamEntries, pricingLabelKey } from "./helpers"

const UNSET_SENTINEL = "__unset__"

export interface MediaModelRowProps {
  model: MediaModel
  expanded: boolean
  saving: boolean
  onToggleExpand: (modelId: string) => void
  onToggleEnabled: (modelId: string, enabled: boolean) => void
  onDefaultChange: (modelId: string, param: string, value: string | number | null) => void
}

export function MediaModelRow({
  model,
  expanded,
  saving,
  onToggleExpand,
  onToggleEnabled,
  onDefaultChange,
}: MediaModelRowProps) {
  const { t } = useTranslation("settings")
  const defaultables = defaultableParamEntries(model)
  const Chevron = expanded ? ChevronDown : ChevronRight

  return (
    <div className="border-b border-border/60 last:border-b-0" data-testid={`media-model-${model.id}`}>
      <div className="flex items-center gap-2 px-3 py-2 text-sm">
        <span
          className="size-2 shrink-0 rounded-full bg-muted-foreground/50"
          title={t("mediaGen.statusCataloged")}
          data-testid="media-model-status-dot"
        />
        <button
          type="button"
          className="flex min-w-0 flex-1 items-center gap-2 text-left"
          onClick={() => onToggleExpand(model.id)}
          aria-expanded={expanded}
        >
          <span className="truncate">{model.display_name}</span>
          <Chevron className="size-3.5 shrink-0 text-muted-foreground" />
        </button>
        <Badge variant="default" className="shrink-0" title={t(`mediaGen.taskNames.${model.task}`)}>
          {model.task}
        </Badge>
        <Badge
          variant={model.channel === "economy" ? "warning" : "success"}
          className="shrink-0"
        >
          {t(model.channel === "economy" ? "mediaGen.channelEconomy" : "mediaGen.channelOfficial")}
        </Badge>
        {model.pricing ? (
          <span className="shrink-0 text-xs text-muted-foreground">
            {t(pricingLabelKey(model.pricing), { amount: model.pricing.amount })}
          </span>
        ) : null}
        <Switch
          checked={model.settings.enabled}
          onCheckedChange={(checked) => onToggleEnabled(model.id, checked)}
          disabled={saving}
          aria-label={t("mediaGen.enabled")}
        />
      </div>

      {expanded ? (
        <div className="space-y-3 bg-muted/10 px-3 py-3 text-xs" data-testid="media-model-detail">
          <div className="flex flex-wrap gap-1.5">
            {capabilityChips(model).map((chip) => (
              <span
                key={chip}
                className="rounded-full border border-border/60 px-2 py-0.5 text-muted-foreground"
              >
                {chip}
              </span>
            ))}
          </div>

          {defaultables.length > 0 ? (
            <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
              <span className="font-medium text-foreground">{t("mediaGen.defaultsTitle")}</span>
              {defaultables.map(([name, spec]) => {
                const current = model.settings.defaults[name]
                if (spec.type === "enum") {
                  return (
                    <label key={name} className="flex items-center gap-1.5">
                      <span className="text-muted-foreground">{name}</span>
                      <Select
                        value={typeof current === "string" ? current : UNSET_SENTINEL}
                        onValueChange={(value) =>
                          onDefaultChange(model.id, name, value === UNSET_SENTINEL ? null : value)
                        }
                        disabled={saving}
                      >
                        <SelectTrigger size="sm" className="h-7 min-w-24 text-xs" data-testid={`media-default-${model.id}-${name}`}>
                          <SelectValue placeholder={t("mediaGen.defaultUnset")} />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value={UNSET_SENTINEL}>{t("mediaGen.defaultUnset")}</SelectItem>
                          {(spec.values ?? []).map((value) => (
                            <SelectItem key={value} value={value}>
                              {value}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </label>
                  )
                }
                return (
                  <label key={name} className="flex items-center gap-1.5">
                    <span className="text-muted-foreground">
                      {name} ({spec.min_value}–{spec.max_value})
                    </span>
                    <Input
                      type="number"
                      min={spec.min_value}
                      max={spec.max_value}
                      defaultValue={typeof current === "number" ? current : ""}
                      disabled={saving}
                      className="h-7 w-20 text-xs"
                      onBlur={(event) => {
                        const raw = event.currentTarget.value.trim()
                        if (raw === "") {
                          if (current !== undefined) onDefaultChange(model.id, name, null)
                          return
                        }
                        const min = spec.min_value ?? Number.MIN_SAFE_INTEGER
                        const max = spec.max_value ?? Number.MAX_SAFE_INTEGER
                        const clamped = Math.min(max, Math.max(min, Math.trunc(Number(raw))))
                        if (Number.isFinite(clamped) && clamped !== current) {
                          event.currentTarget.value = String(clamped)
                          onDefaultChange(model.id, name, clamped)
                        }
                      }}
                    />
                  </label>
                )
              })}
            </div>
          ) : (
            <p className="text-muted-foreground">{t("mediaGen.noDefaultParams")}</p>
          )}

          {model.doc_source ? (
            <p className="text-muted-foreground/80">
              {t("mediaGen.docSource")}: {model.doc_source}
            </p>
          ) : null}
        </div>
      ) : null}
    </div>
  )
}

export const mediaModelRowTestExports = { UNSET_SENTINEL }
