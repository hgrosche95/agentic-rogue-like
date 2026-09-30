// Frame-exact gameplay capture: the page runs on a virtual clock (timectl.js),
// every captured frame advances it by exactly 1/30 s.
import { chromium } from 'playwright';
import fs from 'fs';
const OUT = process.argv[2] || 'rec2';
const SETTING = process.argv[3] || 'Cyberpunk';
const MAX_FRAMES = +(process.argv[4] || 6000);
const SKIP_INTRO = process.argv[5] === 'skip';
fs.mkdirSync(OUT + '/frames', { recursive: true });
const b = await chromium.launch();
const ctx = await b.newContext({ viewport: { width: 1920, height: 1080 } });
await ctx.addInitScript({ path: new URL('./timectl.js', import.meta.url).pathname });
const p = await ctx.newPage();
let run = null;
p.on('response', async (r) => { if (/\/runs(\/|$)/.test(r.url()) && r.request().method() !== 'OPTIONS') { try { const j = await r.json(); if (j && j.nodes) run = j; } catch {} } });
// steps from a node to the nearest unvisited black market
function shopDistance(id) {
  if (!run) return 99;
  const seen = new Set([id]); let frontier = [id];
  for (let d = 0; d < 12; d++) {
    for (const n of frontier) if (run.nodes[n]?.type === 'shop') return d;
    const next = [];
    for (const n of frontier) for (const c of run.nodes[n]?.connections || []) if (!seen.has(c)) { seen.add(c); next.push(c); }
    frontier = next;
  }
  return 99;
}
const cdp = await ctx.newCDPSession(p);
const frames = []; const events = [];
const FRAME = 1000 / 30;
let n = 0;
async function shot() {
  const { data } = await cdp.send('Page.captureScreenshot', { format: 'jpeg', quality: 90 });
  const name = `f${String(n).padStart(6, '0')}.jpg`;
  fs.writeFileSync(`${OUT}/frames/${name}`, Buffer.from(data, 'base64'));
  frames.push([name, n / 30]);
  n++;
}
async function tick(ms) {
  const k = Math.max(1, Math.round(ms / FRAME));
  for (let i = 0; i < k; i++) {
    await p.evaluate((d) => {
      window.__advance(d);
      // a drag or flight cut short when a fight ends would otherwise stay on screen
      if (!document.querySelector('.hand-zone .hand-card')) document.querySelectorAll('.card-drag, .card-flight').forEach((el) => el.remove());
    }, FRAME);
    await shot();
  }
}
const ev = (e) => { events.push([n / 30, e]); console.log((n / 30).toFixed(1), e); };
const has = async (sel) => (await p.$(sel)) !== null;
const clickText = async (re) => { const l = p.getByRole('button', { name: re }).first(); if (await l.count()) { await l.click(); return true; } return false; };
async function glide(x0, y0, x1, y1, frames) {
  for (let i = 1; i <= frames; i++) {
    const e = i / frames, s = e * e * (3 - 2 * e);
    await p.mouse.move(x0 + (x1 - x0) * s, y0 + (y1 - y0) * s);
    await tick(FRAME);
  }
}

await p.goto('http://localhost:5173');
await p.waitForTimeout(3000); // fonts + images, real time
await tick(300);
if (!SKIP_INTRO) {
  ev('intro');
  for (let i = 0; i < 4; i++) { await tick(i === 2 ? 3500 : 3000); ev('intro-next'); await clickText(/continue/i); }
  ev('agi-message'); await tick(12000); await clickText(/show all/i); await tick(2000);
  await clickText(/accept the challenge/i);
} else {
  await clickText(/skip intro/i);
}
ev('settings'); await tick(1500);
await clickText(new RegExp(SETTING, 'i')); await tick(800);
await p.click('.start-run'); ev('start-run'); await tick(1500);

while (n < MAX_FRAMES) {
  await tick(200);
  const cont = p.getByRole('button', { name: /^continue$/i }).first();
  if (await cont.count() && await cont.isVisible()) { ev('victory'); await tick(1600); await cont.click(); await tick(1200); continue; }
  if (await has('.shop-screen')) {
    ev('shop'); await tick(1500);
    const items = await p.$$('.shop-screen button.reward-card, .shop-screen button.artifact-card');
    for (const it of items) { await it.hover(); await tick(350); }
    const buyable = await p.$$('.shop-screen .shop-item:not(:has(.is-short)):not(:has(.is-sold)) button:not([disabled])');
    if (buyable.length) { await buyable[0].click(); ev('buy'); await tick(1500); }
    const more = await p.$$('.shop-screen .shop-item:not(:has(.is-short)):not(:has(.is-sold)) button:not([disabled])');
    if (more.length) { await more[0].click(); ev('buy'); await tick(1500); }
    await p.click('.shop-screen .reward-skip'); await tick(1500); continue;
  }
  if (await has('.artifact-card')) {
    ev('artifact'); await tick(1400);
    const c = await p.$$('.artifact-card');
    for (const k of [0, 1, 2]) { if (c[k]) { await c[k].hover(); await tick(450); } }
    await c[Math.floor(Math.random() * c.length)].click(); await tick(1200); continue;
  }
  if (await has('.reward-card')) {
    ev('reward'); await tick(1400);
    const c = await p.$$('.reward-card');
    for (const k of [0, 1, 2]) { if (c[k]) { await c[k].hover(); await tick(450); } }
    await c[1].click(); await tick(1200); continue;
  }
  if (await has('.hand-zone .hand-card') || await has('.end-turn-button')) {
    const slot = await p.$('.field-slot.is-empty');
    const cards = await p.$$('.hand-zone .hand-card:not(.is-played):not(.is-discarding)');
    const busy = await has('.end-turn-button[disabled]');
    if (await has('.end-turn-button.is-cancel')) {
      ev('discard');
      const d = await p.$$('.hand-zone .hand-card:not(.is-played)');
      if (d[d.length - 1]) await d[d.length - 1].click();
      await tick(500);
      const conf = p.getByRole('button', { name: /confirm|discard/i }).first();
      if (await conf.count()) await conf.click(); else await p.click('.end-turn-button.is-cancel');
      await tick(1200); continue;
    }
    const over = await has('.intent-badge.is-defeated');
    if (!busy && !over && slot && cards.length) {
      const names = await Promise.all(cards.map((c) => c.innerText()));
      const occupied = (await p.$$('.field-slot.is-occupied')).length;
      const order = names.map((t, i) => [i, /kernel panic/i.test(t) ? (occupied >= 2 ? 0 : 9) : /exploit|zero|payload|overflow|brute/i.test(t) ? 1 : 2]).sort((a, b) => a[1] - b[1]);
      if (order[0][1] < 9) {
        const idx = order[0][0];
        const cb = await cards[idx].boundingBox(); const sb = await slot.boundingBox();
        if (cb && sb) {
          ev('play-card:' + names[idx].split('\n').join(' ').slice(0, 30));
          const x0 = cb.x + cb.width / 2, y0 = cb.y + cb.height / 2;
          await p.mouse.move(x0, y0); await tick(250);
          await p.mouse.down(); await tick(100);
          await glide(x0, y0, sb.x + sb.width / 2, sb.y + sb.height / 2, 14);
          await tick(120); await p.mouse.up();
          await tick(500);
          const after = (await p.$$('.hand-zone .hand-card:not(.is-played):not(.is-discarding)')).length;
          if (after === cards.length && !(await has('.end-turn-button[disabled]'))) {
            ev('click-play');
            const again = await p.$$('.hand-zone .hand-card:not(.is-played):not(.is-discarding)');
            try {
              if (again[idx]) { await again[idx].click({ timeout: 2000, force: true }); await tick(200); const sl = await p.$('.field-slot.is-empty'); if (sl) await sl.click({ timeout: 2000, force: true }); }
            } catch (e) { ev('click-play failed'); }
          }
          await tick(1000);
          continue;
        }
      }
    }
  }
  const et = await p.$('.end-turn-button:not(.is-cancel):not([disabled])');
  if (et) { ev('end-turn'); await et.click(); await tick(2600); continue; }
  const reach = await p.$$('.map-node.is-reachable');
  if (reach.length && !(await has('.jump-panel.is-arrived'))) {
    ev('map'); await tick(1500);
    const types = await Promise.all(reach.map((r) => r.getAttribute('class')));
    const choices = (run?.available_choices || []).map((c) => (typeof c === 'string' ? c : c.id));
    let wantType = null;
    if (!globalThis.__shopSeen && choices.length) {
      const best = choices.map((id) => [id, shopDistance(id)]).sort((a, b) => a[1] - b[1])[0];
      if (best && best[1] < 99) wantType = run.nodes[best[0]].type;
    }
    const rank = (c) => (wantType && c.includes('type-' + wantType + ' ') ? -1 : /type-shop/.test(c) && !globalThis.__shopSeen ? 0 : /type-boss/.test(c) ? 1 : /type-elite/.test(c) ? 2 : /type-combat/.test(c) ? 3 : 5);
    const order = types.map((c, i) => [i, rank(c)]).sort((a, b) => a[1] - b[1]);
    for (const [i] of order.slice(1)) { await reach[i].hover(); await tick(400); }
    const pick = order[0][0];
    if (/type-shop/.test(types[pick])) globalThis.__shopSeen = true;
    await reach[pick].hover(); await tick(600);
    await reach[pick].click({ force: true }); ev('jump:' + types[pick]); await tick(2400);
    continue;
  }
  const jb = await p.$('.jump-button:not([disabled])');
  if (jb) {
    ev('map'); await tick(1500);
    const opts = await p.$$('.jump-options button:not([disabled])');
    if (opts.length > 1) { await opts[opts.length - 1].hover(); await tick(500); await opts[0].hover(); await tick(500); await opts[Math.floor(Math.random() * opts.length)].click(); await tick(600); }
    const jb2 = await p.$('.jump-button:not([disabled])');
    if (jb2) { const txt = await jb2.innerText(); await jb2.click(); ev('jump:' + txt); await tick(2400); }
    continue;
  }
  const evb = await p.$$('.event-prompt button:not([disabled]), .overlay button:not([disabled])');
  if (evb.length) { const txt = await evb[0].innerText(); ev('button:' + txt.slice(0, 40)); await tick(1800); await evb[0].click(); await tick(1500); continue; }
  const body = (await p.innerText('body')).slice(0, 300).replace(/\n/g, ' ');
  if (/victory|defeat|game over|run ended|new run/i.test(body) && !(await has('.hand-card'))) { ev('end:' + body); await tick(5000); break; }
  ev('idle:' + body.slice(0, 120));
  await tick(600);
}
fs.writeFileSync(`${OUT}/frames.json`, JSON.stringify(frames));
fs.writeFileSync(`${OUT}/events.json`, JSON.stringify(events));
await b.close();
