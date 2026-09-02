#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""TransferBeat - competizioni.py: classifiche, calendario/risultati e marcatori di campionati e coppe.
Fonte: football-data.org (tier gratuito, chiave in football_data_key.txt o FOOTBALL_DATA_KEY). Dati deterministici,
niente LLM. Limite 10 richieste/minuto -> pausa fra le chiamate. Produce data/competizioni.json (letto da campionati.html).
Uso: python scripts/competizioni.py            (tutte le competizioni)
     COMPS=SA,CL python scripts/competizioni.py (solo alcune)"""
import json, os, sys, time
from datetime import datetime, timezone
try:
    import requests
except ImportError:
    print("manca requests"); sys.exit(1)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
API = "https://api.football-data.org/v4"
PAUSA = float(os.environ.get("FD_PAUSA", "6.5"))     # 10 req/min sul tier gratuito
COMPS = [c for c in os.environ.get("COMPS", "SA,CL,PL,PD,BL1,FL1").split(",") if c]
NOMI = {"SA": {"it": "Serie A", "en": "Serie A", "es": "Serie A"}, "CL": {"it": "Champions League", "en": "Champions League", "es": "Champions League"},
        "PL": {"it": "Premier League", "en": "Premier League", "es": "Premier League"}, "PD": {"it": "Liga", "en": "LaLiga", "es": "LaLiga"},
        "BL1": {"it": "Bundesliga", "en": "Bundesliga", "es": "Bundesliga"}, "FL1": {"it": "Ligue 1", "en": "Ligue 1", "es": "Ligue 1"}}

def key():
    k = os.environ.get("FOOTBALL_DATA_KEY", "").strip()
    if k:
        return k
    try:
        return open(os.path.join(ROOT, "football_data_key.txt")).read().strip()
    except Exception:
        return ""

def get(path, **params):
    for attempt in range(3):
        r = requests.get(API + path, headers={"X-Auth-Token": key()}, params=params, timeout=30)
        if r.status_code == 429:
            time.sleep(20); continue
        r.raise_for_status()
        time.sleep(PAUSA)
        return r.json()
    raise RuntimeError("429 persistente su " + path)

def team(t):
    return {"id": t.get("id"), "name": t.get("name") or "", "short": t.get("shortName") or t.get("name") or "",
            "tla": t.get("tla") or "", "crest": t.get("crest") or ""}

def conv_standings(j):
    out = []
    for st in j.get("standings", []):
        if st.get("type") not in (None, "TOTAL"):
            continue
        rows = [{"pos": r.get("position"), "team": team(r.get("team") or {}), "pg": r.get("playedGames", 0), "v": r.get("won", 0),
                 "n": r.get("draw", 0), "p": r.get("lost", 0), "gf": r.get("goalsFor", 0), "gs": r.get("goalsAgainst", 0),
                 "dr": r.get("goalDifference", 0), "pt": r.get("points", 0), "form": r.get("form") or ""} for r in st.get("table", [])]
        out.append({"group": st.get("group") or st.get("stage") or "", "table": rows})
    season = j.get("season") or {}
    return out, season.get("currentMatchday"), (j.get("competition") or {}).get("emblem", "")

def conv_match(m):
    sc = m.get("score") or {}; ft = sc.get("fullTime") or {}; ht = sc.get("halfTime") or {}
    return {"id": m.get("id"), "utc": m.get("utcDate", ""), "status": m.get("status", ""), "matchday": m.get("matchday"),
            "stage": m.get("stage", ""), "group": m.get("group") or "",
            "home": team(m.get("homeTeam") or {}), "away": team(m.get("awayTeam") or {}),
            "ft": [ft.get("home"), ft.get("away")] if ft.get("home") is not None else None,
            "ht": [ht.get("home"), ht.get("away")] if ht.get("home") is not None else None,
            "winner": sc.get("winner")}

def main():
    if not key():
        print("manca la chiave football-data (football_data_key.txt o FOOTBALL_DATA_KEY)"); sys.exit(1)
    out = {"aggiornato": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "competizioni": []}
    for code in COMPS:
        try:
            try:
                tables, giornata, emblem = conv_standings(get("/competitions/%s/standings" % code))
            except requests.HTTPError as e:   # coppe prima della fase a gironi/campionato: classifica non ancora disponibile
                if e.response is not None and e.response.status_code == 404:
                    tables, giornata, emblem = [], None, ""; time.sleep(PAUSA)
                else:
                    raise
            matches = [conv_match(m) for m in get("/competitions/%s/matches" % code).get("matches", [])]
            sc = get("/competitions/%s/scorers" % code, limit=15)
            marcatori = [{"name": (s.get("player") or {}).get("name", ""), "team": team(s.get("team") or {}),
                          "goals": s.get("goals") or 0, "assists": s.get("assists") or 0, "pen": s.get("penalties") or 0}
                         for s in sc.get("scorers", [])]
        except Exception as e:
            print(code, "ERRORE:", str(e)[:120]); continue
        # giornata corrente: quella dell'API o, se manca, la prima con partite non giocate
        mds = sorted({m["matchday"] for m in matches if m["matchday"]})
        if not giornata:
            pend = [m["matchday"] for m in matches if m["status"] not in ("FINISHED", "AWARDED") and m["matchday"]]
            giornata = min(pend) if pend else (mds[-1] if mds else 1)
        keep = [d for d in mds if giornata - 1 <= d <= giornata + 2]
        giornate = {}
        for d in keep:
            gm = sorted([m for m in matches if m["matchday"] == d], key=lambda x: x["utc"])
            giornate[str(d)] = gm
        # fase a eliminazione (coppe): partite fuori dalla league phase, raggruppate per stage
        stages = {}
        for m in matches:
            if m["stage"] and m["stage"] not in ("REGULAR_SEASON", "LEAGUE_STAGE", "GROUP_STAGE"):
                stages.setdefault(m["stage"], []).append(m)
        for st in stages:
            stages[st].sort(key=lambda x: x["utc"])
        played = sum(1 for m in matches if m["status"] in ("FINISHED", "AWARDED"))
        out["competizioni"].append({"code": code, "nome": NOMI.get(code, {"it": code, "en": code, "es": code}), "emblem": emblem,
                                    "giornata": giornata, "giornate": giornate, "classifica": tables, "marcatori": marcatori,
                                    "stages": stages, "partite_totali": len(matches), "partite_giocate": played})
        print("%s: giornata %s, %d squadre in classifica, %d partite (%d giocate), %d marcatori" %
              (code, giornata, sum(len(t["table"]) for t in tables), len(matches), played, len(marcatori)))
    os.makedirs(DATA, exist_ok=True)
    with open(os.path.join(DATA, "competizioni.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False)
    print("OK:", len(out["competizioni"]), "competizioni ->", os.path.relpath(os.path.join(DATA, "competizioni.json"), ROOT))
    if not out["competizioni"]:
        sys.exit(1)

if __name__ == "__main__":
    main()
