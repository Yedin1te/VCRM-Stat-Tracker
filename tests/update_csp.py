# Aktualisiert den Hash der Content-Security-Policy. Nach jeder Änderung am JavaScript in index.html ausführen:
#   python3 update_csp.py
import re, hashlib, base64, sys
p = sys.argv[1] if len(sys.argv) > 1 else 'index.html'
t = open(p, encoding='utf-8').read()
js = re.search(r'<script>(.*?)</script>', t, re.S).group(1)
h = 'sha256-' + base64.b64encode(hashlib.sha256(js.encode('utf-8')).digest()).decode()
t = re.sub(r"script-src '[^']*'", lambda m: "script-src '" + h + "'", t, count=1)
open(p, 'w', encoding='utf-8').write(t)
print('CSP-Hash gesetzt:', h)
