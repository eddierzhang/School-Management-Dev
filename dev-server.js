#!/usr/bin/env node
/* Local dev server for the registrar console.
 *
 * The published page reaches its records through `window.claude` — which only
 * exists inside the Claude artifact viewer. On localhost there is no such
 * object, so the page would render its "not connected" state and show nothing.
 *
 * This server composes a local page: the artifact head/body skeleton the viewer
 * normally supplies, a stand-in `window.claude.use("db")` backed by the browser's
 * localStorage, and console.html itself, unmodified. console.html stays the one
 * source of truth — nothing here is published.
 *
 *   node dev-server.js          → http://localhost:5173
 *   node dev-server.js 8080     → another port
 */
const http = require('http');
const fs = require('fs');
const path = require('path');

const ROOT = __dirname;
const PORT = parseInt(process.argv[2], 10) || 5173;
const SEED_DIR = path.join(ROOT, 'seed');

function loadSeed() {
  if (!fs.existsSync(SEED_DIR)) return null;
  const store = {};
  for (const f of fs.readdirSync(SEED_DIR)) {
    if (!f.endsWith('.json')) continue;
    const [collection, docId] = f.replace(/\.json$/, '').split('__');
    if (!collection || !docId) continue;
    store[collection + '/' + docId] = JSON.parse(fs.readFileSync(path.join(SEED_DIR, f), 'utf8'));
  }
  return Object.keys(store).length ? store : null;
}

/* The stand-in store. Same call shape as the real db capability, for the subset
   the console uses: collection/doc refs, get/set/update/delete, onSnapshot, and
   acquire. Leases always grant here — one browser, no second writer to race. */
const SHIM = `
<script>
(function () {
  var KEY = 'registrar-dev-store';
  var SEED = window.__SEED__ || {};
  var store;
  try { store = JSON.parse(localStorage.getItem(KEY)) || null; } catch (e) { store = null; }
  if (!store || !Object.keys(store).length) { store = JSON.parse(JSON.stringify(SEED)); persist(); }

  var listeners = [];
  function persist() { try { localStorage.setItem(KEY, JSON.stringify(store)); } catch (e) {} }
  function notify() { persist(); listeners.slice().forEach(function (l) { try { l(); } catch (e) {} }); }
  function clone(v) { return v == null ? v : JSON.parse(JSON.stringify(v)); }
  function snapOf(p) {
    var body = store[p];
    return { id: p.split('/').pop(), exists: !!body, data: function () { return clone(body); },
             metadata: { fromCache: false, hasPendingWrites: false } };
  }
  function childrenOf(cp) {
    var pre = cp + '/';
    return Object.keys(store).filter(function (k) {
      return k.indexOf(pre) === 0 && k.slice(pre.length).indexOf('/') === -1;
    }).sort();
  }
  function subscribe(fn) {
    listeners.push(fn);
    setTimeout(fn, 0);
    return function () { listeners = listeners.filter(function (l) { return l !== fn; }); };
  }

  function docRef(p) {
    return {
      id: p.split('/').pop(), path: p,
      get: function () { return Promise.resolve(snapOf(p)); },
      set: function (data) { store[p] = clone(data); notify(); return Promise.resolve(); },
      update: function (patch) {
        if (!store[p]) return Promise.reject({ code: 'invalid_argument', message: 'No document at ' + p });
        Object.keys(patch).forEach(function (k) { store[p][k] = clone(patch[k]); });
        notify(); return Promise.resolve();
      },
      delete: function () { delete store[p]; notify(); return Promise.resolve(); },
      acquire: function () { return Promise.resolve({ acquired: true, holder: 'local', version: 1 }); },
      onSnapshot: function (next) { return subscribe(function () { next(snapOf(p)); }); },
      collection: function (sub) { return collRef(p + '/' + sub); }
    };
  }
  function collRef(cp) {
    return {
      path: cp,
      doc: function (id) { return docRef(cp + '/' + (id || 'auto-' + Date.now())); },
      add: function (data) { var r = this.doc(); return r.set(data).then(function () { return r; }); },
      get: function () {
        var ds = childrenOf(cp).map(snapOf);
        return Promise.resolve({ docs: ds, size: ds.length, empty: !ds.length,
                                 docChanges: function () { return []; },
                                 metadata: { fromCache: false, hasPendingWrites: false } });
      },
      where: function () { return this; }, orderBy: function () { return this; }, limit: function () { return this; },
      onSnapshot: function (next) {
        return subscribe(function () {
          var ds = childrenOf(cp).map(snapOf);
          next({ docs: ds, size: ds.length, empty: !ds.length,
                 docChanges: function () { return []; },
                 metadata: { fromCache: false, hasPendingWrites: false } });
        });
      }
    };
  }

  window.claude = { use: function (name) {
    return Promise.resolve(name === 'db' ? { doc: docRef, collection: collRef } : null);
  } };

  window.resetRegistrarData = function () { localStorage.removeItem(KEY); location.reload(); };
  console.info('[dev] Local stand-in store active. %d documents. ' +
    'Edits persist in localStorage; run resetRegistrarData() to restore the seed.',
    Object.keys(store).length);
})();
</script>`;

function page() {
  const body = fs.readFileSync(path.join(ROOT, 'console.html'), 'utf8');
  const seed = loadSeed();
  const banner = seed ? '' : `
<div style="background:#FCF2DC;color:#231a05;padding:10px 16px;font:600 13px system-ui">
  No <code>seed/</code> directory found — the console will open empty.
  Run <code>node gen_seed.js</code>, then reload.
</div>`;
  /* The artifact viewer supplies this skeleton at publish time; reproduce it so
     localhost matches what the published page actually renders inside. */
  return `<!doctype html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
  :root { color-scheme: light }
  body { margin: 0; font: 14px system-ui, -apple-system, "Segoe UI", sans-serif;
         background: #f5f5f3 }
  img { max-width: 100% }
  [hidden] { display: none !important }
</style>
<script>window.__SEED__ = ${seed ? JSON.stringify(seed) : '{}'};</script>
${SHIM}
</head>
<body>
${banner}
${body}
</body>
</html>`;
}

http.createServer((req, res) => {
  const url = (req.url || '/').split('?')[0];
  try {
    if (url === '/' || url === '/index.html') {
      res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8', 'Cache-Control': 'no-store' });
      return res.end(page());
    }
    const file = path.join(ROOT, path.normalize(url).replace(/^(\.\.[/\\])+/, ''));
    if (file.startsWith(ROOT) && fs.existsSync(file) && fs.statSync(file).isFile()) {
      const type = { '.js': 'text/javascript', '.css': 'text/css', '.json': 'application/json' }[path.extname(file)]
        || 'text/plain';
      res.writeHead(200, { 'Content-Type': type + '; charset=utf-8' });
      return res.end(fs.readFileSync(file));
    }
    res.writeHead(404, { 'Content-Type': 'text/plain' });
    res.end('Not found');
  } catch (e) {
    res.writeHead(500, { 'Content-Type': 'text/plain' });
    res.end('Server error: ' + e.message);
  }
}).listen(PORT, () => {
  const seeded = loadSeed();
  console.log('Registrar console → http://localhost:' + PORT);
  console.log(seeded ? '  ' + Object.keys(seeded).length + ' seed documents loaded'
                     : '  no seed/ directory — run `node gen_seed.js` first');
});
