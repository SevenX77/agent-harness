// @vitest-environment jsdom

import { act, useState } from "react"
import { createRoot, type Root } from "react-dom/client"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { REDACTED_ENDPOINT_SECRET } from "@/api/llm"
import type { CredentialsState } from "@/api/llm"
import type { ProviderDraft } from "../settings/types"
import { ProviderCard } from "./ProviderCard"

;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true

const toastMock = vi.hoisted(() => Object.assign(vi.fn(), {
  dismiss: vi.fn(),
  error: vi.fn(),
  success: vi.fn(),
}))

vi.mock("sonner", () => ({
  toast: toastMock,
}))

const baseDraft: ProviderDraft = {
  id: "openrouter-openai",
  name: "OpenRouter",
  api_key: REDACTED_ENDPOINT_SECRET,
  base_url: "https://openrouter.ai/api/v1",
  provider_type: "openai_compatible",
  isTesting: false,
}

const basePersisted: CredentialsState["providers"][number] = {
  id: "openrouter-openai",
  name: "OpenRouter",
  api_key: REDACTED_ENDPOINT_SECRET,
  base_url: "https://openrouter.ai/api/v1",
  provider_type: "openai_compatible",
  api_key_length: 35,
}

const MASK_CHAR = "\u2022"
const SECRET_INPUT = 'input[name="provider-secret-openrouter-openai"]'

/** Type into a controlled input the way a browser does: set value, emit input. */
function typeInto(input: HTMLInputElement, value: string): void {
  const setter = Object.getOwnPropertyDescriptor(
    window.HTMLInputElement.prototype,
    "value",
  )?.set
  setter?.call(input, value)
  input.dispatchEvent(new Event("input", { bubbles: true }))
}

describe("ProviderCard API key explicit reveal", () => {
  let container: HTMLDivElement
  let root: Root

  beforeEach(() => {
    container = document.createElement("div")
    document.body.appendChild(container)
    root = createRoot(container)
  })

  afterEach(() => {
    act(() => {
      root.unmount()
    })
    container.remove()
  })

  it("does not load a redacted secret until the user clicks show API key", async () => {
    const revealSecret = vi.fn().mockResolvedValue("sk-live-openrouter")

    function Harness() {
      const [draft, setDraft] = useState(baseDraft)
      return (
        <ProviderCard
          draft={draft}
          persisted={basePersisted}
          onFieldChange={(patch) => setDraft((current) => ({ ...current, ...patch }))}
          onGetModels={vi.fn()}
          onDelete={vi.fn()}
          onRevealApiKey={async () => {
            const secret = await revealSecret()
            setDraft((current) => ({ ...current, api_key: secret }))
            return secret
          }}
        />
      )
    }

    await act(async () => {
      root.render(<Harness />)
    })

    expect(revealSecret).not.toHaveBeenCalled()

    const showButton = container.querySelector<HTMLButtonElement>('[aria-label="Show API key"]')
    expect(showButton).not.toBeNull()

    await act(async () => {
      showButton?.dispatchEvent(new MouseEvent("click", { bubbles: true }))
      await Promise.resolve()
      await Promise.resolve()
    })

    expect(revealSecret).toHaveBeenCalledTimes(1)
    expect(container.querySelector<HTMLInputElement>('input[name="provider-secret-openrouter-openai"]')?.value).toBe("sk-live-openrouter")
  })
  it("keeps the mask when the field is focused", async () => {
    // Design A10 / atom 22: only Eye or Copy exchanges the redacted registry
    // value for the real secret, and the mask is drawn at `api_key_length`
    // rather than the placeholder's 10 positions (2026-08-12 decision).
    // Focusing used to hand the raw draft back, so clicking the field displayed
    // the literal 10-character placeholder — the placeholder shown as content.
    const changes: string[] = []

    function Harness() {
      const [draft, setDraft] = useState(baseDraft)
      return (
        <ProviderCard
          draft={draft}
          persisted={basePersisted}
          onFieldChange={(patch) => {
            if (typeof patch.api_key === "string") changes.push(patch.api_key)
            setDraft((current) => ({ ...current, ...patch }))
          }}
          onGetModels={vi.fn()}
          onDelete={vi.fn()}
          onRevealApiKey={vi.fn()}
        />
      )
    }

    await act(async () => {
      root.render(<Harness />)
    })

    const input = container.querySelector<HTMLInputElement>(SECRET_INPUT)
    expect(input).not.toBeNull()

    await act(async () => {
      input?.dispatchEvent(new FocusEvent("focusin", { bubbles: true }))
      await Promise.resolve()
    })

    expect(input?.value).toBe(MASK_CHAR.repeat(35))
    expect(input?.value).not.toContain("*")
    expect(changes).toEqual([])
  })

  it("treats typing in a masked field as a whole new secret", async () => {
    // A mask cannot be edited into a credential: the field never held one to
    // begin with. So the first character typed starts a fresh key rather than
    // being appended to the mask — the behaviour every password manager uses
    // for a stored secret, and the only one that cannot produce a hybrid like
    // `**********sk-live`.
    const changes: string[] = []

    function Harness() {
      const [draft, setDraft] = useState(baseDraft)
      return (
        <ProviderCard
          draft={draft}
          persisted={basePersisted}
          onFieldChange={(patch) => {
            if (typeof patch.api_key === "string") changes.push(patch.api_key)
            setDraft((current) => ({ ...current, ...patch }))
          }}
          onGetModels={vi.fn()}
          onDelete={vi.fn()}
          onRevealApiKey={vi.fn()}
        />
      )
    }

    await act(async () => {
      root.render(<Harness />)
    })

    const input = container.querySelector<HTMLInputElement>(SECRET_INPUT)!

    await act(async () => {
      input.dispatchEvent(new FocusEvent("focusin", { bubbles: true }))
      await Promise.resolve()
    })
    await act(async () => {
      typeInto(input, MASK_CHAR.repeat(35) + "s")
      await Promise.resolve()
    })

    expect(changes).toEqual(["s"])
    expect(input.value).toBe("s")
  })

  it("takes a paste into a masked field as the whole new secret", async () => {
    const changes: string[] = []

    function Harness() {
      const [draft, setDraft] = useState(baseDraft)
      return (
        <ProviderCard
          draft={draft}
          persisted={basePersisted}
          onFieldChange={(patch) => {
            if (typeof patch.api_key === "string") changes.push(patch.api_key)
            setDraft((current) => ({ ...current, ...patch }))
          }}
          onGetModels={vi.fn()}
          onDelete={vi.fn()}
          onRevealApiKey={vi.fn()}
        />
      )
    }

    await act(async () => {
      root.render(<Harness />)
    })

    const input = container.querySelector<HTMLInputElement>(SECRET_INPUT)!

    await act(async () => {
      input.dispatchEvent(new FocusEvent("focusin", { bubbles: true }))
      await Promise.resolve()
    })
    await act(async () => {
      typeInto(input, MASK_CHAR.repeat(35) + "sk-live-openrouter")
      await Promise.resolve()
    })

    expect(changes).toEqual(["sk-live-openrouter"])
  })

  it("ignores deletions that only shorten the mask", async () => {
    // Removing a mask dot cannot mean "remove a character of the key" — the
    // dots are not the key. Treating it as an edit is how one stray backspace
    // used to overwrite a working credential with nine asterisks. Clearing the
    // key stays available through Eye + select-all, which is explicit.
    const changes: string[] = []

    function Harness() {
      const [draft, setDraft] = useState(baseDraft)
      return (
        <ProviderCard
          draft={draft}
          persisted={basePersisted}
          onFieldChange={(patch) => {
            if (typeof patch.api_key === "string") changes.push(patch.api_key)
            setDraft((current) => ({ ...current, ...patch }))
          }}
          onGetModels={vi.fn()}
          onDelete={vi.fn()}
          onRevealApiKey={vi.fn()}
        />
      )
    }

    await act(async () => {
      root.render(<Harness />)
    })

    const input = container.querySelector<HTMLInputElement>(SECRET_INPUT)!

    await act(async () => {
      input.dispatchEvent(new FocusEvent("focusin", { bubbles: true }))
      await Promise.resolve()
    })
    await act(async () => {
      typeInto(input, MASK_CHAR.repeat(34))
      await Promise.resolve()
    })

    expect(changes).toEqual([])
    expect(input.value).toBe(MASK_CHAR.repeat(35))
  })

  it("edits normally once the secret has been revealed", async () => {
    const changes: string[] = []

    function Harness() {
      const [draft, setDraft] = useState(baseDraft)
      return (
        <ProviderCard
          draft={draft}
          persisted={basePersisted}
          onFieldChange={(patch) => {
            if (typeof patch.api_key === "string") changes.push(patch.api_key)
            setDraft((current) => ({ ...current, ...patch }))
          }}
          onGetModels={vi.fn()}
          onDelete={vi.fn()}
          onRevealApiKey={async () => {
            setDraft((current) => ({ ...current, api_key: "sk-live-openrouter" }))
            return "sk-live-openrouter"
          }}
        />
      )
    }

    await act(async () => {
      root.render(<Harness />)
    })

    await act(async () => {
      container
        .querySelector<HTMLButtonElement>('[aria-label="Show API key"]')
        ?.dispatchEvent(new MouseEvent("click", { bubbles: true }))
      await Promise.resolve()
      await Promise.resolve()
    })

    const input = container.querySelector<HTMLInputElement>(SECRET_INPUT)!
    expect(input.value).toBe("sk-live-openrouter")

    await act(async () => {
      typeInto(input, "sk-live-openrouter-2")
      await Promise.resolve()
    })

    expect(changes).toEqual(["sk-live-openrouter-2"])
  })
})
