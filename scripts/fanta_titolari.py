#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""FantaTB - indice di titolarità (0-100) per la prossima giornata + infortuni/squalifiche con rientro stimato.
Fonti: player_ratings (minuti ed espulsioni delle ultime 3 giornate), API-Football /injuries (1 chiamata)
e /sidelined per i soli indisponibili (una chiamata ciascuno, per la data di rientro)."""
import sys, time, datetime, math
from fanta_common import *

IT = {"knee": "ginocchio", "ankle": "caviglia", "hamstring": "flessore", "muscle": "muscolare", "muscular": "muscolare",
      "thigh": "coscia", "calf": "polpaccio", "groin": "inguine", "illness": "malattia", "back": "schiena", "shoulder": "spalla",
      "foot": "piede", "hip": "anca", "virus": "virus", "fitness": "condizione", "knock": "botta", "achilles": "achille",
      "adductor": "adduttore", "cruciate": "crociato", "ligament": "legamento", "fracture": "frattura", "concussion": "trauma cranico",
      "injury": "", "suspended": "squalifica", "suspension": "squalifica", "yellow": "", "cards": "", "red": "", "card": ""}
def ita(reason):
    words = [IT.get(w.lower().strip(",."), w.lower()) for w in (reason or "").split()]
    return " ".join(w for w in words if w).strip() or "infortunio"

def main():
    today = datetime.date.today()
    rated = [m["number"] for m in sb_get("matchdays", {"select": "number,status", "season": "eq.%d" % SEASON, "status": "eq.rated"})]
    last = max(rated) if rated else 0
    md = int(sys.argv[1]) if len(sys.argv) > 1 else last + 1
    recent = [n for n in range(md - 3, md) if n >= 1]
    players = [p for p in sb_get("players", {"select": "id,name,active", "limit": "5000"}) if p.get("active")]
    rat = sb_get("player_ratings", {"select": "player_id,matchday,minutes,bonus", "season": "eq.%d" % SEASON,
                                     "matchday": "in.(%s)" % ",".join(map(str, recent)) if recent else "eq.0", "limit": "20000"})
    mins = {}
    for r in rat:
        mins.setdefault(r["player_id"], {})[r["matchday"]] = (r["minutes"], (r.get("bonus") or {}).get("esp", 0))
    unavailable = {}   # pid -> (injury, back_at)
    try:
        now = datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S")
        for it in af_get("/injuries", league=LEAGUE_ID, season=SEASON):
            if (it.get("fixture", {}).get("date") or "") < now:
                continue
            pid = it["player"]["id"]; txt = ((it["player"].get("type") or "") + " " + (it["player"].get("reason") or "")).lower()
            unavailable[pid] = ("squalifica" if "suspend" in txt else "infortunio: " + ita(it["player"].get("reason")), None)
        for pid in list(unavailable):
            if unavailable[pid][0] == "squalifica":
                continue
            try:
                ends = [e.get("end") for e in af_get("/sidelined", player=pid) if e.get("end") and e["end"] >= today.isoformat()]
                if ends:
                    unavailable[pid] = (unavailable[pid][0], min(ends))
            except Exception:
                pass
            time.sleep(0.25)
    except Exception as e:
        print("injuries non disponibili:", e)
    rows = []
    for p in players:
        pid = p["id"]; m = mins.get(pid, {}); injury = None; back = None
        if pid in unavailable:
            injury, back = unavailable[pid]; prob = 0
            weeks = max(1, math.ceil((datetime.date.fromisoformat(back) - today).days / 7)) if back else None
            reason = injury + (" · rientro ~%d sett." % weeks if weeks else "")
        elif last and m.get(last) and m[last][1]:
            prob = 0; injury = "squalifica"; reason = "squalifica: espulso nell'ultima giornata"
        elif not recent or not m:
            prob = 40; reason = "nessun dato recente"
        else:
            starts = sum(1 for n in recent if m.get(n, (0, 0))[0] >= 60)
            subs = sum(1 for n in recent if 1 <= m.get(n, (0, 0))[0] < 60)
            played = [n for n in recent if m.get(n, (0, 0))[0] > 0]
            prob = 90 if (starts == len(recent) and len(recent) >= 2) else max(5, min(95, 15 + 25 * starts + 5 * subs))
            if not played:
                prob = 10
            reason = "titolare %d/%d, subentrato %d/%d nelle ultime giornate" % (starts, len(recent), subs, len(recent)) if played else "mai in campo nelle ultime giornate"
        rows.append({"season": SEASON, "matchday": md, "player_id": pid, "prob": prob, "reason": reason, "injury": injury, "back_at": back})
    save_json("titolari-%02d.json" % md, {"updated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "matchday": md,
                                          "status": [{k: r[k] for k in ("player_id", "prob", "reason", "injury", "back_at")} for r in rows]})
    print("giornata %d: %d giocatori, %d indisponibili, %d chiamate API" % (md, len(rows), len(unavailable), calls()))
    if rows and sb_upsert("player_status", rows, on_conflict="season,matchday,player_id"):
        print("upsert player_status ok")

if __name__ == "__main__":
    main()
