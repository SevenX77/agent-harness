// node cdp.mjs "<expression>"  — evaluate JS in the real app window via CDP (port 9222)
const expr = process.argv[2]
if (!expr) { console.error('usage: node cdp.mjs "<expression>"'); process.exit(1) }
const targets = await (await fetch('http://127.0.0.1:9222/json')).json()
const page = targets.find((t) => t.type === 'page' && /:5173/.test(t.url))
if (!page) { console.error('no :5173 page target; targets=' + targets.map(t => t.url).join(', ')); process.exit(2) }
const ws = new WebSocket(page.webSocketDebuggerUrl)
const result = await new Promise((resolve, reject) => {
  const timer = setTimeout(() => reject(new Error('timeout')), 120000)
  ws.onopen = () => {
    ws.send(JSON.stringify({ id: 1, method: 'Runtime.evaluate', params: { expression: expr, returnByValue: true, awaitPromise: true } }))
  }
  ws.onmessage = (m) => {
    const msg = JSON.parse(m.data)
    if (msg.id === 1) { clearTimeout(timer); resolve(msg.result) }
  }
  ws.onerror = (e) => { clearTimeout(timer); reject(new Error('ws error')) }
})
ws.close()
if (result.exceptionDetails) {
  console.error('EXCEPTION:', JSON.stringify(result.exceptionDetails, null, 2))
  process.exit(3)
}
console.log(typeof result.result.value === 'string' ? result.result.value : JSON.stringify(result.result.value, null, 2))
