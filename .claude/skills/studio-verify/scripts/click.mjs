// node click.mjs "<selector-expression>" [dblclick]
// Real mouse events via CDP Input domain (needed for Radix/pointerdown components
// and for ReactFlow node clicks). The expression must evaluate to an Element.
const expr = process.argv[2]
const dbl = process.argv[3] === 'dblclick'
if (!expr) { console.error('usage: node click.mjs "<element expression>" [dblclick]'); process.exit(1) }
const targets = await (await fetch('http://127.0.0.1:9222/json')).json()
const page = targets.find((t) => t.type === 'page' && /:5173/.test(t.url))
if (!page) { console.error('no :5173 page target'); process.exit(2) }
const ws = new WebSocket(page.webSocketDebuggerUrl)
let nextId = 1
const pending = new Map()
function send(method, params) {
  return new Promise((resolve, reject) => {
    const id = nextId++
    pending.set(id, { resolve, reject })
    ws.send(JSON.stringify({ id, method, params }))
  })
}
await new Promise((r) => { ws.onopen = r })
ws.onmessage = (m) => {
  const msg = JSON.parse(m.data)
  if (msg.id && pending.has(msg.id)) { pending.get(msg.id).resolve(msg); pending.delete(msg.id) }
}
const evalRes = await send('Runtime.evaluate', {
  expression: `(() => { const el = ${expr}; if (!el) return null; el.scrollIntoView({block:'center'}); const r = el.getBoundingClientRect(); return {x: r.x + r.width/2, y: r.y + r.height/2} })()`,
  returnByValue: true,
})
const pt = evalRes.result?.result?.value
if (!pt) { console.error('element not found for: ' + expr); ws.close(); process.exit(3) }
const clickCount = dbl ? 2 : 1
await send('Input.dispatchMouseEvent', { type: 'mouseMoved', x: pt.x, y: pt.y, button: 'none', pointerType: 'mouse' })
for (let i = 1; i <= clickCount; i++) {
  await send('Input.dispatchMouseEvent', { type: 'mousePressed', x: pt.x, y: pt.y, button: 'left', clickCount: i, pointerType: 'mouse' })
  await send('Input.dispatchMouseEvent', { type: 'mouseReleased', x: pt.x, y: pt.y, button: 'left', clickCount: i, pointerType: 'mouse' })
}
console.log(`clicked (${dbl ? 'double' : 'single'}) at ${Math.round(pt.x)},${Math.round(pt.y)}`)
ws.close()
