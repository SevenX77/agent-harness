// node shot.mjs <outfile.png> — capture the real app window's page via CDP
import { writeFileSync } from 'node:fs'
const out = process.argv[2]
if (!out) { console.error('usage: node shot.mjs <outfile.png>'); process.exit(1) }
const targets = await (await fetch('http://127.0.0.1:9222/json')).json()
const page = targets.find((t) => t.type === 'page' && /:5173/.test(t.url))
if (!page) { console.error('no :5173 page target'); process.exit(2) }
const ws = new WebSocket(page.webSocketDebuggerUrl)
await new Promise((r) => { ws.onopen = r })
const shot = await new Promise((resolve, reject) => {
  const timer = setTimeout(() => reject(new Error('timeout')), 30000)
  ws.onmessage = (m) => {
    const msg = JSON.parse(m.data)
    if (msg.id === 1) { clearTimeout(timer); resolve(msg.result) }
  }
  ws.send(JSON.stringify({ id: 1, method: 'Page.captureScreenshot', params: { format: 'png' } }))
})
writeFileSync(out, Buffer.from(shot.data, 'base64'))
console.log('saved ' + out)
ws.close()
