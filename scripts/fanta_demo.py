#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""FantaTB - strumento demo/test. Usa la service key (supabase_keys.txt), quindi bypassa le regole: SOLO per prove.
  py fanta_demo.py bots <CODICE_INVITO> [n=7]              crea n account bot (botN@fantatb.test / fantatb-botN) e li iscrive
  py fanta_demo.py rose <CODICE_INVITO>                    riempie le rose di TUTTE le squadre con giocatori casuali (slot e crediti ok)
  py fanta_demo.py bilancia <CODICE_INVITO> [--check] [--seed=N]  RIFA le rose di tutte le squadre bilanciate sul FVM (simulazione reale):
                                                           prezzi in scala sul budget, formazioni migliori, giornate ricalcolate, fase campionato
  py fanta_demo.py formazioni <CODICE_INVITO> <G> [tutti]  formazioni dei bot (o di tutti) per la giornata G
  py fanta_demo.py pulisci <CODICE_INVITO>                 elimina bot, rose, formazioni, calendario e risultati; l'admin resta, crediti pieni
  py fanta_demo.py elimina <CODICE_INVITO>                 elimina la lega intera (e i bot)"""
import sys, os, json, random
from fanta_common import *

TEAMS = ["Real Marzapane", "Atletico Divano", "Dinamo Panchina", "Sporting Grigliata", "Inter Nos", "Bayern Leverkusen di Sotto",
         "Fanta Ultimacenere", "Lokomotiv Tinello", "Borussia Scaldabagno", "Deportivo Merenda", "Olympique Ciabatta", "Juventus Bassa"]
URL, KEY = supabase_conf()
H = {"apikey": KEY, "Authorization": "Bearer " + KEY, "Content-Type": "application/json"}

def req(path, data=None, method=None, prefer=None, auth=None):
    h = dict(H); h["Prefer"] = prefer or "return=representation"
    if auth:
        h["Authorization"] = "Bearer " + auth
    r = requests.request(method or ("POST" if data is not None else "GET"), URL + path, headers=h,
                         data=json.dumps(data) if data is not None else None, timeout=60)
    if r.status_code >= 300:
        raise RuntimeError("%s %s -> %s %s" % (method or "GET/POST", path, r.status_code, r.text[:200]))
    return r.json() if r.text else None

def league(code):
    l = req("/rest/v1/leagues?select=*&invite_code=eq." + code.upper())
    if not l:
        print("lega non trovata:", code); sys.exit(1)
    return l[0]

def members(lid):
    return req("/rest/v1/league_members?select=user_id,team_name,role,credits,call_order&league_id=eq.%s&order=call_order" % lid)

def bot_users():
    return {u["email"]: u["id"] for u in req("/auth/v1/admin/users?per_page=200")["users"] if u["email"].endswith("@fantatb.test")}

def cmd_bots(code, n=7):
    l = league(code); have = bot_users()
    for i in range(1, int(n) + 1):
        email, pw, team = "bot%d@fantatb.test" % i, "fantatb-bot%d" % i, TEAMS[(i - 1) % len(TEAMS)]
        if email not in have:
            req("/auth/v1/admin/users", {"email": email, "password": pw, "email_confirm": True, "user_metadata": {"username": "bot%d" % i}})
        tok = req("/auth/v1/token?grant_type=password", {"email": email, "password": pw})["access_token"]
        try:
            req("/rest/v1/rpc/join_league", {"p_code": l["invite_code"], "p_team": team}, auth=tok, prefer="return=minimal")
            print("iscritto:", email, "->", team)
        except RuntimeError as e:
            print("bot%d:" % i, str(e)[-80:])
    print("squadre in lega:", len(members(l["id"])))

def cmd_rose(code):
    l = league(code); slots = l["settings"].get("slots") or {"P": 3, "D": 8, "C": 8, "A": 6}; credits = l["settings"].get("credits", 500)
    players = req("/rest/v1/players?select=id,name,role,price&active=eq.true&limit=2000")
    rosters = req("/rest/v1/rosters?select=player_id,user_id,price&league_id=eq." + l["id"])
    taken = {r["player_id"] for r in rosters}; role = {p["id"]: p["role"] for p in players}; random.seed()
    for m in members(l["id"]):
        mine = [r for r in rosters if r["user_id"] == m["user_id"]]
        need = {r: slots[r] - sum(1 for x in mine if role.get(x["player_id"]) == r) for r in slots}
        budget = credits - sum(x["price"] for x in mine)
        if sum(need.values()) == 0:
            print(m["team_name"], "già completa"); continue
        for _ in range(60):
            pick = []
            for r in slots:
                pool = sorted([p for p in players if p["role"] == r and p["id"] not in taken and p not in pick], key=lambda p: -p["price"])
                k = min(need[r], random.randint(0, 2)); pick += random.sample(pool[:25], k) + random.sample(pool[25:], need[r] - k)
            cost = sum(p["price"] for p in pick)
            if cost <= budget:
                break
        else:
            print("!! budget insufficiente per", m["team_name"]); continue
        req("/rest/v1/rosters", [{"league_id": l["id"], "player_id": p["id"], "user_id": m["user_id"], "price": p["price"]} for p in pick], prefer="return=minimal")
        req("/rest/v1/league_members?league_id=eq.%s&user_id=eq.%s" % (l["id"], m["user_id"]), {"credits": budget - cost}, "PATCH", "return=minimal")
        taken.update(p["id"] for p in pick)
        print("%-28s +%d giocatori, spesi %d, restano %d" % (m["team_name"], len(pick), cost, budget - cost))

def cmd_formazioni(code, md, who="bot"):
    l = league(code); md = int(md); bots = set(bot_users().values()); bmax = l["settings"].get("bench_size", 7)
    players = req("/rest/v1/players?select=id,role,price&limit=2000"); role = {p["id"]: p["role"] for p in players}; price = {p["id"]: p["price"] for p in players}
    rosters = req("/rest/v1/rosters?select=player_id,user_id&league_id=eq." + l["id"]); rows = []
    for m in members(l["id"]):
        if who != "tutti" and m["user_id"] not in bots:
            continue
        mine = [r["player_id"] for r in rosters if r["user_id"] == m["user_id"]]
        module = random.choice(["4-3-3", "3-4-3", "4-4-2", "3-5-2", "4-5-1"]); d, c, a = map(int, module.split("-")); st = []
        for r, n in (("P", 1), ("D", d), ("C", c), ("A", a)):
            st += sorted([x for x in mine if role.get(x) == r], key=lambda x: -price[x])[:n]
        bench = [x for x in sorted(mine, key=lambda x: ("PDCA".index(role.get(x, "C")), -price[x])) if x not in st][:bmax]
        if len(st) == 11:
            rows.append({"league_id": l["id"], "user_id": m["user_id"], "matchday": md, "module": module, "starters": st, "bench": bench})
        else:
            print("rosa incompleta:", m["team_name"])
    if rows:
        req("/rest/v1/lineups?on_conflict=league_id,user_id,matchday", rows, prefer="resolution=merge-duplicates,return=minimal")
    print("formazioni salvate per la giornata %d: %d" % (md, len(rows)))

def cmd_pulisci(code):
    l = league(code); bots = bot_users(); lid = l["id"]
    for t in ("results", "league_fixtures", "lineups", "rosters", "auction_bids", "rating_overrides"):
        req("/rest/v1/%s?league_id=eq.%s" % (t, lid), method="DELETE", prefer="return=minimal")
    req("/rest/v1/auctions?league_id=eq." + lid, {"status": "idle", "player_id": None, "current_bid": None, "bidder_id": None}, "PATCH", "return=minimal")
    for email, uid in bots.items():
        req("/rest/v1/league_members?league_id=eq.%s&user_id=eq.%s" % (lid, uid), method="DELETE", prefer="return=minimal")
        req("/auth/v1/admin/users/" + uid, method="DELETE", prefer="return=minimal")
    req("/rest/v1/league_members?league_id=eq." + lid, {"credits": l["settings"].get("credits", 500)}, "PATCH", "return=minimal")
    print("lega '%s' ripulita: restano %d squadre, bot eliminati: %d" % (l["name"], len(members(lid)), len(bots)))

def cmd_elimina(code):
    l = league(code)
    req("/rest/v1/leagues?id=eq." + l["id"], method="DELETE", prefer="return=minimal")   # prima la lega (cascata su calendario, rose, formazioni)
    for email, uid in bot_users().items():
        req("/auth/v1/admin/users/" + uid, method="DELETE", prefer="return=minimal")
    print("lega eliminata:", l["name"])

def _val(p):
    """valore di mercato: FVM ufficiale Fantacalcio.it (base 1000, in stats.qt), altrimenti quotazione x 10"""
    v = ((p.get("stats") or {}).get("qt") or {}).get("fvm")
    return float(v) if v else float(p["price"]) * 10

def cmd_bilancia(code, *opts):
    """rose bilanciate per TUTTE le squadre (simulazione reale): draft a serpentina sul FVM per ruolo + scambi correttivi,
    prezzi pagati in scala così che ognuno spenda quasi tutto il budget, formazioni migliori per le giornate già calcolate
    e per la prossima, giornate ricalcolate, fase 'campionato'. Con --check stampa solo il piano. --seed=N per ripetere."""
    check = "--check" in opts; seed = next((int(o.split("=")[1]) for o in opts if o.startswith("--seed=")), None)
    rnd = random.Random(seed)
    l = league(code); lid = l["id"]; s = l["settings"]; slots = s.get("slots") or {"P": 3, "D": 8, "C": 8, "A": 6}
    credits = s.get("credits", 500); bmax = s.get("bench_size", 7)
    mem = members(lid); n = len(mem)
    if n < 2:
        print("servono almeno 2 squadre"); sys.exit(1)
    players = req("/rest/v1/players?select=id,name,role,team,price,stats&active=eq.true&limit=2000")
    sch = json.load(open(os.path.join(DATA, "schede.json"), encoding="utf-8")).get("players", {})
    for p in players:
        p["val"] = _val(p); p["tit"] = (sch.get(str(p["id"])) or {}).get("tit") or 0
    miss = [p["name"] for p in players if not ((p.get("stats") or {}).get("qt") or {}).get("fvm")]
    print("squadre: %d  giocatori attivi: %d  senza FVM: %d %s" % (n, len(players), len(miss), miss[:5]))
    order = list(range(n)); rnd.shuffle(order); rosa = {i: [] for i in range(n)}
    for k, r in enumerate("PDCA"):   # serpentina: fascia per fascia, ogni ruolo parte da una squadra diversa
        pool = sorted([p for p in players if p["role"] == r], key=lambda p: (-p["val"], -p["price"], -p["tit"]))[:n * slots[r]]
        start = (k * 3) % n
        for b in range(slots[r]):
            seq = order[start:] + order[:start]
            if b % 2:
                seq = seq[::-1]
            for i, t in enumerate(seq):
                rosa[t].append(pool[b * n + i])
    tot = lambda t: sum(p["val"] for p in rosa[t])
    for _ in range(500):   # scambi correttivi a parità di ruolo tra la squadra più forte e la più debole
        hi = max(rosa, key=tot); lo = min(rosa, key=tot); gap = tot(hi) - tot(lo); best = None
        for a in rosa[hi]:
            for b in rosa[lo]:
                d = a["val"] - b["val"]
                if a["role"] == b["role"] and 0 < d < gap:
                    ng = abs(gap - 2 * d)
                    if ng < gap and (best is None or ng < best[0]):
                        best = (ng, a, b)
        if not best:
            break
        _, a, b = best; rosa[hi].remove(a); rosa[lo].remove(b); rosa[hi].append(b); rosa[lo].append(a)
    rows, spend, paid = [], {}, {}
    for t in rosa:   # prezzi pagati: FVM in scala sul budget della squadra (resto casuale 0-6), minimo 1, somma esatta
        target = credits - rnd.randint(0, 6); k = target / tot(t)
        pr = {p["id"]: max(1, int(round(p["val"] * k))) for p in rosa[t]}
        diff = target - sum(pr.values()); ordered = sorted(rosa[t], key=lambda p: -p["val"]); i = 0
        while diff != 0:
            p = ordered[i % len(ordered)]; i += 1
            if diff > 0:
                pr[p["id"]] += 1; diff -= 1
            elif pr[p["id"]] > 1:
                pr[p["id"]] -= 1; diff += 1
        spend[t] = sum(pr.values()); paid[t] = pr
        rows += [{"league_id": lid, "player_id": p["id"], "user_id": mem[t]["user_id"], "price": pr[p["id"]]} for p in rosa[t]]
    mds = sorted({x["matchday"] for x in req("/rest/v1/results?select=matchday&league_id=eq." + lid)})
    todo = mds + [(max(mds) + 1) if mds else 1]
    lus = []
    for t in rosa:   # formazione migliore per valore: modulo che massimizza il valore degli 11, panchina 1P 2D 2C 2A
        by = {r: sorted([p for p in rosa[t] if p["role"] == r], key=lambda p: (-p["val"], -p["tit"])) for r in "PDCA"}
        cands = []
        for mod in ("3-4-3", "3-5-2", "4-3-3", "4-4-2", "4-5-1", "5-3-2", "5-4-1"):
            d, c, a = map(int, mod.split("-"))
            if len(by["D"]) < d or len(by["C"]) < c or len(by["A"]) < a:
                continue
            st = by["P"][:1] + by["D"][:d] + by["C"][:c] + by["A"][:a]
            cands.append((sum(p["val"] for p in st), mod, st, (d, c, a)))
        vmax = max(x[0] for x in cands)   # un modulo a caso tra quelli entro il 3% del migliore, per non avere 8 squadre uguali
        v, mod, st, (d, c, a) = rnd.choice([x for x in cands if x[0] >= vmax * 0.97]); sid = {p["id"] for p in st}
        bench = (by["P"][1:2] + by["D"][d:d + 2] + by["C"][c:c + 2] + by["A"][a:a + 2])[:bmax]
        for md in todo:
            lus.append({"league_id": lid, "user_id": mem[t]["user_id"], "matchday": md, "module": mod,
                        "starters": [p["id"] for p in st], "bench": [p["id"] for p in bench]})
        rosa[t].sort(key=lambda p: ("PDCA".index(p["role"]), -p["val"]))
        top = ", ".join("%s %d" % (p["name"], paid[t][p["id"]]) for p in sorted(rosa[t], key=lambda p: -p["val"])[:3])
        print("%-28s FVM %5.0f  spesa %3d  resto %2d  %s  top: %s" % (mem[t]["team_name"], tot(t), spend[t], credits - spend[t], mod, top))
    vals = [tot(t) for t in rosa]
    print("scarto FVM tra la più forte e la più debole: %.1f%%   giornate da ricalcolare: %s   prossima: %d" % (
        (max(vals) - min(vals)) / max(vals) * 100, mds, todo[-1]))
    if check:
        print("(--check: nessuna scrittura)"); return
    for tb in ("lineups", "rosters", "auction_bids"):
        req("/rest/v1/%s?league_id=eq.%s" % (tb, lid), method="DELETE", prefer="return=minimal")
    req("/rest/v1/auctions?league_id=eq." + lid, {"status": "idle", "player_id": None, "current_bid": None, "bidder_id": None}, "PATCH", "return=minimal")
    req("/rest/v1/rosters", rows, prefer="return=minimal")
    for t in rosa:
        req("/rest/v1/league_members?league_id=eq.%s&user_id=eq.%s" % (lid, mem[t]["user_id"]), {"credits": credits - spend[t]}, "PATCH", "return=minimal")
    req("/rest/v1/lineups?on_conflict=league_id,user_id,matchday", lus, prefer="resolution=merge-duplicates,return=minimal")
    for md in mds:
        req("/rest/v1/rpc/compute_matchday", {"p_league": lid, "p_matchday": md}); print("giornata %d ricalcolata" % md)
    s["phase"] = "campionato"
    req("/rest/v1/leagues?id=eq." + lid, {"settings": s}, "PATCH", "return=minimal")
    print("fatto: %d rose da %d, %d formazioni (giornate %s), fase 'campionato'" % (n, len(rows) // n, len(lus), todo))

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(__doc__); sys.exit(1)
    {"bots": cmd_bots, "rose": cmd_rose, "bilancia": cmd_bilancia, "formazioni": cmd_formazioni, "pulisci": cmd_pulisci, "elimina": cmd_elimina}[sys.argv[1]](*sys.argv[2:])
