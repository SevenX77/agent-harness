import * as React from "react"
import { Slot } from "@radix-ui/react-slot"
import { cva, type VariantProps } from "class-variance-authority"

import { cn } from "@/lib/utils"

const tagVariants = cva(
  "inline-flex w-fit shrink-0 items-center justify-center gap-1 overflow-hidden rounded-full border bg-transparent font-medium whitespace-nowrap transition-colors focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50 [&>svg]:pointer-events-none",
  {
    variants: {
      variant: {
        default: "border-border bg-muted/20 text-foreground",
        info: "border-primary/70 bg-primary/10 text-foreground",
        success: "border-success bg-success/10 text-foreground",
        warning: "border-warning bg-success/10 text-foreground",
        destructive: "border-tag-destructive-border bg-success/10 text-foreground",
        "probe-verified": "border-multimodal-border bg-success/10 text-foreground",
        muted: "border-border/70 bg-muted/10 text-muted-foreground",
      },
      size: {
        default: "h-7 px-3 text-sm",
        sm: "h-6 px-2.5 text-xs",
        xs: "h-5 px-1.5 text-[0.625rem]",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  },
)

function Tag({
  className,
  variant = "default",
  size = "default",
  asChild = false,
  ...props
}: React.ComponentProps<"span"> &
  VariantProps<typeof tagVariants> & { asChild?: boolean }) {
  const Comp = asChild ? Slot : "span"

  return (
    <Comp
      data-slot="tag"
      data-variant={variant}
      data-size={size}
      className={cn(tagVariants({ variant, size }), className)}
      {...props}
    />
  )
}

export { Tag, tagVariants }
