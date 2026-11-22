// Checks that the page can be used before the map has arrived: the join step, a group link, an early search.
// Runs on a slowed network so there is time to press things first. No packages needed: Node 22+ and Chrome.
//   node tools/startcheck.mjs <site address> <database address>     (start tools/serve.py and tools/mockdb.py first)
import { spawn } from 'node:child_process';
import { mkdtempSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
const [SITE, DB] = process.argv.slice(2);
const CHROME = process.env.CHROME || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';
const NET = { offline: false, latency: 400, downloadThroughput: 150000, uploadThroughput: 84375 };
const dir = mkdtempSync(join(tmpdir(), 'func-'));
const chrome = spawn(CHROME, ['--headless=new', '--remote-debugging-port=0', '--user-data-dir=' + dir, '--no-first-run', '--disable-extensions', '--hide-scrollbars', 'about:blank'], { stdio: ['ignore', 'ignore', 'pipe'] });
const wsUrl = await new Promise((ok, no) => { let buf = ''; chrome.stderr.on('data', d => { buf += d; const m = buf.match(/DevTools listening on (ws:\/\/\S+)/); if (m) ok(m[1]); }); setTimeout(() => no(new Error('Chrome did not start')), 15000); });
const ws = new WebSocket(wsUrl); await new Promise(r => ws.addEventListener('open', r));
let seq = 0; const waiting = new Map(), listeners = new Set();
ws.addEventListener('message', e => { const m = JSON.parse(e.data); if (m.id && waiting.has(m.id)) { const [ok, no] = waiting.get(m.id); waiting.delete(m.id); m.error ? no(new Error(m.error.message)) : ok(m.result); } else for (const l of listeners) l(m); });
const send = (method, params = {}, sessionId) => new Promise((ok, no) => { const id = ++seq; waiting.set(id, [ok, no]); ws.send(JSON.stringify({ id, method, params, sessionId })); });
const sleep = ms => new Promise(r => setTimeout(r, ms));
let fails = 0; const check = (name, ok, got) => { if (!ok) fails++; console.log((ok ? 'ok   ' : 'FAIL ') + name + (ok ? '' : '  -> ' + JSON.stringify(got))); };
async function page({ lang = 'en', store = {}, geo = true } = {}) {
  const { browserContextId } = await send('Target.createBrowserContext');
  const { targetId } = await send('Target.createTarget', { url: 'about:blank', browserContextId });
  const { sessionId } = await send('Target.attachToTarget', { targetId, flatten: true });
  const s = (m, p) => send(m, p, sessionId);
  await s('Page.enable'); await s('Network.enable'); await s('Runtime.enable');
  await s('Emulation.setDeviceMetricsOverride', { width: 390, height: 780, deviceScaleFactor: 2, mobile: true });
  await s('Network.emulateNetworkConditions', NET);
  const errors = [];
  const sessions = new Set([sessionId]);
  await s('Target.setAutoAttach', { autoAttach: true, waitForDebuggerOnStart: true, flatten: true });
  const l = m => {
    if (m.method === 'Target.attachedToTarget' && sessions.has(m.sessionId)) { const c = m.params.sessionId, cs = (meth, p) => send(meth, p, c).catch(() => {}); sessions.add(c); cs('Network.enable').then(() => cs('Network.emulateNetworkConditions', NET)).then(() => cs('Runtime.runIfWaitingForDebugger')); return; }
    if (!sessions.has(m.sessionId)) return;
    if (m.method === 'Runtime.exceptionThrown') errors.push(m.params.exceptionDetails.exception?.description || m.params.exceptionDetails.text);
    if (m.method === 'Runtime.consoleAPICalled' && m.params.type === 'error') errors.push(m.params.args.map(a => a.value || a.description).join(' '));
  };
  listeners.add(l);
  if (geo) { await send('Browser.grantPermissions', { permissions: ['geolocation'], browserContextId }); await s('Emulation.setGeolocationOverride', { latitude: 21.0285, longitude: 105.8542, accuracy: 20 }); }
  await s('Page.addScriptToEvaluateOnNewDocument', { source: `try { localStorage.setItem('midpoint-lang', ${JSON.stringify(lang)}); ${Object.entries(store).map(([k, v]) => `localStorage.setItem(${JSON.stringify(k)}, ${JSON.stringify(v)});`).join(' ')} } catch (e) {}` });
  const ev = async x => { const r = await s('Runtime.evaluate', { expression: x, returnByValue: true, awaitPromise: true }); if (r.exceptionDetails) throw new Error(r.exceptionDetails.exception?.description || r.exceptionDetails.text); return r.result.value; };
  const until = async (x, limit = 60000) => { const t0 = Date.now(); while (Date.now() - t0 < limit) { try { if (await ev(x)) return true; } catch (e) {} await sleep(150); } return false; };
  const shot = async name => { const r = await s('Page.captureScreenshot', { format: 'png' }); if (process.env.SHOTS) writeFileSync(join(process.env.SHOTS, name + '.png'), Buffer.from(r.data, 'base64')); };
  return { s, ev, until, shot, errors, go: url => s('Page.navigate', { url }), async close() { listeners.delete(l); await send('Target.disposeBrowserContext', { browserContextId }); } };
}
const put = (p, v) => fetch(DB + '/' + p + '.json', { method: 'PUT', body: JSON.stringify(v) });
const get = p => fetch(DB + '/' + p + '.json').then(r => r.json());
const newRoom = async () => { const id = Array.from({ length: 16 }, () => 'abcdefghijklmnopqrstuvwxyz0123456789'[Math.floor(Math.random() * 36)]).join(''); await put('idx/' + id, { '.sv': 'timestamp' }); const pin = (la, lo, n, c, i) => ({ la, lo, n, t: Date.now() + i, c }); await put('rooms/' + id, { s: { m: 'b', g: 'f' }, pins: { aaaaaaa1: pin(21.0362, 105.7906, 'Minh', 0, 0), aaaaaaa2: pin(20.9716, 105.7788, 'Linh', 1, 1) } }); return id; };
const M = 'window.__midpoint', txt = id => `document.getElementById('${id}').textContent`;

// 1. home, first visit: the join step works before the map; "where I am" pressed early is applied when the map lands
{ const p = await page(); await p.go(SITE + '/');
  await p.until(`document.getElementById('join-name') && ${M}`);
  check('home: join step shown before the map', await p.ev(`!${M}.G && !document.getElementById('join').hidden && document.getElementById('app').classList.contains('joining')`));
  check('home: sub text is the solo one', (await p.ev(txt('join-sub'))).startsWith('Add yourself'));
  await p.ev(`(() => { const i = document.getElementById('join-name'); i.value = 'Kevin'; i.dispatchEvent(new Event('input', { bubbles: true })); document.getElementById('join-here').click(); })()`);
  await p.until(`${txt('join-here')}.startsWith('Adding you')`, 8000);
  check('home: early press waits with a clear label', await p.ev(`!${M}.G && document.getElementById('join-here').disabled && ${txt('join-here')}`) === 'Adding you once the map is here…', await p.ev(txt('join-here')));
  await p.shot('func-home-early');
  await p.ev(`${M}.setLang('vi')`);
  check('home: language switch before the map', await p.ev(`!${M}.G && ${txt('join-here')}`) === 'Sẽ thêm bạn khi bản đồ tải xong…', await p.ev(txt('join-here')));
  await p.ev(`${M}.setLang('en')`);
  check('home: map arrives', await p.until(`!!${M}.G`, 90000));
  await sleep(1200);
  const st = await p.ev(`JSON.stringify({ n: ${M}.state.people.length, me: ${M}.state.people.filter(p => p.me).map(p => p.name), ex: ${M}.state.example, joining: document.getElementById('app').classList.contains('joining') })`);
  check('home: I was added once the map landed, under the typed name', st === JSON.stringify({ n: 1, me: ['Kevin'], ex: false, joining: false }), st);
  check('home: the invite button is there as soon as I am on the map', await p.ev(`(() => { const l = document.getElementById('live'), b = document.getElementById('live-start'); return !l.hidden && !b.hidden && b.getBoundingClientRect().width > 0 ? b.textContent : ''; })()`) === 'Invite the group', await p.ev(`(() => { const l = document.getElementById('live'), b = document.getElementById('live-start'); return !l.hidden && !b.hidden && b.getBoundingClientRect().width > 0 ? b.textContent : ''; })()`));
  await p.shot('func-home-after');
  check('home: no script errors', p.errors.length === 0, p.errors); await p.close(); }

// 2. someone who has been here before: the name is remembered, the place is not, and there is one way to add yourself by location
{ const p = await page({ lang: 'vi', store: { 'midpoint-home': JSON.stringify({ la: 21.0362, lo: 105.7906, w: 'Cầu Giấy' }), 'midpoint-name': 'Lan' } }); await p.go(SITE + '/');
  await p.until(`document.getElementById('join-name') && ${M}`);
  check('saved: one button in the join step, in Vietnamese', await p.ev(`!${M}.G && JSON.stringify([...document.querySelectorAll('#join button')].filter(b => !b.hidden).map(b => b.textContent))`) === JSON.stringify(['Dùng vị trí hiện tại của tôi']), await p.ev(`JSON.stringify([...document.querySelectorAll('#join button')].map(b => b.textContent))`));
  check('saved: name filled from last time', await p.ev(`document.getElementById('join-name').value`) === 'Lan');
  check('saved: the place kept by an earlier version is gone', await p.ev(`localStorage.getItem('midpoint-home')`) === null);
  await p.until(`!!${M}.G`, 90000); await sleep(2500);
  check('saved: the example needs no Find button', await p.ev(`${M}.state.example && !!${M}.state.result && document.getElementById('go').hidden`));
  const xy = await p.ev(`(() => { const m = ${M}; m.state.people = []; m.state.example = false; m.state.result = null; m.changed(true); const a = m.toXY(21.03, 105.82), b = m.toXY(21.0, 105.86); m.addPerson(a[0], a[1], 'A', { quiet: true }); m.changed(true); const one = [document.getElementById('go').hidden, [...document.querySelectorAll('#people .note')].map(n => n.textContent).join('|'), (() => { const l = document.getElementById('live'), b = document.getElementById('live-start'); return !l.hidden && !b.hidden && b.getBoundingClientRect().width > 0 ? b.textContent : ''; })()]; m.addPerson(b[0], b[1], 'B', { quiet: true }); m.changed(true); return JSON.stringify([one, document.getElementById('go').hidden, document.getElementById('go').textContent, document.querySelectorAll('#people .note').length]); })()`);
  check('saved: one person shows the invite button and a line of text, two show the Find button', xy === JSON.stringify([[true, 'Hoặc tự thêm bạn ở ô bên dưới.', 'Mời cả nhóm'], false, 'Tìm điểm hẹn', 0]), xy);
  await p.ev(`document.getElementById('go').click()`); await p.until(`!!${M}.state.result`, 8000);
  check('saved: the button goes once the answer is on its way', await p.ev(`document.getElementById('go').hidden`));
  check('saved: no script errors', p.errors.length === 0, p.errors); await p.close(); }

// 3. group link, first visit: who is here shows before the map; early press lands in the group
{ const id = await newRoom(); const p = await page(); await p.go(SITE + '/#g-' + id);
  await p.until(`${M} && ${M}.room && ${M}.room.ready`, 20000);
  check('group: names known before the map', await p.ev(`!${M}.G && ${txt('join-sub')}`) === 'Minh and Linh are on the map. The meeting place updates as people join.', await p.ev(txt('join-sub')));
  await p.shot('func-group-early');
  await p.ev(`(() => { const i = document.getElementById('join-name'); i.value = 'Kevin'; i.dispatchEvent(new Event('input', { bubbles: true })); document.getElementById('join-here').click(); })()`);
  await p.until(`!!${M}.G`, 90000); await sleep(2500);
  const st = await p.ev(`JSON.stringify(${M}.state.people.map(p => [p.name, !!p.me]))`);
  check('group: three people, I am one of them', st === JSON.stringify([['Minh', false], ['Linh', false], ['Kevin', true]]), st);
  const doc = await get('rooms/' + id); const mine = Object.values(doc.pins).filter(x => x.n === 'Kevin');
  check('group: my pin reached the database', Object.keys(doc.pins).length === 3 && mine.length === 1 && Math.abs(mine[0].la - 21.0285) < 0.002, doc.pins);
  check('group: an answer was found', await p.until(`!!(${M}.state.result && ${M}.state.result.target)`, 15000));
  await p.shot('func-group-after');
  check('group: no script errors', p.errors.length === 0, p.errors);
  // 4. the same device comes back: it is already in, so no join step even before the map
  await p.s('Network.clearBrowserCache'); await p.go('about:blank'); await sleep(300); await p.go(SITE + '/#g-' + id);
  await p.until(`${M} && ${M}.room && ${M}.room.ready`, 20000);
  check('return: no join step for someone already in', await p.ev(`document.getElementById('join').hidden && !document.getElementById('app').classList.contains('joining')`));
  await p.until(`!!${M}.G && ${M}.state.people.length === 3`, 90000);
  check('return: still me', await p.ev(`${M}.state.people.filter(p => p.me).length`) === 1);
  check('return: no script errors', p.errors.length === 0, p.errors); await p.close(); }

// 5. a group link whose group is gone, and a link that carries pins
{ const p = await page(); await p.go(SITE + '/#g-zzzzzzzzzzzzzzzz');
  await p.until(`!!(${M} && ${M}.G)`, 90000); await sleep(1500);
  const st = await p.ev(`JSON.stringify({ room: !!${M}.room, ex: ${M}.state.example, n: ${M}.state.people.length, joining: document.getElementById('app').classList.contains('joining') })`);
  check('ended group: falls back to the example, join step on', st === JSON.stringify({ room: false, ex: true, n: 4, joining: true }), st);
  check('ended group: no script errors', p.errors.length === 0, p.errors); await p.close(); }
{ const p = await page(); await p.go(SITE + '/');
  await p.until(`!!(${M} && ${M}.G)`, 90000); await sleep(500);
  const hash = await p.ev(`(() => { const m = ${M}; m.state.people = []; m.state.example = false; const a = m.toXY(21.03, 105.80), b = m.toXY(21.0, 105.85); m.addPerson(a[0], a[1], 'A'); m.addPerson(b[0], b[1], 'B'); return m.hashNow(); })()`);
  await p.go('about:blank'); await sleep(300); await p.go(SITE + '/#' + hash);
  await p.until(`${M}`, 20000);
  check('pins link: no join step before the map', await p.ev(`!${M}.G && document.getElementById('join').hidden`));
  await p.until(`!!${M}.G && ${M}.state.people.length === 2`, 90000);
  check('pins link: pins loaded', await p.ev(`${M}.state.people.map(p => p.name).join()`) === 'A,B');
  check('pins link: no script errors', p.errors.length === 0, p.errors); await p.close(); }
// 6. straight to the search box before the map: the place names are fetched alongside it and the search answers once both are here
{ const p = await page(); await p.go(SITE + '/');
  await p.until(`document.getElementById('search') && ${M}`);
  await p.ev(`(() => { const i = document.getElementById('search'); i.focus(); i.value = 'Kim Ma'; i.dispatchEvent(new Event('input', { bubbles: true })); })()`);
  check('search: typed before the map', await p.ev(`!${M}.G`));
  check('search: results once the map and the names are here', await p.until(`!!${M}.IX && !document.getElementById('hits').hidden && document.querySelectorAll('#hits li').length > 0`, 120000), await p.ev(`document.getElementById('hits').textContent.slice(0, 80)`));
  check('search: no script errors', p.errors.length === 0, p.errors); await p.close(); }
console.log(fails ? fails + ' FAILED' : 'all passed'); process.exitCode = fails ? 1 : 0;
ws.close(); chrome.kill(); await sleep(300); try { rmSync(dir, { recursive: true, force: true }); } catch (e) {}
