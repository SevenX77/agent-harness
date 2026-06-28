import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it, vi } from 'vitest'
import type { ResumeValidityResponse } from '@/api/types'
import type { ResumeRunOptions } from '@/api/client'
import { ResumeNodeToolbar } from './ResumeNodeToolbar'

// NodeToolbar reads the React Flow store to position itself; in a static render
// we stub it (mirrors HitlNodeToolbar.test). Surface nodeId / isVisible /
// position as data-* so the test can assert the control is ANCHORED to the
// failed node above it (the F2 requirement).
const nodeToolbarCalls = vi.hoisted(() => [] as Array<Record<string, unknown>>)

vi.mock('@xyflow/react', () => ({
  Position: { Top: 'top', Bottom: 'bottom', Left: 'left', Right: 'right' },
  NodeToolbar: ({ nodeId, isVisible, position, children }: Record<string, unknown>) => {
    nodeToolbarCalls.push({ nodeId, isVisible, position })
    return (
      <div
        data-testid="resume-node-toolbar"
        data-node-id={String(nodeId)}
        data-visible={String(isVisible)}
        data-position={String(position)}
      >
        {children as React.ReactNode}
      </div>
    )
  },
}))

function validity(overrides: Partial<ResumeValidityResponse> = {}): ResumeValidityResponse {
  return {
    run_id: 'run-1',
    resume_allowed: true,
    reason: 'ok',
    checkpoint_id: 'cp-failnode',
    checkpoint_ns: 'agent:failnode',
    resume_from_node_id: 'failnode',
    resume_to_node_id: null,
    dirty_fields: [],
    snapshot_content_hash: null,
    current_content_hash: null,
    snapshot_execution_fingerprint: null,
    ...overrides,
  } as ResumeValidityResponse
}

describe('ResumeNodeToolbar (N5 #2: node-anchored Resume)', () => {
  it('anchors a [Resume] control on the failed node when resume is allowed', () => {
    const html = renderToStaticMarkup(
      <ResumeNodeToolbar
        runId="run-1"
        nodeId="failnode"
        nodeStatus="error"
        resumeValidity={validity()}
        loading={false}
        error={null}
        resumeLoading={false}
        onResumeNode={() => undefined}
      />,
    )
    const lastCall = nodeToolbarCalls.at(-1)
    // Anchored to the failed node (id == phase name), above it, visible.
    expect(lastCall?.nodeId).toBe('failnode')
    expect(lastCall?.position).toBe('top')
    expect(lastCall?.isVisible).toBe(true)
    expect(html).toContain('Resume from node')
    expect(html).toContain('Resume node')
    // The button is enabled (no `disabled` attribute) when resume is allowed.
    expect(html).not.toContain('disabled=""')
  })

  it('renders nothing when the selected node is not in the error state', () => {
    const html = renderToStaticMarkup(
      <ResumeNodeToolbar
        runId="run-1"
        nodeId="failnode"
        nodeStatus="success"
        resumeValidity={validity()}
        loading={false}
        error={null}
        resumeLoading={false}
        onResumeNode={() => undefined}
      />,
    )
    expect(html).toBe('')
  })

  it('renders nothing without an active run', () => {
    const html = renderToStaticMarkup(
      <ResumeNodeToolbar
        runId={null}
        nodeId="failnode"
        nodeStatus="error"
        resumeValidity={validity()}
        loading={false}
        error={null}
        resumeLoading={false}
        onResumeNode={() => undefined}
      />,
    )
    expect(html).toBe('')
  })

  it('disables the control and shows the reason when resume is not allowed', () => {
    const html = renderToStaticMarkup(
      <ResumeNodeToolbar
        runId="run-1"
        nodeId="failnode"
        nodeStatus="error"
        resumeValidity={validity({ resume_allowed: false, reason: 'dirty_upstream', dirty_fields: ['content_hash'] })}
        loading={false}
        error={null}
        resumeLoading={false}
        onResumeNode={() => undefined}
      />,
    )
    expect(html).toContain('Resume disabled')
    expect(html).toContain('dirty_upstream')
    expect(html).toContain('content_hash')
    expect(html).toContain('disabled=""')
  })

  it('builds a resume request carrying resume_from_node_id when clicked', () => {
    const onResumeNode = vi.fn<(options: ResumeRunOptions) => void>()
    // Render the component body to wire its handler, then pull the button onClick.
    const tree = ResumeNodeToolbar({
      runId: 'run-1',
      nodeId: 'failnode',
      nodeStatus: 'error',
      resumeValidity: validity(),
      loading: false,
      error: null,
      resumeLoading: false,
      onResumeNode,
    })
    // Walk the element tree to find the Button's onClick. The structure is
    // NodeToolbar > section > div > [div, Button]; grab the Button (last child).
    type El = { props?: { children?: unknown; onClick?: () => void } }
    const findOnClick = (node: unknown): (() => void) | null => {
      if (!node || typeof node !== 'object') return null
      const el = node as El
      if (typeof el.props?.onClick === 'function') return el.props.onClick
      const children = el.props?.children
      const list = Array.isArray(children) ? children : [children]
      for (const child of list) {
        const found = findOnClick(child)
        if (found) return found
      }
      return null
    }
    const onClick = findOnClick(tree)
    expect(onClick).toBeTypeOf('function')
    onClick?.()
    expect(onResumeNode).toHaveBeenCalledTimes(1)
    const options = onResumeNode.mock.calls[0][0]
    // The node-level resume MUST carry resume_from_node_id so the engine resumes
    // from THIS node (reuses upstream checkpoints) rather than the whole run.
    expect(options.resumeFromNodeId).toBe('failnode')
    expect(options.checkpointId).toBe('cp-failnode')
    expect(options.checkpointNs).toBe('agent:failnode')
  })
})
