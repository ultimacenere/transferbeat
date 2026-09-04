#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""TransferBeat - seo_audit.py: verifica delle regole di kb/SEO.md §0 su tutte le pagine HTML del sito (sola lettura, nessuna rete).
Controlla title (<=60), description (<=155), canonical, hreflang, H1 unico, JSON-LD (validita' e tipi), breadcrumb, testo statico, link ?lang=,
entita' sfuggite (&lt;p&gt;), "undefined", img senza alt, og:image, e la coerenza fra pagine e sitemap (URL senza file, file senza URL, lastmod).
Uso: py -X utf8 scripts/seo_audit.py            (dalla radice del repo o da scripts/; stampa il rapporto, scrive seo_audit_rows.json accanto al rapporto)
Da lanciare dopo ogni modifica ai generatori (render_site, render_stats, render_articles) o alle hub: kb/SEO.md §4."""
import os, re, json, glob, sys, html
from collections import Counter, defaultdict
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); SITE = "https://transferbeat.com"
OUT = os.getcwd()
os.chdir(ROOT)
files = []
for pat in ["*.html","articoli/*/*.html","squadre/*.html","campionati/*.html","fantacalcio/*.html","giocatori/*.html","fanta/*.html"]:
    files += glob.glob(pat)
files = sorted(set(f.replace("\\","/") for f in files))
def url_of(p):
    if p == "index.html": return SITE + "/"
    if p.endswith("/index.html"): return SITE + "/" + p[:-10]
    return SITE + "/" + p
def first(pat, s):
    m = re.search(pat, s); return html.unescape(m.group(1).strip()) if m else ""
def text_of(h):
    h = re.sub(r"(?is)<(script|style|svg|noscript|template)[^>]*>.*?</\1>", " ", h)
    h = re.sub(r"(?s)<!--.*?-->", " ", h)
    h = re.sub(r"(?s)<[^>]+>", " ", h)
    return re.sub(r"\s+", " ", html.unescape(h)).strip()
def types(o, acc):
    if isinstance(o, dict):
        t = o.get("@type")
        if t: acc.extend(t if isinstance(t, list) else [t])
        for v in o.values(): types(v, acc)
    elif isinstance(o, list):
        for v in o: types(v, acc)
    return acc
def group(p):
    if p.startswith("articoli/"): return "articoli/" + p.split("/")[1]
    if "/" in p: return p.split("/")[0]
    return "root"
rows = {}
for f in files:
    h = open(f, encoding="utf-8", errors="replace").read()
    head, _, body = h.partition("</head>")
    r = {"grp": group(f), "url": url_of(f)}
    r["title"] = first(r"(?is)<title>(.*?)</title>", head)
    r["desc"] = first(r'(?is)<meta\s+name="description"\s+content="([^"]*)"', head) or first(r'(?is)<meta\s+content="([^"]*)"\s+name="description"', head)
    r["canonical"] = first(r'(?is)<link[^>]+rel="canonical"[^>]+href="([^"]+)"', head) or first(r'(?is)<link[^>]+href="([^"]+)"[^>]+rel="canonical"', head)
    r["hreflang"] = re.findall(r'(?is)<link[^>]+hreflang="([^"]+)"[^>]+href="([^"]+)"', head)
    r["robots"] = first(r'(?is)<meta\s+name="robots"\s+content="([^"]*)"', head)
    r["lang"] = first(r'(?is)<html[^>]*\blang="([^"]+)"', h)
    r["og_image"] = first(r'(?is)<meta[^>]+property="og:image"[^>]+content="([^"]+)"', head)
    r["og_title"] = first(r'(?is)<meta[^>]+property="og:title"[^>]+content="([^"]+)"', head)
    r["h1"] = re.findall(r"(?is)<h1[^>]*>(.*?)</h1>", body)
    r["h1txt"] = [text_of(x) for x in r["h1"]]
    r["text"] = len(text_of(body))
    lds, err = [], 0
    for s in re.findall(r'(?is)<script[^>]+type="application/ld\+json"[^>]*>(.*?)</script>', h):
        try: lds.append(json.loads(s))
        except Exception: err += 1
    r["ld_err"] = err; r["ld"] = lds; r["ld_types"] = sorted(set(types(lds, [])))
    r["author_person"] = any(isinstance(o, dict) and isinstance(o.get("author"), dict) and o["author"].get("@type") == "Person" and o["author"].get("url") for o in lds) or any(isinstance(o, dict) and isinstance(o.get("author"), list) and any(a.get("@type")=="Person" for a in o["author"]) for o in lds)
    r["founder"] = any("founder" in json.dumps(o) for o in lds)
    r["sameAs"] = any("sameAs" in json.dumps(o) for o in lds)
    hrefs = re.findall(r'(?is)href="([^"]+)"', body)
    r["lang_links"] = sum(1 for x in hrefs if "?lang=" in x)
    r["links"] = Counter()
    for x in hrefs:
        for k in ("squadre/","campionati/","giocatori/","articoli/","fantacalcio/","chi-siamo"):
            if k in x: r["links"][k] += 1
    r["ltp"] = h.count("&lt;p&gt;")
    r["undef"] = len(re.findall(r"\bundefined\b", text_of(body)))
    r["noalt"] = len([t for t in re.findall(r"(?is)<img\b[^>]*>", body) if "alt=" not in t])
    r["crumb_vis"] = bool(re.search(r'(?is)aria-label="breadcrumb"|class="[^"]*crumb', body))
    rows[f] = r
json.dump({k: {kk: (vv if kk != "ld" else None) for kk, vv in v.items()} for k, v in rows.items()}, open(os.path.join(OUT, "seo_audit_rows.json"), "w", encoding="utf-8"), ensure_ascii=False, default=lambda o: list(o) if isinstance(o, set) else dict(o))
# ---- sitemap
sm = {}; smfile = {}
for s in glob.glob("sitemap-*.xml"):
    x = open(s, encoding="utf-8").read()
    for loc, lm in re.findall(r"(?s)<url>\s*<loc>(.*?)</loc>\s*(?:<lastmod>(.*?)</lastmod>)?", x):
        sm[loc.strip()] = (lm or "").strip(); smfile[loc.strip()] = s
print("=== SITEMAP: %d URL in %d file" % (len(sm), len(glob.glob("sitemap-*.xml"))))
for s in sorted(glob.glob("sitemap-*.xml")):
    urls = [u for u, f in smfile.items() if f == s]
    c = Counter(sm[u][:10] for u in urls)
    print("  %-24s %4d URL  lastmod: %s" % (s, len(urls), ", ".join("%s x%d" % kv for kv in c.most_common(4))))
onsite = {rows[f]["url"] for f in rows}
missing_in_sm = sorted(u for u in onsite if u not in sm)
ghost = sorted(u for u in sm if u not in onsite and not u.endswith("/fanta/"))
print("  pagine HTML NON in sitemap: %d" % len(missing_in_sm)); [print("    -", u) for u in missing_in_sm[:25]]
print("  URL in sitemap SENZA file: %d" % len(ghost)); [print("    -", u) for u in ghost[:25]]
bad_lm = [u for u, lm in sm.items() if not re.match(r"^\d{4}-\d{2}-\d{2}", lm)]
print("  lastmod mancante/malformato: %d" % len(bad_lm))
# ---- report per gruppo
print("\n=== PAGINE per gruppo")
order = ["root","articoli/it","articoli/en","articoli/es","squadre","campionati","fantacalcio","giocatori","fanta"]
tit_all = Counter(r["title"] for r in rows.values()); desc_all = Counter(r["desc"] for r in rows.values())
for g in order:
    rs = {f: r for f, r in rows.items() if r["grp"] == g}
    if not rs: continue
    n = len(rs)
    def cnt(fn): return sum(1 for r in rs.values() if fn(r))
    txt = sorted(r["text"] for r in rs.values())
    print("\n[%s] %d pagine" % (g, n))
    print("  title assente %d | >60 car %d | duplicato (in tutto il sito) %d" % (cnt(lambda r: not r["title"]), cnt(lambda r: len(r["title"])>60), cnt(lambda r: tit_all[r["title"]]>1)))
    print("  description assente %d | >155 car %d | <60 car %d | duplicata %d" % (cnt(lambda r: not r["desc"]), cnt(lambda r: len(r["desc"])>155), cnt(lambda r: 0<len(r["desc"])<60), cnt(lambda r: desc_all[r["desc"]]>1)))
    print("  canonical assente %d | diverso dalla URL %d | hreflang presenti %d | noindex %d | lang html: %s" % (cnt(lambda r: not r["canonical"]), cnt(lambda r: r["canonical"] and r["canonical"]!=r["url"]), cnt(lambda r: bool(r["hreflang"])), cnt(lambda r: "noindex" in r["robots"]), dict(Counter(r["lang"] for r in rs.values()))))
    print("  H1: nessuno %d | piu di uno %d | vuoto %d" % (cnt(lambda r: len(r["h1"])==0), cnt(lambda r: len(r["h1"])>1), cnt(lambda r: r["h1txt"] and not r["h1txt"][0])))
    print("  testo statico (caratteri): min %d | mediana %d | max %d | <1500: %d" % (txt[0], txt[len(txt)//2], txt[-1], cnt(lambda r: r["text"]<1500)))
    print("  JSON-LD: errori %d | senza JSON-LD %d | tipi: %s" % (sum(r["ld_err"] for r in rs.values()), cnt(lambda r: not r["ld_types"]), dict(Counter(t for r in rs.values() for t in r["ld_types"]))))
    print("  BreadcrumbList %d/%d | breadcrumb visibile %d/%d | author Person con url %d | founder %d | sameAs %d" % (cnt(lambda r: "BreadcrumbList" in r["ld_types"]), n, cnt(lambda r: r["crumb_vis"]), n, cnt(lambda r: r["author_person"]), cnt(lambda r: r["founder"]), cnt(lambda r: r["sameAs"])))
    print("  link ?lang= %d pagine | &lt;p&gt; %d | 'undefined' %d pagine | img senza alt %d | og:image assente %d | non in sitemap %d" % (cnt(lambda r: r["lang_links"]>0), sum(r["ltp"] for r in rs.values()), cnt(lambda r: r["undef"]>0), sum(r["noalt"] for r in rs.values()), cnt(lambda r: not r["og_image"]), cnt(lambda r: r["url"] not in sm)))
    lk = Counter()
    for r in rs.values(): lk.update(r["links"])
    print("  link interni medi per pagina: %s" % {k: round(v/n,1) for k, v in lk.items()})
    if g == "root":
        for f, r in sorted(rs.items()):
            print("    %-18s title(%d)=%r\n%s desc(%d) h1=%r testo=%d ld=%s hreflang=%d ?lang=%d" % (f, len(r["title"]), r["title"], " "*22, len(r["desc"]), r["h1txt"][:1], r["text"], r["ld_types"], len(r["hreflang"]), r["lang_links"]))
# ---- dettagli offensori
print("\n=== DETTAGLI")
for f, r in sorted(rows.items()):
    probs = []
    if not r["title"]: probs.append("no title")
    if len(r["title"])>60: probs.append("title %d" % len(r["title"]))
    if not r["desc"]: probs.append("no desc")
    if len(r["desc"])>155: probs.append("desc %d" % len(r["desc"]))
    if not r["canonical"]: probs.append("no canonical")
    elif r["canonical"]!=r["url"]: probs.append("canonical=%s" % r["canonical"])
    if len(r["h1"])!=1: probs.append("h1x%d" % len(r["h1"]))
    if r["ld_err"]: probs.append("ld-err")
    if r["ltp"]: probs.append("&lt;p&gt;")
    if r["undef"]: probs.append("undefined")
    if r["url"] not in sm: probs.append("no-sitemap")
    if r["grp"] not in ("root","fanta") and "BreadcrumbList" not in r["ld_types"]: probs.append("no-breadcrumb")
    if probs: print("  %-50s %s" % (f, "; ".join(probs)))
