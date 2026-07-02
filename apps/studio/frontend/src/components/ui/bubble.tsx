import * as React from 'react'
import { cva, type VariantProps } from 'class-variance-authority'

import { cn } from '@/lib/utils'

/**
 * shadcn `bubble` primitive (chat.md: "The colored message surface is Bubble +
 * BubbleContent, never a styled div with bg-muted and hand-managed corners").
 * Variants follow the published API; only the surfaces the app uses get full
 * styling attention, all on semantic tokens.
 */
const bubbleVariants = cva('flex w-fit max-w-[85%] flex-col gap-1 rounded-lg text-sm', {
  variants: {
    variant: {
      default: 'bg-primary text-primary-foreground',
      secondary: 'bg-secondary text-secondary-foreground',
      muted: 'bg-muted text-foreground',
      tinted: 'bg-accent text-accent-foreground',
      outline: 'border border-border bg-transparent',
      ghost: 'bg-transparent',
      destructive: 'bg-destructive/10 text-destructive',
    },
    align: {
      start: 'self-start',
      end: 'self-end',
    },
  },
  defaultVariants: {
    variant: 'default',
    align: 'start',
  },
})

function Bubble({
  className,
  variant,
  align,
  ...props
}: React.ComponentProps<'div'> & VariantProps<typeof bubbleVariants>) {
  return (
    <div
      data-slot="bubble"
      data-variant={variant ?? 'default'}
      data-align={align ?? 'start'}
      className={cn(bubbleVariants({ variant, align }), className)}
      {...props}
    />
  )
}

function BubbleContent({ className, ...props }: React.ComponentProps<'div'>) {
  return (
    <div
      data-slot="bubble-content"
      className={cn('px-3 py-2 leading-relaxed whitespace-pre-wrap', className)}
      {...props}
    />
  )
}

export { Bubble, BubbleContent, bubbleVariants }
