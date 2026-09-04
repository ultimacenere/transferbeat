#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""FantaTB - listone Serie A da API-Football (rose attuali + trasferimenti + statistiche).

  py fanta_players.py            SINCRONIZZA le rose: aggiorna squadra e stato dei giocatori già in tabella (prezzi e ruoli
                                 invariati), aggiunge i nuovi arrivati con prezzo calcolato, disattiva chi non è più in
                                 nessuna rosa di Serie A (active=false: resta nei voti, sparisce da listone e asta).
  py fanta_players.py --check    SOLO VERIFICA, non scrive nulla: differenze tra la tabella players e le rose di oggi,
                                 più i "sospetti" (in rosa secondo il feed rose, ma con un trasferimento recente altrove).
  py fanta_players.py --prezzi   LISTONE COMPLETO: come la sincronizzazione ma ricalcola prezzi e ruoli di tutti
                                 (primo listone, dopo il mercato di gennaio).

Fonti API-Football: rose attuali (players/squads, 20 chiamate: il provider le aggiorna "più volte a settimana", quindi
possono restare indietro di giorni rispetto ai trasferimenti), trasferimenti per squadra (transfers, 20 chiamate, usati
come contro-verifica), statistiche della stagione precedente (players?league=135, solo se servono prezzi nuovi).
Formula della quotazione in kb/FANTATB.md §6. Scrive data/fanta/listone.json e aggiorna la tabella players."""
import html, re, sys, time, unicodedata
from datetime import date, timedelta
from fanta_common import *

def qt_locked(old):
    """La squadra scritta da fanta_quotazioni.py (listone ufficiale, players.stats.qt) vale piu' del feed rose per 45 giorni."""
    qt = ((old or {}).get("stats") or {}).get("qt") or {}
    return bool(qt.get("date") and qt.get("team") and qt["date"] >= (date.today() - timedelta(days=45)).isoformat())

ROLE_BASE = {"P": 1, "D": 1, "C": 1, "A": 2}
ROLE_APP  = {"P": 8, "D": 10, "C": 12, "A": 14}
ROLE_GOL  = {"P": 0, "D": 3, "C": 2, "A": 1.2}
ROLE_AST  = {"P": 0, "D": 1, "C": 1, "A": 0.8}

def price_of(role, st):
    app = st.get("app", 0); mins = st.get("min", 0); gol = st.get("gol", 0); ast = st.get("ast", 0)
    rating = st.get("rating") or 0; conceded = st.get("conceded", 0)
    q = ROLE_BASE[role] + (min(app, 38) / 38.0) * ROLE_APP[role] + gol * ROLE_GOL[role] + ast * ROLE_AST[role]
    if rating > 6.5 and app >= 10:
        q += (rating - 6.5) * 10
    if role == "P" and app > 0 and conceded / app < 1:
        q += app * 0.3
    return int(max(1, min(60, round(q))))

def stat_rows(season):
    """{player_id: {app,min,gol,ast,rating,conceded}} per la Serie A di una stagione."""
    out = {}
    for it in af_get("/players", league=LEAGUE_ID, season=season):
        pid = it["player"]["id"]; agg = out.setdefault(pid, {"app": 0, "min": 0, "gol": 0, "ast": 0, "rating": None, "conceded": 0, "_r": []})
        for s in it.get("statistics", []):
            g = s.get("games") or {}; go = s.get("goals") or {}
            agg["app"] += g.get("appearences") or 0; agg["min"] += g.get("minutes") or 0
            agg["gol"] += go.get("total") or 0; agg["ast"] += go.get("assists") or 0
            agg["conceded"] += go.get("conceded") or 0
            if g.get("rating"):
                try: agg["_r"].append((float(g["rating"]), g.get("appearences") or 1))
                except ValueError: pass
    for pid, a in out.items():
        if a["_r"]:
            w = sum(n for _, n in a["_r"]); a["rating"] = round(sum(r * n for r, n in a["_r"]) / w, 2)
        a.pop("_r")
    return out

def fetch_rosters():
    """Rose attuali delle 20 squadre: (teams, righe {id,name,team,team_id,role,age,number})."""
    teams = af_get("/teams", league=LEAGUE_ID, season=SEASON)
    rows, seen, doppi = [], set(), 0
    for t in teams:
        tid, tname = t["team"]["id"], t["team"]["name"]
        sq = af_get("/players/squads", team=tid)
        for pl in (sq[0]["players"] if sq else []):
            if pl["id"] in seen:      # in due rose (trasferimento recepito a metà dal feed): tengo la prima occorrenza
                doppi += 1; continue
            seen.add(pl["id"])
            rows.append({"id": pl["id"], "name": html.unescape(pl["name"] or ""), "team": tname, "team_id": tid,
                         "role": role_of(pl.get("position")), "age": pl.get("age"), "number": pl.get("number")})
        time.sleep(0.3)
    if doppi:
        print("doppioni tra rose rimossi:", doppi)
    return teams, rows

def fetch_transfers(teams, since):
    """Ultimo trasferimento (dal `since`) di ogni giocatore che ha coinvolto una squadra di Serie A: {id: (data, da, a)}.
    Scartate le voci senza squadra di arrivo reale (id nullo, nome = nome del giocatore): sono rinnovi/fine prestito
    che il feed registra come trasferimenti, quasi tutte datate 29-30 giugno."""
    out = {}
    for t in teams:
        for it in af_get("/transfers", team=t["team"]["id"]):
            pid = it["player"]["id"]
            for tr in it.get("transfers", []):
                d = tr.get("date") or ""; tm = tr.get("teams") or {}
                dest = tm.get("in") or {}
                if not dest.get("id") or d < since or d <= out.get(pid, ("",))[0]:
                    continue
                out[pid] = (d, (tm.get("out") or {}).get("name") or "?", dest.get("name") or "?")
        time.sleep(0.3)
    return out

def board_titles():
    """Titoli della board notizie del sito (data/it/board.json): cosa dice TransferBeat sui casi dubbi."""
    try:
        b = json.load(open(os.path.join(ROOT, "data", "it", "board.json"), encoding="utf-8"))
    except Exception:
        return []
    return [(col, n.get("quando", ""), n.get("fonte", ""), n.get("titolo", ""))
            for v in b.get("squadre", {}).values() for col, items in (v.get("colonne") or {}).items() for n in items]

def deac(s):
    return unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode("ascii").lower()

def news_for(name, titles):
    """Titoli della board che citano il cognome (parola intera, senza accenti): indicativo, può prendere omonimi."""
    parts = [p for p in re.split(r"[\s.]+", deac(name)) if len(p) >= 4]
    if not parts:
        return []
    rx = re.compile(r"\b%s\b" % re.escape(parts[-1]))
    return [t for t in titles if rx.search(deac(t[3]))][:2]

def compare(rows, db, transfers):
    now = {r["id"]: r for r in rows}
    dbmap = {p["id"]: p for p in db}
    usciti = [p for p in db if p["active"] and p["id"] not in now]
    cambiati = [(p, now[p["id"]]) for p in db if p["active"] and p["id"] in now and now[p["id"]]["team"] != p["team"]]
    rientrati = [p for p in db if not p["active"] and p["id"] in now]
    nuovi = [r for r in rows if r["id"] not in dbmap]
    # sospetti: solo trasferimenti da luglio in poi (giugno = ritorni dai prestiti, poi spesso ri-prestati senza che il feed lo registri)
    lim = "%d-07-01" % SEASON
    sospetti = [(r, transfers[r["id"]]) for r in rows
                if r["id"] in transfers and transfers[r["id"]][0] >= lim and transfers[r["id"]][2] != r["team"]]
    return usciti, cambiati, rientrati, nuovi, sospetti

def report(rows, db, transfers, usciti, cambiati, rientrati, nuovi, sospetti):
    titles = board_titles()
    def dest(p):
        t = transfers.get(p["id"])
        return " -> %s (%s)" % (t[2], t[0]) if t and t[2] != p["team"] else "  (destinazione non registrata dall'API)"
    def news(name):
        return "".join("\n        board: [%s, %s, %s] %s" % (c, q, f, ti[:95]) for c, q, f, ti in news_for(name, titles))
    print("\n== Rose di oggi: %d giocatori in 20 squadre | tabella players: %d attivi, %d inattivi" %
          (len(rows), sum(1 for p in db if p["active"]), sum(1 for p in db if not p["active"])))
    print("\n-- USCITI dalla Serie A (attivi in tabella, oggi in nessuna rosa): %d" % len(usciti))
    for p in usciti:
        print("   %s %-24s %-16s q.%-3s%s%s" % (p["role"], p["name"], p["team"], p["price"], dest(p), news(p["name"])))
    print("\n-- CAMBIATO SQUADRA dentro la Serie A: %d" % len(cambiati))
    for p, r in cambiati:
        print("   %s %-24s %s -> %s" % (p["role"], p["name"], p["team"], r["team"]))
    print("\n-- RIENTRATI (erano inattivi, oggi in una rosa): %d" % len(rientrati))
    for p in rientrati:
        print("   %s %-24s %s" % (p["role"], p["name"], p["team"]))
    print("\n-- NUOVI (in rosa oggi, non in tabella): %d" % len(nuovi))
    for r in nuovi:
        print("   %s %-24s %s" % (r["role"], r["name"], r["team"]))
    print("\n-- SOSPETTI (in rosa secondo il feed rose, ma l'ultimo trasferimento li porta altrove: feed rose in ritardo?): %d" % len(sospetti))
    for r, t in sospetti:
        print("   %s %-24s in rosa %-16s ma trasferito %s -> %s il %s%s" % (r["role"], r["name"], r["team"], t[1], t[2], t[0], news(r["name"])))
    # giocatori usciti che sono già in una rosa di lega: l'admin deve svincolarli (release_player)
    ids = {p["id"] for p in usciti}
    if ids:
        ros = [x for x in sb_get("rosters", {"select": "player_id,league_id,user_id,price"}) if x["player_id"] in ids]
        if ros:
            names = {p["id"]: p["name"] for p in usciti}
            leagues = {l["id"]: l["name"] for l in sb_get("leagues", {"select": "id,name"})}
            members = {(m["league_id"], m["user_id"]): m["team_name"] for m in sb_get("league_members", {"select": "league_id,user_id,team_name"})}
            print("\n!! ATTENZIONE: giocatori usciti già acquistati in una lega (l'admin deve svincolarli con rimborso):")
            for x in ros:
                print("   %s -> lega '%s', squadra '%s', pagato %s" % (names[x["player_id"]], leagues.get(x["league_id"], "?"),
                                                                       members.get((x["league_id"], x["user_id"]), "?"), x["price"]))

def main():
    check = "--check" in sys.argv; prezzi = "--prezzi" in sys.argv
    t0 = time.time()
    teams, rows = fetch_rosters()
    transfers = fetch_transfers(teams, "%d-06-01" % SEASON)
    db = sb_get("players", {"select": "id,name,team,team_id,role,price,active,stats"})
    usciti, cambiati, rientrati, nuovi, sospetti = compare(rows, db, transfers)
    report(rows, db, transfers, usciti, cambiati, rientrati, nuovi, sospetti)
    if check:
        print("\nverifica: %d chiamate API, %.0fs, nessuna scrittura" % (calls(), time.time() - t0)); return
    dbmap = {p["id"]: p for p in db}
    stats = None
    if prezzi or nuovi or rientrati or not db:
        stats = (stat_rows(SEASON - 1), stat_rows(SEASON))
    out = []
    for r in rows:
        old = dbmap.get(r["id"])
        keep = bool(old) and old["active"] and not prezzi   # gli inattivi (aggiunti dai voti con prezzo fittizio) vengono riquotati
        official = bool(old and ((old.get("stats") or {}).get("qt")))   # ruolo e prezzo dal listone ufficiale (fanta_quotazioni.py): non si ricalcolano mai
        row = {"id": r["id"], "season": SEASON, "name": r["name"], "team": r["team"], "team_id": r["team_id"],
               "role": old["role"] if (keep or official) else r["role"], "active": True}
        if keep and qt_locked(old) and old.get("team"):
            row["team"], row["team_id"] = old["team"], old.get("team_id")   # squadra dal listone ufficiale (fanta_quotazioni.py): il feed rose e' in ritardo
        if stats:   # si aggiunge alle statistiche gia' salvate (stats.qt del listone ufficiale non va perso)
            row["stats"] = dict((old or {}).get("stats") or {}, prev=stats[0].get(r["id"], {}), cur=stats[1].get(r["id"], {}), age=r["age"], number=r["number"])
        row["price"] = old["price"] if (keep or official) else price_of(row["role"], (stats[0].get(r["id"]) or stats[1].get(r["id"]) or {}) if stats else {})
        out.append(row)
    out.sort(key=lambda r: ("PDCA".index(r["role"]), -r["price"], r["name"]))
    save_json("listone.json", {"updated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "season": SEASON,
                               "players": [{k: r[k] for k in ("id", "name", "team", "role", "price")} for r in out]})
    if sb_upsert("players", out, on_conflict="id"):
        print("\nupsert players ok: %d righe%s" % (len(out), ", prezzi e ruoli ricalcolati" if prezzi else ", prezzi e ruoli invariati"))
        if usciti:
            sb_patch("players", {"id": "in.(%s)" % ",".join(str(p["id"]) for p in usciti)}, {"active": False})
            print("disattivati (active=false):", ", ".join(p["name"] for p in usciti))
    print("listone: %d giocatori, %d chiamate API, %.0fs" % (len(out), calls(), time.time() - t0))

if __name__ == "__main__":
    main()
