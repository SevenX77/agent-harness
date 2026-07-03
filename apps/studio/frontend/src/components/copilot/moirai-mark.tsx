import type { SVGProps } from 'react'

/**
 * MoirAI identity mark — the constellation Cassiopeia drawn as five stars in a
 * zig-zag. It reads three ways at once, which is exactly what this copilot is:
 *
 *  - the letter **M** (MoirAI),
 *  - a **star constellation** (the celestial / fate theme of the Moirai, the
 *    three Greek Fates the name is taken from),
 *  - a **node-and-edge graph** — the DAG this copilot weaves a skill into.
 *
 * Colour comes from `currentColor`, so callers theme it via text colour
 * (`text-primary`, `text-primary-foreground`, …) — no hardcoded palette.
 */
export function MoiraiMark({
  title,
  ...props
}: SVGProps<SVGSVGElement> & { title?: string }) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      role={title ? 'img' : undefined}
      aria-hidden={title ? undefined : true}
      {...props}
    >
      {title ? <title>{title}</title> : null}
      <path
        d="M4 18 L7.5 6.8 L12 13.4 L16.5 6.8 L20 18"
        stroke="currentColor"
        strokeWidth={1.6}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <circle cx="4" cy="18" r="1.5" fill="currentColor" />
      <circle cx="7.5" cy="6.8" r="2" fill="currentColor" />
      <circle cx="12" cy="13.4" r="1.5" fill="currentColor" />
      <circle cx="16.5" cy="6.8" r="2" fill="currentColor" />
      <circle cx="20" cy="18" r="1.5" fill="currentColor" />
    </svg>
  )
}
