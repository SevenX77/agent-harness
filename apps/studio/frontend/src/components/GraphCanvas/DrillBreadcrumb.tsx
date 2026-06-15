import { Fragment } from 'react'
import { Network } from 'lucide-react'
import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from '@/components/ui/breadcrumb'
import { breadcrumbItems, type DrillStack } from './drill-stack'

interface DrillBreadcrumbProps {
  stack: DrillStack
  rootLabel: string
  /** Pop to a breadcrumb index (-1 = root). */
  onNavigate: (index: number) => void
}

/**
 * Top-left navigation breadcrumb for subgraph drill-down (R9). Renders the
 * root → child → … trail from the drill stack; each non-current level is a
 * clickable link that pops back to it, the deepest level renders inert.
 * Hidden entirely while at the root (empty stack) so the canvas is unchanged.
 */
export function DrillBreadcrumb({ stack, rootLabel, onNavigate }: DrillBreadcrumbProps) {
  if (stack.length === 0) {
    return null
  }
  const items = breadcrumbItems(stack, rootLabel)
  return (
    <div className="rounded-md border border-border bg-card px-2.5 py-1.5 shadow-sm">
      <Breadcrumb>
        <BreadcrumbList>
          {items.map((item, position) => (
            <Fragment key={`${item.index}:${item.label}`}>
              {position > 0 ? <BreadcrumbSeparator /> : null}
              <BreadcrumbItem>
                {item.isCurrent ? (
                  <BreadcrumbPage className="inline-flex items-center gap-1 font-medium">
                    <Network className="size-3" />
                    {item.label}
                  </BreadcrumbPage>
                ) : (
                  <BreadcrumbLink asChild>
                    <button
                      type="button"
                      className="inline-flex items-center gap-1"
                      onClick={() => onNavigate(item.index)}
                    >
                      {item.index === -1 ? <Network className="size-3" /> : null}
                      {item.label}
                    </button>
                  </BreadcrumbLink>
                )}
              </BreadcrumbItem>
            </Fragment>
          ))}
        </BreadcrumbList>
      </Breadcrumb>
    </div>
  )
}
