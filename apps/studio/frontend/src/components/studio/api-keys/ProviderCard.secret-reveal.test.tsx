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
})
