#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""TransferBeat - stats_pull.py: statistiche di squadra e schede giocatore da API-Football -> data/stats/*.json
(kb/FANTATB.md §14). Le pagine le genera render_site.py (modulo render_stats.py), che legge solo questi JSON.

  py scripts/stats_pull.py               squadre + giocatori
  py scripts/stats_pull.py --squadre     classifiche (standings), statistiche di squadra (teams/statistics) e statistiche
                                         per partita (fixtures/statistics, solo le partite finite non ancora in cache)
                                         per le leghe di LEAGUES -> data/stats/teams.json, data/stats/matches.json
  py scripts/stats_pull.py --giocatori   rose di Serie A, profili, statistiche della stagione corrente (Serie A) e della
                                         precedente (tutte le competizioni, in cache per sempre), trasferimenti
                                         -> data/stats/players.json

Chiamate: squadre ~65 + ~10 per giornata nuova per lega; giocatori ~50 a regime (rose 20, stagione corrente ~27,
trasferimenti 20) più, una tantum, 1 chiamata per giocatore per la stagione precedente e 1 per i profili mancanti.
Chiave: apifootball_key.txt nella radice del repo o variabile APIFOOTBALL_KEY (come gli altri script fanta_*)."""
import os, re, sys, time
import requests
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fanta_common import af_get, api_key, calls, SEASON, LEAGUE_ID, API
from site_common import load_json, DATA          # DATA = data/ (quella di fanta_common e' data/fanta)

STATS = os.path.join(DATA, "stats")
LEAGUES = {135: "SA", 39: "PL", 140: "PD"}     # le leghe di teams.json (Serie A, Premier League, Liga)
PLAYER_LEAGUE = LEAGUE_ID                        # schede giocatore: solo Serie A (repo e quota sotto controllo)
FINISHED = ("FT", "AET", "PEN")
PAUSE = 0.25                                     # piano Pro: 300 richieste/minuto
_extra = 0

def now_iso():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

def af_one(path, **params):
    """GET che restituisce la response grezza (per gli endpoint che rispondono con un oggetto, non con una lista)."""
    global _extra
    for attempt in range(4):
        r = requests.get(API + path, headers={"x-apisports-key": api_key()}, params=params, timeout=40)
        _extra += 1
        if r.status_code == 429:
            time.sleep(10 * (attempt + 1)); continue
        r.raise_for_status(); break
    j = r.json()
    if j.get("errors"):
        raise RuntimeError("API-Football: %s" % j["errors"])
    time.sleep(PAUSE)
    return j.get("response")

def n_calls():
    return calls() + _extra

def load(name, default):
    return load_json(os.path.join(STATS, name), default) or default

def _save(name, obj):
    import json
    os.makedirs(STATS, exist_ok=True)
    with open(os.path.join(STATS, name), "w", encoding="utf-8", newline="\n") as f:
        json.dump(obj, f, ensure_ascii=False, indent=0)
        f.write("\n")

def num(v):
    """'58%' -> 58, '1.93' -> 1.93, None -> None."""
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return v
    s = str(v).strip().replace("%", "")
    try:
        f = float(s)
        return int(f) if f == int(f) and "." not in s else round(f, 2)
    except ValueError:
        return None

# ---------- squadre ----------
def minute_totals(d):
    return {k: ((v or {}).get("total") or 0) for k, v in (d or {}).items()}

def trim_team_stats(ts):
    g = ts.get("goals") or {}; gf = g.get("for") or {}; ga = g.get("against") or {}
    pen = ts.get("penalty") or {}; cards = ts.get("cards") or {}
    return {"form": ts.get("form") or "", "fixtures": ts.get("fixtures") or {},
            "goals_for": {"total": gf.get("total") or {}, "avg": {k: num(v) for k, v in (gf.get("average") or {}).items()}, "minute": minute_totals(gf.get("minute"))},
            "goals_against": {"total": ga.get("total") or {}, "avg": {k: num(v) for k, v in (ga.get("average") or {}).items()}, "minute": minute_totals(ga.get("minute"))},
            "biggest": ts.get("biggest") or {}, "clean_sheet": ts.get("clean_sheet") or {}, "failed_to_score": ts.get("failed_to_score") or {},
            "penalty": {"scored": (pen.get("scored") or {}).get("total") or 0, "missed": (pen.get("missed") or {}).get("total") or 0, "total": pen.get("total") or 0},
            "lineups": [{"formation": l.get("formation"), "played": l.get("played") or 0} for l in (ts.get("lineups") or [])],
            "cards": {"yellow": minute_totals(cards.get("yellow")), "red": minute_totals(cards.get("red"))}}

def trim_standing(r):
    def side(s):
        s = s or {}; g = s.get("goals") or {}
        return {"played": s.get("played") or 0, "win": s.get("win") or 0, "draw": s.get("draw") or 0, "lose": s.get("lose") or 0,
                "gf": g.get("for") or 0, "ga": g.get("against") or 0}
    a = side(r.get("all"))
    return {"rank": r.get("rank"), "team_id": r["team"]["id"], "name": r["team"]["name"], "points": r.get("points") or 0, "gd": r.get("goalsDiff") or 0,
            "form": r.get("form") or "", "description": r.get("description") or "", "all": a, "home": side(r.get("home")), "away": side(r.get("away"))}

def pull_teams():
    out = {"updated": now_iso(), "season": SEASON, "leagues": {}, "teams": {}}
    for lid, code in LEAGUES.items():
        st = af_one("/standings", league=lid, season=SEASON) or []
        rows = [trim_standing(r) for grp in ((st[0]["league"].get("standings") or []) if st else []) for r in grp]
        out["leagues"][str(lid)] = {"code": code, "name": (st[0]["league"]["name"] if st else code), "standings": rows}
        for r in rows:
            ts = af_one("/teams/statistics", league=lid, season=SEASON, team=r["team_id"])
            if ts:
                out["teams"][str(r["team_id"])] = dict({"id": r["team_id"], "name": r["name"], "league": lid}, **trim_team_stats(ts))
        print("  %s: %d squadre in classifica" % (code, len(rows)))
    _save("teams.json", out)
    return out

STAT_KEYS = {"Shots on Goal": "shots_on", "Shots off Goal": "shots_off", "Total Shots": "shots", "Blocked Shots": "blocked",
             "Shots insidebox": "inside", "Shots outsidebox": "outside", "Fouls": "fouls", "Corner Kicks": "corners", "Offsides": "offsides",
             "Ball Possession": "possession", "Yellow Cards": "yellow", "Red Cards": "red", "Goalkeeper Saves": "saves",
             "Total passes": "passes", "Passes accurate": "passes_ok", "Passes %": "passes_pct", "expected_goals": "xg", "goals_prevented": "gp"}

def round_no(r):
    m = re.search(r"(\d+)\s*$", r or "")
    return int(m.group(1)) if m and (r or "").startswith("Regular Season") else None

def pull_matches():
    cache = load("matches.json", {"fixtures": {}})
    fx_all = cache.setdefault("fixtures", {})
    new = 0
    for lid, code in LEAGUES.items():
        for f in af_get("/fixtures", league=lid, season=SEASON):
            fid = str(f["fixture"]["id"]); st = f["fixture"]["status"]["short"]
            if st not in FINISHED or fid in fx_all:
                continue
            stats = {}
            for side in af_get("/fixtures/statistics", fixture=int(fid)):
                stats[str(side["team"]["id"])] = {STAT_KEYS[s["type"]]: num(s.get("value")) for s in side.get("statistics", []) if s.get("type") in STAT_KEYS}
            fx_all[fid] = {"league": lid, "round": round_no(f["league"]["round"]), "date": f["fixture"]["date"],
                           "home": f["teams"]["home"]["id"], "away": f["teams"]["away"]["id"],
                           "home_name": f["teams"]["home"]["name"], "away_name": f["teams"]["away"]["name"],
                           "goals": [f["goals"]["home"], f["goals"]["away"]], "stats": stats}
            new += 1
            time.sleep(PAUSE)
        print("  %s: partite in cache %d" % (code, sum(1 for x in fx_all.values() if x["league"] == lid)))
    cache["updated"] = now_iso(); cache["season"] = SEASON
    _save("matches.json", cache)
    print("  nuove partite scaricate:", new)
    return cache

# ---------- giocatori ----------
def trim_block(s):
    t = s.get("team") or {}; l = s.get("league") or {}
    out = {"team": {"id": t.get("id"), "name": t.get("name")},
           "league": {"id": l.get("id"), "name": l.get("name"), "country": l.get("country"), "season": l.get("season")}}
    for k in ("games", "substitutes", "shots", "goals", "passes", "tackles", "duels", "dribbles", "fouls", "cards", "penalty"):
        out[k] = s.get(k) or {}
    g = out["games"]
    if g.get("rating") is not None:
        g["rating"] = num(g["rating"])
    p = out["passes"]
    if p.get("accuracy") is not None:
        p["accuracy"] = num(p["accuracy"])
    return out

def profile_of(pl):
    b = pl.get("birth") or {}
    return {"id": pl["id"], "name": pl.get("name"), "first": pl.get("firstname"), "last": pl.get("lastname"),
            "birth": {"date": b.get("date"), "place": b.get("place"), "country": b.get("country")},
            "nationality": pl.get("nationality"), "height": num(pl.get("height")), "weight": num(pl.get("weight")),
            "injured": bool(pl.get("injured")), "photo": pl.get("photo")}

def trim_transfers(items):
    """[(data, tipo, da, a)] senza doppioni (il feed ripete lo stesso movimento con 'Milan' e 'AC Milan')."""
    out, seen = [], set()
    for tr in items or []:
        tm = tr.get("teams") or {}; i = tm.get("in") or {}; o = tm.get("out") or {}
        k = (tr.get("date"), i.get("id"), o.get("id"))
        if k in seen or not tr.get("date"):
            continue
        seen.add(k)
        out.append({"date": tr.get("date"), "type": tr.get("type"), "from": {"id": o.get("id"), "name": o.get("name")}, "to": {"id": i.get("id"), "name": i.get("name")}})
    out.sort(key=lambda x: x["date"])
    return out

def pull_players():
    P = load("players.json", {"players": {}})
    players = P.setdefault("players", {})
    prev_season = SEASON - 1
    # 1) rose attuali
    teams = af_get("/teams", league=PLAYER_LEAGUE, season=SEASON)
    roster = {}
    for t in teams:
        tid, tname = t["team"]["id"], t["team"]["name"]
        sq = af_get("/players/squads", team=tid)
        for pl in (sq[0]["players"] if sq else []):
            roster.setdefault(pl["id"], {"team": tid, "team_name": tname, "number": pl.get("number"), "position": pl.get("position"), "photo": pl.get("photo"), "sq_name": pl.get("name")})
        time.sleep(PAUSE)
    print("  rose: %d giocatori in %d squadre" % (len(roster), len(teams)))
    # 2) statistiche stagione corrente (Serie A) di chi ha giocato + profilo
    cur = {}
    for it in af_get("/players", league=PLAYER_LEAGUE, season=SEASON):
        pid = it["player"]["id"]
        p = players.setdefault(str(pid), {})
        p.update(profile_of(it["player"]))
        cur.setdefault(pid, []).extend(trim_block(s) for s in it.get("statistics", []))
    ids = set(roster) | set(cur)
    for pid in ids:
        p = players.setdefault(str(pid), {"id": pid})
        r = roster.get(pid)
        if r:
            p.update({"team": r["team"], "team_name": r["team_name"], "number": r["number"], "position": r["position"], "active": True})
            if not p.get("photo"):
                p["photo"] = r["photo"]
            if not p.get("name"):
                p["name"] = r["sq_name"]
        else:
            p["active"] = False           # ha giocato in Serie A quest'anno ma non e' piu' in una rosa
            if pid in cur and cur[pid]:
                b = cur[pid][-1]
                p.setdefault("team", b["team"]["id"]); p.setdefault("team_name", b["team"]["name"]); p.setdefault("position", b["games"].get("position"))
        p["cur"] = cur.get(pid, [])
        p["cur_season"] = SEASON
    print("  stagione corrente: %d giocatori con statistiche" % len(cur))
    _save("players.json", dict(P, updated=now_iso(), season=SEASON, league=PLAYER_LEAGUE))
    # 3) profili mancanti (in rosa ma senza presenze): 1 chiamata ciascuno, poi in cache
    miss = [pid for pid in ids if not players[str(pid)].get("birth")]
    for i, pid in enumerate(miss):
        res = af_one("/players", id=pid, season=SEASON) or af_one("/players/profiles", player=pid) or []
        if res:
            players[str(pid)].update(profile_of(res[0]["player"]))
            if res[0].get("statistics") and not players[str(pid)].get("cur"):
                players[str(pid)]["cur"] = [trim_block(s) for s in res[0]["statistics"] if (s.get("league") or {}).get("id") == PLAYER_LEAGUE]
        if (i + 1) % 50 == 0:
            _save("players.json", dict(P, updated=now_iso(), season=SEASON, league=PLAYER_LEAGUE))
    print("  profili scaricati:", len(miss))
    # 4) stagione precedente, tutte le competizioni: in cache per sempre (non cambia piu')
    todo = [pid for pid in ids if players[str(pid)].get("prev_season") != prev_season]
    for i, pid in enumerate(todo):
        res = af_one("/players", id=pid, season=prev_season) or []
        players[str(pid)]["prev"] = [trim_block(s) for s in (res[0].get("statistics", []) if res else [])]
        players[str(pid)]["prev_season"] = prev_season
        if (i + 1) % 50 == 0:
            _save("players.json", dict(P, updated=now_iso(), season=SEASON, league=PLAYER_LEAGUE))
            print("    stagione precedente: %d/%d" % (i + 1, len(todo)))
    print("  stagione precedente scaricata per %d giocatori" % len(todo))
    # 5) trasferimenti: per squadra (20 chiamate, coprono i movimenti che toccano la Serie A), poi per giocatore solo a chi manca
    seed = {}
    for t in teams:
        for it in af_get("/transfers", team=t["team"]["id"]):
            seed.setdefault(it["player"]["id"], []).extend(it.get("transfers") or [])
        time.sleep(PAUSE)
    solo = 0
    for pid in ids:
        p = players[str(pid)]
        if pid in seed:
            p["transfers"] = trim_transfers(seed[pid])
        elif "transfers" not in p:
            res = af_one("/transfers", player=pid) or []
            p["transfers"] = trim_transfers(res[0].get("transfers") if res else [])
            solo += 1
    print("  trasferimenti: da squadre %d giocatori, chiamate singole %d" % (len(seed), solo))
    # 6) chi non e' piu' ne' in rosa ne' nei tabellini resta in cache ma inattivo (serve alle pagine dei voti passati)
    for k, p in players.items():
        if int(k) not in ids:
            p["active"] = False
    P.update({"updated": now_iso(), "season": SEASON, "league": PLAYER_LEAGUE})
    _save("players.json", P)
    return P

def main():
    args = sys.argv[1:]
    do_teams = "--squadre" in args or not any(a.startswith("--") for a in args)
    do_players = "--giocatori" in args or not any(a.startswith("--") for a in args)
    t0 = time.time()
    if do_teams:
        print("squadre e classifiche"); pull_teams()
        print("partite"); pull_matches()
    if do_players:
        print("giocatori"); pull_players()
    print("stats_pull OK: %d chiamate API, %.0fs" % (n_calls(), time.time() - t0))

if __name__ == "__main__":
    main()
