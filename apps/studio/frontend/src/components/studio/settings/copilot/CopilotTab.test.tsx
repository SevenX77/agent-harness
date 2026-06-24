import { readFile } from "node:fs/promises"
import { renderToStaticMarkup } from "react-dom/server"
import { describe, expect, it, vi } from "vitest"
import {
  CopilotTab,
  copilotBackendReadyCount,
  copilotGroupComboboxFilter,
  copilotGroupSearchValue,
  copilotKeyForGroupId,
  nextCopilotCustomIndex,
  rebuildFallbackChainPreservingRuntime,
} from "./CopilotTab"
import { agentStatusForRoute } from "./CopilotModelGroupCard"
import {
  copilotRouteStatusesFromPersistedResult,
  type CopilotRouteJobStatus,
} from "./copilot-role-test"
import type { CopilotRolePreview, CopilotRoutePreview } from "./copilot-role-derivation"
import type { CredentialsState, ModelGroup, RolesData } from "@/api/llm"

vi.mock("react-i18next", () => ({
  initReactI18next: {
    type: "3rdParty",
    init: () => undefined,
  },
  useTranslation: () => ({
    t: (key: string, options?: { count?: number; defaultValue?: string }) => (
      options?.defaultValue?.replace("{{count}}", String(options.count ?? "")) ?? key
    ),
  }),
}))

vi.mock("@/api/client", () => ({
  getRoleTestResults: vi.fn(async () => ({ results: {} })),
}))

function registryModelGroups(): ModelGroup[] {
  return [
    {
      canonical_id: "claude-opus-4.7",
      display_name: "Claude Opus 4.7",
      provider_models: [
        {
          route_id: "anthropic-official:claude-opus-4-7",
          endpoint_id: "anthropic-official",
          provider_label: "Anthropic Official",
          provider_kind: "official",
          provider_model_id: "claude-opus-4-7",
          ui_state: "ready",
          ui_detail: null,
          retry_at: null,
          reason_code: null,
          capability_state: "known",
          capabilities: {},
          call_method_id: "anthropic_messages",
        },
        {
          route_id: "qiniu-anthropic:claude-opus-4-7",
          endpoint_id: "qiniu-anthropic",
          provider_label: "Qiniu Anthropic",
          provider_kind: "third_party",
          provider_model_id: "claude-opus-4-7",
          ui_state: "untested",
          ui_detail: null,
          retry_at: null,
          reason_code: null,
          capability_state: "known",
          capabilities: {},
          call_method_id: "anthropic_messages",
        },
      ],
      status_summary: {
        ready: 1,
        untested: 1,
        cooling_down: 0,
        historical_ready: 0,
        failed: 0,
        off: 0,
      },
      capability_summary: {
        capability_known_count: 2,
        thinking: "unknown",
        tools: "unknown",
        structured_output: "unknown",
        max_context_tokens: null,
        max_output_tokens: null,
      },
    },
  ]
}

function credentials(): CredentialsState {
  return {
    providers: [
      {
        id: "anthropic-official",
        name: "Anthropic Official",
        provider_type: "anthropic_compatible",
        api_key: "**********",
      },
      {
        id: "qiniu-anthropic",
        name: "Qiniu Anthropic",
        provider_type: "anthropic_compatible",
        api_key: "**********",
      },
    ],
  }
}

function roles(): RolesData {
  return {
    schema_version: 3,
    models: {},
    providers: {},
    model_profiles: {},
    model_bundles: {},
    roles: {
      copilot_opus: {
        role_kind: "copilot",
        system_prompt_prefix: "",
        model_fallback_enabled: true,
        intent: { provider_preference: "manual_order" },
        model_groups: [],
        active_model: "claude-opus-4.7",
        models: {
          "claude-opus-4.7": {
            providers: [
              "anthropic-official:claude-opus-4-7",
              "qiniu-anthropic:claude-opus-4-7",
            ],
          },
        },
        fallback_chain: [
          { route_id: "anthropic-official:claude-opus-4-7", runtime_settings: {} },
          { route_id: "qiniu-anthropic:claude-opus-4-7", runtime_settings: {} },
        ],
        lint_requirements: {},
      },
    },
  }
}

describe("CopilotTab route status projection", () => {
  it("counts a persisted/live 'ready' SDK verdict toward the N/M ready count, not just the backend ui_state", () => {
    const routes = [
      { id: "ready:route", agentStatus: "ready" },
      { id: "untested:route", agentStatus: "untested" },
    ]

    // atom-57: the light's authority is the real SDK verdict (override) > ui_state.
    // A persisted/live 'ready' verdict on an otherwise-untested route lights it green,
    // so the N/M ready count must rise to 2.
    expect(copilotBackendReadyCount(routes, { "untested:route": "ready" })).toBe(2)
    // A persisted 'unsupported' verdict on the only ui_state='ready' route knocks it
    // back out, leaving zero ready routes.
    expect(copilotBackendReadyCount(routes, { "ready:route": "unsupported" })).toBe(0)
    // With no overrides the count falls back to ui_state facts.
    expect(copilotBackendReadyCount(routes, {})).toBe(1)
  })

  it("lets any present SDK verdict override the backend ui_state, with 'testing' strictly highest priority", () => {
    // atom-57 priority: testing (in-flight) > persisted/live SDK verdict > initial ui_state.
    // A persisted/completed verdict beats the backend ui_state.
    expect(agentStatusForRoute("untested", "route-a", { "route-a": "ready" })).toBe("ready")
    expect(agentStatusForRoute("ready", "route-a", { "route-a": "unsupported" })).toBe("unsupported")
    // No override → fall back to the backend ui_state.
    expect(agentStatusForRoute("ready", "route-a", {})).toBe("ready")
    expect(agentStatusForRoute("untested", "route-a", {})).toBe("untested")
    // 'testing' wins even over a stale persisted 'ready', so an in-flight re-test is never masked.
    expect(agentStatusForRoute("untested", "route-a", { "route-a": "testing" })).toBe("testing")
    expect(agentStatusForRoute("ready", "route-a", { "route-a": "testing" })).toBe("testing")
  })

  it("renders SDK ready count from backend DTO facts rather than route test overrides", () => {
    const html = renderToStaticMarkup(
      <CopilotTab data={roles()} credentials={credentials()} modelGroups={registryModelGroups()} />,
    )

    expect(html).toContain("1/2 SDK Ready")
  })
})

describe("CopilotTab #57 status-light persistence across remount", () => {
  // atom-57: the route light's authority is the persisted SDK verdict. On (re)mount,
  // CopilotTab seeds routeStatusOverrides from getRoleTestResults() via
  // copilotRouteStatusesFromPersistedResult, then agentStatusForRoute projects that
  // seed over the backend ui_state. Driving the real seed→project chain proves the
  // light survives a tab reopen / backend restart without resetting to ui_state.
  function seededOverridesFromPersistedResults(
    results: Record<string, { result: unknown }>,
  ): Record<string, CopilotRouteJobStatus> {
    const seeded: Record<string, CopilotRouteJobStatus> = {}
    for (const entry of Object.values(results)) {
      Object.assign(seeded, copilotRouteStatusesFromPersistedResult(entry.result))
    }
    return seeded
  }

  it("paints a persisted 'ready'/'failed' SDK verdict on the route light after remount", () => {
    const persisted = {
      copilot_opus: {
        result: {
          sdk_evidence: {
            routes: {
              // ui_state='ready' for this route, but the last real SDK test failed → failed wins.
              "anthropic-official:claude-opus-4-7": { status: "failed" },
              // ui_state='untested' for this route, but the last real SDK test passed → ready wins.
              "qiniu-anthropic:claude-opus-4-7": { status: "ok" },
            },
          },
        },
      },
    }

    const seeded = seededOverridesFromPersistedResults(persisted)

    // The mount seed restores the persisted verdicts as overrides, and the light
    // projection prefers them over the raw backend ui_state. R-F11: the new
    // 6-state vocabulary uses "failed" where the legacy code used "unsupported".
    expect(agentStatusForRoute("ready", "anthropic-official:claude-opus-4-7", seeded)).toBe("failed")
    expect(agentStatusForRoute("untested", "qiniu-anthropic:claude-opus-4-7", seeded)).toBe("ready")
  })

  it("keeps an in-flight 'testing' override winning over a stale persisted 'ready'", () => {
    // The unified override map carries both the persisted seed and the in-flight job progress.
    // A stale persisted 'ready' must never mask an in-flight re-test.
    const persisted = {
      copilot_opus: {
        result: { sdk_evidence: { routes: { "route-a": { status: "ok" } } } },
      },
    }
    const seeded = seededOverridesFromPersistedResults(persisted)
    expect(seeded["route-a"]).toBe("ready") // persisted seed alone resolves ready

    // In-flight job progress overwrites the persisted seed in the unified map; testing wins.
    const withLiveTest = { ...seeded, "route-a": "testing" as const }
    expect(agentStatusForRoute("untested", "route-a", withLiveTest)).toBe("testing")
  })
})

function opusGroup(canonicalId: string, displayName: string): ModelGroup {
  return {
    canonical_id: canonicalId,
    display_name: displayName,
    provider_models: [
      {
        route_id: `anthropic-official:${canonicalId}`,
        endpoint_id: "anthropic-official",
        provider_label: "Anthropic Official",
        provider_kind: "official",
        provider_model_id: canonicalId,
        ui_state: "ready",
        ui_detail: null,
        retry_at: null,
        reason_code: null,
        capability_state: "known",
        capabilities: {},
        call_method_id: "anthropic_messages",
      },
    ],
    status_summary: { ready: 1, untested: 0, cooling_down: 0, historical_ready: 0, failed: 0, off: 0 },
    capability_summary: {
      capability_known_count: 1,
      thinking: "unknown",
      tools: "unknown",
      structured_output: "unknown",
      max_context_tokens: null,
      max_output_tokens: null,
    },
  } as ModelGroup
}

function emptyRoles(): RolesData {
  return { schema_version: 3, models: {}, providers: {}, model_profiles: {}, model_bundles: {}, roles: {} }
}

function rolesWithDraft(): RolesData {
  return {
    ...emptyRoles(),
    roles: {
      copilot_custom_1: {
        role_kind: "copilot",
        system_prompt_prefix: "",
        model_fallback_enabled: true,
        intent: { provider_preference: "manual_order" },
        model_groups: [],
        active_model: "",
        models: {},
        fallback_chain: [],
      },
    },
  }
}

describe("CopilotTab #56 dynamic float of built-in defaults", () => {
  it("floats the family-ladder built-in default when no copilot role exists", () => {
    const html = renderToStaticMarkup(
      <CopilotTab data={emptyRoles()} credentials={credentials()} modelGroups={[opusGroup("claude-opus-4.8", "Claude Opus 4.8")]} />,
    )
    expect(html).toContain("Claude Opus 4.8")
    expect(html).toContain('data-copilot-role-source="built_in"')
    expect(html).toContain("Built-in")
  })

  it("prefers opus-4.8 over 4.7 when both are available", () => {
    const html = renderToStaticMarkup(
      <CopilotTab
        data={emptyRoles()}
        credentials={credentials()}
        modelGroups={[opusGroup("claude-opus-4.7", "Claude Opus 4.7"), opusGroup("claude-opus-4.8", "Claude Opus 4.8")]}
      />,
    )
    expect(html).toContain("Claude Opus 4.8")
    // 4.7 is not the floated default, so it is NOT surfaced as a built-in card
    expect(html).not.toContain("Claude Opus 4.7")
  })

  it("floats nothing (and seeds no mock) when no ladder model is available", () => {
    const html = renderToStaticMarkup(
      <CopilotTab data={emptyRoles()} credentials={credentials()} modelGroups={[opusGroup("some-other-model", "Some Other Model")]} />,
    )
    expect(html).not.toContain('data-copilot-role-card="true"')
  })
})

describe("CopilotTab broken-legacy copilot record skip (no group binding + has fallback_chain)", () => {
  it("skips a copilot record that has fallback_chain but no model_groups/models, falling back to #56 float defaults", () => {
    const brokenLegacy: RolesData = {
      ...emptyRoles(),
      roles: {
        copilot_opus_4_7: {
          role_kind: "copilot",
          system_prompt_prefix: "",
          model_fallback_enabled: true,
          intent: { provider_preference: "manual_order" },
          model_groups: [],
          active_model: "",
          models: {},
          fallback_chain: [
            { route_id: "anthropic-official:claude-opus-4-7", runtime_settings: {} },
            { route_id: "qiniu-anthropic:claude-opus-4-7", runtime_settings: {} },
          ],
          lint_requirements: {},
        },
      },
    }
    const html = renderToStaticMarkup(
      <CopilotTab data={brokenLegacy} credentials={credentials()} modelGroups={[opusGroup("claude-opus-4.7", "Claude Opus 4.7")]} />,
    )
    // The broken legacy record's title 'Copilot Opus 4 7' must not appear; the
    // float-default Built-in card with the canonical display name does.
    expect(html).not.toContain("Copilot Opus 4 7")
    expect(html).toContain("Claude Opus 4.7")
    expect(html).toContain('data-copilot-role-source="built_in"')
  })

  it("keeps an Add-model draft (no model_groups/models AND empty fallback_chain) so the EmptyCard renders", () => {
    const html = renderToStaticMarkup(
      <CopilotTab data={rolesWithDraft()} credentials={credentials()} modelGroups={registryModelGroups()} />,
    )
    expect(html).toContain('data-copilot-empty-role-card="true"')
  })
})

describe("CopilotTab #61 model-group remove control", () => {
  it("renders an enabled group-level Remove button on a configured role", () => {
    const html = renderToStaticMarkup(
      <CopilotTab data={roles()} credentials={credentials()} modelGroups={registryModelGroups()} />,
    )
    const removeButton = html.match(/<button[^>]*data-copilot-model-group-remove="true"[^>]*>/)
    expect(removeButton).not.toBeNull()
    expect(removeButton?.[0]).not.toContain('disabled=""')
  })
})

describe("CopilotTab #63 searchable model-group combobox", () => {
  it("renders a combobox trigger (not a native select) on the empty draft card", () => {
    const html = renderToStaticMarkup(
      <CopilotTab data={rolesWithDraft()} credentials={credentials()} modelGroups={registryModelGroups()} />,
    )
    const trigger = html.match(/<button[^>]*data-copilot-model-group-select="true"[^>]*>/)
    expect(trigger).not.toBeNull()
    expect(trigger?.[0]).toContain('role="combobox"')
  })
})

describe("copilotGroupComboboxFilter — searchable picker matching (atom-63 ②)", () => {
  function previewRoute(providerLabel: string, providerModelId: string): CopilotRoutePreview {
    return {
      id: `${providerLabel}:${providerModelId}`,
      route_id: `${providerLabel}:${providerModelId}`,
      endpointId: providerLabel,
      providerLabel,
      providerKind: "third_party",
      providerModelId,
      uiState: "ready",
      agentStatus: "ready",
      capabilities: {},
      provider: providerLabel,
      modelId: providerModelId,
      methodId: null,
      note: null,
    }
  }
  const preview: CopilotRolePreview = {
    id: "claude-opus-4.8",
    title: "Claude Opus 4.8",
    description: "Claude Opus 4.8",
    source: "built_in",
    modelLabel: "Claude Opus 4.8",
    sdkId: "claude-agent-sdk",
    activeRouteIds: [],
    availableRoutes: [previewRoute("Qiniu Anthropic", "claude-opus-4-8")],
    routes: [],
  }
  const haystack = copilotGroupSearchValue(preview)

  it("requires every token to match (multi-token AND)", () => {
    expect(copilotGroupComboboxFilter(haystack, "claude opus")).toBe(1)
    expect(copilotGroupComboboxFilter(haystack, "claude gpt")).toBe(0)
  })

  it("matches compactly, ignoring separators", () => {
    expect(copilotGroupComboboxFilter(haystack, "opus-4.8")).toBe(1)
    expect(copilotGroupComboboxFilter(haystack, "opus4.8")).toBe(1)
  })

  it("searches canonical id, provider label and provider model id — not just the display name", () => {
    expect(copilotGroupComboboxFilter(haystack, "qiniu")).toBe(1) // provider label
    expect(copilotGroupComboboxFilter(haystack, "claude-opus-4-8")).toBe(1) // provider model id
  })

  it("shows every option for an empty query", () => {
    expect(copilotGroupComboboxFilter(haystack, "")).toBe(1)
  })
})

describe("R-F6 rebuildFallbackChainPreservingRuntime", () => {
  it("keeps runtime_settings for routes that existed before reorder", () => {
    const before = [
      { route_id: "A", runtime_settings: { max_tokens: 8192, model_id: "claude-opus-4-7" } },
      { route_id: "B", runtime_settings: { max_tokens: 4096 } },
    ]
    const after = rebuildFallbackChainPreservingRuntime(before, ["B", "A"])
    // R-F6 acceptance #1: existing entries keep their runtime_settings.
    expect(after).toEqual([
      { route_id: "B", runtime_settings: { max_tokens: 4096 } },
      { route_id: "A", runtime_settings: { max_tokens: 8192, model_id: "claude-opus-4-7" } },
    ])
  })

  it("seeds new route ids with empty runtime_settings", () => {
    const before = [
      { route_id: "A", runtime_settings: { max_tokens: 8192 } },
    ]
    const after = rebuildFallbackChainPreservingRuntime(before, ["A", "C"])
    expect(after).toEqual([
      { route_id: "A", runtime_settings: { max_tokens: 8192 } },
      // R-F6 acceptance #2: new route id starts at {} (nothing to preserve).
      { route_id: "C", runtime_settings: {} },
    ])
  })

  it("handles a missing runtime_settings on the input gracefully", () => {
    const before = [{ route_id: "A" } as { route_id: string; runtime_settings?: Record<string, unknown> }]
    const after = rebuildFallbackChainPreservingRuntime(before, ["A"])
    expect(after).toEqual([{ route_id: "A", runtime_settings: {} }])
  })
})

describe("R-F5 copilot yaml key helpers", () => {
  // B1: yaml keys must match `[a-z][a-z0-9_]*` so a model-group id with
  // hyphens or dots can't be used directly. The helper canonicalizes via
  // `replace(/[^a-zA-Z0-9]+/g,'_').toLowerCase()` and prepends `copilot_`.
  it("copilotKeyForGroupId — turns 'claude-opus-4.8' into 'copilot_claude_opus_4_8'", () => {
    expect(copilotKeyForGroupId("claude-opus-4.8")).toBe("copilot_claude_opus_4_8")
    expect(copilotKeyForGroupId("DeepSeek V3.2-Pro")).toBe("copilot_deepseek_v3_2_pro")
    expect(copilotKeyForGroupId("a:b/c.d")).toBe("copilot_a_b_c_d")
  })

  it("nextCopilotCustomIndex — picks max+1, not count+1 (collision-safe)", () => {
    // Empty → start at 1.
    expect(nextCopilotCustomIndex([])).toBe(1)
    // Sequential → 4.
    expect(nextCopilotCustomIndex(["copilot_custom_1", "copilot_custom_2", "copilot_custom_3"])).toBe(4)
    // Middle id missing — must NOT recycle _2 (would overwrite the slot
    // a future load could resurrect from yaml).
    expect(nextCopilotCustomIndex(["copilot_custom_1", "copilot_custom_3"])).toBe(4)
    // Non-numeric tail ignored.
    expect(nextCopilotCustomIndex(["copilot_custom_xyz", "copilot_custom_2"])).toBe(3)
    // Non-copilot-custom keys ignored.
    expect(nextCopilotCustomIndex(["copilot_opus_4_7", "claude_opus_4_8"])).toBe(1)
  })
})

describe("R-F12 empty-state CTA + per-card untested warning", () => {
  function emptyCredentials(): CredentialsState {
    return { providers: [] }
  }

  it("renders EmptyCopilotState with CTA when no anthropic-messages route exists", () => {
    const html = renderToStaticMarkup(
      <CopilotTab
        data={emptyRoles()}
        credentials={emptyCredentials()}
        modelGroups={[]}
        onNavigateToApiKeys={() => undefined}
      />,
    )
    expect(html).toContain('data-copilot-empty-state="true"')
    expect(html).toContain("No Anthropic Messages route yet")
    expect(html).toContain("Go to API Keys")
  })

  it("CTA button is disabled when no onNavigateToApiKeys is wired (degrade visibly)", () => {
    const html = renderToStaticMarkup(
      <CopilotTab data={emptyRoles()} credentials={emptyCredentials()} modelGroups={[]} />,
    )
    const cta = html.match(/<button[^>]*data-copilot-empty-cta="true"[^>]*>/)
    expect(cta?.[0]).toContain('disabled=""')
  })

  it("renders per-card 'N routes untested' chip when readyCount === 0 but routes exist", () => {
    // Single untested route → ready=0, total=1 → chip appears.
    const untestedGroup: ModelGroup = {
      ...opusGroup("claude-opus-4.8", "Claude Opus 4.8"),
      provider_models: [
        {
          ...opusGroup("claude-opus-4.8", "Claude Opus 4.8").provider_models[0],
          ui_state: "untested",
        },
      ],
    }
    const html = renderToStaticMarkup(
      <CopilotTab
        data={emptyRoles()}
        credentials={credentials()}
        modelGroups={[untestedGroup]}
        onNavigateToApiKeys={() => undefined}
      />,
    )
    expect(html).toContain('data-copilot-untested-warning="true"')
    expect(html).toContain("1 route has not been tested")
  })
})

describe("R-F14 Add-model defrag", () => {
  it("disables Add when there is already an empty draft card", () => {
    const html = renderToStaticMarkup(
      <CopilotTab data={rolesWithDraft()} credentials={credentials()} modelGroups={registryModelGroups()} />,
    )
    const addBtn = html.match(/<button[^>]*data-copilot-model-add-trigger="true"[^>]*>/)
    expect(addBtn).not.toBeNull()
    expect(addBtn?.[0]).toContain('disabled=""')
    expect(addBtn?.[0]).toContain('data-disabled="true"')
  })

  it("keeps Add enabled when every existing card is bound to a model group", () => {
    const html = renderToStaticMarkup(
      <CopilotTab data={roles()} credentials={credentials()} modelGroups={registryModelGroups()} />,
    )
    const addBtn = html.match(/<button[^>]*data-copilot-model-add-trigger="true"[^>]*>/)
    expect(addBtn).not.toBeNull()
    expect(addBtn?.[0]).not.toContain('disabled=""')
    expect(addBtn?.[0]).toContain('data-disabled="false"')
  })
})

describe("R-F7 Test button waits for in-flight save", () => {
  it("renders Test button as disabled when saveStatus is 'saving'", () => {
    const html = renderToStaticMarkup(
      <CopilotTab
        data={roles()}
        credentials={credentials()}
        modelGroups={registryModelGroups()}
        saveStatus="saving"
      />,
    )
    const testBtn = html.match(/<button[^>]*data-copilot-test-chain="true"[^>]*>/)
    expect(testBtn).not.toBeNull()
    expect(testBtn?.[0]).toContain('disabled=""')
    expect(testBtn?.[0]).toContain('data-copilot-test-save-pending="true"')
  })

  it("keeps Test button enabled when saveStatus is 'idle'", () => {
    const html = renderToStaticMarkup(
      <CopilotTab
        data={roles()}
        credentials={credentials()}
        modelGroups={registryModelGroups()}
        saveStatus="idle"
      />,
    )
    const testBtn = html.match(/<button[^>]*data-copilot-test-chain="true"[^>]*>/)
    expect(testBtn).not.toBeNull()
    expect(testBtn?.[0]).not.toContain('disabled=""')
    expect(testBtn?.[0]).toContain('data-copilot-test-save-pending="false"')
  })
})

describe("R-F15 saveStatus badge in tab header", () => {
  it("renders the saving badge when saveStatus is 'saving'", () => {
    const html = renderToStaticMarkup(
      <CopilotTab
        data={emptyRoles()}
        credentials={credentials()}
        modelGroups={registryModelGroups()}
        saveStatus="saving"
      />,
    )
    // SaveStatusBadge exposes its state on a stable data attribute so tests
    // don't depend on the localized label.
    expect(html).toContain('data-save-status-badge="true"')
    expect(html).toContain('data-save-status="saving"')
  })

  it("renders the saved badge when saveStatus is 'saved'", () => {
    const html = renderToStaticMarkup(
      <CopilotTab
        data={emptyRoles()}
        credentials={credentials()}
        modelGroups={registryModelGroups()}
        saveStatus="saved"
      />,
    )
    expect(html).toContain('data-save-status-badge="true"')
    expect(html).toContain('data-save-status="saved"')
  })

  it("renders nothing visible for idle state (badge collapses)", () => {
    const html = renderToStaticMarkup(
      <CopilotTab
        data={emptyRoles()}
        credentials={credentials()}
        modelGroups={registryModelGroups()}
        saveStatus="idle"
      />,
    )
    expect(html).not.toContain('data-save-status-badge="true"')
  })
})

describe("R-F16 copilot test toast text is routed through i18n", () => {
  // i18n contract: the keys CopilotTab's testRoleRoutes() emits via
  // `t('copilot.testToast.passed' | 'needsAttention' | 'failed', { title })`
  // must exist in BOTH en + zh-CN bundles, and the en/zh strings must include
  // the {{title}} placeholder so role names get interpolated.
  it("en bundle defines copilot.testToast.{passed,needsAttention,failed}", async () => {
    const en = (await import("@/locales/en/settings.json")).default
    expect(en.copilot.testToast.passed).toContain("{{title}}")
    expect(en.copilot.testToast.needsAttention).toContain("{{title}}")
    expect(en.copilot.testToast.failed).toContain("{{title}}")
  })

  it("zh-CN bundle defines copilot.testToast.{passed,needsAttention,failed}", async () => {
    const zh = (await import("@/locales/zh-CN/settings.json")).default
    expect(zh.copilot.testToast.passed).toContain("{{title}}")
    expect(zh.copilot.testToast.needsAttention).toContain("{{title}}")
    expect(zh.copilot.testToast.failed).toContain("{{title}}")
    // R-F16 acceptance: zh-CN copy is actually translated (not the en string).
    expect(zh.copilot.testToast.passed).toContain("测试通过")
    expect(zh.copilot.testToast.needsAttention).toContain("测试")
  })
})

describe("R-F17 copilot a11y aria keys are routed through i18n", () => {
  it("en bundle defines copilot.aria.{testing,ready}", async () => {
    const en = (await import("@/locales/en/settings.json")).default
    expect(en.copilot.aria.testing).toContain("{{title}}")
    expect(en.copilot.aria.ready).toContain("{{title}}")
    expect(en.copilot.aria.ready).toContain("{{ready}}")
    expect(en.copilot.aria.ready).toContain("{{total}}")
  })

  it("zh-CN bundle defines copilot.aria.{testing,ready}", async () => {
    const zh = (await import("@/locales/zh-CN/settings.json")).default
    expect(zh.copilot.aria.testing).toContain("{{title}}")
    expect(zh.copilot.aria.ready).toContain("{{title}}")
    expect(zh.copilot.aria.ready).toContain("{{ready}}")
    expect(zh.copilot.aria.ready).toContain("{{total}}")
    expect(zh.copilot.aria.testing).toContain("正在测试")
  })
})

describe("R-F21 cooldown helpers (FE side)", () => {
  // The Test Button's disabled/countdown behavior derives from two pure helpers
  // wired into CopilotTab's effect / props: `copilotRouteCooldownsFromJob` (live
  // poll) and `copilotRouteCooldownsFromPersistedResult` (mount seed). Exercising
  // the pure helpers covers the cooldown wiring contract without standing up a
  // DOM (this repo's vitest uses the node env, no @testing-library/react).
  it("copilotRouteCooldownsFromJob picks up retry_after_seconds for cooling_down routes only", async () => {
    const { copilotRouteCooldownsFromJob } = await import("./copilot-role-test")
    const job: import("@/api/llm").RoleTestJobResponse = {
      job_id: "j-cd",
      role_name: "copilot_opus",
      status: "running",
      message: null,
      provider_statuses: [
        {
          canonical_id: "claude-opus-4-7",
          route_id: "anthropic-official:claude-opus-4-7",
          status: "cooling_down",
          retry_after_seconds: 42,
        },
        // Non-cooldown routes are skipped even if they happen to carry a value.
        {
          canonical_id: "claude-opus-4-7",
          route_id: "qiniu-anthropic:claude-opus-4-7",
          status: "ok",
          retry_after_seconds: 99,
        },
      ],
      result: null,
    }
    expect(copilotRouteCooldownsFromJob(job)).toEqual({
      "anthropic-official:claude-opus-4-7": 42,
    })
  })

  it("copilotRouteCooldownsFromPersistedResult rehydrates persisted cooldown after remount", async () => {
    const { copilotRouteCooldownsFromPersistedResult } = await import("./copilot-role-test")
    const persisted = {
      sdk_evidence: {
        routes: {
          "anthropic-official:claude-opus-4-7": {
            status: "cooling_down",
            retry_after_seconds: 30,
          },
          // Non-cooldown verdicts contribute nothing to the cooldown map.
          "qiniu-anthropic:claude-opus-4-7": {
            status: "ok",
            retry_after_seconds: null,
          },
        },
      },
    }
    expect(copilotRouteCooldownsFromPersistedResult(persisted)).toEqual({
      "anthropic-official:claude-opus-4-7": 30,
    })
  })

  it("copilotRouteCooldownsFromPersistedResult skips entries without a positive retry value", async () => {
    const { copilotRouteCooldownsFromPersistedResult } = await import("./copilot-role-test")
    const persisted = {
      sdk_evidence: {
        routes: {
          "a": { status: "cooling_down", retry_after_seconds: 0 },
          "b": { status: "cooling_down" }, // no retry hint
          "c": { status: "cooling_down", retry_after_seconds: "soon" }, // wrong type
          "d": { status: "cooling_down", retry_after_seconds: 5 },
        },
      },
    }
    expect(copilotRouteCooldownsFromPersistedResult(persisted)).toEqual({ d: 5 })
  })
})

describe("R-F18 dnd-kit keyboard sensor wiring for copilot route reorder", () => {
  // The card wires `useSensors(PointerSensor, KeyboardSensor)` with
  // `sortableKeyboardCoordinates` so users can Tab to a chip, Space to lift,
  // arrow-keys to move, Space again to drop — without a mouse. dnd-kit's
  // KeyboardSensor doesn't surface anything via SSR HTML, so we assert the
  // import wiring on the module source as a regression guard (preventing a
  // future refactor from dropping the keyboard sensor).
  it("CopilotModelGroupCard imports KeyboardSensor + sortableKeyboardCoordinates and registers them", async () => {
    const source = await readFile(
      new URL("./CopilotModelGroupCard.tsx", import.meta.url),
      "utf8",
    )
    expect(source).toContain("KeyboardSensor")
    expect(source).toContain("sortableKeyboardCoordinates")
    expect(source).toMatch(/useSensor\(\s*KeyboardSensor/)
    expect(source).toMatch(/coordinateGetter:\s*sortableKeyboardCoordinates/)
  })
})

describe("R-F17 a11y aria-busy / aria-live", () => {
  // The Test Button uses aria-busy={isTesting}. SSR snapshots only catch the
  // resting state (isTesting=false), so we assert the attr is emitted and the
  // companion sr-only live region renders the 'ready' phrase by default. Mid-
  // probe behavior is covered by the integration test on testRoleRoutes().
  it("Test button renders aria-busy='false' at rest plus a polite sr-only live region", () => {
    const html = renderToStaticMarkup(
      <CopilotTab data={roles()} credentials={credentials()} modelGroups={registryModelGroups()} />,
    )
    const testBtn = html.match(/<button[^>]*data-copilot-test-chain="true"[^>]*>/)
    expect(testBtn).not.toBeNull()
    expect(testBtn?.[0]).toContain('aria-busy="false"')
    // sr-only live region accompanies the button — emits the ready/total
    // phrase the screen reader reads when probes update the route counts.
    const liveRegion = html.match(/<span[^>]*data-copilot-test-live-status="true"[^>]*>([^<]*)<\/span>/)
    expect(liveRegion).not.toBeNull()
    expect(liveRegion?.[0]).toContain('aria-live="polite"')
    expect(liveRegion?.[0]).toContain('class="sr-only"')
    // Default 'ready' phrase uses the i18n key under the SSR mock that echoes keys.
    expect(liveRegion?.[1]).toContain("copilot.aria.ready")
  })

  it("route grid container exposes aria-live='polite' so route light changes announce politely", () => {
    const html = renderToStaticMarkup(
      <CopilotTab data={roles()} credentials={credentials()} modelGroups={registryModelGroups()} />,
    )
    const grid = html.match(/<div[^>]*data-copilot-provider-grid="true"[^>]*>/)
    expect(grid).not.toBeNull()
    expect(grid?.[0]).toContain('aria-live="polite"')
    expect(grid?.[0]).toContain('role="list"')
  })
})

describe("R-F11 6-state copilot route lights", () => {
  // Build a model group whose two provider_models exercise each of the 6 backend
  // ui_state values so we can SSR the tab and assert each route surface renders
  // with the matching data-agent-sdk-status + aria-label (which the route light
  // derives from). The override map lets us paint testing/cooling_down/etc on
  // top of the backend snapshot without needing a live SDK probe.
  function sixStateGroups(): ModelGroup[] {
    const states: Array<{ id: string; ui_state: ModelGroup["provider_models"][number]["ui_state"] }> = [
      { id: "anthropic-official:claude-opus-4-7", ui_state: "ready" },
      { id: "anthropic-official:claude-opus-4-7-hist", ui_state: "historical_ready" },
      { id: "anthropic-official:claude-opus-4-7-untested", ui_state: "untested" },
      { id: "anthropic-official:claude-opus-4-7-failed", ui_state: "failed" },
      { id: "anthropic-official:claude-opus-4-7-cooldown", ui_state: "cooling_down" },
      { id: "anthropic-official:claude-opus-4-7-off", ui_state: "off" },
    ]
    return [
      {
        canonical_id: "claude-opus-4.7",
        display_name: "Claude Opus 4.7",
        provider_models: states.map(({ id, ui_state }) => ({
          route_id: id,
          endpoint_id: "anthropic-official",
          provider_label: "Anthropic Official",
          provider_kind: "official",
          provider_model_id: id.split(":")[1] ?? id,
          ui_state,
          ui_detail: null,
          retry_at: null,
          reason_code: null,
          capability_state: "known",
          capabilities: {},
          call_method_id: "anthropic_messages",
        })),
        status_summary: {
          ready: 1,
          untested: 1,
          cooling_down: 1,
          historical_ready: 1,
          failed: 1,
          off: 1,
        },
        capability_summary: {
          capability_known_count: 6,
          thinking: "unknown",
          tools: "unknown",
          structured_output: "unknown",
          max_context_tokens: null,
          max_output_tokens: null,
        },
      },
    ]
  }

  function sixStateRoles(): RolesData {
    return {
      schema_version: 3,
      models: {},
      providers: {},
      model_profiles: {},
      model_bundles: {},
      roles: {
        copilot_opus: {
          role_kind: "copilot",
          system_prompt_prefix: "",
          model_fallback_enabled: true,
          intent: { provider_preference: "manual_order" },
          model_groups: [],
          active_model: "claude-opus-4.7",
          models: {
            "claude-opus-4.7": {
              providers: [
                "anthropic-official:claude-opus-4-7",
                "anthropic-official:claude-opus-4-7-hist",
                "anthropic-official:claude-opus-4-7-untested",
                "anthropic-official:claude-opus-4-7-failed",
                "anthropic-official:claude-opus-4-7-cooldown",
                "anthropic-official:claude-opus-4-7-off",
              ],
            },
          },
          fallback_chain: [
            { route_id: "anthropic-official:claude-opus-4-7", runtime_settings: {} },
            { route_id: "anthropic-official:claude-opus-4-7-hist", runtime_settings: {} },
            { route_id: "anthropic-official:claude-opus-4-7-untested", runtime_settings: {} },
            { route_id: "anthropic-official:claude-opus-4-7-failed", runtime_settings: {} },
            { route_id: "anthropic-official:claude-opus-4-7-cooldown", runtime_settings: {} },
            { route_id: "anthropic-official:claude-opus-4-7-off", runtime_settings: {} },
          ],
          lint_requirements: {},
        },
      },
    }
  }

  it("each of the 6 backend ui_state values renders its own route surface attr (data-agent-sdk-status)", () => {
    const html = renderToStaticMarkup(
      <CopilotTab
        data={sixStateRoles()}
        credentials={credentials()}
        modelGroups={sixStateGroups()}
      />,
    )

    // R-F11: each ProviderUiState maps 1:1 to a route surface light value.
    // We assert via the `data-agent-sdk-status` attr rendered on every route
    // chip (`CopilotProviderTag`), which is the public hook the tests use.
    expect(html).toContain('data-agent-sdk-status="ready"')
    expect(html).toContain('data-agent-sdk-status="historical_ready"')
    expect(html).toContain('data-agent-sdk-status="untested"')
    expect(html).toContain('data-agent-sdk-status="failed"')
    expect(html).toContain('data-agent-sdk-status="cooling_down"')
    expect(html).toContain('data-agent-sdk-status="off"')
  })

  it("aria-label for each state surfaces the spec'd Ready/Previously/Untested/Failed/Cooling/Off vocabulary", () => {
    const html = renderToStaticMarkup(
      <CopilotTab
        data={sixStateRoles()}
        credentials={credentials()}
        modelGroups={sixStateGroups()}
      />,
    )

    expect(html).toContain("Claude Agent SDK Ready")
    expect(html).toContain("Claude Agent SDK Previously Connected")
    expect(html).toContain("Claude Agent SDK Untested")
    expect(html).toContain("Claude Agent SDK Failed")
    expect(html).toContain("Claude Agent SDK Cooling Down")
    expect(html).toContain("Claude Agent SDK Off")
  })
})
