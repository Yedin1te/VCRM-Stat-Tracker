# Tests: Jede Seite lässt sich in Hochformat, Querformat und gedrehter Ansicht (⟳) mit dem Finger bis ganz nach unten scrollen,
# der letzte Inhalt liegt nicht unter der Leiste und die Seite scrollt nicht seitwärts.  Start: python3 tests/scroll.test.py
import os, re, sys, json
from playwright.sync_api import sync_playwright
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
APP = os.path.abspath(os.environ.get('APP', os.path.join(ROOT, 'index.html')))
PH = re.search(r"PH='([0-9a-f]{64})'", open(APP, encoding='utf-8').read()).group(1)
RES = []

def state():
    roles = ['ZP', 'AA', 'AA', 'MB', 'MB', 'DI', 'LI', 'AA', 'MB', 'DI', 'ZP']
    pl = [{'id': f'p{i}', 'name': f'Spieler{i}', 'nr': str(i + 1), 'role': roles[i]} for i in range(11)]
    sets = []
    for si in (1, 2):
        ev, t = [], 0
        for k in range(60):
            p = pl[k % 7]; t += 1
            for c, r in ([('rec', ['perf', 'ok', 'bad', 'err'][k % 4]), ('att', ['pt', 'eff', 'rec', 'err'][k % 4])] if k % 2 else [('srv', ['ace', 'eff', 'none', 'err'][k % 4])]):
                ev.append({'id': f's{si}e{k}{c}', 'p': p['id'], 'c': c, 'r': r, 'rot': 1 + k % 6, 't': t, 'pos': [q['id'] for q in pl[:6]]})
        sets.append({'id': f's{si}', 'gid': 'g1', 'opp': 'VC Beispiel', 'date': '2026-11-07', 'serve': 'Aufschlag' if si == 1 else 'Annahme', 'rot': 1,
                     'act': [q['id'] for q in pl[:7]], 'pos': [q['id'] for q in pl[:6]], 'rl': {}, 'ev': ev})
    return {'players': pl, 'games': [{'id': 'g1', 'opp': 'VC Beispiel', 'date': '2026-11-07'}], 'sets': sets, 'cur': 's2', 'pend': []}

PAGE = "(()=>{const d=document.documentElement,b=document.body,rot=d.classList.contains('rot'),s=rot?b:document.scrollingElement;return{rot,top:s.scrollTop,h:s.scrollHeight,c:s.clientHeight,w:s.scrollWidth,cw:s.clientWidth,ox:getComputedStyle(s).overflowX}})()"
MODAL = "(()=>{const m=document.querySelector('.md');return m?{top:m.scrollTop,h:m.scrollHeight,c:m.clientHeight,w:m.scrollWidth,cw:m.clientWidth,ox:getComputedStyle(m).overflowX}:null})()"
LAST = """(()=>{const d=document.documentElement,rot=d.classList.contains('rot'),m=document.querySelector('main'),nav=document.querySelector('nav').getBoundingClientRect();
  const last=[...m.children].filter(e=>e.offsetHeight>0).pop();if(!last)return{ok:true};const r=last.getBoundingClientRect();
  if(rot)return{ok:r.left>=-2,why:'letzter Inhalt liegt außerhalb (links '+Math.round(r.left)+')'};
  const land=d.classList.contains('land');if(land)return{ok:r.bottom<=innerHeight+2,why:'letzter Inhalt ragt unten heraus ('+Math.round(r.bottom)+' > '+innerHeight+')'};
  return{ok:r.bottom<=nav.top+2,why:'letzter Inhalt liegt unter der Leiste ('+Math.round(r.bottom)+' > '+Math.round(nav.top)+')'}})()"""

def swipe(pg, cdp, x, y, dx, dy):
    cdp.send('Input.dispatchTouchEvent', {'type': 'touchStart', 'touchPoints': [{'x': x, 'y': y}]})
    for i in range(1, 11):
        cdp.send('Input.dispatchTouchEvent', {'type': 'touchMove', 'touchPoints': [{'x': x + dx * i / 10, 'y': y + dy * i / 10}]}); pg.wait_for_timeout(16)
    cdp.send('Input.dispatchTouchEvent', {'type': 'touchEnd', 'touchPoints': []}); pg.wait_for_timeout(450)

def sideways(m): return m['w'] > m['cw'] + 1 and m['ox'] not in ('hidden', 'clip')   # scrollbar seitwärts nur, wenn das nicht gesperrt ist

def to_bottom(pg, cdp, metrics, rot, cx, cy):
    """Wischt bis zum Ende. Gibt (hatte_etwas_zu_scrollen, am_ende, seitlich_ueberlaufend) zurück."""
    m0 = pg.evaluate(metrics); tall = m0['h'] > m0['c'] + 1
    for _ in range(25):
        m = pg.evaluate(metrics)
        if m['top'] + m['c'] >= m['h'] - 1: break
        if rot: swipe(pg, cdp, cx - 130, cy, 260, 0)      # gedrehte Ansicht: „nach unten“ ist ein Wisch nach rechts
        else: swipe(pg, cdp, cx, cy + 130, 0, -260)
        if _ == 0 and tall and pg.evaluate(metrics)['top'] <= m0['top']: return tall, False, sideways(m0)
    m = pg.evaluate(metrics)
    return tall, m['top'] + m['c'] >= m['h'] - 1, sideways(m)

def case(name, w, h, rot, view):
    err = ''
    try:
        with sync_playwright() as p:
            br = p.chromium.launch(); ctx = br.new_context(viewport={'width': w, 'height': h}, is_mobile=True, has_touch=True); pg = ctx.new_page(); errs = []
            pg.on('pageerror', lambda e: errs.append(str(e)))
            pg.add_init_script("localStorage.setItem('vbpin','%s');localStorage.setItem('vbtracker1',%s);%s" % (PH, json.dumps(json.dumps(state())), "localStorage.setItem('vbrot','1');" if rot else ''))
            pg.goto('file://' + APP); pg.wait_for_timeout(350)
            tab = {'Spieler': 'pl', 'Spiel': 'game', 'Auswertung (Spiel)': 'eval', 'Auswertung (Alle)': 'eval'}.get(view)
            modal = view in ('Einstellungen', 'Anleitung')
            if modal: pg.locator('nav [data-act=%s]' % ('gear' if view == 'Einstellungen' else 'help')).click()
            else:
                pg.locator(f'nav [data-act=tab][data-v={tab}]').click()
                if tab == 'eval': pg.locator('[data-sel=fset]').select_option('g:g1' if 'Spiel' in view else 'all')
            pg.wait_for_timeout(350)
            cdp = ctx.new_cdp_session(pg); land = pg.evaluate("document.documentElement.classList.contains('land')")
            if modal:
                r = pg.evaluate("(()=>{const r=document.querySelector('.md').getBoundingClientRect();return[r.x+r.width/2,r.y+r.height/2]})()")
                tall, atend, side = to_bottom(pg, cdp, MODAL, rot, r[0], r[1])
            else:
                cx, cy = (w / 2, 64 + (h - 64) / 2) if rot else ((64 + (w - 64) / 2, h / 2) if land else (w / 2, h / 2 - 30))
                tall, atend, side = to_bottom(pg, cdp, PAGE, rot, cx, cy)
                last = pg.evaluate(LAST)
                if not last['ok']: err = last['why']
            if not atend: err = err or 'lässt sich nicht bis ans Ende scrollen'
            if side and not modal: err = err or 'Seite läuft seitwärts über'
            if errs: err = err or 'JS-Fehler: ' + errs[0]
            br.close()
    except Exception as e: err = f'{type(e).__name__}: {str(e)[:160]}'
    RES.append((f'{name:22s} · {view}', not err, err))

SETUPS = [('Hochformat', 390, 844, False), ('Querformat', 844, 390, False), ('Gedreht ⟳', 390, 844, True),
          ('Kleines Hochformat', 360, 640, False), ('Kleines Querformat', 667, 375, False), ('Kleines Gedreht ⟳', 360, 640, True)]
VIEWS = ['Spieler', 'Spiel', 'Auswertung (Spiel)', 'Auswertung (Alle)', 'Einstellungen', 'Anleitung']
if __name__ == '__main__':
    for n, w, h, rot in SETUPS:
        for v in VIEWS: case(n, w, h, rot, v)
    for n, ok, m in RES: print(('PASS ' if ok else 'FAIL ') + n + ('' if ok else '  -> ' + m))
    fails = [r for r in RES if not r[1]]; print(f'\n{len(RES) - len(fails)}/{len(RES)} bestanden'); sys.exit(1 if fails else 0)
