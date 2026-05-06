interface StepIndicatorProps {
  stepIndex: number
  stepCount: number
}

const labels = ['Type', 'Basics', 'Inputs', 'First Phase', 'Preview']

export function StepIndicator({ stepIndex, stepCount }: StepIndicatorProps) {
  return (
    <div className="border-b border-gray-200 dark:border-slate-800 px-6 py-4">
      <div className="mb-3 flex items-center justify-between text-xs font-semibold uppercase text-gray-500 dark:text-gray-400">
        <span>Step {stepIndex + 1} of {stepCount}</span>
        <span>{labels[stepIndex]}</span>
      </div>
      <div className="grid gap-2" style={{ gridTemplateColumns: `repeat(${stepCount}, minmax(0, 1fr))` }}>
        {Array.from({ length: stepCount }, (_, index) => (
          <div
            key={index}
            className={`h-1.5 rounded-full ${index <= stepIndex ? 'bg-sky-600 dark:bg-sky-400' : 'bg-gray-200 dark:bg-slate-800'}`}
          />
        ))}
      </div>
    </div>
  )
}
