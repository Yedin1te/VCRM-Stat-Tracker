// Volleyball-Tracker: Speicher in einer Google Tabelle
// Einfuegen unter: Tabelle > Erweiterungen > Apps Script
// WICHTIG: Ein langes, zufaelliges PASSWORT setzen (mind. 12 Zeichen). Ohne das lehnt das Skript alle Anfragen ab.

const PASSWORT = 'bitte-aendern'; // dasselbe Passwort in der App eintragen

const VERSION = 5; // Die App prüft diese Nummer und warnt, wenn das Skript veraltet ist
const MAX_OPS = 5000, MAX_BODY = 1500000, MAX_FAILS = 10, BLOCK_SECONDS = 900;
const HEAD = {
  Spieler: ['id', 'name', 'nr', 'rolle'],
  Spiele: ['id', 'gegner', 'datum'],
  Saetze: ['id', 'spiel_id', 'gegner', 'datum', 'start', 'laeufer', 'aufstellung', 'positionen', 'rollen'],
  Geloescht: ['id', 'art', 'zeit'], // Grabsteine: gelöschte Datensätze, damit ein altes Gerät sie nicht wieder hochlädt
  Ereignisse: ['id', 'satz_id', 'spieler_id', 'datum', 'gegner', 'satz', 'spieler', 'nr', 'bereich', 'ergebnis', 'laeufer', 'zeit']
};
const ERGEBNISSE = {
  Annahme: ['Fehler', 'Schlecht', 'Ok', 'Perfekt'],
  Angriff: ['Fehler', 'Recycle', 'Wirkung', 'Punkt', 'Block'],
  Aufschlag: ['Fehler', 'Ohne Wirkung', 'Wirkung', 'Ass'],
  Spielstand: ['Punkt Gegner', 'Gegnerfehler', 'Punkt wir', 'Korrektur wir +1', 'Korrektur wir -1', 'Korrektur Gegner +1', 'Korrektur Gegner -1', 'Aufschlag tauschen']
};

// ---------- Hilfsfunktionen ----------
function tab_(n) {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  let s = ss.getSheetByName(n);
  if (!s) {
    s = ss.insertSheet(n);
    s.appendRow(HEAD[n]);
    s.setFrozenRows(1);
    s.getRange(1, 1, s.getMaxRows(), HEAD[n].length).setNumberFormat('@');
    s.getRange(1, 1, 1, HEAD[n].length).setFontWeight('bold');
  } else if (s.getLastColumn() < HEAD[n].length) {
    s.getRange(1, 1, 1, HEAD[n].length).setValues([HEAD[n]]); // aeltere Tabelle: neue Spaltenueberschrift ergaenzen
  }
  return s;
}

// Schutz vor Formel-Injektion: Texte, die mit = + - @ beginnen, bekommen ein Hochkomma vorangestellt
function safe_(v) { v = String(v); return /^[=+\-@\t\r]/.test(v) ? "'" + v : v; }
function unsafe_(v) { v = String(v); return /^'[=+\-@\t\r]/.test(v) ? v.slice(1) : v; }

function rows_(n) {
  return tab_(n).getDataRange().getValues().slice(1).map(r => r.map(x => unsafe_(x)));
}

function out_(o) {
  return ContentService.createTextOutput(JSON.stringify(o)).setMimeType(ContentService.MimeType.JSON);
}

function doGet() {
  return ContentService.createTextOutput('Volleyball-Tracker laeuft.');
}

// ---------- Pruefung der Eingaben ----------
const ROLLEN = ['MB', 'AA', 'DI', 'ZP', 'LI']; // Mittelblocker, Aussen, Diagonal, Zuspieler, Libero
const role_ = v => ROLLEN.indexOf(v) >= 0 ? v : '';
const ID_RE = /^[A-Za-z0-9][A-Za-z0-9_-]{0,39}$/;
const okid_ = v => typeof v === 'string' && ID_RE.test(v);
const str_ = (v, n) => (typeof v === 'string' ? v : typeof v === 'number' && isFinite(v) ? String(v) : '').slice(0, n);
const day_ = v => typeof v === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(v) ? v : '';
const int_ = (v, a, b) => { v = Number(v); return Number.isInteger(v) && v >= a && v <= b ? v : null; };
const ids_list_ = a => Array.isArray(a) && a.length <= 20 && a.every(okid_) ? a : null;
// Rollen pro Satz: { spielerId: 'MB' | 'AA' | 'DI' | 'ZP' | 'LI' | '' }
const rl_ = o => {
  if (o === undefined) return {};
  if (!o || typeof o !== 'object' || Array.isArray(o)) return null;
  const k = Object.keys(o);
  if (k.length > 20) return null;
  for (const x of k) if (!okid_(x) || (o[x] !== '' && ROLLEN.indexOf(o[x]) < 0)) return null;
  return o;
};
const rlStr_ = o => Object.keys(o).map(k => k + ':' + o[k]).join(',');
const rlParse_ = s => { const o = {}; String(s || '').split(',').forEach(p => { const i = p.indexOf(':'); if (i > 0) o[p.slice(0, i)] = p.slice(i + 1); }); return o; };
const pos_ = a => Array.isArray(a) && a.length <= 6 && a.every(x => x === '' || okid_(x)) ? a : null;

// Gibt eine bereinigte Operation zurueck oder null, wenn sie ungueltig ist
function clean_(o) {
  if (!o || typeof o !== 'object') return null;
  const k = o.k;
  if (k === 'p+') {
    const p = o.p; if (!p || !okid_(p.id)) return null;
    return { k, row: [p.id, str_(p.name, 40), str_(p.nr, 3), role_(p.role)] };
  }
  if (k === 'p~') {
    return okid_(o.id) ? { k, id: o.id, role: role_(o.role) } : null;
  }
  if (k === 'p-' || k === 'e-') return okid_(o.id) ? { k, id: o.id } : null;
  if (k === 'g+') {
    const g = o.g; if (!g || !okid_(g.id) || !day_(g.date)) return null;
    return { k, row: [g.id, str_(g.opp, 40), g.date] };
  }
  if (k === 's+') {
    const s = o.s, rot = s && int_(s.rot, 1, 6), act = s && ids_list_(s.act), pos = s && (s.pos === undefined ? [] : pos_(s.pos)), rl = s && rl_(s.rl);
    if (!s || !okid_(s.id) || !okid_(s.gid) || !day_(s.date) || !rot || !act || !pos || !rl || (s.serve !== 'Aufschlag' && s.serve !== 'Annahme')) return null;
    return { k, row: [s.id, s.gid, str_(s.opp, 40), s.date, s.serve, rot, act.join(','), pos.join(','), rlStr_(rl)] };
  }
  if (k === 'g-' || k === 's-') return okid_(o.id) ? { k, id: o.id } : null;
  if (k === 's~') {
    const rot = int_(o.rot, 1, 6), act = ids_list_(o.act), pos = o.pos === undefined ? undefined : pos_(o.pos), rl = o.rl === undefined ? undefined : rl_(o.rl);
    return okid_(o.id) && rot && act && pos !== null && rl !== null ? { k, id: o.id, rot, act, pos, rl } : null;
  }
  if (k === 'e+') {
    const e = o.e, x = o.x;
    if (!e || !x || !okid_(o.sid) || !okid_(e.id) || !(e.p === '' || okid_(e.p))) return null;
    if (!Object.prototype.hasOwnProperty.call(ERGEBNISSE, x.bereich) || ERGEBNISSE[x.bereich].indexOf(x.ergebnis) < 0) return null;
    const rot = int_(e.rot, 1, 6), satz = int_(x.satz, 1, 99), t = Number(e.t);
    if (!rot || !satz || !isFinite(t) || !day_(x.datum)) return null;
    return { k, row: [e.id, o.sid, e.p, x.datum, str_(x.gegner, 40), satz, str_(x.spieler, 40), str_(x.nr, 3), x.bereich, x.ergebnis, rot, Math.floor(t)] };
  }
  return null;
}

// ---------- Anmeldung ----------
function pwOk_(given) {
  if (typeof given !== 'string') return false;
  let d = given.length ^ PASSWORT.length; // Vergleich ohne vorzeitigen Abbruch
  for (let i = 0; i < Math.max(given.length, PASSWORT.length); i++) d |= (given.charCodeAt(i) || 0) ^ (PASSWORT.charCodeAt(i) || 0);
  return d === 0;
}
const fails_ = () => Number(CacheService.getScriptCache().get('fails') || 0);
const addFail_ = () => CacheService.getScriptCache().put('fails', String(fails_() + 1), BLOCK_SECONDS);

function doPost(e) {
  try {
    if (PASSWORT === 'bitte-aendern' || PASSWORT.length < 12) return out_({ error: 'Server nicht eingerichtet: bitte ein langes PASSWORT (mind. 12 Zeichen) setzen' });
    if (fails_() >= MAX_FAILS) return out_({ error: 'Zu viele Fehlversuche. Bitte spaeter erneut versuchen' });
    const raw = e && e.postData && e.postData.contents;
    if (typeof raw !== 'string' || raw.length > MAX_BODY) return out_({ error: 'Ungueltige Anfrage' });
    let b; try { b = JSON.parse(raw); } catch (x) { return out_({ error: 'Ungueltige Anfrage' }); }
    if (!b || typeof b !== 'object' || !pwOk_(b.pw)) { addFail_(); return out_({ error: 'Falsches Passwort' }); }
    const ops = Array.isArray(b.ops) ? b.ops : [];
    if (ops.length > MAX_OPS) return out_({ error: 'Zu viele Operationen' });
    const lock = LockService.getScriptLock();
    lock.waitLock(25000);
    try {
      const ctx = { ids: {}, add: {} };
      let skipped = 0;
      ops.forEach(o => { const c = clean_(o); if (c) apply_(c, ctx); else skipped++; });
      flush_(ctx);
      const st = state_(); st.skipped = skipped;
      return out_(st);
    } finally { lock.releaseLock(); }
  } catch (err) {
    console.error(err); // Details nur im Protokoll, nie an den Aufrufer
    return out_({ error: 'Serverfehler' });
  }
}

// ---------- Schreiben ----------
function ids_(n, ctx) {
  if (!ctx.ids[n]) {
    const s = tab_(n), l = s.getLastRow();
    ctx.ids[n] = l > 1 ? s.getRange(2, 1, l - 1, 1).getValues().map(r => String(r[0])) : [];
  }
  return ctx.ids[n];
}

// Grabsteine für gelöschte Datensätze
function dead_(ctx) {
  if (!ctx.dead) {
    ctx.dead = Object.create(null); ctx.newDead = [];
    const s = tab_('Geloescht'), l = s.getLastRow();
    if (l > 1) s.getRange(2, 1, l - 1, 1).getValues().forEach(x => { ctx.dead[String(x[0])] = 1; });
  }
  return ctx.dead;
}
function bury_(ids, art, ctx) {
  const d = dead_(ctx);
  ids.forEach(id => { id = String(id); if (!d[id]) { d[id] = 1; ctx.newDead.push([id, art, String(Date.now())]); } });
}

function add_(n, row, ctx) {
  const dead = dead_(ctx);
  if (dead[String(row[0])]) return;                        // wurde gelöscht
  if (n === 'Saetze' && dead[String(row[1])]) return;      // zugehöriges Spiel wurde gelöscht
  if (n === 'Ereignisse' && dead[String(row[1])]) return;  // zugehöriger Satz wurde gelöscht
  const ids = ids_(n, ctx);
  if (ids.indexOf(String(row[0])) >= 0) return; // schon vorhanden
  ids.push(String(row[0]));
  (ctx.add[n] = ctx.add[n] || []).push(row.map(safe_));
}

function flush_(ctx) {
  Object.keys(ctx.add).forEach(n => {
    const rows = ctx.add[n], s = tab_(n);
    if (rows.length) s.getRange(s.getLastRow() + 1, 1, rows.length, rows[0].length).setValues(rows);
  });
  ctx.add = {};
  if (ctx.newDead && ctx.newDead.length) {
    const s = tab_('Geloescht');
    s.getRange(s.getLastRow() + 1, 1, ctx.newDead.length, 3).setValues(ctx.newDead);
    ctx.newDead = [];
  }
}

// Entfernt Zeilen, fuer die keep() false liefert (Tabelle wird neu geschrieben, das ist bei vielen Zeilen schneller als einzelnes Loeschen)
function purge_(n, keep, ctx) {
  const s = tab_(n), cols = HEAD[n].length, body = s.getDataRange().getValues().slice(1);
  const kept = body.filter(x => keep(x.map(String)));
  if (kept.length === body.length) return;
  if (body.length) s.getRange(2, 1, body.length, cols).clearContent();
  if (kept.length) s.getRange(2, 1, kept.length, cols).setValues(kept.map(x => { const y = x.slice(0, cols); while (y.length < cols) y.push(''); return y; }));
  delete ctx.ids[n];
}

function apply_(o, ctx) {
  if (o.k === 'p+') add_('Spieler', o.row, ctx);
  else if (o.k === 'g+') add_('Spiele', o.row, ctx);
  else if (o.k === 's+') add_('Saetze', o.row, ctx);
  else if (o.k === 'e+') add_('Ereignisse', o.row, ctx);
  else if (o.k === 's~') {
    flush_(ctx);
    const i = ids_('Saetze', ctx).indexOf(o.id);
    if (i >= 0) {
      const sh = tab_('Saetze');
      sh.getRange(i + 2, 6, 1, 2).setValues([[String(o.rot), o.act.join(',')]]);
      if (o.pos !== undefined) sh.getRange(i + 2, 8, 1, 1).setValues([[safe_(o.pos.join(','))]]);
      if (o.rl !== undefined) sh.getRange(i + 2, 9, 1, 1).setValues([[safe_(rlStr_(o.rl))]]);
    }
  } else if (o.k === 's-' || o.k === 'g-') {
    flush_(ctx);
    if (o.k === 'g-') {
      const setIds = rows_('Saetze').filter(x => x[1] === o.id).map(x => x[0]);
      bury_([o.id].concat(setIds), 'Spiel', ctx);
      purge_('Ereignisse', x => setIds.indexOf(String(x[1])) < 0, ctx);
      purge_('Saetze', x => String(x[1]) !== o.id, ctx);
      purge_('Spiele', x => String(x[0]) !== o.id, ctx);
    } else {
      bury_([o.id], 'Satz', ctx);
      purge_('Ereignisse', x => String(x[1]) !== o.id, ctx);
      purge_('Saetze', x => String(x[0]) !== o.id, ctx);
    }
  } else if (o.k === 'p~') {
    flush_(ctx);
    const i = ids_('Spieler', ctx).indexOf(o.id);
    if (i >= 0) tab_('Spieler').getRange(i + 2, 4, 1, 1).setValues([[o.role]]);
  } else if (o.k === 'p-' || o.k === 'e-') {
    flush_(ctx);
    const n = o.k === 'p-' ? 'Spieler' : 'Ereignisse', ids = ids_(n, ctx), i = ids.lastIndexOf(o.id);
    bury_([o.id], n, ctx);
    if (i >= 0) { tab_(n).deleteRow(i + 2); ids.splice(i, 1); }
  }
}

// ---------- Lesen ----------
function state_() {
  return {
    ver: VERSION,
    players: rows_('Spieler').map(r => ({ id: r[0], name: r[1], nr: r[2], role: r[3] || '' })),
    games: rows_('Spiele').map(r => ({ id: r[0], opp: r[1], date: r[2] })),
    sets: rows_('Saetze').map(r => ({ id: r[0], gid: r[1], opp: r[2], date: r[3], serve: r[4], rot: Number(r[5]) || 1, act: r[6] ? r[6].split(',') : [], pos: r[7] ? r[7].split(',') : [], rl: rlParse_(r[8]) })),
    events: rows_('Ereignisse').map(r => ({ id: r[0], sid: r[1], p: r[2], bereich: r[8], ergebnis: r[9], rot: Number(r[10]) || 1, t: Number(r[11]) || 0 }))
  };
}
