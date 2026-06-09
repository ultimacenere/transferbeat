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
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import brain

LANGS = {
    "it": "hl=it&gl=IT&ceid=IT:it",
    "en": "hl=en-GB&gl=GB&ceid=GB:en",
    "es": "hl=es&gl=ES&ceid=ES:es",
}
GNEWS = "https://news.google.com/rss/search?q={q}&{loc}"
MAX_PER_TEAM = 12
MAX_PER_COL = 6
FEED_ENRICH = int(os.environ.get("FEED_ENRICH", "3"))
UA = {"User-Agent": "Mozilla/5.0 (compatible; TransferBeatBot/1.0)"}
LLM_KEY = os.environ.get("GROQ_API_KEY", "")
LLM_URL = "https://api.groq.com/openai/v1/chat/completions"
LLM_MODEL = os.environ.get("LLM_MODEL", "meta-llama/llama-4-scout-17b-16e-instruct")  # movimenti: secchio separato 30k token/min
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

# segnali di movimento di mercato (IT/EN/ES): i titoli senza segnali non vanno all'LLM
_MOVE_SIGNALS = ("mercato","trasferi","firma","accordo","ufficial","prestito","riscatt","clausola",
                 "cession","addio","colpo","obiettiv","trattativ","ingaggi","offert","interess",
                 "sondaggio","vicino","lascia","arriva","saluta","piace","rinnov","scambio","erede",
                 "transfer","sign","deal","bid","loan","fee","target","swoop","exit","join",
                 "fichaje","traspaso","acuerdo","cesion","cesi\u00f3n","oferta","llega","deja","venta")

def _has_move_signal(t):
    low = (t or "").lower()
    return any(k in low for k in _MOVE_SIGNALS)

def extract_movements_global(titles):
    """Estrazione GLOBALE dei movimenti: da TUTTI i titoli, con provenienza/destinazione
    ESPLICITE (da -> a). Nessuna attribuzione per-squadra qui: la fa assign_movements."""
    if not LLM_KEY or not titles:
        return []
    import time as _t
    out = []
    B = 24
    for i in range(0, len(titles), B):
        batch = [t for t in titles[i:i + B] if t]
        if not batch:
            continue
        for attempt in (1, 2, 3):
            try:
                r = requests.post(LLM_URL, timeout=40,
                    headers={"Authorization": "Bearer " + LLM_KEY, "Content-Type": "application/json"},
                    json={"model": LLM_MODEL, "temperature": 0, "response_format": {"type": "json_object"},
                          "messages": brain.movements_messages(batch)})
                if r.status_code == 429:
                    w = min(float(r.headers.get("retry-after", 0)) or (4 * attempt), 30)
                    _t.sleep(w); continue
                j = r.json()
                if "choices" not in j:
                    _t.sleep(2); continue
                movs = json.loads(j["choices"][0]["message"]["content"]).get("movimenti", [])
                for m in movs:
                    g = (m.get("giocatore") or "").strip()
                    st = m.get("stato") if m.get("stato") in ("rumor", "obj", "conf", "done") else "rumor"
                    if g and len(g) > 2 and not brain.is_coach(g):
                        out.append({"giocatore": g, "da": (m.get("da") or "").strip(),
                                    "a": (m.get("a") or "").strip(), "stato": st})
                break
            except Exception as e:
                print("    LLM movimenti errore:", str(e)[:80]); _t.sleep(2)
    return out

# falsi match da evitare (es. "Inter Miami" non e' l'Inter)
_NO_MATCH = {"inter": ("miami",)}

def _club_rows(teams):
    rows = []
    for t in teams.get("squadre", []):
        names = {t["nome"].lower()}
        if t.get("search"):
            names.add(t["search"].lower())
        rows.append((t["nome"], names))
    return rows

def match_club(s, rows):
    sl = (s or "").strip().lower()
    if not sl:
        return ""
    sl = brain.ALIAS.get(sl, sl).lower()
    # passata 1: match ESATTO (cosi' "Milan" -> Milan e non Inter via "Inter Milan")
    for nome, names in rows:
        if sl in names:
            return nome
    # passata 2: contenimento, solo se nessun club matcha esattamente
    for nome, names in rows:
        if any(b in sl for b in _NO_MATCH.get(nome.lower(), ())):
            continue
        for n in names:
            if n and (sl in n or n in sl):
                return nome
    return ""

def assign_movements(movs, teams):
    """Ogni movimento va SOLO ai club esplicitamente coinvolti: a=entrata, da=uscita."""
    rows = _club_rows(teams)
    per = {}
    def add(team, st, entry):
        per.setdefault(team, {"rumor": [], "obj": [], "conf": [], "done": []})[st].append(entry)
    for m in movs:
        t_da = match_club(m["da"], rows)
        t_a = match_club(m["a"], rows)
        if t_a:
            add(t_a, m["stato"], {"giocatore": m["giocatore"], "direzione": "in", "club": m["da"] or ""})
        if t_da and t_da != t_a:
            add(t_da, m["stato"], {"giocatore": m["giocatore"], "direzione": "out", "club": m["a"] or ""})
    return per

def age_days(pp):
    if not pp:
        return 9999
    try:
        dt = datetime(*pp[:6], tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - dt).days
    except Exception:
        return 9999

STATE_RANK = {"rumor": 0, "obj": 1, "conf": 2, "done": 3}

import unicodedata as _ud
_ACC = str.maketrans({"ø":"o","Ø":"o","ł":"l","Ł":"l","đ":"d","ð":"d","þ":"th","æ":"ae","œ":"oe","ß":"ss"})
def _deaccent(s):
    s = (s or "").translate(_ACC)
    return _ud.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii")
def _norm_name(s):
    return re.sub(r"[^a-z0-9 ]", "", _deaccent(s).lower()).strip()

def _days_since(iso):
    try:
        from datetime import date
        y, mo, d = map(int, iso[:10].split("-"))
        return (date.today() - date(y, mo, d)).days
    except Exception:
        return 0

HIST_BLACKLIST = {"banega", "murillo"}  # ex/storici noti: mai mostrare nei Nomi
STALE_DAYS = 3  # un movimento non piu' citato da >= STALE_DAYS giorni scade (tutti gli stati)

def _same_first(a, b):
    ta = a.split(); tb = b.split()
    fa = ta[0] if ta else ""; fb = tb[0] if tb else ""
    if len(fa) < 3 or len(fb) < 3:
        return False
    return fa.startswith(fb) or fb.startswith(fa)

def merge_nomi(old, new, today, max_age=60):
    """Persistenza movimenti: i rumor restano finche' non vengono promossi (obj/conf/done)
    o non sono piu' citati da oltre max_age giorni. Lo stato puo' solo salire."""
    order = ["rumor", "obj", "conf", "done"]
    m = {}
    for st in order:
        for it in (old or {}).get(st, []):
            key = _norm_name(it.get("giocatore", ""))
            if not key:
                continue
            m[key] = {"giocatore": it["giocatore"], "direzione": it.get("direzione", "in"),
                      "club": it.get("club", ""), "stato": st,
                      "_first": it.get("_first", today), "_seen": it.get("_seen", today)}
    for st in order:
        for it in (new or {}).get(st, []):
            key = _norm_name(it.get("giocatore", ""))
            if not key:
                continue
            if key in m:
                cur = m[key]; cur["_seen"] = today
                if STATE_RANK[st] > STATE_RANK[cur["stato"]]:
                    cur["stato"] = st; cur["direzione"] = it.get("direzione", cur["direzione"])
                    if it.get("club"):
                        cur["club"] = it["club"]
                elif it.get("club") and not cur["club"]:
                    cur["club"] = it["club"]
            else:
                m[key] = {"giocatore": it["giocatore"], "direzione": it.get("direzione", "in"),
                          "club": it.get("club", ""), "stato": st, "_first": today, "_seen": today}
    # fusione varianti dello stesso giocatore: "Hojlund" + "Rasmus Hojlund" -> una voce.
    # Prudente: fonde solo se un nome e' il solo cognome o e' contenuto nell'altro
    # (cosi' "Sebastiano Esposito" e "Francesco Esposito" restano distinti).
    bylast = {}
    for k in list(m.keys()):
        toks = k.split()
        last = toks[-1] if toks else k
        bylast.setdefault(last, []).append(k)
    for last, ks in bylast.items():
        if len(ks) < 2:
            continue
        ks.sort(key=len, reverse=True)
        base = ks[0]
        for k in ks[1:]:
            if k not in m or base not in m or k == base:
                continue
            a = m[base]; b = m[k]
            # stesso cognome + stessa destinazione/direzione => stesso movimento (nome di battesimo rumoroso)
            same_move = bool(a.get("club")) and a.get("club") == b.get("club") and a.get("direzione") == b.get("direzione")
            if k == last or k in base or base in k or _same_first(base, k) or same_move:
                b = m.pop(k)
                if STATE_RANK[b["stato"]] > STATE_RANK[a["stato"]]:
                    a["stato"] = b["stato"]; a["direzione"] = b["direzione"]
                if b.get("club") and not a.get("club"):
                    a["club"] = b["club"]
                fa = a.get("_first") or "9999"; fb = b.get("_first") or "9999"
                a["_first"] = min(fa, fb)
                a["_seen"] = max(a.get("_seen") or "", b.get("_seen") or "")
    out = {"rumor": [], "obj": [], "conf": [], "done": []}
    for it in m.values():
        nm = it.get("giocatore", "")
        toks = _deaccent(nm).lower().split()
        if toks and toks[-1] in HIST_BLACKLIST:
            continue
        stale = _days_since(it["_seen"])
        if stale >= STALE_DAYS:                       # scade su TUTTI gli stati, non solo rumor
            continue
        if (it["stato"] == "rumor" and not it.get("club")
                and it["_seen"] == it["_first"] and _days_since(it["_first"]) >= 1):
            continue                                  # rumor mono-fonte senza club: solo nel giorno stesso
        out[it["stato"]].append({"giocatore": it["giocatore"], "direzione": it["direzione"],
                                 "club": it["club"], "_first": it["_first"], "_seen": it["_seen"]})
    for st in out:
        out[st].sort(key=lambda x: x["_seen"], reverse=True)
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

def build_board(teams, kw, lang, loc, direct_items=None, today=""):
    direct_items = direct_items or []
    old_nomi = {}
    try:
        old = json.load(open(os.path.join(DATA, lang, "board.json"), encoding="utf-8"))
        old_nomi = {k: v.get("nomi", {}) for k, v in old.get("squadre", {}).items()}
    except Exception:
        pass
    base_kw = teams["kw"][lang]
    prepared = {}
    pool = []; _pseen = set()
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
        fresh = [it for it in items if age_days(it.get("pub")) <= 30]
        if fresh:
            items = fresh
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
        prepared[t["nome"]] = (t, colonne, feed)
        for it in items:
            if not _has_move_signal(it["titolo"]):
                continue
            kx = _norm_name(it["titolo"])[:80]
            if kx and kx not in _pseen:
                _pseen.add(kx); pool.append(it["titolo"])
    print("    movimenti: estrazione globale da " + str(len(pool)) + " titoli unici")
    movs = extract_movements_global(pool)
    permov = assign_movements(movs, teams)
    print("    movimenti estratti: " + str(len(movs)) + " -> assegnati a " + str(len(permov)) + " squadre")
    squadre = {}
    for nome, (t, colonne, feed) in prepared.items():
        new_mov = permov.get(nome, {"rumor": [], "obj": [], "conf": [], "done": []})
        nomi = merge_nomi(old_nomi.get(nome), new_mov, today)
        squadre[nome] = {"lab": t["lab"], "col": t["col"], "league": t["league"],
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
    enriched.sort(key=lambda x: (x["pub"] or (), x["affidabilita"]), reverse=True)
    fresh = [e for e in enriched if age_days(e.get("pub")) <= 14]
    pick = fresh if len(fresh) >= 4 else enriched
    def slim(e):
        if not e:
            return None
        info = enrich(e["gn_link"], e["src_href"])
        return {"categoria": e.get("categoria", ""), "titolo": e["titolo"], "fonte": e["fonte"],
                "link": info["url"], "img": info["img"], "dominio": info["dominio"],
                "quando": e.get("quando", "")}
    apertura = slim(pick[0]) if pick else None
    secondari = [slim(e) for e in pick[1:7]]
    mondo = []
    for m in teams.get("mondo_home", []):
        got = fetch(m["search"], 3, loc)
        if got:
            g = got[0]; info = enrich(g["gn_link"], g["src_href"])
            mondo.append({"categoria": m["label"][lang], "titolo": g["titolo"], "fonte": g["fonte"],
                          "link": info["url"], "img": info["img"], "dominio": info["dominio"]})
    ticker = [e["titolo"] for e in pick if e["stato"] in ("done", "conf")][:6]
    if len(ticker) < 4:
        ticker = [e["titolo"] for e in pick][:6]
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
    today = now.strftime("%Y-%m-%d")
    print("[" + lang + "] board... (" + str(len(direct_items)) + " voci da feed diretti)")
    board = {"aggiornato": stamp, "giorno": giorno, "squadre": build_board(teams, kw, lang, loc, direct_items, today)}
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
