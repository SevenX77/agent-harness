interface ConditionalFieldProps {
  when: string
  skipIf: string
  validator: string
  onWhenChange: (value: string) => void
  onSkipIfChange: (value: string) => void
  onValidatorChange: (value: string) => void
}

export function ConditionalField({
  when,
  skipIf,
  validator,
  onWhenChange,
  onSkipIfChange,
  onValidatorChange,
}: ConditionalFieldProps) {
  return (
    <section className="space-y-3">
      <div className="text-xs font-semibold uppercase text-slate-500 dark:text-slate-400">
        Conditions and validation
      </div>
      <label className="block">
        <span className="mb-1 block text-xs font-medium text-slate-500 dark:text-slate-400">when</span>
        <input
          value={when}
          onChange={(event) => onWhenChange(event.target.value)}
          placeholder="context.ready == true"
          className="w-full rounded-md border border-slate-300 bg-white px-3 py-2 font-mono text-xs text-slate-800 outline-none focus:ring-2 focus:ring-sky-500 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100"
        />
      </label>
      <label className="block">
        <span className="mb-1 block text-xs font-medium text-slate-500 dark:text-slate-400">skip_if</span>
        <input
          value={skipIf}
          onChange={(event) => onSkipIfChange(event.target.value)}
          placeholder="context.skip_review"
          className="w-full rounded-md border border-slate-300 bg-white px-3 py-2 font-mono text-xs text-slate-800 outline-none focus:ring-2 focus:ring-sky-500 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100"
        />
      </label>
      <label className="block">
        <span className="mb-1 block text-xs font-medium text-slate-500 dark:text-slate-400">validator</span>
        <input
          value={validator}
          onChange={(event) => onValidatorChange(event.target.value)}
          placeholder="script.validators.validate_output"
          className="w-full rounded-md border border-slate-300 bg-white px-3 py-2 font-mono text-xs text-slate-800 outline-none focus:ring-2 focus:ring-sky-500 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100"
        />
      </label>
    </section>
  )
}
