interface ModelOverrideFieldProps {
  value: string
  onChange: (value: string) => void
}

export function ModelOverrideField({ value, onChange }: ModelOverrideFieldProps) {
  return (
    <label className="block">
      <span className="mb-1 block text-xs font-semibold uppercase text-slate-500 dark:text-slate-400">
        Model override
      </span>
      <input
        value={value}
        onChange={(event) => onChange(event.target.value)}
        placeholder="Use role default"
        className="w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm text-slate-800 outline-none focus:ring-2 focus:ring-sky-500 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100"
      />
    </label>
  )
}
