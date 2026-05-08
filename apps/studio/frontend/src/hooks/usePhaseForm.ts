import { useCallback, useEffect, useMemo, useState } from 'react'
import type { JsonValue, PhaseDef } from '../api/types'
import {
  phaseFromYamlBlock,
  phaseToYamlBlock,
  phaseToolsFromManifest,
  replacePhaseBlock,
  splitSkillMdByPhase,
} from '../utils/yamlAst'

export type PhaseMode = 'llm' | 'logic'

export interface PhaseFormData {
  name: string
  mode: PhaseMode
  llmRole: string
  prompt: string
  userPromptTemplate: string
  agentTools: string[]
  modelOverride: string
  executeSteps: string[]
  validator: string
  when: string
  skipIf: string
}

export interface PhaseFormState {
  phaseId: string
  originalPhase: PhaseDef
  data: PhaseFormData
  yamlBlock: string
}

const EMPTY_DATA: PhaseFormData = {
  name: '',
  mode: 'llm',
  llmRole: '',
  prompt: '',
  userPromptTemplate: '',
  agentTools: [],
  modelOverride: '',
  executeSteps: [],
  validator: '',
  when: '',
  skipIf: '',
}

export function usePhaseForm(markdown: string, phaseId: string | null) {
  const parts = useMemo(() => splitSkillMdByPhase(markdown), [markdown])
  const [state, setState] = useState<PhaseFormState | null>(null)
  const [dirty, setDirty] = useState(false)

  useEffect(() => {
    if (!phaseId) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setState(null)
      setDirty(false)
      return
    }
    const yamlBlock = parts.phases.get(phaseId)
    if (!yamlBlock) {
      setState(null)
      setDirty(false)
      return
    }
    const phase = phaseFromYamlBlock(yamlBlock)
    if (!phase) {
      setState(null)
      setDirty(false)
      return
    }
    setState({
      phaseId,
      originalPhase: phase,
      data: phaseToFormData(phase),
      yamlBlock,
    })
    setDirty(false)
  }, [parts, phaseId])

  const setField = useCallback(<Key extends keyof PhaseFormData>(
    field: Key,
    value: PhaseFormData[Key],
  ) => {
    setState((current) => (
      current
        ? { ...current, data: { ...current.data, [field]: value } }
        : current
    ))
    setDirty(true)
  }, [])

  const reset = useCallback(() => {
    setState((current) => (
      current
        ? { ...current, data: phaseToFormData(current.originalPhase) }
        : current
    ))
    setDirty(false)
  }, [])

  const buildYamlBlock = useCallback(() => {
    if (!state) {
      return null
    }
    return phaseToYamlBlock(formDataToPhase(state.data, state.originalPhase))
  }, [state])

  const applyToMarkdown = useCallback((sourceMarkdown: string = markdown) => {
    const yamlBlock = buildYamlBlock()
    if (!state || !yamlBlock) {
      return sourceMarkdown
    }
    return replacePhaseBlock(sourceMarkdown, state.phaseId, yamlBlock)
  }, [buildYamlBlock, markdown, state])

  return {
    phase: state,
    data: state?.data ?? EMPTY_DATA,
    dirty,
    availableTools: phaseToolsFromManifest(parts.frontmatter),
    setField,
    reset,
    buildYamlBlock,
    applyToMarkdown,
  }
}

export function phaseToFormData(phase: PhaseDef): PhaseFormData {
  const source = phase as unknown as Record<string, JsonValue | undefined>
  return {
    name: phase.name,
    mode: phase.mode,
    llmRole: textValue(source.llm_role),
    prompt: textValue(source.prompt),
    userPromptTemplate: textValue(source.user_prompt_template),
    agentTools: stringArray(source.agent_tools),
    modelOverride: textValue(source.model_override),
    executeSteps: stringArray(source.execute_steps),
    validator: textValue(source.validator),
    when: textValue(source.when),
    skipIf: textValue(source.skip_if),
  }
}

export function formDataToPhase(data: PhaseFormData, originalPhase: PhaseDef): PhaseDef {
  const phase: Record<string, JsonValue> = {
    ...(originalPhase as unknown as Record<string, JsonValue>),
    name: data.name,
    mode: data.mode,
  }

  setOptionalString(phase, 'validator', data.validator)
  setOptionalString(phase, 'when', data.when)
  setOptionalString(phase, 'skip_if', data.skipIf)

  if (data.mode === 'logic') {
    phase.execute_steps = data.executeSteps.length > 0 ? data.executeSteps : ['script.logic.run']
    delete phase.prompt
    delete phase.user_prompt_template
    delete phase.llm_role
    delete phase.agent_tools
    delete phase.model_override
    return phase as unknown as PhaseDef
  }

  setOptionalString(phase, 'llm_role', data.llmRole)
  setOptionalString(phase, 'prompt', data.prompt)
  setOptionalString(phase, 'user_prompt_template', data.userPromptTemplate)
  setOptionalString(phase, 'model_override', data.modelOverride)
  if (data.agentTools.length > 0) {
    phase.agent_tools = data.agentTools
  } else {
    delete phase.agent_tools
  }
  delete phase.execute_steps
  return phase as unknown as PhaseDef
}

function textValue(value: JsonValue | undefined): string {
  return typeof value === 'string' ? value : ''
}

function stringArray(value: JsonValue | undefined): string[] {
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === 'string') : []
}

function setOptionalString(target: Record<string, JsonValue>, key: string, value: string): void {
  if (value.trim()) {
    target[key] = value
  } else {
    delete target[key]
  }
}

export function phaseFormErrors(data: PhaseFormData): Record<string, string> {
  const errors: Record<string, string> = {}
  if (!data.name.trim()) {
    errors.name = 'Phase name is required.'
  }
  if (data.mode === 'llm' && !data.prompt.trim() && !data.userPromptTemplate.trim()) {
    errors.prompt = 'LLM phases need a prompt or user prompt template.'
  }
  if (data.mode === 'logic' && data.executeSteps.length === 0) {
    errors.executeSteps = 'Logic phases need at least one execute step.'
  }
  if (data.executeSteps.some((step) => !step.trim())) {
    errors.executeSteps = 'Execute steps cannot be empty.'
  }
  return errors
}
