// Startet das nachgebaute Google-Skript als lokalen Server für Sync-Tests. Start: node tests/gas_server.js 8765
const http = require('http'), fs = require('fs'), path = require('path'), { makeEnv } = require('./gas_mock');
const PW = 'sync-test-passwort-123';
const SRC = fs.readFileSync(path.join(__dirname, '..', 'Code.gs'), 'utf8').replace("'bitte-aendern'", `'${PW}'`);
const OLD = process.argv[3] === 'old';   // simuliert ein veraltetes Skript: keine Versionsnummer, Löschen wird nicht verstanden
const CODE = OLD ? SRC.replace("if (k === 'g-' || k === 's-') return okid_(o.id) ? { k, id: o.id } : null;", '').replace('ver: VERSION,', '') : SRC;
let env = makeEnv(CODE);
http.createServer((req, res) => {
  let b = ''; req.on('data', d => b += d);
  req.on('end', () => {
    if (req.url.startsWith('/reset')) { env = makeEnv(CODE); return res.end('ok'); }
    res.setHeader('content-type', 'application/json'); res.end(JSON.stringify(env.post(b)));
  });
}).listen(+process.argv[2] || 8765, '127.0.0.1');
