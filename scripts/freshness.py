#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""TransferBeat - freshness.py: la sentinella. Ultimo step di update.yml, SENZA `|| echo`.
Fallisce (exit 1) se i dati generati sono vecchi, vuoti o troppo magri: la lezione delle sei settimane
di strato AI morto a workflow verde. Soglie volutamente basse (circa un terzo dei valori reali del
2026-09-02: rumor 192, obj 70, done 68, feed 160, 59/60 squadre con voci) per non gridare al lupo.
Uso: python scripts/freshness.py           (controlla tutte le lingue)
     FRESH_MAX_HOURS=6 FRESH_MIN_VOCI=80   (soglie via ambiente)"""
import json, os, sys, time, calendar

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
LANGS = ["it", "en", "es"]
MAX_HOURS = float(os.environ.get("FRESH_MAX_HOURS", "6"))
MIN_VOCI = int(os.environ.get("FRESH_MIN_VOCI", "80"))        # somma delle quattro colonne, per lingua
MIN_SQUADRE = int(os.environ.get("FRESH_MIN_SQUADRE", "30"))  # squadre con almeno una voce
MIN_FEED = int(os.environ.get("FRESH_MIN_FEED", "40"))        # voci di feed di giornata, per lingua
MIN_TICKER = int(os.environ.get("FRESH_MIN_TICKER", "3"))
errors, notes = [], []

def age_hours(ts):
    """'2026-09-02T22:52:57' (ora UTC senza suffisso) o con 'Z' -> ore trascorse."""
    if not ts:
        return 1e9
    ts = ts.strip().replace("Z", "")[:19]
    try:
        t = calendar.timegm(time.strptime(ts, "%Y-%m-%dT%H:%M:%S"))
    except ValueError:
        return 1e9
    return (time.time() - t) / 3600.0

def load(path):
    try:
        return json.load(open(path, encoding="utf-8"))
    except Exception as e:
        errors.append("%s: illeggibile (%s)" % (os.path.relpath(path, ROOT), e)); return None

def check_lang(lang):
    b = load(os.path.join(DATA, lang, "board.json")); h = load(os.path.join(DATA, lang, "home.json"))
    if b:
        a = age_hours(b.get("aggiornato"))
        if a > MAX_HOURS: errors.append("%s/board.json: aggiornato %.1f ore fa (max %.0f)" % (lang, a, MAX_HOURS))
        sq = b.get("squadre") or {}
        cnt = {}; con_voci = 0; feed = 0
        for v in sq.values():
            col = v.get("colonne") or {}; n = 0
            for k, arr in col.items():
                cnt[k] = cnt.get(k, 0) + len(arr or []); n += len(arr or [])
            con_voci += n > 0; feed += len(v.get("feed") or [])
        tot = sum(cnt.values())
        notes.append("%s: %d squadre, %d con voci, colonne %s, feed %d, %.1f h" % (lang, len(sq), con_voci, cnt, feed, a))
        if not sq: errors.append("%s/board.json: nessuna squadra" % lang)
        if tot < MIN_VOCI: errors.append("%s/board.json: solo %d voci nelle colonne (min %d)" % (lang, tot, MIN_VOCI))
        if con_voci < MIN_SQUADRE: errors.append("%s/board.json: solo %d squadre con voci (min %d)" % (lang, con_voci, MIN_SQUADRE))
        if feed < MIN_FEED: errors.append("%s/board.json: feed di giornata con %d voci (min %d)" % (lang, feed, MIN_FEED))
        for k in ("rumor", "obj", "conf", "done"):
            if k not in cnt: errors.append("%s/board.json: colonna '%s' assente" % (lang, k))
    if h:
        a = age_hours(h.get("aggiornato"))
        if a > MAX_HOURS: errors.append("%s/home.json: aggiornato %.1f ore fa" % (lang, a))
        if len(h.get("ticker") or []) < MIN_TICKER: errors.append("%s/home.json: ticker con %d voci" % (lang, len(h.get("ticker") or [])))
        if not h.get("apertura"): errors.append("%s/home.json: nessuna apertura" % lang)
        if not h.get("secondari"): errors.append("%s/home.json: nessun secondario" % lang)

def check_competizioni():
    c = load(os.path.join(DATA, "competizioni.json"))
    if not c:
        return
    a = age_hours(c.get("aggiornato")); n = len(c.get("competizioni") or [])
    notes.append("competizioni: %d competizioni, %.1f h" % (n, a))
    if a > 26: errors.append("competizioni.json: aggiornato %.1f ore fa (max 26): football-data non risponde da un giorno" % a)
    if n < 3: errors.append("competizioni.json: solo %d competizioni" % n)

def main():
    for lang in LANGS:
        check_lang(lang)
    check_competizioni()
    for n in notes:
        print("  ", n)
    if errors:
        print("\nFRESHNESS: %d problemi" % len(errors))
        for e in errors:
            print("  !!", e)
        sys.exit(1)
    print("FRESHNESS OK")

if __name__ == "__main__":
    main()
