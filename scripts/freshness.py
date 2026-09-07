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
# Rose: rosters.py rinfresca ogni 5 giorni, quindi 12 giorni = due giri saltati, non un ritardo.
# I minimi sono circa un terzo dei valori reali (155 club / 4267 giocatori) perche' quante
# competizioni rispondano dipende dal piano football-data: sul free ne rispondono 3 su 8 e
# quello e' lo stato NORMALE, non un guasto.
MAX_ROSTERS_DAYS = float(os.environ.get("FRESH_ROSTERS_MAX_DAYS", "12"))
MIN_ROSTERS_CLUB = int(os.environ.get("FRESH_ROSTERS_MIN_CLUB", "50"))
MIN_ROSTERS_GIOCATORI = int(os.environ.get("FRESH_ROSTERS_MIN_GIOCATORI", "1400"))
# quota massima di club con rose EREDITATE da un giro precedente: sopra questa, il file e' pieno ma vecchio.
# Sul piano free di football-data rispondono 3 competizioni su 8, quindi una quota alta di ereditati e' la
# NORMALITA', non un guasto: la soglia va tenuta larga o la sentinella diventa rossa tutti i giorni.
MAX_ROSTERS_EREDITATI = float(os.environ.get("FRESH_ROSTERS_MAX_EREDITATI", "0.9"))
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

def check_rosters():
    """data/rosters.json e' l'anagrafica giocatore -> club: la usano build.roster_club() e
    brain.is_coach(). Se invecchia o si svuota sbagliano in silenzio, e nessuno la guardava:
    lo step di rosters.py in update.yml ha `|| echo`, quindi un rifiuto non si vede."""
    d = load(os.path.join(DATA, "rosters.json"))
    if not d:
        return
    rose = d.get("rose") or {}
    club = len(rose); gio = sum(len(v or []) for v in rose.values())
    ered = d.get("ereditati") or {}; comp = d.get("competizioni") or {}
    giorni = age_hours(d.get("updated")) / 24.0
    notes.append("rose: %d club, %d giocatori, %d ereditati, %s, competizioni ok %s / senza dati %s / ko %s"
                 % (club, gio, len(ered), ("%.1f giorni" % giorni) if d.get("updated") else "data ignota",
                    comp.get("ok") if comp.get("ok") is not None else "?", comp.get("senza_dati") or [], comp.get("ko") or []))
    if not d.get("updated"):
        errors.append("rosters.json: manca il campo 'updated', non si sa di quando sono le rose")
    elif giorni > MAX_ROSTERS_DAYS:
        errors.append("rosters.json: rose aggiornate %.1f giorni fa (max %.0f): il refresh non passa piu'" % (giorni, MAX_ROSTERS_DAYS))
    if club < MIN_ROSTERS_CLUB:
        errors.append("rosters.json: solo %d club (min %d)" % (club, MIN_ROSTERS_CLUB))
    if gio < MIN_ROSTERS_GIOCATORI:
        errors.append("rosters.json: solo %d giocatori (min %d)" % (gio, MIN_ROSTERS_GIOCATORI))
    # Il conteggio dei club e dei giocatori NON dice se il dato e' fresco: da quando i club delle competizioni
    # fallite si ereditano dallo snapshot precedente, un file pieno di dati vecchi ha esattamente gli stessi
    # numeri di un file appena scaricato. Gli unici due segnali che distinguono le due cose sono quante
    # competizioni hanno portato giocatori e quanti club sono ereditati.
    ok = comp.get("ok")
    if ok is not None and len(ok) == 0:
        errors.append("rosters.json: NESSUNA competizione ha portato giocatori nell'ultimo giro "
                      "(senza dati %s, fallite %s): le rose sul disco sono tutte ereditate"
                      % (comp.get("senza_dati") or [], comp.get("ko") or []))
    if club and len(ered) > club * MAX_ROSTERS_EREDITATI:
        errors.append("rosters.json: %d club su %d (%.0f%%) hanno rose ereditate dai giri precedenti (max %.0f%%): "
                      "football-data sta rispondendo per poche competizioni"
                      % (len(ered), club, 100.0 * len(ered) / club, 100.0 * MAX_ROSTERS_EREDITATI))
    vecchi = [v for v in ered.values() if v]
    if vecchi:
        eta = age_hours(min(vecchi)) / 24.0
        notes.append("rose: il dato ereditato piu' vecchio risale a %.1f giorni fa" % eta)
        if eta > MAX_ROSTERS_DAYS:
            errors.append("rosters.json: c'e' una rosa ereditata da %.1f giorni (max %.0f): quel club non viene "
                          "aggiornato da troppo tempo" % (eta, MAX_ROSTERS_DAYS))

    b = d.get("blocco") or {}
    if b:
        # rosters.py ha rifiutato l'ultimo scarico: le rose sul disco sono quelle di prima e
        # restano ferme finche' qualcuno non guarda. E' esattamente il guasto silenzioso.
        errors.append("rosters.json: scarico del %s RIFIUTATO perche' monco (%s) - le rose sono ferme"
                      % (b.get("quando"), b.get("motivo")))
    for a in d.get("avvisi") or []:
        errors.append("rosters.json: " + str(a))

def check_render():
    """Le pagine statiche SEO (render_site.py) devono esserci e avere contenuto: kb/SEO.md §0.1."""
    idx = os.path.join(ROOT, "index.html")
    try:
        s = open(idx, encoding="utf-8").read()
    except Exception as e:
        errors.append("index.html illeggibile (%s)" % e); return
    import re
    m = re.search(r"<!--static:lead-->(.*?)<!--/static:lead-->", s, re.S)
    if not m or len(m.group(1)) < 200: errors.append("index.html: blocco statico di apertura vuoto (render_site.py non ha girato?)")
    for f in ("squadre/index.html", "campionati/index.html", "sitemap-squadre.xml", "llms.txt"):
        if not os.path.exists(os.path.join(ROOT, f)): errors.append(f + ": manca (render_site.py)")
    try:
        if "sitemapindex" not in open(os.path.join(ROOT, "sitemap.xml"), encoding="utf-8").read(): errors.append("sitemap.xml non e' un indice")
    except Exception:
        errors.append("sitemap.xml manca")
    notes.append("render: pagine statiche presenti")

def main():
    for lang in LANGS:
        check_lang(lang)
    check_competizioni()
    check_rosters()
    check_render()
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
