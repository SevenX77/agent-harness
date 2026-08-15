// node console.mjs "<js expression>" [waitMs]
// Run an expression in the real app window and collect console output +
// uncaught exceptions for waitMs (default 4000) — catches silent failures
// where a click visibly does nothing.
const expr = process.argv[2]
const waitMs = Number(process.argv[3] ?? 4000)
if (!expr) { console.error('usage: node console.mjs "<expression>" [waitMs]'); process.exit(1) }
const targets = await (await fetch('http://127.0.0.1:9222/json')).json()
const page = targets.find((t) => t.type === 'page' && /:5173/.test(t.url))
if (!page) { console.error('no :5173 page target'); process.exit(2) }
const ws = new WebSocket(page.webSocketDebuggerUrl)
let id = 1; const pend = new Map(); const logs = []
function send(method, params) { return new Promise((res) => { const i = id++; pend.set(i, res); ws.send(JSON.stringify({ id: i, method, params: params || {} })) }) }
await new Promise((r) => { ws.onopen = r })
ws.onmessage = (m) => {
  const msg = JSON.parse(m.data)
  if (msg.id && pend.has(msg.id)) { pend.get(msg.id)(msg); pend.delete(msg.id); return }
  if (msg.method === 'Runtime.consoleAPICalled') {
    logs.push(msg.params.type + ': ' + msg.params.args.map((a) => a.value ?? a.description ?? '').join(' ').slice(0, 200))
  }
  if (msg.method === 'Runtime.exceptionThrown') {
    logs.push('EXCEPTION: ' + JSON.stringify(msg.params.exceptionDetails).slice(0, 300))
  }
}
await send('Runtime.enable')
await send('Runtime.evaluate', { expression: expr, returnByValue: true, awaitPromise: true })
await new Promise((r) => setTimeout(r, waitMs))
console.log(logs.length ? logs.join('\n') : 'no console output')
ws.close()
