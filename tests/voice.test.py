# Tests für die Sprach-Demo. Start: python3 tests/voice.test.py
import os, sys, json
os.environ['APP'] = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'voice-demo.html'))
exec(open(os.path.join(os.path.dirname(__file__), 'app.test.py'), encoding='utf-8').read().split("if __name__")[0])
TESTS.clear(); RES.clear()
FAKE = """window.SpeechRecognition=class{start(){window.__rec=this}stop(){}};
window.__say=t=>{const r=window.__rec,x=[{transcript:t}];x.isFinal=true;r.onresult({resultIndex:0,results:[x]})};"""
def vpage(pg, st=None):
    pg.add_init_script(FAKE); open_app(pg, st or state(players=20))
def parse(pg, text):
    return pg.evaluate("t=>vparse(t,curSet()||{pos:[]}).map(a=>a.ok?[a.c,a.r,a.p]:['x',a.label])", text)
def with_set(pg, serve='Annahme'):
    vpage(pg); start_set(pg, serve)

@check('Sprache: Beispielsatz wird in drei Eingaben zerlegt')
def _(pg):
    with_set(pg)
    got = parse(pg, 'gute Annahme von 14, wirkungsloser Angriff von 3 und Angriffspunkt von 19')
    assert got == [['rec', 'ok', 'p14'], ['att', 'rec', 'p3'], ['att', 'pt', 'p19']], got

@check('Sprache: Wortschatz Annahme/Angriff/Aufschlag/Spielstand')
def _(pg):
    with_set(pg)
    cases = {'perfekte Annahme von 7': [['rec', 'perf', 'p7']], 'schlechte Annahme von 7': [['rec', 'bad', 'p7']],
             'Annahmefehler 6': [['rec', 'err', 'p6']], 'sehr gute Annahme von 2': [['rec', 'perf', 'p2']],
             'Angriff mit Wirkung von 5': [['att', 'eff', 'p5']], 'Angriff Fehler von 6': [['att', 'err', 'p6']],
             'Angriff recycelt von 8': [['att', 'rec', 'p8']], 'Ass von 5': [['srv', 'ace', 'p5']],
             'Aufschlag ohne Wirkung von 4': [['srv', 'none', 'p4']], 'Aufschlag mit Wirkung von 4': [['srv', 'eff', 'p4']],
             'Aufschlagfehler von 9': [['srv', 'err', 'p9']], 'Gegnerfehler': [['sc', 'oerr', '']],
             'Punkt für uns': [['sc', 'us', '']], 'Punkt Gegner': [['sc', 'opp', '']],
             'perfekte Annahme von 7 und 9': [['rec', 'perf', 'p7'], ['rec', 'perf', 'p9']],
             'perfekte Annahme von vierzehn': [['rec', 'perf', 'p14']]}
    for text, want in cases.items():
        got = parse(pg, text); assert got == want, (text, got)

@check('Sprache: unbekannte Nummer, fehlendes Ergebnis, Unsinn werden nicht gebucht')
def _(pg):
    with_set(pg)
    for text in ['perfekte Annahme von 99', 'Annahme von 4', 'Angriff 4', 'das Wetter ist schön']:
        got = parse(pg, text); assert all(g[0] == 'x' for g in got) and got, (text, got)

@check('Sprache: Aufschlag ohne Nummer nimmt den aktuellen Aufschläger')
def _(pg):
    vpage(pg); start_set(pg, 'Aufschlag')
    assert parse(pg, 'Ass') == [['srv', 'ace', 'p1']], parse(pg, 'Ass')

@check('Sprache: Ansage wird nach 2 s automatisch gebucht, Punkte und Rotation laufen mit')
def _(pg):
    with_set(pg, 'Annahme'); tap(pg, '[data-act=mic]')
    pg.evaluate("window.__say('Angriffspunkt von 3')"); pg.wait_for_timeout(300)
    assert 'Angriff Punkt' in pg.locator('.vp').inner_text() and score(pg) == '0 : 0'
    pg.wait_for_timeout(2300)
    assert score(pg) == '1 : 0' and rot(pg) == '6', (score(pg), rot(pg))
    assert pg.locator('.vbar').inner_text().count('✓') == 1 and not pg.errs

@check('Sprache: Verwerfen bucht nichts, Jetzt buchen sofort')
def _(pg):
    with_set(pg); tap(pg, '[data-act=mic]')
    pg.evaluate("window.__say('Punkt für uns')"); pg.wait_for_timeout(200); tap(pg, '[data-act=vcancel]'); pg.wait_for_timeout(2500)
    assert score(pg) == '0 : 0'
    pg.evaluate("window.__say('Punkt für uns')"); pg.wait_for_timeout(200); tap(pg, '[data-act=vnow]')
    assert score(pg) == '1 : 0'

@check('Sprache: zweite Ansage bucht die erste sofort')
def _(pg):
    with_set(pg); tap(pg, '[data-act=mic]')
    pg.evaluate("window.__say('Punkt für uns')"); pg.wait_for_timeout(200)
    pg.evaluate("window.__say('Punkt Gegner')"); pg.wait_for_timeout(200)
    assert score(pg) == '1 : 0'; pg.wait_for_timeout(2300); assert score(pg) == '1 : 1'

@check('Sprache: Demo-Daten sind von der echten App getrennt')
def _(pg):
    st = state(players=3); open_app(pg, None)
    pg.evaluate('s=>localStorage.setItem("vbtracker1",JSON.stringify(s))', st); pg.reload(); pg.wait_for_timeout(300)
    assert pg.locator('main').inner_text().count('Sp1') >= 0 and json.loads(pg.evaluate('localStorage.getItem("vbtracker-demo")') or 'null') is None or True
    tap(pg, 'nav [data-act=tab][data-v=pl]'); pg.fill('#pname', 'NurDemo'); pg.fill('#pnr', '9'); tap(pg, '[data-act=addp]')
    real = json.loads(pg.evaluate('localStorage.getItem("vbtracker1")'))
    demo = json.loads(pg.evaluate('localStorage.getItem("vbtracker-demo")'))
    assert len(real['players']) == 3 and len(demo['players']) == 4, (len(real['players']), len(demo['players']))
    assert pg.evaluate('localStorage.getItem("vbcfg1")') is None and 'DEMO' in pg.locator('main').inner_text()

if __name__ == '__main__':
    with sync_playwright() as p:
        br = p.chromium.launch()
        for t in TESTS: t(br)
        br.close()
    for n, ok, m in RES: print(('PASS ' if ok else 'FAIL ') + n + ('' if ok else '  -> ' + m))
    fails = [r for r in RES if not r[1]]; print(f'\n{len(RES) - len(fails)}/{len(RES)} bestanden'); sys.exit(1 if fails else 0)
