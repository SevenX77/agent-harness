import i18n from '@/i18n'
import type { ProviderType } from '@/api/llm'

/**
 * How a route is named to a reader who has to pick one.
 *
 * A provider's display name does NOT identify a route: one name routinely
 * covers several base URLs and several protocols. Measured 2026-08-21 in the
 * node `Add compare LLM` dialog — one model offered 17 endpoint options, of
 * which seven read `Qiniu` and nothing else. Choosing was a coin toss.
 *
 * `00_settings-ux-spec.md` §2.1 already says what has to be shown —「tooltip
 * 列出每条 transport（URL × 协议 × 各自 6 态）」— and §1.2 already says how much
 * of it: an endpoint id is 「默认最短」 and only grows when it collides. This
 * module is those two rules applied to a LIST: name every route as briefly as
 * the list allows, and never let two of them read the same.
 */

/** The part of a base URL a reader recognises: the host, minus its TLD. */
export function hostLabel(value: string): string {
  const compactHost = (host: string) => {
    if (!host || host === 'localhost' || /^\d{1,3}(?:\.\d{1,3}){3}(?::\d+)?$/.test(host)) return host
    const [hostname, port] = host.split(':')
    const labels = hostname.split('.').filter(Boolean)
    const compact = labels.length >= 2 ? labels.slice(0, -1).join('.') : hostname
    return port ? `${compact}:${port}` : compact
  }

  try {
    const parsed = new URL(value)
    return compactHost(parsed.host) || value
  } catch {
    return compactHost(value.replace(/^https?:\/\//, '').replace(/\/.*$/, '')) || value
  }
}

/** The protocol FAMILY as an annotation ("OpenAI-compatible"), never a vendor name. */
export function protocolFamilyLabel(protocol: ProviderType | null | undefined): string {
  if (protocol === 'anthropic_compatible') return i18n.t('apiKeys.card.protocolFamily.anthropic')
  if (protocol === 'google_genai') return i18n.t('apiKeys.card.protocolFamily.gemini')
  if (protocol === 'openai_compatible') return i18n.t('apiKeys.card.protocolFamily.openai')
  if (protocol === 'ark_runtime') return i18n.t('apiKeys.card.protocolFamily.ark')
  return i18n.t('apiKeys.card.protocolFamily.unknown')
}

/**
 * One transport: `api.deepseek · OpenAI-compatible`.
 *
 * J-01.L (批示轮三 R3-10): the FIRST name is the provider's identity — its
 * host — and the protocol family is a trailing annotation. The old order
 * (`OpenAI / api.deepseek.com`) put the protocol family's vendor word in the
 * first-name position, so a DeepSeek official card read "OpenAI" to the user
 * (fresh-journey screenshots f09/f13).
 */
export function transportLabel(
  protocol: ProviderType | null | undefined,
  baseUrl: string | null | undefined,
): string {
  return `${hostLabel(baseUrl ?? '')} · ${protocolFamilyLabel(protocol)}`
}

export interface RouteLabelInput {
  route_id: string
  endpoint_id?: string | null
  provider_label: string
  provider_model_id: string
  base_url?: string | null
  protocol?: ProviderType | null
}

const SEPARATOR = ' · '

/**
 * A label per route, each as short as it can be and still tell the others apart.
 *
 * The rule is §1.2's collision rule generalized: start from the provider name,
 * and among the routes that SHARE that name, append only the fields that vary
 * between them — transport first (it is what a reader chooses by), then the
 * model id. Fields shared by the whole set are left out: repeating
 * `OpenAI / api.qnaigc` on every row costs the width that the one differing
 * field needs, in a row that truncates.
 *
 * The postcondition is uniqueness, not brevity: if two routes agree on every
 * readable field, the last resort is the route id, which is unique by
 * construction. A list that hands back two identical labels has not answered
 * the question it exists to answer.
 */
export function distinguishingRouteLabels(routes: readonly RouteLabelInput[]): Map<string, string> {
  const byProvider = new Map<string, RouteLabelInput[]>()
  for (const route of routes) {
    const key = baseName(route).toLowerCase()
    byProvider.set(key, [...(byProvider.get(key) ?? []), route])
  }

  const labels = new Map<string, string>()
  for (const siblings of byProvider.values()) {
    const varies = (of: (route: RouteLabelInput) => string) =>
      new Set(siblings.map(of)).size > 1
    const parts: Array<(route: RouteLabelInput) => string> = []
    if (varies(routeTransport)) parts.push(routeTransport)
    if (varies(routeModelId)) parts.push(routeModelId)
    for (const route of siblings) {
      const said = [baseName(route), ...parts.map((part) => part(route))].filter(Boolean)
      labels.set(route.route_id, said.join(SEPARATOR))
    }
  }

  return disambiguated(routes, labels)
}

function baseName(route: RouteLabelInput): string {
  return route.provider_label.trim() || route.endpoint_id?.trim() || route.route_id
}

function routeTransport(route: RouteLabelInput): string {
  return transportLabel(route.protocol, route.base_url)
}

function routeModelId(route: RouteLabelInput): string {
  return route.provider_model_id.trim()
}

/** Last resort: routes that read the same are told apart by the id that cannot repeat. */
function disambiguated(
  routes: readonly RouteLabelInput[],
  labels: Map<string, string>,
): Map<string, string> {
  const count = new Map<string, number>()
  for (const label of labels.values()) count.set(label, (count.get(label) ?? 0) + 1)
  for (const route of routes) {
    const label = labels.get(route.route_id)
    if (label === undefined || (count.get(label) ?? 0) < 2) continue
    labels.set(route.route_id, [label, route.route_id].join(SEPARATOR))
  }
  return labels
}
