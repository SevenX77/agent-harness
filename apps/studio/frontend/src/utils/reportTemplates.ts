import type {
  BatchRunStatus,
  CallbackEvent,
  CompareResult,
  FieldDifference,
  JsonValue,
  RunDetail,
  TokensMetrics,
} from '../api/types'

export type ExportFormat = 'markdown' | 'html'

export interface RunReportData {
  skillId: string
  run: RunDetail
}

export interface CompareReportData {
  skillId: string
  runId?: string | null
  result: CompareResult
}

export interface BatchReportData {
  status: BatchRunStatus
}

const TRACE_LIMIT = 100

export function renderRunReport(data: RunReportData, format: ExportFormat): string {
  return format === 'html' ? renderRunReportHtml(data) : renderRunReportMarkdown(data)
}

export function renderCompareReport(data: CompareReportData, format: ExportFormat): string {
  return format === 'html' ? renderCompareReportHtml(data) : renderCompareReportMarkdown(data)
}

export function renderBatchReport(data: BatchReportData, format: ExportFormat): string {
  return format === 'html' ? renderBatchReportHtml(data) : renderBatchReportMarkdown(data)
}

export function reportTimestamp(date = new Date()): string {
  return date.toISOString().replace(/[:.]/g, '-')
}

export function reportFileBase(...parts: Array<string | null | undefined>): string {
  return parts
    .filter((part): part is string => Boolean(part))
    .map((part) => part.replace(/[^a-zA-Z0-9_-]+/g, '-').replace(/^-+|-+$/g, ''))
    .filter(Boolean)
    .join('_')
}

function renderRunReportMarkdown({ skillId, run }: RunReportData): string {
  const trace = traceSummary(run.events)
  const metrics = metricsMarkdown(run.metadata.metrics)
  return [
    `# Skill Run Report: ${escapeMarkdown(skillId)}`,
    '',
    `- **Run ID**: ${escapeMarkdown(run.metadata.run_id)}`,
    `- **Status**: ${statusIcon(run.metadata.status)} ${escapeMarkdown(run.metadata.status)}`,
    `- **Time**: ${escapeMarkdown(formatDate(run.metadata.started_at))}`,
    metrics,
    '',
    '## Input',
    fencedJson(run.input_data),
    '',
    '## Output',
    fencedJson(run.final_context),
    '',
    '## Artifacts',
    artifactList(run.artifacts),
    '',
    '## Trace Summary',
    trace.length > 0 ? trace.map((event) => `- ${escapeMarkdown(event)}`).join('\n') : 'No trace events recorded.',
  ].join('\n')
}

function renderCompareReportMarkdown({ skillId, runId, result }: CompareReportData): string {
  return [
    `# Golden Diff Report: ${escapeMarkdown(skillId)}`,
    '',
    runId ? `- **Run ID**: ${escapeMarkdown(runId)}` : null,
    `- **Golden Run ID**: ${escapeMarkdown(result.golden_run_id)}`,
    `- **Similarity Score**: ${Math.round(result.total_score * 100)}%`,
    `- **Fields Compared**: ${result.differences.length}`,
    '',
    '## Differences',
    result.differences.length > 0
      ? result.differences.map(diffMarkdown).join('\n\n')
      : 'No differences recorded.',
  ].filter((line): line is string => line !== null).join('\n')
}

function renderBatchReportMarkdown({ status }: BatchReportData): string {
  const success = status.items.filter((item) => item.status === 'success').length
  const failed = status.items.filter((item) => item.status === 'failed').length
  return [
    `# Batch Run Report: ${escapeMarkdown(status.batch_id)}`,
    '',
    `- **Skill ID**: ${escapeMarkdown(status.skill_id)}`,
    `- **Status**: ${escapeMarkdown(status.status)}`,
    `- **Progress**: ${status.completed}/${status.total}`,
    `- **Success / Failed**: ${success} / ${failed}`,
    '',
    '| Input | Run ID | Status | Tokens |',
    '| --- | --- | --- | ---: |',
    ...status.items.map((item) => (
      `| ${escapeTable(item.input_id)} | ${escapeTable(item.run_id)} | ${escapeTable(item.status)} | ${item.metrics?.total_tokens?.toLocaleString() ?? 'n/a'} |`
    )),
  ].join('\n')
}

function renderRunReportHtml(data: RunReportData): string {
  const run = data.run
  return htmlDocument(
    `Skill Run Report: ${data.skillId}`,
    [
      `<h1>Skill Run Report: ${escapeHtml(data.skillId)}</h1>`,
      `<section class="meta">${metaRow('Run ID', run.metadata.run_id)}${metaRow('Status', run.metadata.status)}${metaRow('Time', formatDate(run.metadata.started_at))}${metricsHtml(run.metadata.metrics)}</section>`,
      sectionHtml('Input', `<pre>${escapeHtml(jsonBlock(run.input_data))}</pre>`),
      sectionHtml('Output', `<pre>${escapeHtml(jsonBlock(run.final_context))}</pre>`),
      sectionHtml('Artifacts', run.artifacts?.length ? `<ul>${run.artifacts.map((item) => `<li>${escapeHtml(item)}</li>`).join('')}</ul>` : '<p>No artifacts recorded.</p>'),
      sectionHtml('Trace Summary', traceListHtml(run.events)),
    ].join('\n'),
  )
}

function renderCompareReportHtml(data: CompareReportData): string {
  return htmlDocument(
    `Golden Diff Report: ${data.skillId}`,
    [
      `<h1>Golden Diff Report: ${escapeHtml(data.skillId)}</h1>`,
      `<section class="meta">${data.runId ? metaRow('Run ID', data.runId) : ''}${metaRow('Golden Run ID', data.result.golden_run_id)}${metaRow('Similarity Score', `${Math.round(data.result.total_score * 100)}%`)}${metaRow('Fields Compared', String(data.result.differences.length))}</section>`,
      sectionHtml('Differences', data.result.differences.length ? data.result.differences.map(diffHtml).join('') : '<p>No differences recorded.</p>'),
    ].join('\n'),
  )
}

function renderBatchReportHtml({ status }: BatchReportData): string {
  const success = status.items.filter((item) => item.status === 'success').length
  const failed = status.items.filter((item) => item.status === 'failed').length
  return htmlDocument(
    `Batch Run Report: ${status.batch_id}`,
    [
      `<h1>Batch Run Report: ${escapeHtml(status.batch_id)}</h1>`,
      `<section class="meta">${metaRow('Skill ID', status.skill_id)}${metaRow('Status', status.status)}${metaRow('Progress', `${status.completed}/${status.total}`)}${metaRow('Success / Failed', `${success} / ${failed}`)}</section>`,
      sectionHtml('Runs', `<table><thead><tr><th>Input</th><th>Run ID</th><th>Status</th><th>Tokens</th></tr></thead><tbody>${status.items.map((item) => `<tr><td>${escapeHtml(item.input_id)}</td><td>${escapeHtml(item.run_id)}</td><td>${escapeHtml(item.status)}</td><td>${item.metrics?.total_tokens?.toLocaleString() ?? 'n/a'}</td></tr>`).join('')}</tbody></table>`),
    ].join('\n'),
  )
}

function metricsMarkdown(metrics: TokensMetrics | null): string {
  if (!metrics) {
    return '- **Metrics**: n/a'
  }
  const cost = metrics.cost_estimate === null ? 'n/a' : `$${metrics.cost_estimate.toFixed(4)}`
  return `- **Total Tokens**: ${metrics.total_tokens.toLocaleString()} (${cost})`
}

function metricsHtml(metrics: TokensMetrics | null): string {
  if (!metrics) {
    return metaRow('Metrics', 'n/a')
  }
  const cost = metrics.cost_estimate === null ? 'n/a' : `$${metrics.cost_estimate.toFixed(4)}`
  return metaRow('Total Tokens', `${metrics.total_tokens.toLocaleString()} (${cost})`)
}

function traceSummary(events: CallbackEvent[]): string[] {
  const errors = events.filter((event) => event.event_type === 'internal_error' || event.event_type === 'validation_fail')
  const firstEvents = events.slice(0, TRACE_LIMIT)
  const merged = [...firstEvents]
  for (const event of errors) {
    if (!merged.includes(event)) {
      merged.push(event)
    }
  }
  const lines = merged.map((event) => {
    const phase = event.phase_name ?? event.current_phase ?? 'system'
    const tokens = typeof event.input_tokens === 'number' || typeof event.output_tokens === 'number'
      ? ` tokens=${Number(event.input_tokens ?? 0) + Number(event.output_tokens ?? 0)}`
      : ''
    return `[${phase}] ${event.event_type}${tokens}`
  })
  if (events.length > TRACE_LIMIT) {
    lines.push(`Trace truncated to ${TRACE_LIMIT} entries plus error events (${events.length} total).`)
  }
  return lines
}

function traceListHtml(events: CallbackEvent[]): string {
  const items = traceSummary(events).map((line) => `<li>${escapeHtml(line)}</li>`).join('')
  return items ? `<ul>${items}</ul>` : '<p>No trace events recorded.</p>'
}

function diffMarkdown(field: FieldDifference): string {
  return [
    `### ${escapeMarkdown(field.field_path)}`,
    '',
    `- **Type**: ${escapeMarkdown(field.type)}`,
    `- **Changed**: ${field.changed ? 'yes' : 'no'}`,
    `- **Score**: ${Math.round(field.score * 100)}%`,
    '',
    '**Current**',
    fencedJson(field.current_value),
    '',
    '**Golden**',
    fencedJson(field.golden_value),
  ].join('\n')
}

function diffHtml(field: FieldDifference): string {
  return `<article class="diff"><h3>${escapeHtml(field.field_path)}</h3><p>Type: ${escapeHtml(field.type)} / Changed: ${field.changed ? 'yes' : 'no'} / Score: ${Math.round(field.score * 100)}%</p><div class="columns"><div><h4>Current</h4><pre>${escapeHtml(jsonBlock(field.current_value))}</pre></div><div><h4>Golden</h4><pre>${escapeHtml(jsonBlock(field.golden_value))}</pre></div></div></article>`
}

function htmlDocument(title: string, body: string): string {
  return `<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <title>${escapeHtml(title)}</title>
  <style>
    :root { color-scheme: light dark; }
    body { margin: 0; padding: 32px; font: 14px/1.5 system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; background: #f8fafc; color: #0f172a; }
    main { max-width: 1040px; margin: 0 auto; }
    h1 { margin: 0 0 20px; font-size: 28px; }
    h2 { margin: 0 0 12px; font-size: 18px; }
    h3 { margin: 0 0 8px; font-size: 15px; }
    section, article.diff { margin: 16px 0; border: 1px solid #e2e8f0; border-radius: 8px; background: #fff; padding: 16px; }
    .meta { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 12px; }
    .meta-item { border: 1px solid #e2e8f0; border-radius: 6px; padding: 10px; background: #f8fafc; }
    .meta-label { display: block; color: #64748b; font-size: 11px; font-weight: 700; text-transform: uppercase; }
    pre { overflow: auto; border-radius: 6px; background: #0f172a; color: #f8fafc; padding: 12px; }
    table { width: 100%; border-collapse: collapse; }
    th, td { border-bottom: 1px solid #e2e8f0; padding: 8px; text-align: left; }
    .columns { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; }
    @media (prefers-color-scheme: dark) {
      body { background: #020617; color: #e2e8f0; }
      section, article.diff { background: #0f172a; border-color: #1e293b; }
      .meta-item { background: #020617; border-color: #1e293b; }
      th, td { border-color: #1e293b; }
    }
  </style>
</head>
<body>
  <main>${body}</main>
</body>
</html>`
}

function sectionHtml(title: string, body: string): string {
  return `<section><h2>${escapeHtml(title)}</h2>${body}</section>`
}

function metaRow(label: string, value: string): string {
  return `<div class="meta-item"><span class="meta-label">${escapeHtml(label)}</span><span>${escapeHtml(value)}</span></div>`
}

function artifactList(artifacts: string[] | null): string {
  if (!artifacts?.length) {
    return 'No artifacts recorded.'
  }
  return artifacts.map((artifact) => `- ${escapeMarkdown(artifact)}`).join('\n')
}

function fencedJson(value: JsonValue | null | unknown): string {
  return `\`\`\`json\n${jsonBlock(value)}\n\`\`\``
}

function jsonBlock(value: unknown): string {
  return JSON.stringify(value ?? {}, null, 2)
}

function formatDate(value: string): string {
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString()
}

function statusIcon(status: string): string {
  return status === 'success' ? '✅' : status === 'failed' ? '❌' : '⏳'
}

function escapeMarkdown(value: string): string {
  return value.replace(/([\\`*_{}[\]()#+.!|-])/g, '\\$1')
}

function escapeTable(value: string): string {
  return escapeMarkdown(value).replace(/\|/g, '\\|')
}

function escapeHtml(value: string): string {
  return value
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')
}

