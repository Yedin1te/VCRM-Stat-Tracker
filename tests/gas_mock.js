// Mini-Nachbildung von Google Sheets/Apps Script für die Tests
const vm = require('vm');
function makeEnv(source) {
  class Sheet {
    constructor(n) { this.name = n; this.rows = []; }
    appendRow(r) { this.rows.push(r.slice()); } setFrozenRows() {} getMaxRows() { return this.rows.length + 100; }
    getLastRow() { let n = this.rows.length; while (n > 0 && this.rows[n - 1].every(x => x === '' || x === undefined)) n--; return n; } getLastColumn() { return this.rows[0] ? this.rows[0].length : 0; } deleteRow(i) { this.rows.splice(i - 1, 1); }
    getRange(r, c, nr = 1, nc = 1) {
      const sh = this;
      return { getValues: () => Array.from({ length: nr }, (_, i) => Array.from({ length: nc }, (_, j) => { const v = (sh.rows[r - 1 + i] || [])[c - 1 + j]; return v === undefined ? '' : v; })),
        setValues(v) { v.forEach((row, i) => { sh.rows[r - 1 + i] = sh.rows[r - 1 + i] || []; row.forEach((x, j) => sh.rows[r - 1 + i][c - 1 + j] = x); }); },
        setNumberFormat() { return this; }, setFontWeight() { return this; },
        clearContent() { for (let i = 0; i < nr; i++) for (let jx = 0; jx < nc; jx++) if (sh.rows[r - 1 + i]) sh.rows[r - 1 + i][c - 1 + jx] = ''; } };
    }
    getDataRange() { return this.getRange(1, 1, this.getLastRow(), this.rows[0] ? this.rows[0].length : 1); }
  }
  const sheets = {}, cache = {}, props = {};
  const ctx = vm.createContext({
    console: { error() {} },
    SpreadsheetApp: { getActiveSpreadsheet: () => ({ getSheetByName: n => sheets[n] || null, insertSheet: n => (sheets[n] = new Sheet(n)) }) },
    CacheService: { getScriptCache: () => ({ get: k => cache[k] || null, put: (k, v) => { cache[k] = v; } }) },
    PropertiesService: { getScriptProperties: () => ({ getProperty: k => (k in props ? props[k] : null), setProperty: (k, v) => { props[k] = v; } }) },
    LockService: { getScriptLock: () => ({ waitLock() {}, releaseLock() {} }) },
    ContentService: { MimeType: { JSON: 'json' }, createTextOutput: s => ({ s, setMimeType() { return this; }, getContent() { return this.s; } }) }
  });
  vm.runInContext(source, ctx);
  const post = b => JSON.parse(ctx.doPost({ postData: { contents: typeof b === 'string' ? b : JSON.stringify(b) } }).getContent());
  return { ctx, sheets, cache, post };
}

module.exports = { makeEnv };
