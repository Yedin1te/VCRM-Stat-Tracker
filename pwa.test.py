# Tests für Installierbarkeit (PWA), Offline-Start und Logo-Erkennung. Start: python3 tests/pwa.test.py
import os, re, sys, json, shutil, tempfile, threading, functools, http.server, socketserver
from PIL import Image
from playwright.sync_api import sync_playwright
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
FILES = ['index.html', 'manifest.json', 'sw.js', 'icon-192.png', 'icon-512.png']
PH = re.search(r"PH='([0-9a-f]{64})'", open(os.path.join(ROOT, 'index.html'), encoding='utf-8').read()).group(1)
RES = []

class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a): pass
def site(logo=None):
    d = tempfile.mkdtemp()
    for f in FILES: shutil.copy(os.path.join(ROOT, f), d)
    if logo: Image.new('RGB', (200, 120), (200, 30, 30)).save(os.path.join(d, logo))
    srv = socketserver.TCPServer(('127.0.0.1', 0), functools.partial(Quiet, directory=d)); srv.allow_reuse_address = True
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return d, srv, f'http://127.0.0.1:{srv.server_address[1]}/'

def run(name, fn, logo=None):
    d, srv, url = site(logo)
    try:
        with sync_playwright() as p:
            br = p.chromium.launch(); ctx = br.new_context(viewport={'width': 1280, 'height': 720}); pg = ctx.new_page(); pg.logs = []; pg.errs = []
            pg.on('console', lambda m: pg.logs.append(m.text)); pg.on('pageerror', lambda e: pg.errs.append(str(e)))
            pg.add_init_script("localStorage.setItem('vbpin','%s')" % PH)
            try: fn(pg, ctx, url); ok, msg = True, ''
            except AssertionError as e: ok, msg = False, str(e) or 'Assertion'
            except Exception as e: ok, msg = False, f'{type(e).__name__}: {str(e)[:200]}'
            br.close()
    finally: srv.shutdown(); shutil.rmtree(d, ignore_errors=True)
    RES.append((name, ok, msg))

def settings_text(pg):
    pg.locator('nav [data-act=gear]').click(); pg.wait_for_timeout(300); return pg.locator('.md').inner_text()

def t_manifest(pg, ctx, url):
    pg.goto(url + 'index.html'); pg.wait_for_timeout(300)
    assert pg.locator('link[rel=manifest]').get_attribute('href') == 'manifest.json'
    assert pg.locator('meta[name=theme-color]').count() == 1 and pg.locator('link[rel=apple-touch-icon]').count() == 1
    m = json.loads(ctx.request.get(url + 'manifest.json').text())
    assert m['display'] == 'standalone' and m['start_url'] == './' and m['name'] and m['short_name']
    sizes = {i['sizes'] for i in m['icons']}; assert {'192x192', '512x512'} <= sizes, sizes
    for i in m['icons']:
        w, h = Image.open(os.path.join(ROOT, i['src'])).size; assert f'{w}x{h}' == i['sizes'], i
    assert not [l for l in pg.logs if 'Content Security Policy' in l], pg.logs
run('PWA: Manifest, Symbole und Kopfzeilen sind gültig, keine CSP-Verstöße', t_manifest)

def t_offline(pg, ctx, url):
    pg.goto(url + 'index.html'); pg.wait_for_function("navigator.serviceWorker.ready.then(()=>true)", timeout=10000)
    pg.reload(); pg.wait_for_timeout(500)
    assert pg.evaluate("!!navigator.serviceWorker.controller"), 'Service Worker steuert die Seite nicht'
    assert 'vbtracker-v1' in pg.evaluate("caches.keys()")
    ctx.set_offline(True); pg.reload(); pg.wait_for_timeout(600)
    assert pg.locator('nav button').count() >= 5, 'App startet offline nicht'
    assert not [l for l in pg.logs if 'Content Security Policy' in l] and not pg.errs, (pg.logs, pg.errs)
run('PWA: Service Worker aktiv, App startet ohne Netz', t_offline)

def t_logo_found(pg, ctx, url):
    pg.goto(url + 'index.html'); pg.wait_for_timeout(800)
    txt = settings_text(pg); assert 'Logo gefunden: Logo.png (200 x 120 Pixel)' in txt, txt
    bg = pg.evaluate("getComputedStyle(document.body,'::before').backgroundImage"); assert 'Logo.png' in bg, bg
run('Logo: Logo.png (Großschreibung) wird gefunden und als Hintergrund gesetzt', t_logo_found, logo='Logo.png')
run('Logo: logo.jpg wird ebenfalls gefunden', lambda pg, ctx, url: (pg.goto(url + 'index.html'), pg.wait_for_timeout(800), None)[2] or (lambda t: (_ for _ in ()).throw(AssertionError(t)) if 'Logo gefunden: logo.jpg' not in t else None)(settings_text(pg)), logo='logo.jpg')

def t_logo_missing(pg, ctx, url):
    pg.goto(url + 'index.html'); pg.wait_for_timeout(1200)
    txt = settings_text(pg); assert 'Kein Logo gefunden' in txt and url + 'logo.png' in txt, txt
    assert 'none' in pg.evaluate("getComputedStyle(document.body,'::before').backgroundImage") and not pg.errs
run('Logo: fehlt die Datei, nennt die App die genaue Adresse', t_logo_missing)

if __name__ == '__main__':
    for n, ok, m in RES: print(('PASS ' if ok else 'FAIL ') + n + ('' if ok else '  -> ' + m))
    fails = [r for r in RES if not r[1]]; print(f'\n{len(RES) - len(fails)}/{len(RES)} bestanden'); sys.exit(1 if fails else 0)
