import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import { FocusedNodeActions, isGoldenlessAgentNode } from './FocusedNodeActions'

const goldenlessAgentNode = { id: 'nodeA', data: { label: 'Node A', mode: 'agent' as const } }

describe('isGoldenlessAgentNode (atom #32 entry① eligibility)', () => {
  it('is true for an agent node without golden', () => {
    expect(isGoldenlessAgentNode({ data: { mode: 'agent' } })).toBe(true)
    expect(isGoldenlessAgentNode({ data: { mode: 'llm', goldenState: 'logic-ok' } })).toBe(true)
    expect(isGoldenlessAgentNode({ data: { mode: 'skill' } })).toBe(true)
  })

  it('is false once the agent node already has golden', () => {
    expect(isGoldenlessAgentNode({ data: { mode: 'agent', goldenState: 'has-golden' } })).toBe(false)
  })

  it('is false for non-agent nodes (logic/subgraph never get golden)', () => {
    expect(isGoldenlessAgentNode({ data: { mode: 'logic' } })).toBe(false)
    expect(isGoldenlessAgentNode({ data: { mode: 'subgraph' } })).toBe(false)
  })

  it('is false when there is no focused node', () => {
    expect(isGoldenlessAgentNode(null)).toBe(false)
    expect(isGoldenlessAgentNode(undefined)).toBe(false)
  })
})

describe('design golden (E3 entry①)', () => {
  it('offers to design this node’s golden with no run in sight', () => {
    const html = renderToStaticMarkup(
      <FocusedNodeActions node={goldenlessAgentNode} canPromote={false} onDesignGolden={() => undefined} />,
    )
    expect(html).toContain('Design golden')
    expect(html).toContain('aria-label="Design golden for node ')
    expect(html).toContain('Node A')
  })

  it('offers it during a run too, beside the promote button', () => {
    const html = renderToStaticMarkup(
      <FocusedNodeActions
        node={goldenlessAgentNode}
        canPromote
        onDesignGolden={() => undefined}
        onPromoteNode={() => undefined}
      />,
    )
    expect(html).toContain('Design golden')
    expect(html).toContain('Promote node to golden')
  })

  it('omits it once the focused agent node already has golden', () => {
    const html = renderToStaticMarkup(
      <FocusedNodeActions
        node={{ id: 'nodeA', data: { label: 'Node A', mode: 'agent', goldenState: 'has-golden' } }}
        onDesignGolden={() => undefined}
      />,
    )
    expect(html).not.toContain('Design golden')
  })

  it('omits it for a node that never gets golden', () => {
    const html = renderToStaticMarkup(
      <FocusedNodeActions
        node={{ id: 'gate', data: { label: 'Gate', mode: 'logic' } }}
        onDesignGolden={() => undefined}
      />,
    )
    expect(html).not.toContain('Design golden')
  })

  it('omits it when no handler is wired', () => {
    const html = renderToStaticMarkup(<FocusedNodeActions node={goldenlessAgentNode} />)
    expect(html).not.toContain('Design golden')
  })
})

describe('promote node to golden (atom #32 entry①)', () => {
  it('renders a per-node promote button beside the focused golden-less agent node', () => {
    const html = renderToStaticMarkup(
      <FocusedNodeActions node={goldenlessAgentNode} canPromote onPromoteNode={() => undefined} />,
    )
    expect(html).toContain('Promote node to golden')
    // The aria-label is node-anchored; the focused node label appears in it
    // (double quotes around the label are HTML-escaped by the static renderer).
    expect(html).toContain('aria-label="Promote node ')
    expect(html).toContain('Node A')
    expect(html).toContain(' to golden"')
  })

  it('omits the per-node button when the focused agent node already has golden', () => {
    const html = renderToStaticMarkup(
      <FocusedNodeActions
        node={{ id: 'nodeA', data: { label: 'Node A', mode: 'agent', goldenState: 'has-golden' } }}
        canPromote
        onPromoteNode={() => undefined}
      />,
    )
    expect(html).not.toContain('Promote node to golden')
  })

  it('omits the per-node button with no run to promote from', () => {
    const html = renderToStaticMarkup(
      <FocusedNodeActions node={goldenlessAgentNode} canPromote={false} onPromoteNode={() => undefined} />,
    )
    expect(html).not.toContain('Promote node to golden')
  })

  it('omits the per-node button when no per-node promote handler is wired', () => {
    const html = renderToStaticMarkup(<FocusedNodeActions node={goldenlessAgentNode} canPromote />)
    expect(html).not.toContain('Promote node to golden')
  })
})

describe('nothing to offer', () => {
  it('renders nothing at all when no node is focused', () => {
    const html = renderToStaticMarkup(
      <FocusedNodeActions node={null} canPromote onDesignGolden={() => undefined} onPromoteNode={() => undefined} />,
    )
    expect(html).toBe('')
  })
})
