import { Skeleton } from "@/components/ui/skeleton"

/**
 * N0 Settings · Shell (atom #2 settings-skeleton).
 *
 * Shell-level loading placeholder for the General tab, shown by
 * SettingsPageContent while `appSettings.isLoading` (the initial app-settings
 * fetch over the sidecar). The shape mirrors General's real layout — a section
 * title block plus four labelled form-field rows (Studio User ID, default skill
 * folder, Gitea host, language) — so the first paint reads as the tab the user
 * is opening, consistent with API Keys (ProviderListSkeleton) and LLM Roles /
 * Copilot (RolesTabSkeleton). General previously rendered its form in a fully
 * DISABLED state while loading, which read as a broken, unusable page and was
 * inconsistent with every other settings tab.
 */
export function GeneralTabSkeleton() {
  return (
    <div data-general-tab-skeleton="true" className="max-w-3xl">
      <div className="mb-6 space-y-2">
        <Skeleton className="h-5 w-32" />
        <Skeleton className="h-4 w-80 max-w-full" />
      </div>
      <div className="space-y-5">
        {Array.from({ length: 4 }).map((_, index) => (
          <div key={index} className="space-y-2">
            <Skeleton className="h-4 w-28" />
            <Skeleton className="h-8 w-full" />
            <Skeleton className="h-3 w-64 max-w-full" />
          </div>
        ))}
      </div>
    </div>
  )
}
