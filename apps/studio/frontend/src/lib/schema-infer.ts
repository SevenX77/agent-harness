import type { JsonObject, JsonValue } from '../api/types'

export type InferredSchema = JsonObject

function inferType(value: JsonValue): InferredSchema {
  if (value === null) {
    return { type: 'null' }
  }

  if (Array.isArray(value)) {
    return {
      type: 'array',
      items: value.length > 0 ? inferType(value[0]) : {},
    }
  }

  if (typeof value === 'object') {
    const properties: JsonObject = {}
    const required: JsonValue[] = []
    Object.entries(value).forEach(([key, nested]) => {
      properties[key] = inferType(nested)
      required.push(key)
    })
    return {
      type: 'object',
      properties,
      required,
    }
  }

  return { type: typeof value }
}

export function inferJsonSchema(value: JsonValue): InferredSchema {
  return inferType(value)
}

export function inferJsonSchemaFromText(text: string): InferredSchema {
  return inferJsonSchema(JSON.parse(text) as JsonValue)
}
