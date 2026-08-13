import type { MediaModel, MediaParamSpec, MediaPricing, MediaProbeResult } from "@/api/media"

export interface ModelGroups {
  image: MediaModel[]
  video: MediaModel[]
}

export function groupModelsByModality(models: MediaModel[]): ModelGroups {
  return {
    image: models.filter((model) => model.modality === "image"),
    video: models.filter((model) => model.modality === "video"),
  }
}

/** Params a user default may target — mirrors gateway validate_model_settings. */
export function defaultableParamEntries(model: MediaModel): Array<[string, MediaParamSpec]> {
  return Object.entries(model.params).filter(
    ([, spec]) => spec.type === "enum" || spec.type === "int_range",
  )
}

/**
 * Locale-neutral capability chips rendered straight from the catalog schema —
 * the same declarative facts the backend validates against, so no chip can
 * claim what the API will not accept.
 */
export function capabilityChips(model: MediaModel): string[] {
  const chips: string[] = []
  for (const [name, spec] of Object.entries(model.params)) {
    if (spec.type === "enum" && spec.values?.length) {
      chips.push(`${name}: ${spec.values.join(" / ")}`)
    } else if (spec.type === "int_range") {
      chips.push(`${name}: ${spec.min_value}–${spec.max_value}`)
    } else if (spec.type === "image_list") {
      const size = spec.max_size_mb != null ? ` · ≤${spec.max_size_mb}MB` : ""
      chips.push(`${name}: ≤${spec.max_items}${size}`)
    } else if (spec.type === "image_slot") {
      const size = spec.max_size_mb != null ? ` ≤${spec.max_size_mb}MB` : ""
      chips.push(`${name}${spec.required ? "" : "?"}${size}`)
    }
  }
  return chips
}

export function pricingLabelKey(
  pricing: MediaPricing,
): "mediaGen.pricingPerImage" | "mediaGen.pricingPerSecond" | "mediaGen.pricingPerRun" {
  switch (pricing.unit) {
    case "per_image":
      return "mediaGen.pricingPerImage"
    case "per_second":
      return "mediaGen.pricingPerSecond"
    case "per_run":
      return "mediaGen.pricingPerRun"
  }
}

export function probeBadgeVariant(probe: MediaProbeResult | null): "success" | "destructive" | "secondary" {
  if (!probe) return "secondary"
  return probe.status === "ok" ? "success" : "destructive"
}

export function probeStatusLabelKey(
  probe: MediaProbeResult,
): "mediaGen.probeOk" | "mediaGen.probeAuthFailed" | "mediaGen.probeNetworkError" {
  switch (probe.status) {
    case "ok":
      return "mediaGen.probeOk"
    case "auth_failed":
      return "mediaGen.probeAuthFailed"
    case "network_error":
      return "mediaGen.probeNetworkError"
  }
}
