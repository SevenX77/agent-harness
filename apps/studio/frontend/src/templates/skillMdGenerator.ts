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
  templateId: string | null
  templateContent: string | null
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

interface SkillMarkdownParts {
  frontmatter: Record<string, unknown>
  body: string
}

function metadataTags(tags: string): string[] {
  return tags
    .split(',')
    .map((tag) => tag.trim())
    .filter(Boolean)
}

function jsonSchemaProperties(inputs: WizardInput[]): Record<string, Record<string, string>> {
  return Object.fromEntries(inputs.map((input) => [input.name, { type: input.type }]))
}

function splitSkillMarkdown(content: string): SkillMarkdownParts | null {
  const match = /^---\n([\s\S]*?)\n---\n?([\s\S]*)$/m.exec(content)
  if (!match) {
    return null
  }
  const loaded = yaml.load(match[1])
  if (!loaded || typeof loaded !== 'object' || Array.isArray(loaded)) {
    return null
  }
  return {
    frontmatter: loaded as Record<string, unknown>,
    body: match[2],
  }
}

function renderMarkdown(frontmatter: Record<string, unknown>, title: string, body?: string): string {
  const rendered = yaml.dump(frontmatter, {
    lineWidth: 120,
    noRefs: true,
    sortKeys: false,
  })
  const fallbackBody = `# ${title}\n`
  return `---\n${rendered}---\n\n${body?.trim() ? body : fallbackBody}`
}

function graphFrontmatter(data: WizardData): Record<string, unknown> {
  return {
    schema_version: '0.3.0',
    name: data.name,
    description: data.description,
    metadata: { tags: metadataTags(data.tags) },
    io: {
      inputs: {
        type: 'object',
        properties: jsonSchemaProperties(data.inputs),
        additionalProperties: true,
      },
      outputs: {
        type: 'object',
        properties: {
          result: { type: 'object' },
        },
        additionalProperties: true,
      },
    },
    phases: [{
      id: data.phaseId,
      src: `phases/${data.phaseId}/SKILL.md`,
      depends_on: [],
    }],
  }
}

function agentFrontmatter(data: WizardData): Record<string, unknown> {
  return {
    mode: 'agent',
    name: data.name,
    role: data.llmRole,
    goal: data.description,
    exit_contract: 'Return the final result.',
    io: {
      inputs: {
        type: 'object',
        properties: jsonSchemaProperties(data.inputs),
        additionalProperties: true,
      },
      outputs: {
        type: 'object',
        additionalProperties: true,
      },
    },
  }
}

function personaFrontmatter(data: WizardData): Record<string, unknown> {
  return {
    mode: 'agent',
    name: data.name,
    role: data.llmRole,
    goal: data.description,
    exit_contract: `Use this persona when work requires ${data.description}.`,
    io: {
      inputs: {
        type: 'object',
        properties: jsonSchemaProperties(data.inputs),
        additionalProperties: true,
      },
      outputs: {
        type: 'object',
        additionalProperties: true,
      },
    },
  }
}

function objectValue(value: unknown): Record<string, unknown> {
  return value && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, unknown> : {}
}

function templateMarkdown(data: WizardData): string | null {
  if (!data.templateContent) {
    return null
  }
  const parsed = splitSkillMarkdown(data.templateContent)
  if (!parsed) {
    return null
  }
  const frontmatter = { ...parsed.frontmatter }
  frontmatter.name = data.name
  frontmatter.description = data.description
  frontmatter.metadata = {
    ...objectValue(frontmatter.metadata),
    tags: metadataTags(data.tags),
  }

  if (data.type === 'graph') {
    const io = { ...objectValue(frontmatter.io) }
    io.inputs = (graphFrontmatter(data).io as { inputs: unknown }).inputs
    io.outputs = objectValue(io.outputs).type ? io.outputs : (graphFrontmatter(data).io as { outputs: unknown }).outputs
    frontmatter.io = io
  } else if (data.type === 'agent') {
    frontmatter.mode = 'agent'
    frontmatter.role = data.llmRole
    frontmatter.goal = data.description
  } else {
    frontmatter.mode = 'agent'
    frontmatter.role = data.llmRole
    frontmatter.goal = data.prompt || data.description
  }

  return renderMarkdown(frontmatter, data.name, `# ${data.name}\n`)
}

export function generateSkillMd(data: WizardData): string {
  const templated = templateMarkdown(data)
  if (templated) {
    return templated
  }

  const frontmatter = data.type === 'graph'
    ? graphFrontmatter(data)
    : data.type === 'agent'
      ? agentFrontmatter(data)
      : personaFrontmatter(data)

  return renderMarkdown(frontmatter, data.name)
}

function safeType(value: unknown): SkillCreatorType {
  return value === 'graph' || value === 'persona' ? value : 'agent'
}

function safeInputType(value: unknown): SkillInputType {
  return value === 'int' || value === 'float' || value === 'bool' || value === 'dict' || value === 'list'
    ? value
    : 'str'
}

function inputFromIoSchema(schema: unknown): WizardInput[] {
  return Object.entries(objectValue(objectValue(schema).properties))
    .map(([name]) => ({
      id: crypto.randomUUID(),
      name,
      type: 'str',
      defaultValue: '',
    }))
}

export function wizardDataFromSkillMd(content: string, templateId: string | null): WizardData {
  const parsed = splitSkillMarkdown(content)
  const frontmatter = parsed?.frontmatter ?? {}
  const type = safeType(frontmatter.type)
  const metadata = objectValue(frontmatter.metadata)
  const tags = Array.isArray(metadata.tags) ? metadata.tags.filter((tag): tag is string => typeof tag === 'string').join(', ') : ''

  let inputs = inputFromIoSchema(objectValue(frontmatter.io).inputs)
  let phaseId = 'draft'
  let llmRole = 'analyst'
  let prompt = ''

  if (type === 'graph') {
    const io = objectValue(frontmatter.io)
    if (Array.isArray(io.inputs)) {
      inputs = io.inputs
        .map(objectValue)
        .filter((input) => Object.keys(input).length > 0)
        .map((input) => ({
          id: crypto.randomUUID(),
          name: typeof input.name === 'string' ? input.name : 'input_text',
          type: safeInputType(input.type),
          defaultValue: typeof input.default === 'string' ? input.default : '',
        }))
    }
    const phases = Array.isArray(frontmatter.phases) ? frontmatter.phases.map(objectValue) : []
    const phase = phases.find((item) => item.mode === 'llm')
    phaseId = typeof phase?.name === 'string' ? phase.name : phaseId
    llmRole = typeof phase?.llm_role === 'string' ? phase.llm_role : llmRole
    prompt = typeof phase?.prompt === 'string' ? phase.prompt : prompt
  } else if (type === 'agent') {
    const profile = objectValue(frontmatter.agent_profile)
    llmRole = typeof profile.llm_role === 'string' ? profile.llm_role : typeof profile.role === 'string' ? profile.role : llmRole
    prompt = typeof frontmatter.user_prompt_template === 'string' ? frontmatter.user_prompt_template : prompt
  } else {
    prompt = typeof frontmatter.role_profile === 'string' ? frontmatter.role_profile : prompt
  }

  return {
    templateId,
    templateContent: content,
    type,
    skillId: '',
    name: typeof frontmatter.name === 'string' ? frontmatter.name : '',
    description: typeof frontmatter.description === 'string' ? frontmatter.description : '',
    tags,
    inputs: inputs.length > 0 ? inputs : [{
      id: crypto.randomUUID(),
      name: 'input_text',
      type: 'str',
      defaultValue: '',
    }],
    phaseId,
    llmRole,
    prompt: prompt || 'Use {input_text} to complete the task.',
  }
}
