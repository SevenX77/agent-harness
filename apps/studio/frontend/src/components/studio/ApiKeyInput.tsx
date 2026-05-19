import { useState, type ChangeEvent } from "react"
import { Eye, EyeOff } from "lucide-react"
import { Input } from "@/components/ui/input"
import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"

interface ApiKeyInputProps {
  value: string
  onChange: (next: string) => void
  providerCode: string
  /** Optional placeholder override (defaults to "Paste API key for <code>"). */
  placeholder?: string
  /** Optional id propagated to the underlying input. */
  inputId?: string
  className?: string
  disabled?: boolean
}

/**
 * Focus-aware masked input for API keys (spec C2 — onChange interception).
 *
 * Behavior:
 *   - Input is *always editable* (no `readOnly` — round 1 ruled that out
 *     because some browsers swallow the first click).
 *   - The DOM `value` is the user-visible string: bullets when masked, real
 *     key when revealed.
 *   - `onChange` reverse-engineers the real value from the display delta:
 *     paste → append; backspace → drop last char; full-select-delete → clear;
 *     plain mode → straight passthrough.
 *   - "Revealed" = focused OR Eye toggle on. Blurring re-masks immediately.
 */
export function ApiKeyInput({
  value,
  onChange,
  providerCode,
  placeholder,
  inputId,
  className,
  disabled,
}: ApiKeyInputProps) {
  const [isVisible, setIsVisible] = useState(false)
  const [isFocused, setIsFocused] = useState(false)

  const shouldShowPlain = isVisible || isFocused
  const displayValue = computeDisplayValue(value, shouldShowPlain)

  function handleChange(event: ChangeEvent<HTMLInputElement>) {
    const next = event.target.value
    onChange(reverseDisplayDelta(value, displayValue, next, shouldShowPlain))
  }

  return (
    <div className={cn("relative", className)}>
      <Input
        id={inputId}
        type="text"
        value={displayValue}
        onChange={handleChange}
        onFocus={() => setIsFocused(true)}
        onBlur={() => setIsFocused(false)}
        autoComplete="off"
        spellCheck={false}
        placeholder={placeholder ?? `Paste API key for ${providerCode}`}
        disabled={disabled}
        // Suppress 1Password / LastPass / Bitwarden autofill on this field —
        // pasting an unrelated saved login here would silently overwrite the
        // user's real key.
        data-1p-ignore=""
        data-lpignore="true"
        data-form-type="other"
        className="pr-9"
      />
      <Button
        type="button"
        variant="ghost"
        size="icon"
        onClick={() => setIsVisible((current) => !current)}
        aria-label={isVisible ? "Hide API key" : "Show API key"}
        aria-pressed={isVisible}
        className="absolute right-1 top-1/2 size-7 -translate-y-1/2 text-muted-foreground hover:text-foreground"
        disabled={disabled}
      >
        {isVisible ? <EyeOff className="size-4" /> : <Eye className="size-4" />}
      </Button>
    </div>
  )
}

/**
 * Convert the real value into what the user should see right now.
 * Exported for unit testing.
 */
export function computeDisplayValue(value: string, shouldShowPlain: boolean): string {
  if (shouldShowPlain) return value
  if (!value) return ""
  return "•".repeat(Math.min(value.length, 32))
}

/**
 * Compute the next real value from a change to the displayed string.
 * Exported for unit testing — see ApiKeyInput.test.tsx for all branches.
 *
 * `nextDisplay` is the value the browser handed us after the user typed.
 * `priorDisplay` is what we *were* showing immediately before the event.
 */
export function reverseDisplayDelta(
  currentValue: string,
  priorDisplay: string,
  nextDisplay: string,
  shouldShowPlain: boolean,
): string {
  if (shouldShowPlain) {
    // The user is editing the real key directly — passthrough.
    return nextDisplay
  }
  if (nextDisplay === "") {
    // Full-select + delete in mask state clears the real key.
    return ""
  }
  if (nextDisplay.length > priorDisplay.length) {
    // Paste / type extra chars — append the tail onto the real key.
    const appended = nextDisplay.slice(priorDisplay.length)
    return currentValue + appended
  }
  if (nextDisplay.length < priorDisplay.length) {
    // Backspace — drop the same suffix off the real key.
    return currentValue.slice(0, nextDisplay.length)
  }
  // Equal length but content differs (mid-mask paste replacing a selection).
  // Treat as "clear + paste new value".
  return nextDisplay === priorDisplay ? currentValue : nextDisplay
}
