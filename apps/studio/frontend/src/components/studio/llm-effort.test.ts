import { describe, expect, it } from "vitest"
import { effortLevelsFromCapabilities, formatEffortLabel, PROVIDER_DEFAULT_EFFORT } from "./llm-effort"

describe("effortLevelsFromCapabilities", () => {
  it("offers every level any of the role's routes sells", () => {
    const levels = effortLevelsFromCapabilities([
      { reasoning_effort: { value: { values: ["low", "high"] }, source: "probed_verified" } },
      { reasoning_effort: { value: { values: ["minimal", "low", "medium", "high"] }, source: "provider_doc" } },
    ])

    expect(levels).toEqual(["minimal", "low", "medium", "high"])
  })

  it("orders levels weakest first however the routes listed them", () => {
    const levels = effortLevelsFromCapabilities([
      { reasoning_effort: { value: { values: ["max", "low", "xhigh"] }, source: "probed_verified" } },
    ])

    expect(levels).toEqual(["low", "xhigh", "max"])
  })

  it("keeps a level it cannot rank rather than dropping it", () => {
    const levels = effortLevelsFromCapabilities([
      { reasoning_effort: { value: { values: ["low", "turbo"] }, source: "probed_verified" } },
    ])

    expect(levels).toEqual(["low", "turbo"])
  })

  it("offers nothing when no route says anything about effort", () => {
    expect(effortLevelsFromCapabilities([{}, { thinking_protocol: { value: true, source: "api_list" } }])).toEqual([])
  })

  it("names the absent choice with a value a Select can carry", () => {
    // Radix rejects "" as an item value: it reserves it for clearing the Select.
    expect(PROVIDER_DEFAULT_EFFORT).not.toBe("")
    expect(formatEffortLabel("xhigh")).toBe("Extra high")
    expect(formatEffortLabel("low")).toBe("Low")
  })
})
