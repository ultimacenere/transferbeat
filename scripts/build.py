#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TransferBeat - build.py (multilingua IT/EN/ES)
Per ogni lingua: legge i feed Google News localizzati, classifica le notizie nelle 4 categorie
con il dizionario di quella lingua, assegna l'affidabilita, deduplica, risale all'URL reale della
testata e ne estrae l'immagine (og:image), e con un LLM opzionale (Groq) estrae i movimenti
strutturati. Scrive data/<lang>/board.json e data/<lang>/home.json.
Variabili: GROQ_API_KEY (opzionale, vista Nomi), ONLY_LANG (per generare una sola lingua).
"""
import json, os, re, sys, html, urllib.parse
from datetime import datetime, timezone

try:
    import feedparser, requests
    from googlenewsdecoder import gnewsdecoder
except ImportError:
    print("Mancano dipendenze. Esegui: pip install -r requirements.txt")
    sys.exit(1)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
RULES = os.path.join(ROOT, "rules")

LANGS = {
    "it": "hl=it&gl=IT&ceid=IT:it",
    "en": "hl=en-GB&gl=GB&ceid=GB:en",
    "es": "hl=es&gl=ES&ceid=ES:es",
}
GNEWS = "https://news.google.com/rss/search?q={q}&{loc}"
MAX_PER_TEAM = 14
MAX_PER_COL = 6
FEED_ENRICH = int(os.environ.get("FEED_ENRICH", "6"))
UA = {"User-Agent": "Mozilla/5.0 (compatible; TransferBeatBot/1.0)"}
LLM_KEY = os.environ.get("GROQ_API_KEY", "")
LLM_URL = "https://api.groq.com/openai/v1/chat/completions"
LLM_MODEL = os.environ.get("LLM_MODEL", "llama-3.3-70b-versatile")
GIORNI = {
  "it": ["Lunedi","Martedi","Mercoledi","Giovedi","Venerdi","Sabato","Domenica"],
  "en": ["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"],
  "es": ["Lunes","Martes","Miercoles","Jueves","Viernes","Sabado","Domingo"],
}
MESI = {
  "it": ["gennaio","febbraio","marzo","aprile","maggio","giugno","luglio","agosto","settembre","ottobre","novembre","dicembre"],
  "en": ["January","February","March","April","May","June","July","August","September","October","November","December"],
  "es": ["enero","febrero","marzo","abril","mayo","junio","julio","agosto","septiembre","octubre","noviembre","diciembre"],
}
AGO = {"it": ("poco fa", " ore fa", " g fa"), "en": ("just now", "h ago", "d ago"), "es": ("ahora", " h", " d")}
_ENRICH_CACHE = {}

def load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)

def clean_title(t):
    t = html.unescape(t or "").strip()
    fonte = ""
    if " - " in t:
        parts = t.rsplit(" - ", 1)
        if len(parts[1]) < 40:
            t, fonte = parts[0].strip(), parts[1].strip()
    return t, fonte

def classify(title, kw):
    low = title.lower()
    for stato in kw["categorie_ordine"]:
        for parola in kw["categorie"][stato]:
            if parola in low:
                return stato
    return "rumor"

def reliability(fonte, kw):
    f = (fonte or "").lower()
    for liv in ("3", "2"):
        for testata in kw["affidabilita"].get(liv, []):
            if testata in f:
                return int(liv)
    return kw.get("_default_affidabilita", 1)

def time_ago(pp, lang):
    if not pp:
        return ""
    now_, hh, dd = AGO[lang]
    dt = datetime(*pp[:6], tzinfo=timezone.utc)
    h = int((datetime.now(timezone.utc) - dt).total_seconds() // 3600)
    if h < 1: return now_
    if h < 24: return str(h) + hh
    return str(h // 24) + dd

def domain_of(url):
    try:
        return urllib.parse.urlparse(url).netloc.replace("www.", "")
    except Exception:
        return ""

def og_image(url):
    try:
        r = requests.get(url, headers=UA, timeout=5)
        h = r.text[:200000]
        for pat in (r'property=["\']og:image["\'][^>]*content=["\']([^"\']+)',
                    r'content=["\']([^"\']+)["\'][^>]*property=["\']og:image',
                    r'name=["\']twitter:image["\'][^>]*content=["\']([^"\']+)'):
            m = re.search(pat, h)
            if m:
                img = html.unescape(m.group(1).strip())
                if img.startswith("//"): img = "https:" + img
                if img.startswith("http"): return img
    except Exception:
        pass
    return ""

def enrich(gn_link, src_href):
    if gn_link in _ENRICH_CACHE:
        return _ENRICH_CACHE[gn_link]
    real, img = src_href or gn_link, ""
    try:
        if "news.google.com" in gn_link:
            out = gnewsdecoder(gn_link, interval=0.4)
            if out.get("status") and out.get("decoded_url"):
                real = out["decoded_url"]
                img = og_image(real)
        else:
            real = gn_link
            img = og_image(real)
    except Exception:
        pass
    res = {"url": real, "img": img, "dominio": domain_of(real)}
    _ENRICH_CACHE[gn_link] = res
    return res

def extract_movements(team, titles, fallback=None):
    base = fallback if fallback else {"rumor": [], "obj": [], "conf": [], "done": []}
    if not LLM_KEY:
        return base
    titles = [t for t in titles if t][:16]
    if not titles:
        return {"rumor": [], "obj": [], "conf": [], "done": []}
    sys_p = "Sei un analista esperto di calciomercato. Rispondi SOLO con JSON valido, nessun altro testo."
    user_p = ("Squadra di riferimento: " + team + ".\n"
        "Dalle notizie qui sotto (in qualsiasi lingua) estrai i movimenti che riguardano " + team + ".\n"
        "Per ogni movimento: giocatore (nome), direzione ('in' se ARRIVA a " + team +
        ", 'out' se LASCIA " + team + "), club (l'altra squadra), "
        "stato ('done'=ufficiale, 'conf'=accordo, 'obj'=obiettivo/trattativa, 'rumor'=voce).\n"
        "Ignora le notizie che non sono il movimento di un singolo giocatore. Non inventare.\n"
        'Formato: {"movimenti":[{"giocatore":"","direzione":"in","club":"","stato":"obj"}]}\n\n'
        "Notizie:\n- " + "\n- ".join(titles))
    try:
        r = requests.post(LLM_URL, timeout=40,
            headers={"Authorization": "Bearer " + LLM_KEY, "Content-Type": "application/json"},
            json={"model": LLM_MODEL, "temperature": 0,
                  "response_format": {"type": "json_object"},
                  "messages": [{"role": "system", "content": sys_p},
                               {"role": "user", "content": user_p}]})
        movs = json.loads(r.json()["choices"][0]["message"]["content"]).get("movimenti", [])
    except Exception as e:
        print("    LLM errore (" + team + "): " + str(e)[:90])
        return base
    out = {"rumor": [], "obj": [], "conf": [], "done": []}
    for m in movs:
        g = (m.get("giocatore") or "").strip()
        if not g:
            continue
        st = m.get("stato") if m.get("stato") in out else "rumor"
        d = "out" if (m.get("direzione") == "out") else "in"
        out[st].append({"giocatore": g, "direzione": d, "club": (m.get("club") or "").strip()})
    return out

def fetch(query, limit, loc):
    feed = feedparser.parse(GNEWS.format(q=urllib.parse.quote(query), loc=loc))
    out = []
    for e in feed.entries[:limit]:
        titolo, fonte = clean_title(getattr(e, "title", ""))
        if not titolo:
            continue
        src = getattr(e, "source", {})
        out.append({"titolo": titolo,
                    "fonte": fonte or (src.get("title") if isinstance(src, dict) else "") or "-",
                    "gn_link": getattr(e, "link", ""),
                    "src_href": src.get("href") if isinstance(src, dict) else "",
                    "pub": getattr(e, "published_parsed", None)})
    return out

def team_match(title, t):
    low = title.lower()
    return t["nome"].lower() in low or t.get("search", "").lower() in low

def fetch_direct(lang, sources):
    out = []
    for sfeed in sources.get("feeds", []):
        if sfeed.get("lang") != lang:
            continue
        try:
            f = feedparser.parse(sfeed["url"])
        except Exception:
            continue
        for e in f.entries[:30]:
            titolo = html.unescape(getattr(e, "title", "") or "").strip()
            link = getattr(e, "link", "")
            if not titolo or not link:
                continue
            out.append({"titolo": titolo, "fonte": sfeed["nome"], "gn_link": link,
                        "src_href": link, "pub": getattr(e, "published_parsed", None),
                        "tier": int(sfeed.get("tier", 1))})
    return out

def dedupe(items):
    seen = {}
    for it in items:
        words = re.sub(r"[^a-z0-9 ]", "", it["titolo"].lower()).split()
        key = " ".join(words[:5])
        if key not in seen or it["affidabilita"] > seen[key]["affidabilita"]:
            seen[key] = it
    return list(seen.values())

def build_board(teams, kw, lang, loc, direct_items=None):
    direct_items = direct_items or []
    old_nomi = {}
    try:
        old = json.load(open(os.path.join(DATA, lang, "board.json"), encoding="utf-8"))
        old_nomi = {k: v.get("nomi", {}) for k, v in old.get("squadre", {}).items()}
    except Exception:
        pass
    base_kw = teams["kw"][lang]
    squadre = {}
    for t in teams["squadre"]:
        q = base_kw + " " + t["search"]
        items = []
        for r in fetch(q, MAX_PER_TEAM, loc):
            r["stato"] = classify(r["titolo"], kw)
            r["affidabilita"] = reliability(r["fonte"], kw)
            r["quando"] = time_ago(r["pub"], lang)
            items.append(r)
        for d in direct_items:
            if team_match(d["titolo"], t):
                items.append({"titolo": d["titolo"], "fonte": d["fonte"], "gn_link": d["gn_link"],
                              "src_href": d["src_href"], "pub": d["pub"],
                              "stato": classify(d["titolo"], kw), "affidabilita": d["tier"],
                              "quando": time_ago(d["pub"], lang)})
        items = dedupe(items)
        items.sort(key=lambda x: (x["affidabilita"], x["pub"] or ()), reverse=True)
        colonne = {"rumor": [], "obj": [], "conf": [], "done": []}
        for it in items:
            col = colonne[it["stato"]]
            if len(col) < MAX_PER_COL:
                col.append({"titolo": it["titolo"], "fonte": it["fonte"],
                            "link": it["src_href"] or it["gn_link"],
                            "affidabilita": it["affidabilita"], "quando": it["quando"]})
        feed = []
        for it in items[:FEED_ENRICH]:
            e = enrich(it["gn_link"], it["src_href"])
            feed.append({"titolo": it["titolo"], "fonte": it["fonte"], "stato": it["stato"],
                         "link": e["url"], "img": e["img"], "dominio": e["dominio"],
                         "affidabilita": it["affidabilita"], "quando": it["quando"]})
        nomi = extract_movements(t["nome"], [it["titolo"] for it in items], old_nomi.get(t["nome"]))
        squadre[t["nome"]] = {"lab": t["lab"], "col": t["col"], "league": t["league"],
                              "colonne": colonne, "feed": feed, "nomi": nomi}
    return squadre

def build_home(teams, kw, lang, loc):
    base_kw = teams["kw"][lang]
    pool = []
    for lega in teams.get("leghe_home", []):
        for r in fetch(base_kw + " " + lega["search"], 8, loc):
            r["categoria"] = lega["label"][lang]
            pool.append(r)
    for it in pool:
        it["stato"] = classify(it["titolo"], kw)
        it["affidabilita"] = reliability(it["fonte"], kw)
        it["quando"] = time_ago(it["pub"], lang)
    enriched = dedupe([dict(p) for p in pool])
    enriched.sort(key=lambda x: (x["affidabilita"], x["pub"] or ()), reverse=True)
    def slim(e):
        if not e:
            return None
        info = enrich(e["gn_link"], e["src_href"])
        return {"categoria": e.get("categoria", ""), "titolo": e["titolo"], "fonte": e["fonte"],
                "link": info["url"], "img": info["img"], "dominio": info["dominio"],
                "quando": e.get("quando", "")}
    apertura = slim(enriched[0]) if enriched else None
    secondari = [slim(e) for e in enriched[1:4]]
    mondo = []
    for m in teams.get("mondo_home", []):
        got = fetch(m["search"], 3, loc)
        if got:
            g = got[0]; info = enrich(g["gn_link"], g["src_href"])
            mondo.append({"categoria": m["label"][lang], "titolo": g["titolo"], "fonte": g["fonte"],
                          "link": info["url"], "img": info["img"], "dominio": info["dominio"]})
    ticker = [e["titolo"] for e in enriched if e["stato"] in ("done", "conf")][:6]
    if len(ticker) < 4:
        ticker = [e["titolo"] for e in enriched][:6]
    return {"ticker": ticker, "apertura": apertura, "secondari": secondari, "mondo": mondo}

def build_lang(lang, teams):
    loc = LANGS[lang]
    try:
        kw = load(os.path.join(RULES, "keywords." + lang + ".json"))
    except Exception:
        kw = load(os.path.join(RULES, "keywords.json"))
    now = datetime.now()
    giorno = GIORNI[lang][now.weekday()] + " " + str(now.day) + " " + MESI[lang][now.month-1]
    stamp = now.strftime("%Y-%m-%dT%H:%M:%S")
    outdir = os.path.join(DATA, lang)
    os.makedirs(outdir, exist_ok=True)
    try:
        sources = load(os.path.join(DATA, "sources.json"))
    except Exception:
        sources = {"feeds": []}
    direct_items = fetch_direct(lang, sources)
    print("[" + lang + "] board... (" + str(len(direct_items)) + " voci da feed diretti)")
    board = {"aggiornato": stamp, "giorno": giorno, "squadre": build_board(teams, kw, lang, loc, direct_items)}
    print("[" + lang + "] home...")
    home = {"aggiornato": stamp, "giorno": giorno}
    home.update(build_home(teams, kw, lang, loc))
    json.dump(board, open(os.path.join(outdir, "board.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    json.dump(home, open(os.path.join(outdir, "home.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    n = sum(len(s["feed"]) for s in board["squadre"].values())
    nm = sum(len(x) for s in board["squadre"].values() for x in s["nomi"].values())
    print("[" + lang + "] OK - " + str(len(board["squadre"])) + " squadre, " + str(n) + " notizie, " + str(nm) + " movimenti")

def main():
    teams = load(os.path.join(DATA, "teams.json"))
    only = os.environ.get("ONLY_LANG", "").strip()
    langs = [only] if only in LANGS else list(LANGS.keys())
    print("Lingue: " + ", ".join(langs) + ("" if LLM_KEY else "  (senza chiave LLM: vista Nomi invariata)"))
    for lang in langs:
        build_lang(lang, teams)

if __name__ == "__main__":
    main()
