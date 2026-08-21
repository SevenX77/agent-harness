import { describe, expect, it } from 'vitest'
import type { CompileError, SkillDetail } from '@/api/types'
import type { SkillGraphNode } from '@/components/nodes'
import { compileErrorsByNode } from '@/components/studio/node-compile-errors'
import { subgraphPreviewChildNodeId } from './subgraph-expansion'
import {
  currentFileAllowsSequentialOverwrite,
  isSequentialOverwriteCompileError,
  sequentialOverwriteConflictForVisibleNode,
  findNextSubgraphExpansionNode,
  sequentialOverwriteRouteFromCompileError,
  sequentialOverwriteRoutesFromCompileErrors,
} from './sequential-overwrite-routing'

function sequentialError(file: string | null, message?: string): CompileError {
  return {
    file,
    line: 1,
    field: 'io.outputs.properties.events_raw',
    severity: 'fatal',
    error_code: 'F-v3-sequential-overwrite-unauthorized',
    conflicting_phase: 'aggregate',
    message: message ?? "Phase 'review' sequentially overwrites field 'events_raw' outputted by upstream phase 'aggregate'.",
  }
}

function subgraphNode(id: string, subgraphPath: string, workspaceRoot: string): SkillGraphNode {
  return {
    id,
    type: 'skill',
    position: { x: 0, y: 0 },
    data: {
      phasePath: 'phase',
      skillId: 'story-deconstruction-v3',
      workspaceRoot,
      phaseId: id,
      label: id,
      mode: 'subgraph',
      status: 'idle',
      dependsOn: [],
      subgraphPath,
    },
  }
}

describe('sequential overwrite routing', () => {
  it('recognizes the conflict by its error code alone', () => {
    const coded = sequentialError('phases/review/LOGIC.md')
    expect(isSequentialOverwriteCompileError(coded)).toBe(true)
    expect(isSequentialOverwriteCompileError({ ...coded, error_code: '[F-v3-sequential-overwrite-unauthorized]' })).toBe(true)
  })

  it('does not recognize a conflict from wording alone', () => {
    // Prose is not a contract: an unrelated diagnostic that happens to describe
    // an overwrite must not open the canvas popover, and a reworded conflict
    // must not stop opening it. Only the code decides.
    const uncoded: CompileError = {
      ...sequentialError('phases/review/LOGIC.md'),
      error_code: null,
    }

    expect(isSequentialOverwriteCompileError(uncoded)).toBe(false)
  })

  it('reads the conflicting field and upstream phase from the fields, not the sentence', () => {
    const route = sequentialOverwriteRouteFromCompileError(
      {
        ...sequentialError('phases/review/LOGIC.md'),
        field: 'io.outputs.properties.events_raw',
        conflicting_phase: 'aggregate',
        // A message that disagrees with the structured axes: whatever the
        // sentence says, the fields are the answer.
        message: 'Phase reworded this diagnostic entirely.',
      },
      '/repo/skills/story-deconstruction-v3',
    )
    expect(route).not.toBeNull()
    if (!route) return

    const reviewNode: SkillGraphNode = {
      ...subgraphNode('review', '', '/repo/skills/story-deconstruction-v3'),
      data: {
        ...subgraphNode('review', '', '/repo/skills/story-deconstruction-v3').data,
        phaseId: 'review',
        mode: 'agent',
      },
    }

    expect(sequentialOverwriteConflictForVisibleNode([reviewNode], route)).toEqual({
      nodeId: 'review',
      fieldName: 'events_raw',
      ancestorNodeId: 'aggregate',
    })
  })

  it('raises no conflict when the engine named no upstream phase', () => {
    const route = sequentialOverwriteRouteFromCompileError(
      { ...sequentialError('phases/review/LOGIC.md'), conflicting_phase: null },
      '/repo/skills/story-deconstruction-v3',
    )
    expect(route).not.toBeNull()
    if (!route) return

    const reviewNode: SkillGraphNode = {
      ...subgraphNode('review', '', '/repo/skills/story-deconstruction-v3'),
      data: {
        ...subgraphNode('review', '', '/repo/skills/story-deconstruction-v3').data,
        phaseId: 'review',
        mode: 'agent',
      },
    }

    expect(sequentialOverwriteConflictForVisibleNode([reviewNode], route)).toBeNull()
  })

  it('derives the full subgraph path chain and target phase from a nested compile error file', () => {
    const route = sequentialOverwriteRouteFromCompileError(
      sequentialError('subgraph/event-timeline/subgraph/event-extraction/phases/review/SKILL.md'),
      '/repo/skills/story-deconstruction-v3',
    )

    expect(route).toMatchObject({
      phaseId: 'review',
      subgraphPaths: [
        '/repo/skills/story-deconstruction-v3/subgraph/event-timeline',
        '/repo/skills/story-deconstruction-v3/subgraph/event-timeline/subgraph/event-extraction',
      ],
    })
  })

  it('routes from the file axis alone — the message is not a location source', () => {
    // Ledger K6. This used to read the path back out of the sentence, because
    // the engine truncated a nested child's `file` to the child-relative part.
    // It no longer does (measured: a conflict two subgraphs deep reports
    // `subgraph/mid/subgraph/leaf/phases/revise/LOGIC.md`), so a message that
    // still happens to carry a location must change nothing about the route —
    // and a `file` the canvas cannot address must be a dead end, not a cue to
    // start parsing prose again.
    const withNoisyMessage = sequentialOverwriteRouteFromCompileError(
      sequentialError(
        'subgraph/event-timeline/phases/review/SKILL.md',
        "D:\\repo\\skills\\other\\subgraph\\somewhere-else\\phases\\review\\SKILL.md:1 Phase 'review' sequentially overwrites field 'events_raw'.",
      ),
      '/repo/skills/story-deconstruction-v3',
    )
    expect(withNoisyMessage).toMatchObject({
      phaseId: 'review',
      subgraphPaths: ['/repo/skills/story-deconstruction-v3/subgraph/event-timeline'],
    })

    const withoutFile = sequentialOverwriteRouteFromCompileError(
      sequentialError(
        null,
        "D:\\repo\\skills\\story-deconstruction-v3\\subgraph\\event-timeline\\phases\\review\\SKILL.md:1 Phase 'review' sequentially overwrites field 'events_raw'.",
      ),
      'D:\\repo\\skills\\story-deconstruction-v3',
    )
    expect(withoutFile).toBeNull()
  })

  it('routes the diagnostics themselves, not the node buckets a diagnostic may not fit in', () => {
    // Ledger N6, measured on the real app: a conflict inside a child skill
    // arrives with every axis the canvas needs (engine PR #946), and the canvas
    // still did nothing — because it was handed the NODE projection, and that
    // projection asks which ROOT node owns the file. A child skill's phase has
    // no root node; `diagnostic-paths.ts` rules exactly that, and it is right
    // for node badges. Routing wants the other thing: the subgraph chain that
    // leads to the preview child, which is in the path itself. So the routing
    // input is the diagnostic list.
    const nested = sequentialError('subgraph/event-timeline/subgraph/event-extraction/phases/review/SKILL.md')

    expect(Object.values(compileErrorsByNode([nested])).flat()).toEqual([])
    expect(sequentialOverwriteRoutesFromCompileErrors([nested], '/repo/skills/story-deconstruction-v3')).toMatchObject([
      {
        phaseId: 'review',
        subgraphPaths: [
          '/repo/skills/story-deconstruction-v3/subgraph/event-timeline',
          '/repo/skills/story-deconstruction-v3/subgraph/event-timeline/subgraph/event-extraction',
        ],
      },
    ])
  })

  it('keeps one route per conflicting phase and ignores diagnostics of other kinds', () => {
    const unrelated: CompileError = {
      ...sequentialError('phases/review/LOGIC.md'),
      error_code: 'F-v3-graph-dataflow-source-missing',
    }
    const duplicated = sequentialError('phases/review/LOGIC.md')

    const routes = sequentialOverwriteRoutesFromCompileErrors(
      [unrelated, duplicated, { ...duplicated }],
      '/repo/skills/story-deconstruction-v3',
    )

    expect(routes.map((route) => route.phaseId)).toEqual(['review'])
  })

  it('finds the next subgraph node to expand by resolved path, not by node id', () => {
    const route = sequentialOverwriteRouteFromCompileError(
      sequentialError('subgraph/event-timeline/subgraph/event-extraction/phases/review/SKILL.md'),
      '/repo/skills/story-deconstruction-v3',
    )
    expect(route).not.toBeNull()
    if (!route) return

    const rootNode = subgraphNode('event_timeline', 'subgraph/event-timeline', '/repo/skills/story-deconstruction-v3')
    const nestedId = subgraphPreviewChildNodeId('event_timeline', 'event_extraction')
    const nestedNode = subgraphNode(
      nestedId,
      'subgraph/event-extraction',
      '/repo/skills/story-deconstruction-v3/subgraph/event-timeline',
    )

    expect(findNextSubgraphExpansionNode([rootNode], new Set(), [route])).toBe('event_timeline')
    expect(findNextSubgraphExpansionNode([rootNode], new Set(['event_timeline']), [route])).toBeNull()
    expect(findNextSubgraphExpansionNode([rootNode, nestedNode], new Set(['event_timeline']), [route])).toBe(nestedId)
  })

  it('maps a nested sequential overwrite route to the visible preview child node for the popover', () => {
    const route = sequentialOverwriteRouteFromCompileError(
      sequentialError('subgraph/event-timeline/subgraph/event-extraction/phases/review/SKILL.md'),
      '/repo/skills/story-deconstruction-v3',
    )
    expect(route).not.toBeNull()
    if (!route) return

    const rootNode = subgraphNode('event_timeline', 'subgraph/event-timeline', '/repo/skills/story-deconstruction-v3')
    const nestedId = subgraphPreviewChildNodeId('event_timeline', 'event_extraction')
    const nestedNode = subgraphNode(
      nestedId,
      'subgraph/event-extraction',
      '/repo/skills/story-deconstruction-v3/subgraph/event-timeline',
    )
    const reviewId = subgraphPreviewChildNodeId(nestedId, 'review')
    const reviewNode: SkillGraphNode = {
      ...subgraphNode(reviewId, '', '/repo/skills/story-deconstruction-v3/subgraph/event-timeline/subgraph/event-extraction'),
      data: {
        ...subgraphNode(reviewId, '', '/repo/skills/story-deconstruction-v3/subgraph/event-timeline/subgraph/event-extraction').data,
        phaseId: 'review',
        label: 'review',
        mode: 'agent',
      },
    }

    expect(sequentialOverwriteConflictForVisibleNode([rootNode, nestedNode, reviewNode], route)).toEqual({
      nodeId: reviewId,
      fieldName: 'events_raw',
      ancestorNodeId: 'aggregate',
    })
  })

  it('treats the current phase file as the source of truth for cleared overwrite warnings', () => {
    const reviewNode: SkillGraphNode = {
      ...subgraphNode('review', '', '/repo/skills/story-deconstruction-v3'),
      data: {
        ...subgraphNode('review', '', '/repo/skills/story-deconstruction-v3').data,
        phaseId: 'review',
        label: 'review',
        mode: 'agent',
        filePath: 'phases/review/SKILL.md',
        resolvedSkillDetail: {
          files: {
            'phases/review/SKILL.md': [
              '---',
              'name: review',
              'allow_sequential_overwrite:',
              '  - events_raw',
              '---',
              '',
            ].join('\n'),
          },
        } as unknown as SkillDetail,
      },
    }

    expect(currentFileAllowsSequentialOverwrite([reviewNode], null, {
      nodeId: 'review',
      fieldName: 'events_raw',
    })).toBe(true)
    expect(currentFileAllowsSequentialOverwrite([reviewNode], null, {
      nodeId: 'review',
      fieldName: 'event_timeline',
    })).toBe(false)
  })
})
