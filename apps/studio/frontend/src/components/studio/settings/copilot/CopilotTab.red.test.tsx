/**
 * WS-5 RED: Settings Copilot consumes real registry DTO, never mock data.
 *
 * Contract (settings-ux-spec §3.2/§3.5, FRONTEND_UI_SPEC §2.9, llm-copilot §6):
 *  - CopilotTab must NOT fall back to `mock-copilot-data` default model groups /
 *    credentials. With no real registry it shows an empty state, not seeded mock
 *    built-in roles like "Opus 4.7 Copilot" / "DeepSeek V4 Copilot".
 *
 * RED today: CopilotTab defaults `modelGroups`/`credentials` to the mock module,
 * so rendering with empty roles still paints two mock built-in role cards.
 */
import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import { CopilotTab } from './CopilotTab'
import type { RolesData } from '@/api/llm'

const emptyRoles = { roles: {} } as unknown as RolesData

describe('CopilotTab real-DTO contract', () => {
  it('does not seed mock built-in copilot roles when no registry is provided', () => {
    const html = renderToStaticMarkup(<CopilotTab data={emptyRoles} />)

    expect(html).not.toContain('Opus 4.7 Copilot')
    expect(html).not.toContain('DeepSeek V4 Copilot')
  })

  it('renders no copilot role cards without real model groups', () => {
    const html = renderToStaticMarkup(<CopilotTab data={emptyRoles} />)

    const roleCards = html.match(/data-copilot-role-card="true"/g) ?? []
    expect(roleCards).toHaveLength(0)
  })
})
