import yaml from 'js-yaml'

export type SkillCreatorType = 'agent' | 'graph' | 'persona'
export type SkillInputType = 'str' | 'int' | 'float' | 'bool' | 'dict' | 'list'

export interface WizardInput {
  id: string
  name: string
  type: SkillInputType
  defaultValue: string
}

export interface WizardData {
  type: SkillCreatorType
  skillId: string
  name: string
  description: string
  tags: string
  inputs: WizardInput[]
  phaseId: string
  llmRole: string
  prompt: string
}

function metadataTags(tags: string): string[] {
  return tags
    .split(',')
    .map((tag) => tag.trim())
    .filter(Boolean)
}

function contextMapping(inputs: WizardInput[]): Record<string, string> {
  return Object.fromEntries(inputs.map((input) => [input.name, `{input.${input.name}}`]))
}

function graphFrontmatter(data: WizardData): Record<string, unknown> {
  return {
    schema_version: '2.0',
    name: data.name,
    description: data.description,
    type: 'graph',
    metadata: { tags: metadataTags(data.tags) },
    context_mapping: contextMapping(data.inputs),
    io: {
      inputs: data.inputs.map((input) => ({
        name: input.name,
        type: input.type,
        source: 'runtime',
      })),
      outputs: [{
        name: 'result',
        type: 'dict',
        target: 'file',
        path: 'output/result.json',
      }],
    },
    phases: [{
      name: data.phaseId,
      mode: 'llm',
      llm_role: data.llmRole,
      prompt: data.prompt,
    }],
  }
}

function agentFrontmatter(data: WizardData): Record<string, unknown> {
  return {
    schema_version: '2.0',
    name: data.name,
    description: data.description,
    type: 'agent',
    metadata: { tags: metadataTags(data.tags) },
    context_mapping: contextMapping(data.inputs),
    agent_profile: {
      role: data.llmRole,
      goal: data.description,
      steps: ['Read the provided input', 'Complete the requested task', 'Return the final result'],
      constraints: ['Be concise and explicit'],
      llm_role: data.llmRole,
    },
    user_prompt_template: data.prompt,
  }
}

function personaFrontmatter(data: WizardData): Record<string, unknown> {
  return {
    schema_version: '2.0',
    name: data.name,
    description: data.description,
    type: 'persona',
    metadata: { tags: metadataTags(data.tags) },
    role_profile: data.prompt || data.description,
    evaluation_rubrics: `Use this persona when work requires ${data.description}.`,
  }
}

export function generateSkillMd(data: WizardData): string {
  const frontmatter = data.type === 'graph'
    ? graphFrontmatter(data)
    : data.type === 'agent'
      ? agentFrontmatter(data)
      : personaFrontmatter(data)

  const rendered = yaml.dump(frontmatter, {
    lineWidth: 120,
    noRefs: true,
    sortKeys: false,
  })
  return `---\n${rendered}---\n\n# ${data.name}\n`
}
