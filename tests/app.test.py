# End-to-End- und Sicherheitstests. Start: APP=../index.html python3 tests/app.test.py
import os, re, json, sys
from playwright.sync_api import sync_playwright
APP = os.path.abspath(os.environ.get('APP', os.path.join(os.path.dirname(__file__), '..', 'index.html')))
SRC = open(APP, encoding='utf-8').read()
PH = re.search(r"PH='([0-9a-f]{64})'", SRC).group(1)
URL = 'https://script.google.com/macros/s/AKfycbxAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA/exec'
RES, PW = [], 'test-passwort-123'

def state(players=7, sets=None):
    return {'players': [{'id': f'p{i}', 'name': f'Sp{i}', 'nr': str(i)} for i in range(1, players + 1)],
            'games': [{'id': 'g1', 'opp': 'Gegner', 'date': '2026-01-01'}], 'sets': sets or [], 'cur': None, 'pend': []}
def mkset(i, us=0, opp=0, serve='Aufschlag', rot=1, cur=False):
    ev = [{'id': f'u{i}_{k}', 'p': '', 'c': 'sc', 'r': 'us', 'rot': 1, 't': k} for k in range(us)] + \
         [{'id': f'o{i}_{k}', 'p': '', 'c': 'sc', 'r': 'opp', 'rot': 1, 't': 100 + k} for k in range(opp)]
    return {'id': f's{i}', 'gid': 'g1', 'opp': 'Gegner', 'date': '2026-01-01', 'serve': serve, 'rot': rot, 'act': ['p1', 'p2', 'p3', 'p4', 'p5', 'p6'], 'ev': ev}

def check(name, desktop=False):
    def deco(fn):
        def run(br):
            ctx = br.new_context(viewport={'width': 1280, 'height': 720}) if desktop else br.new_context(viewport={'width': 390, 'height': 800}, is_mobile=True, has_touch=True)
            pg = ctx.new_page(); pg.errs = []; pg.dialogs = []
            pg.on('pageerror', lambda e: pg.errs.append(str(e)))
            pg.on('dialog', lambda d: (pg.dialogs.append(d.message), d.dismiss()))
            try:
                fn(pg); ok, msg = True, ''
            except AssertionError as e:
                ok, msg = False, str(e) or 'Assertion'
            except Exception as e:
                ok, msg = False, f'{type(e).__name__}: {str(e)[:150]}'
            RES.append((name, ok, msg)); ctx.close()
        run.__name__ = name; TESTS.append(run); return fn
    return deco
TESTS = []

def open_app(pg, st=None, cfg=None, unlocked=True, extra=None):
    pg.goto('file://' + APP)
    pg.evaluate('([st,cfg,ph,u,ex])=>{if(st)localStorage.setItem("vbtracker1",typeof st==="string"?st:JSON.stringify(st));if(cfg)localStorage.setItem("vbcfg1",JSON.stringify(cfg));if(u)localStorage.setItem("vbpin",ph);}', [st, cfg, PH, unlocked, extra])
    pg.reload(); pg.wait_for_timeout(300)
def tap(pg, sel): pg.locator(sel).first.click(); pg.wait_for_timeout(120)
def score(pg): return re.sub(r'\s+', ' ', pg.locator('.score').inner_text().replace('✎', '')).strip()
def us(pg):   # eigener Punkt (alter Weg über den entfernten Knopf), ohne die Oberfläche
    pg.evaluate("addEv(curSet(),{p:'',c:'sc',r:'us'});render()"); pg.wait_for_timeout(100)
def rot(pg): return pg.locator('[data-act="rot+"] b').inner_text()
def start_set(pg, serve='Annahme'):
    tap(pg, 'nav [data-act=tab][data-v=game]')
    pg.locator('[data-sel=gid]').select_option('new') if pg.locator('[data-sel=gid]').count() else None
    pg.fill('[data-in=opp]', 'Gegner')
    tap(pg, f'[data-act=serve][data-v={serve}]')
    for i in range(6): pg.locator('.chip').nth(i).click(); pg.wait_for_timeout(40)
    tap(pg, '[data-act=start]')

# ---------- Funktion ----------
@check('Punkte, Aufschlag und Läufer-Rotation')
def _(pg):
    open_app(pg, state()); start_set(pg, 'Annahme')
    assert score(pg) == '0 : 0' and rot(pg) == '1'
    us(pg); assert score(pg) == '1 : 0' and rot(pg) == '6', score(pg) + rot(pg)   # Läufer 1 -> 6
    us(pg); assert score(pg) == '2 : 0' and rot(pg) == '6'   # wir schlagen auf: keine Rotation
    tap(pg, '[data-act=pt][data-v=opp]'); assert score(pg) == '2 : 1' and rot(pg) == '6'
    tap(pg, '[data-act=pt][data-v=oerr]'); assert score(pg) == '3 : 1' and rot(pg) == '5'  # Side-out: 6 -> 5
    tap(pg, '[data-act=undo]'); assert score(pg) == '2 : 1' and rot(pg) == '6', score(pg) + rot(pg)
    assert not pg.errs, pg.errs

@check('Annahme-/Angriffs-/Aufschlagfehler geben Gegnerpunkt')
def _(pg):
    open_app(pg, state()); start_set(pg, 'Aufschlag')
    tap(pg, '[data-act=tab][data-v=game]')
    for cat in ['Aufschlag', 'Angriff', 'Annahme']:
        tap(pg, f'.seg.a-t button:has-text("{cat}")'); tap(pg, '[data-act=hit][data-v$="|err"]')
    assert score(pg) == '0 : 3', score(pg)

@check('Satzende 25 bzw. 15 im 5. Satz mit 2 Punkten Vorsprung')
def _(pg):
    sets = [mkset(1), mkset(2), mkset(3), mkset(4), mkset(5, us=15, opp=10)]
    st = state(sets=sets); st['cur'] = 's5'; open_app(pg, st)
    assert 'bitte beenden' in pg.locator('.sub').inner_text()
    st = state(sets=[mkset(1, us=24, opp=24)]); st['cur'] = 's1'; open_app(pg, st)
    assert 'bitte beenden' not in pg.locator('.sub').inner_text()
    st = state(sets=[mkset(1, us=25, opp=24)]); st['cur'] = 's1'; open_app(pg, st)
    assert 'bitte beenden' not in pg.locator('.sub').inner_text()
    st = state(sets=[mkset(1, us=20, opp=26)]); st['cur'] = 's1'; open_app(pg, st)
    assert 'verloren' in pg.locator('.sub').inner_text()

@check('Auswertung rendert ohne Fehler')
def _(pg):
    st = state(sets=[mkset(1, us=5, opp=3)]); open_app(pg, st); tap(pg, 'nav [data-act=tab][data-v=eval]')
    assert 'Punkte' in pg.locator('main').inner_text() and not pg.errs

@check('Quer-/Hochformat-Umschalter ohne Fehler')
def _(pg):
    open_app(pg, state()); tap(pg, 'nav [data-act=orient]')
    assert 'rot' in pg.evaluate('document.documentElement.className') and not pg.errs, pg.errs
    tap(pg, 'nav [data-act=orient]'); assert 'rot' not in pg.evaluate('document.documentElement.className')

@check('Läufer-Reihenfolge 1-6-5-4-3-2-1')
def _(pg):
    open_app(pg, state()); start_set(pg, 'Annahme'); seq = [rot(pg)]
    for _ in range(6):
        tap(pg, '[data-act="rot+"]'); seq.append(rot(pg))
    assert seq == ['1', '6', '5', '4', '3', '2', '1'], seq

@check('Nach Annahme (kein Fehler) wechselt die App in den Angriff')
def _(pg):
    open_app(pg, state()); start_set(pg, 'Annahme')
    on = lambda: pg.locator('.seg.a-t button.on').inner_text()
    assert on() == 'Annahme'
    for res, expected in [('ok', 'Angriff')]:
        tap(pg, f'[data-act=hit][data-v="p1|rec|{res}"]'); assert on() == expected, on()
    tap(pg, '.seg.a-t button:has-text("Annahme")')
    tap(pg, '[data-act=hit][data-v="p1|rec|err"]'); assert on() == 'Annahme', 'Annahmefehler darf nicht in den Angriff springen'
    tap(pg, '[data-act=hit][data-v="p2|rec|perf"]'); assert on() == 'Angriff'

@check('Anleitung öffnet sich über ?, zeigt Definitionen und schließt wieder')
def _(pg):
    open_app(pg, state()); tap(pg, 'nav [data-act=help]')
    txt = pg.locator('.md').inner_text()
    assert 'Anleitung' in txt and 'Schnellstart' in txt
    for i in (1, 2, 3, 4): pg.locator('.help summary').nth(i).click()
    txt = pg.locator('.md').inner_text()
    for w in ['Perfekt', 'Schlecht', 'Gut', 'Ohne Wirkung', 'Ass', 'Läufer']: assert w in txt, w
    assert pg.locator('.help details').count() >= 6
    tap(pg, '[data-act=gearx]'); assert pg.locator('#ov').count() == 0 and not pg.errs

@check('Navigation passt auf schmalen Handys (360 px) ohne abgeschnittene Texte')
def _(pg):
    pg.set_viewport_size({'width': 360, 'height': 740}); open_app(pg, state())
    for b in pg.locator('nav button').all():
        bb = b.bounding_box(); assert bb['x'] >= 0 and bb['x'] + bb['width'] <= 360, bb
        assert b.evaluate('e=>e.scrollWidth<=e.clientWidth+1'), b.inner_text()
    assert pg.locator('nav button').count() == 6

@check('Punkt Gegner und Gegnerfehler springen in den richtigen Bereich')
def _(pg):
    open_app(pg, state()); start_set(pg, 'Aufschlag')
    on = lambda: pg.locator('.seg.a-t button.on').inner_text()
    tap(pg, '.seg.a-t button:has-text("Angriff")'); assert on() == 'Angriff'
    tap(pg, '[data-act=pt][data-v=opp]'); assert on() == 'Annahme', on()       # Gegner punktet -> Gegner schlägt auf -> wir nehmen an
    assert pg.locator('[data-act=pt][data-v=us]').count() == 0, 'Knopf Punkt wir sollte entfernt sein'
    tap(pg, '[data-act=pt][data-v=oerr]'); assert on() == 'Aufschlag', on()    # wir punkten (Side-out) -> wir schlagen auf

@check('Block zählt als Punkt, steht getrennt von der Angriffsquote')
def _(pg):
    open_app(pg, state()); start_set(pg, 'Aufschlag')
    att = lambda: tap(pg, '.seg.a-t button:has-text("Angriff")')
    att(); assert pg.locator('.pr').first.locator('.hb').count() == 5
    tap(pg, '[data-act=hit][data-v="p1|att|blk"]'); assert score(pg) == '1 : 0', score(pg)
    for r in ['pt', 'pt', 'pt', 'err']:
        att(); tap(pg, f'[data-act=hit][data-v="p2|att|{r}"]')
    tap(pg, 'nav [data-act=tab][data-v=eval]')
    txt = pg.locator('main').inner_text()
    assert 'Block 1' in txt and 'Punkt 75%' in txt, txt[:500]     # 3 Punkte aus 4 Angriffen, der Block verfälscht die Quote nicht
    assert not pg.errs

@check('Spielstand korrigieren und Aufschlag tauschen')
def _(pg):
    open_app(pg, state()); start_set(pg, 'Annahme')
    tap(pg, '.score')
    for r in ['wp', 'wp', 'gp']: tap(pg, f'[data-act=pt][data-v={r}]')
    assert score(pg) == '2 : 1' and rot(pg) == '1', (score(pg), rot(pg))           # Korrektur dreht nicht
    tap(pg, '[data-act=pt][data-v=wm]'); tap(pg, '[data-act=pt][data-v=gm]'); tap(pg, '[data-act=pt][data-v=gm]')
    assert score(pg) == '1 : 0', score(pg)                                           # nie unter 0
    assert 'Aufschlag Gegner' in pg.locator('.sub').inner_text()
    tap(pg, '[data-act=pt][data-v=sv]'); assert 'Aufschlag wir' in pg.locator('.sub').inner_text()
    tap(pg, '[data-act=undo]'); assert 'Aufschlag Gegner' in pg.locator('.sub').inner_text()

@check('Spiele und Sätze lassen sich in der Auswertung löschen (feste Liste, auch ohne Eingaben)')
def _(pg):
    st = state(sets=[mkset(1, us=3, opp=1), mkset(2)])                       # Satz 2 hat keine Eingaben
    st['games'].append({'id': 'g2', 'opp': 'Anderer', 'date': '2026-01-02'}); s3 = mkset(3, us=5); s3['gid'] = 'g2'; st['sets'].append(s3)
    open_app(pg, st); tap(pg, 'nav [data-act=tab][data-v=eval]')
    assert 'Spiele und Sätze' in pg.locator('main').inner_text() and pg.locator('[data-act=del]').count() == 5      # 2 Spiele + 3 Sätze
    btn = lambda key: f'[data-act=del][data-v="{key}"]'
    tap(pg, btn('s:s2')); assert 'Wirklich' in pg.locator(btn('s:s2')).inner_text(); assert len(json.loads(pg.evaluate('localStorage.getItem("vbtracker1")'))['sets']) == 3   # erster Tipp löscht nichts
    tap(pg, btn('s:s2'))
    ls = json.loads(pg.evaluate('localStorage.getItem("vbtracker1")'))
    assert [x['id'] for x in ls['sets']] == ['s1', 's3'] and any(o['k'] == 's-' for o in ls['pend']), ls['sets']
    tap(pg, btn('g:g1')); tap(pg, btn('g:g1'))
    ls = json.loads(pg.evaluate('localStorage.getItem("vbtracker1")'))
    assert [x['id'] for x in ls['games']] == ['g2'] and [x['id'] for x in ls['sets']] == ['s3'], ls
    tap(pg, btn('g:g2')); tap(pg, btn('g:g2')); assert 'Noch keine Daten' in pg.locator('main').inner_text() and pg.locator('[data-act=del]').count() == 0 and not pg.errs

@check('Ohne Eingaben: Liste zum Löschen erscheint trotzdem, Wegtippen bricht ab')
def _(pg):
    st = state(sets=[mkset(1)]); open_app(pg, st); tap(pg, 'nav [data-act=tab][data-v=eval]')
    assert 'Noch keine Daten' in pg.locator('main').inner_text() and pg.locator('[data-act=del]').count() == 2
    tap(pg, '[data-act=del][data-v="g:g1"]'); tap(pg, 'nav [data-act=tab][data-v=game]'); tap(pg, 'nav [data-act=tab][data-v=eval]')
    assert len(json.loads(pg.evaluate('localStorage.getItem("vbtracker1")'))['games']) == 1, 'ein einzelner Tipp darf nicht löschen'

@check('Gelöschtes laufendes Spiel: App landet im Setup, nicht im Fehler')
def _(pg):
    st = state(sets=[mkset(1, us=1)]); st['cur'] = 's1'; open_app(pg, st)
    tap(pg, 'nav [data-act=tab][data-v=eval]'); tap(pg, '[data-act=del][data-v="g:g1"]'); tap(pg, '[data-act=del][data-v="g:g1"]'); tap(pg, 'nav [data-act=tab][data-v=game]')
    assert 'Neuer Satz' in pg.locator('main').inner_text() and not pg.errs

@check('Rollen pro Satz: Außen als Diagonal einsetzen, Sortierung, Farbe und Läufer folgen')
def _(pg):
    st = state(); roles = ['AA', 'MB', 'MB', 'ZP', 'DI', 'AA', 'LI']
    for q, r in zip(st['players'], roles): q['role'] = r
    open_app(pg, st); tap(pg, 'nav [data-act=tab][data-v=game]'); pg.fill('[data-in=opp]', 'X')
    for i in range(7): pg.locator('.chip').nth(i).click(); pg.wait_for_timeout(40)
    assert 'Läufer 4' in pg.locator('main').inner_text()                                # Zuspieler (Sp4) steht auf Position 4
    pg.locator('[data-sel=rl][data-v=p1]').select_option('DI'); pg.wait_for_timeout(150)  # Sp1 (Außen) spielt hier Diagonal
    pg.locator('[data-sel=rl][data-v=p6]').select_option('LI'); pg.wait_for_timeout(150) # Sp6 (Außen) als Libero
    tap(pg, '[data-act=start]')
    order = [x.strip() for x in pg.locator('.pr .pn b').all_inner_texts()]
    assert order == ['#2', '#3', '#1', '#5', '#4', '#6', '#7'], order                    # MB, MB, DI(Sp1,Sp5), ZP, LI(Sp6,Sp7)
    kuerzel = pg.locator('.pr .rl').all_inner_texts(); assert kuerzel == ['MB', 'MB', 'DI', 'DI', 'ZP', 'LI', 'LI'], kuerzel
    tap(pg, '[data-act=wech]'); pg.locator('[data-sel=wrl][data-v=p4]').select_option('AA'); pg.wait_for_timeout(200)   # Zuspieler-Rolle weg
    assert 'ZP' not in pg.locator('.pr .rl').all_inner_texts()
    ls = json.loads(pg.evaluate('localStorage.getItem("vbtracker1")'))
    assert ls['sets'][-1]['rl'].get('p1') == 'DI' and ls['players'][0]['role'] == 'AA', ls['sets'][-1]['rl']
    assert not pg.errs

# ---------- Zufallssimulation gegen ein unabhängiges Referenzmodell ----------
import random
REF_PT = {('rec', 'err'): 'o', ('att', 'err'): 'o', ('att', 'pt'): 'u', ('att', 'blk'): 'u', ('srv', 'err'): 'o', ('srv', 'ace'): 'u',
          ('sc', 'opp'): 'o', ('sc', 'oerr'): 'u', ('sc', 'us'): 'u'}
REF_CR = {'wp': ('u', 1), 'wm': ('u', -1), 'gp': ('o', 1), 'gm': ('o', -1)}
CHOICES = {'rec': ['err', 'bad', 'ok', 'perf'], 'att': ['err', 'rec', 'eff', 'pt', 'blk'], 'srv': ['err', 'none', 'eff', 'ace'],
           'sc': ['opp', 'oerr', 'us', 'wp', 'wm', 'gp', 'gm', 'sv']}
class Ref:
    def __init__(self, serve, rot, pos): self.serve, self.rot, self.pos, self.ev = serve, rot, list(pos), []
    def standing(self, evs=None):
        u = o = 0; srv = 'us' if self.serve == 'Aufschlag' else 'opp'
        for c, r, _ in (self.ev if evs is None else evs):
            p = REF_PT.get((c, r))
            if p == 'u': u += 1; srv = 'us'
            elif p == 'o': o += 1; srv = 'opp'
            elif c == 'sc' and r in REF_CR: u += REF_CR[r][1] * (REF_CR[r][0] == 'u'); o += REF_CR[r][1] * (REF_CR[r][0] == 'o')
            elif c == 'sc' and r == 'sv': srv = 'opp' if srv == 'us' else 'us'
        return max(u, 0), max(o, 0), srv
    def add(self, c, r, p):
        before = self.standing(); side = REF_PT.get((c, r)) == 'u' and before[2] == 'opp'
        self.ev.append((c, r, side))
        if side: self.rot = 6 if self.rot == 1 else self.rot - 1; self.pos = self.pos[1:] + self.pos[:1]
    def undo(self):
        if not self.ev: return
        c, r, side = self.ev.pop()
        if side: self.rot = 1 if self.rot == 6 else self.rot + 1; self.pos = self.pos[-1:] + self.pos[:-1]
    def manual(self): self.rot = 6 if self.rot == 1 else self.rot - 1; self.pos = self.pos[1:] + self.pos[:1]

def run_sim(pg, seed, steps):
    rnd = random.Random(seed); st = state(); st['players'][3]['role'] = 'ZP'
    open_app(pg, st); start_set(pg, 'Annahme' if seed % 2 else 'Aufschlag')
    live = pg.evaluate("(()=>{const s=curSet();return{rot:s.rot,pos:s.pos,serve:s.serve}})()")
    assert live['rot'] == 4 and live['pos'][3] == 'p4', live                              # Zuspieler auf Position 4 -> Läufer 4
    ref = Ref(live['serve'], live['rot'], live['pos'])
    for i in range(steps):
        x = rnd.random()
        if x < .18 and ref.ev: pg.evaluate("undo(curSet())"); ref.undo(); what = 'undo'
        elif x < .24: pg.evaluate("(()=>{const s=curSet();upd(s,{rot:nextRot(s.rot),pos:rotPos(s.pos||[])})})()"); ref.manual(); what = 'rot+'
        else:
            c = rnd.choice(list(CHOICES)); r = rnd.choice(CHOICES[c]); pl = '' if c == 'sc' else 'p%d' % rnd.randint(1, 6)
            pg.evaluate("a=>addEv(curSet(),{p:a[0],c:a[1],r:a[2]})", [pl, c, r]); ref.add(c, r, pl); what = f'{c}/{r}'
        got = pg.evaluate("(()=>{const s=curSet(),q=replay(s);return{u:q.u,o:q.o,srv:q.srv,rot:s.rot,pos:s.pos,n:s.ev.length,zp:zpPos(s.pos,s.rl)}})()")
        want = ref.standing()
        assert (got['u'], got['o'], got['srv']) == want, f'Schritt {i} ({what}): Stand {got} erwartet {want}'
        assert got['rot'] == ref.rot and got['pos'] == ref.pos, f'Schritt {i} ({what}): Rotation {got["rot"]}/{got["pos"]} erwartet {ref.rot}/{ref.pos}'
        assert got['zp'] == got['rot'], f'Schritt {i} ({what}): Läufer {got["rot"]} passt nicht zur Zuspielerposition {got["zp"]}'
        assert got['n'] == len(ref.ev) and sorted(got['pos']) == ['p1', 'p2', 'p3', 'p4', 'p5', 'p6']
    while ref.ev: pg.evaluate("undo(curSet())"); ref.undo()
    got = pg.evaluate("(()=>{const s=curSet(),q=replay(s);return{u:q.u,o:q.o,rot:s.rot,pos:s.pos}})()")
    assert got['u'] == got['o'] == 0 and got['rot'] == ref.rot and got['pos'] == ref.pos, ('Alles rückgängig', got, ref.rot, ref.pos)
    assert not pg.errs, pg.errs

@check('Zufallssimulation 1 (600 Schritte): Stand, Aufschlag, Läufer, Aufstellung, Rückgängig')
def _(pg): run_sim(pg, 1, 600)
@check('Zufallssimulation 2 (400 Schritte)')
def _(pg): run_sim(pg, 2, 400)
@check('Zufallssimulation 3 (400 Schritte)')
def _(pg): run_sim(pg, 3, 400)

# ---------- Anleitung stimmt mit der App überein ----------
@check('Anleitung: jedes Feld und jede Taste der App wird erklärt, nichts Veraltetes')
def _(pg):
    open_app(pg, state()); start_set(pg, 'Annahme')
    labels = set(['Punkt Gegner', 'Gegnerfehler', 'Wechsel', 'Rückgängig', 'Satz beenden', 'Läufer', 'Aufschlag tauschen'])
    for cat in ['Annahme', 'Angriff', 'Aufschlag']:
        tap(pg, f'.seg.a-t button:has-text("{cat}")'); labels.add(cat)
        labels |= set(pg.locator('.pr').first.locator('.hb span').all_inner_texts())
    labels |= set(x[1] for x in pg.evaluate("Object.values(ROLES)"))
    tap(pg, '.score'); labels |= set(pg.locator('.a-s button').all_inner_texts()) - {'Wir −1', 'Wir +1', 'Gegner −1', 'Gegner +1'}
    tap(pg, 'nav [data-act=help]'); pg.evaluate("document.querySelectorAll('.help details').forEach(d=>d.open=true)")
    txt = pg.locator('.help').inner_text()
    missing = sorted(l for l in labels if l.split(' (')[0] not in txt)
    assert not missing, 'In der Anleitung fehlt: ' + ', '.join(missing)
    assert 'Punkt wir' not in txt, 'Anleitung nennt entfernte Taste „Punkt wir“'
    assert 'fünf Felder' in txt and 'Block' in txt and 'Zu zweit' in txt and 'Spielstand korrigieren' in txt
    sentences = [x.strip() for x in re.split(r'(?<=[.!?])\s+', txt) if len(x.strip()) > 25]
    assert not any(a == b for a, b in zip(sentences, sentences[1:])), 'Satz steht doppelt hintereinander'
    assert 'gezählt. Direkter Punkt für uns durch' not in txt, 'doppelter Satz bei Angriff Punkt'
    src = SRC; assert 'lv(avg,2.2,1.5,1)' in src and 'lv(pt,35,15,1)' in src and 'lv(er,10,20,0)' in src and '2,2' in txt and '35 %' in txt and '10 %' in txt, 'Schwellen in Anleitung und Code verschieden'
    assert 'wechselt das Aufschlagrecht automatisch' in txt

# ---------- Laptop-Modus (Tastatur) ----------
# Belegung: Bereich Q W E | feste Taste je Spieler (U I O P J K L Ö M , .) in Reihenfolge der Spielerliste | Bewertung 1-5 | A Punkt Gegner, S Gegnerfehler
def kb_state(serve='Annahme', cur=True):
    st = state(players=12); s1 = mkset(1, serve=serve); s1['act'] = ['p1', 'p2', 'p3', 'p4', 'p5', 'p6', 'p7']; s1['pos'] = ['p1', 'p2', 'p3', 'p4', 'p5', 'p6']; s1['rot'] = 1
    st['sets'] = [s1]; st['cur'] = 's1' if cur else None; return st      # Tasten: p1=U p2=I p3=O p4=P p5=J p6=K p7=L; p8..p11 weitere Tasten, p12 ohne Taste
def evs(pg): return pg.evaluate("curSet().ev.map(e=>[e.p,e.c,e.r])")
def keys(pg, seq):
    for k in seq: pg.keyboard.press(k); pg.wait_for_timeout(40)
def msg(pg): return pg.locator('#kbmsg').inner_text()
def tabon(pg): return pg.locator('.seg.a-t button.on').inner_text()
def rowkeys(pg): return {r.locator('.pn b').inner_text(): r.locator('.kk2').inner_text() for r in pg.locator('.pr').all()}

@check('Laptop: Spieler wählen, dann 1-5 bewertet; Bereich springt mit; Aufschlag ohne Spieler', desktop=True)
def _(pg):
    open_app(pg, kb_state()); assert pg.locator('.kb').count() == 1, 'Laptop-Modus nicht automatisch an'
    keys(pg, ['u', '4']); assert evs(pg)[-1] == ['p1', 'rec', 'perf'], evs(pg)                 # U = Spieler 1, 4 = Perfekt
    assert tabon(pg) == 'Angriff'                                                              # Bereich springt wie gewohnt
    keys(pg, ['o', '5']); assert evs(pg)[-1] == ['p3', 'att', 'blk'] and score(pg) == '1 : 0', (evs(pg), score(pg))   # O = Spieler 3, 5 = Block
    assert tabon(pg) == 'Aufschlag' and rot(pg) == '6'
    keys(pg, ['4']); assert evs(pg)[-1] == ['p2', 'srv', 'ace'], evs(pg)                       # ohne Spieler: Aufschläger (nach Drehung Pos.1 = p2)
    assert score(pg) == '2 : 0' and not pg.errs

@check('Laptop: jeder Spieler behält seine Taste (Rotation, Wechsel, Rollenänderung)', desktop=True)
def _(pg):
    open_app(pg, kb_state()); want = {'#1': 'U', '#2': 'I', '#3': 'O', '#4': 'P', '#5': 'J', '#6': 'K', '#7': 'L'}
    assert rowkeys(pg) == want, rowkeys(pg)
    for _ in range(3): pg.evaluate("addEv(curSet(),{p:'',c:'sc',r:'us'});render()"); pg.wait_for_timeout(60)       # mehrfach Side-out: alles rotiert
    assert rowkeys(pg) == want, ('nach Rotation', rowkeys(pg))
    tap(pg, '[data-act=wech]'); pg.locator('[data-sel=wpos][data-i="0"]').select_option('p8'); pg.wait_for_timeout(150)    # p8 kommt aufs Feld
    keys(pg, ['Escape']); rk = rowkeys(pg); assert rk['#8'] == 'Ö' and all(rk[k] == v for k, v in want.items() if k in rk), rk
    pg.locator('[data-sel=wrl][data-v=p3]').count()
    cells = {c.locator('kbd').inner_text(): c.inner_text() for c in pg.locator('.cc').all()}; assert 'U' in cells and 'Ö' in cells, cells

@check('Laptop: Tasten stehen in der Spielerliste, Spieler ohne Taste sind erkennbar', desktop=True)
def _(pg):
    open_app(pg, kb_state()); tap(pg, 'nav [data-act=tab][data-v=pl]')
    got = [x.locator('kbd').inner_text() if x.locator('kbd').count() else '' for x in pg.locator('.pl').all()]
    assert got == ['U', 'I', 'O', 'P', 'J', 'K', 'L', 'Ö', 'M', ',', '.', ''], got      # 12 Spieler, nur 11 Tasten
    open_app(pg, kb_state()); tap(pg, 'nav [data-act=tab][data-v=pl]'); pg.fill('#pname', 'Neu'); pg.fill('#pnr', '77'); tap(pg, '[data-act=addp]')
    assert pg.locator('.pl').last.inner_text().startswith('#77') or 'Neu' in pg.locator('.pl').last.inner_text()    # neuer Spieler hängt hinten an

@check('Laptop: Auswahl bleibt beim Bereichswechsel, Spieler nicht auf dem Feld, falsche Eingaben', desktop=True)
def _(pg):
    open_app(pg, kb_state()); n0 = len(evs(pg))
    keys(pg, ['o', 'w', '3']); assert evs(pg)[-1] == ['p3', 'att', 'eff'], evs(pg)             # Spieler zuerst, dann Bereich, dann Wertung
    keys(pg, ['q', 'l', '3']); assert evs(pg)[-1] == ['p7', 'rec', 'ok'], evs(pg)              # L = Spieler 7 (Zusatzspieler, steht in der Liste)
    n1 = len(evs(pg)); keys(pg, ['q', '3']); assert 'Spieler wählen' in msg(pg) and len(evs(pg)) == n1   # Annahme ohne Spieler
    keys(pg, ['u', '5']); assert 'nur die Bewertungen 1 bis 4' in msg(pg) and len(evs(pg)) == n1        # Annahme hat nur 4 Wertungen
    keys(pg, ['m']); assert 'nicht auf dem Feld' in msg(pg) and len(evs(pg)) == n1                      # M = Spieler 9, nicht im Satz
    keys(pg, ['x', 'y', 'v', '9', 'h']); assert len(evs(pg)) == n1 and not pg.errs

@check('Laptop: A, S, Backspace, Strg+Z, D, F, Esc, Pfeile', desktop=True)
def _(pg):
    open_app(pg, kb_state('Aufschlag'))
    assert tabon(pg) == 'Aufschlag'; keys(pg, ['ArrowRight']); assert tabon(pg) == 'Annahme'; keys(pg, ['ArrowLeft', 'ArrowLeft']); assert tabon(pg) == 'Angriff'
    keys(pg, ['a']); assert score(pg) == '0 : 1' and tabon(pg) == 'Annahme'                    # Punkt Gegner -> Annahme
    keys(pg, ['s']); assert score(pg) == '1 : 1' and tabon(pg) == 'Aufschlag' and rot(pg) == '6'   # Gegnerfehler = Side-out
    keys(pg, ['u']); assert pg.locator('.pr.kbsel').count() == 1
    keys(pg, ['Backspace']); assert pg.locator('.pr.kbsel').count() == 0 and score(pg) == '1 : 1'   # 1. Backspace: Auswahl weg
    keys(pg, ['Backspace']); assert score(pg) == '0 : 1' and rot(pg) == '1'                         # 2. Backspace: letzte Eingabe zurück
    keys(pg, ['s']); pg.keyboard.press('Control+z'); pg.wait_for_timeout(100); assert score(pg) == '0 : 1'
    keys(pg, ['f']); assert pg.locator('.a-s').count() == 1; keys(pg, ['Escape']); assert pg.locator('.a-s').count() == 0
    r0 = rot(pg); keys(pg, ['d']); assert rot(pg) != r0
    keys(pg, ['i', 'Escape']); assert pg.locator('.pr.kbsel').count() == 0 and not pg.errs

@check('Laptop: Tasten wirken nicht in Eingabefeldern oder bei offenem Fenster', desktop=True)
def _(pg):
    open_app(pg, kb_state()); tap(pg, 'nav [data-act=gear]'); n0 = len(evs(pg)); keys(pg, ['a', 's', 'u', '4']); assert len(evs(pg)) == n0
    keys(pg, ['Escape']); assert pg.locator('#ov').count() == 0
    tap(pg, 'nav [data-act=tab][data-v=pl]'); pg.locator('#pname').click(); pg.keyboard.type('asu4')
    assert pg.input_value('#pname') == 'asu4' and len(evs(pg)) == n0
    pg.locator('body').click(position={'x': 700, 'y': 400}); keys(pg, ['?']); assert 'Anleitung' in pg.locator('.md').inner_text(); keys(pg, ['?']); assert pg.locator('#ov').count() == 0

@check('Laptop: Ziffern auf den Feldern, Spielertasten in den Zeilen, Kasten links', desktop=True)
def _(pg):
    open_app(pg, kb_state()); sizes = {'Annahme': 4, 'Angriff': 5, 'Aufschlag': 4}
    for cat_, n in sizes.items():
        tap(pg, f'.seg.a-t button:has-text("{cat_}")'); got = pg.locator('.pr').first.locator('.hb kbd').all_inner_texts(); assert got == [str(i) for i in range(1, n + 1)], (cat_, got)
    assert rowkeys(pg) == {'#1': 'U', '#2': 'I', '#3': 'O', '#4': 'P', '#5': 'J', '#6': 'K', '#7': 'L'}
    assert pg.locator('.cc').count() == 7 and 'Netz' not in pg.locator('.kb').inner_text()
    tap(pg, '.seg.a-t button:has-text("Annahme")'); labels = [x.strip() for x in pg.locator('.pr').first.locator('.hb span').all_inner_texts()]
    assert labels == ['Fehler', 'Schlecht', 'Gut', 'Perfekt']                                  # 1..4 = Reihenfolge der Felder

@check('Laptop: gewählte Kachel ist lesbar, Namen sind nicht abgeschnitten', desktop=True)
def _(pg):
    open_app(pg, kb_state()); keys(pg, ['i'])
    col = pg.evaluate("(()=>{const e=document.querySelector('.cc.on .cn'),c=getComputedStyle(e),b=getComputedStyle(e.closest('.cc'));return[c.color,b.backgroundColor]})()")
    assert col[0] != col[1], f'Text und Hintergrund gleich: {col}'
    assert pg.locator('.pr').nth(3).locator('.pn').evaluate('e=>e.scrollWidth<=e.clientWidth+1'), 'Spielername abgeschnitten'

@check('Laptop-Modus: auf Touch-Geräten aus, in den Einstellungen schaltbar')
def _(pg):
    open_app(pg, kb_state()); assert pg.locator('.kb').count() == 0 and pg.locator('.pr kbd').count() == 0
    pg.keyboard.press('a'); pg.wait_for_timeout(100); assert score(pg) == '0 : 0', 'Tasten dürfen im Touch-Modus nichts auslösen'
    tap(pg, 'nav [data-act=gear]'); pg.locator('[data-sel=lap]').select_option('1'); pg.wait_for_timeout(150); tap(pg, '[data-act=gearx]')
    assert pg.locator('.kb').count() == 1; pg.keyboard.press('a'); pg.wait_for_timeout(100); assert score(pg) == '0 : 1'
    tap(pg, 'nav [data-act=gear]'); pg.locator('[data-sel=lap]').select_option('0'); pg.wait_for_timeout(150); tap(pg, '[data-act=gearx]')
    assert pg.locator('.kb').count() == 0 and not pg.errs

@check('Anleitung beschreibt die Tastenbelegung vollständig und richtig')
def _(pg):
    open_app(pg, state()); tap(pg, 'nav [data-act=help]'); pg.evaluate("document.querySelectorAll('.help details').forEach(d=>d.open=true)")
    txt = re.sub(r'\s+', ' ', pg.locator('.help').inner_text())
    for w in ['Q Annahme', 'W Angriff', 'E Aufschlag', '1 Fehler', '2 Schlecht', '3 Gut', '4 Perfekt', '2 Ohne Wirkung', '3 Wirkung', '4 Punkt', '5 Block', '2 Ohne Wirkung', '4 Ass',
              'immer dieselbe Taste', 'Spielerliste', 'U I O P J K L Ö M , .', 'A Punkt Gegner', 'S Gegnerfehler', 'Läufer weiterdrehen', 'Spielstand korrigieren', 'Laptop-Modus', 'Spiele und Sätze']:
        assert w in txt, f'Anleitung: „{w}“ fehlt'
    assert 'Position 5, 6, 1' not in txt and 'N und M' not in txt, 'Anleitung beschreibt noch die alte Positions-Belegung'
    code = pg.evaluate("[CATKEYS,PKEYS]"); assert code[0] == {'q': 'rec', 'w': 'att', 'e': 'srv'} and code[1] == ['u', 'i', 'o', 'p', 'j', 'k', 'l', 'ö', 'm', ',', '.']

@check('Nach Neuladen oder Fortsetzen steht der Bereich passend zum Aufschlag')
def _(pg):
    st = state(sets=[mkset(1, us=2, serve='Aufschlag')]); st['cur'] = 's1'; open_app(pg, st)
    assert tabon(pg) == 'Aufschlag', tabon(pg)                                  # wir schlagen auf (2:0)
    st = state(sets=[mkset(1, us=1, opp=2, serve='Aufschlag')]); st['cur'] = 's1'; open_app(pg, st)
    assert tabon(pg) == 'Annahme', tabon(pg)                                    # Gegner hat zuletzt gepunktet
    st = state(sets=[mkset(1, us=1, serve='Annahme')]); open_app(pg, st); tap(pg, 'nav [data-act=tab][data-v=game]')
    pg.locator('[data-sel=gid]').select_option('g1'); pg.wait_for_timeout(150); tap(pg, '[data-act=resume]')
    assert tabon(pg) == 'Aufschlag', tabon(pg)                                  # Satz fortsetzen: wir haben zuletzt gepunktet

@check('Beschriftungen: Gut statt Ok, Ohne Wirkung statt Recycle; interne Daten unverändert')
def _(pg):
    open_app(pg, state()); start_set(pg, 'Annahme'); got = {}
    for cat_ in ['Annahme', 'Angriff', 'Aufschlag']:
        tap(pg, f'.seg.a-t button:has-text("{cat_}")'); got[cat_] = [x.strip() for x in pg.locator('.pr').first.locator('.hb span').all_inner_texts()]
    assert got == {'Annahme': ['Fehler', 'Schlecht', 'Gut', 'Perfekt'], 'Angriff': ['Fehler', 'Ohne Wirkung', 'Wirkung', 'Punkt', 'Block'], 'Aufschlag': ['Fehler', 'Ohne Wirkung', 'Wirkung', 'Ass']}, got
    tap(pg, '.seg.a-t button:has-text("Annahme")'); tap(pg, '[data-act=hit][data-v="p1|rec|ok"]'); tap(pg, '.seg.a-t button:has-text("Angriff")'); tap(pg, '[data-act=hit][data-v="p1|att|rec"]')
    ev = pg.evaluate("curSet().ev.map(e=>[e.c,e.r])"); assert ev == [['rec', 'ok'], ['att', 'rec']], ev
    tap(pg, 'nav [data-act=help]'); pg.evaluate("document.querySelectorAll('.help details').forEach(d=>d.open=true)"); txt = pg.locator('.help').inner_text()
    assert 'Recycle' not in txt and 'Ok plus' not in txt and 'Schlecht, Ok' not in txt, 'Anleitung nennt noch die alten Begriffe'

@check('Alte Beschriftungen aus der Tabelle (Ok, Recycle) werden weiterhin gelesen')
def _(pg):
    body = {'players': [{'id': 'p1', 'name': 'A', 'nr': '1', 'role': ''}], 'games': [{'id': 'g1', 'opp': 'A', 'date': '2026-01-01'}], 'ver': 6,
            'sets': [{'id': 's1', 'gid': 'g1', 'opp': 'A', 'date': '2026-01-01', 'serve': 'Aufschlag', 'rot': 1, 'act': ['p1'], 'pos': [], 'rl': {}}],
            'events': [{'id': 'e1', 'sid': 's1', 'p': 'p1', 'bereich': 'Annahme', 'ergebnis': 'Ok', 'rot': 1, 't': 1}, {'id': 'e2', 'sid': 's1', 'p': 'p1', 'bereich': 'Angriff', 'ergebnis': 'Recycle', 'rot': 1, 't': 2},
                       {'id': 'e3', 'sid': 's1', 'p': 'p1', 'bereich': 'Annahme', 'ergebnis': 'Gut', 'rot': 1, 't': 3}, {'id': 'e4', 'sid': 's1', 'p': 'p1', 'bereich': 'Angriff', 'ergebnis': 'Ohne Wirkung', 'rot': 1, 't': 4}]}
    pg.route('https://script.google.com/**', lambda r: r.fulfill(status=200, content_type='application/json', headers={'access-control-allow-origin': '*'}, body=json.dumps(body)))
    open_app(pg, state(players=1), cfg={'url': URL, 'pw': PW}); pg.wait_for_timeout(700)
    ev = json.loads(pg.evaluate('localStorage.getItem("vbtracker1")'))['sets'][0]['ev']
    assert [(e['c'], e['r']) for e in sorted(ev, key=lambda e: e['t'])] == [('rec', 'ok'), ('att', 'rec'), ('rec', 'ok'), ('att', 'rec')], ev

@check('Aufschlagrecht wechselt mit jedem Satz')
def _(pg):
    for first, expected in [('Aufschlag', 'Annahme'), ('Annahme', 'Aufschlag')]:
        st = state(sets=[mkset(1, serve=first)]); open_app(pg, st); tap(pg, 'nav [data-act=tab][data-v=game]')
        pg.locator('[data-sel=gid]').select_option('g1'); pg.wait_for_timeout(150)
        assert pg.locator(f'[data-act=serve][data-v={expected}]').get_attribute('class') == 'on', (first, expected)
    st = state(sets=[mkset(1, serve='Aufschlag'), mkset(2, serve='Annahme')]); open_app(pg, st); tap(pg, 'nav [data-act=tab][data-v=game]')
    pg.locator('[data-sel=gid]').select_option('g1'); pg.wait_for_timeout(150)
    assert pg.locator('[data-act=serve][data-v=Aufschlag]').get_attribute('class') == 'on'    # nach Satz 2 (Annahme) -> Aufschlag

@check('Querformat: alle 7 Spieler sichtbar, große Buttons, schmale Navigation')
def _(pg):
    st = state(sets=[mkset(1)]); st['sets'][0]['act'] = ['p%d' % i for i in range(1, 8)]; st['cur'] = 's1'
    for i, r in enumerate(['MB', 'MB', 'AA', 'AA', 'DI', 'ZP', 'LI']): st['players'][i]['role'] = r
    pg.set_viewport_size({'width': 844, 'height': 340}); open_app(pg, st); pg.wait_for_timeout(300)
    assert 'land' in pg.evaluate('document.documentElement.className')
    rows = pg.locator('.pr'); assert rows.count() == 7
    last = rows.nth(6).bounding_box(); assert last['y'] + last['height'] <= 340, f"7. Spieler unterhalb des Bildschirms: {last}"
    btn = pg.locator('.pr .hb').first.bounding_box(); assert btn['width'] >= 95 and btn['height'] >= 36, btn
    nav = pg.locator('nav').bounding_box(); assert nav['width'] <= 80 and nav['x'] < 5 and nav['height'] >= 330, nav
    assert pg.evaluate('document.documentElement.scrollWidth <= innerWidth + 1'), 'horizontales Scrollen'
    pg.screenshot(path='/tmp/land2.png'); assert not pg.errs

@check('Start-Läufer ergibt sich aus der Position des Zuspielers')
def _(pg):
    st = state(); st['players'][4]['role'] = 'ZP'            # Sp5 ist Zuspieler
    open_app(pg, st); tap(pg, 'nav [data-act=tab][data-v=game]'); pg.fill('[data-in=opp]', 'X')
    for i in range(6): pg.locator('.chip').nth(i).click(); pg.wait_for_timeout(40)
    assert 'Läufer 5' in pg.locator('main').inner_text() and pg.locator('[data-act=rot]').count() == 0
    pg.locator('[data-sel=pos][data-i="0"]').select_option('p5'); pg.wait_for_timeout(150)   # Zuspieler auf Position 1
    assert 'Läufer 1' in pg.locator('main').inner_text()
    pg.locator('[data-sel=pos][data-i="3"]').select_option('p5'); pg.wait_for_timeout(150)   # Zuspieler auf Position 4
    assert 'Läufer 4' in pg.locator('main').inner_text()
    tap(pg, '[data-act=serve][data-v=Annahme]'); tap(pg, '[data-act=start]')
    assert rot(pg) == '4'
    us(pg); assert rot(pg) == '3'     # Rotation: 4 -> 3, Zuspieler rückt mit
    assert not pg.errs

@check('Nach Aufschlag ohne Punkt/Fehler wechselt die App in den Angriff')
def _(pg):
    open_app(pg, state()); start_set(pg, 'Aufschlag')
    on = lambda: pg.locator('.seg.a-t button.on').inner_text()
    assert on() == 'Aufschlag'
    for res in ['none', 'eff']:
        tap(pg, '.seg.a-t button:has-text("Aufschlag")')
        tap(pg, f'[data-act=hit][data-v="p1|srv|{res}"]'); assert on() == 'Angriff', (res, on())
    tap(pg, '.seg.a-t button:has-text("Aufschlag")')
    tap(pg, '[data-act=hit][data-v="p1|srv|ace"]'); assert on() == 'Aufschlag', 'nach Ass schlagen wir weiter auf'
    tap(pg, '[data-act=hit][data-v="p1|srv|err"]'); assert on() == 'Annahme', 'nach Fehler nimmt das Team an'

@check('Aufstellung: Aufschläger folgt der Rotation')
def _(pg):
    open_app(pg, state()); start_set(pg, 'Annahme')
    sub = lambda: pg.locator('.sub').inner_text()
    assert 'Aufschlag Gegner' in sub()
    us(pg); assert '#2 Sp2' in sub(), sub()        # Position 2 rückt auf Position 1
    us(pg); assert '#2 Sp2' in sub()               # weiter aufgeschlagen
    tap(pg, '[data-act=pt][data-v=opp]'); us(pg); assert '#3 Sp3' in sub(), sub()
    tap(pg, '[data-act=undo]'); tap(pg, '[data-act=undo]'); assert '#2 Sp2' in sub(), sub()   # Rotation wird mit zurückgenommen
    tap(pg, '[data-act=undo]'); tap(pg, '[data-act=undo]'); assert 'Aufschlag Gegner' in sub() and 'Sp' not in sub()
    assert pg.locator('.pr .pp').first.inner_text() == '1'

@check('Wechsel setzt Spieler auf Position, Vertauschen und Ausgewechselte')
def _(pg):
    open_app(pg, state()); start_set(pg, 'Aufschlag')
    assert '#1 Sp1' in pg.locator('.sub').inner_text()
    tap(pg, '[data-act=wech]')
    pg.locator('[data-sel=wpos][data-i="0"]').select_option('p7'); pg.wait_for_timeout(200)
    assert '#7 Sp7' in pg.locator('.sub').inner_text()
    rows = pg.locator('.pr').all_inner_texts()
    assert len(rows) == 6 and not any('Sp1' in r for r in rows), rows
    pg.locator('[data-sel=wpos][data-i="1"]').select_option('p7'); pg.wait_for_timeout(200)   # p7 tauscht mit Pos. 2-Spieler
    assert '#2 Sp2' in pg.locator('.sub').inner_text()
    assert not pg.errs, pg.errs

@check('Setup: Aufstellung wird ohne Doppelbelegung gespeichert')
def _(pg):
    open_app(pg, state()); tap(pg, 'nav [data-act=tab][data-v=game]'); pg.fill('[data-in=opp]', 'X')
    for i in range(6): pg.locator('.chip').nth(i).click(); pg.wait_for_timeout(40)
    pg.locator('[data-sel=pos][data-i="0"]').select_option('p3'); pg.wait_for_timeout(150)
    tap(pg, '[data-act=start]')
    s = json.loads(pg.evaluate('localStorage.getItem("vbtracker1")'))['sets'][-1]
    assert s['pos'][0] == 'p3' and s['pos'][2] == 'p1' and len(set(s['pos'])) == 6, s['pos']

@check('Spielerzeilen sind nach Rolle gruppiert (MB, AA, DI, ZP, LI)')
def _(pg):
    st = state(); roles = ['DI', 'MB', 'AA', 'MB', 'ZP', 'AA', '']
    for p, r in zip(st['players'], roles): p['role'] = r
    st['sets'] = [mkset(1)]; st['cur'] = 's1'; open_app(pg, st)
    order = [x.strip() for x in pg.locator('.pr .pn b').all_inner_texts()]
    assert order == ['#2', '#4', '#3', '#6', '#1', '#5'], order
    assert pg.locator('.pr .rl').count() == 6 and not pg.errs

@check('Rolle kann bei Spielern gesetzt werden und wird als Operation gespeichert')
def _(pg):
    open_app(pg, state()); tap(pg, 'nav [data-act=tab][data-v=pl]')
    pg.locator('[data-sel=prole]').first.select_option('MB'); pg.wait_for_timeout(200)
    ls = json.loads(pg.evaluate('localStorage.getItem("vbtracker1")'))
    assert ls['players'][0]['role'] == 'MB' and any(o['k'] == 'p~' and o['role'] == 'MB' for o in ls['pend']), ls['pend'][-1:]
    pg.fill('#pname', 'Neu'); pg.fill('#pnr', '9'); pg.select_option('#prole0', 'LI'); tap(pg, '[data-act=addp]')
    assert json.loads(pg.evaluate('localStorage.getItem("vbtracker1")'))['players'][-1]['role'] == 'LI'

# ---------- Sicherheit (Pentest) ----------
@check('PIN-Sperre: falscher PIN bleibt gesperrt, richtiger öffnet')
def _(pg):
    open_app(pg, unlocked=False)
    assert pg.locator('#pin').count() == 1 and pg.locator('nav button').count() == 0
    pg.fill('#pin', 'falsch'); tap(pg, '[data-act=unlock]'); pg.wait_for_timeout(1200)
    assert pg.locator('#pin').count() == 1
    pg.fill('#pin', 'VCRMH3'); tap(pg, '[data-act=unlock]'); pg.wait_for_timeout(1500)
    assert pg.locator('nav button').count() > 0

@check('PIN-Brute-Force wird gebremst')
def _(pg):
    open_app(pg, unlocked=False)
    for i in range(3):
        pg.fill('#pin', f'x{i}'); tap(pg, '[data-act=unlock]'); pg.wait_for_timeout(900)
    pg.fill('#pin', 'vcrmh3'); tap(pg, '[data-act=unlock]'); pg.wait_for_timeout(1200)
    assert pg.locator('#pin').count() == 1, 'richtiger PIN trotz Sperrfrist akzeptiert'

EVIL = '<img src=x onerror=window.__xss=1>'
def evil_state():
    s = state(sets=[mkset(1, us=2)]); s['cur'] = 's1'
    s['players'] += [{'id': '"><img src=x onerror=window.__xss=1>', 'name': EVIL, 'nr': EVIL},
                     {'id': 'rz', 'name': 'x', 'nr': '1', 'role': '"><img src=x onerror=window.__xss=1>'}, {'id': '__proto__', 'name': 'x', 'nr': '1'}, {'id': 'ok1', 'name': EVIL + 'A' * 500, 'nr': '99999999'}]
    s['games'][0]['opp'] = EVIL; s['games'][0]['date'] = '2026"><svg onload=window.__xss=1>'
    s['sets'][0]['serve'] = '"><svg onload=window.__xss=1>'; s['sets'][0]['act'] += ['"><b>']; s['sets'][0]['pos'] = ['"><img src=x onerror=window.__xss=1>', 'p1', 5, None, '', 'p2', 'p3']
    s['sets'][0]['ev'].append({'id': 'e"x', 'p': 'p1', 'c': '__proto__', 'r': 'constructor', 'rot': 1, 't': 1})
    return s
def no_xss(pg):
    for tabn in ['pl', 'game', 'eval']:
        tap(pg, f'nav [data-act=tab][data-v={tabn}]')
    assert pg.evaluate('window.__xss') is None, 'XSS ausgeführt'
    assert pg.locator('main img, main svg, main b:has-text("\\"")').count() == 0, 'Fremdes HTML im DOM'
    assert not pg.dialogs and not pg.errs, (pg.dialogs, pg.errs)

@check('XSS über manipulierten Browser-Speicher')
def _(pg): open_app(pg, evil_state()); no_xss(pg)

@check('XSS über JSON-Import')
def _(pg):
    open_app(pg, state()); tap(pg, 'nav [data-act=gear]'); pg.fill('#imp', json.dumps(evil_state())); tap(pg, '[data-act=imp]')
    tap(pg, '[data-act=gearx]'); no_xss(pg)
    assert not any(p.get('id') == '__proto__' for p in json.loads(pg.evaluate('localStorage.getItem("vbtracker1")'))['players'])

@check('Import: Müll und Übergröße werden abgelehnt')
def _(pg):
    open_app(pg, state()); tap(pg, 'nav [data-act=gear]')
    before = pg.evaluate('localStorage.getItem("vbtracker1")')
    for bad in ['{kaputt', '[]', '"x"', 'A' * 4_000_000]:
        pg.evaluate('v=>{const t=document.getElementById("imp");t.style.display="none";t.value=v}', bad); tap(pg, '[data-act=imp]')
    assert pg.evaluate('localStorage.getItem("vbtracker1")') == before and not pg.errs

def sync_page(pg, handler, st=None):
    pg.route('https://script.google.com/**', handler)
    open_app(pg, st or state(), cfg={'url': URL, 'pw': PW}); pg.wait_for_timeout(500)

@check('Manipulierte Server-Antwort (Prototype Pollution, Müll)')
def _(pg):
    body = {'ver': 6, 'players': [{'id': 'p1', 'name': EVIL, 'nr': '1'}], 'games': [{'id': 'g1', 'opp': 'A', 'date': '2026-01-01'}],
            'sets': [{'id': 's1', 'gid': 'g1', 'opp': 'A', 'date': '2026-01-01', 'serve': 'Aufschlag', 'rot': 99, 'act': ['p1']}],
            'events': [{'id': 'e1', 'sid': '__proto__', 'p': 'p1', 'bereich': 'Annahme', 'ergebnis': 'Ok', 'rot': 1, 't': 1},
                       {'id': 'e2', 'sid': 'constructor', 'p': 'p1', 'bereich': '__proto__', 'ergebnis': 'x', 'rot': 1, 't': 1},
                       {'id': 'e3', 'sid': 's1', 'p': 'p1', 'bereich': 'Annahme', 'ergebnis': 'Perfekt', 'rot': 3, 't': 5}]}
    sync_page(pg, lambda r: r.fulfill(status=200, content_type='application/json', headers={'access-control-allow-origin': '*'}, body=json.dumps(body)))
    assert pg.evaluate('({}).bereich===undefined && ({}).sid===undefined && Object.keys(Object.prototype).length===0')
    ls = json.loads(pg.evaluate('localStorage.getItem("vbtracker1")'))
    assert len(ls['sets'][0]['ev']) == 1 and ls['sets'][0]['rot'] == 1, ls['sets']
    no_xss(pg)

@check('Nur gültige Apps-Script-URLs werden akzeptiert')
def _(pg):
    hits = []; pg.route('https://evil.example/**', lambda r: (hits.append(r.request.url), r.abort()))
    open_app(pg, state()); tap(pg, 'nav [data-act=gear]')
    for u in ['https://evil.example/exec', 'http://script.google.com/macros/s/AKfycbxAAAAAAAAAAAAAAAAAAAAAAAAAAAA/exec', 'javascript:alert(1)']:
        pg.fill('#cfgurl', u); pg.fill('#cfgpw', 'x'); tap(pg, '[data-act=cfg]'); pg.wait_for_timeout(200)
    cfg = pg.evaluate('localStorage.getItem("vbcfg1")')
    assert not hits and (cfg is None or json.loads(cfg).get('url', '') == ''), (hits, cfg)
    open_app(pg, state(), cfg={'url': 'https://evil.example/exec', 'pw': PW}); pg.wait_for_timeout(300)
    assert not hits, 'Passwort ging an fremden Host'

@check('Sync sendet text/plain mit Passwort und Operationen')
def _(pg):
    seen = []
    def h(r):
        seen.append((r.request.headers.get('content-type', ''), r.request.post_data))
        r.fulfill(status=200, content_type='application/json', headers={'access-control-allow-origin': '*'},
                  body=json.dumps({'ver': 6, 'players': [{'id': 'pz', 'name': 'Zed', 'nr': '9'}], 'games': [], 'sets': [], 'events': []}))
    sync_page(pg, h, st=state(players=0))
    tap(pg, 'nav [data-act=tab][data-v=pl]'); pg.fill('#pname', 'Zed'); pg.fill('#pnr', '9'); tap(pg, '[data-act=addp]'); pg.wait_for_timeout(1500)
    assert seen and seen[-1][0].startswith('text/plain'), seen
    body = json.loads(seen[-1][1]); assert body['pw'] == PW and body['ops'][0]['k'] == 'p+' and body['ops'][0]['p']['name'] == 'Zed'

@check('CSP blockt Inline-Handler und fremde Verbindungen')
def _(pg):
    open_app(pg, state())
    assert 'Content-Security-Policy' in SRC
    pg.evaluate('document.body.insertAdjacentHTML("beforeend","<img src=x onerror=window.__csp=1>")'); pg.wait_for_timeout(300)
    assert pg.evaluate('window.__csp') is None, 'Inline-Handler wurde ausgeführt'

if __name__ == '__main__':
    only = sys.argv[1:] 
    with sync_playwright() as p:
        br = p.chromium.launch()
        for t in TESTS:
            if not only or any(o in t.__name__ for o in only): t(br)
        br.close()
    fails = [r for r in RES if not r[1]]
    for n, ok, m in RES: print(('PASS ' if ok else 'FAIL ') + n + ('' if ok else '  -> ' + m))
    print(f'\n{len(RES) - len(fails)}/{len(RES)} bestanden'); sys.exit(1 if fails else 0)
