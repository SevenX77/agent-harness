import { describe, expect, it } from "vitest"
import { routeToolCallingTooltipText } from "./ProviderCard"
import type { ModelInfo } from "../../../api/llm"

/**
 * Whether a route can run an agent phase is a fact the route now carries, and
 * the tooltip is where a reader looks for facts about a route.
 *
 * The gateway settled the measurement (#969) and the host wired it to the route
 * probe (#972), so `tool_protocol` is real data — but nothing on screen said so,
 * which is problem-ledger L6's remaining「UI 呈现」. It reads off `source` and
 * `message_code`, never the English `message`: the message is for logs, and
 * rendering it would show English to a reader who asked for another language.
 */

function model(capabilities: Record<string, unknown> | undefined): ModelInfo {
  return { id: "m1", capabilities } as unknown as ModelInfo
}

describe("routeToolCallingTooltipText", () => {
  it("says the route came back with the result when the loop closed", () => {
    const text = routeToolCallingTooltipText(model({
      tool_protocol: { value: true, source: "probed_verified", message_code: "tool_loop_closed_the_loop" },
    }))

    expect(text).toBe("Tools: called one and came back with the result")
  })

  it("says only that it called one when that is all that was seen", () => {
    // The two rungs are a real difference to someone deciding whether to hand
    // this route an agent phase, and they are only distinguishable because the
    // gateway carries a code — matching English prose would be the alternative.
    const text = routeToolCallingTooltipText(model({
      tool_protocol: { value: true, source: "probed_verified", message_code: "tool_loop_called_the_tool" },
    }))

    expect(text).toBe("Tools: called one when asked")
  })

  it("still reports a measurement whose code it does not recognise", () => {
    // A newer gateway may name an observation this build has no wording for.
    // `probed_verified` alone already answers the question that matters.
    const text = routeToolCallingTooltipText(model({
      tool_protocol: { value: true, source: "probed_verified", message_code: "tool_loop_something_newer" },
    }))

    expect(text).toBe("Tools: measured on this route")
  })

  it("marks a documented claim as documented, not as something anyone watched", () => {
    const text = routeToolCallingTooltipText(model({
      tool_protocol: { value: true, source: "provider_doc" },
    }))

    expect(text).toBe("Tools: listed by the provider, not measured")
  })

  it("says nothing at all when no one has answered the question", () => {
    // Absence means unmeasured, never "cannot" — the gateway refuses to write
    // False precisely because those two are indistinguishable. A line here would
    // also appear on almost every route and carry no information; this tooltip
    // reports what is KNOWN about a route and stays quiet otherwise.
    expect(routeToolCallingTooltipText(model({}))).toBeNull()
    expect(routeToolCallingTooltipText(model(undefined))).toBeNull()
  })

  it("says nothing when the capability is present but not affirmative", () => {
    // Nothing writes False today, but a tooltip that read a false value as
    // "measured" would be asserting the one thing the ladder refuses to claim.
    expect(routeToolCallingTooltipText(model({
      tool_protocol: { value: false, source: "probed_verified" },
    }))).toBeNull()
  })
})
