import * as React from "react"
import * as AccordionPrimitive from "@radix-ui/react-accordion"
import { ChevronDown, ChevronRight } from "lucide-react"

import { cn } from "@/lib/utils"

function CatalogAccordion({
  className,
  ...props
}: React.ComponentProps<typeof AccordionPrimitive.Root>) {
  return (
    <AccordionPrimitive.Root
      data-slot="catalog-accordion"
      className={cn("flex w-full flex-col gap-5", className)}
      {...props}
    />
  )
}

function CatalogAccordionItem({
  className,
  ...props
}: React.ComponentProps<typeof AccordionPrimitive.Item>) {
  return (
    <AccordionPrimitive.Item
      data-slot="catalog-accordion-item"
      className={cn("border-0", className)}
      {...props}
    />
  )
}

function CatalogAccordionTrigger({
  className,
  children,
  ...props
}: React.ComponentProps<typeof AccordionPrimitive.Trigger>) {
  return (
    <AccordionPrimitive.Header className="flex">
      <AccordionPrimitive.Trigger
        data-slot="catalog-accordion-trigger"
        className={cn(
          "group/catalog-accordion-trigger flex flex-1 items-center gap-2 rounded-md px-0 py-0 text-left text-sm font-medium text-foreground transition-colors outline-none hover:no-underline focus-visible:ring-2 focus-visible:ring-ring/50 disabled:pointer-events-none disabled:opacity-50",
          className,
        )}
        {...props}
      >
        <ChevronRight
          data-slot="catalog-accordion-state-icon"
          className="size-4 shrink-0 text-muted-foreground group-aria-expanded/catalog-accordion-trigger:hidden"
        />
        <ChevronDown
          data-slot="catalog-accordion-state-icon"
          className="hidden size-4 shrink-0 text-muted-foreground group-aria-expanded/catalog-accordion-trigger:block"
        />
        {children}
      </AccordionPrimitive.Trigger>
    </AccordionPrimitive.Header>
  )
}

function CatalogAccordionContent({
  className,
  children,
  ...props
}: React.ComponentProps<typeof AccordionPrimitive.Content>) {
  return (
    <AccordionPrimitive.Content
      data-slot="catalog-accordion-content"
      className="overflow-hidden px-2 text-xs/relaxed data-closed:animate-accordion-up data-open:animate-accordion-down"
      {...props}
    >
      <div className={cn("pt-3 pb-4", className)}>
        {children}
      </div>
    </AccordionPrimitive.Content>
  )
}

export {
  CatalogAccordion,
  CatalogAccordionItem,
  CatalogAccordionTrigger,
  CatalogAccordionContent,
}
