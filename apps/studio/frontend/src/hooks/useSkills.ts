import useSWR from 'swr'
import { fetcher } from '../api/client'
import type { SkillDetail } from '../api/types'

// Only the per-skill DETAIL fetch remains. The old GET /skills LIST was retired:
// the Home recent list renders from the local native-fs MRU (useRecentSkills),
// not a Python registry aggregation, and nothing consumed the list data — it only
// powered a misleading "Could not load skills" banner while costing a full engine
// compile per skill on every Home load. Design: Home = local MRU, no registry
// aggregation (D11 "无注册表" / welcome region).
export function useSkills(selectedSkillId: string | null) {
  const {
    data: skillDetail,
    error: skillDetailError,
    mutate: mutateSkillDetail,
  } = useSWR<SkillDetail>(selectedSkillId ? `/skills/${selectedSkillId}` : null, fetcher)

  return {
    skillDetail,
    skillDetailError,
    mutateSkillDetail,
  }
}
