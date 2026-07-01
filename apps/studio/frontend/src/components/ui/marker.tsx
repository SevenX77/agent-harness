import * as React from "react"
import { Slot } from "@radix-ui/react-slot"
import { cva, type VariantProps } from "class-variance-authority"

import { cn } from "@/lib/utils"

const markerVariants = cva(
  "group/marker flex min-w-0 items-center gap-2 text-xs text-muted-foreground",
  {
    variants: {
      variant: {
        default: "py-0.5",
        border: "border-b border-border/60 py-1.5",
        separator:
          "relative justify-center py-2 text-[0.625rem] uppercase before:h-px before:flex-1 before:bg-border/70 after:h-px after:flex-1 after:bg-border/70",
      },
    },
    defaultVariants: {
      variant: "default",
    },
  },
)

function Marker({
  className,
  variant = "default",
  asChild = false,
  ...props
}: React.ComponentProps<"div"> &
  VariantProps<typeof markerVariants> & {
    asChild?: boolean
  }) {
  const Comp = asChild ? Slot : "div"

  return (
    <Comp
      data-slot="marker"
      data-variant={variant}
      className={cn(markerVariants({ variant }), className)}
      {...props}
    />
  )
}

function MarkerIcon({ className, ...props }: React.ComponentProps<"span">) {
  return (
    <span
      data-slot="marker-icon"
      aria-hidden="true"
      className={cn("flex size-4 shrink-0 items-center justify-center text-muted-foreground [&_svg]:size-3.5", className)}
      {...props}
    />
  )
}

function MarkerContent({ className, ...props }: React.ComponentProps<"span">) {
  return (
    <span
      data-slot="marker-content"
      className={cn("min-w-0 truncate", className)}
      {...props}
    />
  )
}

export { Marker, MarkerContent, MarkerIcon, markerVariants }
