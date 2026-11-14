// Playwright crawler for full-size product image URLs on toimitustukku.valioaimo.fi
// (#108; the organisers OK'd using the portal). Builds the raw crawl that
// scripts/build_image_map.py turns into data/product_images.json.gz; the raw crawl
// itself is never committed. See that script's header for the whole rebuild.
//
// Needs a signed-in portal session: it opens a visible browser window with a
// persistent profile (~/.cache/junction-valio-<engine>, outside the repository) and
// YOU sign in there; the script never handles credentials, cookies or tokens. It then
// walks product pages inside the
// shop's own app (in-app route changes) and appends one JSON line per product to
// the results file, so progress is saved continuously. On logout it pauses and
// waits for you to sign in again in the same window.
//
// Modes:
//   listed  crawl shop codes from the listing export that are not crawled yet
//   gtin    search the shop by GTIN for dataset products that are still unmapped,
//           then crawl the product codes found
//   name    search by exact Finnish name for products still missing from the map
//
// Usage (needs the playwright package and its browsers installed):
//   node scripts/portal_crawler_pw.mjs --mode listed [--engine webkit|chromium]
//
// Inputs:  ~/Downloads/valio_portal_images_latest.json (export from the in-page crawler)
//          ~/Downloads/valio_aimo_junction26_product_data.json (the static product file;
//          gtin and name modes); override with --export and --products
// Output:  ~/Downloads/valio_portal_details.jsonl (--out)
import { createRequire } from 'node:module';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import zlib from 'node:zlib';

const require = createRequire(process.env.PW_NODE_MODULES ? path.join(process.env.PW_NODE_MODULES, 'x.js') : import.meta.url);
const { webkit, chromium } = require('playwright');

const args = Object.fromEntries(process.argv.slice(2).reduce((a, v, i, arr) => (v.startsWith('--') ? [...a, [v.slice(2), arr[i + 1]]] : a), []));
const MODE = args.mode || 'listed';
const ENGINE = args.engine || 'webkit';
const DL = path.join(os.homedir(), 'Downloads');
const EXPORT = args.export || path.join(DL, 'valio_portal_images_latest.json');
const PRODUCTS = args.products || path.join(DL, 'valio_aimo_junction26_product_data.json');
const OUT = args.out || path.join(DL, 'valio_portal_details.jsonl');
const PROFILE = args.profile || path.join(os.homedir(), '.cache', `junction-valio-${ENGINE}`);
const BASE = 'https://toimitustukku.valioaimo.fi';
const PAUSE_MS = Number(args.pause || 300); // politeness pause between products

const log = (...a) => console.log(new Date().toISOString().slice(11, 19), ...a);
const gkey = (g) => (String(g || '').replace(/\D/g, '').replace(/^0+/, '') || null);

// ---- state from previous runs ----
const exp = fs.existsSync(EXPORT) ? JSON.parse(fs.readFileSync(EXPORT, 'utf8')) : { listing: [], details: [] };
const done = new Map(); // code -> record with ean/imgs
const searched = new Set(); // gtins already searched
const hitGtins = new Set(); // searched gtins that found at least one product
for (const d of exp.details || []) if (!d.err) done.set(d.code, d);
if (fs.existsSync(OUT)) {
  for (const line of fs.readFileSync(OUT, 'utf8').split('\n')) {
    if (!line.trim()) continue;
    try {
      const r = JSON.parse(line);
      if (r.type === 'search') { searched.add(r.gtin); if (r.codes?.length) hitGtins.add(r.gtin); }
      else if (!r.err) done.set(r.code, r);
    } catch {}
  }
}
let lastProgress = Date.now();
const append = (r) => { fs.appendFileSync(OUT, JSON.stringify(r) + '\n'); lastProgress = Date.now(); };
// Watchdog: WebKit occasionally hangs a page call with no timeout. If nothing was saved
// for 3 minutes (and we are not waiting for a sign-in), exit 3 so the wrapper restarts us.
let waitingForSignIn = false;
setInterval(() => { if (!waitingForSignIn && Date.now() - lastProgress > 180000) { console.log('watchdog: no progress for 3 min, exiting for restart'); process.exit(3); } }, 15000).unref();
log(`resume: ${done.size} products crawled, ${searched.size} GTINs searched; mode=${MODE} engine=${ENGINE}`);

// ---- browser ----
const engine = ENGINE === 'chromium' ? chromium : webkit;
const ctx = await engine.launchPersistentContext(PROFILE, { headless: false, viewport: { width: 1280, height: 900 }, locale: 'fi-FI' });
const page = ctx.pages()[0] || (await ctx.newPage());

async function isLoggedOut() {
  const url = page.url();
  if (/\/login|kirjautuminen\./i.test(url)) return true;
  const t = (await Promise.race([page.title().catch(() => ''), new Promise((r) => setTimeout(() => r(''), 5000))])) || '';
  return /Kirjautuminen|Aimo-Logout/i.test(t);
}
async function ensureLoggedIn() {
  if (!(await isLoggedOut()) && page.url().startsWith(BASE)) return;
  if (!page.url().startsWith(BASE)) await page.goto(BASE + '/fi/', { waitUntil: 'domcontentloaded' }).catch(() => {});
  if (await isLoggedOut()) {
    log('>>> Logged out. Please sign in in the browser window. Waiting...');
    waitingForSignIn = true;
    while (await isLoggedOut() || !page.url().startsWith(BASE)) await page.waitForTimeout(3000);
    log('>>> Signed in, continuing.');
    waitingForSignIn = false; lastProgress = Date.now();
  }
  // Boot the app on a known page so in-app navigation works.
  await page.waitForLoadState('domcontentloaded').catch(() => {});
  await page.waitForTimeout(2000);
}

// page.evaluate with a timeout: a hung evaluate (seen once in WebKit) must not freeze the run.
const ev = (fn, arg, ms = 5000) => Promise.race([page.evaluate(fn, arg).catch(() => null), new Promise((r) => setTimeout(() => r(null), ms))]);

// Poll a page function from Node. page.waitForFunction cannot be used here: the
// shop's Angular Zone.js patches Promise, and waitForFunction then resolves at once
// with a ZoneAwarePromise instead of the predicate's value.
async function poll(fn, arg, timeout, every = 200) {
  const end = Date.now() + timeout;
  for (;;) {
    const v = await ev(fn, arg);
    if (v) return v;
    if (Date.now() > end) return null;
    await page.waitForTimeout(every);
  }
}

// In-app navigation: same as clicking a link inside the shop app.
async function spaGo(p) {
  await ev((p) => { history.pushState({}, '', p); dispatchEvent(new PopStateEvent('popstate', { state: {} })); }, p);
}

async function crawlProduct(code, prevImg) {
  await spaGo('/fi/p/' + code);
  const res = await poll(
    (code) => {
      const t = document.querySelector('main')?.innerText || '';
      const m = t.match(new RegExp('\\b' + code + '\\b[^\\n]{0,40}?EAN\\s*(\\d{8,14})'));
      if (m) return { ean: m[1] };
      if (/ei löytynyt/i.test(document.title)) return { nf: true };
      if (t.includes(code)) { window.__seen = window.__seen || {}; window.__seen[code] = window.__seen[code] || performance.now(); if (performance.now() - window.__seen[code] > 2500) return { noean: true }; }
      return null;
    },
    code,
    10000,
  );
  if (!res) return { code, err: (await isLoggedOut()) ? 'loggedout' : 'timeout' };
  if (res.nf) return { code, err: 'notfound' };
  // Wait for the gallery to show this product's image (differs from previous), max 1.5 s.
  await poll((prev) => { const s = document.querySelector('aimo-product-images img')?.getAttribute('src'); return !!s && s !== prev; }, prevImg, 1500, 100);
  const info = (await ev(() => ({
    imgs: [...new Set([...document.querySelectorAll('aimo-product-images img')].map((i) => i.getAttribute('src')).filter((s) => s && s.includes('/medias/')))],
    name: document.querySelector('h1')?.innerText.trim() || null,
  }))) || { imgs: [], name: null };
  return { code, ean: res.ean || null, name: info.name, imgs: info.imgs, sameAsPrev: !!prevImg && info.imgs[0] === prevImg };
}

// Search the shop for q (a GTIN or a product name). Returns {n, codes, names} for the
// main results (after the "N tuotetta" counter; the carousel above them is excluded).
async function searchQuery(q) {
  await spaGo('/fi/search/' + encodeURIComponent(q));
  const r = await poll(
      (q) => {
        // The previous search's results linger briefly, so only accept text that names this query.
        const t = document.querySelector('main')?.innerText || '';
        if (t.includes('"' + q + '" ei valitettavasti löytynyt')) return { n: 0, codes: [], names: [] };
        if (!t.includes('Tulokset haulle "' + q + '"') || /Ladataan/.test(t)) return null;
        const counter = [...document.querySelectorAll('main *')].find((e) => e.children.length === 0 && /^\s*\d+ tuotetta\s*$/.test(e.textContent));
        if (!counter) return null;
        const n = Number(counter.textContent.match(/\d+/)[0]);
        if (n === 0) return { n: 0, codes: [], names: [] };
        const items = [...document.querySelectorAll('.aimo-product-grid-item')].filter((e) => counter.compareDocumentPosition(e) & Node.DOCUMENT_POSITION_FOLLOWING);
        if (items.length < Math.min(n, 1)) return null;
        return { n, codes: items.map((e) => e.id.replace('product_', '')), names: items.map((e) => e.querySelector('.cx-product-name')?.textContent.trim() || '') };
      },
      q,
      15000,
      250,
  );
  return r;
}
const searchGtin = searchQuery;
const normName = (s) => String(s || '').normalize('NFKC').toLowerCase().replace(/[®™©]/g, '').replace(/\s+/g, ' ').trim();

let prevImg = null;
let n = 0;
const t0 = Date.now();
async function doCode(code) {
  for (let attempt = 0; attempt < 3; attempt++) {
    await ensureLoggedIn();
    const rec = await crawlProduct(code, prevImg);
    if (rec.err === 'loggedout' || (rec.err === 'timeout' && attempt < 2)) continue;
    rec.ts = Date.now();
    append(rec);
    if (!rec.err) { done.set(code, rec); prevImg = rec.imgs[0] || prevImg; }
    n++;
    if (n % 25 === 0) log(`${n} this run (${(n / ((Date.now() - t0) / 1000)).toFixed(2)}/s), total crawled ${done.size}, last ${code}${rec.err ? ' ' + rec.err : ''}`);
    await page.waitForTimeout(PAUSE_MS);
    return rec;
  }
}

await page.goto(BASE + '/fi/', { waitUntil: 'domcontentloaded' }).catch(() => {});
await ensureLoggedIn();

if (MODE === 'listed') {
  const queue = [...new Set((exp.listing || []).map((i) => i.code))].sort().filter((c) => !done.has(c));
  log(`listed mode: ${queue.length} codes to crawl`);
  for (const code of queue) await doCode(code);
} else if (MODE === 'gtin') {
  const products = JSON.parse(fs.readFileSync(PRODUCTS, 'utf8'));
  const known = new Set([...done.values()].map((d) => gkey(d.ean)).filter(Boolean));
  // Per product: all its distinct GTINs, sales unit first. A product is pending while
  // none of its GTINs is a known shop EAN or a successful search. When one GTIN misses,
  // the next one is tried (the shop often knows the consumer-unit GTIN, not the case one).
  const todo = [];
  for (const p of products) {
    const gs = [...new Set([p.salesUnitGtin, p.synkkaData?.gtin, ...(p.units || []).map((u) => u.gtin)].map(gkey).filter(Boolean))];
    if (!gs.length || gs.some((g) => known.has(g) || hitGtins.has(g))) continue;
    const left = gs.filter((g) => !searched.has(g));
    if (left.length) todo.push(Object.assign(left, { fresh: left.length === gs.length }));
  }
  // Never-searched products first (high hit rate); alternate GTINs of misses last.
  todo.sort((a, b) => b.fresh - a.fresh);
  log(`gtin mode: ${todo.filter((l) => l.fresh).length} never-searched products first, then ${todo.filter((l) => !l.fresh).length} retries with alternate GTINs`);
  log(`gtin mode: ${todo.length} dataset products pending, ${todo.reduce((a, l) => a + l.length, 0)} GTINs to try`);

  // A silently expired session still shows the shop, but every search returns nothing.
  // So misses are held back until confirmed: a hit confirms them, and after 8 misses in
  // a row a known product (CANARY) is searched. If the canary is not found either, the
  // held misses are discarded and we wait for a sign-in.
  const CANARY = '6409460002724'; // Forssan Perunasalaatti 400g, shop code 100727
  let held = [];
  const flush = () => { for (const m of held) { append(m); searched.add(m.gtin); } held = []; };
  async function canaryOk() { const r = await searchGtin(CANARY); return !!(r && r.codes.length); }
  async function waitForWorkingSession() {
    log(`>>> Searches return nothing (session expired?). Discarding ${held.length} unconfirmed misses. Please sign in in the browser window. Waiting...`);
    held = [];
    waitingForSignIn = true;
    for (;;) {
      await page.goto(BASE + '/fi/', { waitUntil: 'domcontentloaded' }).catch(() => {});
      await page.waitForTimeout(4000);
      if (!(await isLoggedOut()) && (await canaryOk())) break;
      await page.waitForTimeout(15000);
    }
    waitingForSignIn = false; lastProgress = Date.now();
    log('>>> Search works again, continuing.');
  }

  for (const left of todo) {
    for (const gtin of left) {
      if (searched.has(gtin)) continue;
      await ensureLoggedIn();
      let r = await searchGtin(gtin);
      if (!r && (await isLoggedOut())) { await ensureLoggedIn(); r = await searchGtin(gtin); }
      if (!r) { log(`search timeout ${gtin}`); continue; }
      const rec = { type: 'search', gtin, codes: r.codes, ts: Date.now() };
      if (!r.codes.length) {
        held.push(rec);
        if (held.length >= 8) { if (await canaryOk()) flush(); else await waitForWorkingSession(); }
        await page.waitForTimeout(PAUSE_MS);
        continue;
      }
      flush();
      append(rec);
      searched.add(gtin);
      for (const code of r.codes.slice(0, 3)) if (!done.has(code)) await doCode(code);
      await page.waitForTimeout(PAUSE_MS);
      hitGtins.add(gtin);
      break;
    }
  }
  flush();
} else if (MODE === 'name') {
  // For dataset products still without an image: search the shop by Finnish name and
  // crawl results whose name matches exactly (normalized). --limit N samples N products
  // spread over the list (test run). The map build matches them by EAN or exact name.
  const products = JSON.parse(fs.readFileSync(PRODUCTS, 'utf8'));
  const mapPath = args.map || path.join(path.dirname(new URL(import.meta.url).pathname), '..', 'data', 'product_images.json.gz');
  const mapBytes = fs.readFileSync(mapPath);
  const mapped = new Set(Object.keys(JSON.parse((mapPath.endsWith('.gz') ? zlib.gunzipSync(mapBytes) : mapBytes).toString('utf8'))));
  const nameSearched = new Set();
  if (fs.existsSync(OUT)) for (const l of fs.readFileSync(OUT, 'utf8').split('\n')) { try { const r = JSON.parse(l); if (r.type === 'namesearch') nameSearched.add(r.id); } catch {} }
  let todo = products
    .filter((p) => !mapped.has(p.id) && !nameSearched.has(p.id))
    .map((p) => ({ id: p.id, name: (p.synkkaData?.names || []).find((x) => x.language === 'fi')?.value }))
    .filter((p) => p.name);
  const limit = Number(args.limit || 0);
  if (limit) { const step = Math.max(1, Math.floor(todo.length / limit)); todo = todo.filter((_, i) => i % step === 0).slice(0, limit); }
  log(`name mode: ${todo.length} products to search by name`);
  let exact = 0;
  for (const p of todo) {
    await ensureLoggedIn();
    const r = await searchQuery(p.name);
    if (!r) { log(`name search timeout: ${p.name}`); continue; }
    const want = normName(p.name);
    const match = r.codes.filter((c, i) => normName(r.names[i]) === want);
    append({ type: 'namesearch', id: p.id, q: p.name, n: r.n, results: r.codes.slice(0, 5).map((c, i) => ({ code: c, name: r.names[i] })), exact: match, ts: Date.now() });
    if (match.length) exact++;
    log(`${p.id} "${p.name}" -> ${r.n} results, exact ${match.length ? match.join(',') : '-'}${r.n && !match.length ? ' | top: ' + (r.names[0] || '') : ''}`);
    for (const code of match.slice(0, 2)) if (!done.has(code)) await doCode(code);
    await page.waitForTimeout(PAUSE_MS);
  }
  log(`name mode: ${exact}/${todo.length} with an exact name match`);
}
log(`finished: ${n} products this run, total crawled ${done.size}`);
await ctx.close();
