import { Card, CardContent, CardHeader } from "@/components/ui/card"
import { Skeleton } from "@/components/ui/skeleton"

/**
 * N0 Settings · Shell (atom #2 settings-skeleton).
 *
 * Shell-level loading placeholder for the LLM Roles and Copilot tabs, shown by
 * SettingsPageContent while `rolesData` is null (both tabs share the same
 * lazily-loaded roles + model-groups payload). The shape mirrors those tabs'
 * real layout — a few role-card-shaped bars on the left and the Available
 * Models sidebar block on the right — instead of a generic skeleton, so the
 * first paint reads as the tab the user is opening.
 *
 * API Keys keeps its own ProviderListSkeleton (5 provider-card shapes); General
 * uses GeneralTabSkeleton (form-field-row shapes). Every settings tab now shows a
 * shape-matched skeleton while its data loads — none renders disabled forms.
 */
export function RolesTabSkeleton() {
  return (
    <div
      data-roles-tab-skeleton="true"
      className="grid min-h-full min-w-0 gap-4 lg:h-full lg:min-h-0 lg:grid-cols-[minmax(0,1fr)_minmax(14rem,20vw)] lg:grid-rows-[minmax(0,1fr)] 2xl:grid-cols-[minmax(0,1fr)_minmax(14rem,18rem)]"
    >
      <div className="min-w-0 space-y-4">
        <Card size="sm" className="rounded-md">
          <CardHeader>
            <Skeleton className="h-5 w-40" />
            <Skeleton className="h-4 w-72 max-w-full" />
          </CardHeader>
          <CardContent className="space-y-3">
            <Skeleton className="h-24 w-full" />
            <Skeleton className="h-24 w-full" />
          </CardContent>
        </Card>
        <Card size="sm" className="rounded-md">
          <CardHeader>
            <Skeleton className="h-5 w-36" />
            <Skeleton className="h-4 w-64 max-w-full" />
          </CardHeader>
          <CardContent className="space-y-3">
            <Skeleton className="h-24 w-full" />
          </CardContent>
        </Card>
      </div>
      <aside
        data-roles-tab-skeleton-sidebar="true"
        className="min-w-0 lg:sticky lg:top-0 lg:h-full lg:min-h-0 lg:self-start"
      >
        <div className="flex min-h-0 flex-col gap-3 lg:h-full">
          <div className="space-y-2">
            <Skeleton className="h-5 w-32" />
            <Skeleton className="h-8 w-full" />
          </div>
          <div className="space-y-3">
            <Skeleton className="h-8 w-full" />
            <Skeleton className="h-8 w-full" />
            <Skeleton className="h-8 w-full" />
          </div>
        </div>
      </aside>
    </div>
  )
}
