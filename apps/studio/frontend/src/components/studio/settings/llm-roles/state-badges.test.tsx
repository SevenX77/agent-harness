import { renderToStaticMarkup } from "react-dom/server"
import { describe, expect, it } from "vitest"
import type { ProviderModelOption, ProviderUiState } from "@/api/llm"
import { CoolingDownCountdown, formatCoolingDownRemaining } from "./cooling-down-countdown"
import { ProviderStateBadge } from "./provider-state-badge"
import {
  deriveRoleRouteStatus,
  RoleProviderRouteTooltipContent,
  roleProviderRouteTooltip,
  roleRouteStatusDetail,
  RoleRouteStatusLight,
} from "./role-route-status"

describe("LLM role state badges", () => {
  it("renders exactly the six provider state labels", () => {
    const html = renderToStaticMarkup(
      <>
        <ProviderStateBadge state="ready" />
        <ProviderStateBadge state="historical_ready" detail="Previously connected from shared probe evidence." />
        <ProviderStateBadge state="untested" />
        <ProviderStateBadge state="cooling_down" retryAt="2026-05-26T18:30:00Z" />
        <ProviderStateBadge state="failed" reasonCode="model_failed" detail="Model does not exist." />
        <ProviderStateBadge state="off" />
      </>,
    )

    expect(html).toContain("Ready")
    expect(html).toContain("Previously Connected")
    expect(html).toContain("Untested")
    expect(html).toContain("Cooling Down")
    expect(html).toContain("Failed")
    expect(html).toContain("Off")
    expect(html).toContain('data-provider-state-label="historical_ready"')
    expect(html).toContain('data-provider-state-label="failed"')
    expect(html).not.toContain('data-provider-state-label="needs_setup"')
    expect(html).not.toContain(">model_failed<")
  })

  it("keeps role provider status compact and puts exact diagnostics on the status light", () => {
    const detail = roleRouteStatusDetail({
      providerModel: providerModel("cooling_down", {
        ui_detail: "Retry after transient rate limit.",
        retry_at: "2026-05-26T18:30:00Z",
      }),
      roleFitEntry: {
        route_id: "cooling:gpt-5",
        role_fit: "needs_test",
        warnings: [{ code: "thinking_capability_unknown" }],
      },
    })
    const html = renderToStaticMarkup(
      <RoleRouteStatusLight status="limited" detail={detail} />,
    )

    expect(detail).toContain("Thinking is required but capability is unknown.")
    expect(detail).toContain("Cooling Down: Retry after transient rate limit.")
    expect(html).toContain('data-role-route-status-light="true"')
    expect(html).toContain("Limited:")
    expect(html).toContain("Thinking is required but capability is unknown.")
    expect(html).not.toMatch(/>Can Run<\/span>|>Limited<\/span>|>Blocked<\/span>/)
    expect(html).not.toContain("Using")
    expect(html).not.toContain("Downgraded")
    expect(html).not.toContain("Needs Test")
    expect(html).not.toContain("Not Fit")
  })

  it("builds provider row tooltip from the real model name, capabilities, and role fit", () => {
    const tooltip = roleProviderRouteTooltip({
      status: "runnable",
      providerModel: providerModel("ready", {
        provider_model_id: "claude-haiku-4-5-20251001",
        capability_state: "known",
        capabilities: {
          verified_methods: { value: ["anthropic_messages"], source: "probed_verified" },
          input_modalities: { value: ["text", "image", "pdf"], source: "probed_verified" },
          output_modalities: { value: ["text"], source: "probed_verified" },
          thinking_protocol: { value: true, source: "probed_verified" },
          max_input_tokens: { value: { max: 200000 }, source: "provider_doc" },
          max_output_tokens: { value: { max: 64000 }, source: "provider_doc" },
        },
      }),
      detail: null,
    })

    expect(tooltip.split("\n")[0]).toContain("claude-haiku-4-5-20251001")
    expect(tooltip.split("\n")[0]).toContain("reasoning")
    expect(tooltip).toContain("Methods: anthropic_messages")
    expect(tooltip).toContain("Input: text, image, PDF")
    expect(tooltip).toContain("Output: text")
    expect(tooltip).toContain("Max input: 200,000 tokens")
    expect(tooltip).toContain("Max output: 64,000 tokens")
    expect(tooltip).toContain("Role match: requirements satisfied.")
    expect(tooltip).not.toContain("This route can run")
  })

  it("marks warning and failed tooltip diagnostics with explicit labels and icons", () => {
    const warningTooltip = roleProviderRouteTooltip({
      status: "limited",
      providerModel: providerModel("ready"),
      fallbackProviderModelId: null,
      detail: "Thinking was preferred but is not enabled for this provider model.",
    })
    const failedTooltip = roleProviderRouteTooltip({
      status: "blocked",
      providerModel: providerModel("ready"),
      fallbackProviderModelId: null,
      detail: "Provider returned invalid credentials.",
    })

    const warningHtml = renderToStaticMarkup(
      <RoleProviderRouteTooltipContent tooltip={warningTooltip} />,
    )
    const failedHtml = renderToStaticMarkup(
      <RoleProviderRouteTooltipContent tooltip={failedTooltip} />,
    )

    expect(warningTooltip).toContain("Warning: Thinking was preferred")
    expect(failedTooltip).toContain("Failed: Provider returned invalid credentials.")
    expect(warningHtml).toContain('data-tooltip-diagnostic="warning"')
    expect(warningHtml).toContain('data-tooltip-diagnostic-icon="warning"')
    expect(failedHtml).toContain('data-tooltip-diagnostic="failed"')
    expect(failedHtml).toContain('data-tooltip-diagnostic-icon="failed"')
  })

  it("maps rich route and role-fit projections into three user states", () => {
    const readyProvider = providerModel("ready")

    expect(deriveRoleRouteStatus({
      providerModel: readyProvider,
      roleFitEntry: { route_id: "ready:gpt-5", role_fit: "using" },
    })).toBe("runnable")
    expect(deriveRoleRouteStatus({
      providerModel: readyProvider,
      roleFitEntry: { route_id: "limited:gpt-5", role_fit: "downgraded" },
    })).toBe("limited")
    expect(deriveRoleRouteStatus({
      providerModel: readyProvider,
      roleFitEntry: { route_id: "needs-test:gpt-5", role_fit: "needs_test" },
    })).toBe("limited")
    expect(deriveRoleRouteStatus({
      providerModel: readyProvider,
      roleFitEntry: { route_id: "blocked:gpt-5", role_fit: "not_fit" },
    })).toBe("blocked")
    expect(deriveRoleRouteStatus({
      providerModel: providerModel("historical_ready"),
      roleFitEntry: { route_id: "historical:gpt-5", role_fit: "using" },
    })).toBe("limited")
    expect(deriveRoleRouteStatus({
      providerModel: providerModel("failed"),
      roleFitEntry: { route_id: "failed:gpt-5", role_fit: "using" },
    })).toBe("blocked")
    expect(deriveRoleRouteStatus({
      providerModel: readyProvider,
      roleFitEntry: { route_id: "failed:gpt-5", role_fit: "using" },
      testStatus: "network_error",
    })).toBe("blocked")
  })

  it("formats Cooling Down countdowns and exposes a Test Now action", () => {
    const now = new Date("2026-05-26T18:28:55Z")
    const retryAt = "2026-05-26T18:30:00Z"
    const html = renderToStaticMarkup(
      <CoolingDownCountdown
        retryAt={retryAt}
        now={now}
        onTestNow={() => undefined}
      />,
    )

    expect(formatCoolingDownRemaining(retryAt, now)).toBe("1m 5s")
    expect(html).toContain("1m 5s")
    expect(html).toContain("Test Now")
    expect(html).not.toContain("route")
    expect(html).not.toContain("endpoint")
    expect(html).not.toContain("canonical")
  })
})

function providerModel(uiState: ProviderUiState, overrides: Partial<ProviderModelOption> = {}): ProviderModelOption {
  return {
    route_id: `${uiState}:gpt-5`,
    endpoint_id: uiState,
    provider_label: uiState,
    provider_kind: "third_party",
    provider_model_id: "gpt-5",
    ui_state: uiState,
    ui_detail: null,
    retry_at: null,
    reason_code: null,
    capability_state: "unknown",
    capabilities: {},
    ...overrides,
  }
}
