#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""TransferBeat - fastlane.py (corsia veloce ULTIM'ORA da canali Telegram pubblici)."""
import json, os, re, sys, html, time, unicodedata
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
LLM_MODEL = os.environ.get("FAST_MODEL", os.environ.get("LLM_MODEL", "qwen/qwen3.8-27b"))  # vedi kb §1: compound-* eredita quote di modelli terzi e va in 429
MAX_AGE_H = 12; MAX_ITEMS = 50; MAX_NEW_PER_RUN = 25
MAX_CANDIDATI = 36   # quanti messaggi al massimo mandare al modello in un giro
LOTTO = 12           # messaggi per chiamata: ~2000 token, sotto il tetto di 8000/minuto

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

def llm_process_batch(testi, lang, tentativi=3):
    """Classifica PIU' messaggi in una sola chiamata. Ritorna una lista lunga quanto
    'testi', con un dict per messaggio (o None se non utilizzabile: in quel caso il
    chiamante ricade sulle regole di rules/keywords.*.json)."""
    vuoto = [None] * len(testi)
    if not LLM_KEY or not testi:
        return vuoto
    langname = {"it": "italiano", "en": "English", "es": "espanol"}.get(lang, "italiano")
    for k in range(tentativi):
        try:
            r = requests.post(LLM_URL, timeout=60,
                headers={"Authorization": "Bearer " + LLM_KEY, "Content-Type": "application/json"},
                json={"model": LLM_MODEL, "temperature": 0,
                      "response_format": {"type": "json_object"},
                      "messages": brain.classify_batch_messages(testi, langname)})
            if r.status_code == 429:      # tetto token/minuto: aspetta e ritenta
                try:
                    attesa = int(float(r.headers.get("retry-after") or 0))
                except Exception:
                    attesa = 0
                time.sleep(min(max(attesa, 15 * (k + 1)), 45))
                continue
            r.raise_for_status()
            grezzo = r.json()["choices"][0]["message"]["content"]
            blocco = re.search(r"\{.*\}", grezzo, re.S)   # tollera testo attorno al JSON
            dati = json.loads(blocco.group(0) if blocco else grezzo).get("items")
            if not isinstance(dati, list):
                print("    lotto: risposta senza lista items, uso le regole")
                return vuoto
            # allineamento per NUMERO del messaggio, non per posizione: i modelli
            # saltano o riordinano voci, e una lista piu' corta falserebbe tutto
            per_n = {}
            for pos, d in enumerate(dati):
                if not isinstance(d, dict):
                    continue
                try:
                    n = int(d.get("n", pos + 1))
                except Exception:
                    n = pos + 1
                if not 1 <= n <= len(testi):
                    continue
                d["stato"] = d.get("stato") if d.get("stato") in ("done", "conf", "obj", "rumor") else "rumor"
                d["direzione"] = "out" if d.get("direzione") == "out" else "in"
                per_n[n] = d
            if not per_n:
                return vuoto
            if len(per_n) < len(testi):
                print("    lotto: %d voci su %d (le mancanti passano alle regole)" % (len(per_n), len(testi)))
            return [per_n.get(i + 1) for i in range(len(testi))]
        except Exception as e:
            print("    lotto: errore %s (tentativo %d)" % (str(e)[:60], k + 1))
            time.sleep(2)
    return vuoto

def main():
    experts = load(os.path.join(DATA, "experts.json"), {"canali": []})
    teams = load(os.path.join(DATA, "teams.json"), {"squadre": []})
    kws = {l: load(os.path.join(RULES, "keywords." + l + ".json"),
                   load(os.path.join(RULES, "keywords.json"), {"categorie_ordine": [], "categorie": {}}))
           for l in ("it", "en", "es")}
    team_names = [(t["nome"], t["nome"].lower()) for t in teams.get("squadre", [])]
    prev = load(os.path.join(DATA, "ultimora.json"), {"items": []})
    def _nt(t):
        return re.sub(r"[^a-z0-9]+", " ", (t or "").lower()).strip()[:90]
    # dedup robusto: id stabile del messaggio Telegram ('tg') + titolo normalizzato
    seen = {(it.get("tg") or it.get("link")) for it in prev.get("items", [])}
    seen_titles = {_nt(it.get("titolo")) for it in prev.get("items", [])}
    items = list(prev.get("items", []))
    new_count = 0

    # --- 1) raccolta: solo filtri economici, nessuna chiamata al modello ---
    candidati = []
    for ch in experts.get("canali", []):
        lang = ch.get("lang", "it")
        for m in messages(ch["username"]):
            if m["link"] in seen:
                continue
            if age_h(m["ts"]) > MAX_AGE_H or len(m["txt"]) < 25:
                continue
            candidati.append((ch, lang, m))
            if len(candidati) >= MAX_CANDIDATI:
                break
        if len(candidati) >= MAX_CANDIDATI:
            break

    # --- 2) classificazione A LOTTI (una chiamata ogni LOTTO messaggi) ---
    esiti = {}
    for lang in sorted({c[1] for c in candidati}):
        idx = [i for i, c in enumerate(candidati) if c[1] == lang]
        for s in range(0, len(idx), LOTTO):
            blocco = idx[s:s + LOTTO]
            testi = [candidati[i][2]["txt"] for i in blocco]
            for i, d in zip(blocco, llm_process_batch(testi, lang)):
                esiti[i] = d
    ok = sum(1 for v in esiti.values() if v is not None)
    print("    classificati dal modello: %d/%d (il resto con le regole)" % (ok, len(candidati)))

    # --- 3) elaborazione ---
    for i, (ch, lang, m) in enumerate(candidati):
        kw = kws.get(lang, kws["it"])
        if new_count >= MAX_NEW_PER_RUN:
            break
        low = m["txt"].lower()
        d = esiti.get(i)   # gia' classificato a lotti qui sopra
        giocatore = direzione = club = ""; smentita = False
        if d is not None:
            if not d.get("transfer"):
                seen.add(m["link"]); continue
            titolo = (d.get("titolo") or "").strip()[:130]; stato = d["stato"]
            if not titolo:   # il modello a volte omette il titolo: ripiego sul testo ripulito
                titolo = re.sub(r"[#*_`]", "", m["txt"]).strip()[:120]
            team = match_team(d.get("squadra"), team_names) or next((n for (n, nl) in team_names if nl in low), "")
            giocatore = (d.get("giocatore") or "").strip()
            if brain.is_coach(giocatore):
                giocatore = ""
            direzione = d["direzione"]; club = (d.get("club") or "").strip(); smentita = bool(d.get("smentita"))
        else:
            team = next((n for (n, nl) in team_names if nl in low), "")
            kwords = ("mercato","transfer","fichaj","ufficiale","official","accordo","firma","here we go","obiettiv","trattativ","prestito","clausola","rinnov","colpo","cessione","addio","ingaggio","vola","pista")
            if not (team or any(k in low for k in kwords)):
                continue
            titolo = re.sub(r"[#*_`]", "", m["txt"]).strip()[:120]; stato = classify(m["txt"], kw)
        tkey = _nt(titolo)
        if tkey in seen_titles:
            seen.add(m["link"]); continue
        seen.add(m["link"]); seen_titles.add(tkey); new_count += 1
        items.append({"ts": m["ts"], "fonte": ch["nome"], "tier": int(ch.get("tier", 1)),
                      "titolo": titolo, "stato": stato, "team": team,
                      "giocatore": giocatore, "direzione": direzione, "club": club, "smentita": smentita,
                      "slug": slugify(giocatore), "tg": m["link"], "link": (m.get("src") or m["link"]), "lang": lang})
    items.sort(key=lambda x: x["ts"], reverse=True)
    # pulizia finale: rimuove duplicati per titolo (tiene il piu recente)
    uniq = []; _seent = set()
    for it in items:
        k = _nt(it.get("titolo"))
        if k in _seent:
            continue
        _seent.add(k); uniq.append(it)
    items = uniq[:MAX_ITEMS]
    out = {"aggiornato": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "items": items}
    json.dump(out, open(os.path.join(DATA, "ultimora.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print("ultim'ora: " + str(new_count) + " nuove, " + str(len(items)) + " totali")

if __name__ == "__main__":
    main()
