#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""FantaTB - voti statistici di giornata (formula in kb/FANTATB.md §9).
Uso: python scripts/fanta_voti.py [giornata]   (senza argomento: ultima giornata con partite finite)
Scrive data/fanta/voti-<giornata>.json e fa upsert su player_ratings + matchdays."""
import sys, time, math
from fanta_common import *

BONUS = {"gol": 3, "assist": 1, "rig_sbagliato": -3, "rig_parato": 3, "gol_subito": -1,
         "autogol": -2, "amm": -0.5, "esp": -1}
MIN_MINUTES = 15

def half(x):
    return math.floor(x * 2 + 0.5) / 2.0

def voto_base(rating, minutes):
    if minutes < MIN_MINUTES:
        return None
    if rating is None:
        return 6.0
    return max(4.0, min(8.5, half(rating - 0.8)))

def round_of(n):
    return "Regular Season - %d" % n

def sync_matchdays(allfx):
    """Date di inizio/fine di tutte le giornate -> tabella matchdays (senza toccare lo status)."""
    by = {}
    for f in allfx:
        r = f["league"]["round"]
        if not r.startswith("Regular Season"):
            continue
        n = int(r.split("-")[-1]); d = f["fixture"]["date"]
        lo, hi = by.get(n, (d, d)); by[n] = (min(lo, d), max(hi, d))
    rows = [{"season": SEASON, "number": n, "starts_at": lo, "ends_at": hi} for n, (lo, hi) in sorted(by.items())]
    if rows:
        sb_upsert("matchdays", rows, on_conflict="season,number")
    return rows

def pick_matchday(allfx):
    done = {}
    for f in allfx:
        r = f["league"]["round"]; st = f["fixture"]["status"]["short"]
        done.setdefault(r, []).append(st in ("FT", "AET", "PEN"))
    nums = [int(r.split("-")[-1]) for r, v in done.items() if r.startswith("Regular Season") and any(v)]
    return max(nums) if nums else 1

def main():
    allfx = af_get("/fixtures", league=LEAGUE_ID, season=SEASON)
    sync_matchdays(allfx)
    md = int(sys.argv[1]) if len(sys.argv) > 1 else pick_matchday(allfx)
    fixtures = af_get("/fixtures", league=LEAGUE_ID, season=SEASON, round=round_of(md))
    print("giornata %d: %d partite" % (md, len(fixtures)))
    rows, finished, starts, ends, meta = [], 0, None, None, {}
    for f in fixtures:
        fid = f["fixture"]["id"]; st = f["fixture"]["status"]["short"]; date = f["fixture"]["date"]
        starts = min(starts or date, date); ends = max(ends or date, date)
        if st not in ("FT", "AET", "PEN"):
            continue
        finished += 1
        own = {}
        for ev in af_get("/fixtures/events", fixture=fid):
            if ev.get("type") == "Goal" and (ev.get("detail") or "").lower() == "own goal":
                own[ev["player"]["id"]] = own.get(ev["player"]["id"], 0) + 1
        for team in af_get("/fixtures/players", fixture=fid):
            for pl in team.get("players", []):
                s = (pl.get("statistics") or [{}])[0]; g = s.get("games") or {}; go = s.get("goals") or {}
                pen = s.get("penalty") or {}; cards = s.get("cards") or {}
                minutes = g.get("minutes") or 0
                try: rating = float(g["rating"]) if g.get("rating") else None
                except ValueError: rating = None
                is_gk = (g.get("position") == "G")
                meta[pl["player"]["id"]] = {"name": pl["player"]["name"], "team": team["team"]["name"], "team_id": team["team"]["id"], "pos": g.get("position")}
                b = {"gol": go.get("total") or 0, "assist": go.get("assists") or 0,
                     "rig_sbagliato": pen.get("missed") or 0, "rig_parato": (pen.get("saved") or 0) if is_gk else 0,
                     "gol_subito": (go.get("conceded") or 0) if is_gk else 0,
                     "autogol": own.get(pl["player"]["id"], 0),
                     "amm": cards.get("yellow") or 0, "esp": cards.get("red") or 0}
                b = {k: v for k, v in b.items() if v}
                vb = voto_base(rating, minutes)
                fv = None if vb is None else round(vb + sum(BONUS[k] * v for k, v in b.items()), 2)
                rows.append({"season": SEASON, "matchday": md, "player_id": pl["player"]["id"], "minutes": minutes,
                             "voto": vb, "bonus": b, "fantavoto": fv, "source": "fantatb-stat",
                             "raw": {"rating": rating, "fixture": fid, "gk": is_gk}})
        time.sleep(0.3)
    status = "rated" if fixtures and finished == len(fixtures) else ("live" if finished else "scheduled")
    save_json("voti-%02d.json" % md, {"updated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "matchday": md,
                                     "status": status, "finished": finished, "total": len(fixtures), "ratings": rows})
    print("voti: %d righe, %d/%d partite finite, %d chiamate" % (len(rows), finished, len(fixtures), calls()))
    # i giocatori non ancora nel listone (es. neo-arrivati) vanno inseriti prima, o l'FK fallisce
    best = {}   # un giocatore può comparire due volte nei tabellini API: tengo la riga con più minuti
    for r in rows:
        k = r["player_id"]
        if k not in best or r["minutes"] > best[k]["minutes"]:
            best[k] = r
    rows = list(best.values())
    known = {r["id"] for r in sb_get("players", {"select": "id", "limit": "5000"})}
    if known:
        missing = [r["player_id"] for r in rows if r["player_id"] not in known]
        if missing:   # hanno giocato ma non sono nelle rose attuali (ceduti dopo la giornata): li aggiungo inattivi
            newp = [{"id": pid, "season": SEASON, "name": meta[pid]["name"], "team": meta[pid]["team"], "team_id": meta[pid]["team_id"],
                     "role": {"G": "P", "D": "D", "M": "C", "F": "A"}.get(meta[pid]["pos"] or "", "C"), "price": 1, "active": False}
                    for pid in missing if pid in meta]
            sb_upsert("players", newp, on_conflict="id")
            print("giocatori aggiunti al listone come inattivi:", len(newp))
    if rows and sb_upsert("player_ratings", rows, on_conflict="season,matchday,player_id"):
        sb_upsert("matchdays", [{"season": SEASON, "number": md, "starts_at": starts, "ends_at": ends, "status": status}],
                  on_conflict="season,number")
        print("upsert ok")
        if status == "rated":
            print("leghe calcolate:", sb_rpc("compute_all_leagues", {"p_matchday": md}))

if __name__ == "__main__":
    main()
