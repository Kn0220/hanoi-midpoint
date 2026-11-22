// Time the page's main journeys in headless Chrome at phone speed (slowed CPU, 4G network). No packages needed: Node 22+ and Chrome.
//   node tools/bench.mjs <site address> <database address> [runs]
// Start tools/serve.py and tools/mockdb.py first. Prints the median of each mark, in ms from the start of navigation.
import { spawn } from 'node:child_process';
import { mkdtempSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
const [SITE, DB, RUNS = '3'] = process.argv.slice(2);
const CHROME = process.env.CHROME || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';
const NETS = { fast4g: { latency: 165, downloadThroughput: 1012500, uploadThroughput: 168750 }, slow4g: { latency: 562.5, downloadThroughput: 180000, uploadThroughput: 84375 } };
const CPU = +(process.env.CPU || 4), DETAIL = !!process.env.DETAIL, ONLY = process.env.NET;   // DETAIL=1 adds each long task, each layout shift with what moved, and the page's own timers; NET=fast4g runs one network only
const dir = mkdtempSync(join(tmpdir(), 'bench-'));
const chrome = spawn(CHROME, ['--headless=new', '--remote-debugging-port=0', '--user-data-dir=' + dir, '--no-first-run', '--disable-extensions', '--hide-scrollbars', 'about:blank'], { stdio: ['ignore', 'ignore', 'pipe'] });
const wsUrl = await new Promise((ok, no) => { let buf = ''; chrome.stderr.on('data', d => { buf += d; const m = buf.match(/DevTools listening on (ws:\/\/\S+)/); if (m) ok(m[1]); }); setTimeout(() => no(new Error('Chrome did not start')), 15000); });
const ws = new WebSocket(wsUrl); await new Promise(r => ws.addEventListener('open', r));
let seq = 0; const waiting = new Map(), listeners = new Set();
ws.addEventListener('message', e => { const m = JSON.parse(e.data); if (m.id && waiting.has(m.id)) { const [ok, no] = waiting.get(m.id); waiting.delete(m.id); m.error ? no(new Error(m.error.message)) : ok(m.result); } else for (const l of listeners) l(m); });
const send = (method, params = {}, sessionId) => new Promise((ok, no) => { const id = ++seq; waiting.set(id, [ok, no]); ws.send(JSON.stringify({ id, method, params, sessionId })); });
const sleep = ms => new Promise(r => setTimeout(r, ms));
const WATCH = `window.__lt = []; window.__ls = []; try { new PerformanceObserver(l => { for (const e of l.getEntries()) window.__lt.push([Math.round(e.startTime), Math.round(e.duration)]); }).observe({ type: 'longtask', buffered: true }); new PerformanceObserver(l => { for (const e of l.getEntries()) if (!e.hadRecentInput) window.__ls.push([Math.round(e.startTime), +e.value.toFixed(4), (e.sources || []).map(s => { const n = s.node, p = s.previousRect, c = s.currentRect; return (n ? (n.id ? '#' + n.id : n.nodeName.toLowerCase() + (n.className && n.className.baseVal === undefined ? '.' + String(n.className).split(' ')[0] : '')) : '?') + ' ' + [p.x, p.y, p.width, p.height].map(Math.round).join(',') + ' > ' + [c.x, c.y, c.width, c.height].map(Math.round).join(','); })]); }).observe({ type: 'layout-shift', buffered: true }); } catch (e) {}`;
const READ = `JSON.stringify({ marks: Object.fromEntries(performance.getEntriesByType('mark').map(m => [m.name, Math.round(m.startTime)])), fcp: Math.round((performance.getEntriesByName('first-contentful-paint')[0] || {}).startTime || 0), lt: window.__lt, ls: window.__ls, perf: (window.__midpoint || {}).perf })`;

async function newPage(net) {
  const { browserContextId } = await send('Target.createBrowserContext');
  const { targetId } = await send('Target.createTarget', { url: 'about:blank', browserContextId });
  const { sessionId } = await send('Target.attachToTarget', { targetId, flatten: true });
  const s = (m, p) => send(m, p, sessionId);
  await s('Page.enable'); await s('Network.enable'); await s('Runtime.enable');
  await s('Emulation.setDeviceMetricsOverride', { width: 390, height: 780, deviceScaleFactor: 3, mobile: true });
  await s('Emulation.setTouchEmulationEnabled', { enabled: true });
  await s('Network.emulateNetworkConditions', { offline: false, ...NETS[net] });
  await s('Emulation.setCPUThrottlingRate', { rate: CPU });
  await s('Page.addScriptToEvaluateOnNewDocument', { source: WATCH });
  const bytes = { n: 0, total: 0, by: {} };
  const urls = new Map();
  const sessions = new Set([sessionId]);    // the page and the workers it starts: a worker's downloads are slowed and counted like the page's own
  await s('Target.setAutoAttach', { autoAttach: true, waitForDebuggerOnStart: true, flatten: true });
  const l = m => {
    if (m.method === 'Target.attachedToTarget' && sessions.has(m.sessionId)) { const c = m.params.sessionId, cs = (meth, p) => send(meth, p, c).catch(() => {}); sessions.add(c); cs('Network.enable').then(() => cs('Network.emulateNetworkConditions', { offline: false, ...NETS[net] })).then(() => cs('Emulation.setCPUThrottlingRate', { rate: CPU })).then(() => cs('Runtime.runIfWaitingForDebugger')); return; }
    if (!sessions.has(m.sessionId)) return; if (m.method === 'Network.requestWillBeSent') urls.set(m.params.requestId, m.params.request.url); if (m.method === 'Network.loadingFinished') { const u = urls.get(m.params.requestId) || ''; if (u.startsWith('blob:')) return; bytes.n++; bytes.total += m.params.encodedDataLength; const k = u.split('/').pop().split('?')[0].slice(0, 28) || 'page'; bytes.by[k] = (bytes.by[k] || 0) + m.params.encodedDataLength; }
  };
  listeners.add(l);
  return { s, bytes, reset() { bytes.n = 0; bytes.total = 0; bytes.by = {}; }, async close() { listeners.delete(l); await send('Target.disposeBrowserContext', { browserContextId }); } };
}
async function visit(page, url, until, limit = 90000) {
  page.reset(); await page.s('Page.navigate', { url: 'about:blank' }); await sleep(300); page.reset();
  await page.s('Page.navigate', { url });
  const t0 = Date.now(); let out = null;
  while (Date.now() - t0 < limit) { await sleep(250); try { const r = await page.s('Runtime.evaluate', { expression: READ, returnByValue: true }); out = JSON.parse(r.result.value); if (out.marks[until]) break; } catch (e) {} }
  await sleep(1500);                         // let the first drawing and any late shifts land
  const r = await page.s('Runtime.evaluate', { expression: READ, returnByValue: true }); out = JSON.parse(r.result.value);
  const usable = out.marks['mp-typeable'] || 0;
  return { fcp: out.fcp, ...out.marks, blocked: out.lt.reduce((a, [, d]) => a + Math.max(0, d - 50), 0), longest: Math.max(0, ...out.lt.map(x => x[1])), shiftAfterUsable: +out.ls.filter(([t]) => usable && t > usable).reduce((a, [, v]) => a + v, 0).toFixed(4), kB: Math.round(page.bytes.total / 1024), requests: page.bytes.n, ...(DETAIL ? { detail: { tasks: out.lt, shifts: out.ls, perf: out.perf, files: page.bytes.by } } : {}) };
}
async function room() {                      // a group with three friends already in it
  const id = Array.from({ length: 16 }, () => 'abcdefghijklmnopqrstuvwxyz0123456789'[Math.floor(Math.random() * 36)]).join('');
  const put = (p, v) => fetch(DB + '/' + p + '.json', { method: 'PUT', body: JSON.stringify(v) }).then(r => { if (!r.ok) throw new Error('database said ' + r.status + ' for ' + p); });
  await put('idx/' + id, { '.sv': 'timestamp' });
  const pin = (la, lo, n, c, i) => ({ la, lo, n, t: Date.now() + i, c });
  await put('rooms/' + id, { s: { m: 'b', g: 'f' }, pins: { aaaaaaa1: pin(21.0362, 105.7906, 'Minh', 0, 0), aaaaaaa2: pin(20.9716, 105.7788, 'Linh', 1, 1), aaaaaaa3: pin(21.0477, 105.8889, 'Huy', 2, 2) } });
  return id;
}
const median = a => { const b = a.filter(x => x !== undefined).sort((x, y) => x - y); return b.length ? b[Math.floor(b.length / 2)] : undefined; };
const results = {};
for (const net of Object.keys(NETS).filter(n => !ONLY || n === ONLY)) {
  const runs = { 'home, first visit': [], 'home, return visit': [], 'group link, first visit': [], 'group link, return visit': [] };
  for (let i = 0; i < +RUNS; i++) {
    let p = await newPage(net);
    runs['home, first visit'].push(await visit(p, SITE + '/', 'mp-answer'));
    runs['home, return visit'].push(await visit(p, SITE + '/', 'mp-answer'));
    await p.close(); p = await newPage(net);
    const id = await room();
    runs['group link, first visit'].push(await visit(p, SITE + '/#g-' + id, 'mp-answer'));
    runs['group link, return visit'].push(await visit(p, SITE + '/#g-' + id, 'mp-answer'));
    await p.close();
  }
  for (const [name, list] of Object.entries(runs)) { const keys = [...new Set(list.flatMap(Object.keys))]; results[net + ' | ' + name] = Object.fromEntries(keys.map(k => [k, k === 'detail' ? list[0][k] : median(list.map(r => r[k]))])); }
}
console.log(JSON.stringify(results, null, 1));
ws.close(); chrome.kill(); await sleep(300); try { rmSync(dir, { recursive: true, force: true }); } catch (e) {}
