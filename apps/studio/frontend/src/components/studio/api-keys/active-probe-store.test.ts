import { describe, expect, it, vi } from "vitest"
import {
  clearActiveProbeEndpoint,
  subscribeActiveProbeAtom,
  subscribeActiveProbeEndpoint,
  updateActiveProbeEndpoint,
} from "./active-probe-store"

describe("active probe store", () => {
  it("notifies only the endpoint/model atoms whose active state changed", () => {
    const targetModel = vi.fn()
    const siblingModel = vi.fn()
    const otherEndpointModel = vi.fn()
    const targetEndpoint = vi.fn()
    const otherEndpoint = vi.fn()

    const unsubscribeTargetModel = subscribeActiveProbeAtom("endpoint-a", "model-a", targetModel)
    const unsubscribeSiblingModel = subscribeActiveProbeAtom("endpoint-a", "model-b", siblingModel)
    const unsubscribeOtherEndpointModel = subscribeActiveProbeAtom("endpoint-b", "model-a", otherEndpointModel)
    const unsubscribeTargetEndpoint = subscribeActiveProbeEndpoint("endpoint-a", targetEndpoint)
    const unsubscribeOtherEndpoint = subscribeActiveProbeEndpoint("endpoint-b", otherEndpoint)

    try {
      updateActiveProbeEndpoint("endpoint-a", ["model-a"])

      expect(targetModel).toHaveBeenCalledTimes(1)
      expect(targetEndpoint).toHaveBeenCalledTimes(1)
      expect(siblingModel).not.toHaveBeenCalled()
      expect(otherEndpointModel).not.toHaveBeenCalled()
      expect(otherEndpoint).not.toHaveBeenCalled()

      updateActiveProbeEndpoint("endpoint-a", ["model-a"])

      expect(targetModel).toHaveBeenCalledTimes(1)
      expect(targetEndpoint).toHaveBeenCalledTimes(1)

      updateActiveProbeEndpoint("endpoint-a", ["model-b"])

      expect(targetModel).toHaveBeenCalledTimes(2)
      expect(siblingModel).toHaveBeenCalledTimes(1)
      expect(targetEndpoint).toHaveBeenCalledTimes(2)
      expect(otherEndpointModel).not.toHaveBeenCalled()
      expect(otherEndpoint).not.toHaveBeenCalled()
    } finally {
      clearActiveProbeEndpoint("endpoint-a")
      clearActiveProbeEndpoint("endpoint-b")
      unsubscribeTargetModel()
      unsubscribeSiblingModel()
      unsubscribeOtherEndpointModel()
      unsubscribeTargetEndpoint()
      unsubscribeOtherEndpoint()
    }
  })
})
