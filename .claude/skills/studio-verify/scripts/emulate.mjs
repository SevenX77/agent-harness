// node emulate.mjs <width> <height> | node emulate.mjs clear
import { requireCdpClaim } from './lease-guard.mjs'

requireCdpClaim()

const targets = await (await fetch('http://127.0.0.1:9222/json')).json()
const page = targets.find((t) => t.type === 'page' && /:5173/.test(t.url))
const ws = new WebSocket(page.webSocketDebuggerUrl)
let id = 1; const pend = new Map()
function send(method, params) { return new Promise((res) => { const i = id++; pend.set(i, res); ws.send(JSON.stringify({id: i, method, params: params || {}})) }) }
await new Promise((r) => { ws.onopen = r })
ws.onmessage = (m) => { const msg = JSON.parse(m.data); if (msg.id && pend.has(msg.id)) { pend.get(msg.id)(msg); pend.delete(msg.id) } }
if (process.argv[2] === 'clear') {
  await send('Emulation.clearDeviceMetricsOverride')
  console.log('cleared')
} else {
  const [w, h] = process.argv.slice(2).map(Number)
  await send('Emulation.setDeviceMetricsOverride', {width: w, height: h, deviceScaleFactor: 0, mobile: false})
  console.log('set ' + w + 'x' + h)
}
ws.close()
