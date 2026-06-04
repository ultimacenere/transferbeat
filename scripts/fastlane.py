#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TransferBeat - fastlane.py  (corsia veloce ULTIM'ORA)
Legge i canali Telegram pubblici degli esperti (via t.me/s, nessuna API/login),
tiene solo i messaggi recenti e pertinenti al mercato, li classifica e (se c'e' la
chiave) li riscrive in un titolo neutro con un LLM, e aggiorna data/ultimora.json.
Pensato per girare ogni 5 minuti su GitHub Actions e pubblicare sul branch 'live'.
"""
import json, os, re, sys, html
from datetime import datetime, timezone

try:
    import requests
except ImportError:
    print("Manca requests"); sys.exit(1)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data"); RULES = os.path.join(ROOT, "rules")
UA = {"User-Agent": "Mozilla/5.0 (compatible; TransferBeatBot/1.0)"}
LLM_KEY = os.environ.get("GROQ_API_KEY", "")
LLM_URL = "https://api.groq.com/openai/v1/chat/completions"
LLM_MODEL = os.environ.get("LLM_MODEL", "llama-3.1-8b-instant")
MAX_AGE_H = 12
MAX_ITEMS = 50
MAX_NEW_PER_RUN = 20

def load(p, d=None):
    try:
        return json.load(open(p, encoding="utf-8"))
    except Exception:
        return d

def messages(ch):
    try:
        r = requests.get("https://t.me/s/" + ch, headers=UA, timeout=12)
    except Exception:
        return []
    out = []
    for b in r.text.split("tgme_widget_message_wrap")[1:]:
        ml = re.search(r'tgme_widget_message_date"[^>]*href="(https://t\.me/[^"]+)"', b)
        mt = re.search(r'<time[^>]*datetime="([^"]+)"', b)
        mx = re.search(r'tgme_widget_message_text[^"]*"[^>]*>(.*?)</div>', b, re.S)
        if not (ml and mx):
            continue
        txt = re.sub(r"<br\s*/?>", " ", mx.group(1))
        txt = re.sub(r"<[^>]+>", "", html.unescape(txt)).strip()
        txt = re.sub(r"https?://\S+", "", txt).strip()
        if txt:
            out.append({"link": ml.group(1), "ts": mt.group(1), "txt": txt})
    return out

def age_h(ts):
    try:
        dt = datetime.fromisoformat(ts)
        return (datetime.now(timezone.utc) - dt).total_seconds() / 3600
    except Exception:
        return 999

def classify(title, kw):
    low = title.lower()
    for stato in kw["categorie_ordine"]:
        for parola in kw["categorie"][stato]:
            if parola in low:
                return stato
    return "rumor"

def llm_process(txt, lang):
    """Ritorna (transfer:bool, titolo:str, stato:str). Se manca la chiave: None (usa fallback)."""
    if not LLM_KEY:
        return None
    langname = {"it": "italiano", "en": "English", "es": "español"}.get(lang, "italiano")
    sys_p = ("Sei un analista di calciomercato. Rispondi SOLO con JSON. Campi: "
             "transfer (true SOLO se la notizia riguarda un trasferimento, una trattativa, "
             "un rinnovo o una voce su un calciatore; false per gossip, partite, opinioni, eventi), "
             "titolo (titolo conciso e neutro, max 100 caratteri, in " + langname + ", senza emoji ne hashtag ne virgolette), "
             "stato (uno tra: done=ufficiale, conf=accordo, obj=trattativa/obiettivo, rumor=voce).")
    try:
        r = requests.post(LLM_URL, timeout=20,
            headers={"Authorization": "Bearer " + LLM_KEY, "Content-Type": "application/json"},
            json={"model": LLM_MODEL, "temperature": 0, "response_format": {"type": "json_object"},
                  "messages": [{"role": "system", "content": sys_p},
                               {"role": "user", "content": txt[:500]}]})
        d = json.loads(r.json()["choices"][0]["message"]["content"])
        st = d.get("stato") if d.get("stato") in ("done", "conf", "obj", "rumor") else "rumor"
        return (bool(d.get("transfer")), (d.get("titolo") or "").strip()[:130], st)
    except Exception:
        return None

def main():
    experts = load(os.path.join(DATA, "experts.json"), {"canali": []})
    teams = load(os.path.join(DATA, "teams.json"), {"squadre": []})
    kws = {l: load(os.path.join(RULES, "keywords." + l + ".json"),
                   load(os.path.join(RULES, "keywords.json"), {"categorie_ordine": [], "categorie": {}}))
           for l in ("it", "en", "es")}
    team_names = [(t["nome"], t["nome"].lower()) for t in teams.get("squadre", [])]

    prev = load(os.path.join(DATA, "ultimora.json"), {"items": []})
    seen = {it["link"] for it in prev.get("items", [])}
    items = list(prev.get("items", []))

    new_count = 0
    for ch in experts.get("canali", []):
        lang = ch.get("lang", "it"); kw = kws.get(lang, kws["it"])
        for m in messages(ch["username"]):
            if m["link"] in seen:
                continue
            if age_h(m["ts"]) > MAX_AGE_H:
                continue
            if len(m["txt"]) < 25:
                continue
            if new_count >= MAX_NEW_PER_RUN:
                break
            low = m["txt"].lower()
            team = next((n for (n, nl) in team_names if nl in low), "")
            res = llm_process(m["txt"], lang)
            if res is not None:
                transfer, titolo, stato = res
                if not transfer:
                    seen.add(m["link"]); continue
            else:
                kwords = ("mercato","transfer","fichaj","ufficiale","official","accordo","firma","here we go","obiettiv","trattativ","prestito","clausola","rinnov","colpo","cessione","addio","ingaggio","vola","pista")
                if not (team or any(k in low for k in kwords)):
                    continue
                titolo = re.sub(r"[#*_`]", "", m["txt"]).strip()[:120]; stato = classify(m["txt"], kw)
            seen.add(m["link"]); new_count += 1
            items.append({"ts": m["ts"], "fonte": ch["nome"], "tier": int(ch.get("tier", 1)),
                          "titolo": titolo, "stato": stato, "team": team, "link": m["link"], "lang": lang})

    items.sort(key=lambda x: x["ts"], reverse=True)
    items = items[:MAX_ITEMS]
    out = {"aggiornato": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "items": items}
    json.dump(out, open(os.path.join(DATA, "ultimora.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print("ultim'ora: " + str(new_count) + " nuove, " + str(len(items)) + " totali")

if __name__ == "__main__":
    main()
