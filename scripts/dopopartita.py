#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""TransferBeat - dopopartita.py: il dossier delle partite della sera, per l'articolo DOPOPARTITA delle 23.

Perche' uno script e non la lettura di data/competizioni.json. Alle 23 quel file e' fermo al giro delle 22 di
update.yml, partito con le partite delle 20:45 ancora in corso: chi scrivesse da li' troverebbe "in corso" e sarebbe
tentato di completare il risultato da un titolo. Qui i dati si prendono da API-Football nel momento in cui servono e,
se una partita non e' finita, lo script aspetta invece di lasciare un buco da riempire a occhio. Come dossier.py, i
numeri li scrive il codice; l'articolo li racconta.

Uso:  py -X utf8 scripts/dopopartita.py [--data AAAA-MM-GG] [--attendi MINUTI]
Senza --data il giorno e' quello del turno di redazione (se la pianificata 'dopopartita' ha il turno), altrimenti
oggi in ora italiana: cosi' un rilancio dopo mezzanotte racconta ancora la sera giusta.
Scrive data/dossier/dopopartita-AAAA-MM-GG.json e .md.

NESSUNA ATTESA SUPERA --attendi (consigliato 8): lo strumento Bash delle pianificate ha un limite di 10 minuti.
Se allo scadere una partita e' ancora in corso e non e' passato il tempo massimo della partita, esce con 12 e va
rilanciato; oltre il tempo massimo (calcio d'inizio + 2 ore e 45) procede con le partite finite.

Uscite: 0 dossier pronto · 10 nessuna partita serale · 11 nessuna partita finita entro il tempo massimo ·
12 partite ancora in corso: rilanciare lo stesso comando · 1 errore (chiave, API, dati incompleti).
"""
import argparse, datetime as dt, json, os, re, subprocess, sys, time

QUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, QUI)
from fanta_common import af_get, SEASON                   # noqa: E402

RADICE = os.path.dirname(QUI)
USCITA = os.path.join(RADICE, "data", "dossier")
ORA_SERALE = "17:30"            # calcio d'inizio (ora italiana) da cui una partita e' "della sera"
DURATA_MASSIMA_MIN = 165        # calcio d'inizio + supplementari e rigori: oltre, una partita non si aspetta piu'
ITALIA = 768
# lega -> (nome, priorita' con squadra italiana, priorita' senza, filtro). 1 apre il pezzo, 6 va fra "le altre".
LEGHE = {
    135: ("Serie A", 1, 1, "tutte"),
    32: ("Qualificazioni ai Mondiali", 2, None, "italia"), 960: ("Qualificazioni agli Europei", 2, None, "italia"),
    5: ("Nations League", 2, None, "italia"), 1: ("Mondiali", 2, None, "italia"), 4: ("Europei", 2, None, "italia"),
    10: ("Amichevole", 2, None, "italia"),
    2: ("Champions League", 3, 6, "tutte"),
    137: ("Coppa Italia", 4, 4, "tutte"), 547: ("Supercoppa Italiana", 4, 4, "tutte"),
    3: ("Europa League", 5, None, "italiane"), 848: ("Conference League", 5, None, "italiane"),
    39: ("Premier League", 6, 6, "tutte"), 140: ("Liga", 6, 6, "tutte"), 78: ("Bundesliga", 6, 6, "tutte"), 61: ("Ligue 1", 6, 6, "tutte"),
}
FINITE = {"FT", "AET", "PEN"}
NON_GIOCABILI = {"PST", "CANC", "ABD", "AWD", "WO"}
IN_CORSO = {"1H", "HT", "2H", "ET", "BT", "P", "LIVE", "INT", "SUSP"}
STATO_IT = {"NS": "non ancora iniziata", "TBD": "orario da definire", "1H": "primo tempo in corso", "HT": "intervallo",
            "2H": "secondo tempo in corso", "ET": "supplementari in corso", "BT": "pausa prima dei supplementari",
            "P": "rigori in corso", "INT": "interrotta", "SUSP": "sospesa", "LIVE": "in corso",
            "PST": "rinviata", "CANC": "annullata", "ABD": "abbandonata", "AWD": "risultato a tavolino", "WO": "vittoria a tavolino"}
STAT = [("Ball Possession", "Possesso palla"), ("Total Shots", "Tiri totali"), ("Shots on Goal", "Tiri in porta"),
        ("expected_goals", "xG (gol attesi)"), ("Corner Kicks", "Calci d'angolo"), ("Goalkeeper Saves", "Parate"),
        ("Passes %", "Precisione passaggi"), ("Fouls", "Falli"), ("Offsides", "Fuorigioco")]


class Errore(RuntimeError):
    pass


# ----------------------------------------------------------------------------------------------- tempo e turno
def ora_roma(t=None):
    """Ora italiana senza tzdata: stessa regola di redazione.py (ultima domenica di marzo e di ottobre, 01:00 UTC)."""
    t = (t or dt.datetime.now(dt.timezone.utc)).astimezone(dt.timezone.utc)

    def ultima_dom(m):
        g = dt.date(t.year, m, 31)
        while g.weekday() != 6:
            g -= dt.timedelta(days=1)
        return dt.datetime.combine(g, dt.time(1), dt.timezone.utc)
    off = 2 if ultima_dom(3) <= t < ultima_dom(10) else 1
    return (t + dt.timedelta(hours=off)).replace(tzinfo=dt.timezone(dt.timedelta(hours=off)))


def file_turno():
    try:
        gd = subprocess.run(["git", "rev-parse", "--absolute-git-dir"], cwd=RADICE, capture_output=True, text=True).stdout.strip()
        return os.path.join(gd, "redazione.lock") if gd else None
    except OSError:
        return None


def turno_dopopartita():
    p = file_turno()
    try:
        t = json.load(open(p, encoding="utf-8")) if p else None
        return t if t and t.get("pianificata") == "dopopartita" else None
    except (OSError, ValueError):
        return None


def battito():
    """Segno di vita sul turno: mentre si aspettano le partite nessun'altra pianificata deve crederlo abbandonato."""
    p = file_turno()
    if p and os.path.exists(p):
        try:
            os.utime(p, None)
        except OSError:
            pass


def inizio_ts(f):
    return (f.get("fixture") or {}).get("timestamp") or 0


def inizio_locale(f):
    """Ora italiana dal timestamp, mai dalla stringa `date`, che dipende dal parametro timezone della chiamata: il
    dettaglio per id la restituisce in UTC, e "Napoli-Bologna ore 16:00" invece delle 18:00 e' un errore che passa
    in un articolo senza che nessuno se ne accorga."""
    ts = inizio_ts(f)
    return ora_roma(dt.datetime.fromtimestamp(ts, dt.timezone.utc)).strftime("%H:%M") if ts else ""


def turno_it(turno):
    for schema, testo in ((r"Regular Season - (\d+)$", "%sª giornata"), (r"League Stage - (\d+)$", "%sª giornata della fase campionato")):
        m = re.match(schema, turno or "")
        if m:
            return testo % m.group(1)
    return turno or "turno non indicato"


# ----------------------------------------------------------------------------------------------- selezione
def squadre_serie_a():
    """{id: partite di Serie A giocate} da data/stats/teams.json. Serve due volte: per riconoscere le italiane nelle
    coppe e per verificare che la classifica contenga le partite di stasera."""
    try:
        d = json.load(open(os.path.join(RADICE, "data", "stats", "teams.json"), encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise Errore("data/stats/teams.json illeggibile (%s): senza, le coppe perderebbero le italiane in silenzio" % e)
    out = {}
    for k, v in (d.get("teams") or {}).items():
        if isinstance(v, dict) and v.get("league") in (135, "135"):
            out[int(v.get("id") or k)] = (((v.get("fixtures") or {}).get("played") or {}).get("total"))
    if len(out) < 18:
        raise Errore("data/stats/teams.json ha solo %d squadre di Serie A: dato incompleto, non procedo" % len(out))
    return out


def priorita(f, italiane):
    lid = f["league"]["id"]
    if lid not in LEGHE:
        return None
    _, con, senza, filtro = LEGHE[lid]
    casa, ospite = f["teams"]["home"]["id"], f["teams"]["away"]["id"]
    if filtro == "italia":
        return con if ITALIA in (casa, ospite) else None
    ha_italiana = bool(set(italiane) & {casa, ospite})
    return con if ha_italiana else senza


def serali(giorno, italiane):
    fx = af_get("/fixtures", date=giorno.isoformat(), timezone="Europe/Rome")
    out = []
    for f in fx:
        p = priorita(f, italiane)
        if p is not None and inizio_locale(f) >= ORA_SERALE:
            f["_priorita"] = p
            f["_italiana"] = bool(set(italiane) & {f["teams"]["home"]["id"], f["teams"]["away"]["id"]}) or \
                ITALIA in (f["teams"]["home"]["id"], f["teams"]["away"]["id"])
            out.append(f)
    return sorted(out, key=lambda f: (f["_priorita"], not f["_italiana"], inizio_ts(f), f["league"]["id"]))


# ----------------------------------------------------------------------------------------------- analisi
def minuto(ev):
    t = ev.get("time") or {}
    return "%s%s'" % (t.get("elapsed"), ("+%s" % t["extra"]) if t.get("extra") else "")


def numero(v):
    if v in (None, ""):
        return None
    if isinstance(v, str) and v.endswith("%"):
        v = v[:-1]
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def bonus_regolamento():
    try:
        from fanta_voti import BONUS
        return dict(BONUS)
    except Exception:
        return None


def analizza(d, bonus):
    f, lg, sq = d["fixture"], d["league"], d["teams"]
    casa, ospite = sq["home"], sq["away"]
    squadra_di = {casa["id"]: casa["name"], ospite["id"]: ospite["name"]}
    avversaria = {casa["id"]: ospite["id"], ospite["id"]: casa["id"]}
    sc = d.get("score") or {}

    # nomi completi e squadra di ogni giocatore, per id: gli eventi e le formazioni hanno l'iniziale ("S. Lobotka")
    nome_di, team_di = {}, {}
    for lato in d.get("players") or []:
        for p in lato.get("players") or []:
            nome_di[p["player"]["id"]] = p["player"]["name"]
            team_di[p["player"]["id"]] = lato["team"]["id"]

    def nome(persona):
        persona = persona or {}
        return nome_di.get(persona.get("id")) or persona.get("name")

    m = {"id": f["id"], "competizione": LEGHE[lg["id"]][0], "turno": lg.get("round"), "turno_it": turno_it(lg.get("round")),
         "inizio": inizio_locale(d), "stadio": (f.get("venue") or {}).get("name"), "citta": (f.get("venue") or {}).get("city"),
         "arbitro": (f.get("referee") or "").split(",")[0].strip() or None, "stato": f["status"]["short"],
         "casa": casa["name"], "ospite": ospite["name"], "risultato": [d["goals"]["home"], d["goals"]["away"]],
         "novanta": [(sc.get("fulltime") or {}).get("home"), (sc.get("fulltime") or {}).get("away")],
         "primo_tempo": [(sc.get("halftime") or {}).get("home"), (sc.get("halftime") or {}).get("away")],
         "rigori": [(sc.get("penalty") or {}).get("home"), (sc.get("penalty") or {}).get("away")]}

    gol, sbagliati, rossi, var, lotteria = [], [], [], [], []
    gialli, gia_ammoniti = {casa["name"]: [], ospite["name"]: []}, set()
    parziale, gol_senza_autore = [0, 0], 0
    for ev in d.get("events") or []:
        tipo, det = ev.get("type"), ev.get("detail") or ""
        chi_id = (ev.get("player") or {}).get("id")
        chi = nome(ev.get("player"))
        ev_team = (ev.get("team") or {}).get("id")
        if (ev.get("comments") or "") == "Penalty Shootout":
            # la lotteria dei rigori non e' fatta di gol della partita: va raccontata a parte
            lotteria.append({"giocatore": chi, "squadra": squadra_di.get(team_di.get(chi_id, ev_team)),
                             "esito": "segnato" if tipo == "Goal" and det != "Missed Penalty" else "sbagliato"})
            continue
        if tipo == "Goal" and det == "Missed Penalty":
            sbagliati.append({"minuto": minuto(ev), "giocatore": chi, "squadra": squadra_di.get(team_di.get(chi_id, ev_team))})
        elif tipo == "Goal":
            autogol = det == "Own Goal"
            beneficiaria = ev_team
            if autogol and chi_id in team_di:
                beneficiaria = avversaria.get(team_di[chi_id], ev_team)
            if beneficiaria in avversaria:
                parziale[0 if beneficiaria == casa["id"] else 1] += 1
            if not chi:
                gol_senza_autore += 1
                continue
            gol.append({"minuto": minuto(ev), "giocatore": chi,
                        "squadra_giocatore": squadra_di.get(team_di.get(chi_id, avversaria.get(beneficiaria) if autogol else beneficiaria)),
                        "a_favore_di": squadra_di.get(beneficiaria),
                        "assist": None if autogol else nome(ev.get("assist")),
                        "tipo": "autogol" if autogol else ("rigore" if det == "Penalty" else "azione"),
                        "parziale": "%d-%d" % tuple(parziale)})
        elif tipo == "Card" and det in ("Red Card", "Second Yellow card"):
            doppia = det == "Second Yellow card" or chi_id in gia_ammoniti
            rossi.append({"minuto": minuto(ev), "giocatore": chi, "squadra": squadra_di.get(team_di.get(chi_id, ev_team)),
                          "motivo": "doppia ammonizione" if doppia else "rosso diretto"})
        elif tipo == "Card" and det == "Yellow Card":
            s = squadra_di.get(team_di.get(chi_id, ev_team))
            if chi_id not in gia_ammoniti and chi:
                gialli.setdefault(s, []).append(chi)
            gia_ammoniti.add(chi_id)
        elif tipo == "Var":
            var.append({"minuto": minuto(ev), "squadra": squadra_di.get(ev_team), "decisione": det, "giocatore": chi})
    ufficiale = [x or 0 for x in m["risultato"]]
    m["gol_coerenti"] = parziale == ufficiale and not gol_senza_autore
    if not m["gol_coerenti"]:
        for g in gol:
            g["parziale"] = None                          # parziali calcolati su eventi sbagliati: meglio non darli
    m.update(gol=gol, gol_senza_autore=gol_senza_autore, rigori_sbagliati=sbagliati, espulsioni=rossi, ammoniti=gialli,
             var=var, lotteria=lotteria, somma_eventi=parziale)

    stat = {}
    for lato in d.get("statistics") or []:
        valori = {s["type"]: s.get("value") for s in lato.get("statistics") or []}
        stat[squadra_di.get(lato["team"]["id"], lato["team"]["name"])] = {et: valori.get(k) for k, et in STAT}
    m["statistiche"] = stat

    m["formazioni"] = {squadra_di.get(lu["team"]["id"], lu["team"]["name"]): {
        "modulo": lu.get("formation"), "allenatore": (lu.get("coach") or {}).get("name"),
        "titolari": [nome(p.get("player")) for p in lu.get("startXI") or []]} for lu in d.get("lineups") or []}

    giocatori, fanta, portieri = [], [], {}
    for lato in d.get("players") or []:
        tid = lato["team"]["id"]
        squadra = squadra_di.get(tid, lato["team"]["name"])
        for p in lato.get("players") or []:
            s = (p.get("statistics") or [{}])[0]
            g = s.get("games") or {}
            minuti = g.get("minutes") or 0
            if not minuti:
                continue
            gl, cards, pen = s.get("goals") or {}, s.get("cards") or {}, s.get("penalty") or {}
            riga = {"id": p["player"]["id"], "giocatore": p["player"]["name"], "squadra": squadra, "ruolo": g.get("position"),
                    "minuti": minuti, "voto_statistico": numero(g.get("rating")), "gol": gl.get("total") or 0,
                    "assist": gl.get("assists") or 0, "subiti": gl.get("conceded"), "gialli": cards.get("yellow") or 0,
                    "rossi": cards.get("red") or 0, "rig_sbagliati": pen.get("missed") or 0, "rig_parati": pen.get("saved") or 0}
            giocatori.append(riga)
            if riga["ruolo"] == "G":
                portieri.setdefault(tid, []).append(riga)
    # gol subiti dei portieri: in alcune competizioni (Champions, Coppa Italia) API-Football non li da'. Se in porta
    # ne ha giocato uno solo, sono i gol dell'avversaria; se due, e il dato manca, si dichiara che manca.
    avvisi_portieri = []
    for tid, lista in portieri.items():
        lato_avv = 1 if tid == casa["id"] else 0
        for r in lista:
            if r["subiti"] is None:
                if len(lista) == 1 and m["gol_coerenti"]:
                    r["subiti"] = ufficiale[lato_avv]
                else:
                    avvisi_portieri.append("%s (%s): gol subiti non disponibili" % (r["giocatore"], r["squadra"]))
    m["avvisi_portieri"] = avvisi_portieri

    if bonus:
        for r in giocatori:
            voci, totale = [], 0.0
            for chiave, campo, etichetta in (("gol", "gol", "gol"), ("assist", "assist", "assist"),
                                             ("rig_sbagliato", "rig_sbagliati", "rigore sbagliato"),
                                             ("rig_parato", "rig_parati", "rigore parato"), ("amm", "gialli", "ammonizione"),
                                             ("esp", "rossi", "espulsione")):
                n = r[campo]
                if n:
                    voci.append("%s %s (%+g)" % (n, etichetta, n * bonus[chiave]))
                    totale += n * bonus[chiave]
            if r["ruolo"] == "G" and r["subiti"]:
                voci.append("%s gol subiti (%+g)" % (r["subiti"], r["subiti"] * bonus["gol_subito"]))
                totale += r["subiti"] * bonus["gol_subito"]
            if voci:
                fanta.append({"giocatore": r["giocatore"], "squadra": r["squadra"], "voci": voci, "totale": totale})
        for g in gol:
            if g["tipo"] == "autogol":
                fanta.append({"giocatore": g["giocatore"], "squadra": g["squadra_giocatore"],
                              "voci": ["autogol (%+g)" % bonus["autogol"]], "totale": bonus["autogol"]})
    valutati = [x for x in giocatori if x["voto_statistico"] is not None and x["minuti"] >= 30]
    m["migliori"] = sorted(valutati, key=lambda x: -x["voto_statistico"])[:4]
    m["peggiori"] = sorted(valutati, key=lambda x: x["voto_statistico"])[:3]
    m["fantacalcio"] = sorted(fanta, key=lambda x: -x["totale"])
    m["giocate_serie_a"] = {casa["id"]: casa["name"], ospite["id"]: ospite["name"]}
    return m


def classifica_serie_a(partite_sa, giocate_prima):
    """Classifica verificata: per ogni squadra di stasera le partite giocate devono essere quelle che aveva PRIMA
    (data/stats/teams.json, aggiornato la notte precedente) piu' una. Il numero della giornata non basta: con un
    recupero stasera la squadra puo' avere meno partite del turno e la classifica sembrerebbe aggiornata."""
    righe = af_get("/standings", league=135, season=SEASON)
    tabella = righe[0]["league"]["standings"][0] if righe else []
    stasera = {}
    for p in partite_sa:
        stasera.update(p["giocate_serie_a"])
    out, dubbi = [], []
    for r in tabella:
        tid, nome = r["team"]["id"], r["team"]["name"]
        giocate = (r.get("all") or {}).get("played")
        if tid in stasera:
            prima = giocate_prima.get(tid)
            if prima is None or giocate is None:
                dubbi.append("%s: partite giocate prima di stasera non note, classifica non verificabile" % nome)
            elif giocate == prima:
                dubbi.append("%s risulta ancora a %d partite: la partita di stasera non e' contata" % (nome, giocate))
            elif giocate != prima + 1:
                dubbi.append("%s: %d partite in classifica, %d prima di stasera: conto che non torna" % (nome, giocate, prima))
        out.append({"pos": r["rank"], "squadra": nome, "punti": r["points"], "giocate": giocate,
                    "diff_reti": r.get("goalsDiff"), "stasera": tid in stasera})
    return out, dubbi


# ----------------------------------------------------------------------------------------------- dossier leggibile
def riga_risultato(m):
    testo = "%s %s-%s %s" % (m["casa"], m["risultato"][0], m["risultato"][1], m["ospite"])
    if m["stato"] in ("AET", "PEN") and m["novanta"][0] is not None:
        testo += " (%s-%s al 90', %s dopo i supplementari)" % (m["novanta"][0], m["novanta"][1],
                                                                "%s-%s" % tuple(m["risultato"]))
    if m["stato"] == "PEN" and m["rigori"][0] is not None:
        testo += ", %s-%s ai rigori" % tuple(m["rigori"])
    return testo


def scrivi_md(dossier):
    L = []
    a = L.append
    a("# DOSSIER DOPOPARTITA — %s" % dossier["data"])
    a("")
    a("Generato alle %s (ora italiana) da API-Football. Partite con calcio d'inizio dalle %s in poi." % (dossier["generato"], ORA_SERALE))
    a("REGOLA: ogni risultato, minuto, marcatore e numero dell'articolo viene da questo dossier. Se un dato qui non c'e', "
      "nell'articolo non c'e'. Le partite nella sezione NON CONCLUSE non hanno un risultato da scrivere.")
    a("Nomi: sono quelli completi di API-Football per id. Usali cosi' come sono.")
    a("")
    for i, m in enumerate(dossier["principali"], 1):
        a("## %d. %s — %s, %s" % (i, riga_risultato(m), m["competizione"], m["turno_it"]))
        a("- Calcio d'inizio %s · %s%s · arbitro %s" % (m["inizio"], m["stadio"] or "stadio non indicato",
                                                     (", " + m["citta"]) if m.get("citta") else "", m["arbitro"] or "non indicato"))
        a("- Primo tempo: %s-%s" % tuple(m["primo_tempo"]))
        a("")
        a("### Gol ed episodi")
        if m["gol"]:
            for g in m["gol"]:
                if g["tipo"] == "autogol":
                    a("- %s autogol di %s (%s), a favore di %s%s" % (g["minuto"], g["giocatore"], g["squadra_giocatore"],
                                                                     g["a_favore_di"], " → " + g["parziale"] if g["parziale"] else ""))
                else:
                    a("- %s %s (%s)%s%s%s" % (g["minuto"], g["giocatore"], g["squadra_giocatore"],
                                              " su assist di %s" % g["assist"] if g.get("assist") else "",
                                              " — su rigore" if g["tipo"] == "rigore" else "",
                                              " → " + g["parziale"] if g["parziale"] else ""))
        else:
            a("- nessun gol")
        if not m["gol_coerenti"]:
            a("- ATTENZIONE: gli eventi dei gol NON tornano con il risultato ufficiale (eventi: %d-%d, ufficiale: %s-%s%s). "
              "Usa SOLO il risultato ufficiale; i marcatori qui sopra sono quelli degli eventi con un autore, senza parziali: "
              "non attribuire altri gol e non scrivere la sequenza." % (m["somma_eventi"][0], m["somma_eventi"][1],
                                                                          m["risultato"][0], m["risultato"][1],
                                                                          ", %d gol senza autore" % m["gol_senza_autore"] if m["gol_senza_autore"] else ""))
        for r in m["rigori_sbagliati"]:
            a("- rigore sbagliato: %s (%s) al %s" % (r["giocatore"], r["squadra"], r["minuto"]))
        for r in m["espulsioni"]:
            a("- espulso: %s (%s) al %s, %s" % (r["giocatore"], r["squadra"], r["minuto"], r["motivo"]))
        for v in m["var"]:
            a("- VAR al %s: %s (%s%s)" % (v["minuto"], v["decisione"], v["squadra"], ", " + v["giocatore"] if v.get("giocatore") else ""))
        amm = ["%s: %s" % (k, ", ".join(v)) for k, v in m["ammoniti"].items() if v]
        a("- ammoniti — " + ("; ".join(amm) if amm else "nessuno"))
        if m["lotteria"]:
            a("- lotteria dei rigori, in ordine: " + "; ".join("%s (%s) %s" % (x["giocatore"], x["squadra"], x["esito"]) for x in m["lotteria"]))
        a("")
        if m["statistiche"]:
            a("### Numeri della partita")
            squadre = list(m["statistiche"])
            a("| | %s |" % " | ".join(squadre))
            a("|---|%s|" % "|".join("---" for _ in squadre))
            for _, et in STAT:
                a("| %s | %s |" % (et, " | ".join("non disponibile" if m["statistiche"][s].get(et) is None else str(m["statistiche"][s][et]) for s in squadre)))
            a("")
        if m["formazioni"]:
            a("### Formazioni")
            for s, fz in m["formazioni"].items():
                a("- %s (%s, all. %s): %s" % (s, fz["modulo"] or "modulo non indicato", fz["allenatore"] or "non indicato", ", ".join(x for x in fz["titolari"] if x)))
            a("")
        a("### Migliori e peggiori secondo il voto STATISTICO di API-Football (non una pagella giornalistica)")
        for x in m["migliori"]:
            a("- %s (%s) %.1f in %d' — gol %d, assist %d" % (x["giocatore"], x["squadra"], x["voto_statistico"], x["minuti"], x["gol"], x["assist"]))
        a("- peggiori: " + ("; ".join("%s (%s) %.1f" % (x["giocatore"], x["squadra"], x["voto_statistico"]) for x in m["peggiori"]) or "non disponibili"))
        a("")
        a("### In ottica fantacalcio (bonus e malus del regolamento FantaTB)")
        if dossier["bonus"] is None:
            a("- regolamento non leggibile: sezione non disponibile")
        elif m["fantacalcio"]:
            for x in m["fantacalcio"]:
                a("- %s (%s): %s → %+g" % (x["giocatore"], x["squadra"], ", ".join(x["voci"]), x["totale"]))
        else:
            a("- nessun bonus o malus")
        for w in m["avvisi_portieri"]:
            a("- ATTENZIONE: " + w + ": il malus dei gol subiti per quel portiere NON si scrive")
        a("- I fantavoti FantaTB (voto + bonus) escono nella notte: qui ci sono SOLO i bonus e i malus, non i voti.")
        a("")
    if dossier.get("classifica"):
        a("## Classifica di Serie A")
        if dossier["dubbi_classifica"]:
            a("ATTENZIONE: classifica NON verificata (%s). NON scriverla nell'articolo." % "; ".join(dossier["dubbi_classifica"]))
        for r in dossier["classifica"]:
            if r["pos"] > 8 and not r["stasera"]:
                continue
            a("- %d. %s %d %s (%d giocate, differenza reti %+d)%s" % (
                r["pos"], r["squadra"], r["punti"], "punto" if r["punti"] == 1 else "punti", r["giocate"] or 0,
                r["diff_reti"] or 0, " ← ha giocato stasera" if r["stasera"] else ""))
        a("(prime otto, piu' le squadre che hanno giocato stasera)")
        a("")
    if dossier["altre"]:
        a("## Le altre partite della sera (per il paragrafo finale)")
        for m in dossier["altre"]:
            marcatori = ", ".join("%s %s%s" % (g["giocatore"], g["minuto"], " (autogol, a favore di %s)" % g["a_favore_di"] if g["tipo"] == "autogol" else "")
                                  for g in m["gol"]) or "nessun gol"
            if not m["gol_coerenti"]:
                marcatori = "marcatori non affidabili, scrivi solo il risultato"
            a("- %s, ore %s: %s — %s" % (m["competizione"], m["inizio"], riga_risultato(m), marcatori))
        a("")
    if dossier["non_concluse"]:
        a("## NON CONCLUSE (nessun risultato da scrivere)")
        for m in dossier["non_concluse"]:
            quando = " alle %s" % dossier["generato"] if m["stato"] in IN_CORSO or m["stato"] in ("NS", "TBD") else ""
            a("- %s: %s-%s, %s%s" % (m["competizione"], m["casa"], m["ospite"], STATO_IT.get(m["stato"], m["stato"]), quando))
        a("")
    a("## COSA NON ABBIAMO")
    a("- Dichiarazioni di allenatori e giocatori: non sono nei dati. Niente virgolettati.")
    a("- Pagelle giornalistiche: i voti qui sono statistici, calcolati da API-Football. Chiamali \"voto statistico\".")
    a("- Diagnosi degli infortuni: se un giocatore esce, i dati dicono solo che e' uscito, non perche'.")
    a("- Fantavoti FantaTB: escono nella notte.")
    senza_xg = [m["casa"] + "-" + m["ospite"] for m in dossier["principali"] if any(v.get("xG (gol attesi)") is None for v in m["statistiche"].values())]
    if senza_xg:
        a("- xG non disponibili per: " + ", ".join(senza_xg))
    return "\n".join(L) + "\n"


# ----------------------------------------------------------------------------------------------- main
def dettagli(ids):
    per_id = {}
    for tentativo in range(2):
        mancanti = [i for i in ids if i not in per_id]
        for j in range(0, len(mancanti), 20):
            for d in af_get("/fixtures", ids="-".join(str(x) for x in mancanti[j:j + 20]), timezone="Europe/Rome"):
                per_id[d["fixture"]["id"]] = d
        if all(i in per_id for i in ids):
            return per_id
        time.sleep(5)
    raise Errore("API-Football non ha restituito il dettaglio di %s partite: dossier incompleto, non procedo" % len([i for i in ids if i not in per_id]))


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--data", help="giorno da raccontare (predefinito: il giorno del turno di redazione, o oggi)")
    p.add_argument("--attendi", type=int, default=0, help="minuti massimi di attesa in questa esecuzione (consigliato 8)")
    a = p.parse_args()
    try:
        if a.data:
            giorno = dt.date.fromisoformat(a.data)
        else:
            t = turno_dopopartita()
            giorno = dt.date.fromisoformat(t["giorno"]) if t and t.get("giorno") else ora_roma().date()
        giocate_prima = squadre_serie_a()
        partenza = time.time()
        while True:
            battito()
            fx = serali(giorno, giocate_prima)
            if not fx:
                print("NESSUNA PARTITA SERALE il %s nelle competizioni seguite. Niente articolo." % giorno)
                return 10
            principali = [f for f in fx if f["_priorita"] <= 5] or fx
            limite = max(inizio_ts(f) for f in principali) + DURATA_MASSIMA_MIN * 60
            da_aspettare = [f for f in principali if f["fixture"]["status"]["short"] in IN_CORSO | {"NS", "TBD"}]
            if not da_aspettare or time.time() >= limite:
                break
            resta = partenza + a.attendi * 60 - time.time()
            elenco = ", ".join("%s-%s %s" % (f["teams"]["home"]["name"], f["teams"]["away"]["name"], f["fixture"]["status"]["short"]) for f in da_aspettare)
            if resta <= 30:
                print("PARTITE ANCORA IN CORSO alle %s: %s. Rilancia lo stesso comando (tempo massimo: %s)." % (
                    ora_roma().strftime("%H:%M"), elenco, ora_roma(dt.datetime.fromtimestamp(limite, dt.timezone.utc)).strftime("%H:%M")))
                return 12
            print("%s: da concludere %s: ricontrollo fra %d secondi" % (ora_roma().strftime("%H:%M"), elenco, min(240, resta - 15)))
            time.sleep(max(15, min(240, resta - 15)))

        finite = [f for f in fx if f["fixture"]["status"]["short"] in FINITE]
        non_concluse = [f for f in fx if f["fixture"]["status"]["short"] not in FINITE]
        if not finite:
            print("PARTITE SERALI NON CONCLUSE entro il tempo massimo: %s. Niente articolo." % ", ".join(
                "%s-%s (%s)" % (f["teams"]["home"]["name"], f["teams"]["away"]["name"], f["fixture"]["status"]["short"]) for f in fx))
            return 11
        bonus = bonus_regolamento()
        per_id = dettagli([f["fixture"]["id"] for f in finite])
        partite = []
        for f in finite:
            m = analizza(per_id[f["fixture"]["id"]], bonus)
            m["priorita"], m["italiana"] = f["_priorita"], f["_italiana"]
            partite.append(m)
        principali = [m for m in partite if m["priorita"] <= 5]
        altre = [m for m in partite if m["priorita"] > 5]
        if not principali:
            principali, altre = altre[:1], altre[1:]      # solo partite estere: apre la prima, dichiarato nel prompt
        dossier = {"data": giorno.isoformat(), "generato": ora_roma().strftime("%H:%M"), "bonus": bonus,
                   "solo_estere": not any(m["priorita"] <= 5 for m in partite),
                   "principali": principali, "altre": altre,
                   "non_concluse": [{"competizione": LEGHE[f["league"]["id"]][0], "casa": f["teams"]["home"]["name"],
                                     "ospite": f["teams"]["away"]["name"], "stato": f["fixture"]["status"]["short"]} for f in non_concluse],
                   "classifica": None, "dubbi_classifica": []}
        sa = [m for m in principali if m["competizione"] == "Serie A"]
        if sa:
            try:
                dossier["classifica"], dossier["dubbi_classifica"] = classifica_serie_a(sa, giocate_prima)
            except Exception as e:
                dossier["dubbi_classifica"] = ["classifica non scaricata: %s" % e]
        os.makedirs(USCITA, exist_ok=True)
        base = os.path.join(USCITA, "dopopartita-%s" % giorno.isoformat())
        with open(base + ".json", "w", encoding="utf-8") as fh:
            json.dump(dossier, fh, ensure_ascii=False, indent=1, default=str)
        with open(base + ".md", "w", encoding="utf-8") as fh:
            fh.write(scrivi_md(dossier))
    except Errore as e:
        print("ERRORE:", e)
        return 1
    print("DOSSIER PRONTO: %s.md — %d partite principali, %d altre, %d non concluse%s%s" % (
        os.path.relpath(base, RADICE), len(principali), len(altre), len(non_concluse),
        " — SOLO PARTITE ESTERE" if dossier["solo_estere"] else "",
        " — classifica NON verificata" if dossier["dubbi_classifica"] else ""))
    for m in principali:
        print("  %s (%s)%s" % (riga_risultato(m), m["competizione"], "" if m["gol_coerenti"] else " — EVENTI GOL INCOERENTI"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
