#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""FantaTB - listone Serie A: rose attuali (players/squads) + statistiche stagione precedente ->
quotazione FantaTB (formula in kb/FANTATB.md §10). Scrive data/fanta/listone.json e fa upsert su players."""
import time
from fanta_common import *

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

def main():
    t0 = time.time()
    teams = af_get("/teams", league=LEAGUE_ID, season=SEASON)
    print("squadre:", len(teams))
    prev = stat_rows(SEASON - 1)
    cur = stat_rows(SEASON)
    rows = []
    for t in teams:
        tid, tname = t["team"]["id"], t["team"]["name"]
        sq = af_get("/players/squads", team=tid)
        for pl in (sq[0]["players"] if sq else []):
            role = role_of(pl.get("position"))
            st = prev.get(pl["id"]) or cur.get(pl["id"]) or {}
            rows.append({"id": pl["id"], "season": SEASON, "name": pl["name"], "team": tname, "team_id": tid,
                         "role": role, "price": price_of(role, st), "active": True,
                         "stats": {"prev": prev.get(pl["id"], {}), "cur": cur.get(pl["id"], {}), "age": pl.get("age"), "number": pl.get("number")}})
        time.sleep(0.3)
    rows.sort(key=lambda r: ("PDCA".index(r["role"]), -r["price"], r["name"]))
    save_json("listone.json", {"updated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "season": SEASON,
                               "players": [{k: r[k] for k in ("id", "name", "team", "role", "price")} for r in rows]})
    print("listone: %d giocatori, %d chiamate API, %.0fs" % (len(rows), calls(), time.time() - t0))
    if sb_upsert("players", rows, on_conflict="id"):
        print("upsert players ok")

if __name__ == "__main__":
    main()
