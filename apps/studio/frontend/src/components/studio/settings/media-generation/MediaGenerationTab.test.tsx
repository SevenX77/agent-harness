import { renderToStaticMarkup } from "react-dom/server"
import { describe, expect, it, vi } from "vitest"
import type { MediaModel, MediaProviderView, MediaRegistry } from "@/api/media"
import enSettings from "@/locales/en/settings.json"
import zhSettings from "@/locales/zh-CN/settings.json"
import {
  capabilityChips,
  defaultableParamEntries,
  groupModelsByModality,
  probeBadgeVariant,
  probeStatusLabelKey,
} from "./helpers"
import { MediaProviderCard } from "./MediaProviderCard"

vi.mock("react-i18next", () => ({
  initReactI18next: { type: "3rdParty", init: () => undefined },
  useTranslation: () => ({
    t: (key: string, options?: Record<string, unknown>) => {
      if (options && Object.keys(options).length > 0) {
        return `${key}:${Object.values(options).join(",")}`
      }
      return key
    },
  }),
}))

function model(overrides: Partial<MediaModel>): MediaModel {
  return {
    id: "rh-image-v2-t2i",
    provider: "runninghub",
    display_name: "全能图片V2-文生图-低价渠道版",
    modality: "image",
    task: "t2i",
    channel: "economy",
    endpoint_kind: "standard",
    endpoint: "/openapi/v2/x/y",
    pricing: { unit: "per_image", amount: 0.19, currency: "CNY" },
    params: {
      prompt: { type: "string", required: true },
      resolution: { type: "enum", required: true, values: ["1k", "2k", "4k"] },
      duration: { type: "int_range", required: false, min_value: 6, max_value: 30 },
      imageUrls: { type: "image_list", required: true, max_items: 10, max_size_mb: 30 },
    },
    doc_source: "AI-story-forge:docs/api/runninghub/nbv2_t2i_rh.md",
    settings: { enabled: true, defaults: {} },
    ...overrides,
  }
}

const provider: MediaProviderView = {
  id: "runninghub",
  base_url: "https://www.runninghub.cn",
  api_key_set: true,
  last_probe: {
    status: "ok",
    checked_at: "2026-08-13T00:00:00+00:00",
    latency_ms: 412,
    remain_coins: "1024",
    remain_money: "99",
  },
}

const registry: MediaRegistry = {
  providers: [provider],
  models: [
    model({}),
    model({ id: "rh-video-x-i2v", modality: "video", task: "i2v", display_name: "全能视频X" }),
  ],
}

describe("media helpers", () => {
  it("groups models by modality", () => {
    const groups = groupModelsByModality(registry.models)
    expect(groups.image.map((m) => m.id)).toEqual(["rh-image-v2-t2i"])
    expect(groups.video.map((m) => m.id)).toEqual(["rh-video-x-i2v"])
  })

  it("only enum and int_range params are defaultable — mirrors gateway validation", () => {
    const entries = defaultableParamEntries(model({}))
    expect(entries.map(([name]) => name).sort()).toEqual(["duration", "resolution"])
  })

  it("renders capability chips from the declarative schema", () => {
    const chips = capabilityChips(model({}))
    expect(chips).toContain("resolution: 1k / 2k / 4k")
    expect(chips).toContain("duration: 6–30")
    expect(chips).toContain("imageUrls: ≤10 · ≤30MB")
  })

  it("maps probe status to badge variant and label", () => {
    expect(probeBadgeVariant(null)).toBe("secondary")
    expect(probeBadgeVariant(provider.last_probe)).toBe("success")
    expect(
      probeBadgeVariant({ status: "auth_failed", checked_at: "x" }),
    ).toBe("destructive")
    expect(probeStatusLabelKey({ status: "network_error", checked_at: "x" })).toBe(
      "mediaGen.probeNetworkError",
    )
  })
})

describe("MediaProviderCard rendering", () => {
  const noop = () => undefined
  const cardProps = {
    provider,
    models: registry.models,
    keyDraft: null,
    baseUrlDraft: null,
    revealedKey: null,
    probing: false,
    savingModelIds: new Set<string>(),
    expandedModelIds: new Set<string>(),
    onKeyDraftChange: noop,
    onKeyCommit: noop,
    onBaseUrlDraftChange: noop,
    onBaseUrlCommit: noop,
    onToggleReveal: noop,
    onProbe: noop,
    onToggleExpand: noop,
    onToggleEnabled: noop,
    onDefaultChange: noop,
  }

  it("renders balance, probe status and both modality groups", () => {
    const html = renderToStaticMarkup(<MediaProviderCard {...cardProps} />)
    expect(html).toContain("mediaGen.probeOk")
    expect(html).toContain("mediaGen.balanceCoins:1024")
    expect(html).toContain("mediaGen.imageModels")
    expect(html).toContain("mediaGen.videoModels")
    expect(html).toContain("全能图片V2-文生图-低价渠道版")
    expect(html).toContain("全能视频X")
    expect(html).toContain("mediaGen.pricingPerImage:0.19")
  })

  it("shows expanded capability chips and default selects for the expanded model", () => {
    const html = renderToStaticMarkup(
      <MediaProviderCard {...cardProps} expandedModelIds={new Set(["rh-image-v2-t2i"])} />,
    )
    expect(html).toContain("resolution: 1k / 2k / 4k")
    expect(html).toContain("mediaGen.defaultsTitle")
    expect(html).toContain("media-default-rh-image-v2-t2i-resolution")
  })

  it("disables the probe button when no key is stored", () => {
    const html = renderToStaticMarkup(
      <MediaProviderCard
        {...cardProps}
        provider={{ ...provider, api_key_set: false, last_probe: null }}
      />,
    )
    expect(html).toContain("mediaGen.untested")
    expect(html).toMatch(
      /<button[^>]*(disabled[^>]*data-testid="media-probe-button"|data-testid="media-probe-button"[^>]*disabled)/,
    )
  })
})

describe("mediaGen i18n bundle contract", () => {
  const CJK = /[一-鿿]/
  const en = enSettings.mediaGen as Record<string, unknown>
  const zh = zhSettings.mediaGen as Record<string, unknown>

  it("en + zh define the same mediaGen keys", () => {
    expect(Object.keys(zh).sort()).toEqual(Object.keys(en).sort())
  })

  it("zh copy is actual Chinese for user-facing strings", () => {
    expect(CJK.test(String(zh.title))).toBe(true)
    expect(CJK.test(String(zh.testConnection))).toBe(true)
    expect(CJK.test(String(zh.channelEconomy))).toBe(true)
  })

  it("both tab bundles carry the renamed LLM API-Key label and the new tab", () => {
    expect(enSettings.tabs.apiKeys).toBe("LLM API-Key")
    expect(zhSettings.tabs.apiKeys).toBe("LLM API-Key")
    expect(enSettings.tabs.mediaGeneration).toBe("Media Generation")
    expect(zhSettings.tabs.mediaGeneration).toBe("媒体生成")
  })

  it("placeholder names survive in both locales", () => {
    for (const key of ["balanceCoins", "lastChecked", "pricingPerImage"] as const) {
      const enValue = String(en[key])
      const zhValue = String(zh[key])
      const placeholders = enValue.match(/{{\w+}}/g) ?? []
      for (const placeholder of placeholders) {
        expect(zhValue).toContain(placeholder)
      }
    }
  })
})
