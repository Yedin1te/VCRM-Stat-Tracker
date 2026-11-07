# Sync-Tests gegen das nachgebaute Google-Skript (lokaler Server). Start: python3 tests/sync.test.py
import os, sys, json, time, subprocess, urllib.request
os.environ['APP'] = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'index.html'))
exec(open(os.path.join(os.path.dirname(__file__), 'app.test.py'), encoding='utf-8').read().split("if __name__")[0])
TESTS.clear(); RES.clear()
PORT, OLDPORT, SPW = 8766, 8767, 'sync-test-passwort-123'
srv = subprocess.Popen(['node', os.path.join(os.path.dirname(__file__), 'gas_server.js'), str(PORT)])
srv_old = subprocess.Popen(['node', os.path.join(os.path.dirname(__file__), 'gas_server.js'), str(OLDPORT), 'old']); time.sleep(1.2)
ONLINE = {'on': True, 'port': PORT}
def post(path, data=b'', port=None): return urllib.request.urlopen(urllib.request.Request(f'http://127.0.0.1:{port or ONLINE["port"]}{path}', data=data, method='POST')).read()
def handler(route):
    if not ONLINE['on']: return route.abort()
    route.fulfill(status=200, content_type='application/json', headers={'access-control-allow-origin': '*'}, body=post('/', route.request.post_data.encode()))
def device(br, st=None):
    ctx = br.new_context(viewport={'width': 390, 'height': 800}, is_mobile=True, has_touch=True); pg = ctx.new_page(); pg.errs = []
    pg.on('pageerror', lambda e: pg.errs.append(str(e))); pg.route('https://script.google.com/**', handler)
    open_app(pg, st, cfg={'url': URL, 'pw': SPW}); return pg
def do_sync(pg): pg.evaluate('sync()'); pg.wait_for_timeout(250)
def snap(pg):
    d = json.loads(pg.evaluate('localStorage.getItem("vbtracker1")'))
    return {'players': sorted((p['id'], p['name'], p['nr'], p.get('role', '')) for p in d['players']),
            'games': sorted((g['id'], g['opp'], g['date']) for g in d['games']),
            'sets': sorted((x['id'], x['gid'], x['serve'], x['rot'], tuple(x['pos']), tuple(sorted(x['act'])), tuple(sorted(x.get('rl', {}).items())),
                            tuple(sorted((e['id'], e['p'], e['c'], e['r'], e['rot']) for e in x['ev']))) for x in d['sets'])}
def run(name, fn, old=False):
    ONLINE['on'] = True; ONLINE['port'] = OLDPORT if old else PORT; post('/reset')
    with sync_playwright() as p:
        br = p.chromium.launch(); ok, msg = True, ''
        try: fn(br)
        except AssertionError as e: ok, msg = False, str(e) or 'Assertion'
        except Exception as e: ok, msg = False, f'{type(e).__name__}: {str(e)[:200]}'
        br.close(); RES.append((name, ok, msg))

def rich_state():
    st = state(players=7); st['players'][3]['role'] = 'ZP'; st['players'][0]['role'] = 'AA'
    s1 = mkset(1, us=3, opp=2); s1['pos'] = ['p1', 'p2', 'p3', 'p4', 'p5', 'p6']; s1['rl'] = {'p1': 'DI', 'p7': 'LI'}
    s1['ev'] += [{'id': 'x1', 'p': 'p2', 'c': 'att', 'r': 'blk', 'rot': 2, 't': 300}, {'id': 'x2', 'p': 'p3', 'c': 'rec', 'r': 'perf', 'rot': 2, 't': 301},
                 {'id': 'x3', 'p': '', 'c': 'sc', 'r': 'wp', 'rot': 2, 't': 302}, {'id': 'x4', 'p': 'p5', 'c': 'srv', 'r': 'none', 'rot': 2, 't': 303}]
    s2 = mkset(2, us=1, serve='Annahme'); s2['pos'] = ['p2', 'p3', 'p4', 'p5', 'p6', 'p1']; s2['rot'] = 3
    st['sets'] = [s1, s2]; st['games'].append({'id': 'g2', 'opp': 'B-Team', 'date': '2026-02-02'})
    s3 = mkset(3, us=2); s3['gid'] = 'g2'; st['sets'].append(s3); return st

def t_roundtrip(br):
    a = device(br, rich_state()); a.evaluate('pushAll()'); a.wait_for_timeout(600); do_sync(a)
    b = device(br); do_sync(b)
    sa, sb = snap(a), snap(b); assert sa == sb, f'A und B verschieden:\nA={json.dumps(sa)[:300]}\nB={json.dumps(sb)[:300]}'
    assert len(sb['sets']) == 3 and sum(len(x[7]) for x in sb['sets']) == len(rich_state()['sets'][0]['ev']) + len(rich_state()['sets'][1]['ev']) + len(rich_state()['sets'][2]['ev'])
    assert not a.errs and not b.errs, (a.errs, b.errs)
run('Sync: Rundreise Handy A -> Tabelle -> Handy B (Rollen, Aufstellung, Block, Korrekturen)', t_roundtrip)

def t_delete(br):
    a = device(br, rich_state()); a.evaluate('pushAll()'); a.wait_for_timeout(600)
    b = device(br); do_sync(b); assert len(snap(b)['sets']) == 3
    a.evaluate("op({k:'s-',id:'s2'})"); a.wait_for_timeout(1500); do_sync(b)
    assert [x[0] for x in snap(b)['sets']] == ['s1', 's3'], snap(b)['sets']
    a.evaluate("op({k:'g-',id:'g1'})"); a.wait_for_timeout(1500); do_sync(b)
    sb = snap(b); assert [x[0] for x in sb['games']] == ['g2'] and [x[0] for x in sb['sets']] == ['s3'], sb['games']
    assert snap(a) == sb
run('Sync: Löschen von Satz und Spiel kommt auf dem anderen Handy an', t_delete)

def t_offline(br):
    a = device(br, state(players=7)); a.evaluate('pushAll()'); a.wait_for_timeout(600)
    ONLINE['on'] = False
    a.evaluate("(()=>{op({k:'g+',g:{id:'gx',opp:'Offline',date:'2026-03-03'}});op({k:'s+',s:{id:'sx',gid:'gx',opp:'Offline',date:'2026-03-03',serve:'Annahme',rot:1,act:['p1'],pos:['p1','','','','',''],rl:{}}});addEv(curSet()||S.sets[0],{p:'p1',c:'rec',r:'ok'})})()")
    a.wait_for_timeout(1200); do_sync(a)
    assert a.evaluate('S.pend.length') >= 3 and 'Fehler' in a.evaluate("document.getElementById('st')?document.getElementById('st').textContent:stTxt()") or a.evaluate('S.pend.length') >= 3
    ONLINE['on'] = True; do_sync(a); a.wait_for_timeout(500)
    assert a.evaluate('S.pend.length') == 0, 'Warteschlange nicht abgearbeitet'
    b = device(br); do_sync(b); assert any(x[0] == 'sx' for x in snap(b)['sets']), 'Offline-Satz kam nicht in der Tabelle an'
run('Sync: Eingaben ohne Netz werden nachgeholt', t_offline)

def t_two(br):
    st = state(players=7); st['players'][3]['role'] = 'ZP'
    a = device(br, st); a.evaluate('pushAll()'); a.wait_for_timeout(600)
    start_set(a, 'Annahme'); a.wait_for_timeout(1500); do_sync(a)
    b = device(br); do_sync(b)
    tap(b, 'nav [data-act=tab][data-v=game]'); b.locator('[data-sel=gid]').select_option('g1') if False else None
    b.evaluate("(()=>{S.cur=S.sets[S.sets.length-1].id;render()})()")                  # entspricht Tipp auf 'Satz 1 fortsetzen'
    assert b.evaluate('curSet().id') == a.evaluate('curSet().id')
    # A: punkt-entscheidende Eingaben, B: nur Bewertungen ohne Punkt, abwechselnd und mit Verzögerung beim Abgleich
    for rnd_ in range(6):
        a.evaluate("addEv(curSet(),{p:'p2',c:'att',r:'pt'})")                         # A: Punkt (Side-out bei Annahme -> Drehung)
        b.evaluate("addEv(curSet(),{p:'p3',c:'rec',r:'ok'})"); b.evaluate("addEv(curSet(),{p:'p5',c:'srv',r:'eff'})")
        a.wait_for_timeout(900); b.wait_for_timeout(900)
        a.evaluate("addEv(curSet(),{p:'p1',c:'sc',r:'opp'})")
        b.evaluate("addEv(curSet(),{p:'p4',c:'att',r:'rec'})")
        a.wait_for_timeout(900); b.wait_for_timeout(900)
    do_sync(a); do_sync(b); do_sync(a)
    sa, sb = snap(a), snap(b); assert sa == sb, 'Handys sind nach dem Abgleich verschieden'
    ev = sa['sets'][-1][7]; assert len(ev) == 6 * 5, len(ev)
    got = a.evaluate("(()=>{const s=curSet(),q=replay(s);return{u:q.u,o:q.o,rot:s.rot,pos:s.pos,zp:zpPos(s.pos,s.rl)}})()")
    gotb = b.evaluate("(()=>{const s=curSet(),q=replay(s);return{u:q.u,o:q.o,rot:s.rot,pos:s.pos,zp:zpPos(s.pos,s.rl)}})()")
    assert got == gotb and got['zp'] == got['rot'], (got, gotb)
    assert not a.errs and not b.errs
run('Zu zweit: A zählt Punkte, B zählt Bewertungen -> beide Handys zeigen denselben Stand und Läufer', t_two)

def t_connect(br):
    ctx = br.new_context(viewport={'width': 390, 'height': 800}, is_mobile=True, has_touch=True); a = ctx.new_page(); a.errs = []
    a.on('pageerror', lambda e: a.errs.append(str(e))); a.route('https://script.google.com/**', handler)
    st = rich_state(); open_app(a, st)                                          # lokale Daten, noch keine Tabelle
    tap(a, 'nav [data-act=gear]'); a.fill('#cfgurl', URL); a.fill('#cfgpw', SPW); tap(a, '[data-act=cfg]'); a.wait_for_timeout(1500)
    local = snap(a); assert len(local['sets']) == 3 and len(local['players']) == 7, 'lokale Daten gingen beim Verbinden verloren'
    b = device(br); do_sync(b); assert snap(b) == local, 'Tabelle enthält nicht die lokalen Daten'
    ctx.close()
run('Sync: Verbinden mit leerer Tabelle behält und überträgt die lokalen Daten', t_connect)

def t_conflict(br):
    st = state(players=7); st['players'][3]['role'] = 'ZP'
    a = device(br, st); a.evaluate('pushAll()'); a.wait_for_timeout(600); start_set(a, 'Annahme'); a.wait_for_timeout(1500); do_sync(a)
    b = device(br); do_sync(b); b.evaluate("(()=>{S.cur=S.sets[S.sets.length-1].id;render()})()")
    for i in range(8):                                  # beide zählen gleichzeitig Punkte, ohne Abgleich dazwischen
        a.evaluate("addEv(curSet(),{p:'p2',c:'att',r:'pt'})"); b.evaluate("addEv(curSet(),{p:'p3',c:'att',r:'pt'})")
        a.evaluate("addEv(curSet(),{p:'',c:'sc',r:'opp'})"); b.evaluate("addEv(curSet(),{p:'',c:'sc',r:'opp'})")
    a.wait_for_timeout(2500); b.wait_for_timeout(2500); do_sync(a); do_sync(b); do_sync(a)
    assert snap(a) == snap(b), 'Handys nach Abgleich verschieden'
    assert not a.errs and not b.errs
run('Zu zweit ohne Aufteilung: kein Absturz, beide Handys zeigen nach dem Abgleich denselben Stand', t_conflict)

def t_resurrect(br):
    a = device(br, rich_state()); a.evaluate('pushAll()'); a.wait_for_timeout(600)
    b = device(br); do_sync(b); assert len(snap(b)['sets']) == 3
    a.evaluate("op({k:'g-',id:'g1'})"); a.wait_for_timeout(1500)                     # A löscht Spiel 1 (Satz 1 und 2)
    assert [x[0] for x in snap(a)['games']] == ['g2']
    b.evaluate('queueAll()'); do_sync(b); do_sync(b); do_sync(a)                       # B kennt die Löschung nicht und lädt seinen alten Stand erneut hoch
    sa, sb = snap(a), snap(b)
    assert [x[0] for x in sb['games']] == ['g2'] and [x[0] for x in sb['sets']] == ['s3'], ('Gelöschtes kam bei B zurück', sb['games'], [x[0] for x in sb['sets']])
    assert sa == sb and [x[0] for x in sa['games']] == ['g2'], 'Gelöschtes kam bei A zurück'
    c = device(br); do_sync(c); assert [x[0] for x in snap(c)['games']] == ['g2'], 'neues Handy sieht Gelöschtes'
run('Sync: Gelöschtes wird auch von einem alten Handy nicht wieder hochgeladen', t_resurrect)

def t_oldscript(br):
    a = device(br, rich_state()); a.evaluate('pushAll()'); a.wait_for_timeout(800); do_sync(a)
    st = a.evaluate("document.getElementById('st')?document.getElementById('st').textContent:''"); assert 'veraltet' in st, st
    a.evaluate("op({k:'g-',id:'g1'})"); a.wait_for_timeout(1800)                      # automatischer Abgleich nach dem Löschen
    st = a.evaluate("document.getElementById('st').textContent"); assert 'Löschen wurde vom Google-Skript nicht ausgeführt' in st, st
    assert any(x[0] == 'g1' for x in snap(a)['games']), 'Server ist die Wahrheit: der Eintrag ist wieder da, die App warnt'
    do_sync(a); st = a.evaluate("document.getElementById('st').textContent"); assert 'veraltet' in st, st      # Warnung bleibt bestehen
run('Sync: veraltetes Google-Skript wird erkannt, Löschen meldet den Fehler deutlich', t_oldscript, old=True)

def t_newscript_ok(br):
    a = device(br, rich_state()); a.evaluate('pushAll()'); a.wait_for_timeout(800); do_sync(a)
    st = a.evaluate("document.getElementById('st').textContent"); assert 'Synchronisiert' in st and 'veraltet' not in st, st
    a.evaluate("op({k:'s-',id:'s2'})"); a.wait_for_timeout(1500); do_sync(a)
    st = a.evaluate("document.getElementById('st').textContent"); assert 'Synchronisiert' in st and 'nicht ausgeführt' not in st, st
run('Sync: aktuelles Skript wird akzeptiert, keine Warnung beim Löschen', t_newscript_ok)

if __name__ == '__main__':
    srv.terminate(); srv_old.terminate()
    for n, ok, m in RES: print(('PASS ' if ok else 'FAIL ') + n + ('' if ok else '  -> ' + m))
    fails = [r for r in RES if not r[1]]; print(f'\n{len(RES) - len(fails)}/{len(RES)} bestanden'); sys.exit(1 if fails else 0)
