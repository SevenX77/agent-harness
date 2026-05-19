export function SectionHeading({ label }: { label: string }) {
  return (
    <div className="px-2 pb-0.5 pt-1 text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
      {label}
    </div>
  )
}
