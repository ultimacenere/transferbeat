#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""TransferBeat - rosters.py: scarica le rose attuali (football-data.org) e le salva
in data/rosters.json (club -> giocatori). Free tier: 3 chiamate (SA, PD, PL)."""
import json, os, sys, time, unicodedata
try:
    import requests
except ImportError:
    print("manca requests"); sys.exit(1)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
CODES = ["SA", "PD", "PL"]
ALIAS = {"Atleti": "Atlético Madrid", "Barça": "Barcelona", "Athletic": "Athletic Club",
         "Celta": "Celta Vigo", "Sevilla FC": "Sevilla", "Brighton Hove": "Brighton",
         "Leeds United": "Leeds", "Nottingham": "Nottingham Forest", "Wolverhampton": "Wolves"}

def get_key():
    k = os.environ.get("FOOTBALL_DATA_KEY", "").strip()
    if k:
        return k
    try:
        return open(os.path.join(ROOT, "football_data_key.txt")).read().strip()
    except Exception:
        return ""

def deac(s):
    return unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode("ascii").lower().strip()

def board_names():
    try:
        b = json.load(open(os.path.join(DATA, "it", "board.json"), encoding="utf-8"))
        return set(b.get("squadre", {}).keys())
    except Exception:
        return set()

def resolve(team, BN):
    sn = team.get("shortName") or team.get("name") or ""
    if sn in BN:
        return sn
    if sn in ALIAS:
        return ALIAS[sn]
    d = deac(sn)
    for bn in BN:
        if d and (d in deac(bn) or deac(bn) in d):
            return bn
    return sn

def fetch(code, key):
    r = requests.get("https://api.football-data.org/v4/competitions/%s/teams" % code,
                     headers={"X-Auth-Token": key}, timeout=30)
    r.raise_for_status()
    return r.json().get("teams", [])

import calendar
def _is_fresh(days=5):
    try:
        d = json.load(open(os.path.join(DATA, "rosters.json"), encoding="utf-8"))
        ts = calendar.timegm(time.strptime(d.get("updated", ""), "%Y-%m-%dT%H:%M:%SZ"))
        return (time.time() - ts) < days * 86400
    except Exception:
        return False

def main():
    key = get_key()
    if not key:
        print("nessuna chiave football-data (FOOTBALL_DATA_KEY o football_data_key.txt) - salto")
        return
    if _is_fresh(5) and not os.environ.get("FORCE_ROSTERS"):
        print("rose ancora fresche (<5 giorni) - salto refresh"); return
    BN = board_names()
    rose = {}; unresolved = []
    for i, code in enumerate(CODES):
        if i:
            time.sleep(7)
        try:
            teams = fetch(code, key)
        except Exception as e:
            print("  errore", code, str(e)[:80]); continue
        for t in teams:
            club = resolve(t, BN)
            if club not in BN:
                unresolved.append(t.get("shortName"))
            sq = [p.get("name") for p in t.get("squad", []) if p.get("name")]
            if sq:
                rose[club] = sq
    if not rose:
        print("nessuna rosa scaricata - non sovrascrivo"); return
    out = {"updated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "rose": rose}
    json.dump(out, open(os.path.join(DATA, "rosters.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print("rose:", len(rose), "club,", sum(len(v) for v in rose.values()), "giocatori")
    if unresolved:
        print("NON risolti:", unresolved)

if __name__ == "__main__":
    main()
