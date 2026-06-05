#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TransferBeat - articles.py
Trasforma le notizie dei canali social/esperti (Telegram) in ARTICOLI nostri:
- 1 articolo per giocatore/trattativa, che si AGGIORNA nel tempo (stato monotono: rumor<conf<done; mai a ritroso salvo smentita).
- L'LLM scrive un pezzo breve e FATTUALE, citando esplicitamente le fonti (no invenzioni).
- Traduzioni EN/ES.
- Genera pagine statiche articoli/<lang>/<slug>.html con JSON-LD NewsArticle, OG, hreflang, link alle fonti.
- Genera data/articles/index.json (per il front-end), sitemap.xml e robots.txt.
Le notizie dei SITI restano link esterni (non passano di qui): solo social/esperti diventano articoli.
"""
import json, os, re, sys, html, unicodedata, hashlib
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    import requests
    import brain
    from fastlane import messages, age_h, llm_process
except Exception as e:
    print("Dipendenze mancanti:", e); sys.exit(1)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
ARTDIR = os.path.join(DATA, "articles")       # store JSON dei singoli articoli
PAGES = os.path.join(ROOT, "articoli")        # pagine HTML pubbliche
SITE = "https://transferbeat.com"
LLM_KEY = os.environ.get("GROQ_API_KEY", "")
LLM_URL = "https://api.groq.com/openai/v1/chat/completions"
ARTICLE_MODELS = [os.environ.get("LLM_MODEL", "llama-3.3-70b-versatile"), "llama-3.1-8b-instant"]  # qualita, con fallback
LANGS = ("it", "en", "es")
MAX_AGE_H = 18          # quanto indietro guardare nei canali
MAX_UPDATES = 8         # quante note tenere per articolo
KEEP_DAYS = 75          # articoli piu vecchi (non aggiornati) escono dall'indice

STATE_RANK = {"rumor": 0, "obj": 1, "conf": 2, "done": 3}
STATE_LABEL = {
    "it": {"rumor": "Rumor", "obj": "Obiettivo", "conf": "Trattativa confermata", "done": "Affare concluso"},
    "en": {"rumor": "Rumour", "obj": "Target", "conf": "Deal agreed", "done": "Done deal"},
    "es": {"rumor": "Rumor", "obj": "Objetivo", "conf": "Negociacion confirmada", "done": "Cerrado"},
}
UI = {
  "it": {"by": "Redazione TransferBeat", "sources": "Fonti", "updated": "Aggiornato il",
         "home": "Home", "board": "Board live", "disc": "TransferBeat aggrega notizie di mercato citando le fonti originali. Notizia in aggiornamento.",
         "back": "Tutti gli articoli", "status": "Stato"},
  "en": {"by": "TransferBeat Newsroom", "sources": "Sources", "updated": "Updated on",
         "home": "Home", "board": "Live board", "disc": "TransferBeat aggregates transfer news citing the original sources. Developing story.",
         "back": "All articles", "status": "Status"},
  "es": {"by": "Redaccion TransferBeat", "sources": "Fuentes", "updated": "Actualizado el",
         "home": "Inicio", "board": "Board en vivo", "disc": "TransferBeat agrega noticias de mercado citando las fuentes originales. Noticia en desarrollo.",
         "back": "Todos los articulos", "status": "Estado"},
}
TITLE_SITE = "TransferBeat"

def load(p, d=None):
    try:
        return json.load(open(p, encoding="utf-8"))
    except Exception:
        return d

def slugify(name):
    s = unicodedata.normalize("NFKD", name or "").encode("ascii", "ignore").decode("ascii")
    s = re.sub(r"[^a-zA-Z0-9]+", "-", s).strip("-").lower()
    return s

def now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

def esc(s):
    return html.escape(str(s or ""), quote=True)

def _llm_chat(sys_p, user_p, temp=0.0, retries=2):
    """Chiamata Groq robusta con FALLBACK DI MODELLO: prova il 70b, se la quota giornaliera (TPD)
    e' esaurita passa all'8b. Gestisce anche il limite al minuto con piccola attesa."""
    import time
    for model in ARTICLE_MODELS:
        for a in range(retries):
            try:
                r = requests.post(LLM_URL, timeout=45,
                    headers={"Authorization": "Bearer " + LLM_KEY, "Content-Type": "application/json"},
                    json={"model": model, "temperature": temp, "response_format": {"type": "json_object"},
                          "messages": [{"role": "system", "content": sys_p}, {"role": "user", "content": user_p}]})
                if r.status_code == 429:
                    body = r.text.lower()
                    if "per day" in body or "tpd" in body:
                        print("    " + model + ": quota giornaliera esaurita, passo al modello di riserva")
                        break  # cambia modello
                    wait = min(float(r.headers.get("retry-after", 0)) or (2 * (a + 1)), 65)
                    print("    rate-limit al minuto, attendo", round(wait, 1), "s"); time.sleep(wait); continue
                j = r.json()
                if "choices" not in j:
                    print("    risposta anomala:", str(j)[:120]); time.sleep(2); continue
                return json.loads(j["choices"][0]["message"]["content"])
            except Exception as e:
                print("    LLM errore:", str(e)[:120]); time.sleep(2)
    return None

# ---------- LLM: scrittura articolo (IT+EN+ES in un'unica chiamata) ----------
def _stub(player, team, club, direzione, stato):
    t = player + (" verso " + club if (direzione == "in" and club) else (" lascia " + team if direzione == "out" else ""))
    one = {"title": (t or player)[:70], "lead": player + ": ultimi aggiornamenti di mercato.",
           "body": ["Notizia in aggiornamento su " + player + "."]}
    return {l: dict(one) for l in LANGS}

def _clamp(c, fallback_title):
    b = c.get("body") or []
    if isinstance(b, str): b = [b]
    return {"title": (c.get("title") or fallback_title)[:90],
            "lead": (c.get("lead") or "")[:240],
            "body": [str(x)[:1200] for x in b if str(x).strip()][:4] or ["—"]}

def write_article(player, team, club, direzione, stato, smentita, updates):
    """Ritorna {it:{...}, en:{...}, es:{...}}. Solo fatti dalle note, con attribuzione. Una sola chiamata LLM."""
    if not LLM_KEY:
        return _stub(player, team, club, direzione, stato)
    note = "\n".join("- [" + u["fonte"] + "] " + (u.get("testo") or "")[:240] for u in updates[:MAX_UPDATES])
    statotxt = {"rumor": "una semplice voce/indiscrezione", "obj": "una trattativa in corso",
                "conf": "un affare ormai dato per fatto", "done": "un trasferimento ufficiale"}.get(stato, "una voce")
    if smentita:
        statotxt = "una trattativa che e' stata smentita/saltata"
    movimento = (player + " e' in USCITA da " + (team or "?") + (" verso " + club if club else "")) if direzione == "out" else (player + " e' in ARRIVO a " + (team or "?") + (" dal " + club if club else ""))
    sys_p = brain.article_system()
    user_p = ("Contesto trattativa:\n"
              "- Giocatore: " + player + "\n"
              "- Club coinvolti: " + (team or "?") + (" e " + club if club else "") + "\n"
              "- Movimento (RISPETTALO): " + movimento + "\n"
              "- Situazione: si tratta di " + statotxt + "\n\n"
              "Note dalle fonti (piu recenti in alto):\n" + note + "\n\n"
              "Scrivi un articolo BREVE e fattuale (2-3 paragrafi brevi) nelle TRE lingue: italiano, inglese, spagnolo. "
              "Ogni affermazione attribuita a una fonte; se ufficiale scrivi 'ufficiale'; se smentita spiega che l'affare e' saltato; "
              "chiudi indicando lo stato attuale.\n"
              'Formato JSON: {"it":{"title":"","lead":"","body":["",""]},"en":{...},"es":{...}}')
    d = _llm_chat(sys_p, user_p, temp=0.2)
    if d is None:
        return None
    return {l: _clamp(d.get(l) or {}, player) for l in LANGS}

# ---------- raccolta dai canali ----------
def collect(experts, teams):
    """Legge i movimenti GIA' classificati dal fast lane (ultimora.json): nessuna chiamata LLM qui.
    L'LLM servira' solo a scrivere gli articoli. Sorgente: file locale o branch live."""
    tinfo = {t["nome"]: t for t in teams.get("squadre", [])}
    data = load(os.path.join(DATA, "ultimora.json"))
    if not data:
        try:
            r = requests.get("https://raw.githubusercontent.com/ultimacenere/transferbeat/live/data/ultimora.json", timeout=15)
            data = r.json()
        except Exception:
            data = {"items": []}
    found = []
    for i in data.get("items", []):
        player = (i.get("giocatore") or "").strip()
        team = (i.get("team") or "").strip()
        if not player or len(player) < 3 or team not in tinfo or brain.is_coach(player):
            continue
        found.append({"player": player, "team": team, "club": (i.get("club") or "").strip(),
                      "direzione": i.get("direzione") or "in", "stato": i.get("stato") or "rumor",
                      "smentita": bool(i.get("smentita")), "fonte": i.get("fonte") or "",
                      "tier": int(i.get("tier") or 1), "link": i.get("link") or "",
                      "ts": i.get("ts") or now_iso(), "testo": (i.get("titolo") or "")[:300],
                      "lab": tinfo[team].get("lab", ""), "col": tinfo[team].get("col", "#0a9d57"),
                      "league": tinfo[team].get("league", "")})
    return found

def upsert(items):
    os.makedirs(ARTDIR, exist_ok=True)
    touched = {}
    for it in items:
        slug = slugify(it["player"])
        if not slug:
            continue
        path = os.path.join(ARTDIR, slug + ".json")
        art = load(path) or {"slug": slug, "giocatore": it["player"], "created": now_iso(),
                             "stato": "rumor", "smentita": False, "updates": [], "content": {}}
        # nuova nota? (per link)
        if not any(u["link"] == it["link"] for u in art["updates"]):
            art["updates"].insert(0, {"ts": it["ts"], "fonte": it["fonte"], "tier": it["tier"],
                                      "link": it["link"], "stato": it["stato"], "smentita": it["smentita"],
                                      "testo": it["testo"][:300]})
        art["updates"] = art["updates"][:MAX_UPDATES]
        # stato monotono, salvo smentita nell'ultima nota
        last_smentita = it["smentita"]
        if last_smentita:
            art["smentita"] = True
        else:
            art["smentita"] = False
            if STATE_RANK.get(it["stato"], 0) >= STATE_RANK.get(art.get("stato", "rumor"), 0):
                art["stato"] = it["stato"]
        # metadati piu recenti
        art["giocatore"] = it["player"]; art["team"] = it["team"]; art["club"] = it["club"]
        art["direzione"] = it["direzione"]; art["league"] = it["league"]; art["lab"] = it["lab"]; art["col"] = it["col"]
        art["updated"] = now_iso()
        touched[slug] = (art, path)
    # genera/aggiorna contenuto solo se cambiato
    for slug, (art, path) in touched.items():
        sig = hashlib.md5((art["stato"] + str(art["smentita"]) + "|".join(u["link"] for u in art["updates"])).encode()).hexdigest()
        if art.get("_sig") != sig or not art.get("content"):
            import time as _t; _t.sleep(0.5)
            cont = write_article(art["giocatore"], art.get("team", ""), art.get("club", ""),
                                 art.get("direzione", "in"), art["stato"], art["smentita"], art["updates"])
            if cont:
                art["content"] = cont
                art["_sig"] = sig
                print("  articolo:", slug, "(" + art["stato"] + ("/smentita" if art["smentita"] else "") + ")")
        json.dump(art, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    return list(touched.keys())

def all_articles():
    out = []
    if not os.path.isdir(ARTDIR):
        return out
    for fn in os.listdir(ARTDIR):
        if fn.endswith(".json"):
            a = load(os.path.join(ARTDIR, fn))
            if a and a.get("content"):
                out.append(a)
    out.sort(key=lambda a: a.get("updated", ""), reverse=True)
    return out

if __name__ == "__main__":
    import render_articles  # noqa
    experts = load(os.path.join(DATA, "experts.json"), {"canali": []})
    teams = load(os.path.join(DATA, "teams.json"), {"squadre": []})
    print("Raccolgo dai canali...", "(senza LLM)" if not LLM_KEY else "")
    items = collect(experts, teams)
    print("trovate", len(items), "note social con giocatore+club")
    upsert(items)
    arts = all_articles()
    render_articles.render_all(arts, SITE, PAGES, DATA)
    print("OK:", len(arts), "articoli totali")
