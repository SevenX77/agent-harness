import type { PhaseFormData } from '../../hooks/usePhaseForm'
import { phaseFormErrors } from '../../hooks/usePhaseForm'
import { ConditionalField } from './fields/ConditionalField'
import { LlmRoleField } from './fields/LlmRoleField'
import { ModelOverrideField } from './fields/ModelOverrideField'
import { PhaseNameField } from './fields/PhaseNameField'
import { PromptField } from './fields/PromptField'
import { ToolsMultiSelect } from './fields/ToolsMultiSelect'

interface PhaseFormBodyProps {
  data: PhaseFormData
  availableTools: string[]
  onChange: <Key extends keyof PhaseFormData>(field: Key, value: PhaseFormData[Key]) => void
}

export function PhaseFormBody({ data, availableTools, onChange }: PhaseFormBodyProps) {
  const errors = phaseFormErrors(data)

  return (
    <div className="space-y-5">
      <PhaseNameField
        name={data.name}
        mode={data.mode}
        error={errors.name}
        onNameChange={(value) => onChange('name', value)}
        onModeChange={(value) => onChange('mode', value)}
      />

      {data.mode === 'llm' ? (
        <>
          <div className="grid grid-cols-2 gap-3">
            <LlmRoleField value={data.llmRole} onChange={(value) => onChange('llmRole', value)} />
            <ModelOverrideField
              value={data.modelOverride}
              onChange={(value) => onChange('modelOverride', value)}
            />
          </div>
          <PromptField
            label="Prompt"
            value={data.prompt}
            error={errors.prompt}
            onChange={(value) => onChange('prompt', value)}
          />
          <PromptField
            label="User prompt template"
            value={data.userPromptTemplate}
            onChange={(value) => onChange('userPromptTemplate', value)}
          />
          <ToolsMultiSelect
            selected={data.agentTools}
            options={availableTools}
            onChange={(tools) => onChange('agentTools', tools)}
          />
        </>
      ) : (
        <label className="block">
          <span className="mb-1 block text-xs font-semibold uppercase text-slate-500 dark:text-slate-400">
            Execute steps
          </span>
          <textarea
            value={data.executeSteps.join('\n')}
            onChange={(event) => onChange(
              'executeSteps',
              event.target.value.split('\n').map((line) => line.trim()).filter(Boolean),
            )}
            rows={Math.max(4, data.executeSteps.length + 1)}
            className="w-full resize-y rounded-md border border-slate-300 bg-white px-3 py-2 font-mono text-xs leading-5 text-slate-800 outline-none focus:ring-2 focus:ring-sky-500 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-100"
          />
          {errors.executeSteps ? (
            <span className="mt-1 block text-xs text-red-600 dark:text-red-400">{errors.executeSteps}</span>
          ) : null}
        </label>
      )}

      <ConditionalField
        when={data.when}
        skipIf={data.skipIf}
        validator={data.validator}
        onWhenChange={(value) => onChange('when', value)}
        onSkipIfChange={(value) => onChange('skipIf', value)}
        onValidatorChange={(value) => onChange('validator', value)}
      />
    </div>
  )
}
