import { describe, expect, it } from "vitest"
import { computeDisplayValue, reverseDisplayDelta } from "./ApiKeyInput"

describe("computeDisplayValue", () => {
  it("returns the raw value when plain mode is on", () => {
    expect(computeDisplayValue("sk-secret", true)).toBe("sk-secret")
  })

  it("returns empty string for empty value regardless of mode", () => {
    expect(computeDisplayValue("", true)).toBe("")
    expect(computeDisplayValue("", false)).toBe("")
  })

  it("returns N bullets when masked, where N === value.length up to 32", () => {
    expect(computeDisplayValue("abc", false)).toBe("•••")
    expect(computeDisplayValue("a".repeat(40), false)).toBe("•".repeat(32))
  })
})

describe("reverseDisplayDelta", () => {
  // Spec C2 — five mask-state branches.

  it("passes through in plain (reveal) mode", () => {
    expect(reverseDisplayDelta("oldKey", "oldKey", "newKey", true)).toBe("newKey")
  })

  it("clears the real value when the masked display goes empty", () => {
    // User selected the whole display and hit Backspace.
    expect(reverseDisplayDelta("sk-secret", "•••••••••", "", false)).toBe("")
  })

  it("appends pasted characters onto the real value when display grows", () => {
    // Browser handed us 8 bullets (prior 6 + 2 new chars).
    expect(reverseDisplayDelta("sk-abc", "••••••", "••••••XY", false)).toBe("sk-abcXY")
  })

  it("drops a suffix off the real value when the display shrinks", () => {
    // User backspaced one character; display went from 6 to 5 bullets.
    expect(reverseDisplayDelta("sk-abc", "••••••", "•••••", false)).toBe("sk-ab")
  })

  it("treats equal-length-different-content as 'clear + paste new value'", () => {
    // User selected the entire mask and typed a new string the same length.
    expect(reverseDisplayDelta("oldKeyABC", "•••••••••", "newKeyXYZ", false)).toBe("newKeyXYZ")
  })

  it("returns the current value when nothing changed (defensive no-op)", () => {
    expect(reverseDisplayDelta("oldKey", "••••••", "••••••", false)).toBe("oldKey")
  })
})
