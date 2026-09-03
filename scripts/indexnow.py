#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""TransferBeat - indexnow.py: segnala a IndexNow (Bing, Yandex, Seznam, Naver; Google non aderisce) le URL cambiate (kb/SEO.md §3.6).
La chiave e' nel file indexnow-<chiave>.txt nella root del sito (pubblica per protocollo: il motore la legge da transferbeat.com).
Uso: python scripts/indexnow.py                  URL dei file cambiati fra HEAD~1 e HEAD (dopo un push da update.yml)
     python scripts/indexnow.py <da> <a>         fra due commit (pubblica.sh passa origin/main prima del push e HEAD)
     python scripts/indexnow.py --urls URL...    URL esplicite
     INDEXNOW_DRY=1 stampa e non invia. Esce SEMPRE con 0: non deve mai bloccare un push."""
import glob, os, re, subprocess, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITE = "https://transferbeat.com"
HOST = "transferbeat.com"
SERVED = re.compile(r"^(index\.html|[a-z0-9-]+\.html|articoli/[a-z]{2}/[^/]+\.html|squadre/[^/]+\.html|campionati/[^/]+\.html|fantacalcio/[^/]+\.html|"
                    r"fanta/index\.html|llms\.txt|sitemap[a-z-]*\.xml|data/fanta/[^/]+\.json)$")

def key():
    for p in glob.glob(os.path.join(ROOT, "indexnow-*.txt")):
        k = open(p, encoding="utf-8").read().strip()
        if re.match(r"^[a-f0-9]{16,64}$", k):
            return k, os.path.basename(p)
    return None, None

def url_of(path):
    path = path.replace("\\", "/")
    if not SERVED.match(path):
        return None
    if path == "index.html":
        return SITE + "/"
    if path.endswith("/index.html"):
        return SITE + "/" + path[:-len("index.html")]
    return SITE + "/" + path

def changed(a, b):
    try:
        out = subprocess.run(["git", "diff", "--name-only", a, b], cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60)
        return [l.strip() for l in out.stdout.splitlines() if l.strip()]
    except Exception as e:
        print("indexnow: git diff fallito:", str(e)[:120]); return []

def main():
    args = sys.argv[1:]
    if args and args[0] == "--urls":
        urls = args[1:]
    else:
        a, b = (args + ["HEAD~1", "HEAD"])[:2] if len(args) >= 2 else ("HEAD~1", "HEAD")
        if len(args) == 1:
            a, b = args[0], "HEAD"
        if not a:
            a = "HEAD~1"
        urls = [u for u in (url_of(p) for p in changed(a, b)) if u]
    urls = list(dict.fromkeys(urls))[:10000]
    if not urls:
        print("indexnow: nessuna URL pubblica cambiata"); return
    k, fname = key()
    print("indexnow: %d URL" % len(urls) + ("" if k else " (nessuna chiave indexnow-*.txt: non invio)"))
    if not k or os.environ.get("INDEXNOW_DRY"):
        for u in urls[:20]:
            print("  ", u)
        return
    try:
        import requests
        r = requests.post("https://api.indexnow.org/indexnow", json={"host": HOST, "key": k, "keyLocation": SITE + "/" + fname, "urlList": urls},
                          headers={"Content-Type": "application/json; charset=utf-8"}, timeout=20)
        print("indexnow: HTTP", r.status_code, (r.text or "")[:120].replace("\n", " "))
    except Exception as e:
        print("indexnow: invio fallito:", str(e)[:120])

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print("indexnow: errore:", str(e)[:120])
    sys.exit(0)
