#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""FantaTB - probabili formazioni della prossima giornata, costruite SOLO dai nostri dati (kb/FANTATB.md §20).
Per ogni squadra: modulo e undici dell'ultima formazione ufficiale (API-Football /fixtures/lineups, con la griglia delle posizioni),
probabilità di ogni giocatore dalle ultime 3 formazioni ufficiali (pesi 0,5/0,3/0,2) fusa con l'indice di titolarità (titolari-NN.json),
indisponibili e squalificati dall'indice, sostituti scelti per posizione, ballottaggi quando l'alternativa è vicina.

  py scripts/fanta_probabili.py [giornata]     scrive data/fanta/probabili-NN.json (giornata = ultima rated + 1 se omessa)
Chiamate API: 1 (/fixtures della stagione) + 1 per ogni partita giocata non ancora in cache (data/fanta/lineups.json), quindi ~10 a settimana."""
import sys, os, json, time, datetime, re, unicodedata
from fanta_common import *

SPECIAL = str.maketrans({"ð": "d", "Ð": "D", "đ": "d", "Đ": "D", "ø": "o", "Ø": "O", "ł": "l", "Ł": "L", "ß": "ss", "æ": "ae", "ı": "i", "İ": "I"})
def norm(s):
    s = unicodedata.normalize("NFKD", str(s or "").translate(SPECIAL)).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", " ", s).strip()

def fix_moji(s):
    """Il feed consegna a volte nomi in UTF-8 letto come latin-1 ('OulaÃ¯', 'ObriÄ‡'): li riporto a UTF-8."""
    try:
        if any(ch in (s or "") for ch in ("Ã", "Ä", "Å", "Ð")):
            return s.encode("latin-1").decode("utf-8")
    except Exception:
        pass
    return s or ""

def make_canon(lst):
    """pid del feed -> pid del listone: stesso id, oppure stesso cognome nella stessa squadra (doppioni di id API, kb §16)."""
    by_team = {}
    for p in lst.values():
        by_team.setdefault(p.get("team"), []).append(p)
    cache = {}
    def canon(pid, name, team):
        if pid in lst:
            return pid
        k = (pid, team)
        if k in cache:
            return cache[k]
        toks = [t for t in norm(fix_moji(name)).split() if len(t) >= 3]
        best = None
        for p in by_team.get(team, []):
            ptoks = [t for t in norm(p["name"]).split() if len(t) >= 3]
            if toks and ptoks and (toks[-1] == ptoks[-1] or (len(toks[-1]) >= 5 and any(t.startswith(toks[-1]) or toks[-1].startswith(t) for t in ptoks if len(t) >= 5))):
                if best is None or len(p["name"]) < len(best["name"]):
                    best = p
        cache[k] = best["id"] if best else pid
        return cache[k]
    return canon

W = [0.5, 0.3, 0.2]                      # pesi delle ultime 3 formazioni ufficiali (dalla più recente)
POS_OF_ROLE = {"P": "G", "D": "D", "C": "M", "A": "F"}
ROLE_OF_POS = {"G": "P", "D": "D", "M": "C", "F": "A"}
CACHE = os.path.join(DATA, "lineups.json")

def load_cache():
    try:
        return json.load(open(CACHE, encoding="utf-8"))
    except Exception:
        return {"fixtures": {}}

def lineups_of(fid, cache):
    k = str(fid)
    if k not in cache["fixtures"]:
        lu = af_get("/fixtures/lineups", fixture=fid)
        if not lu:
            return None
        cache["fixtures"][k] = [{"team": t["team"]["id"], "name": t["team"]["name"], "formation": t.get("formation"),
                                 "coach": (t.get("coach") or {}).get("name"),
                                 "xi": [{"id": p["player"]["id"], "name": p["player"]["name"], "pos": p["player"].get("pos"), "grid": p["player"].get("grid")} for p in t.get("startXI", [])],
                                 "bench": [{"id": p["player"]["id"], "name": p["player"]["name"], "pos": p["player"].get("pos")} for p in t.get("substitutes", [])]} for t in lu]
        time.sleep(0.25)
    return cache["fixtures"][k]

def main():
    allfx = af_get("/fixtures", league=LEAGUE_ID, season=SEASON)
    def rnd(f):
        r = f["league"]["round"]
        return int(r.split("-")[-1]) if r.startswith("Regular Season") else 0
    played = {}
    for f in allfx:
        if f["fixture"]["status"]["short"] in ("FT", "AET", "PEN") and rnd(f):
            played.setdefault(rnd(f), []).append(f)
    if len(sys.argv) > 1:
        md = int(sys.argv[1])
    else:
        rated = [m["number"] for m in sb_get("matchdays", {"select": "number,status", "season": "eq.%d" % SEASON, "status": "eq.rated"})]
        md = (max(rated) if rated else (max(played) if played else 0)) + 1
    fixtures = sorted([f for f in allfx if rnd(f) == md], key=lambda f: f["fixture"]["date"])
    if not fixtures:
        raise SystemExit("nessuna partita per la giornata %d" % md)
    # indice di titolarità e listone
    tit = {}
    try:
        t = json.load(open(os.path.join(DATA, "titolari-%02d.json" % md), encoding="utf-8"))
        tit = {s["player_id"]: s for s in t.get("status", [])}
    except Exception:
        pass
    lst = {p["id"]: p for p in json.load(open(os.path.join(DATA, "listone.json"), encoding="utf-8")).get("players", [])}
    cache = load_cache()
    # ultime 3 formazioni ufficiali per squadra (partite finite delle giornate precedenti, dalla più recente)
    recent_fx = [f for r in sorted([r for r in played if r < md], reverse=True)[:5] for f in played[r]]
    hist = {}   # team_id -> [lineup dict più recente prima, ...]
    for f in sorted(recent_fx, key=lambda f: f["fixture"]["date"], reverse=True):
        lu = lineups_of(f["fixture"]["id"], cache)
        for t in (lu or []):
            if len(hist.setdefault(t["team"], [])) < 3:
                t = dict(t); t["fixture"] = f["fixture"]["id"]; t["date"] = f["fixture"]["date"][:10]
                t["opponent"] = f["teams"]["away"]["name"] if f["teams"]["home"]["id"] == t["team"] else f["teams"]["home"]["name"]
                hist[t["team"]].append(t)
    json.dump(cache, open(CACHE, "w", encoding="utf-8"), ensure_ascii=False)
    now = datetime.datetime.utcnow()
    first = min(f["fixture"]["date"] for f in fixtures)
    days = (datetime.datetime.strptime(first[:19], "%Y-%m-%dT%H:%M:%S") - now).total_seconds() / 86400
    stage = "giorno-gara" if days < 1 else ("vigilia" if days <= 3 else "settimana")
    teams = {}
    canon = make_canon(lst)
    for tid, L in hist.items():
        if not L:
            continue
        name = L[0]["name"]
        for lu in L:   # id del feed -> id del listone (doppioni) e nomi ripuliti, una volta sola
            for p in lu["xi"] + lu["bench"]:
                p["id"] = canon(p["id"], p.get("name"), name); p["name"] = fix_moji(p.get("name"))
        score, seen = {}, {}
        for i, lu in enumerate(L):
            w = W[i] if i < len(W) else 0
            for p in lu["xi"]:
                score[p["id"]] = score.get(p["id"], 0) + 100 * w; seen[p["id"]] = seen.get(p["id"]) or p
            for p in lu["bench"]:
                score[p["id"]] = score.get(p["id"], 0) + 15 * w; seen[p["id"]] = seen.get(p["id"]) or p
        last_xi = {p["id"] for p in L[0]["xi"]}
        def info(pid):
            p = seen.get(pid) or {}; lp = lst.get(pid) or {}
            role = lp.get("role") or ROLE_OF_POS.get(p.get("pos") or "", "C")
            return {"id": pid, "name": lp.get("name") or p.get("name") or ("#%d" % pid), "role": role, "pos": p.get("pos") or POS_OF_ROLE[role]}
        prob, why = {}, {}
        for pid in score:
            s = tit.get(pid) or {}
            if s.get("injury") or (s.get("prob") == 0 and "squalific" in (s.get("reason") or "")):
                prob[pid] = 0; why[pid] = s.get("reason") or s.get("injury"); continue
            p0 = min(95, score[pid])
            if pid in last_xi:
                p0 = max(p0, 70)
            if s.get("prob"):
                p0 = 0.7 * p0 + 0.3 * s["prob"]
            prob[pid] = int(round(max(5, min(95, p0))))
            why[pid] = "titolare nelle ultime %d su %d" % (sum(1 for lu in L if pid in {x["id"] for x in lu["xi"]}), len(L))
        # slot dall'ultima formazione: chi è disponibile resta, gli altri vengono sostituiti per posizione
        assigned, xi = set(), []
        avail = lambda pid: prob.get(pid, 0) > 0 and pid not in assigned
        def best_for(pos, grid):
            cands = [pid for pid in prob if avail(pid) and (seen[pid].get("pos") or POS_OF_ROLE[info(pid)["role"]]) == pos]
            same_slot = {x["id"] for lu in L[1:] for x in lu["xi"] if x.get("grid") == grid}
            cands.sort(key=lambda pid: (-(prob[pid] + (8 if pid in same_slot else 0)), info(pid)["name"]))
            return cands[0] if cands else None
        for p in L[0]["xi"]:
            pid = p["id"] if avail(p["id"]) else best_for(p["pos"], p.get("grid"))
            if pid is None:
                continue
            assigned.add(pid); d = info(pid); d.update({"grid": p.get("grid"), "prob": prob[pid], "why": why.get(pid), "ballot": None,
                                                        "out_for": (info(p["id"])["name"] if pid != p["id"] else None)})
            xi.append(d)
        for d in xi:   # ballottaggi: alternativa vicina nella stessa posizione
            alt = [pid for pid in prob if avail(pid) and (seen[pid].get("pos") or POS_OF_ROLE[info(pid)["role"]]) == d["pos"] and prob[pid] >= 30 and prob[pid] >= d["prob"] - 30]
            if alt:
                a = max(alt, key=lambda pid: prob[pid]); assigned.add(a)
                tot = d["prob"] + prob[a]
                d["ballot"] = {"id": a, "name": info(a)["name"], "prob": prob[a], "share": int(round(100 * prob[a] / tot))}
                d["share"] = 100 - d["ballot"]["share"]
        bench = sorted([pid for pid in prob if avail(pid)], key=lambda pid: (-prob[pid], info(pid)["name"]))
        bench_rows = []
        for pos in ("G", "D", "M", "F"):
            bench_rows += [info(pid) | {"prob": prob[pid]} for pid in bench if (seen[pid].get("pos") or POS_OF_ROLE[info(pid)["role"]]) == pos][:2 if pos != "G" else 1]
        out = [info(pid) | {"reason": why[pid], "back_at": (tit.get(pid) or {}).get("back_at")} for pid in prob if prob[pid] == 0]
        doubt = [info(pid) | {"prob": prob[pid], "reason": why[pid]} for pid in prob if 0 < prob[pid] < 60 and pid in last_xi and pid not in assigned]
        teams[name] = {"id": tid, "coach": L[0].get("coach"), "module": L[0].get("formation"), "based_on": [{"fixture": lu["fixture"], "date": lu["date"], "opponent": lu["opponent"], "formation": lu.get("formation")} for lu in L],
                       "xi": xi, "bench": bench_rows, "out": sorted(out, key=lambda x: x["name"]), "doubt": doubt}
    fx_out = [{"id": f["fixture"]["id"], "date": f["fixture"]["date"], "home": f["teams"]["home"]["name"], "away": f["teams"]["away"]["name"],
               "home_id": f["teams"]["home"]["id"], "away_id": f["teams"]["away"]["id"], "venue": (f["fixture"].get("venue") or {}).get("name"), "status": f["fixture"]["status"]["short"]}
              for f in fixtures]
    missing = [n for f in fx_out for n in (f["home"], f["away"]) if n not in teams]
    save_json("probabili-%02d.json" % md, {"updated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "season": SEASON, "matchday": md, "stage": stage,
                                           "fixtures": fx_out, "teams": teams, "missing": missing})
    print("giornata %d (%s): %d partite, %d squadre con probabile, %d senza storico %s, %d chiamate API" % (md, stage, len(fx_out), len(teams), len(missing), missing, calls()))

if __name__ == "__main__":
    main()
