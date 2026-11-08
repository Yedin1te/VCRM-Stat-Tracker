// Tests fuer Code.gs mit einer Mini-Nachbildung von Google Sheets. Start: node tests/gas.test.js
const fs = require('fs'), vm = require('vm'), path = require('path'), assert = require('assert');
const SRC = fs.readFileSync(path.join(__dirname, '..', 'Code.gs'), 'utf8');
const PW = 'ein-langes-test-passwort';

const { makeEnv } = require('./gas_mock');
const good = () => makeEnv(SRC.replace("'bitte-aendern'", `'${PW}'`));
const P = (id, name = 'Anna', nr = '7') => ({ k: 'p+', p: { id, name, nr } });
const EV = (id, extra = {}) => ({ k: 'e+', sid: 's1', e: { id, p: 'p1', rot: 1, t: 5 }, x: { datum: '2026-01-01', gegner: 'X', satz: 1, spieler: 'Anna', nr: '7', bereich: 'Annahme', ergebnis: 'Perfekt', ...extra } });

const tests = [];
const t = (n, f) => tests.push([n, f]);

t('Standard-Passwort wird abgelehnt', () => { const e = makeEnv(SRC); assert(/nicht eingerichtet/.test(e.post({ pw: 'bitte-aendern', ops: [] }).error)); });
t('Kurzes Passwort wird abgelehnt', () => { const e = makeEnv(SRC.replace("'bitte-aendern'", "'kurz'")); assert(e.post({ pw: 'kurz', ops: [] }).error); });
t('Falsches/fehlendes Passwort wird abgelehnt, nichts gespeichert', () => {
  const e = good();
  for (const pw of ['falsch', '', undefined, null, 123, [PW], { a: 1 }]) assert.strictEqual(e.post({ pw, ops: [P('p1')] }).error, 'Falsches Passwort');
  assert(!e.sheets.Spieler || e.sheets.Spieler.rows.length <= 1);
});
t('Brute-Force-Sperre nach 10 Fehlversuchen (auch mit richtigem Passwort)', () => {
  const e = good();
  for (let i = 0; i < 10; i++) e.post({ pw: 'x' + i, ops: [] });
  assert(/Zu viele Fehlversuche/.test(e.post({ pw: PW, ops: [] }).error));
});
t('Kaputte Anfragen liefern kontrollierte Fehler ohne Details', () => {
  const e = good();
  for (const body of ['{kaputt', 'null', '[]', '"x"', '']) { const r = e.post(body); assert(r.error && !/at |Error|stack/i.test(r.error), body + ' -> ' + JSON.stringify(r)); }
  assert(good().ctx.doPost({}).getContent().includes('error'));
});
t('Gueltige Operationen werden gespeichert und ausgeliefert', () => {
  const e = good();
  const r = e.post({ pw: PW, ops: [P('p1'), { k: 'g+', g: { id: 'g1', opp: 'Gegner', date: '2026-01-01' } },
    { k: 's+', s: { id: 's1', gid: 'g1', opp: 'Gegner', date: '2026-01-01', serve: 'Annahme', rot: 1, act: ['p1'] } }, EV('e1')] });
  assert.strictEqual(r.players[0].name, 'Anna'); assert.strictEqual(r.sets[0].act[0], 'p1');
  assert.strictEqual(r.events[0].ergebnis, 'Perfekt'); assert.strictEqual(r.skipped, 0);
});
t('Doppelte Operationen sind idempotent', () => { const e = good(); e.post({ pw: PW, ops: [P('p1'), EV('e1')] }); const r = e.post({ pw: PW, ops: [P('p1'), EV('e1')] }); assert.strictEqual(r.players.length, 1); assert.strictEqual(r.events.length, 1); });
t('Aendern und Loeschen funktionieren', () => {
  const e = good();
  e.post({ pw: PW, ops: [P('p1'), P('p2', 'Ben', '8'), { k: 's+', s: { id: 's1', gid: 'g1', opp: 'G', date: '2026-01-01', serve: 'Annahme', rot: 1, act: ['p1'] } }, EV('e1'), EV('e2')] });
  const r = e.post({ pw: PW, ops: [{ k: 's~', id: 's1', rot: 4, act: ['p1', 'p2'] }, { k: 'e-', id: 'e1' }, { k: 'p-', id: 'p1' }] });
  assert.strictEqual(r.sets[0].rot, 4); assert.deepStrictEqual(r.sets[0].act, ['p1', 'p2']);
  assert.deepStrictEqual(r.events.map(x => x.id), ['e2']); assert.deepStrictEqual(r.players.map(x => x.id), ['p2']);
});
t('Ungueltige Operationen werden uebersprungen (Typen, IDs, Bereiche, Grenzen)', () => {
  const e = good();
  const bad = [null, 5, 'x', { k: 'drop' }, { k: '__proto__' }, P('<img>'), P('__proto__'), P('a b'), P('x'.repeat(41)), { k: 'p+', p: null },
    EV('e9', { bereich: '__proto__' }), EV('e9', { ergebnis: 'Zauberei' }), EV('e9', { satz: 'a' }), EV('e9', { datum: '1.1.2026' }),
    { k: 's+', s: { id: 's1', gid: 'g1', date: '2026-01-01', serve: 'X', rot: 1, act: [] } },
    { k: 's+', s: { id: 's1', gid: 'g1', date: '2026-01-01', serve: 'Annahme', rot: 9, act: [] } },
    { k: 's~', id: 's1', rot: 1, act: new Array(50).fill('a') }];
  const r = e.post({ pw: PW, ops: bad });
  assert.strictEqual(r.skipped, bad.length); assert.strictEqual(r.players.length + r.events.length + r.sets.length, 0);
});
t('Zu viele Operationen / zu grosser Body werden abgelehnt', () => {
  const e = good();
  assert(e.post({ pw: PW, ops: new Array(5001).fill(P('p1')) }).error);
  assert(e.post(JSON.stringify({ pw: PW, ops: [], pad: 'x'.repeat(1600000) })).error);
});
t('Formel-Injektion wird neutralisiert und kommt unveraendert zurueck', () => {
  const e = good();
  const names = ['=HYPERLINK("http://evil","x")', '+1+1', '-2+3', '@SUM(A1)', 'Normal'];
  const r = e.post({ pw: PW, ops: names.map((n, i) => P('p' + (i + 1), n, '1')) });
  assert.deepStrictEqual(r.players.map(p => p.name), names);
  for (const row of e.sheets.Spieler.rows.slice(1)) assert(!/^[=+\-@]/.test(row[1]), 'Zelle beginnt mit Formelzeichen: ' + row[1]);
});
t('Lange Texte werden gekuerzt', () => { const e = good(); const r = e.post({ pw: PW, ops: [P('p1', 'A'.repeat(500), '123456')] }); assert.strictEqual(r.players[0].name.length, 40); assert.strictEqual(r.players[0].nr.length, 3); });
t('Prototype-Pollution-Versuche haben keine Wirkung', () => {
  const e = good(); e.post('{"pw":"' + PW + '","__proto__":{"polluted":1},"ops":[{"k":"p+","p":{"id":"p1","name":"x","nr":"1","__proto__":{"polluted":2}}}]}');
  assert.strictEqual(({}).polluted, undefined);
});

t('Aufstellung (Positionen) wird gespeichert, geaendert und ausgeliefert', () => {
  const e = good();
  const pos = ['p1', 'p2', 'p3', 'p4', 'p5', 'p6'];
  e.post({ pw: PW, ops: [{ k: 's+', s: { id: 's1', gid: 'g1', opp: 'G', date: '2026-01-01', serve: 'Annahme', rot: 1, act: pos, pos } }] });
  let r = e.post({ pw: PW, ops: [{ k: 's~', id: 's1', rot: 6, act: pos, pos: ['p2', 'p3', 'p4', 'p5', 'p6', 'p1'] }] });
  assert.deepStrictEqual(r.sets[0].pos, ['p2', 'p3', 'p4', 'p5', 'p6', 'p1']); assert.strictEqual(r.sets[0].rot, 6);
  r = e.post({ pw: PW, ops: [{ k: 's~', id: 's1', rot: 5, act: pos }] }); // ohne pos: Aufstellung bleibt
  assert.deepStrictEqual(r.sets[0].pos, ['p2', 'p3', 'p4', 'p5', 'p6', 'p1']); assert.strictEqual(r.sets[0].rot, 5);
});
t('Ungueltige Aufstellungen werden abgelehnt', () => {
  const e = good(), s = { id: 's1', gid: 'g1', opp: 'G', date: '2026-01-01', serve: 'Annahme', rot: 1, act: [] };
  const r = e.post({ pw: PW, ops: [{ k: 's+', s: { ...s, pos: ['<img>', 'p1'] } }, { k: 's+', s: { ...s, pos: new Array(7).fill('p1') } }, { k: 's+', s: { ...s, pos: 'p1' } }] });
  assert.strictEqual(r.skipped, 3); assert.strictEqual(r.sets.length, 0);
});
t('Aeltere Tabelle ohne Spalte "positionen" wird ergaenzt', () => {
  const e = good(); e.post({ pw: PW, ops: [] });
  e.sheets.Saetze.rows[0] = e.sheets.Saetze.rows[0].slice(0, 7);
  const r = e.post({ pw: PW, ops: [] });
  assert.strictEqual(e.sheets.Saetze.rows[0][7], 'positionen'); assert(r.sets);
});

t('Rolle wird gespeichert, geaendert, ungueltige Rollen werden leer', () => {
  const e = good();
  let r = e.post({ pw: PW, ops: [{ k: 'p+', p: { id: 'p1', name: 'A', nr: '1', role: 'MB' } }, { k: 'p+', p: { id: 'p2', name: 'B', nr: '2', role: '<b>' } }] });
  assert.strictEqual(r.players[0].role, 'MB'); assert.strictEqual(r.players[1].role, '');
  r = e.post({ pw: PW, ops: [{ k: 'p~', id: 'p2', role: 'LI' }, { k: 'p~', id: 'p1', role: 'x"' }, { k: 'p~', id: '<x>', role: 'AA' }] });
  assert.strictEqual(r.players[1].role, 'LI'); assert.strictEqual(r.players[0].role, ''); assert.strictEqual(r.skipped, 1);
});
t('Aeltere Spieler-Tabelle ohne Spalte "rolle" wird ergaenzt', () => {
  const e = good(); e.post({ pw: PW, ops: [P('p1')] });
  e.sheets.Spieler.rows[0] = e.sheets.Spieler.rows[0].slice(0, 3); e.sheets.Spieler.rows[1] = e.sheets.Spieler.rows[1].slice(0, 3);
  const r = e.post({ pw: PW, ops: [{ k: 'p~', id: 'p1', role: 'DI' }] });
  assert.strictEqual(e.sheets.Spieler.rows[0][3], 'rolle'); assert.strictEqual(r.players[0].role, 'DI');
});

const SET = (id, gid = 'g1', extra = {}) => ({ k: 's+', s: { id, gid, opp: 'G', date: '2026-01-01', serve: 'Annahme', rot: 1, act: ['p1'], ...extra } });
const GM = id => ({ k: 'g+', g: { id, opp: 'G', date: '2026-01-01' } });
t('Satz loeschen entfernt Satz und seine Ereignisse, nicht die anderen', () => {
  const e = good();
  e.post({ pw: PW, ops: [P('p1'), GM('g1'), SET('s1'), SET('s2'), EV('e1'), { ...EV('e2'), sid: 's2' }, { ...EV('e3'), sid: 's2' }] });
  const r = e.post({ pw: PW, ops: [{ k: 's-', id: 's2' }] });
  assert.deepStrictEqual(r.sets.map(x => x.id), ['s1']); assert.deepStrictEqual(r.events.map(x => x.id), ['e1']);
  assert.strictEqual(r.games.length, 1); assert.strictEqual(r.players.length, 1);
});
t('Spiel loeschen entfernt Spiel, Saetze und Ereignisse, andere Spiele bleiben', () => {
  const e = good();
  e.post({ pw: PW, ops: [P('p1'), GM('g1'), GM('g2'), SET('s1', 'g1'), SET('s2', 'g1'), SET('s3', 'g2'), EV('e1'), { ...EV('e2'), sid: 's2' }, { ...EV('e3'), sid: 's3' }] });
  let r = e.post({ pw: PW, ops: [{ k: 'g-', id: 'g1' }] });
  assert.deepStrictEqual(r.games.map(x => x.id), ['g2']); assert.deepStrictEqual(r.sets.map(x => x.id), ['s3']); assert.deepStrictEqual(r.events.map(x => x.id), ['e3']);
  r = e.post({ pw: PW, ops: [{ ...EV('e9'), sid: 's3' }, { k: 'g-', id: 'gibtsnicht' }, { k: 'g-', id: '<x>' }] }); // danach weiter schreiben moeglich
  assert.strictEqual(r.events.length, 2); assert.strictEqual(r.skipped, 1);
  assert.strictEqual(e.sheets.Ereignisse.getLastRow(), 3);
});
t('Neue Ergebnisse: Block und Spielstand-Korrekturen werden akzeptiert', () => {
  const e = good(); e.post({ pw: PW, ops: [P('p1')] });
  const r = e.post({ pw: PW, ops: [EV('b1', { ergebnis: 'Block', bereich: 'Angriff' }), EV('k1', { bereich: 'Spielstand', ergebnis: 'Korrektur wir +1' }), EV('k2', { bereich: 'Spielstand', ergebnis: 'Aufschlag tauschen' }), EV('k3', { bereich: 'Spielstand', ergebnis: 'Korrektur Gegner -1' })] });
  assert.strictEqual(r.skipped, 0); assert.strictEqual(r.events.length, 4);
});
t('Satz-Rollen werden gespeichert, geaendert und validiert', () => {
  const e = good();
  let r = e.post({ pw: PW, ops: [SET('s1', 'g1', { rl: { p1: 'DI', p2: '' } })] });
  assert.deepStrictEqual(r.sets[0].rl, { p1: 'DI', p2: '' });
  r = e.post({ pw: PW, ops: [{ k: 's~', id: 's1', rot: 2, act: ['p1'], rl: { p1: 'LI' } }] });
  assert.deepStrictEqual(r.sets[0].rl, { p1: 'LI' }); assert.strictEqual(r.sets[0].rot, 2);
  r = e.post({ pw: PW, ops: [{ k: 's~', id: 's1', rot: 3, act: ['p1'] }] });          // ohne rl: bleibt
  assert.deepStrictEqual(r.sets[0].rl, { p1: 'LI' });
  r = e.post({ pw: PW, ops: [SET('s9', 'g1', { rl: { p1: '<b>' } }), SET('s8', 'g1', { rl: { '<x>': 'MB' } }), SET('s7', 'g1', { rl: 'x' })] });
  assert.strictEqual(r.skipped, 3); assert.strictEqual(r.sets.length, 1);
});

t('Gelöschtes bleibt gelöscht, auch wenn ein altes Gerät es erneut hochlädt', () => {
  const e = good(), adds = [P('p1'), GM('g1'), SET('s1', 'g1'), EV('e1')];
  e.post({ pw: PW, ops: adds });
  let r = e.post({ pw: PW, ops: [{ k: 'g-', id: 'g1' }] });
  assert.strictEqual(r.games.length + r.sets.length + r.events.length, 0);
  r = e.post({ pw: PW, ops: adds.concat([GM('g1'), SET('s9', 'g1'), { ...EV('e9'), sid: 's1' }]) });      // altes Handy lädt alles wieder hoch
  assert.deepStrictEqual([r.games.length, r.sets.length, r.events.length], [0, 0, 0], 'gelöschtes Spiel kam zurück');
  assert.strictEqual(r.players.length, 1);                                                                 // der Spieler wurde nicht gelöscht
  r = e.post({ pw: PW, ops: [GM('g2'), SET('s2', 'g2'), { ...EV('e2'), sid: 's2' }] });                      // Neues geht weiterhin
  assert.deepStrictEqual([r.games.length, r.sets.length, r.events.length], [1, 1, 1]);
});
t('Gelöschter Satz, Spieler und zurückgenommene Eingabe kommen nicht wieder', () => {
  const e = good(), s2ev = { ...EV('e2'), sid: 's2' };
  e.post({ pw: PW, ops: [P('p1'), P('p2', 'B', '8'), GM('g1'), SET('s1'), SET('s2'), EV('e1'), s2ev, EV('e3')] });
  let r = e.post({ pw: PW, ops: [{ k: 's-', id: 's2' }, { k: 'p-', id: 'p2' }, { k: 'e-', id: 'e3' }] });
  assert.deepStrictEqual(r.sets.map(x => x.id), ['s1']); assert.deepStrictEqual(r.players.map(x => x.id), ['p1']); assert.deepStrictEqual(r.events.map(x => x.id), ['e1']);
  r = e.post({ pw: PW, ops: [P('p2', 'B', '8'), SET('s2'), s2ev, EV('e3')] });
  assert.deepStrictEqual(r.sets.map(x => x.id), ['s1']); assert.deepStrictEqual(r.players.map(x => x.id), ['p1']); assert.deepStrictEqual(r.events.map(x => x.id), ['e1']);
});
t('Antwort enthält die Versionsnummer, IDs wie "constructor" sind keine Grabsteine', () => {
  const e = good(); let r = e.post({ pw: PW, ops: [P('constructor', 'X', '1'), P('toString', 'Y', '2')] });
  assert(r.ver >= 5); assert.strictEqual(r.players.length, 2);
});

t('Antwort nennt die gelöschten IDs', () => {
  const e = good(); e.post({ pw: PW, ops: [GM('g1'), SET('s1', 'g1')] });
  const r = e.post({ pw: PW, ops: [{ k: 'g-', id: 'g1' }] }); assert(r.dead.includes('g1') && r.dead.includes('s1'), r.dead);
});

t('Alte Beschriftungen (Ok, Recycle) werden angenommen und als Gut / Ohne Wirkung gespeichert', () => {
  const e = good(); e.post({ pw: PW, ops: [P('p1')] });
  const r = e.post({ pw: PW, ops: [EV('o1', { ergebnis: 'Ok' }), EV('o2', { bereich: 'Angriff', ergebnis: 'Recycle' }), EV('n1', { ergebnis: 'Gut' }), EV('n2', { bereich: 'Angriff', ergebnis: 'Ohne Wirkung' }), EV('bad', { ergebnis: 'Recycle' })] });
  assert.strictEqual(r.skipped, 1, 'Recycle bei Annahme ist ungültig');
  assert.deepStrictEqual(r.events.map(x => x.bereich + ':' + x.ergebnis), ['Annahme:Gut', 'Angriff:Ohne Wirkung', 'Annahme:Gut', 'Angriff:Ohne Wirkung']);
});
t('Bestehende Tabellenzeilen mit alten Beschriftungen werden einmalig umgestellt', () => {
  const e = good(), sh = e.ctx.tab_('Ereignisse');
  sh.appendRow(['x1', 's1', 'p1', '2026-01-01', 'G', '1', 'A', '1', 'Annahme', 'Ok', '1', '5']);
  sh.appendRow(['x2', 's1', 'p1', '2026-01-01', 'G', '1', 'A', '1', 'Angriff', 'Recycle', '1', '6']);
  sh.appendRow(['x3', 's1', 'p1', '2026-01-01', 'G', '1', 'A', '1', 'Angriff', 'Punkt', '1', '7']);
  let r = e.post({ pw: PW, ops: [] });
  assert.deepStrictEqual(r.events.map(x => x.ergebnis), ['Gut', 'Ohne Wirkung', 'Punkt']);
  assert.deepStrictEqual(sh.rows.slice(1).map(x => x[9]), ['Gut', 'Ohne Wirkung', 'Punkt'], 'Tabelle selbst wurde nicht umgestellt');
  r = e.post({ pw: PW, ops: [] }); assert.strictEqual(r.events.length, 3);
});
t('Versionsnummer ist 6', () => { assert.strictEqual(good().post({ pw: PW, ops: [] }).ver, 6); });

let fail = 0;
for (const [n, f] of tests) { try { f(); console.log('PASS ' + n); } catch (err) { fail++; console.log('FAIL ' + n + '\n     -> ' + String(err.message).split('\n')[0]); } }
console.log(`\n${tests.length - fail}/${tests.length} bestanden`); process.exit(fail ? 1 : 0);
