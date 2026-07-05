import type { SWRConfiguration } from "swr"

export const STUDIO_TRUTH_SWR_CONFIG = {
  revalidateIfStale: false,
  revalidateOnFocus: false,
  revalidateOnReconnect: false,
} satisfies SWRConfiguration
