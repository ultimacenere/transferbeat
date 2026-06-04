#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""TransferBeat - fastlane.py (corsia veloce ULTIM'ORA da canali Telegram pubblici)."""
import json, os, re, sys, html, unicodedata
from datetime import datetime, timezone
try:
    import requests
except ImportError:
    print("Manca requests"); sys.exit(1)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data"); RULES = os.path.join(ROOT, "rules")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import brain
UA = {"User-Agent": "Mozilla/5.0 (compatible; TransferBeatBot/1.0)"}
LLM_KEY = os.environ.get("GROQ_API_KEY", "")
LLM_URL = "https://api.groq.com/openai/v1/chat/completions"
LLM_MODEL = os.environ.get("LLM_MODEL", "llama-3.1-8b-instant")  # lavoro pesante: modello piccolo, secchio 500k/giorno
MAX_AGE_H = 12; MAX_ITEMS = 50; MAX_NEW_PER_RUN = 25

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
        raw = mx.group(1)
        txt = re.sub(r"<br\s*/?>", " ", raw)
        txt = re.sub(r"<[^>]+>", "", html.unescape(txt)).strip()
        # link alla TESTATA: primo href esterno (non t.me) nel post, o primo URL visibile
        src = ""
        mh = re.search(r'href="(https?://[^"]+)"', raw)
        if mh and "t.me" not in mh.group(1):
            src = html.unescape(mh.group(1))
        else:
            mu = re.search(r'https?://[^\s"<]+', txt)
            if mu and "t.me" not in mu.group(0):
                src = mu.group(0)
        txt = re.sub(r"https?://\S+", "", txt).strip()
        if txt:
            out.append({"link": ml.group(1), "ts": mt.group(1), "txt": txt, "src": src})
    return out

def age_h(ts):
    try:
        return (datetime.now(timezone.utc) - datetime.fromisoformat(ts)).total_seconds() / 3600
    except Exception:
        return 999

def classify(title, kw):
    low = title.lower()
    for stato in kw["categorie_ordine"]:
        for parola in kw["categorie"][stato]:
            if parola in low:
                return stato
    return "rumor"

def match_team(s, team_names):
    sl = (s or "").lower()
    if not sl:
        return ""
    return next((n for (n, nl) in team_names if nl in sl or sl in nl), "")

def slugify(name):
    x = unicodedata.normalize("NFKD", name or "").encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-zA-Z0-9]+", "-", x).strip("-").lower()

def llm_process(txt, lang):
    if not LLM_KEY:
        return None
    langname = {"it": "italiano", "en": "English", "es": "espanol"}.get(lang, "italiano")
    sys_p = (
      "Sei un analista di calciomercato. Rispondi SOLO con JSON valido.\n"
      "Campi:\n"
      "- transfer: true SOLO se riguarda un trasferimento/trattativa/rinnovo/voce su un calciatore; false per gossip, partite, opinioni, eventi.\n"
      "- titolo: titolo conciso e neutro, max 100 caratteri, in " + langname + ", senza emoji ne hashtag ne virgolette.\n"
      "- stato: 'done' se ufficiale/annunciato/firmato; 'conf' se l'affare e' dato per FATTO o c'e' un accordo (es. 'X lascia il club', 'X al club Y' come certezza); 'obj' se in trattativa/obiettivo/contatti; 'rumor' solo se semplice voce/idea/sondaggio/interesse.\n"
      "- squadra: il club di Serie A, La Liga o Premier League coinvolto (provenienza o destinazione); vuoto se nessuna delle tre leghe.\n"
      "- giocatore: nome del calciatore (vuoto se non chiaro).\n"
      "- direzione: 'in' se ARRIVA a 'squadra', 'out' se la LASCIA.\n"
      "- club: l'altra squadra coinvolta (vuoto se non indicata).\n"
      "- smentita: true se la notizia SMENTISCE o annulla un trasferimento/trattativa gia' dato (es. 'salta tutto', 'non se ne fa nulla'); false altrimenti.")
    try:
        r = requests.post(LLM_URL, timeout=25,
            headers={"Authorization": "Bearer " + LLM_KEY, "Content-Type": "application/json"},
            json={"model": LLM_MODEL, "temperature": 0, "response_format": {"type": "json_object"},
                  "messages": brain.classify_messages(txt, langname)})
        d = json.loads(r.json()["choices"][0]["message"]["content"])
        d["stato"] = d.get("stato") if d.get("stato") in ("done", "conf", "obj", "rumor") else "rumor"
        d["direzione"] = "out" if d.get("direzione") == "out" else "in"
        return d
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
            if age_h(m["ts"]) > MAX_AGE_H or len(m["txt"]) < 25:
                continue
            if new_count >= MAX_NEW_PER_RUN:
                break
            low = m["txt"].lower()
            d = llm_process(m["txt"], lang)
            giocatore = direzione = club = ""; smentita = False
            if d is not None:
                if not d.get("transfer"):
                    seen.add(m["link"]); continue
                titolo = (d.get("titolo") or "").strip()[:130]; stato = d["stato"]
                team = match_team(d.get("squadra"), team_names) or next((n for (n, nl) in team_names if nl in low), "")
                giocatore = (d.get("giocatore") or "").strip(); direzione = d["direzione"]; club = (d.get("club") or "").strip(); smentita = bool(d.get("smentita"))
            else:
                team = next((n for (n, nl) in team_names if nl in low), "")
                kwords = ("mercato","transfer","fichaj","ufficiale","official","accordo","firma","here we go","obiettiv","trattativ","prestito","clausola","rinnov","colpo","cessione","addio","ingaggio","vola","pista")
                if not (team or any(k in low for k in kwords)):
                    continue
                titolo = re.sub(r"[#*_`]", "", m["txt"]).strip()[:120]; stato = classify(m["txt"], kw)
            seen.add(m["link"]); new_count += 1
            items.append({"ts": m["ts"], "fonte": ch["nome"], "tier": int(ch.get("tier", 1)),
                          "titolo": titolo, "stato": stato, "team": team,
                          "giocatore": giocatore, "direzione": direzione, "club": club, "smentita": smentita,
                          "slug": slugify(giocatore), "link": (m.get("src") or m["link"]), "lang": lang})
    items.sort(key=lambda x: x["ts"], reverse=True)
    items = items[:MAX_ITEMS]
    out = {"aggiornato": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "items": items}
    json.dump(out, open(os.path.join(DATA, "ultimora.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print("ultim'ora: " + str(new_count) + " nuove, " + str(len(items)) + " totali")

if __name__ == "__main__":
    main()
