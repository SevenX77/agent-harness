import { useEffect, useMemo, useRef, useState } from "react"
import type { SkillDetail } from "@/api/types"
import { isTauriRuntime } from "@/config/runtime"
import { readWorkspaceFile } from "@/lib/tauri"
import {
  loadRecursiveSubgraphMembership,
  subgraphMembership,
  type SubgraphMembership,
} from "./subgraph-membership"

export interface SubgraphMembershipTree {
  key: string
  topLevel: SubgraphMembership[]
  items: SubgraphMembership[]
  loading: boolean
}

export function useSkillSubgraphMembershipTree({
  skillDetail,
  workspaceRoot,
  enabled = true,
}: {
  skillDetail?: SkillDetail
  workspaceRoot?: string | null
  enabled?: boolean
}): SubgraphMembershipTree {
  const topLevel = useMemo(() => {
    const ownerRoot = workspaceRoot ?? null
    return subgraphMembership(skillDetail, ownerRoot).map((subgraph) => ({
      ...subgraph,
      workspaceRoot: ownerRoot,
    }))
  }, [skillDetail, workspaceRoot])

  return useSubgraphMembershipTree({ topLevel, enabled })
}

export function useSubgraphMembershipTree({
  topLevel,
  enabled = true,
}: {
  topLevel: SubgraphMembership[]
  enabled?: boolean
}): SubgraphMembershipTree {
  const key = useMemo(() => subgraphMembershipKey(topLevel), [topLevel])
  const keyedTopLevelRef = useRef<{ key: string; topLevel: SubgraphMembership[] } | null>(null)
  if (keyedTopLevelRef.current?.key !== key) {
    keyedTopLevelRef.current = { key, topLevel }
  }
  const keyedTopLevel = keyedTopLevelRef.current.topLevel
  const [resolved, setResolved] = useState<SubgraphMembershipTree>(() => ({
    key,
    topLevel: keyedTopLevel,
    items: keyedTopLevel,
    loading: false,
  }))

  useEffect(() => {
    let cancelled = false

    if (!enabled || !isTauriRuntime() || keyedTopLevel.length === 0) {
      setResolved((current) => {
        if (current.key === key && !current.loading) {
          return current
        }
        return { key, topLevel: keyedTopLevel, items: keyedTopLevel, loading: false }
      })
      return () => {
        cancelled = true
      }
    }

    setResolved((current) => {
      if (current.key === key) {
        return current
      }
      return { key, topLevel: keyedTopLevel, items: keyedTopLevel, loading: true }
    })

    void loadRecursiveSubgraphMembership(keyedTopLevel, readWorkspaceFile)
      .then((memberships) => {
        if (!cancelled) {
          setResolved({ key, topLevel: keyedTopLevel, items: memberships, loading: false })
        }
      })
      .catch(() => {
        if (!cancelled) {
          setResolved({ key, topLevel: keyedTopLevel, items: keyedTopLevel, loading: false })
        }
      })

    return () => {
      cancelled = true
    }
  }, [enabled, key, keyedTopLevel])

  return resolved.key === key
    ? resolved
    : { key, topLevel: keyedTopLevel, items: keyedTopLevel, loading: enabled && isTauriRuntime() && keyedTopLevel.length > 0 }
}

function subgraphMembershipKey(subgraphs: SubgraphMembership[]): string {
  return subgraphs.map((subgraph) => [
    subgraph.id,
    subgraph.label,
    subgraph.level,
    subgraph.filePath,
    subgraph.workspaceRoot ?? "",
    subgraph.path ?? "",
    subgraph.legacyTargetSkill ?? "",
    subgraph.status,
  ].join("\u0001")).join("\u0002")
}
