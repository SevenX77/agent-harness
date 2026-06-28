import { describe, expect, it } from 'vitest'
import type { CompileError, SkillDetail } from '@/api/types'
import type { SkillGraphNode } from '@/components/nodes'
import { subgraphPreviewChildNodeId } from './subgraph-expansion'
import {
  currentFileAllowsSequentialOverwrite,
  sequentialOverwriteConflictForVisibleNode,
  findNextSubgraphExpansionNode,
  sequentialOverwriteRouteFromCompileError,
} from './sequential-overwrite-routing'

function sequentialError(file: string | null, message?: string): CompileError {
  return {
    file,
    line: 1,
    field: null,
    severity: 'fatal',
    error_code: 'F-v3-sequential-overwrite-unauthorized',
    message: message ?? "Phase 'review' sequentially overwrites field 'events_raw' outputted by upstream phase 'aggregate'.",
  }
}

function subgraphNode(id: string, subgraphPath: string, workspaceRoot: string): SkillGraphNode {
  return {
    id,
    type: 'skill',
    position: { x: 0, y: 0 },
    data: {
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

  it('recovers a nested route from the diagnostic location when the file axis is truncated', () => {
    const route = sequentialOverwriteRouteFromCompileError(
      sequentialError(
        'phases/review/SKILL.md',
        "D:\\repo\\skills\\story-deconstruction-v3\\subgraph\\event-timeline\\subgraph\\event-extraction\\phases\\review\\SKILL.md:1 Phase 'review' sequentially overwrites field 'events_raw' outputted by upstream phase 'aggregate'.",
      ),
      'D:\\repo\\skills\\story-deconstruction-v3',
    )

    expect(route).toMatchObject({
      phaseId: 'review',
      subgraphPaths: [
        'D:/repo/skills/story-deconstruction-v3/subgraph/event-timeline',
        'D:/repo/skills/story-deconstruction-v3/subgraph/event-timeline/subgraph/event-extraction',
      ],
    })
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
