// Product image crawl, first pass (#108; see scripts/build_image_map.py for the whole
// rebuild). Needs a signed-in portal session: it runs inside your own logged-in
// toimitustukku.valioaimo.fi tab (paste into console / devtools) and never reads or
// stores credentials, cookies or tokens. What it collects stays in the browser's
// IndexedDB and the exported JSON in ~/Downloads; the raw crawl is never committed.
//
// Worker K of N: walks shop product codes collected by the listing crawl
// (IndexedDB junction_imgmap.items) via in-app route changes, and stores
// {code, ean, name, imgs[]} into IndexedDB junction_imgdetail.details.
// imgs are the full-size 300Wx300H-1200Wx1200H media URLs shown on the product page.
// Set window.__W = {N, K} before running. Stop with __W.stop = true.
(() => {
  const W = (window.__W = Object.assign({ N: 1, K: 0 }, window.__W || {}, { done: 0, errs: 0, running: true, stop: false }));
  const openDb = (name, store) => new Promise((res, rej) => { const r = indexedDB.open(name, 1); r.onupgradeneeded = () => r.result.createObjectStore(store, { keyPath: 'code' }); r.onsuccess = () => res(r.result); r.onerror = rej; });
  const keys = (db, st) => new Promise((res) => { const r = db.transaction(st).objectStore(st).getAllKeys(); r.onsuccess = () => res(r.result); });
  const put = (db, st, v) => new Promise((res, rej) => { const tx = db.transaction(st, 'readwrite'); tx.objectStore(st).put(v); tx.oncomplete = res; tx.onerror = rej; });
  // Mutation-driven waits: not subject to background-tab timer throttling.
  const waitFor = (cond, ms) => new Promise((res) => {
    const t0 = performance.now(); let v = cond(t0); if (v) return res(v);
    const mo = new MutationObserver(() => { const v = cond(t0); if (v) { mo.disconnect(); clearTimeout(t); res(v); } });
    mo.observe(document.body, { subtree: true, childList: true, attributes: true, characterData: true });
    const t = setTimeout(() => { mo.disconnect(); res(cond(t0) || null); }, ms);
  });
  const galleryImgs = () => [...new Set([...document.querySelectorAll('aimo-product-images img')].map((i) => i.getAttribute('src')).filter((s) => s && s.includes('/medias/')))];
  W.run = async () => {
    const L = await openDb('junction_imgmap', 'items');
    const D = await openDb('junction_imgdetail', 'details');
    let prev = galleryImgs()[0] || null;
    while (!W.stop) {
      // Done = has a result, or already failed twice.
      const recs = await new Promise((res) => { const r = D.transaction('details').objectStore('details').getAll(); r.onsuccess = () => res(r.result); });
      const tries = Object.fromEntries(recs.map((r) => [r.code, r.err ? r.tries || 1 : 99]));
      const done = new Set(recs.filter((r) => tries[r.code] >= 2).map((r) => r.code));
      const codes = (await keys(L, 'items')).sort().filter((c, i) => i % W.N === W.K && !done.has(c));
      if (!codes.length) { W.idle = (W.idle || 0) + 1; if (W.idle > 3) break; await new Promise((r) => setTimeout(r, 20000)); continue; }
      W.idle = 0;
      for (const code of codes) {
        if (W.stop) break;
        history.pushState({}, '', '/fi/p/' + code);
        dispatchEvent(new PopStateEvent('popstate', { state: {} }));
        // e.g. "637652 EAN 6418047171319" or "1086 2,0 kg / ltkEAN 6416250007890"
        const re = new RegExp('\\b' + code + '\\b[^\\n]{0,40}?EAN\\s*(\\d{8,14})');
        // Some product pages show no EAN: accept them 2.5 s after the code appears.
        let seenAt = null;
        const m = await waitFor(() => {
          const t = document.querySelector('main')?.innerText || '';
          const hit = t.match(re); if (hit) return hit;
          if (/ei löytynyt/i.test(document.title)) return 'nf';
          if (t.includes(code)) { seenAt = seenAt || performance.now(); if (performance.now() - seenAt > 2500) return 'noean'; }
          return null;
        }, 8000);
        let rec;
        if (m && m !== 'nf') {
          // Wait until the gallery shows a new image, or 1.5 s passes (same image or no image).
          await waitFor((t0) => { const g = galleryImgs(); return (g.length && g[0] !== prev) || performance.now() - t0 > 1500; }, 2500);
          const imgs = galleryImgs();
          rec = { code, ean: m === 'noean' ? null : m[1], name: document.querySelector('h1')?.innerText.trim() || null, imgs, sameAsPrev: imgs[0] === prev };
          prev = imgs[0] || prev;
        } else { rec = { code, err: m === 'nf' ? 'notfound' : 'timeout', tries: (tries[code] || 0) + 1 }; W.errs++; }
        await put(D, 'details', rec); W.done++; W.last = code;
      }
    }
    W.running = false;
  };
  W.run().catch((e) => { W.err = String(e); W.running = false; });
})();
